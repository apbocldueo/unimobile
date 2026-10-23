"""Strict durable DTOs for Stage 5.2A Benchmark Experiment resources."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any, Literal

from pydantic import (
    Field,
    StrictBool,
    StrictInt,
    field_serializer,
    field_validator,
    model_validator,
)

from zhixing.benchmark import (
    BenchmarkOutcome,
    BenchmarkPlan,
    BenchmarkStageStatus,
    ExperimentProtocol,
)
from zhixing.components import RunStatus
from zhixing.benchmark.identity import canonical_hash

from .benchmark_models import (
    StudioBenchmarkPreviewRequestV1,
    StudioPreviewExecutionLimitsV1,
    StudioPreviewScheduleEntryV1,
    _protocol_from_browser,
    _protocol_to_browser,
)
from .models import StudioModel
from .evidence_origin import StudioExecutionEvidenceOriginV1
from .run_models import RunSnapshotV1
from .run_safety import SanitizationPolicy, sanitize_runtime_value
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .benchmark_publication_models import (
        StudioBenchmarkArtifactDescriptorV1,
        StudioBenchmarkPublicationDiagnosticV1,
    )


EXPERIMENT_SNAPSHOT_MAX_BYTES = 2 * 1024 * 1024
JAVASCRIPT_SAFE_INTEGER_MAX = 9_007_199_254_740_991
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_EXPERIMENT_ID = re.compile(r"^experiment-[a-f0-9]{32}$")
_TASK_RUN_ID = re.compile(r"^task-run-[a-f0-9]{32}$")
_EVENT_ID = re.compile(r"^benchmark-event-[a-f0-9]{32}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")


class StudioBenchmarkExperimentLifecycle(str, Enum):
    """Service lifecycle independent from Agent and Benchmark outcomes."""

    ACCEPTED = "accepted"
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    FINALIZING = "finalizing"
    TERMINAL = "terminal"


class StudioBenchmarkExperimentTerminalReason(str, Enum):
    """Explicit Experiment reason stored only for terminal resources."""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class StudioBenchmarkExperimentHistoryFilterV1(StudioModel):
    """Exact immutable query identity for durable Experiment history."""

    schema_version: Literal[1] = 1
    lifecycle: StudioBenchmarkExperimentLifecycle | None = None
    catalog_entry_id: str | None = None
    agent_id: str | None = None
    accepted_from: StrictInt | None = Field(
        default=None,
        ge=0,
        le=JAVASCRIPT_SAFE_INTEGER_MAX,
    )
    accepted_before: StrictInt | None = Field(
        default=None,
        ge=0,
        le=JAVASCRIPT_SAFE_INTEGER_MAX,
    )

    @field_validator("catalog_entry_id", "agent_id")
    @classmethod
    def _stable_filter_identity(cls, value: str | None) -> str | None:
        """Validate one optional exact Catalog or Agent identity.

        Args:
            value: Candidate stable identity or ``None``.

        Raises:
            ValueError: Identity syntax is unsafe or unsupported.

        Returns:
            Validated exact identity or ``None``.
        """
        if value is None:
            return None
        if not isinstance(value, str) or _STABLE_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark history filter identity")
        return value

    @model_validator(mode="after")
    def _half_open_time_range(
        self,
    ) -> "StudioBenchmarkExperimentHistoryFilterV1":
        """Require a non-empty half-open acceptance interval when bounded.

        Raises:
            ValueError: Both bounds exist and do not satisfy ``from < before``.

        Returns:
            Validated immutable filter identity.
        """
        if (
            self.accepted_from is not None
            and self.accepted_before is not None
            and self.accepted_from >= self.accepted_before
        ):
            raise ValueError(
                "Benchmark history acceptedFrom must precede acceptedBefore"
            )
        return self

    def canonical_identity(self) -> dict[str, object]:
        """Serialize only active filters into their canonical public identity.

        Returns:
            Camel-case finite JSON identity used to bind continuation cursors.
        """
        value = self.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
            exclude={"schema_version"},
        )
        return dict(sorted(value.items()))

    def fingerprint(self) -> str:
        """Return the non-reversible canonical filter fingerprint.

        Returns:
            Stable SHA-256 identity for exact cursor/query matching.
        """
        return canonical_hash(self.canonical_identity())

    def is_empty(self) -> bool:
        """Return whether the query has no active scalar filters.

        Returns:
            ``True`` only for the backward-compatible unfiltered query.
        """
        return not self.canonical_identity()


class StudioBenchmarkTaskRunLifecycle(str, Enum):
    """TaskRun service lifecycle independent from Benchmark outcome."""

    SCHEDULED = "scheduled"
    PREPARING = "preparing"
    EVALUATING = "evaluating"
    CLEANING_UP = "cleaning_up"
    # Retained only so schema-4 rows can be read without inventing new facts.
    STARTING = "starting"
    RUNNING = "running"
    CANCELLING = "cancelling"
    TERMINAL = "terminal"


class StudioBenchmarkTaskRunTerminalReason(str, Enum):
    """Explicit terminal reason for one planned TaskRun."""

    COMPLETED = "completed"
    CANCELLED_BEFORE_START = "cancelled_before_start"
    CANCELLED = "cancelled"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class StudioBenchmarkAvailability(str, Enum):
    """Availability that never invents an unproduced Benchmark fact."""

    PENDING = "pending"
    NOT_PRODUCED = "not_produced"
    AVAILABLE = "available"
    FAILED = "failed"


class StudioBenchmarkEventSource(str, Enum):
    """Typed producer identity for one durable Experiment journal fact."""

    SERVICE = "service"
    WORKER = "worker"
    CORE = "core"
    AGENT = "agent"


class StudioBenchmarkRecoveryDecision(str, Enum):
    """Conservative startup decision for one stale Experiment."""

    REQUEUE = "requeue"
    INTERRUPT = "interrupt"
    PUBLICATION_ONLY = "publication_only"
    FINALIZE_ONLY = "finalize_only"


class StudioBenchmarkRecoveryTaskRunV1(StudioModel):
    """Bounded TaskRun facts needed to classify startup recovery."""

    schema_version: Literal[1] = 1
    task_run_id: str
    lifecycle: StudioBenchmarkTaskRunLifecycle
    terminal_reason: StudioBenchmarkTaskRunTerminalReason | None = None
    result_availability: StudioBenchmarkAvailability
    replay_availability: StudioBenchmarkAvailability

    @field_validator("task_run_id")
    @classmethod
    def _task_run_identity(cls, value: str) -> str:
        """Validate one stable TaskRun identity.

        Args:
            value: Candidate opaque identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _TASK_RUN_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark recovery TaskRun identity")
        return value


class StudioBenchmarkRecoveryCandidateV1(StudioModel):
    """Database-neutral stale aggregate projection for startup recovery."""

    schema_version: Literal[1] = 1
    experiment_id: str
    previous_lifecycle: StudioBenchmarkExperimentLifecycle
    recovery_token: str
    prior_event_high_water_mark: int = Field(ge=0)
    accepted_at: int = Field(ge=0)
    cancellation_requested: StrictBool
    publication_committed: StrictBool
    task_runs: tuple[StudioBenchmarkRecoveryTaskRunV1, ...] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("experiment_id")
    @classmethod
    def _experiment_identity(cls, value: str) -> str:
        """Validate one stable Experiment identity.

        Args:
            value: Candidate opaque identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark recovery Experiment identity")
        return value

    @field_validator("recovery_token")
    @classmethod
    def _recovery_digest(cls, value: str) -> str:
        """Require a non-reversible canonical recovery token.

        Args:
            value: Candidate SHA-256 token.

        Raises:
            ValueError: Token syntax is invalid.

        Returns:
            Validated token.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid Benchmark recovery token")
        return value


class StudioBenchmarkRecoveryCandidatePageV1(StudioModel):
    """Deterministic bounded page of stale recovery candidates."""

    schema_version: Literal[1] = 1
    items: tuple[StudioBenchmarkRecoveryCandidateV1, ...] = Field(
        max_length=100,
    )
    next_cursor: str | None = Field(default=None, max_length=1024)


class StudioBenchmarkRecoveryAttemptV1(StudioModel):
    """Safe versioned recovery decision persisted to the event journal."""

    schema_version: Literal[1] = 1
    attempt_id: str
    experiment_id: str
    previous_lifecycle: StudioBenchmarkExperimentLifecycle
    decision: StudioBenchmarkRecoveryDecision
    affected_task_run_ids: tuple[str, ...] = Field(max_length=100)
    prior_event_high_water_mark: int = Field(ge=0)

    @field_validator("attempt_id")
    @classmethod
    def _attempt_digest(cls, value: str) -> str:
        """Validate a non-reversible stable attempt identity.

        Args:
            value: Candidate SHA-256 attempt identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid Benchmark recovery attempt identity")
        return value

    @field_validator("experiment_id")
    @classmethod
    def _attempt_experiment_identity(cls, value: str) -> str:
        """Validate the affected Experiment identity.

        Args:
            value: Candidate opaque identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid recovery attempt Experiment identity")
        return value

    @field_validator("affected_task_run_ids")
    @classmethod
    def _affected_task_identities(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Validate and deduplicate affected TaskRun identities.

        Args:
            value: Candidate stable TaskRun identities.

        Raises:
            ValueError: An identity is invalid or duplicated.

        Returns:
            Validated identities in supplied order.
        """
        if len(set(value)) != len(value):
            raise ValueError("recovery TaskRun identities must be unique")
        if any(_TASK_RUN_ID.fullmatch(item) is None for item in value):
            raise ValueError("invalid affected recovery TaskRun identity")
        return value


class StudioBenchmarkRecoverySummaryV1(StudioModel):
    """Bounded process-local summary of one completed startup scan."""

    schema_version: Literal[1] = 1
    scanned: int = Field(default=0, ge=0)
    requeued: int = Field(default=0, ge=0)
    interrupted: int = Field(default=0, ge=0)
    publication_only: int = Field(default=0, ge=0)
    finalize_only: int = Field(default=0, ge=0)


class StudioBenchmarkTaskPhaseV1(StudioModel):
    """Bounded persisted projection of one Benchmark lifecycle phase."""

    phase: str = Field(min_length=1, max_length=128)
    status: BenchmarkStageStatus
    duration_ms: float = Field(default=0.0, ge=0)
    error_code: str = Field(default="", max_length=256)
    message: str = Field(default="", max_length=1000)
    evidence: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: tuple[str, ...] = Field(default_factory=tuple, max_length=50)


class StudioBenchmarkEvaluationV1(StudioModel):
    """Bounded recursive Evaluation Tree projection without live evaluators."""

    path: str = Field(min_length=1, max_length=512)
    name: str = Field(min_length=1, max_length=256)
    status: BenchmarkStageStatus
    is_pass: bool | None = None
    reason: str = Field(default="", max_length=1000)
    score: float | None = None
    token: float | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    children: tuple["StudioBenchmarkEvaluationV1", ...] = Field(
        default_factory=tuple,
        max_length=50,
    )


class StudioBenchmarkTaskResultV1(StudioModel):
    """Safe normalized TaskResult stored inline by the Stage 5.2B service."""

    schema_version: Literal[1] = 1
    planned_task_run_id: str
    core_task_run_id: str = Field(min_length=1, max_length=160)
    agent_run_id: str | None = Field(default=None, max_length=160)
    agent_id: str = Field(min_length=1, max_length=160)
    agent_revision_id: str = Field(min_length=1, max_length=160)
    task_id: str = Field(min_length=1, max_length=160)
    repeat: int = Field(ge=0)
    schedule_order: int = Field(ge=0)
    service_terminal_reason: StudioBenchmarkTaskRunTerminalReason
    agent_graph_identity: str
    benchmark_plan_identity: str
    experiment_protocol_identity: str
    task_instance_identity: str
    agent_status: RunStatus | None = None
    benchmark_outcome: BenchmarkOutcome
    phases: tuple[StudioBenchmarkTaskPhaseV1, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    evaluation: StudioBenchmarkEvaluationV1 | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    fairness_warnings: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=50,
    )
    logical_artifact_refs: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    diagnostics: tuple[str, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    evidence_origin: StudioExecutionEvidenceOriginV1 = Field(
        default_factory=StudioExecutionEvidenceOriginV1
    )

    @field_validator("planned_task_run_id")
    @classmethod
    def _planned_task_run_identity(cls, value: str) -> str:
        """Require the stable public planned TaskRun identity.

        Args:
            value: Candidate planned resource identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated planned TaskRun identity.
        """
        if _TASK_RUN_ID.fullmatch(value) is None:
            raise ValueError("invalid planned Benchmark TaskRun identity")
        return value

    @field_validator(
        "agent_graph_identity",
        "benchmark_plan_identity",
        "experiment_protocol_identity",
        "task_instance_identity",
    )
    @classmethod
    def _result_digest(cls, value: str) -> str:
        """Require canonical identities in persisted result provenance.

        Args:
            value: Candidate SHA-256 identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("TaskResult provenance must use SHA-256 identities")
        return value


class StudioBenchmarkSourceSnapshotV1(StudioModel):
    """Safe Catalog source identity without a host filesystem locator."""

    source_id: str
    source_kind: Literal["package", "catalog", "installed"]
    relative_key: str = Field(min_length=1, max_length=512)
    catalog_entry_id: str
    package_identity: str
    package_content_identity: str
    benchmark_plan_identity: str
    experiment_protocol_identity: str

    @field_validator(
        "source_id",
        "catalog_entry_id",
        "package_identity",
    )
    @classmethod
    def _bounded_identity(cls, value: str) -> str:
        """Require one bounded non-path source identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is blank, oversized, or path-shaped.

        Returns:
            Validated identity.
        """
        if not value or len(value) > 512:
            raise ValueError("Benchmark source identity must be bounded")
        if value.startswith(("/", "\\\\")) or re.match(
            r"^[A-Za-z]:[\\/]", value
        ):
            raise ValueError("host paths are not source identities")
        return value

    @field_validator(
        "package_content_identity",
        "benchmark_plan_identity",
        "experiment_protocol_identity",
    )
    @classmethod
    def _digest_identity(cls, value: str) -> str:
        """Require a canonical SHA-256 identity.

        Args:
            value: Candidate canonical identity.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("canonical identity must be a SHA-256 digest")
        return value


class ExperimentDefinitionSnapshotV1(StudioModel):
    """Complete immutable Stage 5.2A definition accepted by the service."""

    schema_version: Literal[1] = 1
    preview_fingerprint: str
    snapshot_fingerprint: str
    source: StudioBenchmarkSourceSnapshotV1
    agent_snapshots: tuple[RunSnapshotV1, ...] = Field(min_length=1)
    benchmark_plan: BenchmarkPlan
    protocol: ExperimentProtocol
    split: str = Field(min_length=1, max_length=128)
    task_ids: tuple[str, ...] = Field(min_length=1)
    schedule: tuple[StudioPreviewScheduleEntryV1, ...] = Field(min_length=1)
    device_profile_id: str
    execution_limits: StudioPreviewExecutionLimitsV1

    @field_validator("protocol", mode="before")
    @classmethod
    def _parse_protocol(cls, value: object) -> object:
        """Translate browser aliases before formal Protocol validation.

        Args:
            value: Stored or browser-facing Protocol body.

        Returns:
            Mapping prepared for formal Protocol parsing.
        """
        return _protocol_from_browser(value)

    @field_serializer("protocol")
    def _serialize_protocol(
        self,
        value: ExperimentProtocol,
    ) -> dict[str, Any]:
        """Serialize the formal Protocol with browser field aliases.

        Args:
            value: Validated Experiment Protocol.

        Returns:
            Camel-case Protocol mapping.
        """
        return _protocol_to_browser(value)

    @field_validator("preview_fingerprint", "snapshot_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        """Validate a canonical snapshot digest.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid definition fingerprint")
        return value

    @field_validator("device_profile_id")
    @classmethod
    def _profile_identity(cls, value: str) -> str:
        """Reject malformed or raw-serial-like profile identities.

        Args:
            value: Candidate safe profile identity.

        Raises:
            ValueError: Identity is unsafe.

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
            raise ValueError("raw device serial is not accepted")
        return value


class StudioBenchmarkExperimentCreateRequestV1(StudioModel):
    """Idempotent request containing the complete preview definition."""

    schema_version: Literal[1] = 1
    client_request_id: str
    preview_fingerprint: str
    definition: StudioBenchmarkPreviewRequestV1

    @field_validator("client_request_id")
    @classmethod
    def _client_identity(cls, value: str) -> str:
        """Validate a bounded stable client request identity.

        Args:
            value: Candidate idempotency identity.

        Raises:
            ValueError: Identity is unstable.

        Returns:
            Validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("client request identity must be stable")
        return value

    @field_validator("preview_fingerprint")
    @classmethod
    def _preview_digest(cls, value: str) -> str:
        """Validate the submitted preview fingerprint.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid preview fingerprint")
        return value


def canonical_experiment_request_fingerprint(
    request: StudioBenchmarkExperimentCreateRequestV1,
) -> str:
    """Hash create content while excluding the idempotency identity.

    Args:
        request: Strict complete create request.

    Raises:
        TypeError: Request content is not JSON-compatible.
        ValueError: Request content contains non-finite values.

    Returns:
        SHA-256-prefixed canonical content fingerprint.
    """
    payload = {
        "schemaVersion": request.schema_version,
        "previewFingerprint": request.preview_fingerprint,
        "definition": request.definition.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def canonical_snapshot_json(snapshot: ExperimentDefinitionSnapshotV1) -> str:
    """Serialize and enforce the Stage 5.2A inline snapshot limit.

    Args:
        snapshot: Complete strict immutable definition snapshot.

    Raises:
        ValueError: Canonical UTF-8 JSON exceeds 2 MiB or is non-finite.
        TypeError: Snapshot is not JSON-compatible.

    Returns:
        Deterministic finite JSON text.
    """
    text = json.dumps(
        snapshot.model_dump(mode="json", by_alias=True, exclude_none=True),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    if len(text.encode("utf-8")) > EXPERIMENT_SNAPSHOT_MAX_BYTES:
        raise ValueError("Benchmark Experiment definition snapshot is too large")
    return text


class StudioBenchmarkExperimentCancellationV1(StudioModel):
    """One safe persisted cancellation request."""

    schema_version: Literal[1] = 1
    client_request_id: str
    requested_at: int = Field(ge=0)
    reason_code: Literal["user_requested"] = "user_requested"

    @field_validator("client_request_id")
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Validate cancellation idempotency identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is unstable.

        Returns:
            Validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("cancellation request identity must be stable")
        return value


class StudioBenchmarkExperimentCancelRequestV1(StudioModel):
    """Versioned cooperative cancellation command for non-terminal work."""

    schema_version: Literal[1] = 1
    client_request_id: str
    reason_code: Literal["user_requested"] = "user_requested"

    @field_validator("client_request_id")
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Validate cancellation idempotency identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is unstable.

        Returns:
            Validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("cancellation request identity must be stable")
        return value


class StudioBenchmarkTaskRunRecordV1(StudioModel):
    """Storage-neutral stable planned TaskRun record."""

    schema_version: Literal[1] = 1
    task_run_id: str
    experiment_id: str
    planned_entry_id: str
    order: int = Field(ge=0)
    agent_id: str
    revision_id: str
    task_id: str
    repeat: int = Field(ge=0)
    derived_seed: int
    lifecycle: StudioBenchmarkTaskRunLifecycle
    terminal_reason: StudioBenchmarkTaskRunTerminalReason | None = None
    process_owner_id: str = Field(default="", max_length=160)
    core_task_run_id: str | None = Field(default=None, max_length=160)
    agent_run_id: str | None = Field(default=None, max_length=160)
    task_instance_identity: str | None = None
    phases: tuple[StudioBenchmarkTaskPhaseV1, ...] = Field(
        default_factory=tuple,
        max_length=32,
    )
    agent_status: RunStatus | None = None
    benchmark_outcome: BenchmarkOutcome | None = None
    evaluation: StudioBenchmarkEvaluationV1 | None = None
    task_instance_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    phase_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    agent_status_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    outcome_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    result_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    evaluation_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    replay_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    report_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    trajectory_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    bundle_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    replay_id: str | None = None
    artifacts: tuple["StudioBenchmarkArtifactDescriptorV1", ...] = Field(
        default_factory=tuple,
        max_length=2000,
    )
    publication_diagnostics: tuple[
        "StudioBenchmarkPublicationDiagnosticV1", ...
    ] = Field(default_factory=tuple, max_length=100)
    links: "StudioBenchmarkTaskRunLinksV1 | None" = None
    result: StudioBenchmarkTaskResultV1 | None = None
    result_fingerprint: str | None = None
    created_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    started_at: int | None = Field(default=None, ge=0)
    evaluating_at: int | None = Field(default=None, ge=0)
    cleaning_up_at: int | None = Field(default=None, ge=0)
    terminal_at: int | None = Field(default=None, ge=0)

    @field_validator("task_run_id")
    @classmethod
    def _task_run_identity(cls, value: str) -> str:
        """Validate an opaque TaskRun identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _TASK_RUN_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark TaskRun identity")
        return value

    @field_validator("experiment_id")
    @classmethod
    def _experiment_identity(cls, value: str) -> str:
        """Validate an opaque Experiment identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark Experiment identity")
        return value

    @model_validator(mode="after")
    def _terminal_shape(self) -> "StudioBenchmarkTaskRunRecordV1":
        """Keep terminal reason and timestamp consistent with lifecycle.

        Raises:
            ValueError: Terminal fields disagree with lifecycle.

        Returns:
            Validated record.
        """
        if self.lifecycle is StudioBenchmarkTaskRunLifecycle.TERMINAL:
            if self.terminal_reason is None or self.terminal_at is None:
                raise ValueError("terminal TaskRun requires reason and timestamp")
        elif self.terminal_reason is not None or self.terminal_at is not None:
            raise ValueError("non-terminal TaskRun cannot have terminal facts")
        if (self.result is None) != (self.result_fingerprint is None):
            raise ValueError("TaskRun result and fingerprint must be stored together")
        if (
            self.result is not None
            and self.result.planned_task_run_id != self.task_run_id
        ):
            raise ValueError("TaskResult planned identity does not match TaskRun")
        if self.result_availability is StudioBenchmarkAvailability.AVAILABLE:
            if self.result is None:
                raise ValueError("available TaskRun result requires result facts")
        elif self.result is not None:
            raise ValueError("non-available TaskRun cannot expose a result")
        availability_facts = (
            (
                self.task_instance_availability,
                self.task_instance_identity is not None,
                "TaskInstance",
            ),
            (self.phase_availability, bool(self.phases), "phase"),
            (
                self.agent_status_availability,
                self.agent_status is not None,
                "Agent status",
            ),
        )
        for availability, present, label in availability_facts:
            if availability is StudioBenchmarkAvailability.AVAILABLE and not present:
                raise ValueError(f"available {label} requires persisted facts")
            if availability is not StudioBenchmarkAvailability.AVAILABLE and present:
                raise ValueError(f"non-available {label} cannot expose facts")
        if (
            self.replay_availability is StudioBenchmarkAvailability.AVAILABLE
        ) != (self.replay_id is not None):
            raise ValueError(
                "available Benchmark Replay requires an explicit identity"
            )
        return self


class StudioBenchmarkExperimentRecordV1(StudioModel):
    """Storage-neutral durable Benchmark Experiment aggregate root."""

    schema_version: Literal[1] = 1
    experiment_id: str
    client_request_id: str
    request_fingerprint: str
    request: StudioBenchmarkExperimentCreateRequestV1
    definition: ExperimentDefinitionSnapshotV1
    lifecycle: StudioBenchmarkExperimentLifecycle
    terminal_reason: StudioBenchmarkExperimentTerminalReason | None = None
    cancellation: StudioBenchmarkExperimentCancellationV1 | None = None
    process_owner_id: str = Field(default="", max_length=160)
    outcome_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    report_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    replay_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    trajectory_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    bundle_availability: StudioBenchmarkAvailability = (
        StudioBenchmarkAvailability.NOT_PRODUCED
    )
    report_artifact_id: str | None = None
    bundle_artifact_id: str | None = None
    publication_diagnostics: tuple[
        "StudioBenchmarkPublicationDiagnosticV1", ...
    ] = Field(default_factory=tuple, max_length=100)
    event_high_water_mark: int = Field(ge=0)
    accepted_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    terminal_at: int | None = Field(default=None, ge=0)

    @field_validator("experiment_id")
    @classmethod
    def _experiment_identity(cls, value: str) -> str:
        """Validate an opaque Experiment identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark Experiment identity")
        return value

    @field_validator("request_fingerprint")
    @classmethod
    def _request_digest(cls, value: str) -> str:
        """Validate the persisted canonical request fingerprint.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid request fingerprint")
        return value

    @model_validator(mode="after")
    def _terminal_shape(self) -> "StudioBenchmarkExperimentRecordV1":
        """Keep terminal fields and lifecycle consistent.

        Raises:
            ValueError: Terminal fields disagree with lifecycle.

        Returns:
            Validated record.
        """
        if self.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL:
            if self.terminal_reason is None or self.terminal_at is None:
                raise ValueError(
                    "terminal Experiment requires reason and timestamp"
                )
        elif self.terminal_reason is not None or self.terminal_at is not None:
            raise ValueError("non-terminal Experiment cannot have terminal facts")
        return self


class StudioBenchmarkEventDraftV1(StudioModel):
    """Unsequenced aggregate event submitted to the durable journal."""

    schema_version: Literal[1] = 1
    event_id: str
    timestamp: int = Field(ge=0)
    source: StudioBenchmarkEventSource = StudioBenchmarkEventSource.SERVICE
    kind: str = Field(min_length=1, max_length=160)
    task_run_id: str | None = None
    source_sequence: int | None = Field(default=None, ge=1)
    phase: str = Field(default="", max_length=128)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id")
    @classmethod
    def _event_identity(cls, value: str) -> str:
        """Validate a stable opaque event identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EVENT_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark event identity")
        return value

    @field_validator("payload", mode="before")
    @classmethod
    def _safe_bounded_payload(cls, value: object) -> dict[str, Any]:
        """Sanitize and bound one durable event payload before persistence.

        Args:
            value: Candidate runtime or service payload.

        Raises:
            ValueError: Sanitized payload is not a mapping or exceeds 64 KiB.

        Returns:
            Safe bounded JSON mapping.
        """
        sanitized = sanitize_runtime_value(
            value,
            policy=SanitizationPolicy(
                max_depth=6,
                max_members=50,
                max_text=4000,
                max_total_text=48 * 1024,
            ),
        )
        if not isinstance(sanitized.value, dict):
            raise ValueError("Benchmark event payload must be a mapping")
        encoded = json.dumps(
            sanitized.value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        if len(encoded) > 64 * 1024:
            raise ValueError("Benchmark event payload exceeds 64 KiB")
        return sanitized.value


class StudioBenchmarkEventEnvelopeV1(StudioBenchmarkEventDraftV1):
    """Persisted event with an Experiment-local journal sequence."""

    experiment_id: str
    sequence: int = Field(ge=1)
    fingerprint: str

    @field_validator("fingerprint")
    @classmethod
    def _event_digest(cls, value: str) -> str:
        """Validate the canonical event fingerprint.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid Benchmark event fingerprint")
        return value


class StudioBenchmarkEventPageV1(StudioModel):
    """Bounded continuous page from one Benchmark Experiment journal."""

    schema_version: Literal[1] = 1
    experiment_id: str
    items: tuple[StudioBenchmarkEventEnvelopeV1, ...] = Field(max_length=500)
    next_cursor: int = Field(ge=0)
    high_water_mark: int = Field(ge=0)
    terminal: StrictBool


def benchmark_event_fingerprint(draft: StudioBenchmarkEventDraftV1) -> str:
    """Hash an unsequenced event for identity conflict detection.

    Args:
        draft: Strict event draft.

    Raises:
        ValueError: Event contains non-finite JSON.
        TypeError: Event is not JSON-compatible.

    Returns:
        SHA-256-prefixed canonical event digest.
    """
    encoded = json.dumps(
        draft.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


class StudioBenchmarkExperimentCapabilitiesV1(StudioModel):
    """Truthful composed Benchmark Experiment capability facts for clients."""

    executes: StrictBool = False
    cancel_accepted: Literal[True] = True
    cancel_active: StrictBool = False
    event_stream: StrictBool = False
    replay: StrictBool = False
    reports: StrictBool = False


class StudioBenchmarkExperimentLinksV1(StudioModel):
    """Only links backed by implemented Benchmark Experiment routes."""

    self_link: str = Field(alias="self")
    cancel: str | None = None
    task_runs: str
    artifacts: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    events: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    event_stream: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    report: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    bundle: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class StudioBenchmarkTaskRunLinksV1(StudioModel):
    """Typed links emitted only for implemented and available TaskRun facts."""

    self_link: str = Field(alias="self")
    artifacts: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    replay: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class StudioBenchmarkExperimentResourceV1(StudioModel):
    """Safe public Experiment resource including the immutable definition."""

    schema_version: Literal[1] = 1
    experiment_id: str
    client_request_id: str
    definition: ExperimentDefinitionSnapshotV1
    lifecycle: StudioBenchmarkExperimentLifecycle
    terminal_reason: StudioBenchmarkExperimentTerminalReason | None = None
    cancellation: StudioBenchmarkExperimentCancellationV1 | None = None
    outcome_availability: StudioBenchmarkAvailability
    report_availability: StudioBenchmarkAvailability
    replay_availability: StudioBenchmarkAvailability
    trajectory_availability: StudioBenchmarkAvailability
    bundle_availability: StudioBenchmarkAvailability
    publication_diagnostics: tuple[
        "StudioBenchmarkPublicationDiagnosticV1", ...
    ] = Field(default_factory=tuple, max_length=100)
    event_high_water_mark: int = Field(ge=0)
    accepted_at: int
    updated_at: int
    terminal_at: int | None = None
    capabilities: StudioBenchmarkExperimentCapabilitiesV1 = (
        StudioBenchmarkExperimentCapabilitiesV1()
    )
    links: StudioBenchmarkExperimentLinksV1

    @classmethod
    def from_record(
        cls,
        record: StudioBenchmarkExperimentRecordV1,
        *,
        execution_enabled: bool = False,
        event_transport_enabled: bool = False,
        publication_enabled: bool = False,
    ) -> "StudioBenchmarkExperimentResourceV1":
        """Project one storage-neutral record into the safe HTTP resource.

        Args:
            record: Strict durable Experiment record.
            execution_enabled: Whether this process owns an execution worker.
            event_transport_enabled: Whether public event page and SSE routes
                are fully composed.
            publication_enabled: Whether managed publication, resolver, and
                native Replay routes are fully composed.

        Raises:
            ValueError: Projected values violate the public DTO.

        Returns:
            Safe public Experiment resource.
        """
        base = f"/studio/benchmark-experiments/{record.experiment_id}"
        return cls(
            experiment_id=record.experiment_id,
            client_request_id=record.client_request_id,
            definition=record.definition,
            lifecycle=record.lifecycle,
            terminal_reason=record.terminal_reason,
            cancellation=record.cancellation,
            outcome_availability=record.outcome_availability,
            report_availability=record.report_availability,
            replay_availability=record.replay_availability,
            trajectory_availability=record.trajectory_availability,
            bundle_availability=record.bundle_availability,
            publication_diagnostics=record.publication_diagnostics,
            event_high_water_mark=record.event_high_water_mark,
            accepted_at=record.accepted_at,
            updated_at=record.updated_at,
            terminal_at=record.terminal_at,
            capabilities=StudioBenchmarkExperimentCapabilitiesV1(
                executes=execution_enabled,
                cancel_active=execution_enabled,
                event_stream=event_transport_enabled,
                replay=publication_enabled,
                reports=publication_enabled,
            ),
            links=StudioBenchmarkExperimentLinksV1(
                self_link=base,
                cancel=(
                    f"{base}/cancel"
                    if record.lifecycle
                    is not StudioBenchmarkExperimentLifecycle.TERMINAL
                    else None
                ),
                task_runs=f"{base}/task-runs",
                artifacts=(
                    f"{base}/artifacts" if publication_enabled else None
                ),
                events=(f"{base}/events" if event_transport_enabled else None),
                event_stream=(
                    f"{base}/events/stream"
                    if event_transport_enabled
                    else None
                ),
                report=(
                    f"{base}/report"
                    if publication_enabled
                    and record.report_availability
                    is StudioBenchmarkAvailability.AVAILABLE
                    else None
                ),
                bundle=(
                    f"{base}/bundle"
                    if publication_enabled
                    and record.bundle_availability
                    is StudioBenchmarkAvailability.AVAILABLE
                    else None
                ),
            ),
        )


class StudioBenchmarkExperimentCreateResponseV1(StudioModel):
    """Versioned create wrapper distinguishing new from idempotent retry."""

    schema_version: Literal[1] = 1
    created: StrictBool
    experiment: StudioBenchmarkExperimentResourceV1


class StudioBenchmarkTaskRunPageV1(StudioModel):
    """Stable bounded TaskRun page scoped to one Experiment."""

    schema_version: Literal[1] = 1
    experiment_id: str
    items: tuple[StudioBenchmarkTaskRunRecordV1, ...]
    next_cursor: str | None = None


class StudioBenchmarkExperimentRecordPageV1(StudioModel):
    """Internal bounded page of durable Experiment aggregate records."""

    schema_version: Literal[1] = 1
    items: tuple[StudioBenchmarkExperimentRecordV1, ...] = Field(
        max_length=100
    )
    next_cursor: str | None = None


class StudioBenchmarkHistoryAgentV1(StudioModel):
    """Immutable Agent/revision identity shown in Experiment history."""

    agent_id: str
    revision_id: str


class StudioBenchmarkHistorySourceV1(StudioModel):
    """Immutable Package and Catalog identity shown in Experiment history."""

    catalog_entry_id: str
    package_identity: str
    split: str


class StudioBenchmarkExperimentHistoryLinksV1(StudioModel):
    """Implemented same-service links for one Experiment history item."""

    self_link: str = Field(alias="self")
    task_runs: str
    artifacts: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    report: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )
    bundle: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class StudioBenchmarkExperimentHistoryItemV1(StudioModel):
    """Compact immutable Experiment history summary without its definition."""

    schema_version: Literal[1] = 1
    experiment_id: str
    lifecycle: StudioBenchmarkExperimentLifecycle
    terminal_reason: StudioBenchmarkExperimentTerminalReason | None = None
    source: StudioBenchmarkHistorySourceV1
    agents: tuple[StudioBenchmarkHistoryAgentV1, ...] = Field(
        min_length=1,
        max_length=100,
    )
    planned_task_run_count: int = Field(ge=1)
    outcome_availability: StudioBenchmarkAvailability
    report_availability: StudioBenchmarkAvailability
    replay_availability: StudioBenchmarkAvailability
    trajectory_availability: StudioBenchmarkAvailability
    bundle_availability: StudioBenchmarkAvailability
    accepted_at: int = Field(ge=0)
    updated_at: int = Field(ge=0)
    terminal_at: int | None = Field(default=None, ge=0)
    links: StudioBenchmarkExperimentHistoryLinksV1

    @model_validator(mode="after")
    def _history_shape(self) -> "StudioBenchmarkExperimentHistoryItemV1":
        """Keep terminal facts, availability links, and Agent order coherent.

        Raises:
            ValueError: Summary facts or links contradict each other.

        Returns:
            Validated compact history item.
        """
        terminal = (
            self.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL
        )
        if terminal != (
            self.terminal_reason is not None and self.terminal_at is not None
        ):
            raise ValueError(
                "terminal history lifecycle requires reason and timestamp"
            )
        if self.updated_at < self.accepted_at:
            raise ValueError("history update precedes acceptance")
        if self.terminal_at is not None and self.terminal_at < self.accepted_at:
            raise ValueError("history terminal timestamp precedes acceptance")
        agent_keys = tuple(
            (agent.agent_id, agent.revision_id) for agent in self.agents
        )
        if len(agent_keys) != len(set(agent_keys)):
            raise ValueError("history Agent identities must be unique")
        report_link = self.links.report is not None
        if report_link != (
            self.report_availability is StudioBenchmarkAvailability.AVAILABLE
        ):
            raise ValueError("history report link disagrees with availability")
        bundle_link = self.links.bundle is not None
        if bundle_link != (
            self.bundle_availability is StudioBenchmarkAvailability.AVAILABLE
        ):
            raise ValueError("history bundle link disagrees with availability")
        return self

    @classmethod
    def from_record(
        cls,
        record: StudioBenchmarkExperimentRecordV1,
        *,
        publication_enabled: bool,
    ) -> "StudioBenchmarkExperimentHistoryItemV1":
        """Project one durable Experiment into a compact history summary.

        Args:
            record: Durable Experiment record with immutable definition.
            publication_enabled: Whether reporting routes are composed.

        Raises:
            ValueError: Durable facts cannot form a valid public summary.

        Returns:
            Compact history item without the full definition.
        """
        base = f"/studio/benchmark-experiments/{record.experiment_id}"
        return cls(
            experiment_id=record.experiment_id,
            lifecycle=record.lifecycle,
            terminal_reason=record.terminal_reason,
            source=StudioBenchmarkHistorySourceV1(
                catalog_entry_id=record.definition.source.catalog_entry_id,
                package_identity=record.definition.source.package_identity,
                split=record.definition.split,
            ),
            agents=tuple(
                StudioBenchmarkHistoryAgentV1(
                    agent_id=snapshot.agent_id,
                    revision_id=snapshot.revision_id,
                )
                for snapshot in record.definition.agent_snapshots
            ),
            planned_task_run_count=len(record.definition.schedule),
            outcome_availability=record.outcome_availability,
            report_availability=record.report_availability,
            replay_availability=record.replay_availability,
            trajectory_availability=record.trajectory_availability,
            bundle_availability=record.bundle_availability,
            accepted_at=record.accepted_at,
            updated_at=record.updated_at,
            terminal_at=record.terminal_at,
            links=StudioBenchmarkExperimentHistoryLinksV1(
                self_link=base,
                task_runs=f"{base}/task-runs",
                artifacts=(
                    f"{base}/artifacts" if publication_enabled else None
                ),
                report=(
                    f"{base}/report"
                    if publication_enabled
                    and record.report_availability
                    is StudioBenchmarkAvailability.AVAILABLE
                    else None
                ),
                bundle=(
                    f"{base}/bundle"
                    if publication_enabled
                    and record.bundle_availability
                    is StudioBenchmarkAvailability.AVAILABLE
                    else None
                ),
            ),
        )


class StudioBenchmarkExperimentHistoryPageV1(StudioModel):
    """Newest-first bounded Experiment history page."""

    schema_version: Literal[1] = 1
    items: tuple[StudioBenchmarkExperimentHistoryItemV1, ...] = Field(
        max_length=100
    )
    next_cursor: str | None = None

    @model_validator(mode="after")
    def _stable_order(self) -> "StudioBenchmarkExperimentHistoryPageV1":
        """Require deterministic newest-first item ordering.

        Raises:
            ValueError: Items are duplicated or out of order.

        Returns:
            Validated history page.
        """
        keys = tuple(
            (item.accepted_at, item.experiment_id) for item in self.items
        )
        if len(keys) != len(set(keys)) or tuple(
            sorted(keys, reverse=True)
        ) != keys:
            raise ValueError("history page order is unstable")
        return self


__all__ = [
    "EXPERIMENT_SNAPSHOT_MAX_BYTES",
    "JAVASCRIPT_SAFE_INTEGER_MAX",
    "ExperimentDefinitionSnapshotV1",
    "StudioBenchmarkAvailability",
    "StudioBenchmarkEventDraftV1",
    "StudioBenchmarkEventEnvelopeV1",
    "StudioBenchmarkEventPageV1",
    "StudioBenchmarkEventSource",
    "StudioBenchmarkEvaluationV1",
    "StudioBenchmarkExperimentCancelRequestV1",
    "StudioBenchmarkExperimentCancellationV1",
    "StudioBenchmarkExperimentCapabilitiesV1",
    "StudioBenchmarkExperimentCreateRequestV1",
    "StudioBenchmarkExperimentCreateResponseV1",
    "StudioBenchmarkExperimentHistoryFilterV1",
    "StudioBenchmarkExperimentHistoryItemV1",
    "StudioBenchmarkExperimentHistoryLinksV1",
    "StudioBenchmarkExperimentHistoryPageV1",
    "StudioBenchmarkExperimentLifecycle",
    "StudioBenchmarkExperimentLinksV1",
    "StudioBenchmarkExperimentRecordPageV1",
    "StudioBenchmarkExperimentRecordV1",
    "StudioBenchmarkExperimentResourceV1",
    "StudioBenchmarkExperimentTerminalReason",
    "StudioBenchmarkHistoryAgentV1",
    "StudioBenchmarkHistorySourceV1",
    "StudioBenchmarkRecoveryAttemptV1",
    "StudioBenchmarkRecoveryCandidatePageV1",
    "StudioBenchmarkRecoveryCandidateV1",
    "StudioBenchmarkRecoveryDecision",
    "StudioBenchmarkRecoverySummaryV1",
    "StudioBenchmarkRecoveryTaskRunV1",
    "StudioBenchmarkSourceSnapshotV1",
    "StudioBenchmarkTaskRunLifecycle",
    "StudioBenchmarkTaskRunPageV1",
    "StudioBenchmarkTaskRunLinksV1",
    "StudioBenchmarkTaskPhaseV1",
    "StudioBenchmarkTaskRunRecordV1",
    "StudioBenchmarkTaskResultV1",
    "StudioBenchmarkTaskRunTerminalReason",
    "benchmark_event_fingerprint",
    "canonical_experiment_request_fingerprint",
    "canonical_snapshot_json",
]


from .benchmark_publication_models import (  # noqa: E402
    StudioBenchmarkArtifactDescriptorV1,
    StudioBenchmarkPublicationDiagnosticV1,
)

StudioBenchmarkTaskRunRecordV1.model_rebuild()
StudioBenchmarkExperimentRecordV1.model_rebuild()
StudioBenchmarkExperimentResourceV1.model_rebuild()
