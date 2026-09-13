"""Local scheduling, device leasing, and Android execution for Studio Runs."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Iterator, Literal, Mapping

from zhixing.catalog import (
    BUILTIN_COMPONENT_CATALOG,
    BuiltInComponentResolver,
    CatalogComponentResolver,
    DiscoveredComponentEnvironment,
    empty_component_environment,
)
from zhixing.components import (
    AgentState,
    ObservationRequest,
    RunResult,
    RunStatus,
    RuntimeContext,
    TaskInput,
)
from zhixing.graph import AgentGraph
from zhixing.runtime import (
    AndroidGraphRuntime,
    SimpleCancellationSignal,
    bind_execution_plan,
)

from .run_artifacts import LocalStudioRunArtifactStore
from .device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    DeviceAuthorityCode,
    resolve_exact_android_session,
)
from .run_debug import StudioRunDebugCapture
from .run_errors import (
    StudioRunConflictError,
    StudioRunDeviceBusyError,
    StudioRunEvidenceError,
    StudioRunValidationError,
)
from .run_events import DurableRunEventService
from .run_models import (
    RunEvidenceAvailability,
    StudioRunLifecycle,
    StudioRunRecordV1,
    StudioRunResultSummaryV1,
)
from .run_protocols import NativeRunReplayFinalizer, StudioRunRepository
from .run_safety import redact_text
from .catalog import StudioComponentCatalog, build_studio_component_catalog
from .eligibility import evaluate_run_snapshot_eligibility


class ActiveRunRegistry:
    """Thread-safe in-memory registry of active cancellation signals."""

    def __init__(self) -> None:
        """Create an empty active Run registry.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._lock = threading.Lock()
        self._signals: dict[str, SimpleCancellationSignal] = {}

    def register(
        self,
        run_id: str,
        signal: SimpleCancellationSignal,
    ) -> None:
        """Register one worker-owned cancellation signal.

        Args:
            run_id (str): Stable Run identity.
            signal (SimpleCancellationSignal): Worker signal.

        Raises:
            StudioRunConflictError: Run is already active.

        Returns:
            None.
        """
        with self._lock:
            if run_id in self._signals:
                raise StudioRunConflictError(
                    "studio.run.already_active",
                    "Studio Run already has an active worker",
                )
            self._signals[run_id] = signal

    def cancel(self, run_id: str) -> bool:
        """Signal one active Run if it belongs to this process.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            None.

        Returns:
            bool: True when an active signal was found.
        """
        with self._lock:
            signal = self._signals.get(run_id)
        if signal is None:
            return False
        signal.cancel()
        return True

    def remove(self, run_id: str) -> None:
        """Remove one finished worker signal.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            None.

        Returns:
            None.
        """
        with self._lock:
            self._signals.pop(run_id, None)

    def contains(self, run_id: str) -> bool:
        """Return whether a Run currently has a local worker.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            None.

        Returns:
            bool: Active membership.
        """
        with self._lock:
            return run_id in self._signals


class LocalThreadRunScheduler:
    """Bounded local scheduler with no unbounded pending Run queue."""

    def __init__(self, *, max_workers: int = 1) -> None:
        """Create a bounded background executor.

        Args:
            max_workers (int): Maximum concurrently submitted workers.

        Raises:
            ValueError: Worker count is not positive.

        Returns:
            None.
        """
        if max_workers < 1:
            raise ValueError("max_workers must be positive")
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="zhixing-studio-run",
        )
        self._slots = threading.BoundedSemaphore(max_workers)
        self._closed = False
        self._lock = threading.Lock()
        self._futures: set[Future[None]] = set()

    def submit(self, run_id: str, execute: Callable[[str], None]) -> None:
        """Schedule one Run or reject immediately when all slots are occupied.

        Args:
            run_id (str): Persisted Run identity.
            execute (Callable[[str], None]): Worker callback.

        Raises:
            StudioRunDeviceBusyError: Scheduler has no free execution slot.
            RuntimeError: Scheduler is closed.

        Returns:
            None.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError("Studio Run scheduler is closed")
        if not self._slots.acquire(blocking=False):
            raise StudioRunDeviceBusyError(
                "studio.run.scheduler_busy",
                "Local Studio Run worker is busy",
            )

        def invoke() -> None:
            """Execute one callback and release its bounded slot.

            Args:
                None.

            Raises:
                Exception: Worker callback failures remain visible on the Future.

            Returns:
                None.
            """
            try:
                execute(run_id)
            finally:
                self._slots.release()

        try:
            future = self._executor.submit(invoke)
        except Exception:
            self._slots.release()
            raise
        with self._lock:
            self._futures.add(future)

        def forget(done: Future[None]) -> None:
            """Forget one completed Future from bounded scheduler metadata.

            Args:
                done (Future[None]): Completed worker Future.

            Raises:
                None.

            Returns:
                None.
            """
            with self._lock:
                self._futures.discard(done)

        future.add_done_callback(forget)

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting work and release executor resources.

        Args:
            wait (bool): Whether to wait for active workers.

        Raises:
            None.

        Returns:
            None.
        """
        with self._lock:
            self._closed = True
        self._executor.shutdown(wait=wait, cancel_futures=False)


class DeviceLeaseRegistry:
    """Process-local exclusive lease registry for private target identities."""

    def __init__(self) -> None:
        """Create an empty device lease registry.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self._lock = threading.Lock()
        self._owners: dict[str, str] = {}

    @contextmanager
    def acquire(
        self,
        target_key: str,
        run_id: str,
        *,
        profile_id: str = "",
    ) -> Iterator[None]:
        """Acquire one non-blocking exclusive device lease.

        Args:
            target_key (str): Private process-local exact-target identity.
            run_id (str): Requesting Run identity.
            profile_id (str): Optional safe identity used only for diagnostics.

        Raises:
            StudioRunDeviceBusyError: Profile already has an owner.

        Yields:
            None: Lease remains held within the context.
        """
        with self._lock:
            owner = self._owners.get(target_key)
            if owner is not None and owner != run_id:
                raise StudioRunDeviceBusyError(
                    DeviceAuthorityCode.TARGET_BUSY.value,
                    "Selected local Android device is busy",
                )
            self._owners[target_key] = run_id
        try:
            yield
        finally:
            with self._lock:
                if self._owners.get(target_key) == run_id:
                    self._owners.pop(target_key, None)


class ProductionComponentResolverFactory:
    """Build one explicit run-scoped built-in/external component resolver."""

    def __init__(
        self,
        *,
        external_environment: DiscoveredComponentEnvironment | None = None,
        secret_provider: Mapping[str, Any] | Callable[[str], Any] | None = None,
        dependency_provider: Mapping[str, Any] | None = None,
        constructor_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Configure explicit production binding dependencies.

        Args:
            external_environment (DiscoveredComponentEnvironment | None):
                Already-discovered external catalog; no implicit scan occurs.
            secret_provider (Mapping[str, Any] | Callable[[str], Any] | None):
                Runtime-only secret reference provider.
            dependency_provider (Mapping[str, Any] | None): Explicit dependencies.
            constructor_kwargs (Mapping[str, Any] | None): Constructor defaults.

        Raises:
            None.

        Returns:
            None.
        """
        self.external_environment = (
            external_environment or empty_component_environment()
        )
        self.secret_provider = secret_provider
        self.dependency_provider = dict(dependency_provider or {})
        self.constructor_kwargs = dict(constructor_kwargs or {})

    def create(self) -> CatalogComponentResolver:
        """Build a fresh resolver without connecting a device.

        Args:
            None.

        Raises:
            None.

        Returns:
            CatalogComponentResolver: Run-scoped resolver with built-in fallback.
        """
        builtins = BuiltInComponentResolver(
            secret_provider=self.secret_provider,
            dependency_provider=self.dependency_provider,
            constructor_kwargs=self.constructor_kwargs,
        )
        return CatalogComponentResolver(
            self.external_environment.catalog,
            secret_provider=self.secret_provider,
            dependency_provider=self.dependency_provider,
            fallback=builtins,
        )

    def validate_graph_bindings(self, graph: AgentGraph) -> None:
        """Verify component identities and roles without constructing instances.

        Args:
            graph: Immutable AgentGraph selected for a future execution.

        Raises:
            StudioRunValidationError: A component node has no metadata-level
                candidate available in the configured environment.

        Returns:
            None.
        """
        external = self.external_environment.catalog
        for node in graph.nodes:
            if node.component is None or node.role is None:
                continue
            available = False
            for reference in node.component.candidates:
                built_in = BUILTIN_COMPONENT_CATALOG.get(
                    reference.namespace,
                    reference.name,
                )
                built_in_matches = bool(
                    built_in is not None
                    and (
                        reference.version is None
                        or reference.version == built_in.version
                    )
                )
                try:
                    external_entry = external.resolve(reference)
                except Exception:
                    external_entry = None
                if (
                    reference.version is None
                    and built_in_matches
                    and external_entry is not None
                ):
                    # Runtime resolution deliberately rejects this ambiguous
                    # unversioned identity, so preflight must do the same.
                    continue
                if external_entry is not None:
                    declared_role = external_entry.specification.role
                    if (
                        declared_role is None
                        or declared_role.value == node.role.value
                    ):
                        available = True
                        break
                if built_in_matches:
                    status = BUILTIN_COMPONENT_CATALOG.availability(
                        reference.namespace,
                        reference.name,
                    )
                    if status.available:
                        available = True
                        break
            if not available:
                raise StudioRunValidationError(
                    "studio.run.component_unavailable",
                    "AgentGraph component binding is unavailable",
                )


@dataclass(frozen=True)
class PreparedAndroidRun:
    """Bound execution plan plus internal device profile selection."""

    plan: Any
    profile: AndroidDeviceProfile


class AndroidStudioRunExecutionAdapter:
    """Bind one snapshot and delegate device execution to AndroidGraphRuntime."""

    def __init__(
        self,
        *,
        components: ProductionComponentResolverFactory,
        artifacts: LocalStudioRunArtifactStore,
        profiles: AndroidDeviceProfileResolver | None = None,
        leases: DeviceLeaseRegistry | None = None,
        contract_catalog: Any | None = None,
        component_catalog: StudioComponentCatalog | None = None,
        warning_sink: Callable[[str, tuple[str, ...]], None] | None = None,
    ) -> None:
        """Configure run-scoped binding, evidence, and device boundaries.

        Args:
            components (ProductionComponentResolverFactory): Resolver factory.
            artifacts (LocalStudioRunArtifactStore): Managed evidence store.
            profiles (AndroidDeviceProfileResolver | None): Device profiles.
            leases (DeviceLeaseRegistry | None): Exclusive local leases.
            contract_catalog (Any | None): Optional extension contract catalog.
            component_catalog: Exact safe Catalog used for worker policy preflight.
            warning_sink (Callable[[str, tuple[str, ...]], None] | None):
                Persistence callback for storage warnings.

        Raises:
            None.

        Returns:
            None.
        """
        self.components = components
        self.artifacts = artifacts
        self.profiles = profiles or AndroidDeviceProfileResolver()
        self.leases = leases or DeviceLeaseRegistry()
        self.contract_catalog = contract_catalog
        self.component_catalog = component_catalog or build_studio_component_catalog()
        self.warning_sink = warning_sink

    def prepare(self, record: StudioRunRecordV1) -> PreparedAndroidRun:
        """Verify graph identity and bind components before device side effects.

        Args:
            record (StudioRunRecordV1): Persisted immutable Run.

        Raises:
            StudioRunValidationError: Snapshot identity is invalid.
            GraphBindingError: Component or graph binding fails.

        Returns:
            PreparedAndroidRun: Bound plan and internal profile.
        """
        eligibility = evaluate_run_snapshot_eligibility(
            record.snapshot,
            catalog=self.component_catalog,
            contract_catalog=self.contract_catalog,
        )
        if not eligibility.current_policy_eligible:
            issue = eligibility.diagnostics[0]
            raise StudioRunValidationError(issue.code, issue.message)
        try:
            graph = AgentGraph.model_validate(record.snapshot.agent_graph)
            actual_hash = graph.canonical_hash(
                contract_catalog=self.contract_catalog
            )
        except Exception as error:
            raise StudioRunValidationError(
                "studio.run.graph_snapshot_invalid",
                "Run AgentGraph snapshot cannot be validated",
            ) from error
        if actual_hash != record.snapshot.canonical_hash:
            raise StudioRunValidationError(
                "studio.run.graph_identity_mismatch",
                "Run AgentGraph identity does not match its snapshot",
            )
        plan = bind_execution_plan(
            graph,
            self.components.create(),
            contract_catalog=self.contract_catalog,
        )
        profile = self.profiles.resolve(record.request.device_profile_id)
        return PreparedAndroidRun(plan=plan, profile=profile)

    def execute(
        self,
        record: StudioRunRecordV1,
        runtime: RuntimeContext,
    ) -> RunResult:
        """Execute one prepared Run through the existing Android Graph Runtime.

        Args:
            record (StudioRunRecordV1): Persisted immutable Run.
            runtime (RuntimeContext): Caller-owned event/debug/cancel context.

        Raises:
            StudioRunEvidenceError: Evidence preflight fails.
            StudioRunDeviceBusyError: Device profile has another owner.
            GraphBindingError: Component binding fails.

        Returns:
            RunResult: Canonical Android Runtime result.
        """
        prepared = self.prepare(record)
        if runtime.cancellation.is_cancelled():
            return _cancelled_result(record.run_id)
        warnings = self.artifacts.preflight()
        if self.warning_sink is not None:
            self.warning_sink(record.run_id, warnings)
        if runtime.cancellation.is_cancelled():
            return _cancelled_result(record.run_id)
        with self.leases.acquire(
            prepared.profile.target_key,
            record.run_id,
            profile_id=prepared.profile.profile_id,
        ):
            if runtime.cancellation.is_cancelled():
                return _cancelled_result(record.run_id)
            session = resolve_exact_android_session(prepared.profile)
            if runtime.cancellation.is_cancelled():
                return _cancelled_result(record.run_id)
            result = AndroidGraphRuntime().run(
                prepared.plan,
                {
                    "task": TaskInput(
                        instruction=record.request.task.text,
                        metadata=record.request.task.metadata,
                    ),
                    # This is a declarative request value, not an observation.
                    # Only an explicit DeviceObserve node may turn it into a
                    # screenshot/XML device side effect.
                    "value": ObservationRequest(include_ui_tree=True),
                },
                artifact_root=self.artifacts.runtime_root,
                serial=session.serial,
                runtime=runtime,
                device=session.device,
            )
            self.artifacts.register_runtime_namespace(record.run_id)
            return result


def _cancelled_result(run_id: str) -> RunResult:
    """Build a canonical pre-execution cancelled result.

    Args:
        run_id (str): Stable Run identity.

    Raises:
        None.

    Returns:
        RunResult: CANCELLED result without device side effects.
    """
    return RunResult(
        run_id=run_id,
        status=RunStatus.CANCELLED,
        state=AgentState(),
        error="Studio Run was cancelled before the next activation",
        error_details={"kernel_error_code": "runtime.cancelled"},
        kernel_status="cancelled",
    )


def _failure_result(
    run_id: str,
    error: Exception,
    *,
    code: str,
) -> RunResult:
    """Convert an orchestration exception into a safe canonical failure.

    Args:
        run_id (str): Stable Run identity.
        error (Exception): Internal failure.
        code (str): Stable public-safe error code.

    Raises:
        None.

    Returns:
        RunResult: Safe FAILURE result.
    """
    safe, _redacted, _truncated = redact_text(str(error), max_length=1000)
    return RunResult(
        run_id=run_id,
        status=RunStatus.FAILURE,
        state=AgentState(),
        error=safe or type(error).__name__,
        error_details={"kernel_error_code": code},
        kernel_status="not_started",
    )


class StudioRunOrchestrator:
    """Own worker lifecycle, cancellation, result, Replay, and terminal event."""

    _NONTERMINAL = (
        StudioRunLifecycle.ACCEPTED,
        StudioRunLifecycle.STARTING,
        StudioRunLifecycle.RUNNING,
        StudioRunLifecycle.CANCELLING,
    )

    def __init__(
        self,
        *,
        runs: StudioRunRepository,
        events: DurableRunEventService,
        execution: AndroidStudioRunExecutionAdapter,
        debug: StudioRunDebugCapture,
        process_owner_id: str,
        active: ActiveRunRegistry | None = None,
        replay: NativeRunReplayFinalizer | None = None,
    ) -> None:
        """Configure all explicit local Run orchestration boundaries.

        Args:
            runs (StudioRunRepository): Persistent lifecycle repository.
            events (DurableRunEventService): Durable event service.
            execution (AndroidStudioRunExecutionAdapter): Android adapter.
            debug (StudioRunDebugCapture): Explicit debug evidence sink.
            process_owner_id (str): Current process owner identity.
            active (ActiveRunRegistry | None): In-memory cancellation registry.
            replay (NativeRunReplayFinalizer | None): Optional native finalizer.

        Raises:
            None.

        Returns:
            None.
        """
        self.runs = runs
        self.events = events
        self.execution = execution
        self.debug = debug
        self.process_owner_id = process_owner_id
        self.active = active or ActiveRunRegistry()
        self.replay = replay

    def cancel_active(self, run_id: str) -> None:
        """Signal one worker in this process without changing persistence.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            None.

        Returns:
            None.
        """
        self.active.cancel(run_id)

    def _finish(
        self,
        run_id: str,
        result: RunResult,
        *,
        error_code: str = "",
    ) -> None:
        """Commit result, native Replay availability, and unique terminal event.

        Args:
            run_id (str): Stable Run identity.
            result (RunResult): Canonical Runtime result.
            error_code (str): Optional orchestration error code.

        Raises:
            StudioRunError: Result or terminal event persistence fails.

        Returns:
            None.
        """
        summary = StudioRunResultSummaryV1.from_runtime(
            result,
            error_code=error_code,
        )
        record, _won = self.runs.finish_run(
            run_id,
            summary,
            expected=self._NONTERMINAL,
        )
        replay_state = record.replay_availability
        replay_error = ""
        if self.replay is not None and replay_state is not RunEvidenceAvailability.AVAILABLE:
            try:
                self.replay.finalize(run_id)
                record = self.runs.set_replay_availability(
                    run_id,
                    RunEvidenceAvailability.AVAILABLE,
                )
            except Exception:
                replay_error = "studio.run.replay_finalization_failed"
                record = self.runs.set_replay_availability(
                    run_id,
                    RunEvidenceAvailability.MISSING,
                    error_code=replay_error,
                )
        high_water_mark = self.events.repository.high_water_mark(run_id)
        if high_water_mark:
            latest = self.events.repository.query_events(
                run_id,
                after=high_water_mark - 1,
                limit=1,
            )
            if latest.items and latest.items[-1].kind == "run.terminal":
                return
        persisted_result = record.result or summary
        self.events.append(
            run_id,
            self.events.service_event(
                kind="run.terminal",
                source="result",
                event_id="service-run-terminal",
                timestamp=(record.terminal_at or record.updated_at) / 1000,
                payload={
                    "result": persisted_result.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                    ),
                    "replayAvailability": record.replay_availability.value,
                    "replayErrorCode": replay_error,
                    "finalHighWaterMark": high_water_mark + 1,
                },
            ),
        )

    def execute(self, run_id: str) -> None:
        """Execute and deterministically finalize one persisted Run.

        Args:
            run_id (str): Stable Run identity scheduled by the local service.

        Raises:
            StudioRunError: Terminal evidence cannot be persisted.

        Returns:
            None.
        """
        signal = SimpleCancellationSignal()
        self.active.register(run_id, signal)
        try:
            record = self.runs.get_run(run_id)
            if record.cancellation_requested or (
                record.lifecycle is StudioRunLifecycle.CANCELLING
            ):
                signal.cancel()
                self._finish(run_id, _cancelled_result(run_id))
                return
            try:
                self.runs.transition(
                    run_id,
                    expected=(StudioRunLifecycle.ACCEPTED,),
                    target=StudioRunLifecycle.STARTING,
                    process_owner_id=self.process_owner_id,
                )
                self.events.append(
                    run_id,
                    self.events.service_event(
                        kind="run.starting",
                        event_id="service-run-starting",
                    ),
                )
                current = self.runs.get_run(run_id)
                if current.cancellation_requested:
                    signal.cancel()
                    self._finish(run_id, _cancelled_result(run_id))
                    return
                record = self.runs.transition(
                    run_id,
                    expected=(StudioRunLifecycle.STARTING,),
                    target=StudioRunLifecycle.RUNNING,
                )
                self.events.append(
                    run_id,
                    self.events.service_event(
                        kind="run.running",
                        event_id="service-run-running",
                    ),
                )
                runtime = RuntimeContext(
                    run_id=run_id,
                    max_steps=record.snapshot.agent_graph.get(
                        "policies",
                        {},
                    ).get("max_steps", 15),
                    event_sink=self.events.runtime_sink(run_id, signal),
                    debug_sink=self.debug.capture,
                    cancellation=signal,
                )
                result = self.execution.execute(record, runtime)
                self._finish(run_id, result)
            except Exception as error:
                code = getattr(error, "code", "")
                if not code:
                    info = getattr(error, "info", None)
                    code = getattr(info, "code", "") or "studio.run.execution_failed"
                self._finish(
                    run_id,
                    _failure_result(run_id, error, code=code),
                    error_code=code,
                )
        finally:
            self.active.remove(run_id)

    def reject_scheduling(self, run_id: str, error: Exception) -> None:
        """Terminally reject a persisted Run that cannot obtain a worker slot.

        Args:
            run_id (str): Stable Run identity.
            error (Exception): Bounded scheduler rejection.

        Raises:
            StudioRunError: Terminal evidence cannot be persisted.

        Returns:
            None.
        """
        code = getattr(error, "code", "studio.run.scheduler_busy")
        self._finish(
            run_id,
            _failure_result(run_id, error, code=code),
            error_code=code,
        )

    def recover_interrupted(self) -> tuple[str, ...]:
        """Finalize all nonterminal Runs left by a different process owner.

        Args:
            None.

        Raises:
            StudioRunError: Recovery evidence cannot be persisted.

        Returns:
            tuple[str, ...]: Recovered Run identities.
        """
        recovered: list[str] = []
        for record in self.runs.list_nonterminal_for_other_owner(
            self.process_owner_id
        ):
            error = StudioRunEvidenceError(
                "studio.run.service_restarted",
                "Studio service restarted before the Run reached a checkpoint",
            )
            self._finish(
                record.run_id,
                _failure_result(
                    record.run_id,
                    error,
                    code=error.code,
                ),
                error_code=error.code,
            )
            recovered.append(record.run_id)
        return tuple(recovered)


def new_process_owner_id() -> str:
    """Create one opaque local process ownership identity.

    Args:
        None.

    Raises:
        None.

    Returns:
        str: Process-scoped opaque identity.
    """
    return f"process-{uuid.uuid4().hex}"


__all__ = [
    "ActiveRunRegistry",
    "AndroidDeviceProfile",
    "AndroidDeviceProfileResolver",
    "AndroidStudioRunExecutionAdapter",
    "DeviceLeaseRegistry",
    "LocalThreadRunScheduler",
    "ProductionComponentResolverFactory",
    "StudioRunOrchestrator",
    "new_process_owner_id",
]
