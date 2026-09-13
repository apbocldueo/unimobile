"""Strict versioned DTOs for persisted Studio trajectory replay evidence."""

from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import Field, field_validator, model_validator

from .models import StudioModel, StudioProjectionEntry
from .evidence_origin import (
    StudioExecutionEvidenceOriginV1,
    legacy_replay_origin,
)


ReplayAvailabilityState = Literal[
    "available",
    "not_captured",
    "excluded",
    "hidden",
    "missing",
    "corrupt",
    "redacted",
    "truncated",
]
ReplayIntegrityState = Literal["complete", "partial", "corrupt"]
ReplayProvenance = Literal[
    "real_android_excerpt",
    "fake_contract_fixture",
    "native_replay_package",
    "native_studio_run",
    "native_benchmark_task_run",
    "legacy_benchmark_import",
]
ReplaySourceKind = Literal[
    "benchmark_lifecycle",
    "agent_graph",
    "observation",
    "action",
    "run_result",
]


class ReplayIntegrityDiagnostic(StudioModel):
    """One safe, stable diagnostic about imported replay evidence."""

    code: str
    message: str
    severity: Literal["warning", "error"] = "warning"
    source: str = ""
    causal_index: int | None = Field(default=None, ge=0)

    @field_validator("code", "message")
    @classmethod
    def _required_bounded_text(cls, value: str) -> str:
        """Require and bound diagnostic code and message text.

        Args:
            value (str): Candidate diagnostic field.

        Raises:
            ValueError: The diagnostic code is blank.

        Returns:
            str: One-line bounded text.
        """
        normalized = str(value).strip().replace("\n", " ")[:500]
        if not normalized:
            raise ValueError("Replay diagnostic text cannot be blank")
        return normalized

    @field_validator("source")
    @classmethod
    def _bounded_source(cls, value: str) -> str:
        """Bound an optional diagnostic source label.

        Args:
            value (str): Candidate source label.

        Raises:
            None.

        Returns:
            str: One-line bounded source label.
        """
        return str(value).replace("\n", " ")[:256]


class ReplayEvidenceAvailability(StudioModel):
    """Availability and provenance for one class of replay evidence."""

    state: ReplayAvailabilityState
    reason_code: str = ""
    detail: str = ""

    @field_validator("reason_code", "detail")
    @classmethod
    def _bounded_detail(cls, value: str) -> str:
        """Bound reader-facing availability detail.

        Args:
            value (str): Candidate safe detail.

        Raises:
            None.

        Returns:
            str: One-line bounded detail.
        """
        return str(value).replace("\n", " ")[:500]


class ReplayArtifactDescriptor(StudioModel):
    """Public metadata for one replay-scoped opaque artifact."""

    artifact_id: str = Field(pattern=r"^artifact-[a-f0-9]{32}$")
    kind: str
    availability: ReplayAvailabilityState
    content_type: str
    size: int = Field(ge=0)
    sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    schema_version: str = "1"
    provenance: str = ""
    hidden: bool = False

    @field_validator("kind", "content_type", "schema_version", "provenance")
    @classmethod
    def _bounded_descriptor_text(cls, value: str) -> str:
        """Bound artifact metadata stored in public DTOs.

        Args:
            value (str): Candidate metadata value.

        Raises:
            None.

        Returns:
            str: Bounded string.
        """
        return str(value)[:256]

    @model_validator(mode="after")
    def _content_shape(self) -> "ReplayArtifactDescriptor":
        """Require integrity metadata only for readable content.

        Args:
            None.

        Raises:
            ValueError: Available content has no hash or media type.

        Returns:
            ReplayArtifactDescriptor: Validated descriptor.
        """
        if self.availability in {"available", "redacted", "truncated"}:
            if not self.sha256 or not self.content_type:
                raise ValueError(
                    "readable replay artifact requires hash and content type"
                )
        return self


class ReplayRunSnapshot(StudioModel):
    """Immutable graph and authoring identity fixed for one replayed run."""

    agent_id: str = ""
    revision_id: str | None = None
    contract_version: str = "1.1"
    canonical_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    graph_status: ReplayAvailabilityState = "not_captured"
    agent_graph: dict[str, Any] | None = None
    presentation: dict[str, Any] | None = None
    source_map: tuple[dict[str, Any], ...] = ()
    authoring_policy: str | None = None
    lowering_profile: str | None = None
    capability_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    capability_document: dict[str, Any] | None = None
    projection_map: tuple[StudioProjectionEntry, ...] = ()
    provider_identities: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _verified_graph_shape(self) -> "ReplayRunSnapshot":
        """Keep graph content and availability status consistent.

        Args:
            None.

        Raises:
            ValueError: Graph availability and content disagree.

        Returns:
            ReplayRunSnapshot: Validated immutable snapshot.
        """
        if self.graph_status == "available":
            if self.agent_graph is None or self.canonical_hash is None:
                raise ValueError(
                    "available graph snapshot requires body and canonical hash"
                )
        elif self.agent_graph is not None:
            raise ValueError("unavailable graph snapshot cannot contain a graph body")
        return self


class ReplayRunResultSummary(StudioModel):
    """Safe terminal Agent execution facts used by Replay and History."""

    status: str
    kernel_status: str = ""
    error: str = ""
    step_count: int = Field(default=0, ge=0)
    activation_count: int = Field(default=0, ge=0)
    interaction_count: int = Field(default=0, ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)

    @field_validator("status", "kernel_status", "error")
    @classmethod
    def _bounded_result_text(cls, value: str) -> str:
        """Normalize bounded run-result strings.

        Args:
            value (str): Candidate run-result value.

        Raises:
            None.

        Returns:
            str: Bounded one-line text.
        """
        return str(value).replace("\n", " ")[:1000]


class ReplayBenchmarkPhase(StudioModel):
    """One outer Benchmark lifecycle phase retained independently."""

    phase: str
    status: str
    duration_ms: float | None = Field(default=None, ge=0)
    error_code: str = ""
    message: str = ""
    evidence: dict[str, Any] = Field(default_factory=dict)


class ReplayBenchmarkContext(StudioModel):
    """Optional Benchmark identities, phases, outcome, and evaluation."""

    experiment_id: str
    task_id: str
    agent_id: str
    repeat: int = Field(ge=0)
    outcome: Literal["pass", "fail", "invalid", "skipped"]
    identities: dict[str, str] = Field(default_factory=dict)
    phases: tuple[ReplayBenchmarkPhase, ...] = ()
    evaluation: dict[str, Any] | None = None


class ReplayObservation(StudioModel):
    """One observation correlated to a causal Replay moment."""

    observation_id: str
    sequence: int = Field(ge=0)
    interaction_step: int = Field(ge=0)
    screenshot_artifact_id: str | None = None
    ui_artifact_id: str | None = None
    width: int = Field(default=0, ge=0)
    height: int = Field(default=0, ge=0)
    platform: str = ""
    device_id: str = ""
    overlay: tuple[dict[str, Any], ...] = ()


class ReplayAction(StudioModel):
    """One safe action result correlated to a causal Replay moment."""

    action_id: str
    sequence: int = Field(ge=0)
    interaction_step: int = Field(ge=0)
    status: str
    action_type: str
    effect_performed: bool = False
    effect_kind: str = ""
    terminal_status: str | None = None
    message: str = ""
    error: str = ""
    artifact_id: str | None = None


class NormalizedReplayMoment(StudioModel):
    """Transport-independent causal unit consumed by the Studio reducer."""

    moment_id: str
    causal_index: int = Field(ge=0)
    source_kind: ReplaySourceKind
    source_sequence: int | None = Field(default=None, ge=0)
    timestamp: float | None = None
    phase: str = ""
    kind: str
    role: str = ""
    component: str = ""
    node_id: str = ""
    node_path: str = ""
    activation_id: str = ""
    parent_activation_id: str = ""
    loop_path: str = ""
    loop_iteration: int | None = Field(default=None, ge=0)
    interaction_step: int = Field(default=0, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    observation_id: str | None = None
    action_id: str | None = None
    artifact_ids: tuple[str, ...] = ()


class ReplayEvidenceEnvelope(StudioModel):
    """Complete public replay resource assembled from verified evidence."""

    schema_version: Literal[1] = 1
    run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,160}$")
    imported_at: int = Field(ge=0)
    provenance: ReplayProvenance
    evidence_origin: StudioExecutionEvidenceOriginV1 = Field(
        default_factory=StudioExecutionEvidenceOriginV1
    )
    integrity_state: ReplayIntegrityState
    snapshot: ReplayRunSnapshot
    result: ReplayRunResultSummary
    moments: tuple[NormalizedReplayMoment, ...]
    observations: tuple[ReplayObservation, ...] = ()
    actions: tuple[ReplayAction, ...] = ()
    benchmark: ReplayBenchmarkContext | None = None
    artifacts: tuple[ReplayArtifactDescriptor, ...] = ()
    availability: dict[str, ReplayEvidenceAvailability] = Field(default_factory=dict)
    integrity: tuple[ReplayIntegrityDiagnostic, ...] = ()

    @model_validator(mode="before")
    @classmethod
    def _legacy_origin(cls, value: object) -> object:
        """Supply conservative typed origin for stored pre-5.6 envelopes.

        Args:
            value: Candidate Replay envelope mapping.

        Raises:
            None.

        Returns:
            Mapping with a derived origin only when the field was absent.
        """
        if not isinstance(value, Mapping):
            return value
        if "evidenceOrigin" in value or "evidence_origin" in value:
            return value
        payload = dict(value)
        payload["evidenceOrigin"] = legacy_replay_origin(
            str(payload.get("provenance") or "legacy_benchmark_import")
        ).model_dump(mode="json", by_alias=True)
        return payload

    @model_validator(mode="after")
    def _unique_identities(self) -> "ReplayEvidenceEnvelope":
        """Reject ambiguous public identities before persistence.

        Args:
            None.

        Raises:
            ValueError: Moment, observation, action, or artifact IDs repeat.

        Returns:
            ReplayEvidenceEnvelope: Validated envelope.
        """
        identity_groups = (
            ("moment", [item.moment_id for item in self.moments]),
            ("observation", [item.observation_id for item in self.observations]),
            ("action", [item.action_id for item in self.actions]),
            ("artifact", [item.artifact_id for item in self.artifacts]),
        )
        for name, identities in identity_groups:
            if len(identities) != len(set(identities)):
                raise ValueError(f"Replay {name} identities must be unique")
        indexes = [item.causal_index for item in self.moments]
        if indexes != sorted(indexes):
            raise ValueError("Replay moments must be in causal-index order")
        return self


class ReplayListItem(StudioModel):
    """Compact persisted Replay summary for History."""

    run_id: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,160}$")
    agent_id: str
    agent_status: str
    benchmark_outcome: str | None = None
    provenance: ReplayProvenance
    evidence_origin: StudioExecutionEvidenceOriginV1 = Field(
        default_factory=StudioExecutionEvidenceOriginV1
    )
    integrity_state: ReplayIntegrityState
    evidence_completeness: int = Field(ge=0, le=100)
    imported_at: int

    @model_validator(mode="before")
    @classmethod
    def _legacy_origin(cls, value: object) -> object:
        """Supply conservative typed origin for old compact Replay rows.

        Args:
            value: Candidate compact Replay mapping.

        Raises:
            None.

        Returns:
            Mapping with derived origin when absent.
        """
        if not isinstance(value, Mapping):
            return value
        if "evidenceOrigin" in value or "evidence_origin" in value:
            return value
        payload = dict(value)
        payload["evidenceOrigin"] = legacy_replay_origin(
            str(payload.get("provenance") or "legacy_benchmark_import")
        ).model_dump(mode="json", by_alias=True)
        return payload


class ReplayPage(StudioModel):
    """Bounded cursor page of Replay summaries."""

    items: tuple[ReplayListItem, ...]
    next_cursor: str | None = None


__all__ = [
    "NormalizedReplayMoment",
    "ReplayAction",
    "ReplayArtifactDescriptor",
    "ReplayAvailabilityState",
    "ReplayBenchmarkContext",
    "ReplayBenchmarkPhase",
    "ReplayEvidenceAvailability",
    "ReplayEvidenceEnvelope",
    "ReplayIntegrityDiagnostic",
    "ReplayIntegrityState",
    "ReplayListItem",
    "ReplayObservation",
    "ReplayPage",
    "ReplayProvenance",
    "ReplayRunResultSummary",
    "ReplayRunSnapshot",
    "ReplaySourceKind",
]
