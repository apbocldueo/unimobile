"""Deterministic multi-task and multi-Agent Benchmark suite runtime."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Mapping

from zhixing.benchmark.identity import canonical_hash
from zhixing.benchmark.models import BenchmarkPlan, ExperimentProtocol, TaskInstance
from zhixing.devices.manager import DeviceManager
from zhixing.sdk import ExecutableAgent
from zhixing.benchmark.reporting.writer import finalize_suite_result

from .context import preflight_device
from .lifecycle import execute_environment_calls
from .resolver import BenchmarkComponentResolver, RegistryBenchmarkComponentResolver
from .engine import LifecycleRecorder, execute_task_run, persist_task_manifest
from .materializer import (
    TaskInstancePool,
    build_schedule,
    materialize_task,
)
from .models import (
    BenchmarkCancellationSignal,
    BenchmarkLifecycleEvent,
    BenchmarkOutcome,
    BenchmarkPublicationPolicy,
    BenchmarkRunConfig,
    BenchmarkStageResult,
    BenchmarkStageStatus,
    BenchmarkSuiteResult,
    BenchmarkTaskResult,
)
from .resources import (
    BenchmarkResourceProvider,
    EmptyBenchmarkResourceProvider,
)


def _shared_stage_reference(
    experiment_id: str,
    phase: str,
    boundary: str,
) -> str:
    """Build one portable reference for suite-boundary evidence.

    Args:
        experiment_id (str): Experiment correlation identity.
        phase (str): Shared lifecycle phase.
        boundary (str): Stable boundary identity within the experiment.

    Raises:
        ValueError: Any reference segment is blank.

    Returns:
        str: Logical reference that does not expose a host path.
    """
    if not experiment_id.strip() or not phase.strip() or not boundary.strip():
        raise ValueError("shared stage reference segments must not be blank")
    return f"benchmark-stage://{experiment_id}/{phase}/{boundary}"


def _finalize_if_enabled(
    result: BenchmarkSuiteResult,
    *,
    run_config: BenchmarkRunConfig,
) -> BenchmarkSuiteResult:
    """Finalize suite artifacts unless the runtime caller deferred publication.

    Args:
        result (BenchmarkSuiteResult): Complete in-memory suite facts.
        run_config (BenchmarkRunConfig): Runtime-only publication policy.

    Raises:
        None: Writer failures remain normalized by the reporting finalizer.

    Returns:
        BenchmarkSuiteResult: Original facts or facts with artifact references.
    """
    if (
        run_config.publication_policy
        is BenchmarkPublicationPolicy.DEFER
    ):
        return result
    return finalize_suite_result(
        result,
        artifact_root=run_config.artifact_root,
    )


def _execute_shared_environment_stage(
    *,
    phase: str,
    boundary: str,
    calls: tuple[Mapping[str, Any], ...],
    resolver: BenchmarkComponentResolver,
    resource_provider: BenchmarkResourceProvider,
    device: Any,
    recorder: LifecycleRecorder,
) -> tuple[BenchmarkStageResult, tuple[BenchmarkLifecycleEvent, ...], str]:
    """Execute one reset or cleanup at a shared suite boundary.

    Args:
        phase (str): ``reset`` or ``cleanup``.
        boundary (str): Stable suite or task-batch identity.
        calls (tuple[Mapping[str, Any], ...]): Ordered materialized calls.
        resolver (BenchmarkComponentResolver): Benchmark component boundary.
        resource_provider (BenchmarkResourceProvider): Package resources.
        device (Any): Shared fake or Android device.
        recorder (LifecycleRecorder): Suite lifecycle recorder.

    Raises:
        None: Component failures are normalized into the returned stage.

    Returns:
        tuple[BenchmarkStageResult, tuple[BenchmarkLifecycleEvent, ...], str]:
        Shared stage, its emitted events, and a portable evidence reference.
    """
    phase_name = f"{phase}_shared"
    reference = _shared_stage_reference(
        recorder.experiment_id,
        phase_name,
        boundary,
    )
    event_start = len(recorder.events)
    recorder.emit(
        phase_name,
        "start",
        payload={"boundary": boundary, "evidence_ref": reference},
    )
    try:
        evidence = execute_environment_calls(
            calls,
            requested_phase=phase,
            resolver=resolver,
            resource_provider=resource_provider,
            device=device,
        )
        stage = BenchmarkStageResult(
            phase=phase_name,
            status=BenchmarkStageStatus.SUCCESS,
            evidence={"calls": evidence, "boundary": boundary},
            artifact_refs=(reference,),
        )
        recorder.emit(
            phase_name,
            "complete",
            payload={"boundary": boundary, "evidence_ref": reference},
        )
    except Exception as error:
        stage = BenchmarkStageResult(
            phase=phase_name,
            status=BenchmarkStageStatus.FAILURE,
            error_code=f"benchmark.{phase}.failed",
            message=f"{phase_name} failed ({type(error).__name__})",
            evidence={"boundary": boundary},
            artifact_refs=(reference,),
        )
        recorder.emit(
            phase_name,
            "fail",
            payload={
                "boundary": boundary,
                "evidence_ref": reference,
                "code": stage.error_code,
            },
        )
    return stage, tuple(recorder.events[event_start:]), reference


def _attach_shared_stage(
    results: list[BenchmarkTaskResult],
    indexes: tuple[int, ...],
    *,
    phase: str,
    stage: BenchmarkStageResult,
    events: tuple[BenchmarkLifecycleEvent, ...],
    reference: str,
    invalidate_on_failure: bool,
    run_config: BenchmarkRunConfig,
) -> None:
    """Attach one shared boundary result to every affected task result.

    Args:
        results (list[BenchmarkTaskResult]): Mutable suite result collection.
        indexes (tuple[int, ...]): Affected result indexes.
        phase (str): Per-run stage represented by the shared boundary.
        stage (BenchmarkStageResult): Shared boundary evidence.
        events (tuple[BenchmarkLifecycleEvent, ...]): Shared lifecycle events.
        reference (str): Portable shared evidence reference.
        invalidate_on_failure (bool): Whether failure invalidates each result.
        run_config (BenchmarkRunConfig): Manifest persistence policy.

    Raises:
        None: Manifest rewrite failures are represented as persistence stages.

    Returns:
        None: Results are replaced in place.
    """
    for index in indexes:
        original = results[index]
        replaced_stages = tuple(
            replace(
                item,
                artifact_refs=tuple(
                    dict.fromkeys((*item.artifact_refs, reference))
                ),
            )
            if item.phase == phase
            else item
            for item in original.stages
        )
        outcome = original.outcome
        if (
            invalidate_on_failure
            and stage.status is BenchmarkStageStatus.FAILURE
        ):
            outcome = BenchmarkOutcome.INVALID
        updated = replace(
            original,
            outcome=outcome,
            stages=(*replaced_stages, stage),
            lifecycle_events=(*original.lifecycle_events, *events),
        )
        if run_config.persist_manifests:
            _, persistence_error = persist_task_manifest(
                updated,
                artifact_root=run_config.artifact_root,
            )
            if persistence_error is not None:
                updated = replace(
                    updated,
                    stages=(
                        *updated.stages,
                        BenchmarkStageResult(
                            phase="persistence",
                            status=BenchmarkStageStatus.FAILURE,
                            error_code="benchmark.manifest.write_failed",
                            message=(
                                "Benchmark result manifest could not be rewritten "
                                f"({type(persistence_error).__name__})"
                            ),
                        ),
                    ),
                )
        results[index] = updated


def _invalid_result(
    *,
    plan: BenchmarkPlan,
    protocol: ExperimentProtocol,
    agent_id: str,
    agent: ExecutableAgent,
    task_id: str,
    repeat: int,
    run_config: BenchmarkRunConfig,
    phase: str,
    code: str,
    recorder: LifecycleRecorder,
) -> BenchmarkTaskResult:
    """Create a structured INVALID result before Agent execution.

    Args:
        plan (BenchmarkPlan): Source Plan.
        protocol (ExperimentProtocol): Source Protocol.
        agent_id (str): Candidate Agent name.
        agent (ExecutableAgent): Candidate executable.
        task_id (str): Benchmark task identity.
        repeat (int): Repeat index.
        run_config (BenchmarkRunConfig): Runtime identity.
        phase (str): Failed infrastructure phase.
        code (str): Stable failure code.
        recorder (LifecycleRecorder): Event recorder.

    Raises:
        None.

    Returns:
        BenchmarkTaskResult: Safe invalid result.
    """
    task_run_id = canonical_hash(
        {
            "experiment": run_config.experiment_id,
            "agent": agent_id,
            "task": task_id,
            "repeat": repeat,
            "invalid_phase": phase,
        }
    ).removeprefix("sha256:")[:32]
    recorder.emit(
        phase,
        "fail",
        task_run_id=task_run_id,
        task_id=task_id,
        agent_id=agent_id,
        repeat=repeat,
        payload={"code": code},
    )
    return BenchmarkTaskResult(
        experiment_id=run_config.experiment_id,
        task_run_id=task_run_id,
        task_id=task_id,
        repeat=repeat,
        agent_id=agent_id,
        agent_graph_identity=agent.canonical_hash,
        benchmark_plan_identity=plan.canonical_hash(),
        experiment_protocol_identity=protocol.canonical_hash(),
        task_instance_identity=canonical_hash(
            {"plan": plan.canonical_hash(), "task": task_id, "repeat": repeat}
        ),
        outcome=BenchmarkOutcome.INVALID,
        stages=(
            BenchmarkStageResult(
                phase=phase,
                status=BenchmarkStageStatus.FAILURE,
                error_code=code,
                message=f"{phase} prevented a valid Benchmark run",
            ),
        ),
        lifecycle_events=(recorder.events[-1],),
        fairness_warnings=protocol.fairness_warnings,
    )


def _skipped_result(
    *,
    plan: BenchmarkPlan,
    protocol: ExperimentProtocol,
    agent_id: str,
    agent: ExecutableAgent,
    task_id: str,
    repeat: int,
    run_config: BenchmarkRunConfig,
    reason: str,
) -> BenchmarkTaskResult:
    """Create an explicit suite-policy SKIPPED result.

    Args:
        plan (BenchmarkPlan): Source Plan.
        protocol (ExperimentProtocol): Source Protocol.
        agent_id (str): Candidate Agent name.
        agent (ExecutableAgent): Candidate executable.
        task_id (str): Benchmark task identity.
        repeat (int): Repeat index.
        run_config (BenchmarkRunConfig): Runtime identity.
        reason (str): Stable skip reason.

    Raises:
        None.

    Returns:
        BenchmarkTaskResult: Structured skipped result.
    """
    task_run_id = canonical_hash(
        {
            "experiment": run_config.experiment_id,
            "agent": agent_id,
            "task": task_id,
            "repeat": repeat,
            "skipped": reason,
        }
    ).removeprefix("sha256:")[:32]
    return BenchmarkTaskResult(
        experiment_id=run_config.experiment_id,
        task_run_id=task_run_id,
        task_id=task_id,
        repeat=repeat,
        agent_id=agent_id,
        agent_graph_identity=agent.canonical_hash,
        benchmark_plan_identity=plan.canonical_hash(),
        experiment_protocol_identity=protocol.canonical_hash(),
        task_instance_identity=canonical_hash(
            {"plan": plan.canonical_hash(), "task": task_id, "repeat": repeat}
        ),
        outcome=BenchmarkOutcome.SKIPPED,
        stages=(
            BenchmarkStageResult(
                phase="suite",
                status=BenchmarkStageStatus.SKIPPED,
                message=reason,
            ),
        ),
        fairness_warnings=protocol.fairness_warnings,
    )


class BenchmarkExperimentRuntime:
    """Public Build–Run–Evaluate runtime for graph-native Mobile Agents."""

    def run(
        self,
        plan: BenchmarkPlan,
        protocol: ExperimentProtocol,
        agents: Mapping[str, ExecutableAgent],
        *,
        run_config: BenchmarkRunConfig | None = None,
        resource_provider: BenchmarkResourceProvider | None = None,
        resolver: BenchmarkComponentResolver | None = None,
        device: Any | None = None,
        event_sink: Callable[[BenchmarkLifecycleEvent], None] | None = None,
        cancellation: BenchmarkCancellationSignal | None = None,
    ) -> BenchmarkSuiteResult:
        """Run a deterministic Benchmark suite over one shared device session.

        Args:
            plan (BenchmarkPlan): Pure compiled Benchmark definition.
            protocol (ExperimentProtocol): Enforced experiment policy.
            agents (Mapping[str, ExecutableAgent]): Named graph-native Agents.
            run_config (BenchmarkRunConfig | None): Runtime-only bindings.
            resource_provider (BenchmarkResourceProvider | None): Package resources.
            resolver (BenchmarkComponentResolver | None): Benchmark plugin resolver.
            device (Any | None): Explicit fake or real Android device.
            event_sink (Callable[[BenchmarkLifecycleEvent], None] | None): Live events.
            cancellation (BenchmarkCancellationSignal | None): Optional
                caller-owned cooperative cancellation signal.

        Raises:
            ValueError: Input selection is invalid.

        Returns:
            BenchmarkSuiteResult: Ordered task outcomes and audit evidence.
        """
        config = run_config or BenchmarkRunConfig()
        if (
            config.publication_policy
            is BenchmarkPublicationPolicy.DEFER
            and config.persist_manifests
        ):
            config = replace(config, persist_manifests=False)
        if not agents:
            raise ValueError("Benchmark runtime requires at least one ExecutableAgent")
        if any(not name.strip() for name in agents):
            raise ValueError("Benchmark Agent names must not be blank")
        selected_provider = resource_provider or EmptyBenchmarkResourceProvider()
        selected_resolver = resolver or RegistryBenchmarkComponentResolver()
        recorder = LifecycleRecorder(config.experiment_id, sink=event_sink)
        fairness_warnings = list(protocol.fairness_warnings)
        if (
            protocol.isolation.reset == "before_each_task"
            and len(agents) > 1
        ):
            fairness_warnings.append(
                "benchmark.protocol.shared_device_state_across_agents"
            )
            if protocol.task_materialization.strict_fairness:
                raise ValueError(
                    "strict fairness rejects before_each_task with multiple Agents"
                )
        schedule = build_schedule(
            plan,
            protocol,
            list(agents),
            task_ids=config.task_ids,
        )
        if cancellation is not None and cancellation.is_cancelled():
            cancelled_results = tuple(
                _skipped_result(
                    plan=plan,
                    protocol=protocol,
                    agent_id=entry.agent_id,
                    agent=agents[entry.agent_id],
                    task_id=entry.task_id,
                    repeat=entry.repeat,
                    run_config=config,
                    reason="execution cancelled before device preflight",
                )
                for entry in schedule
            )
            return _finalize_if_enabled(
                BenchmarkSuiteResult(
                    experiment_id=config.experiment_id,
                    benchmark_plan_identity=plan.canonical_hash(),
                    experiment_protocol_identity=protocol.canonical_hash(),
                    results=cancelled_results,
                    lifecycle_events=tuple(recorder.events),
                    fairness_warnings=tuple(
                        sorted(set(fairness_warnings))
                    ),
                ),
                run_config=config,
            )
        selected_device = device or DeviceManager.get_android_device(config.serial)
        selected_task_ids = {entry.task_id for entry in schedule}
        selected_app_ids = {
            task.app
            for task in plan.tasks
            if task.id in selected_task_ids and task.app is not None
        }
        plan_apps = tuple(
            item for item in plan.apps if item.id in selected_app_ids
        )
        required_apps = tuple(
            {
                item.id: item
                for item in (*plan_apps, *protocol.apps)
            }.values()
        )
        valid_device, provenance = preflight_device(
            selected_device,
            platform=protocol.device.platform,
            locale=protocol.device.locale,
            orientation=protocol.device.orientation,
            apps=required_apps,
        )
        task_by_id = {task.id: task for task in plan.tasks}
        pool = TaskInstancePool()
        materialized_instances: dict[str, TaskInstance] = {}
        materialization_errors: set[str] = set()
        for entry in schedule:
            if cancellation is not None and cancellation.is_cancelled():
                break
            if (
                entry.shared_instance_key in materialized_instances
                or entry.shared_instance_key in materialization_errors
            ):
                continue
            task = task_by_id[entry.task_id]
            try:
                materialized_instances[entry.shared_instance_key] = (
                    pool.get_or_materialize(
                        entry.shared_instance_key,
                        lambda task=task, entry=entry: materialize_task(
                            plan,
                            task,
                            repeat=entry.repeat,
                            seed=entry.seed,
                            resolver=selected_resolver,
                            resource_provider=selected_provider,
                        ),
                    )
                )
            except Exception:
                materialization_errors.add(entry.shared_instance_key)
        results: list[BenchmarkTaskResult] = []
        stop_suite = False
        if not valid_device:
            for entry in schedule:
                results.append(
                    _invalid_result(
                        plan=plan,
                        protocol=protocol,
                        agent_id=entry.agent_id,
                        agent=agents[entry.agent_id],
                        task_id=entry.task_id,
                        repeat=entry.repeat,
                        run_config=config,
                        phase="preflight",
                        code="benchmark.preflight.unverified_or_mismatch",
                        recorder=recorder,
                    )
                )
            return _finalize_if_enabled(
                BenchmarkSuiteResult(
                    experiment_id=config.experiment_id,
                    benchmark_plan_identity=plan.canonical_hash(),
                    experiment_protocol_identity=protocol.canonical_hash(),
                    results=tuple(results),
                    lifecycle_events=tuple(recorder.events),
                    fairness_warnings=tuple(
                        sorted(set(fairness_warnings))
                    ),
                    device_provenance={
                        **provenance,
                        "device_id": config.safe_device_id(),
                    },
                ),
                run_config=config,
            )

        current_batch: tuple[int, str] | None = None
        batch_result_start = 0
        batch_reset_stage: BenchmarkStageResult | None = None
        batch_reset_events: tuple[BenchmarkLifecycleEvent, ...] = ()
        batch_reset_reference = ""
        instance_for_batch: TaskInstance | None = None
        once_cleanup_calls: list[Mapping[str, Any]] = []
        once_cleanup_result_indexes: list[int] = []
        seen_cleanup_instances: set[str] = set()
        once_reset_stage: BenchmarkStageResult | None = None
        once_reset_events: tuple[BenchmarkLifecycleEvent, ...] = ()
        once_reset_reference = ""
        if (
            protocol.isolation.reset == "once"
            and materialized_instances
            and not (
                cancellation is not None
                and cancellation.is_cancelled()
            )
        ):
            reset_calls = tuple(
                call
                for instance in materialized_instances.values()
                for call in instance.environment_initializer
            )
            (
                once_reset_stage,
                once_reset_events,
                once_reset_reference,
            ) = _execute_shared_environment_stage(
                phase="reset",
                boundary="suite",
                calls=reset_calls,
                resolver=selected_resolver,
                resource_provider=selected_provider,
                device=selected_device,
                recorder=recorder,
            )
        agent_ids = tuple(sorted(agents))
        for entry in schedule:
            if cancellation is not None and cancellation.is_cancelled():
                results.append(
                    _skipped_result(
                        plan=plan,
                        protocol=protocol,
                        agent_id=entry.agent_id,
                        agent=agents[entry.agent_id],
                        task_id=entry.task_id,
                        repeat=entry.repeat,
                        run_config=config,
                        reason="execution cancelled before TaskRun",
                    )
                )
                continue
            if stop_suite:
                results.append(
                    _skipped_result(
                        plan=plan,
                        protocol=protocol,
                        agent_id=entry.agent_id,
                        agent=agents[entry.agent_id],
                        task_id=entry.task_id,
                        repeat=entry.repeat,
                        run_config=config,
                        reason="suite stopped by failure policy",
                    )
                )
                continue
            batch = (entry.repeat, entry.task_id)
            if batch != current_batch:
                current_batch = batch
                batch_result_start = len(results)
                batch_reset_stage = None
                batch_reset_events = ()
                batch_reset_reference = ""
                instance_for_batch = None
            if entry.shared_instance_key in materialization_errors:
                result = _invalid_result(
                    plan=plan,
                    protocol=protocol,
                    agent_id=entry.agent_id,
                    agent=agents[entry.agent_id],
                    task_id=entry.task_id,
                    repeat=entry.repeat,
                    run_config=config,
                    phase="materialization",
                    code="benchmark.materialization.failed",
                    recorder=recorder,
                )
                results.append(result)
                if not protocol.failure.initializer.continue_suite:
                    stop_suite = True
                continue
            instance = materialized_instances[entry.shared_instance_key]
            instance_for_batch = instance
            if (
                protocol.isolation.cleanup == "once"
                and entry.shared_instance_key not in seen_cleanup_instances
            ):
                seen_cleanup_instances.add(entry.shared_instance_key)
                once_cleanup_calls.extend(instance.cleanup_initializer)

            if (
                protocol.isolation.reset == "before_each_task"
                and batch_reset_stage is None
            ):
                (
                    batch_reset_stage,
                    batch_reset_events,
                    batch_reset_reference,
                ) = _execute_shared_environment_stage(
                    phase="reset",
                    boundary=f"repeat-{entry.repeat}-task-{entry.task_id}",
                    calls=tuple(instance.environment_initializer),
                    resolver=selected_resolver,
                    resource_provider=selected_provider,
                    device=selected_device,
                    recorder=recorder,
                )
                if cancellation is not None and cancellation.is_cancelled():
                    results.append(
                        _skipped_result(
                            plan=plan,
                            protocol=protocol,
                            agent_id=entry.agent_id,
                            agent=agents[entry.agent_id],
                            task_id=entry.task_id,
                            repeat=entry.repeat,
                            run_config=config,
                            reason="execution cancelled after shared reset",
                        )
                    )
                    continue
            selected_shared_reset = (
                once_reset_stage
                if protocol.isolation.reset == "once"
                else batch_reset_stage
            )
            selected_reset_events = (
                once_reset_events
                if protocol.isolation.reset == "once"
                else batch_reset_events
            )
            selected_reset_reference = (
                once_reset_reference
                if protocol.isolation.reset == "once"
                else batch_reset_reference
            )
            if (
                selected_shared_reset is not None
                and selected_shared_reset.status
                is BenchmarkStageStatus.FAILURE
            ):
                result = _invalid_result(
                    plan=plan,
                    protocol=protocol,
                    agent_id=entry.agent_id,
                    agent=agents[entry.agent_id],
                    task_id=entry.task_id,
                    repeat=entry.repeat,
                    run_config=config,
                    phase="reset_shared",
                    code="benchmark.reset.failed",
                    recorder=recorder,
                )
                results.append(result)
                _attach_shared_stage(
                    results,
                    (len(results) - 1,),
                    phase="reset_shared",
                    stage=selected_shared_reset,
                    events=selected_reset_events,
                    reference=selected_reset_reference,
                    invalidate_on_failure=True,
                    run_config=config,
                )
                if not protocol.failure.initializer.continue_suite:
                    stop_suite = True
                continue

            execute_reset = protocol.isolation.reset == "before_each_agent"
            execute_cleanup = protocol.isolation.cleanup == "after_each_run"
            result = execute_task_run(
                plan=plan,
                protocol=protocol,
                task_instance=instance,
                agent_id=entry.agent_id,
                agent=agents[entry.agent_id],
                run_config=config,
                resolver=selected_resolver,
                resource_provider=selected_provider,
                device=selected_device,
                recorder=recorder,
                execute_reset=execute_reset,
                execute_cleanup=execute_cleanup,
                shared_stage_refs=(
                    (selected_reset_reference,)
                    if selected_reset_reference
                    else ()
                ),
                cancellation=cancellation,
            )
            results.append(result)
            if selected_shared_reset is not None:
                _attach_shared_stage(
                    results,
                    (len(results) - 1,),
                    phase="reset",
                    stage=selected_shared_reset,
                    events=selected_reset_events,
                    reference=selected_reset_reference,
                    invalidate_on_failure=True,
                    run_config=config,
                )
            if protocol.isolation.cleanup == "once":
                once_cleanup_result_indexes.append(len(results) - 1)

            is_last_agent = entry.agent_id == agent_ids[-1]
            if (
                protocol.isolation.cleanup == "after_each_task"
                and is_last_agent
                and instance_for_batch is not None
            ):
                (
                    shared_stage,
                    shared_events,
                    shared_reference,
                ) = _execute_shared_environment_stage(
                    phase="cleanup",
                    boundary=f"repeat-{entry.repeat}-task-{entry.task_id}",
                    calls=tuple(instance_for_batch.cleanup_initializer),
                    resolver=selected_resolver,
                    resource_provider=selected_provider,
                    device=selected_device,
                    recorder=recorder,
                )
                _attach_shared_stage(
                    results,
                    tuple(range(batch_result_start, len(results))),
                    phase="cleanup",
                    stage=shared_stage,
                    events=shared_events,
                    reference=shared_reference,
                    invalidate_on_failure=(
                        protocol.failure.cleanup.outcome.value == "invalidate"
                    ),
                    run_config=config,
                )
            failure_rules = {
                "reset": protocol.failure.initializer,
                "setup": protocol.failure.initializer,
                "evaluator_pre": protocol.failure.evaluator,
                "agent": protocol.failure.agent,
                "evaluation": protocol.failure.evaluator,
                "cleanup": protocol.failure.cleanup,
                "cleanup_shared": protocol.failure.cleanup,
            }
            for stage in results[-1].stages:
                if (
                    stage.status is BenchmarkStageStatus.FAILURE
                    and stage.phase in failure_rules
                    and not failure_rules[stage.phase].continue_suite
                ):
                    stop_suite = True
                    break

        if protocol.isolation.cleanup == "once" and once_cleanup_result_indexes:
            (
                suite_cleanup,
                suite_cleanup_events,
                suite_cleanup_reference,
            ) = _execute_shared_environment_stage(
                phase="cleanup",
                boundary="suite",
                calls=tuple(once_cleanup_calls),
                resolver=selected_resolver,
                resource_provider=selected_provider,
                device=selected_device,
                recorder=recorder,
            )
            _attach_shared_stage(
                results,
                tuple(once_cleanup_result_indexes),
                phase="cleanup",
                stage=suite_cleanup,
                events=suite_cleanup_events,
                reference=suite_cleanup_reference,
                invalidate_on_failure=(
                    protocol.failure.cleanup.outcome.value == "invalidate"
                ),
                run_config=config,
            )

        ordered_results = tuple(
            sorted(
                results,
                key=lambda item: (item.repeat, item.task_id, item.agent_id),
            )
        )
        return _finalize_if_enabled(
            BenchmarkSuiteResult(
                experiment_id=config.experiment_id,
                benchmark_plan_identity=plan.canonical_hash(),
                experiment_protocol_identity=protocol.canonical_hash(),
                results=ordered_results,
                lifecycle_events=tuple(recorder.events),
                fairness_warnings=tuple(sorted(set(fairness_warnings))),
                device_provenance={
                    **provenance,
                    "device_id": config.safe_device_id(),
                },
            ),
            run_config=config,
        )
