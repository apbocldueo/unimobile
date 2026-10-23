"""Database-neutral ports for Studio Benchmark publication and Replay."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Protocol

from zhixing.benchmark import BenchmarkSuiteResult

from .benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkExperimentRecordV1,
    StudioBenchmarkTaskRunRecordV1,
)
from .benchmark_publication_models import (
    StudioBenchmarkArtifactAvailability,
    StudioBenchmarkArtifactDescriptorV1,
    StudioBenchmarkArtifactMetadataPageV1,
    StudioBenchmarkManagedArtifactRecordV1,
    StudioBenchmarkPreparedPublicationV1,
    StudioBenchmarkPublicationRecordV1,
)
from .replay_contracts import ReplayArtifactRecord
from .replay_models import ReplayEvidenceEnvelope


class StudioBenchmarkPublicationRepository(Protocol):
    """Persistence port for publication metadata and coordinated visibility."""

    def get_publication(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkPublicationRecordV1 | None:
        """Return a committed publication or ``None``."""
        ...

    def get_artifact(
        self,
        experiment_id: str,
        artifact_id: str,
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Resolve one managed artifact only in its owning Experiment."""
        ...

    def list_artifacts(
        self,
        experiment_id: str,
        *,
        task_run_id: str | None = None,
    ) -> tuple[StudioBenchmarkManagedArtifactRecordV1, ...]:
        """List bounded managed descriptors for one scope."""
        ...

    def list_artifact_metadata(
        self,
        experiment_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> StudioBenchmarkArtifactMetadataPageV1:
        """List visible descriptor metadata without opening artifact bodies."""
        ...

    def update_artifact_availability(
        self,
        experiment_id: str,
        artifact_id: str,
        availability: StudioBenchmarkArtifactAvailability,
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Close one missing or corrupt artifact fact."""
        ...

    def commit_publication(
        self,
        *,
        publication: StudioBenchmarkPublicationRecordV1,
        artifacts: tuple[StudioBenchmarkManagedArtifactRecordV1, ...],
        replay: ReplayEvidenceEnvelope | None,
        replay_artifacts: tuple[ReplayArtifactRecord, ...],
        events: tuple[StudioBenchmarkEventDraftV1, ...],
    ) -> StudioBenchmarkPublicationRecordV1:
        """Atomically expose publication, artifacts, Replay, mappings, events."""
        ...


class StudioBenchmarkPublicationPreparer(Protocol):
    """Prepare formal Core reporting output in an owned private namespace."""

    def prepare(
        self,
        suite: BenchmarkSuiteResult,
        *,
        planned_task_run_id: str,
        definition_snapshot: dict[str, object],
        prepared_at: int,
    ) -> StudioBenchmarkPreparedPublicationV1:
        """Write and describe complete formal reporting output."""
        ...

    def load(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkPreparedPublicationV1:
        """Load and verify one previously prepared private manifest."""
        ...

    def member_path(
        self,
        experiment_id: str,
        reference: str,
    ) -> Path:
        """Resolve one declared member beneath its private staging root."""
        ...


class StudioBenchmarkManagedArtifactStore(Protocol):
    """Opaque managed content boundary independent from host paths."""

    def import_file(
        self,
        *,
        experiment_id: str,
        task_run_id: str | None,
        reference: str,
        kind: str,
        content_type: str,
        source: Path,
        trusted_root: Path,
        expected_sha256: str,
        hidden: bool = False,
        causal_identity: str = "",
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Verify, store, and return one stable managed artifact record."""
        ...

    def open_artifact(
        self,
        experiment_id: str,
        artifact_id: str,
    ) -> tuple[StudioBenchmarkArtifactDescriptorV1, BinaryIO]:
        """Open one verified readable artifact."""
        ...

    def storage_path(
        self,
        record: StudioBenchmarkManagedArtifactRecordV1,
    ) -> Path:
        """Resolve an internal record beneath the managed root."""
        ...


class StudioBenchmarkBundleVerifier(Protocol):
    """Verify an exported Studio Benchmark Experiment bundle."""

    def verify(self, source: str | Path) -> bool:
        """Return true only for a complete safe digest-verified bundle."""
        ...


class StudioBenchmarkReplayPublisher(Protocol):
    """Build native Benchmark Replay without independently committing it."""

    def build(
        self,
        *,
        experiment: StudioBenchmarkExperimentRecordV1,
        task_run: StudioBenchmarkTaskRunRecordV1,
        replay_id: str,
        imported_at: int,
        artifacts: tuple[StudioBenchmarkManagedArtifactRecordV1, ...],
    ) -> ReplayEvidenceEnvelope:
        """Build a validated Replay envelope from durable facts."""
        ...


class StudioBenchmarkPublisher(Protocol):
    """Idempotently promote a terminal TaskRun into public evidence."""

    def publish(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        timestamp: int,
    ) -> StudioBenchmarkPublicationRecordV1:
        """Publish formal evidence and native Replay for one TaskRun."""
        ...


__all__ = [
    "StudioBenchmarkBundleVerifier",
    "StudioBenchmarkManagedArtifactStore",
    "StudioBenchmarkPublicationPreparer",
    "StudioBenchmarkPublicationRepository",
    "StudioBenchmarkPublisher",
    "StudioBenchmarkReplayPublisher",
]
