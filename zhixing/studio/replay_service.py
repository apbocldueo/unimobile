"""Application service for offline Studio Replay import and read access."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

from .replay_adapters import (
    LegacyBenchmarkReplayAdapter,
    NativeReplayPackageAdapter,
)
from .replay_models import ReplayArtifactDescriptor, ReplayEvidenceEnvelope, ReplayPage
from .replay_storage import (
    ReplayArtifactStore,
    ReplayBundleStore,
    SQLiteReplayRepository,
    default_studio_artifact_directory,
)


class ReplayApplicationService:
    """Orchestrate explicit imports and bounded read-only Replay use cases."""

    def __init__(
        self,
        *,
        repository: SQLiteReplayRepository,
        artifact_store: ReplayArtifactStore,
        bundle_store: ReplayBundleStore,
    ) -> None:
        """Configure explicit Replay persistence boundaries.

        Args:
            repository (SQLiteReplayRepository): Structured metadata adapter.
            artifact_store (ReplayArtifactStore): Managed binary content store.
            bundle_store (ReplayBundleStore): Versioned export boundary.

        Raises:
            None.

        Returns:
            None.
        """
        self.repository = repository
        self.artifact_store = artifact_store
        self.bundle_store = bundle_store

    def import_native_package(self, source: str | Path) -> ReplayEvidenceEnvelope:
        """Import one explicit native Replay package.

        Args:
            source (str | Path): Caller-authorized local ZIP path.

        Raises:
            ReplayImportError: Package is invalid or unsafe.
            ReplayConflictError: Run was already imported.
            OSError: Source or managed storage cannot be read.

        Returns:
            ReplayEvidenceEnvelope: Persisted immutable Replay.
        """
        candidate = NativeReplayPackageAdapter().load(Path(source))
        return self.artifact_store.import_candidate(candidate)

    def import_legacy_benchmark(
        self,
        run_directory: str | Path,
        *,
        benchmark_result: str | Path | None = None,
        artifact_root: str | Path | None = None,
        graph_snapshot: str | Path | None = None,
        provenance: str = "legacy_benchmark_import",
    ) -> ReplayEvidenceEnvelope:
        """Import one explicit legacy Benchmark task-run directory.

        Args:
            run_directory (str | Path): Directory containing result and
                trajectory files.
            benchmark_result (str | Path | None): Optional explicit Benchmark
                result document when the compound source stores it separately.
            artifact_root (str | Path | None): Trusted runtime artifact root.
            graph_snapshot (str | Path | None): Explicit JSON/YAML AgentGraph.
            provenance (str): Truthful evidence provenance label.

        Raises:
            ReplayImportError: Legacy evidence is invalid or inconsistent.
            ReplayConflictError: Run was already imported.
            OSError: Source or managed storage cannot be read.

        Returns:
            ReplayEvidenceEnvelope: Persisted immutable Replay.
        """
        candidate = LegacyBenchmarkReplayAdapter().load(
            Path(run_directory),
            benchmark_result=(
                Path(benchmark_result) if benchmark_result is not None else None
            ),
            artifact_root=(
                Path(artifact_root) if artifact_root is not None else None
            ),
            graph_snapshot=(
                Path(graph_snapshot) if graph_snapshot is not None else None
            ),
            provenance=provenance,
        )
        return self.artifact_store.import_candidate(candidate)

    def list_replays(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        agent_id: str | None = None,
    ) -> ReplayPage:
        """List persisted Replay summaries.

        Args:
            limit (int): Page size.
            cursor (str | None): Optional opaque cursor.
            agent_id (str | None): Optional exact Agent identity filter.

        Raises:
            ValueError: Pagination is invalid.

        Returns:
            ReplayPage: Stable bounded page.
        """
        return self.repository.list_replays(
            limit=limit,
            cursor=cursor,
            agent_id=agent_id,
        )

    def get_replay(self, run_id: str) -> ReplayEvidenceEnvelope:
        """Read one immutable Replay resource.

        Args:
            run_id (str): Stable run identity.

        Raises:
            ReplayNotFoundError: Run is absent.

        Returns:
            ReplayEvidenceEnvelope: Persisted evidence.
        """
        return self.repository.get_replay(run_id)

    def open_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> tuple[ReplayArtifactDescriptor, BinaryIO]:
        """Open one verified artifact using opaque identities.

        Args:
            run_id (str): Owning run identity.
            artifact_id (str): Replay-scoped artifact identity.

        Raises:
            ReplayArtifactNotFoundError: Pair is absent.
            ReplayImportError: Content is missing or corrupt.

        Returns:
            tuple[ReplayArtifactDescriptor, BinaryIO]: Metadata and stream.
        """
        return self.artifact_store.open_artifact(run_id, artifact_id)

    def export_bundle(self, run_id: str) -> Path:
        """Create or replace one managed default Replay export.

        Args:
            run_id (str): Persisted run identity.

        Raises:
            ReplayNotFoundError: Run is absent.
            ReplayImportError: Included content is corrupt.
            OSError: Export cannot be written.

        Returns:
            Path: Managed bundle path.
        """
        target = self.artifact_store.root / "exports" / f"{run_id}.zip"
        return self.bundle_store.write_bundle(run_id, target)


def build_default_replay_service(
    database_path: str | Path,
) -> ReplayApplicationService:
    """Build the default SQLite metadata and Local Artifact Store adapters.

    Args:
        database_path (str | Path): Workspace-isolated Studio database.

    Raises:
        OSError: Managed storage cannot be created.
        sqlite3.Error: Database migration fails.

    Returns:
        ReplayApplicationService: Configured offline Replay service.
    """
    repository = SQLiteReplayRepository(database_path)
    artifacts = ReplayArtifactStore(
        default_studio_artifact_directory(database_path),
        repository,
    )
    return ReplayApplicationService(
        repository=repository,
        artifact_store=artifacts,
        bundle_store=ReplayBundleStore(repository, artifacts),
    )


__all__ = ["ReplayApplicationService", "build_default_replay_service"]
