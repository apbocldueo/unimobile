"""Stage 5.2B Benchmark preflight, execution adapter, and single worker."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, replace
from typing import Any, Callable

from zhixing.benchmark import (
    BenchmarkExperimentRuntime,
    BenchmarkLifecycleEvent,
    BenchmarkOutcome,
    BenchmarkPublicationPolicy,
    BenchmarkRunConfig,
    BenchmarkSuiteResult,
    BenchmarkTaskResult,
    BenchmarkValidationLevel,
    PackageBenchmarkResourceProvider,
    RegistryBenchmarkComponentResolver,
)
from zhixing.benchmark.identity import canonical_hash
from zhixing.graph import AgentGraph
from zhixing.runtime import SimpleCancellationSignal
from zhixing.sdk import ExecutableAgent

from .benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkStorageError,
    StudioBenchmarkValidationError,
)
from .benchmark_evidence import (
    LocalStudioBenchmarkEvidenceStore,
)
from .benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventSource,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunTerminalReason,
)
from .benchmark_experiment_protocols import (
    StudioBenchmarkExperimentAggregate,
    StudioBenchmarkExperimentRepository,
)
from .benchmark_result import project_benchmark_task_result
from .benchmark_publication_models import (
    StudioBenchmarkPreparedPublicationV1,
    StudioBenchmarkPublicationDiagnosticV1,
)
from .benchmark_publication_protocols import (
    StudioBenchmarkPublicationPreparer,
    StudioBenchmarkPublisher,
)
from .benchmark_service import StudioBenchmarkApplicationService
from .run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    DeviceLeaseRegistry,
    ProductionComponentResolverFactory,
)
from .device_profiles import (
    DeviceAuthorityCode,
    resolve_exact_android_session,
)
from .run_errors import StudioRunValidationError
from .evidence_origin import StudioExecutionEvidenceOriginV1
from .eligibility import evaluate_run_snapshot_eligibility


Clock = Callable[[], int]


def _now_ms() -> int:
    """Return wall-clock Unix epoch milliseconds.

    Returns:
        Integer Unix epoch milliseconds.
    """
    return time.time_ns() // 1_000_000


def _event_id(seed: dict[str, Any]) -> str:
    """Derive one stable opaque Benchmark journal event identity.

    Args:
        seed: Safe deterministic identity material.

    Raises:
        TypeError: Seed is not JSON compatible.
        ValueError: Seed contains a non-finite number.

    Returns:
        Event identity with a 128-bit hexadecimal suffix.
    """
    suffix = canonical_hash(seed).removeprefix("sha256:")[:32]
    return f"benchmark-event-{suffix}"


class StudioBenchmarkExecutionCancelled(RuntimeError):
    """Internal cooperative stop observed before a trustworthy Core result."""


@dataclass(frozen=True)
class PreparedStudioBenchmarkExecution:
    """Purely verified immutable definition and fresh executable Agent."""

    aggregate: StudioBenchmarkExperimentAggregate
    agent: ExecutableAgent
    resource_provider: PackageBenchmarkResourceProvider


@dataclass(frozen=True)
class ExecutedStudioBenchmarkResult:
    """Complete Core result plus independent formal preparation outcome."""

    suite: BenchmarkSuiteResult
    task_result: BenchmarkTaskResult
    evidence_origin: StudioExecutionEvidenceOriginV1
    prepared_publication: StudioBenchmarkPreparedPublicationV1 | None = None
    preparation_diagnostic: StudioBenchmarkPublicationDiagnosticV1 | None = None


def _snapshot_fingerprint(aggregate: StudioBenchmarkExperimentAggregate) -> str:
    """Recompute the immutable snapshot fingerprint accepted at create.

    Args:
        aggregate: Durable Experiment aggregate.

    Raises:
        TypeError: Snapshot facts are unexpectedly not JSON compatible.
        ValueError: Snapshot facts contain a non-finite number.

    Returns:
        Canonical snapshot fingerprint.
    """
    snapshot = aggregate.experiment.definition
    payload = {
        "contract": "studio-benchmark-experiment-definition-v1",
        "previewFingerprint": snapshot.preview_fingerprint,
        "source": snapshot.source.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        "agentSnapshots": [
            item.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            for item in snapshot.agent_snapshots
        ],
        "benchmarkPlan": snapshot.benchmark_plan.model_dump(
            mode="json",
            exclude_none=True,
        ),
        "protocol": snapshot.protocol.canonical_payload(),
        "split": snapshot.split,
        "taskIds": list(snapshot.task_ids),
        "schedule": [
            item.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            )
            for item in snapshot.schedule
        ],
        "deviceProfileId": snapshot.device_profile_id,
        "executionLimits": snapshot.execution_limits.model_dump(
            mode="json",
            by_alias=True,
        ),
    }
    return canonical_hash(payload)


class StudioBenchmarkExecutionAdapter:
    """Verify immutable definitions and delegate lifecycle to Benchmark Core."""

    def __init__(
        self,
        *,
        definitions: StudioBenchmarkApplicationService,
        components: ProductionComponentResolverFactory,
        evidence: LocalStudioBenchmarkEvidenceStore,
        profiles: AndroidDeviceProfileResolver,
        leases: DeviceLeaseRegistry | None = None,
        publication_preparer: StudioBenchmarkPublicationPreparer | None = None,
        clock: Clock = _now_ms,
    ) -> None:
        """Configure all pure, storage, profile, and device boundaries.

        Args:
            definitions: Frozen Catalog, revision, and contract environment.
            components: Fresh Agent component resolver factory.
            evidence: Permanent private Benchmark evidence store.
            profiles: Safe profile ID to local runtime binding resolver.
            leases: Optional process-local exclusive device lease registry.
            publication_preparer: Optional complete-suite formal writer.
            clock: Injectable integer-millisecond preparation clock.

        Raises:
            None.

        Returns:
            None.
        """
        self.definitions = definitions
        self.components = components
        self.evidence = evidence
        self.profiles = profiles
        self.leases = leases or DeviceLeaseRegistry()
        self.publication_preparer = publication_preparer
        self.clock = clock

    def prepare(
        self,
        aggregate: StudioBenchmarkExperimentAggregate,
    ) -> PreparedStudioBenchmarkExecution:
        """Perform complete no-device immutable definition preflight.

        Args:
            aggregate: Claimed durable Experiment and planned TaskRun.

        Raises:
            StudioBenchmarkValidationError: Snapshot, cardinality, source,
                resource, graph, or component contract verification fails.

        Returns:
            Purely verified execution input with a fresh Agent recipe.
        """
        record = aggregate.experiment
        snapshot = record.definition
        if (
            len(aggregate.task_runs) != 1
            or len(snapshot.agent_snapshots) != 1
            or len(snapshot.schedule) != 1
            or len(snapshot.task_ids) != 1
            or snapshot.protocol.repeats != 1
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.cardinality_unsupported",
                "Stage 5.2B supports one Agent, one Task, and one repeat",
            )
        if _snapshot_fingerprint(aggregate) != snapshot.snapshot_fingerprint:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.snapshot_tampered",
                "Benchmark Experiment snapshot fingerprint is invalid",
            )
        task_run = aggregate.task_runs[0]
        planned = snapshot.schedule[0]
        if (
            planned.planned_entry_id != task_run.planned_entry_id
            or planned.agent_id != task_run.agent_id
            or planned.revision_id != task_run.revision_id
            or planned.task_id != task_run.task_id
            or planned.repeat != task_run.repeat
            or planned.derived_seed != task_run.derived_seed
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.schedule_mismatch",
                "Planned TaskRun does not match the immutable schedule",
            )
        agent_snapshot = snapshot.agent_snapshots[0]
        policy = evaluate_run_snapshot_eligibility(
            agent_snapshot,
            catalog=self.definitions.component_catalog,
            contract_catalog=self.definitions.contract_catalog,
        )
        if not policy.current_policy_eligible:
            issue = policy.diagnostics[0]
            raise StudioBenchmarkValidationError(issue.code, issue.message)
        try:
            entry, compiled = self.definitions.catalog.compile_split(
                snapshot.source.catalog_entry_id,
                snapshot.split,
                validation_level=BenchmarkValidationLevel.FULL,
            )
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.source_unavailable",
                "Saved Benchmark Package source cannot be verified",
            ) from error
        plan = compiled.plan
        protocol = compiled.protocol
        if plan is None or protocol is None:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.definition_invalid",
                "Saved Benchmark definition is no longer valid",
            )
        if (
            entry.source_id != snapshot.source.source_id
            or entry.source_kind != snapshot.source.source_kind
            or entry.relative_key != snapshot.source.relative_key
            or entry.candidate.identity != snapshot.source.package_identity
            or plan.package_content_identity
            != snapshot.source.package_content_identity
            or plan.canonical_hash()
            != snapshot.source.benchmark_plan_identity
            or snapshot.benchmark_plan.canonical_hash()
            != snapshot.source.benchmark_plan_identity
            or snapshot.protocol.canonical_hash()
            != snapshot.source.experiment_protocol_identity
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.definition_drift",
                "Saved Benchmark Package identities no longer match",
            )
        if task_run.task_id not in {
            task.id for task in snapshot.benchmark_plan.tasks
        }:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.task_missing",
                "Selected task is absent from the immutable Benchmark Plan",
            )
        provider = PackageBenchmarkResourceProvider(
            entry.candidate.root,
            snapshot.benchmark_plan,
        )
        try:
            for resource in snapshot.benchmark_plan.resources:
                scheme = (
                    "asset"
                    if resource.kind.value == "asset"
                    else "groundtruth"
                )
                provider.resolve(f"{scheme}://{resource.id}")
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.resource_drift",
                "Saved Benchmark logical resource cannot be verified",
            ) from error
        if (
            agent_snapshot.agent_id != task_run.agent_id
            or agent_snapshot.revision_id != task_run.revision_id
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.agent_snapshot_mismatch",
                "Saved Agent snapshot does not match the planned TaskRun",
            )
        try:
            graph = AgentGraph.model_validate(agent_snapshot.agent_graph)
            graph_identity = graph.canonical_hash(
                contract_catalog=self.definitions.contract_catalog,
            )
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.agent_graph_invalid",
                "Saved AgentGraph cannot be validated",
            ) from error
        if graph_identity != agent_snapshot.canonical_hash:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.agent_graph_drift",
                "Saved AgentGraph identity is invalid",
            )
        try:
            self.components.validate_graph_bindings(graph)
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.component_unavailable",
                "Saved AgentGraph component binding is unavailable",
            ) from error
        agent = ExecutableAgent(
            graph=graph,
            resolver_factory=self.components.create,
            contract_catalog=self.definitions.contract_catalog,
        )
        return PreparedStudioBenchmarkExecution(
            aggregate=aggregate,
            agent=agent,
            resource_provider=provider,
        )

    def execute(
        self,
        prepared: PreparedStudioBenchmarkExecution,
        *,
        cancellation: SimpleCancellationSignal,
        event_sink: Callable[[BenchmarkLifecycleEvent], None],
    ) -> ExecutedStudioBenchmarkResult:
        """Acquire storage/profile/device boundaries and invoke Benchmark Core.

        Args:
            prepared: Purely verified immutable execution input.
            cancellation: Shared cooperative cancellation signal.
            event_sink: Synchronous durable Core event adapter.

        Raises:
            StudioBenchmarkExecutionCancelled: Cancellation precedes Core.
            StudioBenchmarkStorageError: Evidence preflight fails.
            StudioRunError: Profile or device lease is unavailable.
            RuntimeError: Core returns inconsistent coordinates.

        Returns:
            Complete Core suite, its one verified TaskResult, and independent
            formal preparation outcome.
        """
        record = prepared.aggregate.experiment
        task = prepared.aggregate.task_runs[0]
        namespace = self.evidence.preflight(record.experiment_id)
        if cancellation.is_cancelled():
            raise StudioBenchmarkExecutionCancelled(
                "cancelled after evidence preflight"
            )
        pinned = prepared.aggregate.binding_authority
        if pinned is None:
            raise StudioRunValidationError(
                DeviceAuthorityCode.PROFILE_UNBOUND.value,
                "Accepted Benchmark Experiment has no pinned device authority",
            )
        profile: AndroidDeviceProfile = self.profiles.resolve(
            record.definition.device_profile_id
        )
        if pinned.profile_id != profile.profile_id:
            raise StudioRunValidationError(
                DeviceAuthorityCode.BINDING_DRIFTED.value,
                "Selected Android device binding changed after acceptance",
            )
        if cancellation.is_cancelled():
            raise StudioBenchmarkExecutionCancelled(
                "cancelled before device lease"
            )
        with self.leases.acquire(
            profile.target_key,
            record.experiment_id,
            profile_id=profile.profile_id,
        ):
            if cancellation.is_cancelled():
                raise StudioBenchmarkExecutionCancelled(
                    "cancelled before exact target verification"
                )
            session = resolve_exact_android_session(
                profile,
                pinned_binding_fingerprint=pinned.binding_fingerprint,
            )
            if cancellation.is_cancelled():
                raise StudioBenchmarkExecutionCancelled(
                    "cancelled before Benchmark Runtime"
                )
            suite = BenchmarkExperimentRuntime().run(
                record.definition.benchmark_plan,
                record.definition.protocol,
                {task.agent_id: prepared.agent},
                run_config=BenchmarkRunConfig(
                    artifact_root=namespace.runtime_root,
                    serial=session.serial,
                    task_ids=(task.task_id,),
                    experiment_id=record.experiment_id,
                    publication_policy=BenchmarkPublicationPolicy.DEFER,
                ),
                resource_provider=prepared.resource_provider,
                resolver=RegistryBenchmarkComponentResolver(),
                device=session.device,
                event_sink=event_sink,
                cancellation=cancellation,
            )
        evidence_origin = StudioExecutionEvidenceOriginV1.from_runtime(
            acquisition=(
                "contract_fixture"
                if session.environment_candidate == "fake_device"
                else "fresh_execution"
            ),
            environment=session.environment_candidate,
            device_profile_id=profile.profile_id,
            device_provenance=suite.device_provenance,
        )
        suite = replace(
            suite,
            device_provenance={
                key: value
                for key, value in suite.device_provenance.items()
                if key != "device_id"
            }
            | {
                "evidence_origin": evidence_origin.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
            },
        )
        if len(suite.results) != 1:
            raise RuntimeError("Benchmark Core returned unexpected cardinality")
        result = suite.results[0]
        if (
            result.experiment_id != record.experiment_id
            or result.agent_id != task.agent_id
            or result.task_id != task.task_id
            or result.repeat != task.repeat
        ):
            raise RuntimeError("Benchmark Core result coordinates do not match")
        prepared_publication = None
        preparation_diagnostic = None
        if self.publication_preparer is not None:
            try:
                prepared_publication = self.publication_preparer.prepare(
                    suite,
                    planned_task_run_id=task.task_run_id,
                    definition_snapshot=record.definition.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                    ),
                    prepared_at=self.clock(),
                )
            except Exception as error:
                preparation_diagnostic = StudioBenchmarkPublicationDiagnosticV1(
                    code=(
                        getattr(error, "code", "")
                        or "benchmark.publication.preparation_failed"
                    ),
                    message="Benchmark formal publication preparation failed",
                    component="preparation",
                    retryable=True,
                )
        return ExecutedStudioBenchmarkResult(
            suite=suite,
            task_result=result,
            evidence_origin=evidence_origin,
            prepared_publication=prepared_publication,
            preparation_diagnostic=preparation_diagnostic,
        )


class ActiveBenchmarkExperimentRegistry:
    """Thread-safe registry for process-local cooperative cancellation signals."""

    def __init__(self) -> None:
        """Create an empty active execution registry."""
        self._lock = threading.Lock()
        self._signals: dict[str, SimpleCancellationSignal] = {}

    def register(
        self,
        experiment_id: str,
        signal: SimpleCancellationSignal,
    ) -> None:
        """Register a newly claimed Experiment signal.

        Args:
            experiment_id: Durable Experiment identity.
            signal: Worker-owned mutable cancellation signal.

        Raises:
            StudioBenchmarkConflictError: Experiment is already active.

        Returns:
            None.
        """
        with self._lock:
            if experiment_id in self._signals:
                raise StudioBenchmarkConflictError(
                    "benchmark.experiment.already_active",
                    "Benchmark Experiment already has an active worker",
                )
            self._signals[experiment_id] = signal

    def cancel(self, experiment_id: str) -> bool:
        """Notify one active worker after cancellation was persisted.

        Args:
            experiment_id: Durable Experiment identity.

        Raises:
            None.

        Returns:
            True when an active local signal was found.
        """
        with self._lock:
            signal = self._signals.get(experiment_id)
        if signal is None:
            return False
        signal.cancel()
        return True

    def remove(self, experiment_id: str) -> None:
        """Forget one completed worker signal.

        Args:
            experiment_id: Durable Experiment identity.

        Raises:
            None.

        Returns:
            None.
        """
        with self._lock:
            self._signals.pop(experiment_id, None)

    def cancel_all(self) -> int:
        """Request cooperative cancellation for every active local execution.

        Raises:
            None.

        Returns:
            Number of active signals notified.
        """
        with self._lock:
            signals = tuple(self._signals.values())
        for signal in signals:
            signal.cancel()
        return len(signals)


class DurableBenchmarkRuntimeEventAdapter:
    """Synchronously map Core events to the stable planned TaskRun journal."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkExperimentRepository,
        experiment_id: str,
        planned_task_run_id: str,
        process_owner_id: str,
        cancellation: SimpleCancellationSignal,
    ) -> None:
        """Configure planned/Core identity mapping and append-failure behavior.

        Args:
            repository: Durable Experiment repository.
            experiment_id: Owning Experiment identity.
            planned_task_run_id: Stable public TaskRun identity.
            process_owner_id: Current process ownership identity.
            cancellation: Shared signal cancelled on journal failure.

        Raises:
            None.

        Returns:
            None.
        """
        self.repository = repository
        self.experiment_id = experiment_id
        self.planned_task_run_id = planned_task_run_id
        self.process_owner_id = process_owner_id
        self.cancellation = cancellation
        self._phase_states: set[str] = set()

    def __call__(self, event: BenchmarkLifecycleEvent) -> None:
        """Persist one Core event before Core starts its next effect.

        Args:
            event: Ordered Core lifecycle event.

        Raises:
            StudioBenchmarkError: Journal or transition persistence fails.

        Returns:
            None.
        """
        identity_seed = {
            "experiment": self.experiment_id,
            "plannedTaskRun": self.planned_task_run_id,
            "source": "core",
            "sourceSequence": event.sequence,
            "phase": event.phase,
            "kind": event.kind,
        }
        draft = StudioBenchmarkEventDraftV1(
            event_id=_event_id(identity_seed),
            timestamp=max(0, int(event.timestamp * 1000)),
            source=StudioBenchmarkEventSource.CORE,
            kind=f"benchmark.{event.phase}.{event.kind}",
            task_run_id=self.planned_task_run_id,
            source_sequence=event.sequence,
            phase=event.phase,
            payload={
                "coreTaskRunId": event.task_run_id or None,
                "taskId": event.task_id,
                "agentId": event.agent_id,
                "repeat": event.repeat,
                "durationMs": event.duration_ms,
                "corePayload": dict(event.payload),
            },
        )
        try:
            transition = None
            if event.kind == "start" and event.phase == "evaluation":
                transition = StudioBenchmarkTaskRunLifecycle.EVALUATING
            elif event.kind == "start" and event.phase.startswith("cleanup"):
                transition = StudioBenchmarkTaskRunLifecycle.CLEANING_UP
            if transition is not None and event.phase not in self._phase_states:
                self._phase_states.add(event.phase)
                experiment = self.repository.get_experiment(self.experiment_id)
                lifecycle = (
                    StudioBenchmarkExperimentLifecycle.CANCELLING
                    if experiment.lifecycle
                    is StudioBenchmarkExperimentLifecycle.CANCELLING
                    else StudioBenchmarkExperimentLifecycle.RUNNING
                )
                self.repository.transition_execution(
                    self.experiment_id,
                    self.planned_task_run_id,
                    process_owner_id=self.process_owner_id,
                    experiment_lifecycle=lifecycle,
                    task_lifecycle=transition,
                    timestamp=draft.timestamp,
                    event=draft,
                )
            else:
                self.repository.append_runtime_event(
                    self.experiment_id,
                    process_owner_id=self.process_owner_id,
                    event=draft,
                )
        except Exception:
            self.cancellation.cancel()
            raise


class StudioBenchmarkExperimentOrchestrator:
    """Own claim, preflight, Core execution, result commit, and finalization."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkExperimentRepository,
        execution: StudioBenchmarkExecutionAdapter,
        process_owner_id: str,
        active: ActiveBenchmarkExperimentRegistry | None = None,
        publisher: StudioBenchmarkPublisher | None = None,
        clock: Clock = _now_ms,
    ) -> None:
        """Configure durable worker orchestration dependencies.

        Args:
            repository: Transactional Experiment aggregate repository.
            execution: Pure preflight and Benchmark Core execution adapter.
            process_owner_id: Current opaque process ownership identity.
            active: Optional shared active cancellation registry.
            publisher: Optional idempotent formal evidence publisher.
            clock: Injectable integer-millisecond clock.

        Raises:
            ValueError: Process owner is blank.

        Returns:
            None.
        """
        if not process_owner_id.strip():
            raise ValueError("process_owner_id must not be blank")
        self.repository = repository
        self.execution = execution
        self.process_owner_id = process_owner_id
        self.active = active or ActiveBenchmarkExperimentRegistry()
        self.publisher = publisher
        self.clock = clock

    def cancel_active(self, experiment_id: str) -> bool:
        """Notify a local worker after its cancellation fact commits.

        Args:
            experiment_id: Durable Experiment identity.

        Raises:
            None.

        Returns:
            True when an active local worker was notified.
        """
        return self.active.cancel(experiment_id)

    def _finish_without_result(
        self,
        aggregate: StudioBenchmarkExperimentAggregate,
        *,
        cancelled: bool,
        error_code: str,
    ) -> None:
        """Close pre-result execution and finalize its aggregate.

        Args:
            aggregate: Claimed one-TaskRun aggregate.
            cancelled: Whether cooperative cancellation caused the stop.
            error_code: Safe orchestration failure code.

        Raises:
            StudioBenchmarkError: Transactional finish or finalization fails.

        Returns:
            None.
        """
        task_reason = (
            StudioBenchmarkTaskRunTerminalReason.CANCELLED
            if cancelled
            else StudioBenchmarkTaskRunTerminalReason.FAILED
        )
        experiment_reason = (
            StudioBenchmarkExperimentTerminalReason.CANCELLED
            if cancelled
            else StudioBenchmarkExperimentTerminalReason.FAILED
        )
        task = aggregate.task_runs[0]
        self.repository.finish_task_without_result(
            aggregate.experiment.experiment_id,
            task.task_run_id,
            process_owner_id=self.process_owner_id,
            terminal_reason=task_reason,
            timestamp=self.clock(),
            error_code=error_code,
        )
        self.repository.finalize_experiment(
            aggregate.experiment.experiment_id,
            process_owner_id=self.process_owner_id,
            terminal_reason=experiment_reason,
            timestamp=self.clock(),
        )

    def execute(self, experiment_id: str) -> None:
        """Claim and execute one locally enrolled durable Experiment.

        Args:
            experiment_id: Durable Experiment identity selected by scheduler.

        Raises:
            StudioBenchmarkStorageError: Claim fails before this process owns a
                TaskRun and therefore cannot be normalized into its aggregate.

        Returns:
            None.
        """
        try:
            aggregate = self.repository.claim_experiment(
                experiment_id,
                process_owner_id=self.process_owner_id,
                timestamp=self.clock(),
            )
        except StudioBenchmarkConflictError:
            return
        signal = SimpleCancellationSignal()
        registered = False
        result_committed = False
        publication_committed = self.publisher is None
        final_reason = StudioBenchmarkExperimentTerminalReason.COMPLETED
        try:
            self.active.register(experiment_id, signal)
            registered = True
            if self.repository.get_experiment(experiment_id).cancellation is not None:
                signal.cancel()
            prepared = self.execution.prepare(aggregate)
            if signal.is_cancelled():
                raise StudioBenchmarkExecutionCancelled("cancelled in preflight")
            task = aggregate.task_runs[0]
            self.repository.transition_execution(
                experiment_id,
                task.task_run_id,
                process_owner_id=self.process_owner_id,
                experiment_lifecycle=StudioBenchmarkExperimentLifecycle.RUNNING,
                task_lifecycle=StudioBenchmarkTaskRunLifecycle.RUNNING,
                timestamp=self.clock(),
                event=StudioBenchmarkEventDraftV1(
                    event_id=_event_id(
                        {
                            "kind": "worker.execution_started",
                            "experiment": experiment_id,
                        }
                    ),
                    timestamp=self.clock(),
                    source=StudioBenchmarkEventSource.WORKER,
                    kind="worker.execution_started",
                    task_run_id=task.task_run_id,
                    phase="runtime",
                ),
            )
            sink = DurableBenchmarkRuntimeEventAdapter(
                repository=self.repository,
                experiment_id=experiment_id,
                planned_task_run_id=task.task_run_id,
                process_owner_id=self.process_owner_id,
                cancellation=signal,
            )
            executed = self.execution.execute(
                prepared,
                cancellation=signal,
                event_sink=sink,
            )
            core_result = (
                executed.task_result
                if isinstance(executed, ExecutedStudioBenchmarkResult)
                else executed
            )
            actually_cancelled = bool(
                signal.is_cancelled()
                and (
                    core_result.outcome is BenchmarkOutcome.SKIPPED
                    or (
                        core_result.agent_result is not None
                        and core_result.agent_result.status.value == "cancelled"
                    )
                )
            )
            task_terminal_reason = (
                StudioBenchmarkTaskRunTerminalReason.CANCELLED
                if actually_cancelled
                else StudioBenchmarkTaskRunTerminalReason.COMPLETED
            )
            projected, fingerprint = project_benchmark_task_result(
                core_result,
                planned_task_run_id=task.task_run_id,
                agent_revision_id=task.revision_id,
                schedule_order=task.order,
                service_terminal_reason=task_terminal_reason,
                evidence_origin=(
                    executed.evidence_origin
                    if isinstance(executed, ExecutedStudioBenchmarkResult)
                    else None
                ),
            )
            self.repository.commit_task_result(
                experiment_id,
                task.task_run_id,
                process_owner_id=self.process_owner_id,
                result=projected,
                fingerprint=fingerprint,
                terminal_reason=task_terminal_reason,
                timestamp=self.clock(),
            )
            result_committed = True
            if self.publisher is not None:
                self.publisher.publish(
                    experiment_id,
                    task.task_run_id,
                    timestamp=self.clock(),
                )
                publication_committed = True
            final_reason = (
                StudioBenchmarkExperimentTerminalReason.CANCELLED
                if actually_cancelled
                else StudioBenchmarkExperimentTerminalReason.COMPLETED
            )
            self.repository.finalize_experiment(
                experiment_id,
                process_owner_id=self.process_owner_id,
                terminal_reason=final_reason,
                timestamp=self.clock(),
            )
        except StudioBenchmarkExecutionCancelled:
            if not result_committed:
                self._finish_without_result(
                    aggregate,
                    cancelled=True,
                    error_code="benchmark.execution.cancelled",
                )
        except Exception as error:
            try:
                if result_committed and publication_committed:
                    # A complete immutable TaskResult already won the race.
                    # Retry only the matching Experiment terminal fact; never
                    # replace it with a service-failed interpretation.
                    self.repository.finalize_experiment(
                        experiment_id,
                        process_owner_id=self.process_owner_id,
                        terminal_reason=final_reason,
                        timestamp=self.clock(),
                    )
                elif not result_committed:
                    self._finish_without_result(
                        aggregate,
                        cancelled=False,
                        error_code=(
                            getattr(error, "code", "")
                            or "benchmark.execution.worker_failed"
                        ),
                    )
                # A durable TaskResult with an uncommitted publication remains
                # finalizing. Stage 5.2C-3 owns safe startup recovery.
            except Exception:
                # The original persistence boundary may be unavailable. 5.2C
                # owns durable recovery of an unfinished process-owned row.
                pass
        finally:
            if registered:
                self.active.remove(experiment_id)


class LocalBenchmarkExperimentScheduler:
    """Single long-lived repository-backed worker with a bounded wake flag."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkExperimentRepository,
        orchestrator: StudioBenchmarkExperimentOrchestrator,
        process_owner_id: str,
    ) -> None:
        """Start one daemon worker consuming locally enrolled durable work.

        Args:
            repository: Durable pending-work source.
            orchestrator: Single Experiment worker callback.
            process_owner_id: Current process ownership identity.

        Raises:
            ValueError: Process owner is blank.

        Returns:
            None.
        """
        if not process_owner_id.strip():
            raise ValueError("process_owner_id must not be blank")
        self.repository = repository
        self.orchestrator = orchestrator
        self.process_owner_id = process_owner_id
        self._wake = threading.Event()
        self._closed = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name="zhixing-studio-benchmark",
            daemon=True,
        )
        self._thread.start()

    def wake(self) -> None:
        """Wake the worker without adding an in-memory definition queue.

        Raises:
            RuntimeError: Scheduler has already closed.

        Returns:
            None.
        """
        if self._closed.is_set():
            raise RuntimeError("Benchmark Experiment scheduler is closed")
        self._wake.set()

    def _run(self) -> None:
        """Consume all locally enrolled work in stable repository order.

        Raises:
            None: Claim/read failures stop the current bounded wake cycle.

        Returns:
            None.
        """
        while not self._closed.is_set():
            self._wake.wait()
            self._wake.clear()
            while not self._closed.is_set():
                experiment_id = self.repository.next_enrolled_experiment(
                    process_owner_id=self.process_owner_id
                )
                if experiment_id is None:
                    break
                try:
                    self.orchestrator.execute(experiment_id)
                except Exception:
                    # A claim/read failure means repository progress is
                    # uncertain. Stop this wake cycle instead of spinning on
                    # the same durable row; a later safe wake can retry it.
                    break

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop the scheduler without deleting durable work or evidence.

        Args:
            wait: Whether to wait for the active cooperative worker.

        Raises:
            None.

        Returns:
            None.
        """
        self._closed.set()
        self.orchestrator.active.cancel_all()
        self._wake.set()
        if wait:
            self._thread.join()


def new_benchmark_process_owner_id() -> str:
    """Create one opaque process-scoped Benchmark worker identity.

    Returns:
        Opaque process identity.
    """
    return f"benchmark-process-{uuid.uuid4().hex}"


__all__ = [
    "ActiveBenchmarkExperimentRegistry",
    "DurableBenchmarkRuntimeEventAdapter",
    "LocalBenchmarkExperimentScheduler",
    "PreparedStudioBenchmarkExecution",
    "StudioBenchmarkExecutionAdapter",
    "StudioBenchmarkExecutionCancelled",
    "StudioBenchmarkExperimentOrchestrator",
    "new_benchmark_process_owner_id",
]
