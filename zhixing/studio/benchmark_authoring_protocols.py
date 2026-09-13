"""Database-neutral ports for Studio Benchmark authoring."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO, Protocol

from .benchmark_authoring_models import (
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkAuthoringRevisionV1,
    StudioBenchmarkDraftPageV1,
    StudioBenchmarkDraftRecordV1,
)
from .benchmark_authoring_freeze_models import (
    StudioBenchmarkPackageRevisionDetailV1,
    StudioBenchmarkPackageRevisionV1,
    StudioBenchmarkValidationAttestationV1,
)
from .benchmark_authoring_release_models import (
    StudioBenchmarkPackageExportV1,
    StudioBenchmarkPackagePublicationV1,
    StudioBenchmarkPackageRevisionPageV1,
    StudioBenchmarkStoredExportV1,
    StudioBenchmarkStoredPublicationV1,
)


class StudioBenchmarkManagedContent(Protocol):
    """Immutable local authoring byte storage hidden behind opaque identity."""

    def store_stream(
        self,
        stream: BinaryIO,
        *,
        max_bytes: int,
    ) -> tuple[str, str, int]:
        """Store bounded bytes and return content identity, digest, and size."""

    def store_bytes(
        self,
        payload: bytes,
        *,
        max_bytes: int,
    ) -> tuple[str, str, int]:
        """Store bounded immutable bytes for a canonical definition member."""

    def store_file(
        self,
        source: Path,
        *,
        max_bytes: int,
    ) -> tuple[str, str, int]:
        """Store one bounded regular non-symlink source file."""

    def content_path(self, content_identity: str) -> Path:
        """Resolve an existing immutable content identity for internal use."""

    def open_verified(
        self,
        content_identity: str,
        *,
        expected_sha256: str,
        expected_size: int,
    ) -> BinaryIO:
        """Open bytes only after identity, regular-file, size, and digest checks."""


class StudioBenchmarkAuthoringRepository(Protocol):
    """Persistence contract for drafts, revisions, and command idempotency."""

    def find_create_result(
        self,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> tuple[StudioBenchmarkDraftRecordV1, StudioBenchmarkAuthoringRevisionV1] | None:
        """Return a matching committed create result or raise on ID conflict."""

    def create_draft(
        self,
        *,
        client_request_id: str,
        request_fingerprint: str,
        name: str,
        document: StudioBenchmarkAuthoringDocumentV1,
        provenance: StudioBenchmarkAuthoringProvenanceV1,
    ) -> tuple[
        StudioBenchmarkDraftRecordV1,
        StudioBenchmarkAuthoringRevisionV1,
        bool,
    ]:
        """Create an initial draft/revision atomically or return an idempotent result."""

    def list_drafts(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkDraftPageV1:
        """Return one bounded deterministic draft page."""

    def get_draft(self, draft_id: str) -> StudioBenchmarkDraftRecordV1:
        """Return one draft record."""

    def get_revision(
        self,
        draft_id: str,
        revision_id: str,
    ) -> StudioBenchmarkAuthoringRevisionV1:
        """Return one exact revision owned by a draft."""

    def has_save_command(
        self,
        draft_id: str,
        *,
        client_request_id: str,
    ) -> bool:
        """Return whether a draft-local save command identity is durable."""

    def save_revision(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
        base_revision_id: str,
        document: StudioBenchmarkAuthoringDocumentV1,
        provenance: StudioBenchmarkAuthoringProvenanceV1,
    ) -> tuple[
        StudioBenchmarkDraftRecordV1,
        StudioBenchmarkAuthoringRevisionV1,
        bool,
    ]:
        """Append one optimistic immutable revision or return a prior retry."""

    def find_freeze_result(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1 | None:
        """Return a matching durable freeze result or raise on ID conflict."""

    def commit_freeze(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
        expected_revision_id: str,
        attestation: StudioBenchmarkValidationAttestationV1,
        package_revision: StudioBenchmarkPackageRevisionV1,
    ) -> tuple[StudioBenchmarkPackageRevisionDetailV1, bool]:
        """Atomically commit one successful exact-current freeze."""

    def get_package_revision(
        self,
        draft_id: str,
        package_revision_id: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1:
        """Read one exact immutable Package revision through its draft."""

    def list_package_revisions(
        self,
        draft_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkPackageRevisionPageV1:
        """Return one stable draft-scoped frozen revision page."""

    def find_publication_result(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackagePublicationV1 | None:
        """Return a matching publication command result or conflict."""

    def find_export_result(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackageExportV1 | None:
        """Return a matching Package export command result or conflict."""

    def find_semantic_publication(
        self,
        package_identity: str,
    ) -> StudioBenchmarkStoredPublicationV1 | None:
        """Return the managed authority for one readable Package version."""

    def find_package_export(
        self,
        draft_id: str,
        package_revision_id: str,
    ) -> StudioBenchmarkStoredExportV1 | None:
        """Return the deterministic export for one exact owned Package."""

    def list_publication_records(
        self,
    ) -> tuple[StudioBenchmarkStoredPublicationV1, ...]:
        """Return all durable managed publications for restart."""

    def commit_publication(
        self,
        draft_id: str,
        *,
        requested_package_revision_id: str,
        client_request_id: str,
        request_fingerprint: str,
        record: StudioBenchmarkStoredPublicationV1,
    ) -> tuple[StudioBenchmarkPackagePublicationV1, bool]:
        """Atomically commit publication metadata and command result."""

    def commit_export(
        self,
        draft_id: str,
        *,
        requested_package_revision_id: str,
        client_request_id: str,
        request_fingerprint: str,
        record: StudioBenchmarkStoredExportV1,
    ) -> tuple[StudioBenchmarkPackageExportV1, bool]:
        """Atomically commit export metadata and command result."""

    def get_publication(
        self,
        draft_id: str,
        package_revision_id: str,
        publication_id: str,
    ) -> StudioBenchmarkPackagePublicationV1:
        """Read one exact scoped publication."""

    def get_export_record(
        self,
        draft_id: str,
        package_revision_id: str,
        export_id: str,
    ) -> StudioBenchmarkStoredExportV1:
        """Read one exact scoped export with its opaque private locator."""

    def get_export(
        self,
        draft_id: str,
        package_revision_id: str,
        export_id: str,
    ) -> StudioBenchmarkPackageExportV1:
        """Read one exact scoped public export descriptor."""


__all__ = [
    "StudioBenchmarkAuthoringRepository",
    "StudioBenchmarkManagedContent",
]
