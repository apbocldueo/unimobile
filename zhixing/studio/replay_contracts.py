"""Database-neutral contracts for Studio Replay import and persistence."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping, Protocol

from .replay_models import (
    ReplayArtifactDescriptor,
    ReplayEvidenceEnvelope,
    ReplayListItem,
    ReplayPage,
)


class ReplayRepositoryError(RuntimeError):
    """Base error for safe Replay repository failures."""


class ReplayNotFoundError(ReplayRepositoryError, LookupError):
    """Requested Replay identity does not exist."""


class ReplayArtifactNotFoundError(ReplayRepositoryError, LookupError):
    """Requested replay-scoped artifact does not exist."""


class ReplayConflictError(ReplayRepositoryError):
    """A Replay with the same immutable run identity already exists."""


class ReplayImportError(ValueError):
    """Explicit local import source is invalid, unsafe, or inconsistent."""

    def __init__(self, code: str, message: str) -> None:
        """Create one stable safe import failure.

        Args:
            code (str): Stable machine-readable import code.
            message (str): Safe explanation without source paths.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__(str(message).replace("\n", " ")[:500])
        self.code = code


@dataclass(frozen=True)
class ReplayArtifactRecord:
    """Internal descriptor paired with an opaque store-relative reference."""

    descriptor: ReplayArtifactDescriptor
    storage_ref: str


@dataclass(frozen=True)
class ReplayImportArtifact:
    """One verified import input from a file or ZIP member."""

    descriptor: ReplayArtifactDescriptor
    source_path: Path
    bundle_member: str | None = None
    trusted_root: Path | None = None


@dataclass(frozen=True)
class ReplayImportCandidate:
    """Parsed envelope and artifact inputs awaiting atomic persistence."""

    envelope: ReplayEvidenceEnvelope
    artifacts: Mapping[str, ReplayImportArtifact]


class ReplayRepository(Protocol):
    """Structured persistence contract independent of the SQLite adapter."""

    def create_replay(
        self,
        envelope: ReplayEvidenceEnvelope,
        artifacts: tuple[ReplayArtifactRecord, ...],
    ) -> ReplayEvidenceEnvelope:
        """Persist one immutable Replay and its artifact index atomically."""

    def list_replays(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        agent_id: str | None = None,
    ) -> ReplayPage:
        """List Replay summaries in stable newest-first order.

        Args:
            limit: Bounded page size.
            cursor: Optional opaque pagination cursor.
            agent_id: Optional exact safe Agent identity filter.

        Raises:
            ValueError: Pagination or Agent identity is invalid.

        Returns:
            ReplayPage: Stable bounded Replay page.
        """

    def get_replay(self, run_id: str) -> ReplayEvidenceEnvelope:
        """Load one immutable Replay envelope."""

    def get_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> ReplayArtifactRecord:
        """Resolve one artifact only within its owning Replay."""


class ReplaySourceAdapter(Protocol):
    """Parse one explicit trusted source into an import candidate."""

    def load(self, source: Path, **options: object) -> ReplayImportCandidate:
        """Parse and verify an explicit local source without persistence."""


class ReplayArtifactResolver(Protocol):
    """Resolve opaque artifact records without exposing host paths."""

    def open_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> tuple[ReplayArtifactDescriptor, BinaryIO]:
        """Open one verified regular artifact for bounded streaming."""


class ReplayBundleWriter(Protocol):
    """Export a Replay using versioned relative members and hashes."""

    def write_bundle(self, run_id: str, target: Path) -> Path:
        """Write and verify one Replay bundle at an explicit local target."""


class ReplayBundleReader(Protocol):
    """Verify and parse one native Replay package."""

    def load(self, source: Path, **options: object) -> ReplayImportCandidate:
        """Load one versioned Replay package without trusting member paths."""


def replay_list_item(envelope: ReplayEvidenceEnvelope) -> ReplayListItem:
    """Derive one compact History item from an immutable envelope.

    Args:
        envelope (ReplayEvidenceEnvelope): Persisted Replay facts.

    Raises:
        None.

    Returns:
        ReplayListItem: Compact safe summary.
    """
    available = sum(
        1 for item in envelope.availability.values() if item.state == "available"
    )
    total = len(envelope.availability)
    completeness = 100 if total == 0 else round(available * 100 / total)
    return ReplayListItem(
        run_id=envelope.run_id,
        agent_id=envelope.snapshot.agent_id,
        agent_status=envelope.result.status,
        benchmark_outcome=(
            envelope.benchmark.outcome if envelope.benchmark is not None else None
        ),
        provenance=envelope.provenance,
        evidence_origin=envelope.evidence_origin,
        integrity_state=envelope.integrity_state,
        evidence_completeness=completeness,
        imported_at=envelope.imported_at,
    )


__all__ = [
    "ReplayArtifactNotFoundError",
    "ReplayArtifactRecord",
    "ReplayArtifactResolver",
    "ReplayBundleReader",
    "ReplayBundleWriter",
    "ReplayConflictError",
    "ReplayImportArtifact",
    "ReplayImportCandidate",
    "ReplayImportError",
    "ReplayNotFoundError",
    "ReplayRepository",
    "ReplayRepositoryError",
    "ReplaySourceAdapter",
    "replay_list_item",
]
