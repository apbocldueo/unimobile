"""Database-neutral protocols for Studio Run persistence and execution."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any, BinaryIO, Protocol

from zhixing.components import RunResult

from .run_models import (
    CreateStudioRunRequestV1,
    RunEvidenceAvailability,
    RunSnapshotV1,
    StudioRunArtifactDescriptorV1,
    StudioRunArtifactRecordV1,
    StudioRunEventDraftV1,
    StudioRunEventEnvelopeV1,
    StudioRunEventPageV1,
    StudioRunLifecycle,
    StudioRunRecordV1,
    StudioRunResultSummaryV1,
)


class StudioRunRepository(Protocol):
    """Persistence contract for immutable Run snapshots and lifecycle state."""

    def create_run(
        self,
        request: CreateStudioRunRequestV1,
        snapshot: RunSnapshotV1,
        *,
        process_owner_id: str,
    ) -> tuple[StudioRunRecordV1, bool]:
        """Create or return an idempotent Run and whether it was newly created."""

    def get_by_client_request_id(
        self,
        client_request_id: str,
    ) -> StudioRunRecordV1 | None:
        """Return an existing idempotency record before new-run validation."""

    def get_run(self, run_id: str) -> StudioRunRecordV1:
        """Read one Run by stable identity."""

    def transition(
        self,
        run_id: str,
        *,
        expected: tuple[StudioRunLifecycle, ...],
        target: StudioRunLifecycle,
        process_owner_id: str | None = None,
    ) -> StudioRunRecordV1:
        """Apply one compare-and-swap lifecycle transition."""

    def request_cancel(self, run_id: str) -> StudioRunRecordV1:
        """Persist an idempotent cancellation request."""

    def finish_run(
        self,
        run_id: str,
        result: StudioRunResultSummaryV1,
        *,
        expected: tuple[StudioRunLifecycle, ...],
    ) -> tuple[StudioRunRecordV1, bool]:
        """Commit one terminal result and report whether this call won."""

    def set_replay_availability(
        self,
        run_id: str,
        availability: RunEvidenceAvailability,
        *,
        error_code: str = "",
    ) -> StudioRunRecordV1:
        """Update native Replay finalization availability."""

    def set_storage_warnings(
        self,
        run_id: str,
        warnings: tuple[str, ...],
    ) -> StudioRunRecordV1:
        """Persist bounded storage warning codes for one Run."""

    def list_nonterminal_for_other_owner(
        self,
        process_owner_id: str,
    ) -> tuple[StudioRunRecordV1, ...]:
        """List nonterminal Runs that do not belong to the active process."""


class StudioRunEventRepository(Protocol):
    """Persistence contract for the durable run-scoped event journal."""

    def append_event(
        self,
        run_id: str,
        event: StudioRunEventDraftV1,
    ) -> tuple[StudioRunEventEnvelopeV1, bool]:
        """Append or idempotently return one journal event."""

    def query_events(
        self,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioRunEventPageV1:
        """Read one bounded continuous event page."""

    def high_water_mark(self, run_id: str) -> int:
        """Return the latest committed journal sequence."""


class StudioRunArtifactRepository(Protocol):
    """Persistence contract for managed Run artifact descriptors."""

    def put_artifact(self, record: StudioRunArtifactRecordV1) -> None:
        """Create one immutable artifact record."""

    def get_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> StudioRunArtifactRecordV1:
        """Resolve one artifact only within its owning Run."""

    def list_artifacts(
        self,
        run_id: str,
    ) -> tuple[StudioRunArtifactRecordV1, ...]:
        """List artifact records for one Run in stable order."""

    def update_artifact_availability(
        self,
        run_id: str,
        artifact_id: str,
        availability: RunEvidenceAvailability,
    ) -> StudioRunArtifactRecordV1:
        """Update integrity availability after a verified read failure."""


class RunScheduler(Protocol):
    """Bounded background scheduling boundary for Run identities."""

    def submit(self, run_id: str, execute: Callable[[str], None]) -> None:
        """Schedule one persisted Run identity."""

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting work and release worker resources."""


class RunExecutionAdapter(Protocol):
    """Execute one persisted Run through an explicit runtime boundary."""

    def execute(self, record: StudioRunRecordV1, runtime: Any) -> RunResult:
        """Execute one Run record with a caller-owned RuntimeContext."""


class NativeRunReplayFinalizer(Protocol):
    """Register one terminal managed Run as an immutable Replay."""

    def finalize(self, run_id: str) -> Any:
        """Create or return the native Replay for a terminal Run."""


class ManagedRunArtifactStore(Protocol):
    """Managed local content contract for live Run evidence."""

    def preflight(self) -> tuple[str, ...]:
        """Verify storage and return non-blocking warning codes."""

    def write_bytes(
        self,
        run_id: str,
        *,
        kind: str,
        content_type: str,
        content: bytes,
        hidden: bool = False,
        provenance: str = "native_studio_run",
        causal_identity: str = "",
        original_size: int | None = None,
    ) -> StudioRunArtifactDescriptorV1:
        """Persist and register one bounded artifact."""

    def open_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> tuple[StudioRunArtifactDescriptorV1, BinaryIO]:
        """Open one verified non-hidden managed artifact."""

    def path_for_record(self, record: StudioRunArtifactRecordV1) -> Path:
        """Resolve one internal record to a verified managed path."""


__all__ = [
    "ManagedRunArtifactStore",
    "NativeRunReplayFinalizer",
    "RunExecutionAdapter",
    "RunScheduler",
    "StudioRunArtifactRepository",
    "StudioRunEventRepository",
    "StudioRunRepository",
]
