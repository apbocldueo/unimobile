"""Stage 5.2A application service for durable Benchmark Experiment resources."""

from __future__ import annotations

import re
import time
import uuid
from typing import Any, Callable, Mapping

from pydantic import ValidationError

from zhixing.benchmark.identity import canonical_hash

from .benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkSnapshotTooLargeError,
    StudioBenchmarkValidationError,
)
from .benchmark_experiment_models import (
    ExperimentDefinitionSnapshotV1,
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkExperimentCancelRequestV1,
    StudioBenchmarkExperimentCancellationV1,
    StudioBenchmarkExperimentCreateRequestV1,
    StudioBenchmarkExperimentCreateResponseV1,
    StudioBenchmarkExperimentHistoryFilterV1,
    StudioBenchmarkExperimentHistoryItemV1,
    StudioBenchmarkExperimentHistoryPageV1,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentRecordV1,
    StudioBenchmarkExperimentResourceV1,
    StudioBenchmarkSourceSnapshotV1,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunPageV1,
    StudioBenchmarkTaskRunRecordV1,
    canonical_experiment_request_fingerprint,
    canonical_snapshot_json,
)
from .benchmark_experiment_protocols import (
    StudioBenchmarkExperimentBindingAuthority,
    StudioBenchmarkExperimentRepository,
)
from .benchmark_publication_models import (
    StudioBenchmarkArtifactInventoryItemV1,
    StudioBenchmarkArtifactInventoryPageV1,
)
from .benchmark_publication_protocols import (
    StudioBenchmarkPublicationRepository,
)
from .benchmark_service import StudioBenchmarkApplicationService


Clock = Callable[[], int]
IdentityFactory = Callable[[str], str]
DispatchCallback = Callable[[str, bool], None]
CancelCallback = Callable[[str], bool]
_EXPERIMENT_ID = re.compile(r"^experiment-[a-f0-9]{32}$")
_TASK_RUN_ID = re.compile(r"^task-run-[a-f0-9]{32}$")


def _now_ms() -> int:
    """Return wall-clock time in Unix epoch milliseconds.

    Returns:
        Integer Unix epoch milliseconds.
    """
    return time.time_ns() // 1_000_000


def _new_identity(kind: str) -> str:
    """Generate one opaque identity for an allowed resource kind.

    Args:
        kind: ``experiment``, ``task-run``, or ``benchmark-event``.

    Raises:
        ValueError: Kind is unknown.

    Returns:
        Opaque identity with a random 128-bit suffix.
    """
    if kind not in {"experiment", "task-run", "benchmark-event"}:
        raise ValueError("unknown Benchmark Experiment identity kind")
    return f"{kind}-{uuid.uuid4().hex}"


class StudioBenchmarkExperimentApplicationService:
    """Create, query, dispatch, and cooperatively cancel durable Experiments."""

    def __init__(
        self,
        *,
        definitions: StudioBenchmarkApplicationService,
        repository: StudioBenchmarkExperimentRepository,
        publication_repository: StudioBenchmarkPublicationRepository | None = None,
        clock: Clock = _now_ms,
        identity_factory: IdentityFactory = _new_identity,
        dispatch: DispatchCallback | None = None,
        cancel_active: CancelCallback | None = None,
        execution_enabled: bool = False,
        event_transport_enabled: bool = False,
        publication_enabled: bool = False,
    ) -> None:
        """Configure definition and persistence boundaries.

        Args:
            definitions: Existing pure Catalog/Composer application service.
            repository: Typed durable Experiment aggregate repository.
            publication_repository: Optional managed publication metadata
                repository used only by reporting inventory queries.
            clock: Injectable integer-millisecond clock.
            identity_factory: Injectable opaque identity factory.
            dispatch: Optional post-commit enrollment and worker wake callback.
            cancel_active: Optional post-persistence active signal callback.
            execution_enabled: Whether this process owns a Benchmark worker.
            event_transport_enabled: Whether public event query/SSE routes are
                fully composed for projected resources.
            publication_enabled: Whether managed report, bundle, artifact, and
                native Replay routes are fully composed.

        Returns:
            None.
        """
        self.definitions = definitions
        self.repository = repository
        self.publication_repository = publication_repository
        self._clock = clock
        self._identity_factory = identity_factory
        self._dispatch = dispatch
        self._cancel_active = cancel_active
        self._execution_enabled = bool(execution_enabled)
        self._event_transport_enabled = bool(event_transport_enabled)
        self._publication_enabled = bool(publication_enabled)

    @staticmethod
    def parse_create_request(
        raw: Mapping[str, Any],
    ) -> StudioBenchmarkExperimentCreateRequestV1:
        """Parse an untrusted complete create request.

        Args:
            raw: Browser-submitted JSON mapping.

        Raises:
            StudioBenchmarkValidationError: Request violates the strict DTO.

        Returns:
            Strict complete create request.
        """
        try:
            return StudioBenchmarkExperimentCreateRequestV1.model_validate(
                dict(raw)
            )
        except ValidationError as error:
            first = error.errors(include_url=False, include_input=False)[0]
            location = ".".join(str(item) for item in first["loc"])
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.request_invalid",
                "Invalid Benchmark Experiment request at "
                f"{location}: {first['msg']}",
            ) from error

    @staticmethod
    def parse_cancel_request(
        raw: Mapping[str, Any],
    ) -> StudioBenchmarkExperimentCancelRequestV1:
        """Parse an untrusted cooperative cancellation request.

        Args:
            raw: Browser-submitted JSON mapping.

        Raises:
            StudioBenchmarkValidationError: Request violates the strict DTO.

        Returns:
            Strict cancel command.
        """
        try:
            return StudioBenchmarkExperimentCancelRequestV1.model_validate(
                dict(raw)
            )
        except ValidationError as error:
            first = error.errors(include_url=False, include_input=False)[0]
            location = ".".join(str(item) for item in first["loc"])
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.cancel_request_invalid",
                "Invalid Benchmark Experiment cancellation at "
                f"{location}: {first['msg']}",
            ) from error

    @staticmethod
    def validate_experiment_id(experiment_id: str) -> str:
        """Validate an opaque Experiment path identity.

        Args:
            experiment_id: URL-decoded identity.

        Raises:
            StudioBenchmarkValidationError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(experiment_id) is None:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.identifier_invalid",
                "Benchmark Experiment identity is invalid",
            )
        return experiment_id

    @staticmethod
    def validate_task_run_id(task_run_id: str) -> str:
        """Validate an opaque TaskRun path identity.

        Args:
            task_run_id: URL-decoded identity.

        Raises:
            StudioBenchmarkValidationError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _TASK_RUN_ID.fullmatch(task_run_id) is None:
            raise StudioBenchmarkValidationError(
                "benchmark.task_run.identifier_invalid",
                "Benchmark TaskRun identity is invalid",
            )
        return task_run_id

    def _build_snapshot(
        self,
        request: StudioBenchmarkExperimentCreateRequestV1,
    ) -> tuple[
        ExperimentDefinitionSnapshotV1,
        tuple[StudioBenchmarkTaskRunRecordV1, ...],
        int,
        str,
    ]:
        """Prepare current facts once and build the complete accepted snapshot.

        Args:
            request: Strict request with complete preview definition.

        Raises:
            StudioBenchmarkConflictError: Current definition drifted.
            StudioBenchmarkSnapshotTooLargeError: Snapshot exceeds 2 MiB.
            StudioBenchmarkValidationError: Current definition is invalid.

        Returns:
            Snapshot, TaskRuns, acceptance timestamp, and Experiment identity.
        """
        prepared = self.definitions.prepare_definition(request.definition)
        preview = prepared.preview
        if preview.preview_fingerprint != request.preview_fingerprint:
            raise StudioBenchmarkConflictError(
                "benchmark.experiment.definition_conflict",
                "Benchmark definition changed after preview",
            )
        plan = prepared.benchmark_plan
        if plan.package_identity is None or plan.package_content_identity is None:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.package_identity_missing",
                "Benchmark Package identity is incomplete",
            )
        source = StudioBenchmarkSourceSnapshotV1(
            source_id=prepared.source_id,
            source_kind=prepared.source_kind,
            relative_key=prepared.relative_key,
            catalog_entry_id=request.definition.benchmark.catalog_entry_id,
            package_identity=plan.package_identity,
            package_content_identity=plan.package_content_identity,
            benchmark_plan_identity=plan.canonical_hash(),
            experiment_protocol_identity=request.definition.protocol.canonical_hash(),
        )
        snapshot_payload = {
            "contract": "studio-benchmark-experiment-definition-v1",
            "previewFingerprint": preview.preview_fingerprint,
            "source": source.model_dump(
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
                for item in prepared.agent_snapshots
            ],
            "benchmarkPlan": plan.model_dump(mode="json", exclude_none=True),
            "protocol": request.definition.protocol.canonical_payload(),
            "split": request.definition.benchmark.split,
            "taskIds": list(request.definition.benchmark.task_ids),
            "schedule": [
                item.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                )
                for item in preview.schedule
            ],
            "deviceProfileId": request.definition.device_profile_id,
            "executionLimits": preview.execution_limits.model_dump(
                mode="json",
                by_alias=True,
            ),
        }
        snapshot = ExperimentDefinitionSnapshotV1(
            preview_fingerprint=preview.preview_fingerprint,
            snapshot_fingerprint=canonical_hash(snapshot_payload),
            source=source,
            agent_snapshots=prepared.agent_snapshots,
            benchmark_plan=plan,
            protocol=request.definition.protocol,
            split=request.definition.benchmark.split,
            task_ids=request.definition.benchmark.task_ids,
            schedule=preview.schedule,
            device_profile_id=request.definition.device_profile_id,
            execution_limits=preview.execution_limits,
        )
        try:
            canonical_snapshot_json(snapshot)
        except ValueError as error:
            raise StudioBenchmarkSnapshotTooLargeError(
                "benchmark.experiment.snapshot_too_large",
                "Benchmark Experiment definition snapshot exceeds 2097152 bytes",
            ) from error
        accepted_at = self._clock()
        experiment_id = self._identity_factory("experiment")
        task_runs = tuple(
            StudioBenchmarkTaskRunRecordV1(
                task_run_id=self._identity_factory("task-run"),
                experiment_id=experiment_id,
                planned_entry_id=item.planned_entry_id,
                order=item.order,
                agent_id=item.agent_id,
                revision_id=item.revision_id,
                task_id=item.task_id,
                repeat=item.repeat,
                derived_seed=item.derived_seed,
                lifecycle=StudioBenchmarkTaskRunLifecycle.SCHEDULED,
                created_at=accepted_at,
                updated_at=accepted_at,
            )
            for item in preview.schedule
        )
        return snapshot, task_runs, accepted_at, experiment_id

    def create_experiment(
        self,
        raw: Mapping[str, Any] | StudioBenchmarkExperimentCreateRequestV1,
    ) -> StudioBenchmarkExperimentCreateResponseV1:
        """Create or idempotently return a durable accepted Experiment.

        Durable idempotency is resolved before current Catalog/revision
        preparation, preserving an already-committed fact across source drift.

        Args:
            raw: Strict DTO or untrusted browser request.

        Raises:
            StudioBenchmarkConflictError: Idempotency or definition conflicts.
            StudioBenchmarkValidationError: Request/current definition invalid.
            StudioBenchmarkSnapshotTooLargeError: Snapshot exceeds 2 MiB.

        Returns:
            Versioned create wrapper with a truthful created flag.
        """
        request = (
            raw
            if isinstance(raw, StudioBenchmarkExperimentCreateRequestV1)
            else self.parse_create_request(raw)
        )
        fingerprint = canonical_experiment_request_fingerprint(request)
        existing = self.repository.find_by_client_request_id(
            request.client_request_id
        )
        if existing is not None:
            if existing.request_fingerprint != fingerprint:
                raise StudioBenchmarkConflictError(
                    "benchmark.experiment.idempotency_conflict",
                    "Client request identity is already used",
                )
            if self._dispatch is not None:
                self._dispatch(existing.experiment_id, False)
            return StudioBenchmarkExperimentCreateResponseV1(
                created=False,
                experiment=StudioBenchmarkExperimentResourceV1.from_record(
                    existing,
                    execution_enabled=self._execution_enabled,
                    event_transport_enabled=self._event_transport_enabled,
                    publication_enabled=self._publication_enabled,
                ),
            )
        snapshot, task_runs, accepted_at, experiment_id = self._build_snapshot(
            request
        )
        private_binding = self.definitions.profiles.binding_authority(
            snapshot.device_profile_id
        )
        binding_authority = StudioBenchmarkExperimentBindingAuthority(
            experiment_id=experiment_id,
            profile_id=private_binding.profile_id,
            binding_fingerprint=private_binding.binding_fingerprint,
            environment_candidate=private_binding.environment_candidate,
            created_at=accepted_at,
        )
        record = StudioBenchmarkExperimentRecordV1(
            experiment_id=experiment_id,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
            request=request,
            definition=snapshot,
            lifecycle=StudioBenchmarkExperimentLifecycle.ACCEPTED,
            event_high_water_mark=1,
            accepted_at=accepted_at,
            updated_at=accepted_at,
        )
        initial_event = StudioBenchmarkEventDraftV1(
            event_id=self._identity_factory("benchmark-event"),
            timestamp=accepted_at,
            kind="experiment.accepted",
            payload={
                "snapshotFingerprint": snapshot.snapshot_fingerprint,
                "taskRunCount": len(task_runs),
            },
        )
        result = self.repository.create_accepted_experiment(
            experiment=record,
            request=request,
            snapshot=snapshot,
            task_runs=task_runs,
            initial_event=initial_event,
            binding_authority=binding_authority,
        )
        if self._dispatch is not None:
            self._dispatch(
                result.aggregate.experiment.experiment_id,
                result.created,
            )
        return StudioBenchmarkExperimentCreateResponseV1(
            created=result.created,
            experiment=StudioBenchmarkExperimentResourceV1.from_record(
                result.aggregate.experiment,
                execution_enabled=self._execution_enabled,
                event_transport_enabled=self._event_transport_enabled,
                publication_enabled=self._publication_enabled,
            ),
        )

    def get_experiment(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkExperimentResourceV1:
        """Return one safe durable Experiment resource.

        Args:
            experiment_id: Opaque Experiment identity.

        Raises:
            StudioBenchmarkValidationError: Identity syntax is invalid.
            StudioBenchmarkNotFoundError: Experiment is absent.

        Returns:
            Safe public Experiment resource.
        """
        record = self.repository.get_experiment(
            self.validate_experiment_id(experiment_id)
        )
        return StudioBenchmarkExperimentResourceV1.from_record(
            record,
            execution_enabled=self._execution_enabled,
            event_transport_enabled=self._event_transport_enabled,
            publication_enabled=self._publication_enabled,
        )

    def list_experiments(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        filters: StudioBenchmarkExperimentHistoryFilterV1 | None = None,
    ) -> StudioBenchmarkExperimentHistoryPageV1:
        """Return compact filtered newest-first durable Experiment history.

        Args:
            limit: Requested page size within 1..100.
            cursor: Optional opaque continuation cursor.
            filters: Optional exact durable History query identity.

        Raises:
            StudioBenchmarkValidationError: Limit or cursor is invalid.
            StudioBenchmarkError: Storage facts cannot be read safely.

        Returns:
            Bounded history page projected only from immutable durable facts.
        """
        page = self.repository.list_experiments(
            limit=limit,
            cursor=cursor,
            filters=filters,
        )
        return StudioBenchmarkExperimentHistoryPageV1(
            items=tuple(
                StudioBenchmarkExperimentHistoryItemV1.from_record(
                    record,
                    publication_enabled=self._publication_enabled,
                )
                for record in page.items
            ),
            next_cursor=page.next_cursor,
        )

    def list_artifact_inventory(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkArtifactInventoryPageV1:
        """Return visible Experiment artifact metadata and safe content links.

        Args:
            experiment_id: Opaque owning Experiment identity.
            limit: Requested visible page size within 1..100.
            cursor: Optional opaque Experiment-bound continuation cursor.

        Raises:
            StudioBenchmarkValidationError: Identity, limit, or cursor invalid.
            StudioBenchmarkNotFoundError: Publication service or Experiment is
                unavailable.
            StudioBenchmarkError: Stored metadata cannot be read safely.

        Returns:
            Metadata-only inventory with aggregate hidden count.
        """
        validated = self.validate_experiment_id(experiment_id)
        if (
            not self._publication_enabled
            or self.publication_repository is None
        ):
            raise StudioBenchmarkNotFoundError(
                "benchmark.publication.unavailable",
                "Benchmark publication service is not configured",
            )
        page = self.publication_repository.list_artifact_metadata(
            validated,
            limit=limit,
            cursor=cursor,
        )
        return StudioBenchmarkArtifactInventoryPageV1(
            experiment_id=page.experiment_id,
            items=tuple(
                StudioBenchmarkArtifactInventoryItemV1.from_descriptor(
                    descriptor
                )
                for descriptor in page.items
            ),
            hidden_count=page.hidden_count,
            next_cursor=page.next_cursor,
        )

    def list_task_runs(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkTaskRunPageV1:
        """List stable planned TaskRuns for one Experiment.

        Args:
            experiment_id: Opaque Experiment identity.
            limit: Page size within 1..100.
            cursor: Optional opaque scoped continuation cursor.

        Raises:
            StudioBenchmarkValidationError: Identity, limit, or cursor invalid.
            StudioBenchmarkNotFoundError: Experiment is absent.

        Returns:
            Stable bounded TaskRun page.
        """
        return self.repository.list_task_runs(
            self.validate_experiment_id(experiment_id),
            limit=limit,
            cursor=cursor,
        )

    def get_task_run(
        self,
        experiment_id: str,
        task_run_id: str,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Return one TaskRun through its owning Experiment scope.

        Args:
            experiment_id: Opaque Experiment identity.
            task_run_id: Opaque TaskRun identity.

        Raises:
            StudioBenchmarkValidationError: Either identity is invalid.
            StudioBenchmarkNotFoundError: Scoped TaskRun is absent.

        Returns:
            Safe storage-neutral TaskRun resource.
        """
        return self.repository.get_task_run(
            self.validate_experiment_id(experiment_id),
            self.validate_task_run_id(task_run_id),
        )

    def cancel_experiment(
        self,
        experiment_id: str,
        raw: Mapping[str, Any] | StudioBenchmarkExperimentCancelRequestV1,
    ) -> StudioBenchmarkExperimentResourceV1:
        """Persist cancellation before notifying an optional active worker.

        Args:
            experiment_id: Opaque Experiment identity.
            raw: Strict DTO or untrusted cancel request.

        Raises:
            StudioBenchmarkValidationError: Request or identity is invalid.
            StudioBenchmarkConflictError: Cancellation loses a transition race.
            StudioBenchmarkNotFoundError: Experiment is absent.

        Returns:
            Current accepted-cancelled, active-cancelling, finalizing, or
            immutable terminal resource.
        """
        request = (
            raw
            if isinstance(raw, StudioBenchmarkExperimentCancelRequestV1)
            else self.parse_cancel_request(raw)
        )
        cancellation = StudioBenchmarkExperimentCancellationV1(
            client_request_id=request.client_request_id,
            requested_at=self._clock(),
            reason_code=request.reason_code,
        )
        aggregate = self.repository.request_cancellation(
            self.validate_experiment_id(experiment_id),
            cancellation,
        )
        if self._cancel_active is not None:
            self._cancel_active(aggregate.experiment.experiment_id)
        return StudioBenchmarkExperimentResourceV1.from_record(
            aggregate.experiment,
            execution_enabled=self._execution_enabled,
            event_transport_enabled=self._event_transport_enabled,
            publication_enabled=self._publication_enabled,
        )


__all__ = ["StudioBenchmarkExperimentApplicationService"]
