"""Strict versioned DTOs for durable Studio Benchmark authoring."""

from __future__ import annotations

import json
import math
import re
from pathlib import PurePosixPath
from typing import Annotated, Any, Literal, Mapping

from pydantic import Field, StrictInt, field_validator, model_validator

from zhixing.benchmark.identity import canonical_hash

from .models import StudioModel


STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES = 2 * 1024 * 1024
STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS = 256
STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES = 64 * 1024 * 1024
STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES = 256 * 1024 * 1024
STUDIO_BENCHMARK_AUTHORING_MAX_PAGE_SIZE = 100
STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS = 100

_DRAFT_ID = re.compile(r"^benchmark-draft-[a-f0-9]{32}$")
_REVISION_ID = re.compile(r"^benchmark-authoring-revision-[a-f0-9]{32}$")
_CATALOG_ENTRY_ID = re.compile(r"^benchmark-entry-[a-f0-9]{32}$")
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_STABLE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTENT_ID = re.compile(r"^benchmark-content-[a-f0-9]{64}$")
_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+"
    r"(?:;[ \t]*[A-Za-z0-9!#$&^_.+-]+="
    r"(?:[A-Za-z0-9!#$&^_.+-]+|\"[A-Za-z0-9 !#$&'()*+,./:;<=>?@\[\\\]^_`{|}~-]+\"))*$"
)
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "authorization",
    "password",
    "secret",
    "secret_key",
}
_DEVICE_ABSOLUTE_PREFIXES = (
    "/data/local/tmp/",
    "/sdcard/",
    "/storage/emulated/",
)


def _json_bytes(value: Any) -> bytes:
    """Encode deterministic finite JSON used for limits and fingerprints.

    Args:
        value: JSON-compatible value.

    Raises:
        TypeError: Value is not JSON-compatible.
        ValueError: Value contains a non-finite number.

    Returns:
        Canonical compact UTF-8 JSON.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _is_host_absolute(value: str) -> bool:
    """Return whether text looks like a host path rather than device data.

    Args:
        value: Candidate semantic string.

    Raises:
        None.

    Returns:
        True for Unix, UNC, home, or Windows absolute host paths.
    """
    if value.startswith(_DEVICE_ABSOLUTE_PREFIXES):
        return False
    return bool(
        value.startswith(("/", "~/", "\\\\"))
        or re.match(r"^[A-Za-z]:[\\/]", value)
    )


def _validate_safe_json(value: Any, path: tuple[str | int, ...] = ()) -> None:
    """Reject unsafe or non-JSON authoring values recursively.

    Args:
        value: Candidate parsed definition value.
        path: Current field path used only for safe validation messages.

    Raises:
        ValueError: Value contains unsafe or non-JSON content.

    Returns:
        None.
    """
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite number at {path or ('document',)}")
        return
    if isinstance(value, str):
        if _is_host_absolute(value):
            raise ValueError(f"host absolute path at {path or ('document',)}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_safe_json(item, path + (index,))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string key at {path or ('document',)}")
            normalized = key.strip().lower().replace("-", "_")
            secret_key = normalized in _SECRET_KEYS or normalized.endswith(
                ("_api_key", "_password", "_secret", "_token")
            )
            if secret_key:
                is_reference = (
                    isinstance(item, Mapping)
                    and set(item) in ({"secret_ref"}, {"secretRef"})
                    and isinstance(
                        item.get("secret_ref", item.get("secretRef")),
                        str,
                    )
                ) or (
                    isinstance(item, str)
                    and re.fullmatch(
                        r"\$\{[A-Za-z_][A-Za-z0-9_.-]*\}",
                        item,
                    )
                    is not None
                )
                if not is_reference:
                    raise ValueError(f"resolved secret at {path + (key,)}")
            _validate_safe_json(item, path + (key,))
        return
    raise ValueError(
        f"unsupported {type(value).__name__} at {path or ('document',)}"
    )


def validate_benchmark_authoring_safe_json(value: Any) -> None:
    """Validate a parsed value against the public authoring safety envelope.

    Args:
        value: Candidate parsed JSON value.

    Raises:
        ValueError: The value contains a host path, resolved secret, non-finite
            number, non-string key, or unsupported runtime object.

    Returns:
        None.
    """
    _validate_safe_json(value)


def _package_path(value: str) -> str:
    """Validate and normalize one bounded Package-relative POSIX path.

    Args:
        value: Candidate path.

    Raises:
        ValueError: Path is empty, absolute, ambiguous, or traverses upward.

    Returns:
        Canonical POSIX path.
    """
    if (
        not value
        or len(value) > 512
        or "\x00" in value
        or "\\" in value
    ):
        raise ValueError("invalid Package-relative path")
    logical = PurePosixPath(value)
    if (
        logical.is_absolute()
        or ".." in logical.parts
        or "." in logical.parts
        or logical.as_posix() != value
    ):
        raise ValueError("path must be normalized and Package-relative")
    return value


def _request_id(value: str) -> str:
    """Validate one client request identity.

    Args:
        value: Candidate identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _CLIENT_REQUEST_ID.fullmatch(value) is None:
        raise ValueError("invalid client request identity")
    return value


def validate_benchmark_authoring_resource_id(value: str) -> str:
    """Validate one stable logical authoring resource identity.

    Args:
        value: Candidate logical resource identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated logical resource identity.
    """
    if _STABLE_ID.fullmatch(value) is None:
        raise ValueError("invalid resource identity")
    return value


def validate_benchmark_authoring_media_type(value: str) -> str:
    """Validate one bounded header-safe authoring media type.

    Args:
        value: Candidate Internet media type.

    Raises:
        ValueError: Media type is blank, oversized, or header-unsafe.

    Returns:
        Validated media type without normalization.
    """
    if (
        not value
        or len(value) > 255
        or "\r" in value
        or "\n" in value
        or _MEDIA_TYPE.fullmatch(value) is None
    ):
        raise ValueError("invalid resource media type")
    return value


def validate_benchmark_authoring_resource_path(
    value: str,
    *,
    kind: Literal["asset", "ground_truth"] | None = None,
) -> str:
    """Validate one normalized resource path and optional kind directory.

    Args:
        value: Candidate Package-relative path.
        kind: Optional logical resource kind whose directory must match.

    Raises:
        ValueError: Path is unsafe, unsupported, or disagrees with its kind.

    Returns:
        Validated Package-relative resource path.
    """
    normalized = _package_path(value)
    expected = f"{kind}/" if kind == "ground_truth" else "assets/"
    if kind is None:
        if not normalized.startswith(("assets/", "ground_truth/")):
            raise ValueError("resource path must use assets/ or ground_truth/")
    elif not normalized.startswith(expected):
        raise ValueError("resource kind and Package path disagree")
    return normalized


def validate_benchmark_draft_id(value: str) -> str:
    """Validate one opaque Benchmark authoring draft identity.

    Args:
        value: Candidate identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _DRAFT_ID.fullmatch(value) is None:
        raise ValueError("invalid Benchmark draft identity")
    return value


def validate_benchmark_authoring_revision_id(value: str) -> str:
    """Validate one opaque Benchmark authoring revision identity.

    Args:
        value: Candidate identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _REVISION_ID.fullmatch(value) is None:
        raise ValueError("invalid Benchmark authoring revision identity")
    return value


class StudioBenchmarkAuthoringManifestV1(StudioModel):
    """Parsed authoring manifest at the fixed Package root location."""

    path: Literal["benchmark.yaml"] = "benchmark.yaml"
    document: dict[str, Any]

    @field_validator("document")
    @classmethod
    def _safe_document(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Validate parsed manifest safety without enforcing Core semantics.

        Args:
            value: Parsed manifest mapping.

        Raises:
            ValueError: Mapping contains unsafe content.

        Returns:
            Validated mapping.
        """
        _validate_safe_json(value, ("manifest",))
        return value


class StudioBenchmarkAuthoringTaskFileV1(StudioModel):
    """One parsed JSON task array at a Package-relative logical path."""

    path: str
    tasks: tuple[Any, ...]

    @field_validator("path")
    @classmethod
    def _task_path(cls, value: str) -> str:
        """Require a normalized task JSON path.

        Args:
            value: Candidate logical path.

        Raises:
            ValueError: Path is unsafe or not a task JSON member.

        Returns:
            Validated path.
        """
        normalized = _package_path(value)
        if not normalized.startswith("tasks/") or not normalized.endswith(".json"):
            raise ValueError("task file must use tasks/*.json")
        return normalized

    @field_validator("tasks")
    @classmethod
    def _safe_tasks(cls, value: tuple[Any, ...]) -> tuple[Any, ...]:
        """Validate task-array JSON safety without requiring BenchmarkTask V1.

        Args:
            value: Parsed task members.

        Raises:
            ValueError: Members contain unsafe data.

        Returns:
            Validated members.
        """
        _validate_safe_json(value, ("tasks",))
        return value


class StudioBenchmarkAuthoringProtocolFileV1(StudioModel):
    """One parsed Protocol mapping at a Package-relative logical path."""

    path: str
    document: dict[str, Any]

    @field_validator("path")
    @classmethod
    def _protocol_path(cls, value: str) -> str:
        """Require a normalized Protocol JSON/YAML path.

        Args:
            value: Candidate logical path.

        Raises:
            ValueError: Path is unsafe or outside the Protocol directory.

        Returns:
            Validated path.
        """
        normalized = _package_path(value)
        if not normalized.startswith("protocols/") or not normalized.endswith(
            (".json", ".yaml", ".yml")
        ):
            raise ValueError("Protocol file must use protocols/*.(json|yaml|yml)")
        return normalized

    @field_validator("document")
    @classmethod
    def _safe_document(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Validate Protocol JSON safety without requiring formal validity.

        Args:
            value: Parsed Protocol mapping.

        Raises:
            ValueError: Mapping contains unsafe content.

        Returns:
            Validated mapping.
        """
        _validate_safe_json(value, ("protocols",))
        return value


class StudioBenchmarkAuthoringResourceV1(StudioModel):
    """Metadata-only reference to immutable server-owned authoring bytes."""

    id: str
    kind: Literal["asset", "ground_truth"]
    path: str
    media_type: str = Field(min_length=1, max_length=255)
    sha256: str
    size: StrictInt = Field(ge=0)
    content_identity: str

    @field_validator("id")
    @classmethod
    def _resource_id(cls, value: str) -> str:
        """Validate one stable logical resource identity.

        Args:
            value: Candidate resource ID.

        Raises:
            ValueError: ID is malformed.

        Returns:
            Validated ID.
        """
        return validate_benchmark_authoring_resource_id(value)

    @field_validator("path")
    @classmethod
    def _resource_path(cls, value: str) -> str:
        """Validate one resource Package path.

        Args:
            value: Candidate logical path.

        Raises:
            ValueError: Path is unsafe or outside supported directories.

        Returns:
            Validated path.
        """
        return validate_benchmark_authoring_resource_path(value)

    @field_validator("media_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        """Validate one response-header-safe media type.

        Args:
            value: Candidate declared media type.

        Raises:
            ValueError: Media type is malformed or header-unsafe.

        Returns:
            Validated media type.
        """
        return validate_benchmark_authoring_media_type(value)

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        """Validate one prefixed SHA-256 digest.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid resource digest")
        return value

    @field_validator("content_identity")
    @classmethod
    def _content_id(cls, value: str) -> str:
        """Validate one opaque managed content identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _CONTENT_ID.fullmatch(value) is None:
            raise ValueError("invalid managed content identity")
        return value


class StudioBenchmarkAuthoringDocumentV1(StudioModel):
    """Safe parsed multi-file Benchmark authoring document."""

    schema_version: Literal[1] = 1
    status: Literal["unvalidated"] = "unvalidated"
    manifest: StudioBenchmarkAuthoringManifestV1
    task_files: tuple[StudioBenchmarkAuthoringTaskFileV1, ...]
    protocol_files: tuple[StudioBenchmarkAuthoringProtocolFileV1, ...] = ()
    resources: tuple[StudioBenchmarkAuthoringResourceV1, ...] = ()
    directories: tuple[Literal["assets", "ground_truth"], ...] = (
        "assets",
        "ground_truth",
    )

    @model_validator(mode="after")
    def _closed_inventory(self) -> "StudioBenchmarkAuthoringDocumentV1":
        """Require deterministic unique inventory and a bounded document.

        Args:
            None.

        Raises:
            ValueError: Inventory is duplicated, unsorted, or oversized.

        Returns:
            Validated authoring document.
        """
        task_paths = [item.path for item in self.task_files]
        protocol_paths = [item.path for item in self.protocol_files]
        resource_paths = [item.path for item in self.resources]
        resource_ids = [item.id for item in self.resources]
        all_paths = ["benchmark.yaml", *task_paths, *protocol_paths, *resource_paths]
        if len(all_paths) != len(set(all_paths)):
            raise ValueError("authoring member paths must be unique")
        if len(resource_ids) != len(set(resource_ids)):
            raise ValueError("authoring resource identities must be unique")
        if task_paths != sorted(task_paths):
            raise ValueError("task files must use deterministic path order")
        if protocol_paths != sorted(protocol_paths):
            raise ValueError("Protocol files must use deterministic path order")
        if resource_paths != sorted(resource_paths):
            raise ValueError("resources must use deterministic path order")
        if len(all_paths) > STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS:
            raise ValueError("authoring member count exceeds the safe limit")
        if self.directories != ("assets", "ground_truth"):
            raise ValueError("authoring logical directories are fixed")
        payload = self.model_dump(mode="json", by_alias=True, exclude_none=True)
        if len(_json_bytes(payload)) > STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES:
            raise ValueError("authoring definition exceeds the safe byte limit")
        return self

    @property
    def fingerprint(self) -> str:
        """Return deterministic identity for the complete authoring document.

        Args:
            None.

        Raises:
            None.

        Returns:
            SHA-256-prefixed canonical document fingerprint.
        """
        return canonical_hash(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class StudioBenchmarkAuthoringProvenanceV1(StudioModel):
    """Safe source provenance for an immutable authoring revision."""

    source_kind: Literal["template", "catalog", "edit", "legacy_migration"]
    template_name: Literal[
        "minimal",
        "dynamic-task",
        "composite-evaluation",
    ] | None = None
    catalog_entry_id: str | None = None
    catalog_snapshot_identity: str | None = None
    package_identity: str | None = Field(default=None, max_length=384)
    source_fingerprint: str | None = None
    source_display_name: str | None = Field(default=None, min_length=1, max_length=255)
    preview_fingerprint: str | None = None
    candidate_document_fingerprint: str | None = None
    migration_contract_identity: str | None = None
    task_entry_count: StrictInt | None = Field(default=None, ge=0, le=100)
    unique_task_count: StrictInt | None = Field(default=None, ge=0, le=100)

    @field_validator("catalog_entry_id")
    @classmethod
    def _entry_id(cls, value: str | None) -> str | None:
        """Validate an optional opaque Catalog identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if value is not None and _CATALOG_ENTRY_ID.fullmatch(value) is None:
            raise ValueError("invalid Catalog entry identity")
        return value

    @field_validator(
        "catalog_snapshot_identity",
        "source_fingerprint",
        "preview_fingerprint",
        "candidate_document_fingerprint",
        "migration_contract_identity",
    )
    @classmethod
    def _optional_digest(cls, value: str | None) -> str | None:
        """Validate optional prefixed SHA-256 identities.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if value is not None and _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid provenance digest")
        return value

    @field_validator("source_display_name")
    @classmethod
    def _source_display_name(cls, value: str | None) -> str | None:
        """Reject path-like or control-bearing migration display names.

        Args:
            value: Optional safe browser file basename.

        Raises:
            ValueError: The value is path-like, blank, or unsafe.

        Returns:
            The validated optional display name.
        """
        if value is not None and (
            not value.strip()
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or "\x00" in value
            or any(ord(character) < 32 for character in value)
        ):
            raise ValueError("invalid migration source display name")
        return value

    @model_validator(mode="after")
    def _source_shape(self) -> "StudioBenchmarkAuthoringProvenanceV1":
        """Require fields appropriate to one source kind.

        Args:
            None.

        Raises:
            ValueError: Source-specific fields disagree.

        Returns:
            Validated provenance.
        """
        migration_values = (
            self.source_display_name,
            self.preview_fingerprint,
            self.candidate_document_fingerprint,
            self.migration_contract_identity,
            self.task_entry_count,
            self.unique_task_count,
        )
        if self.source_kind == "template":
            if self.template_name is None or any(
                value is not None
                for value in (
                    self.catalog_entry_id,
                    self.catalog_snapshot_identity,
                    *migration_values,
                )
            ):
                raise ValueError("invalid template provenance")
        elif self.source_kind == "catalog":
            if (
                self.catalog_entry_id is None
                or self.catalog_snapshot_identity is None
                or self.package_identity is None
                or self.source_fingerprint is None
                or self.template_name is not None
                or any(value is not None for value in migration_values)
            ):
                raise ValueError("invalid Catalog provenance")
        elif self.source_kind == "legacy_migration":
            if (
                self.source_fingerprint is None
                or any(value is None for value in migration_values)
                or any(
                    value is not None
                    for value in (
                        self.template_name,
                        self.catalog_entry_id,
                        self.catalog_snapshot_identity,
                        self.package_identity,
                    )
                )
                or self.task_entry_count != self.unique_task_count
            ):
                raise ValueError("invalid legacy migration provenance")
        elif any(
            value is not None
            for value in (
                self.template_name,
                self.catalog_entry_id,
                self.catalog_snapshot_identity,
                self.package_identity,
                self.source_fingerprint,
                *migration_values,
            )
        ):
            raise ValueError("edit provenance contains source fields")
        return self


class StudioBenchmarkDraftRecordV1(StudioModel):
    """Mutable draft metadata with one current immutable revision pointer."""

    draft_id: str
    name: str = Field(min_length=1, max_length=256)
    current_revision_id: str
    created_at: StrictInt = Field(ge=0)
    updated_at: StrictInt = Field(ge=0)

    @field_validator("draft_id")
    @classmethod
    def _draft_id(cls, value: str) -> str:
        """Validate the opaque draft identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("current_revision_id")
    @classmethod
    def _revision_id(cls, value: str) -> str:
        """Validate the current opaque authoring revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_authoring_revision_id(value)


class StudioBenchmarkAuthoringRevisionV1(StudioModel):
    """One immutable unvalidated Benchmark authoring revision."""

    schema_version: Literal[1] = 1
    revision_id: str
    draft_id: str
    ordinal: StrictInt = Field(ge=1)
    parent_revision_id: str | None = None
    document: StudioBenchmarkAuthoringDocumentV1
    document_fingerprint: str
    provenance: StudioBenchmarkAuthoringProvenanceV1
    status: Literal["unvalidated"] = "unvalidated"
    created_at: StrictInt = Field(ge=0)

    @field_validator("revision_id", "parent_revision_id")
    @classmethod
    def _revision_ids(cls, value: str | None) -> str | None:
        """Validate authoring revision identities.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return (
            validate_benchmark_authoring_revision_id(value)
            if value is not None
            else None
        )

    @field_validator("draft_id")
    @classmethod
    def _draft_id(cls, value: str) -> str:
        """Validate the owning draft identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("document_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        """Validate a document fingerprint.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid authoring document fingerprint")
        return value

    @model_validator(mode="after")
    def _revision_shape(self) -> "StudioBenchmarkAuthoringRevisionV1":
        """Verify fingerprint and parent shape.

        Args:
            None.

        Raises:
            ValueError: Stored identity facts disagree.

        Returns:
            Validated revision.
        """
        if self.document_fingerprint != self.document.fingerprint:
            raise ValueError("authoring document fingerprint mismatch")
        if (self.ordinal == 1) != (self.parent_revision_id is None):
            raise ValueError("initial revision alone may omit a parent")
        return self


class StudioBenchmarkDraftPageV1(StudioModel):
    """Bounded deterministic page of Benchmark draft metadata."""

    schema_version: Literal[1] = 1
    items: tuple[StudioBenchmarkDraftRecordV1, ...]
    next_cursor: str | None = None


class StudioBenchmarkDraftDetailV1(StudioModel):
    """One draft and its complete current immutable revision."""

    schema_version: Literal[1] = 1
    draft: StudioBenchmarkDraftRecordV1
    current_revision: StudioBenchmarkAuthoringRevisionV1

    @model_validator(mode="after")
    def _current_matches(self) -> "StudioBenchmarkDraftDetailV1":
        """Require the embedded revision to be the draft current child.

        Args:
            None.

        Raises:
            ValueError: Draft/revision identities disagree.

        Returns:
            Validated detail.
        """
        if (
            self.current_revision.draft_id != self.draft.draft_id
            or self.current_revision.revision_id
            != self.draft.current_revision_id
        ):
            raise ValueError("draft current revision does not match")
        return self


class StudioBenchmarkTemplateDraftSourceV1(StudioModel):
    """Create-source parameters for a built-in scaffold template."""

    kind: Literal["template"] = "template"
    template: Literal["minimal", "dynamic-task", "composite-evaluation"]
    publisher: str
    package_name: str
    version: str = "0.1.0"

    @field_validator("publisher", "package_name")
    @classmethod
    def _identity_segments(cls, value: str) -> str:
        """Validate one Package identity segment.

        Args:
            value: Candidate identity segment.

        Raises:
            ValueError: Segment is malformed.

        Returns:
            Validated segment.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("invalid Package identity segment")
        return value

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        """Validate Package semantic version syntax.

        Args:
            value: Candidate semantic version.

        Raises:
            ValueError: Version is malformed.

        Returns:
            Validated version.
        """
        if _SEMVER.fullmatch(value) is None:
            raise ValueError("invalid Package semantic version")
        return value


class StudioBenchmarkCatalogDraftSourceV1(StudioModel):
    """Create-source parameters for an opaque current Catalog entry."""

    kind: Literal["catalog"] = "catalog"
    catalog_entry_id: str

    @field_validator("catalog_entry_id")
    @classmethod
    def _entry_id(cls, value: str) -> str:
        """Validate the opaque Catalog entry identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _CATALOG_ENTRY_ID.fullmatch(value) is None:
            raise ValueError("invalid Catalog entry identity")
        return value


StudioBenchmarkDraftSourceV1 = Annotated[
    StudioBenchmarkTemplateDraftSourceV1 | StudioBenchmarkCatalogDraftSourceV1,
    Field(discriminator="kind"),
]


class StudioBenchmarkDraftCreateRequestV1(StudioModel):
    """Strict idempotent request to create one Benchmark draft."""

    schema_version: Literal[1] = 1
    client_request_id: str
    name: str = Field(min_length=1, max_length=256)
    source: StudioBenchmarkDraftSourceV1

    @field_validator("client_request_id")
    @classmethod
    def _client_request_id(cls, value: str) -> str:
        """Validate the create request identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _request_id(value)

    @property
    def fingerprint(self) -> str:
        """Return the canonical create request fingerprint.

        Args:
            None.

        Raises:
            None.

        Returns:
            SHA-256-prefixed request fingerprint.
        """
        return canonical_hash(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class StudioBenchmarkRevisionSaveRequestV1(StudioModel):
    """Strict idempotent optimistic request to append an authoring revision."""

    schema_version: Literal[1] = 1
    client_request_id: str
    base_revision_id: str
    document: StudioBenchmarkAuthoringDocumentV1

    @field_validator("client_request_id")
    @classmethod
    def _client_request_id(cls, value: str) -> str:
        """Validate the save request identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _request_id(value)

    @field_validator("base_revision_id")
    @classmethod
    def _base_revision_id(cls, value: str) -> str:
        """Validate the optimistic base revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @property
    def fingerprint(self) -> str:
        """Return the canonical save request fingerprint.

        Args:
            None.

        Raises:
            None.

        Returns:
            SHA-256-prefixed request fingerprint.
        """
        return canonical_hash(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class StudioBenchmarkAuthoringContentUploadRequestV1(StudioModel):
    """Strict metadata for one draft-owned managed-content upload."""

    schema_version: Literal[1] = 1
    client_request_id: str
    base_revision_id: str
    resource_id: str
    kind: Literal["asset", "ground_truth"]
    path: str
    media_type: str

    @field_validator("client_request_id")
    @classmethod
    def _client_request_id(cls, value: str) -> str:
        """Validate the upload command identity.

        Args:
            value: Candidate client request identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _request_id(value)

    @field_validator("base_revision_id")
    @classmethod
    def _base_revision_id(cls, value: str) -> str:
        """Validate the optimistic base revision identity.

        Args:
            value: Candidate immutable revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("resource_id")
    @classmethod
    def _resource_id(cls, value: str) -> str:
        """Validate the new logical resource identity.

        Args:
            value: Candidate logical resource identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated resource identity.
        """
        return validate_benchmark_authoring_resource_id(value)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        """Validate the new Package-relative resource path.

        Args:
            value: Candidate Package-relative path.

        Raises:
            ValueError: Path is unsafe or unsupported.

        Returns:
            Validated path.
        """
        return validate_benchmark_authoring_resource_path(value)

    @field_validator("media_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        """Validate the declared upload media type.

        Args:
            value: Candidate media type.

        Raises:
            ValueError: Media type is malformed or header-unsafe.

        Returns:
            Validated media type.
        """
        return validate_benchmark_authoring_media_type(value)

    @model_validator(mode="after")
    def _kind_path(self) -> "StudioBenchmarkAuthoringContentUploadRequestV1":
        """Require the Package directory to agree with resource kind.

        Raises:
            ValueError: Kind and Package-relative path disagree.

        Returns:
            Validated upload metadata.
        """
        validate_benchmark_authoring_resource_path(self.path, kind=self.kind)
        return self

    def fingerprint(
        self,
        *,
        draft_id: str,
        sha256: str,
        size: int,
    ) -> str:
        """Return the canonical byte-bound upload command fingerprint.

        Args:
            draft_id: Owning draft identity.
            sha256: Server-derived prefixed content digest.
            size: Server-derived content size.

        Raises:
            ValueError: Draft or byte facts are malformed.

        Returns:
            SHA-256-prefixed canonical command fingerprint.
        """
        validate_benchmark_draft_id(draft_id)
        if _DIGEST.fullmatch(sha256) is None or size < 0:
            raise ValueError("invalid managed content facts")
        return canonical_hash(
            {
                "contract": "studio-benchmark-authoring-content-command-v1",
                "operation": "upload",
                "draftId": draft_id,
                **self.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                "sha256": sha256,
                "size": size,
            }
        )


class StudioBenchmarkAuthoringContentReplaceRequestV1(StudioModel):
    """Strict metadata for replacing one owned logical resource."""

    schema_version: Literal[1] = 1
    client_request_id: str
    base_revision_id: str
    resource_id: str
    media_type: str

    @field_validator("client_request_id")
    @classmethod
    def _client_request_id(cls, value: str) -> str:
        """Validate the replacement command identity.

        Args:
            value: Candidate client request identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _request_id(value)

    @field_validator("base_revision_id")
    @classmethod
    def _base_revision_id(cls, value: str) -> str:
        """Validate the optimistic base revision identity.

        Args:
            value: Candidate immutable revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("resource_id")
    @classmethod
    def _resource_id(cls, value: str) -> str:
        """Validate the target logical resource identity.

        Args:
            value: Candidate logical resource identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated resource identity.
        """
        return validate_benchmark_authoring_resource_id(value)

    @field_validator("media_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        """Validate the replacement media type.

        Args:
            value: Candidate media type.

        Raises:
            ValueError: Media type is malformed or header-unsafe.

        Returns:
            Validated media type.
        """
        return validate_benchmark_authoring_media_type(value)

    def fingerprint(
        self,
        *,
        draft_id: str,
        kind: Literal["asset", "ground_truth"],
        path: str,
        sha256: str,
        size: int,
    ) -> str:
        """Return the canonical byte-bound replacement fingerprint.

        Args:
            draft_id: Owning draft identity.
            kind: Stable target resource kind.
            path: Stable target Package-relative path.
            sha256: Server-derived prefixed content digest.
            size: Server-derived content size.

        Raises:
            ValueError: Ownership or byte facts are malformed.

        Returns:
            SHA-256-prefixed canonical command fingerprint.
        """
        validate_benchmark_draft_id(draft_id)
        validate_benchmark_authoring_resource_path(path, kind=kind)
        if _DIGEST.fullmatch(sha256) is None or size < 0:
            raise ValueError("invalid managed content facts")
        return canonical_hash(
            {
                "contract": "studio-benchmark-authoring-content-command-v1",
                "operation": "replace",
                "draftId": draft_id,
                **self.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                "kind": kind,
                "path": path,
                "sha256": sha256,
                "size": size,
            }
        )


class StudioBenchmarkAuthoringContentRemoveRequestV1(StudioModel):
    """Strict metadata for one logical managed-resource removal."""

    schema_version: Literal[1] = 1
    client_request_id: str
    base_revision_id: str
    resource_id: str

    @field_validator("client_request_id")
    @classmethod
    def _client_request_id(cls, value: str) -> str:
        """Validate the removal command identity.

        Args:
            value: Candidate client request identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _request_id(value)

    @field_validator("base_revision_id")
    @classmethod
    def _base_revision_id(cls, value: str) -> str:
        """Validate the optimistic base revision identity.

        Args:
            value: Candidate immutable revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("resource_id")
    @classmethod
    def _resource_id(cls, value: str) -> str:
        """Validate the removed logical resource identity.

        Args:
            value: Candidate logical resource identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated resource identity.
        """
        return validate_benchmark_authoring_resource_id(value)

    def fingerprint(
        self,
        *,
        draft_id: str,
        kind: Literal["asset", "ground_truth"],
        path: str,
        sha256: str,
        size: int,
    ) -> str:
        """Return the canonical removal fingerprint bound to the base resource.

        Args:
            draft_id: Owning draft identity.
            kind: Removed resource kind.
            path: Removed Package-relative path.
            sha256: Digest referenced by the base revision.
            size: Size referenced by the base revision.

        Raises:
            ValueError: Ownership or content facts are malformed.

        Returns:
            SHA-256-prefixed canonical command fingerprint.
        """
        validate_benchmark_draft_id(draft_id)
        validate_benchmark_authoring_resource_path(path, kind=kind)
        if _DIGEST.fullmatch(sha256) is None or size < 0:
            raise ValueError("invalid managed content facts")
        return canonical_hash(
            {
                "contract": "studio-benchmark-authoring-content-command-v1",
                "operation": "remove",
                "draftId": draft_id,
                **self.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                "kind": kind,
                "path": path,
                "sha256": sha256,
                "size": size,
            }
        )


class StudioBenchmarkAuthoringContentCommandResultV1(StudioModel):
    """Versioned result that can rehydrate a later resource editor."""

    schema_version: Literal[1] = 1
    operation: Literal["upload", "replace", "remove"]
    created: bool
    draft: StudioBenchmarkDraftRecordV1
    revision: StudioBenchmarkAuthoringRevisionV1
    resource: StudioBenchmarkAuthoringResourceV1 | None = None
    removed_resource_id: str | None = None

    @field_validator("removed_resource_id")
    @classmethod
    def _removed_resource_id(cls, value: str | None) -> str | None:
        """Validate an optional removed logical resource identity.

        Args:
            value: Candidate removed resource identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity or None.
        """
        return (
            validate_benchmark_authoring_resource_id(value)
            if value is not None
            else None
        )

    @model_validator(mode="after")
    def _result_shape(self) -> "StudioBenchmarkAuthoringContentCommandResultV1":
        """Require operation-specific result fields and ownership coherence.

        Raises:
            ValueError: Result fields or aggregate identities disagree.

        Returns:
            Validated command result.
        """
        if self.draft.draft_id != self.revision.draft_id:
            raise ValueError("content command aggregate result does not match")
        if self.operation == "remove":
            if self.resource is not None or self.removed_resource_id is None:
                raise ValueError("remove result fields are invalid")
        elif self.resource is None or self.removed_resource_id is not None:
            raise ValueError("write result fields are invalid")
        return self


class StudioBenchmarkDraftCreateResponseV1(StudioModel):
    """Versioned result of an idempotent draft create command."""

    schema_version: Literal[1] = 1
    created: bool
    draft: StudioBenchmarkDraftRecordV1
    revision: StudioBenchmarkAuthoringRevisionV1


class StudioBenchmarkRevisionSaveResponseV1(StudioModel):
    """Versioned result of an idempotent authoring revision command."""

    schema_version: Literal[1] = 1
    created: bool
    draft: StudioBenchmarkDraftRecordV1
    revision: StudioBenchmarkAuthoringRevisionV1


__all__ = [
    "STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES",
    "STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS",
    "STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS",
    "STUDIO_BENCHMARK_AUTHORING_MAX_PAGE_SIZE",
    "STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES",
    "STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES",
    "StudioBenchmarkAuthoringContentCommandResultV1",
    "StudioBenchmarkAuthoringContentRemoveRequestV1",
    "StudioBenchmarkAuthoringContentReplaceRequestV1",
    "StudioBenchmarkAuthoringContentUploadRequestV1",
    "StudioBenchmarkAuthoringDocumentV1",
    "StudioBenchmarkAuthoringManifestV1",
    "StudioBenchmarkAuthoringProtocolFileV1",
    "StudioBenchmarkAuthoringProvenanceV1",
    "StudioBenchmarkAuthoringResourceV1",
    "StudioBenchmarkAuthoringRevisionV1",
    "StudioBenchmarkAuthoringTaskFileV1",
    "StudioBenchmarkCatalogDraftSourceV1",
    "StudioBenchmarkDraftCreateRequestV1",
    "StudioBenchmarkDraftCreateResponseV1",
    "StudioBenchmarkDraftDetailV1",
    "StudioBenchmarkDraftPageV1",
    "StudioBenchmarkDraftRecordV1",
    "StudioBenchmarkDraftSourceV1",
    "StudioBenchmarkRevisionSaveRequestV1",
    "StudioBenchmarkRevisionSaveResponseV1",
    "StudioBenchmarkTemplateDraftSourceV1",
    "validate_benchmark_authoring_revision_id",
    "validate_benchmark_authoring_safe_json",
    "validate_benchmark_authoring_media_type",
    "validate_benchmark_authoring_resource_id",
    "validate_benchmark_authoring_resource_path",
    "validate_benchmark_draft_id",
]
