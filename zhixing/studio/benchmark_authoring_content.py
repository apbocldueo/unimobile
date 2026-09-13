"""Draft-owned managed-content commands for Studio Benchmark authoring."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, BinaryIO, Literal, Mapping

from pydantic import ValidationError

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    StudioBenchmarkAuthoringContentCommandResultV1,
    StudioBenchmarkAuthoringContentRemoveRequestV1,
    StudioBenchmarkAuthoringContentReplaceRequestV1,
    StudioBenchmarkAuthoringContentUploadRequestV1,
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringManifestV1,
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkAuthoringResourceV1,
    StudioBenchmarkAuthoringRevisionV1,
    validate_benchmark_authoring_resource_id,
    validate_benchmark_authoring_resource_path,
    validate_benchmark_authoring_revision_id,
    validate_benchmark_draft_id,
)
from .benchmark_authoring_protocols import (
    StudioBenchmarkAuthoringRepository,
    StudioBenchmarkManagedContent,
)


_MANIFEST_RESOURCE_FIELDS = (
    "id",
    "kind",
    "path",
    "media_type",
    "sha256",
    "size",
)
_FORBIDDEN_MANIFEST_RESOURCE_FIELDS = frozenset(
    {
        "contentIdentity",
        "content_identity",
        "destination",
        "hostPath",
        "host_path",
        "sourcePath",
        "source_path",
    }
)


def _request_invalid(message: str, error: Exception | None = None) -> Exception:
    """Build one bounded authoring-content validation failure.

    Args:
        message: Safe public explanation.
        error: Optional internal parse failure retained only as cause.

    Raises:
        None.

    Returns:
        Typed safe validation failure.
    """
    failure = StudioBenchmarkAuthoringValidationError(
        "benchmark.authoring.content_request_invalid",
        message,
    )
    if error is not None:
        failure.__cause__ = error
    return failure


def _single_query_values(
    query: Mapping[str, list[str]],
    *,
    expected: frozenset[str],
) -> dict[str, str]:
    """Require one exact single-valued query envelope.

    Args:
        query: Untrusted query values from the HTTP parser.
        expected: Exact allowed and required field names.

    Raises:
        StudioBenchmarkAuthoringValidationError: Keys or cardinality differ.

    Returns:
        Flattened single-valued query mapping.
    """
    if frozenset(query) != expected:
        raise _request_invalid(
            "Benchmark authoring content query fields are invalid"
        )
    flattened: dict[str, str] = {}
    for key in expected:
        values = query.get(key)
        if values is None or len(values) != 1 or not values[0]:
            raise _request_invalid(
                "Benchmark authoring content query values are invalid"
            )
        flattened[key] = values[0]
    if flattened["schemaVersion"] != "1":
        raise _request_invalid(
            "Benchmark authoring content requires schemaVersion 1"
        )
    return flattened


def parse_authoring_content_upload_query(
    *,
    resource_id: str,
    media_type: str,
    query: Mapping[str, list[str]],
) -> StudioBenchmarkAuthoringContentUploadRequestV1:
    """Parse strict upload metadata before draft or storage access.

    Args:
        resource_id: Logical resource identity from the owned route.
        media_type: Declared request Content-Type.
        query: Untrusted parsed query envelope.

    Raises:
        StudioBenchmarkAuthoringValidationError: Metadata is malformed.

    Returns:
        Strict upload request DTO.
    """
    values = _single_query_values(
        query,
        expected=frozenset(
            {
                "schemaVersion",
                "clientRequestId",
                "baseRevisionId",
                "kind",
                "path",
            }
        ),
    )
    try:
        return StudioBenchmarkAuthoringContentUploadRequestV1(
            schema_version=1,
            client_request_id=values["clientRequestId"],
            base_revision_id=values["baseRevisionId"],
            resource_id=resource_id,
            kind=values["kind"],
            path=values["path"],
            media_type=media_type,
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise _request_invalid(
            "Benchmark authoring upload metadata is invalid",
            error,
        )


def parse_authoring_content_replace_query(
    *,
    resource_id: str,
    media_type: str,
    query: Mapping[str, list[str]],
) -> StudioBenchmarkAuthoringContentReplaceRequestV1:
    """Parse strict replacement metadata before draft or storage access.

    Args:
        resource_id: Logical resource identity from the owned route.
        media_type: Declared request Content-Type.
        query: Untrusted parsed query envelope.

    Raises:
        StudioBenchmarkAuthoringValidationError: Metadata is malformed.

    Returns:
        Strict replacement request DTO.
    """
    values = _single_query_values(
        query,
        expected=frozenset(
            {
                "schemaVersion",
                "clientRequestId",
                "baseRevisionId",
            }
        ),
    )
    try:
        return StudioBenchmarkAuthoringContentReplaceRequestV1(
            schema_version=1,
            client_request_id=values["clientRequestId"],
            base_revision_id=values["baseRevisionId"],
            resource_id=resource_id,
            media_type=media_type,
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise _request_invalid(
            "Benchmark authoring replacement metadata is invalid",
            error,
        )


def parse_authoring_content_remove_query(
    *,
    resource_id: str,
    query: Mapping[str, list[str]],
) -> StudioBenchmarkAuthoringContentRemoveRequestV1:
    """Parse strict logical-removal metadata before draft access.

    Args:
        resource_id: Logical resource identity from the owned route.
        query: Untrusted parsed query envelope.

    Raises:
        StudioBenchmarkAuthoringValidationError: Metadata is malformed.

    Returns:
        Strict logical-removal request DTO.
    """
    values = _single_query_values(
        query,
        expected=frozenset(
            {
                "schemaVersion",
                "clientRequestId",
                "baseRevisionId",
            }
        ),
    )
    try:
        return StudioBenchmarkAuthoringContentRemoveRequestV1(
            schema_version=1,
            client_request_id=values["clientRequestId"],
            base_revision_id=values["baseRevisionId"],
            resource_id=resource_id,
        )
    except (ValidationError, TypeError, ValueError) as error:
        raise _request_invalid(
            "Benchmark authoring removal metadata is invalid",
            error,
        )


def _manifest_known_fields(
    resource: StudioBenchmarkAuthoringResourceV1,
) -> dict[str, Any]:
    """Project authoritative resource facts into manifest field names.

    Args:
        resource: Strict server-owned resource metadata.

    Raises:
        None.

    Returns:
        Known manifest resource fields without private content identity.
    """
    return {
        "id": resource.id,
        "kind": resource.kind,
        "path": resource.path,
        "media_type": resource.media_type,
        "sha256": resource.sha256,
        "size": resource.size,
    }


class _AuthoringResourceProjection:
    """Validated one-to-one view of strict and manifest resource inventories."""

    def __init__(self, document: StudioBenchmarkAuthoringDocumentV1) -> None:
        """Validate and copy one immutable base document inventory.

        Args:
            document: Exact immutable base revision document.

        Raises:
            StudioBenchmarkAuthoringValidationError: Inventories are ambiguous
                or contradictory.

        Returns:
            None.
        """
        self._document = document
        self._manifest_document = deepcopy(document.manifest.document)
        raw_resources = self._manifest_document.get("resources", [])
        if not isinstance(raw_resources, list):
            raise _request_invalid(
                "Benchmark authoring manifest resources are incoherent"
            )
        manifest_by_id: dict[str, dict[str, Any]] = {}
        manifest_paths: set[str] = set()
        for raw in raw_resources:
            if not isinstance(raw, Mapping):
                raise _request_invalid(
                    "Benchmark authoring manifest resources are incoherent"
                )
            item = deepcopy(dict(raw))
            if _FORBIDDEN_MANIFEST_RESOURCE_FIELDS.intersection(item):
                raise _request_invalid(
                    "Benchmark authoring manifest resource fields are unsafe"
                )
            if any(field not in item for field in _MANIFEST_RESOURCE_FIELDS):
                raise _request_invalid(
                    "Benchmark authoring manifest resources are incomplete"
                )
            resource_id = item.get("id")
            path = item.get("path")
            if (
                not isinstance(resource_id, str)
                or not isinstance(path, str)
                or resource_id in manifest_by_id
                or path in manifest_paths
            ):
                raise _request_invalid(
                    "Benchmark authoring manifest resources are ambiguous"
                )
            manifest_by_id[resource_id] = item
            manifest_paths.add(path)
        strict_by_id = {item.id: item for item in document.resources}
        if set(strict_by_id) != set(manifest_by_id):
            raise _request_invalid(
                "Benchmark authoring resource inventories disagree"
            )
        for resource_id, resource in strict_by_id.items():
            try:
                validate_benchmark_authoring_resource_path(
                    resource.path,
                    kind=resource.kind,
                )
            except ValueError as error:
                raise _request_invalid(
                    "Benchmark authoring resource kind and path disagree",
                    error,
                )
            raw = manifest_by_id[resource_id]
            known = _manifest_known_fields(resource)
            if any(
                isinstance(raw[field], bool)
                if field == "size"
                else False
                for field in _MANIFEST_RESOURCE_FIELDS
            ) or any(raw[field] != value for field, value in known.items()):
                raise _request_invalid(
                    "Benchmark authoring resource inventories disagree"
                )
        self._strict_by_id = strict_by_id
        self._manifest_by_id = manifest_by_id

    def require(self, resource_id: str) -> StudioBenchmarkAuthoringResourceV1:
        """Return one owned base resource or fail without implicit upload.

        Args:
            resource_id: Stable logical resource identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Resource is absent.

        Returns:
            Owned strict resource metadata.
        """
        resource = self._strict_by_id.get(resource_id)
        if resource is None:
            raise StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.resource_not_found",
                "Benchmark authoring resource was not found",
            )
        return resource

    def ensure_upload_available(self, *, resource_id: str, path: str) -> None:
        """Reject duplicate logical identities or Package paths.

        Args:
            resource_id: Proposed new logical identity.
            path: Proposed new Package-relative path.

        Raises:
            StudioBenchmarkAuthoringValidationError: Identity or path exists.

        Returns:
            None.
        """
        if resource_id in self._strict_by_id or any(
            item.path == path for item in self._strict_by_id.values()
        ):
            raise _request_invalid(
                "Benchmark authoring resource identity or path already exists"
            )

    def upload(
        self,
        resource: StudioBenchmarkAuthoringResourceV1,
    ) -> StudioBenchmarkAuthoringDocumentV1:
        """Add one authoritative resource to both inventories.

        Args:
            resource: Server-derived managed resource metadata.

        Raises:
            StudioBenchmarkAuthoringValidationError: Projection is invalid.

        Returns:
            Complete deterministic next authoring document.
        """
        self.ensure_upload_available(
            resource_id=resource.id,
            path=resource.path,
        )
        strict = {**self._strict_by_id, resource.id: resource}
        manifest = {
            **self._manifest_by_id,
            resource.id: _manifest_known_fields(resource),
        }
        return self._build(strict, manifest)

    def replace(
        self,
        resource: StudioBenchmarkAuthoringResourceV1,
    ) -> StudioBenchmarkAuthoringDocumentV1:
        """Replace authoritative bytes while preserving logical extensions.

        Args:
            resource: Replacement metadata with stable ID, kind, and path.

        Raises:
            StudioBenchmarkAuthoringValidationError: Projection is invalid.

        Returns:
            Complete deterministic next authoring document.
        """
        current = self.require(resource.id)
        if (
            current.kind != resource.kind
            or current.path != resource.path
        ):
            raise _request_invalid(
                "Benchmark authoring replacement changed logical identity"
            )
        manifest_item = deepcopy(self._manifest_by_id[resource.id])
        manifest_item.update(_manifest_known_fields(resource))
        strict = {**self._strict_by_id, resource.id: resource}
        manifest = {**self._manifest_by_id, resource.id: manifest_item}
        return self._build(strict, manifest)

    def remove(self, resource_id: str) -> StudioBenchmarkAuthoringDocumentV1:
        """Remove one logical resource from both next-revision inventories.

        Args:
            resource_id: Existing logical resource identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Resource is absent.

        Returns:
            Complete deterministic next authoring document.
        """
        self.require(resource_id)
        strict = {
            key: value
            for key, value in self._strict_by_id.items()
            if key != resource_id
        }
        manifest = {
            key: value
            for key, value in self._manifest_by_id.items()
            if key != resource_id
        }
        return self._build(strict, manifest)

    def _build(
        self,
        strict: Mapping[str, StudioBenchmarkAuthoringResourceV1],
        manifest: Mapping[str, dict[str, Any]],
    ) -> StudioBenchmarkAuthoringDocumentV1:
        """Build one strict next document from coherent projected inventories.

        Args:
            strict: Strict resources keyed by logical identity.
            manifest: Manifest declarations keyed by logical identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: Result is unsafe or too
                large.

        Returns:
            Validated complete immutable document value.
        """
        strict_items = tuple(sorted(strict.values(), key=lambda item: item.path))
        manifest_items = [
            deepcopy(item)
            for item in sorted(
                manifest.values(),
                key=lambda item: str(item["path"]),
            )
        ]
        manifest_document = deepcopy(self._manifest_document)
        manifest_document["resources"] = manifest_items
        try:
            return StudioBenchmarkAuthoringDocumentV1(
                manifest=StudioBenchmarkAuthoringManifestV1(
                    path=self._document.manifest.path,
                    document=manifest_document,
                ),
                task_files=self._document.task_files,
                protocol_files=self._document.protocol_files,
                resources=strict_items,
                directories=self._document.directories,
            )
        except (ValidationError, TypeError, ValueError) as error:
            raise _request_invalid(
                "Benchmark authoring content projection is invalid",
                error,
            )


@dataclass(frozen=True)
class StudioBenchmarkAuthoringContentRead:
    """Verified stream and safe metadata for one exact owned resource."""

    revision: StudioBenchmarkAuthoringRevisionV1
    resource: StudioBenchmarkAuthoringResourceV1
    stream: BinaryIO


class StudioBenchmarkAuthoringContentApplicationService:
    """Coordinate bounded managed bytes with immutable authoring revisions."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        content: StudioBenchmarkManagedContent,
    ) -> None:
        """Bind database-neutral authoring and managed-content ports.

        Args:
            repository: Durable draft/revision and command persistence.
            content: Private immutable managed byte store.

        Raises:
            None.

        Returns:
            None.
        """
        self._repository = repository
        self._content = content

    def _base_projection(
        self,
        *,
        draft_id: str,
        base_revision_id: str,
        client_request_id: str,
    ) -> tuple[
        StudioBenchmarkAuthoringRevisionV1,
        _AuthoringResourceProjection,
    ]:
        """Load an owned base and reject new stale commands before streaming.

        Args:
            draft_id: Owning draft identity.
            base_revision_id: Client-observed exact immutable revision.
            client_request_id: Draft-local command identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: Identity is malformed.
            StudioBenchmarkAuthoringNotFoundError: Owned draft/revision is absent.
            StudioBenchmarkAuthoringRevisionConflictError: A new command is stale.

        Returns:
            Exact base revision and validated resource projection.
        """
        try:
            validate_benchmark_draft_id(draft_id)
            validate_benchmark_authoring_revision_id(base_revision_id)
        except ValueError as error:
            raise _request_invalid(
                "Benchmark authoring ownership identity is invalid",
                error,
            )
        draft = self._repository.get_draft(draft_id)
        base = self._repository.get_revision(draft_id, base_revision_id)
        if (
            draft.current_revision_id != base_revision_id
            and not self._repository.has_save_command(
                draft_id,
                client_request_id=client_request_id,
            )
        ):
            raise StudioBenchmarkAuthoringRevisionConflictError(
                "benchmark.authoring.revision_conflict",
                "Benchmark draft current revision has changed",
                current_revision_id=draft.current_revision_id,
            )
        return base, _AuthoringResourceProjection(base.document)

    @staticmethod
    def _result_resource(
        revision: StudioBenchmarkAuthoringRevisionV1,
        resource_id: str,
    ) -> StudioBenchmarkAuthoringResourceV1:
        """Resolve one authoritative resource from a committed result.

        Args:
            revision: Newly committed or idempotently replayed revision.
            resource_id: Expected logical resource identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Durable result is inconsistent.

        Returns:
            Authoritative resource metadata from the result revision.
        """
        for resource in revision.document.resources:
            if resource.id == resource_id:
                return resource
        raise StudioBenchmarkAuthoringNotFoundError(
            "benchmark.authoring.resource_not_found",
            "Benchmark authoring resource was not found",
        )

    def upload(
        self,
        draft_id: str,
        request: StudioBenchmarkAuthoringContentUploadRequestV1,
        stream: BinaryIO,
    ) -> StudioBenchmarkAuthoringContentCommandResultV1:
        """Store a new owned resource and append one immutable revision.

        Args:
            draft_id: Owning draft identity.
            request: Strict upload command metadata.
            stream: Binary content source.

        Raises:
            StudioBenchmarkError: Ownership, storage, idempotency, or CAS fails.

        Returns:
            Newly created or idempotently replayed command result.
        """
        _base, projection = self._base_projection(
            draft_id=draft_id,
            base_revision_id=request.base_revision_id,
            client_request_id=request.client_request_id,
        )
        projection.ensure_upload_available(
            resource_id=request.resource_id,
            path=request.path,
        )
        content_identity, sha256, size = self._content.store_stream(
            stream,
            max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
        )
        resource = StudioBenchmarkAuthoringResourceV1(
            id=request.resource_id,
            kind=request.kind,
            path=request.path,
            media_type=request.media_type,
            sha256=sha256,
            size=size,
            content_identity=content_identity,
        )
        document = projection.upload(resource)
        draft, revision, created = self._repository.save_revision(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint(
                draft_id=draft_id,
                sha256=sha256,
                size=size,
            ),
            base_revision_id=request.base_revision_id,
            document=document,
            provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
        )
        return StudioBenchmarkAuthoringContentCommandResultV1(
            operation="upload",
            created=created,
            draft=draft,
            revision=revision,
            resource=self._result_resource(revision, request.resource_id),
        )

    def replace(
        self,
        draft_id: str,
        request: StudioBenchmarkAuthoringContentReplaceRequestV1,
        stream: BinaryIO,
    ) -> StudioBenchmarkAuthoringContentCommandResultV1:
        """Replace one resource's bytes without mutating its logical history.

        Args:
            draft_id: Owning draft identity.
            request: Strict replacement command metadata.
            stream: Binary replacement source.

        Raises:
            StudioBenchmarkError: Ownership, storage, idempotency, or CAS fails.

        Returns:
            Newly created or idempotently replayed command result.
        """
        _base, projection = self._base_projection(
            draft_id=draft_id,
            base_revision_id=request.base_revision_id,
            client_request_id=request.client_request_id,
        )
        current = projection.require(request.resource_id)
        content_identity, sha256, size = self._content.store_stream(
            stream,
            max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
        )
        resource = StudioBenchmarkAuthoringResourceV1(
            id=current.id,
            kind=current.kind,
            path=current.path,
            media_type=request.media_type,
            sha256=sha256,
            size=size,
            content_identity=content_identity,
        )
        if resource == current:
            raise _request_invalid(
                "Benchmark authoring replacement would not change the resource"
            )
        document = projection.replace(resource)
        draft, revision, created = self._repository.save_revision(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint(
                draft_id=draft_id,
                kind=current.kind,
                path=current.path,
                sha256=sha256,
                size=size,
            ),
            base_revision_id=request.base_revision_id,
            document=document,
            provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
        )
        return StudioBenchmarkAuthoringContentCommandResultV1(
            operation="replace",
            created=created,
            draft=draft,
            revision=revision,
            resource=self._result_resource(revision, request.resource_id),
        )

    def remove(
        self,
        draft_id: str,
        request: StudioBenchmarkAuthoringContentRemoveRequestV1,
    ) -> StudioBenchmarkAuthoringContentCommandResultV1:
        """Logically remove one current resource in a new immutable revision.

        Args:
            draft_id: Owning draft identity.
            request: Strict logical-removal command metadata.

        Raises:
            StudioBenchmarkError: Ownership, idempotency, or CAS fails.

        Returns:
            Newly created or idempotently replayed command result.
        """
        _base, projection = self._base_projection(
            draft_id=draft_id,
            base_revision_id=request.base_revision_id,
            client_request_id=request.client_request_id,
        )
        current = projection.require(request.resource_id)
        document = projection.remove(request.resource_id)
        draft, revision, created = self._repository.save_revision(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint(
                draft_id=draft_id,
                kind=current.kind,
                path=current.path,
                sha256=current.sha256,
                size=current.size,
            ),
            base_revision_id=request.base_revision_id,
            document=document,
            provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
        )
        return StudioBenchmarkAuthoringContentCommandResultV1(
            operation="remove",
            created=created,
            draft=draft,
            revision=revision,
            removed_resource_id=request.resource_id,
        )

    def open_content(
        self,
        draft_id: str,
        revision_id: str,
        resource_id: str,
    ) -> StudioBenchmarkAuthoringContentRead:
        """Open one exact integrity-verified draft/revision/resource capability.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact immutable revision identity.
            resource_id: Logical resource identity within that revision.

        Raises:
            StudioBenchmarkAuthoringValidationError: Identity is malformed.
            StudioBenchmarkAuthoringNotFoundError: Owned scope is absent.
            StudioBenchmarkAuthoringStorageError: Managed bytes fail integrity.

        Returns:
            Safe resource metadata and open verified binary stream.
        """
        try:
            validate_benchmark_draft_id(draft_id)
            validate_benchmark_authoring_revision_id(revision_id)
            validate_benchmark_authoring_resource_id(resource_id)
        except ValueError as error:
            raise _request_invalid(
                "Benchmark authoring content identity is invalid",
                error,
            )
        revision = self._repository.get_revision(draft_id, revision_id)
        resource = next(
            (
                item
                for item in revision.document.resources
                if item.id == resource_id
            ),
            None,
        )
        if resource is None:
            raise StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.resource_not_found",
                "Benchmark authoring resource was not found",
            )
        stream = self._content.open_verified(
            resource.content_identity,
            expected_sha256=resource.sha256,
            expected_size=resource.size,
        )
        return StudioBenchmarkAuthoringContentRead(
            revision=revision,
            resource=resource,
            stream=stream,
        )


__all__ = [
    "StudioBenchmarkAuthoringContentApplicationService",
    "StudioBenchmarkAuthoringContentRead",
    "parse_authoring_content_remove_query",
    "parse_authoring_content_replace_query",
    "parse_authoring_content_upload_query",
]
