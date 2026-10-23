"""Definition-only application service for Studio Benchmark authoring."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_import import (
    StudioBenchmarkAuthoringPackageAdapter,
)
from .benchmark_authoring_models import (
    StudioBenchmarkCatalogDraftSourceV1,
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkAuthoringRevisionV1,
    StudioBenchmarkDraftCreateRequestV1,
    StudioBenchmarkDraftCreateResponseV1,
    StudioBenchmarkDraftDetailV1,
    StudioBenchmarkDraftPageV1,
    StudioBenchmarkRevisionSaveRequestV1,
    StudioBenchmarkRevisionSaveResponseV1,
    StudioBenchmarkTemplateDraftSourceV1,
    validate_benchmark_authoring_revision_id,
    validate_benchmark_draft_id,
)
from .benchmark_authoring_protocols import (
    StudioBenchmarkAuthoringRepository,
)
from .benchmark_service import StudioBenchmarkCatalogService


def _validation_error(message: str, error: Exception) -> Exception:
    """Build one safe validation failure without echoing submitted values.

    Args:
        message: Stable bounded public explanation.
        error: Internal parse failure retained only as exception cause.

    Raises:
        None.

    Returns:
        Safe typed validation error with the original cause attached.
    """
    failure = StudioBenchmarkAuthoringValidationError(
        "benchmark.authoring.request_invalid",
        message,
    )
    failure.__cause__ = error
    return failure


class StudioBenchmarkAuthoringApplicationService:
    """Coordinate strict requests, managed sources, and durable revisions."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        packages: StudioBenchmarkAuthoringPackageAdapter,
        catalog: StudioBenchmarkCatalogService,
    ) -> None:
        """Bind definition-only authoring ports.

        Args:
            repository: Durable draft/revision persistence.
            packages: Private scaffold and Catalog copy adapter.
            catalog: Process-frozen opaque Benchmark Catalog.

        Raises:
            None.

        Returns:
            None.
        """
        self._repository = repository
        self._packages = packages
        self._catalog = catalog

    @staticmethod
    def parse_create_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkDraftCreateRequestV1:
        """Parse a strict create union before any mutable source access.

        Args:
            payload: Untrusted decoded JSON object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is malformed.

        Returns:
            Strict create request with canonical fingerprint support.
        """
        try:
            return StudioBenchmarkDraftCreateRequestV1.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as error:
            raise _validation_error(
                "Benchmark authoring create request is invalid",
                error,
            )

    @staticmethod
    def parse_save_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkRevisionSaveRequestV1:
        """Parse a strict optimistic save before repository access.

        Args:
            payload: Untrusted decoded JSON object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is malformed.

        Returns:
            Strict save request with canonical fingerprint support.
        """
        try:
            return StudioBenchmarkRevisionSaveRequestV1.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as error:
            raise _validation_error(
                "Benchmark authoring revision request is invalid",
                error,
            )

    def create_draft(
        self,
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkDraftCreateResponseV1:
        """Create an initial immutable revision from a template or Catalog copy.

        Args:
            payload: Untrusted decoded JSON create request.

        Raises:
            StudioBenchmarkAuthoringValidationError: Request/source is unsafe.
            StudioBenchmarkError: Catalog, storage, or idempotency fails.

        Returns:
            Created or durably replayed draft/revision response.
        """
        request = self.parse_create_request(payload)
        existing = self._repository.find_create_result(
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
        )
        if existing is not None:
            return StudioBenchmarkDraftCreateResponseV1(
                created=False,
                draft=existing[0],
                revision=existing[1],
            )
        if isinstance(request.source, StudioBenchmarkTemplateDraftSourceV1):
            prepared = self._packages.from_template(request.source)
            provenance = StudioBenchmarkAuthoringProvenanceV1(
                source_kind="template",
                template_name=request.source.template,
                package_identity=prepared.package_identity,
                source_fingerprint=prepared.source_fingerprint,
            )
        elif isinstance(request.source, StudioBenchmarkCatalogDraftSourceV1):
            source = self._catalog.resolve_authoring_source(
                request.source.catalog_entry_id
            )
            prepared = self._packages.from_catalog(source)
            provenance = StudioBenchmarkAuthoringProvenanceV1(
                source_kind="catalog",
                catalog_entry_id=source.catalog_entry_id,
                catalog_snapshot_identity=source.catalog_snapshot_identity,
                package_identity=prepared.package_identity,
                source_fingerprint=prepared.source_fingerprint,
            )
        else:  # pragma: no cover - discriminated Pydantic union is exhaustive.
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.request_invalid",
                "Benchmark authoring source is unsupported",
            )
        draft, revision, created = self._repository.create_draft(
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
            name=request.name,
            document=prepared.document,
            provenance=provenance,
        )
        return StudioBenchmarkDraftCreateResponseV1(
            created=created,
            draft=draft,
            revision=revision,
        )

    def list_drafts(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkDraftPageV1:
        """List bounded newest-first draft metadata.

        Args:
            limit: Requested page size.
            cursor: Optional opaque continuation cursor.

        Raises:
            StudioBenchmarkAuthoringValidationError: Page input is invalid.
            StudioBenchmarkError: Durable reads fail.

        Returns:
            One deterministic page.
        """
        return self._repository.list_drafts(limit=limit, cursor=cursor)

    def get_draft(self, draft_id: str) -> StudioBenchmarkDraftDetailV1:
        """Read one draft with its current immutable revision.

        Args:
            draft_id: Opaque draft identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: Identity is malformed.
            StudioBenchmarkError: Draft or current revision cannot be read.

        Returns:
            Draft/current-revision detail.
        """
        try:
            validate_benchmark_draft_id(draft_id)
        except ValueError as error:
            raise _validation_error(
                "Benchmark authoring draft identity is invalid",
                error,
            )
        draft = self._repository.get_draft(draft_id)
        revision = self._repository.get_revision(
            draft_id,
            draft.current_revision_id,
        )
        return StudioBenchmarkDraftDetailV1(
            draft=draft,
            current_revision=revision,
        )

    def get_revision(
        self,
        draft_id: str,
        revision_id: str,
    ) -> StudioBenchmarkAuthoringRevisionV1:
        """Read one exact immutable revision through its owning draft.

        Args:
            draft_id: Opaque owning draft identity.
            revision_id: Opaque exact revision identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: An identity is malformed.
            StudioBenchmarkError: Owned revision cannot be read.

        Returns:
            Exact immutable authoring revision.
        """
        try:
            validate_benchmark_draft_id(draft_id)
            validate_benchmark_authoring_revision_id(revision_id)
        except ValueError as error:
            raise _validation_error(
                "Benchmark authoring resource identity is invalid",
                error,
            )
        return self._repository.get_revision(draft_id, revision_id)

    def save_revision(
        self,
        draft_id: str,
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkRevisionSaveResponseV1:
        """Append an idempotent optimistic immutable authoring revision.

        Args:
            draft_id: Opaque owning draft identity.
            payload: Untrusted decoded JSON save request.

        Raises:
            StudioBenchmarkAuthoringValidationError: Request is malformed.
            StudioBenchmarkError: Draft, conflict, idempotency, or storage fails.

        Returns:
            Created or durably replayed revision response.
        """
        try:
            validate_benchmark_draft_id(draft_id)
        except ValueError as error:
            raise _validation_error(
                "Benchmark authoring draft identity is invalid",
                error,
            )
        request = self.parse_save_request(payload)
        draft, revision, created = self._repository.save_revision(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
            base_revision_id=request.base_revision_id,
            document=request.document,
            provenance=StudioBenchmarkAuthoringProvenanceV1(
                source_kind="edit"
            ),
        )
        return StudioBenchmarkRevisionSaveResponseV1(
            created=created,
            draft=draft,
            revision=revision,
        )


__all__ = ["StudioBenchmarkAuthoringApplicationService"]
