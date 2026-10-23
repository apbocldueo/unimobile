"""Strict DTOs for bounded legacy BenchmarkTask JSON migration."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, StrictInt, field_validator

from zhixing.benchmark.identity import canonical_hash

from .benchmark_authoring_models import (
    StudioBenchmarkAuthoringRevisionV1,
    StudioBenchmarkDraftRecordV1,
)
from .models import StudioModel


STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES = 1024 * 1024
STUDIO_BENCHMARK_MIGRATION_MAX_TASKS = 100
STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS = 100

_STABLE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SOURCE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_. ()+-]{0,254}$")

_MIGRATION_BEHAVIOR_CONTRACT = {
    "schemaVersion": 1,
    "source": "standalone-benchmark-task-v1-json-text",
    "taskPolicy": "retain-source-order-no-rewrite-no-dedupe",
    "pluginPolicy": "explicit-initializer-environment-cleanup-evaluator-leaves",
    "appPolicy": "true-dominates-all-explicit-false-otherwise-unresolved",
    "packagePolicy": "explicit-wrapper-no-protocol-ground-truth-or-content",
    "evidencePolicy": "definition-only-unvalidated",
}
STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY = canonical_hash(
    _MIGRATION_BEHAVIOR_CONTRACT
)


def _digest(value: str) -> str:
    """Validate one canonical prefixed SHA-256 identity.

    Args:
        value: Candidate digest.

    Raises:
        ValueError: The identity is malformed.

    Returns:
        The validated digest.
    """
    if _DIGEST.fullmatch(value) is None:
        raise ValueError("invalid SHA-256 identity")
    return value


class StudioBenchmarkLegacyMigrationTargetV1(StudioModel):
    """Explicit Package wrapper and draft intent for one migration."""

    draft_name: str = Field(min_length=1, max_length=256)
    publisher: str
    package_name: str
    version: str
    title: str = Field(min_length=1, max_length=512)
    platform: Literal["android", "harmonyos"]
    split: str
    task_file_path: str = "tasks/imported.json"

    @field_validator("draft_name", "title")
    @classmethod
    def _non_blank_text(cls, value: str) -> str:
        """Require bounded display text with visible content.

        Args:
            value: Candidate display text.

        Raises:
            ValueError: Text is blank or contains control characters.

        Returns:
            The original text without silent normalization.
        """
        if not value.strip() or any(ord(character) < 32 for character in value):
            raise ValueError("display text must be non-blank and control-free")
        return value

    @field_validator("publisher", "package_name", "split")
    @classmethod
    def _identity_segment(cls, value: str) -> str:
        """Require one stable Package or split identifier.

        Args:
            value: Candidate identifier.

        Raises:
            ValueError: The identifier is malformed.

        Returns:
            The validated identifier.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("invalid stable Package identity segment")
        return value

    @field_validator("version")
    @classmethod
    def _semantic_version(cls, value: str) -> str:
        """Require one readable semantic version.

        Args:
            value: Candidate version.

        Raises:
            ValueError: The version is malformed.

        Returns:
            The validated version.
        """
        if _SEMVER.fullmatch(value) is None:
            raise ValueError("invalid Package semantic version")
        return value

    @field_validator("task_file_path")
    @classmethod
    def _task_path(cls, value: str) -> str:
        """Require one normalized Package-relative task JSON target.

        Args:
            value: Candidate target member path.

        Raises:
            ValueError: The path is absolute, traversing, or unsupported.

        Returns:
            The validated path.
        """
        logical = PurePosixPath(value)
        if (
            not value
            or len(value) > 512
            or "\x00" in value
            or "\\" in value
            or logical.is_absolute()
            or ".." in logical.parts
            or "." in logical.parts
            or logical.as_posix() != value
            or not value.startswith("tasks/")
            or not value.endswith(".json")
        ):
            raise ValueError("task target must be normalized tasks/*.json")
        return value


class StudioBenchmarkLegacyMigrationSourceRequestV1(StudioModel):
    """Strict source-text envelope shared by Preview and Confirm."""

    schema_version: Literal[1] = 1
    source_name: str = Field(min_length=1, max_length=255)
    source_text: str
    target: StudioBenchmarkLegacyMigrationTargetV1

    @field_validator("source_name")
    @classmethod
    def _safe_source_name(cls, value: str) -> str:
        """Accept a display basename rather than a browser or host path.

        Args:
            value: Browser-supplied display name.

        Raises:
            ValueError: The value is path-like, blank, or control-bearing.

        Returns:
            The validated display name.
        """
        if (
            value in {".", ".."}
            or _SOURCE_NAME.fullmatch(value) is None
            or "/" in value
            or "\\" in value
            or "\x00" in value
        ):
            raise ValueError("sourceName must be a bounded safe display name")
        return value

    @field_validator("source_text")
    @classmethod
    def _source_bound(cls, value: str) -> str:
        """Enforce the exact submitted UTF-8 source-text capacity.

        Args:
            value: Submitted JSON text.

        Raises:
            ValueError: The UTF-8 source exceeds one MiB.

        Returns:
            The exact submitted text.
        """
        if len(value.encode("utf-8")) > STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES:
            raise ValueError("sourceText exceeds the one MiB migration limit")
        return value


class StudioBenchmarkLegacyMigrationConfirmRequestV1(
    StudioBenchmarkLegacyMigrationSourceRequestV1
):
    """Exact idempotent authority used to confirm one reviewed preview."""

    client_request_id: str
    preview_fingerprint: str
    migration_contract_identity: str

    @field_validator("client_request_id")
    @classmethod
    def _request_id(cls, value: str) -> str:
        """Require one stable browser command identity.

        Args:
            value: Candidate command identity.

        Raises:
            ValueError: The identity is malformed.

        Returns:
            The validated identity.
        """
        if _CLIENT_REQUEST_ID.fullmatch(value) is None:
            raise ValueError("invalid client request identity")
        return value

    _preview_digest = field_validator("preview_fingerprint")(_digest)
    _contract_digest = field_validator("migration_contract_identity")(_digest)

    @property
    def fingerprint(self) -> str:
        """Return the canonical complete Confirm command fingerprint.

        Args:
            None.

        Raises:
            None.

        Returns:
            A SHA-256 identity binding source, target, preview, and request ID.
        """
        return canonical_hash(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class StudioBenchmarkLegacyMigrationSourceFactsV1(StudioModel):
    """Bounded non-sensitive facts about submitted source text."""

    source_name: str
    utf8_size: StrictInt = Field(ge=0, le=STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES)
    source_fingerprint: str
    entry_count: StrictInt = Field(ge=0)
    unique_task_count: StrictInt = Field(ge=0)

    _source_digest = field_validator("source_fingerprint")(_digest)


class StudioBenchmarkLegacyMigrationDiagnosticV1(StudioModel):
    """One sanitized field-addressable source diagnostic."""

    code: str = Field(min_length=1, max_length=160)
    severity: Literal["error", "warning"]
    message: str = Field(min_length=1, max_length=300)
    source_index: StrictInt | None = Field(default=None, ge=0)
    field_path: tuple[str | StrictInt, ...] = ()
    task_id: str | None = Field(default=None, max_length=160)


class StudioBenchmarkLegacyMigrationDiffEntryV1(StudioModel):
    """One deterministic semantic Package wrapper or omission fact."""

    code: str = Field(min_length=1, max_length=160)
    category: Literal["wrapper", "declaration", "omission", "representation"]
    path: tuple[str, ...]
    message: str = Field(min_length=1, max_length=300)


class StudioBenchmarkLegacyMigrationTaskChangesV1(StudioModel):
    """Explicit task-preservation counts for migration review."""

    retained: StrictInt = Field(ge=0)
    renamed: Literal[0] = 0
    removed: Literal[0] = 0
    deduplicated: Literal[0] = 0
    rewritten: Literal[0] = 0


class StudioBenchmarkLegacyMigrationDiffV1(StudioModel):
    """Bounded deterministic semantic diff for one projected Package."""

    task_changes: StudioBenchmarkLegacyMigrationTaskChangesV1
    entries: tuple[StudioBenchmarkLegacyMigrationDiffEntryV1, ...]
    plugin_ids: tuple[str, ...]
    app_ids: tuple[str, ...]


class StudioBenchmarkLegacyMigrationPostWorkV1(StudioModel):
    """One explicit author-owned task left after mechanical migration."""

    code: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=300)
    source_indexes: tuple[StrictInt, ...] = ()


class StudioBenchmarkLegacyMigrationEvidenceV1(StudioModel):
    """Truthful false evidence facts for a definition-only migration."""

    validation: Literal[False] = False
    contract_test: Literal[False] = False
    freeze: Literal[False] = False
    publication: Literal[False] = False
    export: Literal[False] = False
    execution: Literal[False] = False
    device: Literal[False] = False


class StudioBenchmarkLegacyMigrationPreviewV1(StudioModel):
    """Transient strict result of pure legacy source analysis."""

    schema_version: Literal[1] = 1
    confirmable: bool
    source: StudioBenchmarkLegacyMigrationSourceFactsV1
    target: StudioBenchmarkLegacyMigrationTargetV1
    migration_contract_identity: str
    candidate_document_fingerprint: str | None = None
    preview_fingerprint: str | None = None
    diff: StudioBenchmarkLegacyMigrationDiffV1
    diagnostics: tuple[StudioBenchmarkLegacyMigrationDiagnosticV1, ...]
    post_migration_work: tuple[StudioBenchmarkLegacyMigrationPostWorkV1, ...]
    evidence: StudioBenchmarkLegacyMigrationEvidenceV1 = (
        StudioBenchmarkLegacyMigrationEvidenceV1()
    )

    _contract_digest = field_validator("migration_contract_identity")(_digest)
    _candidate_digest = field_validator("candidate_document_fingerprint")(
        lambda value: _digest(value) if value is not None else value
    )
    _preview_digest = field_validator("preview_fingerprint")(
        lambda value: _digest(value) if value is not None else value
    )


class StudioBenchmarkLegacyMigrationConfirmResponseV1(StudioModel):
    """Authoritative fresh or replayed durable migration result."""

    schema_version: Literal[1] = 1
    created: bool
    draft: StudioBenchmarkDraftRecordV1
    revision: StudioBenchmarkAuthoringRevisionV1
    source_fingerprint: str
    preview_fingerprint: str
    migration_contract_identity: str
    candidate_document_fingerprint: str
    evidence: StudioBenchmarkLegacyMigrationEvidenceV1 = (
        StudioBenchmarkLegacyMigrationEvidenceV1()
    )

    _source_digest = field_validator("source_fingerprint")(_digest)
    _preview_digest = field_validator("preview_fingerprint")(_digest)
    _contract_digest = field_validator("migration_contract_identity")(_digest)
    _candidate_digest = field_validator("candidate_document_fingerprint")(_digest)


__all__ = [
    "STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY",
    "STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS",
    "STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES",
    "STUDIO_BENCHMARK_MIGRATION_MAX_TASKS",
    "StudioBenchmarkLegacyMigrationConfirmRequestV1",
    "StudioBenchmarkLegacyMigrationConfirmResponseV1",
    "StudioBenchmarkLegacyMigrationDiagnosticV1",
    "StudioBenchmarkLegacyMigrationDiffEntryV1",
    "StudioBenchmarkLegacyMigrationDiffV1",
    "StudioBenchmarkLegacyMigrationEvidenceV1",
    "StudioBenchmarkLegacyMigrationPostWorkV1",
    "StudioBenchmarkLegacyMigrationPreviewV1",
    "StudioBenchmarkLegacyMigrationSourceFactsV1",
    "StudioBenchmarkLegacyMigrationSourceRequestV1",
    "StudioBenchmarkLegacyMigrationTargetV1",
    "StudioBenchmarkLegacyMigrationTaskChangesV1",
]
