"""Application service for immutable Benchmark Package publication and export."""

from __future__ import annotations

import time
from typing import BinaryIO, Callable
import uuid

from pydantic import ValidationError

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringReleaseConflictError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_protocols import StudioBenchmarkAuthoringRepository
from .benchmark_authoring_release_models import (
    STUDIO_BENCHMARK_MANAGED_SOURCE_ID,
    StudioBenchmarkExportResultV1,
    StudioBenchmarkPackageExportV1,
    StudioBenchmarkPackagePublicationV1,
    StudioBenchmarkPackageRevisionPageV1,
    StudioBenchmarkPublicationResultV1,
    StudioBenchmarkReleaseCommandV1,
    StudioBenchmarkStoredExportV1,
    StudioBenchmarkStoredPublicationV1,
    benchmark_release_request_fingerprint,
)
from .benchmark_authoring_release_storage import (
    LocalStudioBenchmarkPackageReleaseStore,
    StudioBenchmarkFrozenClosureReader,
)
from .benchmark_service import (
    StudioBenchmarkCatalogService,
    StudioBenchmarkCatalogSnapshotOwner,
)


def _new_release_id(prefix: str) -> str:
    """Create one opaque UUID-derived release resource identity.

    Args:
        prefix: Stable resource prefix.

    Raises:
        None.

    Returns:
        Opaque resource identity.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


class StudioBenchmarkPackageReleaseApplicationService:
    """Publish and export only exact immutable validated Package revisions."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        frozen_reader: StudioBenchmarkFrozenClosureReader,
        storage: LocalStudioBenchmarkPackageReleaseStore,
        catalog: StudioBenchmarkCatalogSnapshotOwner,
        clock: Callable[[], int] | None = None,
        identity_factory: Callable[[str], str] | None = None,
    ) -> None:
        """Configure runtime-incapable release dependencies.

        Args:
            repository: Durable authoring/freeze/release metadata boundary.
            frozen_reader: Exact immutable content reader.
            storage: Private managed Package and archive store.
            catalog: Process-owned immutable Catalog snapshot pointer.
            clock: Optional deterministic millisecond clock.
            identity_factory: Optional deterministic opaque ID factory.

        Raises:
            None.

        Returns:
            None.
        """
        self._repository = repository
        self._reader = frozen_reader
        self._storage = storage
        self._catalog = catalog
        self._clock = clock or (lambda: time.time_ns() // 1_000_000)
        self._identity_factory = identity_factory or _new_release_id

    @staticmethod
    def parse_command(raw: object) -> StudioBenchmarkReleaseCommandV1:
        """Parse an untrusted publication or export JSON command.

        Args:
            raw: Untrusted JSON-compatible request body.

        Raises:
            StudioBenchmarkAuthoringValidationError: Body violates the strict
                schema-1 release command contract.

        Returns:
            Strict minimal idempotent release command.
        """
        try:
            return StudioBenchmarkReleaseCommandV1.model_validate(raw)
        except ValidationError as error:
            first = error.errors(include_url=False, include_input=False)[0]
            location = ".".join(str(item) for item in first["loc"]) or "request"
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.release_request_invalid",
                f"Invalid Benchmark release request at {location}: {first['msg']}",
            ) from error

    def list_package_revisions(
        self,
        draft_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkPackageRevisionPageV1:
        """List immutable release candidates without consulting mutable drafts.

        Args:
            draft_id: Owning draft identity.
            limit: Bounded page size.
            cursor: Optional draft-bound continuation cursor.

        Raises:
            StudioBenchmarkAuthoringStorageError: Durable rows are invalid.

        Returns:
            Stable Package-revision page.
        """
        return self._repository.list_package_revisions(
            draft_id, limit=limit, cursor=cursor
        )

    def recover_publications(self) -> int:
        """Verify and install every durable managed publication before serving.

        Raises:
            StudioBenchmarkAuthoringStorageError: Metadata or managed bytes fail
                closed reconstruction.

        Returns:
            Number of durable managed entries installed.
        """
        records = self._repository.list_publication_records()

        def recover(
            snapshot: StudioBenchmarkCatalogService,
        ) -> tuple[StudioBenchmarkCatalogService, int]:
            """Build a complete recovered snapshot under the writer lock.

            Args:
                snapshot: Captured initial Catalog including configured sources.

            Raises:
                StudioBenchmarkAuthoringStorageError: A durable relation,
                    managed tree, or reconstructed Catalog identity is invalid.

            Returns:
                Complete next Catalog snapshot and recovered entry count.
            """
            current = snapshot
            for record in records:
                publication = record.publication
                detail = self._repository.get_package_revision(
                    publication.draft_id,
                    publication.package_revision_id,
                )
                package = detail.package_revision
                if (
                    publication.validation_attestation_id
                    != package.validation_attestation_id
                    or publication.package_identity != package.package_identity
                    or publication.package_content_identity
                    != package.package_content_identity
                    or publication.closure_identity != package.closure_identity
                ):
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.publication_integrity",
                        "Durable Benchmark publication is inconsistent",
                    )
                package_root = self._storage.verify_package(
                    record.managed_locator, detail
                )
                try:
                    current, catalog_entry_id = current.with_managed_package(
                        source_id=STUDIO_BENCHMARK_MANAGED_SOURCE_ID,
                        publication_id=publication.publication_id,
                        package_root=package_root,
                        package_identity=publication.package_identity,
                        package_content_identity=(
                            publication.package_content_identity
                        ),
                        closure_identity=publication.closure_identity,
                    )
                except Exception as error:
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.publication_integrity",
                        "Managed Benchmark publication cannot be reconstructed",
                    ) from error
                if catalog_entry_id != publication.catalog_entry_id:
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.publication_integrity",
                        "Managed Benchmark Catalog identity is inconsistent",
                    )
            return current, len(records)

        return self._catalog.serialized_update(recover)

    @staticmethod
    def _assert_no_catalog_conflict(
        snapshot: StudioBenchmarkCatalogService,
        *,
        package_identity: str,
        package_content_identity: str,
        closure_identity: str,
    ) -> None:
        """Reject divergent current sources while allowing explicit equivalents.

        Args:
            snapshot: Captured complete current Catalog.
            package_identity: Readable frozen Package version.
            package_content_identity: Frozen canonical Package content identity.
            closure_identity: Frozen complete member closure identity.

        Raises:
            StudioBenchmarkAuthoringReleaseConflictError: A current concrete
                source has different canonical content or managed closure.

        Returns:
            None.
        """
        for fact in snapshot.semantic_facts(package_identity):
            if fact.package_content_identity != package_content_identity or (
                fact.managed and fact.closure_identity != closure_identity
            ):
                raise StudioBenchmarkAuthoringReleaseConflictError(
                    "benchmark.authoring.publication_version_conflict",
                    "Benchmark Package version has different Catalog content",
                )

    def publish(
        self,
        draft_id: str,
        package_revision_id: str,
        request: StudioBenchmarkReleaseCommandV1,
    ) -> StudioBenchmarkPublicationResultV1:
        """Publish one exact immutable frozen Package into managed Catalog.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Exact immutable release candidate.
            request: Strict idempotent publication command.

        Raises:
            StudioBenchmarkAuthoringReleaseConflictError: Readable version has
                divergent current content.
            StudioBenchmarkAuthoringStorageError: Frozen bytes, storage,
                compilation, or durable commit fails closed.

        Returns:
            Durable publication after Catalog visibility is established.
        """
        fingerprint = benchmark_release_request_fingerprint(
            operation="publish",
            draft_id=draft_id,
            package_revision_id=package_revision_id,
            request=request,
        )
        retry = self._repository.find_publication_result(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
        )
        if retry is not None:
            return StudioBenchmarkPublicationResultV1(
                created=False, publication=retry
            )
        detail = self._repository.get_package_revision(
            draft_id, package_revision_id
        )
        self._reader.verify(detail)
        package = detail.package_revision

        def publish_locked(
            snapshot: StudioBenchmarkCatalogService,
        ) -> tuple[
            StudioBenchmarkCatalogService,
            StudioBenchmarkPublicationResultV1,
        ]:
            """Serialize semantic checks, commit, and snapshot replacement.

            Args:
                snapshot: One immutable Catalog captured by the writer lock.

            Raises:
                StudioBenchmarkAuthoringReleaseConflictError: A readable
                    Package version already has divergent content.
                StudioBenchmarkAuthoringStorageError: Managed materialization,
                    Catalog compilation, or durable commit fails closed.

            Returns:
                Complete next snapshot and durable publication result.
            """
            locked_retry = self._repository.find_publication_result(
                draft_id,
                client_request_id=request.client_request_id,
                request_fingerprint=fingerprint,
            )
            if locked_retry is not None:
                return snapshot, StudioBenchmarkPublicationResultV1(
                    created=False, publication=locked_retry
                )
            self._assert_no_catalog_conflict(
                snapshot,
                package_identity=package.package_identity,
                package_content_identity=package.package_content_identity,
                closure_identity=package.closure_identity,
            )
            existing = self._repository.find_semantic_publication(
                package.package_identity
            )
            if existing is not None:
                publication, _created = self._repository.commit_publication(
                    draft_id,
                    requested_package_revision_id=package_revision_id,
                    client_request_id=request.client_request_id,
                    request_fingerprint=fingerprint,
                    record=existing,
                )
                return snapshot, StudioBenchmarkPublicationResultV1(
                    created=False,
                    publication=publication,
                )
            publication_id = self._identity_factory(
                "benchmark-package-publication"
            )
            package_root = self._storage.materialize_package(
                publication_id, detail, self._reader
            )
            try:
                next_snapshot, catalog_entry_id = snapshot.with_managed_package(
                    source_id=STUDIO_BENCHMARK_MANAGED_SOURCE_ID,
                    publication_id=publication_id,
                    package_root=package_root,
                    package_identity=package.package_identity,
                    package_content_identity=package.package_content_identity,
                    closure_identity=package.closure_identity,
                )
            except Exception as error:
                raise StudioBenchmarkAuthoringStorageError(
                    "benchmark.authoring.publication_compile_failed",
                    "Managed Benchmark Package could not enter Catalog",
                ) from error
            publication = StudioBenchmarkPackagePublicationV1(
                publicationId=publication_id,
                draftId=draft_id,
                packageRevisionId=package_revision_id,
                validationAttestationId=package.validation_attestation_id,
                packageIdentity=package.package_identity,
                packageContentIdentity=package.package_content_identity,
                closureIdentity=package.closure_identity,
                catalogEntryId=catalog_entry_id,
                createdAt=self._clock(),
            )
            committed, created = self._repository.commit_publication(
                draft_id,
                requested_package_revision_id=package_revision_id,
                client_request_id=request.client_request_id,
                request_fingerprint=fingerprint,
                record=StudioBenchmarkStoredPublicationV1(
                    publication=publication,
                    managedLocator=publication_id,
                ),
            )
            if not created and committed.publication_id != publication_id:
                # A durable equivalent can win only outside this process. Build
                # from its verified tree before making that authority visible.
                durable = self._repository.find_semantic_publication(
                    package.package_identity
                )
                if durable is None:
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.publication_integrity",
                        "Committed Benchmark publication could not be reconstructed",
                    )
                durable_detail = self._repository.get_package_revision(
                    committed.draft_id, committed.package_revision_id
                )
                durable_root = self._storage.verify_package(
                    durable.managed_locator, durable_detail
                )
                next_snapshot, entry_id = snapshot.with_managed_package(
                    source_id=STUDIO_BENCHMARK_MANAGED_SOURCE_ID,
                    publication_id=committed.publication_id,
                    package_root=durable_root,
                    package_identity=committed.package_identity,
                    package_content_identity=committed.package_content_identity,
                    closure_identity=committed.closure_identity,
                )
                if entry_id != committed.catalog_entry_id:
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.publication_integrity",
                        "Committed Benchmark Catalog identity is inconsistent",
                    )
            return next_snapshot, StudioBenchmarkPublicationResultV1(
                created=created,
                publication=committed,
            )

        return self._catalog.serialized_update(publish_locked)

    def export_package(
        self,
        draft_id: str,
        package_revision_id: str,
        request: StudioBenchmarkReleaseCommandV1,
    ) -> StudioBenchmarkExportResultV1:
        """Generate one deterministic archive for an exact frozen Package.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Exact immutable release candidate.
            request: Strict idempotent export command.

        Raises:
            StudioBenchmarkAuthoringStorageError: Frozen bytes, archive, or
                durable commit fails closed.

        Returns:
            Durable export descriptor independent of publication.
        """
        fingerprint = benchmark_release_request_fingerprint(
            operation="export",
            draft_id=draft_id,
            package_revision_id=package_revision_id,
            request=request,
        )
        retry = self._repository.find_export_result(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
        )
        if retry is not None:
            return StudioBenchmarkExportResultV1(
                created=False, packageExport=retry
            )
        detail = self._repository.get_package_revision(
            draft_id, package_revision_id
        )
        self._reader.verify(detail)
        package = detail.package_revision
        existing = self._repository.find_package_export(
            draft_id, package_revision_id
        )
        if existing is not None:
            committed, _created = self._repository.commit_export(
                draft_id,
                requested_package_revision_id=package_revision_id,
                client_request_id=request.client_request_id,
                request_fingerprint=fingerprint,
                record=existing,
            )
            return StudioBenchmarkExportResultV1(
                created=False,
                packageExport=committed,
            )
        export_id = self._identity_factory("benchmark-package-export")
        size, digest = self._storage.create_export(
            export_id, detail, self._reader
        )
        content_link = (
            "/api/studio/benchmark-authoring/drafts/"
            f"{draft_id}/package-revisions/{package_revision_id}/"
            f"exports/{export_id}/content"
        )
        package_export = StudioBenchmarkPackageExportV1(
            exportId=export_id,
            draftId=draft_id,
            packageRevisionId=package_revision_id,
            validationAttestationId=package.validation_attestation_id,
            packageIdentity=package.package_identity,
            packageContentIdentity=package.package_content_identity,
            closureIdentity=package.closure_identity,
            memberCount=len(package.members),
            filename=self._storage.export_filename(package_revision_id),
            size=size,
            sha256=digest,
            contentLink=content_link,
            createdAt=self._clock(),
        )
        committed, created = self._repository.commit_export(
            draft_id,
            requested_package_revision_id=package_revision_id,
            client_request_id=request.client_request_id,
            request_fingerprint=fingerprint,
            record=StudioBenchmarkStoredExportV1(
                packageExport=package_export,
                archiveLocator=export_id,
            ),
        )
        return StudioBenchmarkExportResultV1(
            created=created,
            packageExport=committed,
        )

    def get_publication(
        self,
        draft_id: str,
        package_revision_id: str,
        publication_id: str,
    ) -> StudioBenchmarkPackagePublicationV1:
        """Read one exact durable publication through full ownership.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Owning immutable Package revision.
            publication_id: Exact publication identity.

        Raises:
            StudioBenchmarkAuthoringStorageError: Durable metadata is invalid.

        Returns:
            Strict immutable publication.
        """
        return self._repository.get_publication(
            draft_id, package_revision_id, publication_id
        )

    def get_export(
        self,
        draft_id: str,
        package_revision_id: str,
        export_id: str,
    ) -> StudioBenchmarkPackageExportV1:
        """Read one exact durable export descriptor through full ownership.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Owning immutable Package revision.
            export_id: Exact export identity.

        Raises:
            StudioBenchmarkAuthoringStorageError: Durable metadata is invalid.

        Returns:
            Strict immutable export descriptor.
        """
        return self._repository.get_export(
            draft_id, package_revision_id, export_id
        )

    def open_export(
        self,
        draft_id: str,
        package_revision_id: str,
        export_id: str,
    ) -> tuple[StudioBenchmarkPackageExportV1, BinaryIO]:
        """Resolve and verify one exact archive for HTTP GET or HEAD.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Owning immutable Package revision.
            export_id: Exact export identity.

        Raises:
            StudioBenchmarkAuthoringStorageError: Metadata or bytes fail closed.

        Returns:
            Public descriptor and verified readable binary stream.
        """
        record = self._repository.get_export_record(
            draft_id, package_revision_id, export_id
        )
        detail = self._repository.get_package_revision(
            draft_id, package_revision_id
        )
        return record.package_export, self._storage.open_export(
            record.package_export, detail
        )


__all__ = ["StudioBenchmarkPackageReleaseApplicationService"]
