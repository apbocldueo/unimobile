"""Strict versioned DTOs for Studio Run resources, events, and debug evidence."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any, Literal, Mapping

from pydantic import Field, StrictBool, field_validator, model_validator

from zhixing.components import RunEvent, RunResult

from .models import StudioModel, StudioProjectionEntry
from .run_safety import reject_unsafe_run_metadata, sanitize_runtime_value


_RESOURCE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_RUN_ID = re.compile(r"^run-[a-f0-9]{32}$")
_ARTIFACT_ID = re.compile(r"^artifact-[a-f0-9]{32}$")


class StudioRunLifecycle(str, Enum):
    """Persistent resource lifecycle independent from Agent RunStatus."""

    ACCEPTED = "accepted"
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    TERMINAL = "terminal"


class RunEvidenceAvailability(str, Enum):
    """Availability vocabulary shared by Run debug and artifact evidence."""

    AVAILABLE = "available"
    NOT_CAPTURED = "not_captured"
    EXCLUDED = "excluded"
    HIDDEN = "hidden"
    MISSING = "missing"
    CORRUPT = "corrupt"
    REDACTED = "redacted"
    TRUNCATED = "truncated"


class StudioRunTaskV1(StudioModel):
    """Bounded ordinary Agent task input, independent from BenchmarkTask."""

    text: str = Field(min_length=1, max_length=32768)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text")
    @classmethod
    def _non_blank_text(cls, value: str) -> str:
        """Reject blank task instructions.

        Args:
            value (str): Candidate instruction.

        Raises:
            ValueError: The instruction is blank.

        Returns:
            str: Original non-blank instruction.
        """
        if not value.strip():
            raise ValueError("task text must not be blank")
        return value

    @field_validator("metadata")
    @classmethod
    def _safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Validate bounded task metadata before persistence.

        Args:
            value (dict[str, Any]): Candidate JSON metadata.

        Raises:
            ValueError: Metadata is unsafe or exceeds limits.

        Returns:
            dict[str, Any]: Detached validated metadata.
        """
        lowered = {
            re.sub(r"(?<!^)(?=[A-Z])", "_", str(key))
            .lower()
            .replace("-", "_")
            for key in value
        }
        benchmark_markers = {"evaluation", "evaluator", "initializer", "benchmark"}
        if "task_id" in lowered and lowered.intersection(benchmark_markers):
            raise ValueError("BenchmarkTask-shaped input is not a Studio Run task")
        return reject_unsafe_run_metadata(value)


class CreateStudioRunRequestV1(StudioModel):
    """Versioned idempotent request to execute one saved Agent revision."""

    schema_version: Literal[1] = 1
    client_request_id: str
    agent_id: str
    revision_id: str
    task: StudioRunTaskV1
    device_profile_id: str = "local-android"
    runtime_kind: Literal["android"] = "android"

    @field_validator(
        "client_request_id",
        "agent_id",
        "revision_id",
        "device_profile_id",
    )
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Require a bounded stable resource identity.

        Args:
            value (str): Candidate identity.

        Raises:
            ValueError: Identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _RESOURCE_ID.fullmatch(value):
            raise ValueError("Run request identities must be stable")
        normalized = value.lower().replace("-", "_")
        if normalized in {"serial", "adb_serial", "device_serial"}:
            raise ValueError("raw device serial is not an accepted identity")
        return value


def canonical_run_request_fingerprint(request: CreateStudioRunRequestV1) -> str:
    """Compute a deterministic request fingerprint for idempotent creation.

    Args:
        request (CreateStudioRunRequestV1): Strict request DTO.

    Raises:
        ValueError: Request cannot be serialized as finite JSON.

    Returns:
        str: SHA-256-prefixed canonical request digest.
    """
    encoded = json.dumps(
        request.model_dump(mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class RunSnapshotV1(StudioModel):
    """Self-contained immutable authoring and graph evidence for one Run."""

    schema_version: Literal[1] = 1
    agent_id: str
    revision_id: str
    contract_version: Literal["1.1"] = "1.1"
    compile_contract_version: str = "studio-compile-v1"
    canonical_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    agent_graph: dict[str, Any]
    presentation: dict[str, Any] = Field(default_factory=dict)
    source_map: tuple[dict[str, Any], ...] = ()
    authoring_policy: str | None = None
    lowering_profile: str | None = None
    capability_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    capability_document: dict[str, Any] = Field(default_factory=dict)
    projection_map: tuple[StudioProjectionEntry, ...] = ()
    provider_identities: tuple[str, ...] = ()

    @field_validator("agent_id", "revision_id")
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Validate snapshot resource identities.

        Args:
            value (str): Candidate identity.

        Raises:
            ValueError: Identity is unstable.

        Returns:
            str: Validated identity.
        """
        if not _RESOURCE_ID.fullmatch(value):
            raise ValueError("snapshot identity must be stable")
        return value


class StudioRunResultSummaryV1(StudioModel):
    """Safe terminal execution facts retained by the Run resource."""

    status: str
    kernel_status: str = ""
    error_code: str = ""
    error: str = Field(default="", max_length=1000)
    step_count: int = Field(default=0, ge=0)
    activation_count: int = Field(default=0, ge=0)
    interaction_count: int = Field(default=0, ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)
    final_output: Any = None
    artifact_namespace: str = ""

    @classmethod
    def from_runtime(
        cls,
        result: RunResult,
        *,
        error_code: str = "",
    ) -> "StudioRunResultSummaryV1":
        """Build a bounded summary from the canonical Runtime result.

        Args:
            result (RunResult): Runtime terminal result.
            error_code (str): Stable orchestration error code, when present.

        Raises:
            ValueError: Sanitized fields violate the strict DTO.

        Returns:
            StudioRunResultSummaryV1: Safe terminal summary.
        """
        usage = sanitize_runtime_value(result.usage).value
        output = sanitize_runtime_value(result.final_output).value
        error = sanitize_runtime_value(result.error).value
        details = sanitize_runtime_value(result.error_details).value
        code = error_code
        if not code and isinstance(details, Mapping):
            code = str(details.get("kernel_error_code") or "")
        return cls(
            status=result.status.value,
            kernel_status=result.kernel_status,
            error_code=code[:160],
            error=str(error)[:1000],
            step_count=(
                result.step_count
                if result.step_count is not None
                else result.state.step
            ),
            activation_count=result.activation_count,
            interaction_count=result.interaction_count,
            usage=usage if isinstance(usage, dict) else {"value": usage},
            final_output=output,
            artifact_namespace=str(result.artifact_namespace)[:256],
        )


class StudioRunRecordV1(StudioModel):
    """Internal storage-neutral Run record with the full immutable snapshot."""

    run_id: str
    client_request_id: str
    request_fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    request: CreateStudioRunRequestV1
    snapshot: RunSnapshotV1
    lifecycle: StudioRunLifecycle
    cancellation_requested: StrictBool = False
    process_owner_id: str = ""
    accepted_at: int = Field(ge=0)
    started_at: int | None = Field(default=None, ge=0)
    updated_at: int = Field(ge=0)
    terminal_at: int | None = Field(default=None, ge=0)
    result: StudioRunResultSummaryV1 | None = None
    replay_availability: RunEvidenceAvailability = (
        RunEvidenceAvailability.NOT_CAPTURED
    )
    replay_error_code: str = ""
    storage_warnings: tuple[str, ...] = ()

    @field_validator("run_id")
    @classmethod
    def _valid_run_id(cls, value: str) -> str:
        """Validate generated Run identity.

        Args:
            value (str): Candidate Run identity.

        Raises:
            ValueError: Identity does not use the stable Run form.

        Returns:
            str: Validated Run identity.
        """
        if not _RUN_ID.fullmatch(value):
            raise ValueError("invalid Studio Run identity")
        return value

    @model_validator(mode="after")
    def _terminal_shape(self) -> "StudioRunRecordV1":
        """Keep terminal timestamps and result availability consistent.

        Args:
            None.

        Raises:
            ValueError: Lifecycle and terminal fields disagree.

        Returns:
            StudioRunRecordV1: Validated record.
        """
        if self.lifecycle is StudioRunLifecycle.TERMINAL:
            if self.terminal_at is None or self.result is None:
                raise ValueError("terminal Run requires timestamp and result")
        elif self.terminal_at is not None or self.result is not None:
            raise ValueError("non-terminal Run cannot contain terminal result")
        return self


class StudioRunResourceV1(StudioModel):
    """Public Run resource without graph bodies or storage implementation data."""

    schema_version: Literal[1] = 1
    run_id: str
    client_request_id: str
    agent_id: str
    revision_id: str
    canonical_hash: str
    task: StudioRunTaskV1
    device_profile_id: str
    lifecycle: StudioRunLifecycle
    cancellation_requested: StrictBool
    result_availability: RunEvidenceAvailability
    result: StudioRunResultSummaryV1 | None = None
    replay_availability: RunEvidenceAvailability
    event_high_water_mark: int = Field(default=0, ge=0)
    accepted_at: int
    started_at: int | None = None
    updated_at: int
    terminal_at: int | None = None
    storage_warnings: tuple[str, ...] = ()

    @classmethod
    def from_record(
        cls,
        record: StudioRunRecordV1,
        *,
        event_high_water_mark: int = 0,
    ) -> "StudioRunResourceV1":
        """Project an internal record into its safe HTTP-facing representation.

        Args:
            record (StudioRunRecordV1): Internal storage-neutral record.
            event_high_water_mark (int): Last committed journal sequence.

        Raises:
            ValueError: Projected data violates the public DTO.

        Returns:
            StudioRunResourceV1: Public Run resource.
        """
        return cls(
            run_id=record.run_id,
            client_request_id=record.client_request_id,
            agent_id=record.snapshot.agent_id,
            revision_id=record.snapshot.revision_id,
            canonical_hash=record.snapshot.canonical_hash,
            task=record.request.task,
            device_profile_id=record.request.device_profile_id,
            lifecycle=record.lifecycle,
            cancellation_requested=record.cancellation_requested,
            result_availability=(
                RunEvidenceAvailability.AVAILABLE
                if record.result is not None
                else RunEvidenceAvailability.NOT_CAPTURED
            ),
            result=record.result,
            replay_availability=record.replay_availability,
            event_high_water_mark=event_high_water_mark,
            accepted_at=record.accepted_at,
            started_at=record.started_at,
            updated_at=record.updated_at,
            terminal_at=record.terminal_at,
            storage_warnings=record.storage_warnings,
        )


RunEventSource = Literal["service", "runtime", "storage", "result", "replay"]


class StudioRunEventDraftV1(StudioModel):
    """Unsequenced event submitted to the durable Run journal."""

    schema_version: Literal[1] = 1
    event_id: str
    timestamp: float
    source: RunEventSource
    kind: str
    payload: dict[str, Any] = Field(default_factory=dict)
    runtime_sequence: int | None = Field(default=None, ge=1)
    node_path: str = ""
    activation_id: str = ""
    interaction_step: int | None = Field(default=None, ge=0)

    @field_validator("event_id", "kind", "node_path", "activation_id")
    @classmethod
    def _bounded_text(cls, value: str) -> str:
        """Bound event identity and routing text.

        Args:
            value (str): Candidate text.

        Raises:
            ValueError: Required event identity or kind is blank.

        Returns:
            str: Bounded text.
        """
        bounded = str(value)[:256]
        return bounded

    @model_validator(mode="after")
    def _required_identity(self) -> "StudioRunEventDraftV1":
        """Require stable non-empty event identity and kind.

        Args:
            None.

        Raises:
            ValueError: Identity or kind is blank.

        Returns:
            StudioRunEventDraftV1: Validated event draft.
        """
        if not self.event_id or not self.kind:
            raise ValueError("Run event identity and kind are required")
        return self


class StudioRunEventEnvelopeV1(StudioRunEventDraftV1):
    """Persisted event with an independent run-local journal sequence."""

    run_id: str
    sequence: int = Field(ge=1)
    fingerprint: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")


def run_event_fingerprint(draft: StudioRunEventDraftV1) -> str:
    """Hash an unsequenced event for idempotent journal append.

    Args:
        draft (StudioRunEventDraftV1): Strict event draft.

    Raises:
        ValueError: Event cannot be serialized as finite JSON.

    Returns:
        str: SHA-256-prefixed canonical payload digest.
    """
    encoded = json.dumps(
        draft.model_dump(mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def runtime_event_draft(event: RunEvent) -> StudioRunEventDraftV1:
    """Wrap one canonical Runtime event without reusing its sequence domain.

    Args:
        event (RunEvent): Runtime event emitted by RuntimeContext.

    Raises:
        ValueError: Sanitized event violates the journal DTO.

    Returns:
        StudioRunEventDraftV1: Durable journal draft.
    """
    safe = sanitize_runtime_value(event.to_safe_dict()).value
    payload = safe if isinstance(safe, dict) else {"value": safe}
    identity_seed = json.dumps(
        {
            "runtimeSequence": event.sequence,
            "kind": event.kind,
            "nodePath": event.node_path,
            "activationId": event.activation_id,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    identity = hashlib.sha256(identity_seed).hexdigest()[:32]
    return StudioRunEventDraftV1(
        event_id=f"runtime-{identity}",
        timestamp=event.timestamp,
        source="runtime",
        kind=event.kind,
        payload=payload,
        runtime_sequence=event.sequence,
        node_path=event.node_path,
        activation_id=event.activation_id,
        interaction_step=event.interaction_step,
    )


class StudioRunEventPageV1(StudioModel):
    """Bounded continuous page from one Run event journal."""

    schema_version: Literal[1] = 1
    run_id: str
    items: tuple[StudioRunEventEnvelopeV1, ...]
    next_cursor: int = Field(ge=0)
    high_water_mark: int = Field(ge=0)
    terminal: StrictBool


class StudioRunArtifactDescriptorV1(StudioModel):
    """Public metadata for one run-scoped managed artifact."""

    schema_version: Literal[1] = 1
    artifact_id: str
    kind: str
    availability: RunEvidenceAvailability
    content_type: str = ""
    size: int = Field(default=0, ge=0)
    original_size: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    provenance: str = ""
    hidden: StrictBool = False
    causal_identity: str = ""

    @field_validator("artifact_id")
    @classmethod
    def _valid_artifact_id(cls, value: str) -> str:
        """Validate opaque artifact identity.

        Args:
            value (str): Candidate identity.

        Raises:
            ValueError: Identity is not opaque artifact form.

        Returns:
            str: Validated identity.
        """
        if not _ARTIFACT_ID.fullmatch(value):
            raise ValueError("invalid Studio Run artifact identity")
        return value

    @model_validator(mode="after")
    def _readable_shape(self) -> "StudioRunArtifactDescriptorV1":
        """Require integrity metadata for readable artifact states.

        Args:
            None.

        Raises:
            ValueError: Readable content has no media type or hash.

        Returns:
            StudioRunArtifactDescriptorV1: Validated descriptor.
        """
        if self.availability in {
            RunEvidenceAvailability.AVAILABLE,
            RunEvidenceAvailability.REDACTED,
            RunEvidenceAvailability.TRUNCATED,
        } and (not self.content_type or not self.sha256):
            raise ValueError("readable artifact requires content type and hash")
        return self


class StudioRunArtifactRecordV1(StudioModel):
    """Internal descriptor plus managed relative storage reference."""

    run_id: str
    descriptor: StudioRunArtifactDescriptorV1
    storage_ref: str


class DebugEvidenceReferenceV1(StudioModel):
    """Safe browser-facing reference to one activation-scoped artifact."""

    schema_version: Literal[1] = 1
    kind: str = Field(min_length=1, max_length=160)
    artifact_id: str | None = None
    availability: RunEvidenceAvailability
    content_type: str = Field(default="", max_length=256)
    size: int = Field(default=0, ge=0)
    original_size: int | None = Field(default=None, ge=0)
    sha256: str | None = Field(default=None, pattern=r"^sha256:[0-9a-f]{64}$")
    provenance: str = Field(default="", max_length=256)
    causal_identity: str = Field(default="", max_length=256)
    hidden: StrictBool = False

    @field_validator("artifact_id")
    @classmethod
    def _valid_optional_artifact_id(cls, value: str | None) -> str | None:
        """Validate an optional opaque artifact identity.

        Args:
            value (str | None): Candidate browser artifact identity.

        Raises:
            ValueError: Identity is present but not an opaque artifact ID.

        Returns:
            str | None: Validated identity or absence marker.
        """
        if value is not None and not _ARTIFACT_ID.fullmatch(value):
            raise ValueError("invalid Studio Run artifact identity")
        return value

    @model_validator(mode="after")
    def _safe_reference_shape(self) -> "DebugEvidenceReferenceV1":
        """Keep readable references complete and hidden evidence non-addressable.

        Args:
            None.

        Raises:
            ValueError: Reference metadata could imply an unsafe readable shape.

        Returns:
            DebugEvidenceReferenceV1: Validated browser-facing reference.
        """
        readable = self.availability in {
            RunEvidenceAvailability.AVAILABLE,
            RunEvidenceAvailability.REDACTED,
            RunEvidenceAvailability.TRUNCATED,
        }
        if readable and (
            self.hidden
            or self.artifact_id is None
            or not self.content_type
            or not self.sha256
        ):
            raise ValueError(
                "readable debug evidence requires an opaque ID, media type, and hash"
            )
        if self.availability is RunEvidenceAvailability.HIDDEN and (
            not self.hidden or self.artifact_id is not None
        ):
            raise ValueError(
                "hidden debug evidence must not expose a browser artifact identity"
            )
        return self

    @classmethod
    def from_descriptor(
        cls,
        descriptor: StudioRunArtifactDescriptorV1,
        *,
        expose_artifact_id: bool = True,
    ) -> "DebugEvidenceReferenceV1":
        """Project a managed descriptor into safe browser-facing metadata.

        Args:
            descriptor (StudioRunArtifactDescriptorV1): Persisted descriptor.
            expose_artifact_id (bool): Whether ordinary artifact reads are allowed.

        Raises:
            ValueError: Descriptor and exposure policy form an invalid reference.

        Returns:
            DebugEvidenceReferenceV1: Detached typed evidence reference.
        """
        visible = expose_artifact_id and not descriptor.hidden
        return cls(
            kind=descriptor.kind,
            artifact_id=descriptor.artifact_id if visible else None,
            availability=(
                descriptor.availability
                if visible
                else RunEvidenceAvailability.HIDDEN
            ),
            content_type=descriptor.content_type if visible else "",
            size=descriptor.size if visible else 0,
            original_size=descriptor.original_size if visible else None,
            sha256=descriptor.sha256 if visible else None,
            provenance=descriptor.provenance,
            causal_identity=descriptor.causal_identity,
            hidden=not visible,
        )


class DebugPayloadEnvelopeV1(StudioModel):
    """Versioned activation-scoped component debug evidence."""

    schema_version: Literal[1] = 1
    debug_id: str
    run_id: str
    node_path: str
    activation_id: str
    component_identity: str
    role: str
    stage: Literal["start", "complete", "fail"]
    task: Any = None
    input_summary: Any = None
    output_summary: Any = None
    duration_ms: float | None = Field(default=None, ge=0)
    error: str = ""
    usage: dict[str, Any] = Field(default_factory=dict)
    artifact_ids: tuple[str, ...] = ()
    evidence_refs: dict[str, DebugEvidenceReferenceV1] = Field(
        default_factory=dict
    )
    availability: dict[str, RunEvidenceAvailability] = Field(default_factory=dict)
    diagnostics: tuple[str, ...] = ()


__all__ = [
    "CreateStudioRunRequestV1",
    "DebugEvidenceReferenceV1",
    "DebugPayloadEnvelopeV1",
    "RunEvidenceAvailability",
    "RunSnapshotV1",
    "StudioRunArtifactDescriptorV1",
    "StudioRunArtifactRecordV1",
    "StudioRunEventDraftV1",
    "StudioRunEventEnvelopeV1",
    "StudioRunEventPageV1",
    "StudioRunLifecycle",
    "StudioRunRecordV1",
    "StudioRunResourceV1",
    "StudioRunResultSummaryV1",
    "StudioRunTaskV1",
    "canonical_run_request_fingerprint",
    "run_event_fingerprint",
    "runtime_event_draft",
]
