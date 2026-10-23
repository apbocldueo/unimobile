"""Strict versioned DTOs for Studio Benchmark Catalog and preview."""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from pydantic import (
    Field,
    StrictBool,
    field_serializer,
    field_validator,
)

from zhixing.benchmark import ExperimentProtocol
from zhixing.benchmark.diagnostics import BenchmarkDiagnostic

from .models import StudioModel


_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s\"'(])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\s\"']+)"
)
_PROTOCOL_ALIASES = {
    "schemaVersion": "schema_version",
    "taskOrder": "task_order",
    "taskMaterialization": "task_materialization",
    "reuseAcrossAgents": "reuse_across_agents",
    "strictFairness": "strict_fairness",
    "versionPolicy": "version_policy",
    "osVersion": "os_version",
    "packageId": "package_id",
    "maxInteractions": "max_interactions",
    "maxActivations": "max_activations",
    "timeoutSeconds": "timeout_seconds",
    "tokenLimit": "token_limit",
    "requireObservableTokens": "require_observable_tokens",
    "requireVerifiedReset": "require_verified_reset",
    "continueSuite": "continue_suite",
    "preserveEvidence": "preserve_evidence",
}


def _bounded_safe_text(value: object, *, limit: int = 500) -> str:
    """Return bounded single-line text with host paths redacted.

    Args:
        value: Candidate text-like value.
        limit: Maximum returned character count.

    Raises:
        None.

    Returns:
        Safe reader-facing text.
    """
    text = str(value).replace("\r", " ").replace("\n", " ")
    return _ABSOLUTE_PATH.sub(" [redacted-path]", text)[:limit]


def _protocol_from_browser(value: object) -> object:
    """Translate known browser aliases before formal Protocol validation.

    Args:
        value: Untrusted protocol value.

    Raises:
        None.

    Returns:
        Recursively translated value; unknown keys remain for strict rejection.
    """
    if isinstance(value, list):
        return [_protocol_from_browser(item) for item in value]
    if isinstance(value, Mapping):
        return {
            _PROTOCOL_ALIASES.get(str(key), str(key)): _protocol_from_browser(item)
            for key, item in value.items()
        }
    return value


def _protocol_to_browser(protocol: ExperimentProtocol) -> dict[str, Any]:
    """Serialize the formal Protocol using Studio camel-case field names.

    Args:
        protocol: Validated formal ExperimentProtocol.

    Raises:
        None.

    Returns:
        JSON-compatible camel-case protocol mapping.
    """
    reverse = {value: key for key, value in _PROTOCOL_ALIASES.items()}

    def convert(value: object) -> object:
        """Recursively convert mapping keys to browser aliases.

        Args:
            value: JSON-compatible protocol value.

        Raises:
            None.

        Returns:
            Converted JSON-compatible value.
        """
        if isinstance(value, list):
            return [convert(item) for item in value]
        if isinstance(value, dict):
            return {
                reverse.get(str(key), str(key)): convert(item)
                for key, item in value.items()
            }
        return value

    return convert(
        protocol.model_dump(mode="json", exclude_none=True)
    )  # type: ignore[return-value]


class StudioBenchmarkDiagnosticV1(StudioModel):
    """Bounded browser-safe Benchmark diagnostic."""

    code: str = Field(max_length=160)
    message: str = Field(max_length=500)
    severity: Literal["error", "warning", "info"] = "error"
    source: str = Field(default="", max_length=160)
    path: tuple[str | int, ...] = ()
    task_id: str | None = Field(default=None, max_length=256)

    @classmethod
    def from_domain(
        cls,
        diagnostic: BenchmarkDiagnostic,
    ) -> "StudioBenchmarkDiagnosticV1":
        """Project one definition diagnostic without unsafe source values.

        Args:
            diagnostic: Formal Benchmark diagnostic.

        Raises:
            ValueError: Projected values violate the DTO.

        Returns:
            Safe Studio diagnostic.
        """
        safe_path = tuple(
            item
            if isinstance(item, int)
            else _bounded_safe_text(item, limit=160)
            for item in diagnostic.path[:16]
        )
        source = _bounded_safe_text(diagnostic.source, limit=160)
        if "/" in source or "\\" in source:
            source = "benchmark"
        return cls(
            code=_bounded_safe_text(diagnostic.code, limit=160),
            message=_bounded_safe_text(diagnostic.message),
            severity=diagnostic.severity.value,
            source=source,
            path=safe_path,
            task_id=(
                _bounded_safe_text(diagnostic.task_id, limit=256)
                if diagnostic.task_id is not None
                else None
            ),
        )


class StudioBenchmarkSplitSummaryV1(StudioModel):
    """One stable split name and its indexed task count."""

    name: str = Field(min_length=1, max_length=128)
    task_count: int | None = Field(default=None, ge=0)


class StudioBenchmarkCatalogEntryV1(StudioModel):
    """Safe Catalog list item for one concrete Package source."""

    catalog_entry_id: str
    package_identity: str = Field(min_length=1, max_length=384)
    title: str = Field(min_length=1, max_length=512)
    version: str = Field(min_length=1, max_length=128)
    source_kind: Literal["package", "catalog", "installed"]
    platforms: tuple[Literal["android", "harmonyos"], ...]
    splits: tuple[StudioBenchmarkSplitSummaryV1, ...]
    availability: Literal["available", "invalid"]
    warnings: tuple[StudioBenchmarkDiagnosticV1, ...] = ()

    @field_validator("catalog_entry_id")
    @classmethod
    def _opaque_entry_id(cls, value: str) -> str:
        """Require the opaque entry identity form.

        Args:
            value: Candidate entry identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if re.fullmatch(r"benchmark-entry-[a-f0-9]{32}", value) is None:
            raise ValueError("invalid Catalog entry identity")
        return value


class StudioBenchmarkCatalogPageV1(StudioModel):
    """Versioned bounded page of Catalog entries."""

    schema_version: Literal[1] = 1
    items: tuple[StudioBenchmarkCatalogEntryV1, ...]
    next_cursor: str | None = None


class StudioBenchmarkRequirementV1(StudioModel):
    """Safe logical App or plugin requirement."""

    id: str = Field(min_length=1, max_length=255)
    kind: Literal["app", "plugin"]
    platform: str = Field(default="", max_length=64)
    version: str = Field(default="", max_length=128)
    optional: StrictBool = False
    requires_login: StrictBool = False


class StudioBenchmarkResourceSummaryV1(StudioModel):
    """Safe content-addressed resource metadata without source paths."""

    id: str = Field(min_length=1, max_length=255)
    kind: str = Field(min_length=1, max_length=64)
    media_type: str = Field(min_length=1, max_length=255)
    sha256: str
    size: int = Field(ge=0)

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str) -> str:
        """Validate one prefixed content digest.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid content digest")
        return value


class StudioBenchmarkDetailV1(StudioModel):
    """Versioned safe Package detail for one concrete Catalog entry."""

    schema_version: Literal[1] = 1
    catalog_entry_id: str
    package_identity: str
    package_content_identity: str | None = None
    title: str
    version: str
    source_kind: Literal["package", "catalog", "installed"]
    availability: Literal["available", "invalid"]
    platforms: tuple[Literal["android", "harmonyos"], ...]
    splits: tuple[StudioBenchmarkSplitSummaryV1, ...]
    requirements: tuple[StudioBenchmarkRequirementV1, ...] = ()
    resources: tuple[StudioBenchmarkResourceSummaryV1, ...] = ()
    default_protocol: ExperimentProtocol | None = None
    diagnostics: tuple[StudioBenchmarkDiagnosticV1, ...] = ()

    @field_validator("default_protocol", mode="before")
    @classmethod
    def _parse_default_protocol(cls, value: object) -> object:
        """Translate browser aliases when parsing a serialized detail.

        Args:
            value: Optional untrusted protocol mapping.

        Raises:
            ValueError: Formal Protocol validation rejects the mapping.

        Returns:
            Mapping prepared for formal Protocol parsing.
        """
        return _protocol_from_browser(value)

    @field_serializer("default_protocol")
    def _serialize_protocol(
        self,
        value: ExperimentProtocol | None,
    ) -> dict[str, Any] | None:
        """Serialize the formal default Protocol for browser consumers.

        Args:
            value: Optional formal ExperimentProtocol.

        Raises:
            None.

        Returns:
            Camel-case protocol mapping or null.
        """
        return _protocol_to_browser(value) if value is not None else None


class StudioBenchmarkTaskMetadataV1(StudioModel):
    """Safe authoring metadata for one Benchmark task template."""

    task_id: str = Field(min_length=1, max_length=256)
    split: str = Field(min_length=1, max_length=128)
    instruction: str = Field(min_length=1, max_length=32768)
    app: str | None = Field(default=None, max_length=255)
    task_type: Literal["static", "dynamic"]
    requires_login: StrictBool | None = None
    max_steps: int | None = Field(default=None, gt=0)
    initializer_count: int = Field(ge=0)
    evaluator_kind: str = Field(min_length=1, max_length=160)


class StudioBenchmarkTaskPageV1(StudioModel):
    """Versioned stable page of Benchmark task metadata."""

    schema_version: Literal[1] = 1
    catalog_entry_id: str
    split: str
    items: tuple[StudioBenchmarkTaskMetadataV1, ...]
    next_cursor: str | None = None


class StudioBenchmarkValidationIdentitiesV1(StudioModel):
    """Canonical identities produced by definition validation."""

    package: str | None = None
    package_content: str | None = None
    benchmark_plan: str | None = None
    experiment_protocol: str | None = None


class StudioBenchmarkValidationResultV1(StudioModel):
    """Versioned definition-only validation response."""

    schema_version: Literal[1] = 1
    catalog_entry_id: str
    valid: StrictBool
    identities: StudioBenchmarkValidationIdentitiesV1
    diagnostics: tuple[StudioBenchmarkDiagnosticV1, ...] = ()


class StudioDeviceProfileV1(StudioModel):
    """Safe static device profile descriptor."""

    device_profile_id: str
    label: str = Field(min_length=1, max_length=255)
    platform: Literal["android", "harmonyos"]
    availability: Literal["configured"] = "configured"

    @field_validator("device_profile_id")
    @classmethod
    def _stable_profile_id(cls, value: str) -> str:
        """Validate one browser-facing profile identity.

        Args:
            value: Candidate profile identity.

        Raises:
            ValueError: Identity is unstable or resembles a serial field.

        Returns:
            Validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("device profile identity must be stable")
        if value.lower().replace("-", "_") in {
            "serial",
            "adb_serial",
            "device_serial",
        }:
            raise ValueError("raw serial is not a profile identity")
        return value


class StudioDeviceProfilePageV1(StudioModel):
    """Versioned safe device profile directory."""

    schema_version: Literal[1] = 1
    items: tuple[StudioDeviceProfileV1, ...]


class StudioPreviewAgentRevisionV1(StudioModel):
    """One immutable Agent revision selected for preview."""

    agent_id: str
    revision_id: str

    @field_validator("agent_id", "revision_id")
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Validate Agent resource identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("Agent revision identity must be stable")
        return value


class StudioPreviewBenchmarkSelectionV1(StudioModel):
    """Exact Catalog entry, split, and tasks selected for preview."""

    catalog_entry_id: str
    split: str = Field(min_length=1, max_length=128)
    task_ids: tuple[str, ...] = Field(min_length=1, max_length=100)

    @field_validator("task_ids")
    @classmethod
    def _unique_task_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require bounded unique non-blank task identities.

        Args:
            value: Candidate task identities.

        Raises:
            ValueError: A task is blank or repeated.

        Returns:
            Original ordered task identities.
        """
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("task identities must be non-blank and bounded")
        if len(value) != len(set(value)):
            raise ValueError("task identities must be unique")
        return value


class StudioBenchmarkPreviewRequestV1(StudioModel):
    """Strict preview-only Experiment definition request."""

    schema_version: Literal[1] = 1
    agent_revisions: tuple[StudioPreviewAgentRevisionV1, ...] = Field(
        min_length=1,
        max_length=16,
    )
    benchmark: StudioPreviewBenchmarkSelectionV1
    protocol: ExperimentProtocol
    device_profile_id: str

    @field_validator("protocol", mode="before")
    @classmethod
    def _formal_protocol(cls, value: object) -> object:
        """Translate browser aliases before formal Protocol validation.

        Args:
            value: Untrusted protocol mapping.

        Raises:
            ValueError: ExperimentProtocol rejects the translated mapping.

        Returns:
            Mapping prepared for formal Protocol parsing.
        """
        return _protocol_from_browser(value)

    @field_serializer("protocol")
    def _serialize_protocol(
        self,
        value: ExperimentProtocol,
    ) -> dict[str, Any]:
        """Serialize the requested formal Protocol for browser round trips.

        Args:
            value: Formal ExperimentProtocol.

        Raises:
            None.

        Returns:
            Camel-case protocol mapping.
        """
        return _protocol_to_browser(value)

    @field_validator("device_profile_id")
    @classmethod
    def _stable_profile_id(cls, value: str) -> str:
        """Validate preview profile identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("device profile identity must be stable")
        if value.lower().replace("-", "_") in {
            "serial",
            "adb_serial",
            "device_serial",
        }:
            raise ValueError("raw serial is not a profile identity")
        return value


class StudioPreviewAgentIdentityV1(StudioModel):
    """Verified immutable Agent identity returned by preview."""

    agent_id: str
    revision_id: str
    agent_graph: str


class StudioPreviewIdentitiesV1(StudioModel):
    """Canonical definition identities returned by preview."""

    package: str
    package_content: str
    benchmark_plan: str
    experiment_protocol: str


class StudioPreviewExecutionLimitsV1(StudioModel):
    """Advertised Stage 5.1 cardinality limits."""

    max_agents: Literal[1] = 1
    max_selected_tasks: Literal[1] = 1
    max_repeats: Literal[1] = 1
    multi_agent_comparison: Literal[False] = False


class StudioPreviewTaskInstanceV1(StudioModel):
    """Dynamic/static instance availability without materialization."""

    availability: Literal["pending_materialization", "template_only"]
    identity: None = None
    parameters: None = None


class StudioPreviewScheduleEntryV1(StudioModel):
    """One deterministic Agent × task × repeat planned entry."""

    planned_entry_id: str
    agent_id: str
    revision_id: str
    task_id: str
    repeat: int = Field(ge=0)
    order: int = Field(ge=0)
    derived_seed: int
    task_instance: StudioPreviewTaskInstanceV1


class StudioBenchmarkPreviewResponseV1(StudioModel):
    """Versioned preview-only normalized Experiment definition."""

    schema_version: Literal[1] = 1
    preview_only: Literal[True] = True
    preview_fingerprint: str
    identities: StudioPreviewIdentitiesV1
    agent_revisions: tuple[StudioPreviewAgentIdentityV1, ...]
    normalized_protocol: ExperimentProtocol
    device_profile_id: str
    execution_limits: StudioPreviewExecutionLimitsV1
    schedule: tuple[StudioPreviewScheduleEntryV1, ...]
    diagnostics: tuple[StudioBenchmarkDiagnosticV1, ...] = ()

    @field_validator("normalized_protocol", mode="before")
    @classmethod
    def _parse_normalized_protocol(cls, value: object) -> object:
        """Translate browser aliases when parsing a serialized preview.

        Args:
            value: Untrusted normalized protocol mapping.

        Raises:
            ValueError: Formal Protocol validation rejects the mapping.

        Returns:
            Mapping prepared for formal Protocol parsing.
        """
        return _protocol_from_browser(value)

    @field_validator("preview_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        """Validate the canonical preview digest.

        Args:
            value: Candidate fingerprint.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid preview fingerprint")
        return value

    @field_serializer("normalized_protocol")
    def _serialize_protocol(
        self,
        value: ExperimentProtocol,
    ) -> dict[str, Any]:
        """Serialize normalized formal Protocol for browsers.

        Args:
            value: Formal ExperimentProtocol.

        Raises:
            None.

        Returns:
            Camel-case protocol mapping.
        """
        return _protocol_to_browser(value)


__all__ = [
    "StudioBenchmarkCatalogEntryV1",
    "StudioBenchmarkCatalogPageV1",
    "StudioBenchmarkDetailV1",
    "StudioBenchmarkDiagnosticV1",
    "StudioBenchmarkPreviewRequestV1",
    "StudioBenchmarkPreviewResponseV1",
    "StudioBenchmarkRequirementV1",
    "StudioBenchmarkResourceSummaryV1",
    "StudioBenchmarkSplitSummaryV1",
    "StudioBenchmarkTaskMetadataV1",
    "StudioBenchmarkTaskPageV1",
    "StudioBenchmarkValidationIdentitiesV1",
    "StudioBenchmarkValidationResultV1",
    "StudioDeviceProfilePageV1",
    "StudioDeviceProfileV1",
    "StudioPreviewAgentIdentityV1",
    "StudioPreviewAgentRevisionV1",
    "StudioPreviewBenchmarkSelectionV1",
    "StudioPreviewExecutionLimitsV1",
    "StudioPreviewIdentitiesV1",
    "StudioPreviewScheduleEntryV1",
    "StudioPreviewTaskInstanceV1",
]
