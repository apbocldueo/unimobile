"""Single-task Benchmark lifecycle orchestration over ExecutableAgent."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, Mapping

from zhixing.benchmark.identity import canonical_hash
from zhixing.benchmark.models import (
    BenchmarkPlan,
    ExperimentProtocol,
    FailureOutcome,
    TaskInstance,
)
from zhixing.components import AgentState, RunStatus, RuntimeContext, TaskInput
from zhixing.sdk import AgentRunConfig, ExecutableAgent

from zhixing.benchmark.compatibility import build_legacy_evaluator_context
from zhixing.benchmark.reporting.safety import safe_export

from .lifecycle import execute_environment_calls
from .resolver import BenchmarkComponentResolver
from .evaluator import (
    PreparedEvaluatorNode,
    evaluate_tree,
    prepare_evaluator_tree,
    run_evaluator_pre_hooks,
)
from .models import (
    BenchmarkCancellationSignal,
    BenchmarkLifecycleEvent,
    BenchmarkOutcome,
    BenchmarkRunConfig,
    BenchmarkStageResult,
    BenchmarkStageStatus,
    BenchmarkTaskResult,
    CompositeCancellation,
    DeadlineCancellation,
    EvaluationNodeResult,
)
from .resources import BenchmarkResourceProvider


class LifecycleRecorder:
    """Run-local ordered Benchmark lifecycle event recorder."""

    def __init__(
        self,
        experiment_id: str,
        *,
        sink: Callable[[BenchmarkLifecycleEvent], None] | None = None,
    ) -> None:
        """Create an empty recorder.

        Args:
            experiment_id (str): Stable experiment correlation ID.
            sink (Callable[[BenchmarkLifecycleEvent], None] | None): Live callback.

        Raises:
            ValueError: Experiment ID is blank.

        Returns:
            None.
        """
        if not experiment_id.strip():
            raise ValueError("experiment_id must not be blank")
        self.experiment_id = experiment_id
        self.sink = sink
        self.events: list[BenchmarkLifecycleEvent] = []
        self._sequence = 0

    def emit(
        self,
        phase: str,
        kind: str,
        *,
        task_run_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        repeat: int = 0,
        duration_ms: float | None = None,
        payload: Mapping[str, Any] | None = None,
    ) -> BenchmarkLifecycleEvent:
        """Emit one ordered lifecycle event.

        Args:
            phase (str): Lifecycle phase.
            kind (str): Start, complete, fail, or skipped.
            task_run_id (str): Run-local task identity.
            task_id (str): Benchmark task identity.
            agent_id (str): Candidate Agent identity.
            repeat (int): Repeat index.
            duration_ms (float | None): Completed duration.
            payload (Mapping[str, Any] | None): Safe event details.

        Raises:
            Exception: A caller sink failure propagates.

        Returns:
            BenchmarkLifecycleEvent: Emitted event.
        """
        self._sequence += 1
        event = BenchmarkLifecycleEvent(
            experiment_id=self.experiment_id,
            sequence=self._sequence,
            phase=phase,
            kind=kind,
            task_run_id=task_run_id,
            task_id=task_id,
            agent_id=agent_id,
            repeat=repeat,
            duration_ms=duration_ms,
            payload=payload or {},
        )
        self.events.append(event)
        if self.sink is not None:
            self.sink(event)
        return event


def _error_stage(
    phase: str,
    started: float,
    error: Exception,
    *,
    code: str,
) -> BenchmarkStageResult:
    """Normalize an exception without exposing its repr or host paths.

    Args:
        phase (str): Failed lifecycle phase.
        started (float): Monotonic start time.
        error (Exception): Caught exception.
        code (str): Stable error code.

    Raises:
        None.

    Returns:
        BenchmarkStageResult: Safe failure result.
    """
    return BenchmarkStageResult(
        phase=phase,
        status=BenchmarkStageStatus.FAILURE,
        duration_ms=(time.perf_counter() - started) * 1000,
        error_code=code,
        message=f"{phase} failed ({type(error).__name__})",
    )


def _skip_stage(phase: str, reason: str) -> BenchmarkStageResult:
    """Create an explicit skipped stage.

    Args:
        phase (str): Lifecycle phase.
        reason (str): Stable reason code or text.

    Raises:
        None.

    Returns:
        BenchmarkStageResult: Skipped result.
    """
    return BenchmarkStageResult(
        phase=phase,
        status=BenchmarkStageStatus.SKIPPED,
        message=reason,
    )


def _phase_calls(
    instance: TaskInstance,
    phase: str,
    resolver: BenchmarkComponentResolver,
) -> tuple[Mapping[str, Any], ...]:
    """Select calls whose explicit or resolved namespace belongs to a phase.

    Args:
        instance (TaskInstance): Materialized task.
        phase (str): Reset or setup.
        resolver (BenchmarkComponentResolver): Component resolver.

    Raises:
        ValueError: Legacy routing is ambiguous.

    Returns:
        tuple[Mapping[str, Any], ...]: Ordered calls; filtering is performed by
        the environment adapter after all calls resolve.
    """
    del phase, resolver
    return tuple(instance.environment_initializer)


def _outcome_after_failures(
    *,
    protocol: ExperimentProtocol,
    stages: list[BenchmarkStageResult],
    agent_status: RunStatus | None,
    evaluation: EvaluationNodeResult | None,
    cancellation_observed: bool,
) -> BenchmarkOutcome:
    """Compute Benchmark outcome separately from Agent RunStatus.

    Args:
        protocol (ExperimentProtocol): Stage failure semantics.
        stages (list[BenchmarkStageResult]): Ordered lifecycle results.
        agent_status (RunStatus | None): Optional Graph outcome.
        evaluation (EvaluationNodeResult | None): Optional evaluator evidence.
        cancellation_observed (bool): Whether cooperative cancellation was
            observed before the TaskRun completed.

    Raises:
        None.

    Returns:
        BenchmarkOutcome: PASS, FAIL, INVALID, or SKIPPED.
    """
    failed = {item.phase for item in stages if item.status is BenchmarkStageStatus.FAILURE}
    if failed & {"materialization", "preflight", "reset", "setup", "evaluator_pre"}:
        return BenchmarkOutcome.INVALID
    if "evaluation" in failed:
        return (
            BenchmarkOutcome.FAIL
            if protocol.failure.evaluator.outcome is FailureOutcome.FAIL
            else BenchmarkOutcome.INVALID
        )
    if "cleanup" in failed and protocol.failure.cleanup.outcome is FailureOutcome.INVALIDATE:
        return BenchmarkOutcome.INVALID
    if evaluation is not None:
        return BenchmarkOutcome.PASS if evaluation.is_pass else BenchmarkOutcome.FAIL
    if cancellation_observed:
        return BenchmarkOutcome.SKIPPED
    if agent_status is not None and agent_status is not RunStatus.SUCCESS:
        return (
            BenchmarkOutcome.INVALID
            if protocol.failure.agent.outcome is FailureOutcome.INVALIDATE
            else BenchmarkOutcome.FAIL
        )
    return BenchmarkOutcome.INVALID


def persist_task_manifest(
    result: BenchmarkTaskResult,
    *,
    artifact_root: Path,
) -> tuple[str, Exception | None]:
    """Persist one safe task manifest without deleting existing artifacts.

    Args:
        result (BenchmarkTaskResult): Result to persist.
        artifact_root (Path): Runtime-only host artifact root.

    Raises:
        None: Persistence failures are returned.

    Returns:
        tuple[str, Exception | None]: Relative reference and optional failure.
    """
    reference = f"{result.task_run_id}/benchmark-result.json"
    try:
        target = artifact_root / result.task_run_id / "benchmark-result.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                safe_export(result.to_safe_dict()),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except Exception as error:
        return reference, error
    return reference, None


def execute_task_run(
    *,
    plan: BenchmarkPlan,
    protocol: ExperimentProtocol,
    task_instance: TaskInstance,
    agent_id: str,
    agent: ExecutableAgent,
    run_config: BenchmarkRunConfig,
    resolver: BenchmarkComponentResolver,
    resource_provider: BenchmarkResourceProvider,
    device: Any,
    recorder: LifecycleRecorder,
    execute_reset: bool = True,
    execute_cleanup: bool = True,
    shared_stage_refs: tuple[str, ...] = (),
    cancellation: BenchmarkCancellationSignal | None = None,
) -> BenchmarkTaskResult:
    """Execute one materialized task through the complete Graph lifecycle.

    Args:
        plan (BenchmarkPlan): Source Plan.
        protocol (ExperimentProtocol): Enforced fairness and failure policy.
        task_instance (TaskInstance): Concrete task assigned to this Agent.
        agent_id (str): Stable candidate name.
        agent (ExecutableAgent): Graph-native executable recipe.
        run_config (BenchmarkRunConfig): Runtime bindings.
        resolver (BenchmarkComponentResolver): Benchmark component boundary.
        resource_provider (BenchmarkResourceProvider): Package resource service.
        device (Any): Shared explicit device.
        recorder (LifecycleRecorder): Suite-level event recorder.
        execute_reset (bool): Whether reset belongs to this run boundary.
        execute_cleanup (bool): Whether cleanup belongs to this run boundary.
        shared_stage_refs (tuple[str, ...]): Shared lifecycle evidence references.
        cancellation (BenchmarkCancellationSignal | None): Optional caller-owned
            cooperative cancellation signal.

    Raises:
        None: Stage failures are normalized into BenchmarkTaskResult.

    Returns:
        BenchmarkTaskResult: Structured task outcome and evidence.
    """
    plan_identity = plan.canonical_hash()
    protocol_identity = protocol.canonical_hash()
    instance_identity = task_instance.canonical_hash()
    task_run_id = canonical_hash(
        {
            "experiment": run_config.experiment_id,
            "agent": agent_id,
            "task_instance": instance_identity,
        }
    ).removeprefix("sha256:")[:32]
    start_event_index = len(recorder.events)
    stages: list[BenchmarkStageResult] = [
        BenchmarkStageResult(
            phase="materialization",
            status=BenchmarkStageStatus.SUCCESS,
            evidence={
                "task_instance_identity": instance_identity,
                "notes": list(task_instance.materialization_notes),
            },
        )
    ]
    prepared: PreparedEvaluatorNode | None = None
    evaluation: EvaluationNodeResult | None = None
    agent_result = None
    can_run_agent = True
    cancellation_observed = bool(
        cancellation is not None and cancellation.is_cancelled()
    )

    if execute_reset and not cancellation_observed:
        started = time.perf_counter()
        recorder.emit(
            "reset", "start", task_run_id=task_run_id, task_id=task_instance.task_id,
            agent_id=agent_id, repeat=task_instance.repeat,
        )
        try:
            evidence = execute_environment_calls(
                _phase_calls(task_instance, "reset", resolver),
                requested_phase="reset",
                resolver=resolver,
                resource_provider=resource_provider,
                device=device,
            )
            if protocol.isolation.require_verified_reset and not evidence:
                raise RuntimeError("task has no verifiable reset operation")
            stage = BenchmarkStageResult(
                phase="reset",
                status=BenchmarkStageStatus.SUCCESS,
                duration_ms=(time.perf_counter() - started) * 1000,
                evidence={"calls": evidence},
            )
            recorder.emit(
                "reset", "complete", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
            )
        except Exception as error:
            stage = _error_stage(
                "reset", started, error, code="benchmark.reset.failed"
            )
            recorder.emit(
                "reset", "fail", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
                payload={"code": stage.error_code},
            )
            can_run_agent = False
        stages.append(stage)
        cancellation_observed = bool(
            cancellation is not None and cancellation.is_cancelled()
        )
        if cancellation_observed:
            can_run_agent = False
    elif execute_reset:
        stages.append(_skip_stage("reset", "execution cancelled before reset"))
        can_run_agent = False
    else:
        stages.append(
            BenchmarkStageResult(
                phase="reset",
                status=BenchmarkStageStatus.SKIPPED,
                message="reset executed at a shared suite boundary",
                artifact_refs=shared_stage_refs,
            )
        )

    started = time.perf_counter()
    if can_run_agent and not cancellation_observed:
        recorder.emit(
            "setup", "start", task_run_id=task_run_id, task_id=task_instance.task_id,
            agent_id=agent_id, repeat=task_instance.repeat,
        )
        try:
            evidence = execute_environment_calls(
                _phase_calls(task_instance, "setup", resolver),
                requested_phase="setup",
                resolver=resolver,
                resource_provider=resource_provider,
                device=device,
            )
            stage = BenchmarkStageResult(
                phase="setup",
                status=BenchmarkStageStatus.SUCCESS,
                duration_ms=(time.perf_counter() - started) * 1000,
                evidence={"calls": evidence},
            )
            recorder.emit(
                "setup", "complete", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
            )
        except Exception as error:
            stage = _error_stage(
                "setup", started, error, code="benchmark.setup.failed"
            )
            recorder.emit(
                "setup", "fail", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
                payload={"code": stage.error_code},
            )
            can_run_agent = False
        stages.append(stage)
        cancellation_observed = bool(
            cancellation is not None and cancellation.is_cancelled()
        )
        if cancellation_observed:
            can_run_agent = False
    else:
        stages.append(
            _skip_stage(
                "setup",
                (
                    "execution cancelled before setup"
                    if cancellation_observed
                    else "reset failed"
                ),
            )
        )

    started = time.perf_counter()
    if can_run_agent and not cancellation_observed:
        recorder.emit(
            "evaluator_pre", "start", task_run_id=task_run_id,
            task_id=task_instance.task_id, agent_id=agent_id,
            repeat=task_instance.repeat,
        )
        try:
            prepared = prepare_evaluator_tree(
                task_instance.evaluator,
                resolver=resolver,
                device=device,
            )
            pre_context = build_legacy_evaluator_context(
                task_instance=task_instance,
                run_result=None,
            )
            evidence = run_evaluator_pre_hooks(prepared, pre_context)
            stage = BenchmarkStageResult(
                phase="evaluator_pre",
                status=BenchmarkStageStatus.SUCCESS,
                duration_ms=(time.perf_counter() - started) * 1000,
                evidence={"leaves": evidence},
            )
            recorder.emit(
                "evaluator_pre", "complete", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
            )
        except Exception as error:
            stage = _error_stage(
                "evaluator_pre", started, error,
                code="benchmark.evaluator_pre.failed",
            )
            recorder.emit(
                "evaluator_pre", "fail", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
                payload={"code": stage.error_code},
            )
            can_run_agent = False
        stages.append(stage)
        cancellation_observed = bool(
            cancellation is not None and cancellation.is_cancelled()
        )
        if cancellation_observed:
            can_run_agent = False
    else:
        stages.append(
            _skip_stage(
                "evaluator_pre",
                (
                    "execution cancelled before evaluator preparation"
                    if cancellation_observed
                    else "setup did not complete"
                ),
            )
        )

    started = time.perf_counter()
    if can_run_agent and not cancellation_observed:
        recorder.emit(
            "agent", "start", task_run_id=task_run_id,
            task_id=task_instance.task_id, agent_id=agent_id,
            repeat=task_instance.repeat,
        )
        max_steps = min(
            protocol.budget.max_interactions,
            next(
                (
                    task.max_steps
                    for task in plan.tasks
                    if task.id == task_instance.task_id and task.max_steps is not None
                ),
                protocol.budget.max_interactions,
            ),
        )
        deadline = DeadlineCancellation.after(
            protocol.budget.timeout_seconds
        )
        runtime_cancellation: BenchmarkCancellationSignal = (
            CompositeCancellation((deadline, cancellation))
            if cancellation is not None
            else deadline
        )
        runtime = RuntimeContext(
            run_id=task_run_id,
            max_steps=max_steps,
            max_activations=protocol.budget.max_activations,
            state=AgentState(
                current_task=TaskInput(task_instance.instruction)
            ),
            device=device,
            cancellation=runtime_cancellation,
            metadata={
                "experiment_id": run_config.experiment_id,
                "agent_id": agent_id,
                "agent_graph_identity": agent.canonical_hash,
                "benchmark_plan_identity": plan_identity,
                "experiment_protocol_identity": protocol_identity,
                "task_instance_identity": instance_identity,
                "task_id": task_instance.task_id,
                "repeat": task_instance.repeat,
                "deadline_mode": "cooperative",
            },
        )
        agent_result = agent.run(
            TaskInput(task_instance.instruction),
            AgentRunConfig(
                serial=run_config.serial,
                artifact_root=run_config.artifact_root,
                max_steps=max_steps,
                max_activations=protocol.budget.max_activations,
            ),
            device=device,
            runtime=runtime,
        )
        agent_ok = agent_result.status is RunStatus.SUCCESS
        stage = BenchmarkStageResult(
            phase="agent",
            status=(
                BenchmarkStageStatus.SUCCESS
                if agent_ok
                else BenchmarkStageStatus.FAILURE
            ),
            duration_ms=(time.perf_counter() - started) * 1000,
            error_code=(
                "" if agent_ok else "benchmark.agent.failed"
            ),
            message=("" if agent_ok else agent_result.error[:1000]),
            evidence={
                "run_id": agent_result.run_id,
                "run_status": agent_result.status.value,
                "kernel_status": agent_result.kernel_status,
                "interaction_count": agent_result.interaction_count,
                "activation_count": agent_result.activation_count,
            },
            artifact_refs=(
                (agent_result.artifact_namespace,)
                if agent_result.artifact_namespace
                else ()
            ),
        )
        recorder.emit(
            "agent", "complete" if agent_ok else "fail",
            task_run_id=task_run_id, task_id=task_instance.task_id,
            agent_id=agent_id, repeat=task_instance.repeat,
            duration_ms=stage.duration_ms,
            payload={"run_status": agent_result.status.value},
        )
        stages.append(stage)
        cancellation_observed = bool(runtime_cancellation.is_cancelled())
    else:
        stages.append(
            _skip_stage(
                "agent",
                (
                    "execution cancelled before Agent"
                    if cancellation_observed
                    else "Benchmark infrastructure invalid"
                ),
            )
        )

    should_evaluate = prepared is not None and (
        agent_result is not None
        and (
            agent_result.status is RunStatus.SUCCESS
            or protocol.failure.agent.outcome
            is FailureOutcome.EVALUATE_IF_POSSIBLE
        )
    )
    started = time.perf_counter()
    if should_evaluate and not cancellation_observed:
        recorder.emit(
            "evaluation", "start", task_run_id=task_run_id,
            task_id=task_instance.task_id, agent_id=agent_id,
            repeat=task_instance.repeat,
        )
        try:
            evaluation_context = build_legacy_evaluator_context(
                task_instance=task_instance,
                run_result=agent_result,
                artifact_refs=(
                    (agent_result.artifact_namespace,)
                    if agent_result and agent_result.artifact_namespace
                    else ()
                ),
            )
            evaluation = evaluate_tree(prepared, evaluation_context)
            stage = BenchmarkStageResult(
                phase="evaluation",
                status=(
                    BenchmarkStageStatus.SUCCESS
                    if evaluation.status is BenchmarkStageStatus.SUCCESS
                    else BenchmarkStageStatus.FAILURE
                ),
                duration_ms=(time.perf_counter() - started) * 1000,
                error_code=(
                    ""
                    if evaluation.status is BenchmarkStageStatus.SUCCESS
                    else "benchmark.evaluation.invalid"
                ),
                evidence={
                    "is_pass": evaluation.is_pass,
                    "score": evaluation.score,
                    "root_path": evaluation.path,
                },
            )
            recorder.emit(
                "evaluation",
                (
                    "complete"
                    if evaluation.status is BenchmarkStageStatus.SUCCESS
                    else "fail"
                ),
                task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
                payload={"is_pass": evaluation.is_pass},
            )
        except Exception as error:
            stage = _error_stage(
                "evaluation", started, error,
                code="benchmark.evaluation.failed",
            )
            recorder.emit(
                "evaluation", "fail", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
                payload={"code": stage.error_code},
            )
        stages.append(stage)
        cancellation_observed = bool(
            cancellation is not None and cancellation.is_cancelled()
        )
    else:
        stages.append(
            _skip_stage(
                "evaluation",
                (
                    "execution cancelled before evaluation"
                    if cancellation_observed
                    else "no evaluable Agent evidence"
                ),
            )
        )

    started = time.perf_counter()
    if execute_cleanup:
        recorder.emit(
            "cleanup", "start", task_run_id=task_run_id,
            task_id=task_instance.task_id, agent_id=agent_id,
            repeat=task_instance.repeat,
        )
        try:
            evidence = execute_environment_calls(
                task_instance.cleanup_initializer,
                requested_phase="cleanup",
                resolver=resolver,
                resource_provider=resource_provider,
                device=device,
            )
            stage = BenchmarkStageResult(
                phase="cleanup",
                status=BenchmarkStageStatus.SUCCESS,
                duration_ms=(time.perf_counter() - started) * 1000,
                evidence={"calls": evidence},
            )
            recorder.emit(
                "cleanup", "complete", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
            )
        except Exception as error:
            stage = _error_stage(
                "cleanup", started, error, code="benchmark.cleanup.failed"
            )
            recorder.emit(
                "cleanup", "fail", task_run_id=task_run_id,
                task_id=task_instance.task_id, agent_id=agent_id,
                repeat=task_instance.repeat, duration_ms=stage.duration_ms,
                payload={"code": stage.error_code},
            )
        stages.append(stage)
    else:
        stages.append(
            BenchmarkStageResult(
                phase="cleanup",
                status=BenchmarkStageStatus.SKIPPED,
                message="cleanup executes at a shared suite boundary",
                artifact_refs=shared_stage_refs,
            )
        )

    usage = dict(agent_result.usage) if agent_result is not None else {}
    token_observable = any(
        key in usage for key in ("total_tokens", "tokens", "llm_usage")
    )
    if protocol.budget.token_limit is not None and not token_observable:
        stages.append(
            BenchmarkStageResult(
                phase="token_budget",
                status=BenchmarkStageStatus.UNVERIFIED,
                error_code="benchmark.budget.tokens_unobservable",
                message="Token usage was not observable for this Agent run.",
            )
        )
    outcome = _outcome_after_failures(
        protocol=protocol,
        stages=stages,
        agent_status=agent_result.status if agent_result else None,
        evaluation=evaluation,
        cancellation_observed=cancellation_observed,
    )
    if (
        protocol.budget.token_limit is not None
        and protocol.budget.require_observable_tokens
        and not token_observable
        and outcome is not BenchmarkOutcome.SKIPPED
    ):
        outcome = BenchmarkOutcome.INVALID
    selected_events = tuple(recorder.events[start_event_index:])
    result = BenchmarkTaskResult(
        experiment_id=run_config.experiment_id,
        task_run_id=task_run_id,
        task_id=task_instance.task_id,
        repeat=task_instance.repeat,
        agent_id=agent_id,
        agent_graph_identity=agent.canonical_hash,
        benchmark_plan_identity=plan_identity,
        experiment_protocol_identity=protocol_identity,
        task_instance_identity=instance_identity,
        outcome=outcome,
        stages=tuple(stages),
        lifecycle_events=selected_events,
        agent_result=agent_result,
        evaluation=evaluation,
        usage=usage,
        artifact_namespace=(
            agent_result.artifact_namespace if agent_result is not None else ""
        ),
        fairness_warnings=protocol.fairness_warnings,
    )
    if run_config.persist_manifests:
        reference, persistence_error = persist_task_manifest(
            result,
            artifact_root=run_config.artifact_root,
        )
        if persistence_error is not None:
            persistence = BenchmarkStageResult(
                phase="persistence",
                status=BenchmarkStageStatus.FAILURE,
                error_code="benchmark.manifest.write_failed",
                message=(
                    "Benchmark result manifest could not be written "
                    f"({type(persistence_error).__name__})"
                ),
            )
            result = replace(result, stages=(*result.stages, persistence))
        elif not result.artifact_namespace:
            result = replace(result, artifact_namespace=reference.rsplit("/", 1)[0])
    return result
