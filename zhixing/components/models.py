"""Stable runtime values for composing ZhiXing components.

Existing Agent protocol classes are imported and re-exported rather than
duplicated so values produced by current built-ins keep their class identity.
"""

from __future__ import annotations

import hashlib
import re
import math
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional, Union

from zhixing.core.agent.protocol import (
    Action,
    ActionType,
    MemoryFragment,
    PerceptionInput,
    PerceptionResult,
    PlanInput,
    PlanResult,
    VerifierInput,
    VerifierResult,
)
from zhixing.core.benchmark.protocol import EvalResult


PlanningInput = PlanInput
PlanningResult = PlanResult
EvaluationResult = EvalResult


def safe_device_reference(value: object) -> str:
    """Return an empty or non-reversible device identity for evidence.

    Args:
        value: Raw device identifier or an already-safe reference.

    Returns:
        Empty text, an existing safe reference, or a short SHA-256 reference.
    """
    text = str(value or "")
    if not text or text.startswith("device-sha256:"):
        return text
    return "device-sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    TERMINAL = "terminal"
    CANCELLED = "cancelled"
    DEVICE_FAILURE = "device_failure"


class RunStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    STEP_LIMIT = "step_limit"
    CANCELLED = "cancelled"
    DEVICE_FAILURE = "device_failure"


class MemoryOperation(str, Enum):
    APPEND = "append"
    READ = "read"
    RESET = "reset"
    LOAD_KNOWLEDGE = "load_knowledge"
    RETRIEVE_EXPERIENCE = "retrieve_experience"


class DeviceOperation(str, Enum):
    OBSERVE = "observe"
    TAP = "tap"
    LONG_PRESS = "long_press"
    SWIPE = "swipe"
    TEXT = "text"
    KEY = "key"
    START_APP = "start_app"
    WAIT = "wait"
    SHELL = "shell"


class DeviceEffectKind(str, Enum):
    NONE = "none"
    UI_INPUT = "ui_input"
    APP_LAUNCH = "app_launch"
    FILE_SYSTEM = "file_system"
    WAIT = "wait"
    SHELL = "shell"


class BenchmarkInitKind(str, Enum):
    TASK_PARAMETER = "task_parameter"
    ENVIRONMENT = "environment"


class EvaluationStatus(str, Enum):
    """Execution status for one evaluator invocation."""

    COMPLETED = "completed"
    ERROR = "error"
    INVALID = "invalid"
    SKIPPED = "skipped"


class UsageAvailability(str, Enum):
    """Whether evaluator model usage is observable."""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class TaskInput:
    instruction: str
    id: Optional[str] = None
    app: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceObservation:
    screenshot_path: str
    width: int
    height: int
    ui_path: Optional[str] = None
    platform: str = "unknown"
    sequence: int = 0
    observed_at: float = field(default_factory=time.time)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    device_id: str = ""
    interaction_step: int = 0
    screenshot_artifact: str = ""
    ui_artifact: Optional[str] = None

    @classmethod
    def from_legacy(cls, value: PerceptionInput, **kwargs: Any) -> "DeviceObservation":
        return cls(
            screenshot_path=value.screenshot_path,
            width=value.width,
            height=value.height,
            ui_path=value.ui_path,
            **kwargs,
        )

    def to_legacy(self) -> PerceptionInput:
        return PerceptionInput(
            screenshot_path=self.screenshot_path,
            width=self.width,
            height=self.height,
            ui_path=self.ui_path,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize one observation without device handles or image bytes.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible observation metadata and artifacts.
        """
        return {
            "screenshot_path": self.screenshot_path,
            "width": self.width,
            "height": self.height,
            "ui_path": self.ui_path,
            "platform": self.platform,
            "sequence": self.sequence,
            "observed_at": self.observed_at,
            "metadata": redact_mapping(self.metadata),
            "device_id": safe_device_reference(self.device_id),
            "interaction_step": self.interaction_step,
            "screenshot_artifact": self.screenshot_artifact,
            "ui_artifact": self.ui_artifact,
        }


@dataclass(frozen=True)
class ReasoningInput:
    task: TaskInput
    plan: PlanResult
    perception: PerceptionResult
    memory_context: tuple[MemoryFragment, ...] = ()
    available_apps: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    verification: Optional[VerifierResult] = None


@dataclass(frozen=True)
class GroundingInput:
    observation: DeviceObservation
    description: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GroundingResult:
    x: int
    y: int
    confidence: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class LLMInput:
    prompt: str
    images: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: Optional[LLMUsage] = None
    model: Optional[str] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryInput:
    operation: MemoryOperation
    fragment: Optional[MemoryFragment] = None
    query: str = ""
    screenshot_path: str = ""
    task: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MemoryResult:
    operation: MemoryOperation
    accepted: bool = True
    fragments: tuple[MemoryFragment, ...] = ()
    action: Optional[Action] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceRequest:
    operation: DeviceOperation
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ObservationRequest:
    include_ui_tree: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeviceResult:
    operation: DeviceOperation
    success: bool
    observation: Optional[DeviceObservation] = None
    value: Any = None
    error: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionExecutionInput:
    action: Action
    observation: Optional[DeviceObservation] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ActionResult:
    action: Action
    status: ExecutionStatus
    message: str = ""
    error: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)
    effect_performed: bool = False
    effect_kind: DeviceEffectKind = DeviceEffectKind.NONE
    terminal_status: Optional[RunStatus] = None
    device_id: str = ""

    @property
    def succeeded(self) -> bool:
        return self.status in {ExecutionStatus.SUCCESS, ExecutionStatus.TERMINAL}

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize an action result without exposing runtime services.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible action execution evidence.
        """
        return {
            "action_type": self.action.type.value,
            "status": self.status.value,
            "message": _redact_text(self.message),
            "error": _redact_text(self.error),
            "metadata": redact_mapping(self.metadata),
            "effect_performed": self.effect_performed,
            "effect_kind": self.effect_kind.value,
            "terminal_status": self.terminal_status.value if self.terminal_status else None,
            "device_id": safe_device_reference(self.device_id),
        }


@dataclass(frozen=True)
class BenchmarkInitInput:
    kind: BenchmarkInitKind
    params: Mapping[str, Any] = field(default_factory=dict)
    meta: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkInitResult:
    kind: BenchmarkInitKind
    success: bool
    value: Any = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EvaluationInput:
    context: Mapping[str, Any]


@dataclass(frozen=True)
class EvaluationEvidence:
    """One typed, safely serializable evaluator evidence item."""

    kind: str
    value: Mapping[str, Any] = field(default_factory=dict)
    artifact_ref: str = ""
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate evidence identity and reference shape.

        Raises:
            ValueError: The kind or artifact reference is unsafe.

        Returns:
            None.
        """
        if not re.fullmatch(
            r"(?:system\.state|visual\.image|text\.match|"
            r"trajectory\.sequence|artifact\.file|custom\.[a-z0-9_.-]+)",
            self.kind,
        ):
            raise ValueError("unsupported evaluation evidence kind")
        if self.artifact_ref:
            if (
                self.artifact_ref.startswith(("/", "\\"))
                or ".." in self.artifact_ref.replace("\\", "/").split("/")
            ):
                raise ValueError("artifact_ref must be a safe relative reference")

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the bounded evidence item.

        Returns:
            dict[str, Any]: Safe evidence payload.
        """
        return {
            "kind": self.kind,
            "value": redact_mapping(self.value),
            "artifact_ref": _redact_text(self.artifact_ref),
            "metadata": redact_mapping(self.metadata),
        }


@dataclass(frozen=True)
class EvaluationUsage:
    """Normalized evaluator usage with explicit availability."""

    availability: UsageAvailability = UsageAvailability.UNAVAILABLE
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    def __post_init__(self) -> None:
        """Validate available usage counters.

        Raises:
            ValueError: A counter is negative or unavailable usage has counters.

        Returns:
            None.
        """
        counters = (
            self.prompt_tokens,
            self.completion_tokens,
            self.total_tokens,
        )
        if any(value is not None and value < 0 for value in counters):
            raise ValueError("evaluation usage counters must be non-negative")
        if (
            self.availability is UsageAvailability.UNAVAILABLE
            and any(value is not None for value in counters)
        ):
            raise ValueError("unavailable usage must not contain counters")

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize evaluator usage without fabricating unavailable zeros.

        Returns:
            dict[str, Any]: Safe usage payload.
        """
        return {
            "availability": self.availability.value,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


@dataclass(frozen=True)
class EvaluationResultV2:
    """Canonical typed output for one Benchmark evaluator invocation."""

    evaluator_id: str
    status: EvaluationStatus
    passed: bool | None
    score: float | None = None
    reason: str = ""
    duration_ms: float = 0.0
    usage: EvaluationUsage = field(default_factory=EvaluationUsage)
    evidence: tuple[EvaluationEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
    error_code: str = ""
    schema_version: str = "2.0"

    def __post_init__(self) -> None:
        """Validate decision, score, and stable identity invariants.

        Raises:
            ValueError: The result contains inconsistent or non-finite values.

        Returns:
            None.
        """
        if not self.evaluator_id.strip():
            raise ValueError("evaluator_id must not be blank")
        if self.status is EvaluationStatus.COMPLETED and self.passed is None:
            raise ValueError("completed evaluation requires a pass decision")
        if self.status is not EvaluationStatus.COMPLETED and self.passed is not None:
            raise ValueError("non-completed evaluation must not claim pass or fail")
        if self.score is not None and (
            not math.isfinite(self.score) or not 0.0 <= self.score <= 1.0
        ):
            raise ValueError("evaluation score must be finite and normalized")
        if not math.isfinite(self.duration_ms) or self.duration_ms < 0:
            raise ValueError("duration_ms must be finite and non-negative")

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the canonical evaluator result.

        Returns:
            dict[str, Any]: Safe versioned evaluator result.
        """
        return {
            "schema_version": self.schema_version,
            "evaluator_id": self.evaluator_id,
            "status": self.status.value,
            "passed": self.passed,
            "score": self.score,
            "reason": _redact_text(self.reason),
            "duration_ms": round(self.duration_ms, 3),
            "usage": self.usage.to_safe_dict(),
            "evidence": [item.to_safe_dict() for item in self.evidence],
            "metadata": redact_mapping(self.metadata),
            "error_code": self.error_code,
        }


@dataclass
class AgentState:
    current_task: Optional[TaskInput] = None
    plan: Optional[PlanResult] = None
    step: int = 0
    last_observation: Optional[DeviceObservation] = None
    last_action: Optional[Action] = None
    last_action_result: Optional[ActionResult] = None
    observation_history: list[DeviceObservation] = field(default_factory=list)
    strategy_state: dict[str, Any] = field(default_factory=dict)

    def reset(self, task: Optional[TaskInput] = None) -> None:
        """Reset all run-scoped mutable state for a new task.

        Args:
            task (Optional[TaskInput]): Task assigned to the new run.

        Raises:
            None.

        Returns:
            None: The state is reset in place.
        """
        self.current_task = task
        self.plan = None
        self.step = 0
        self.last_observation = None
        self.last_action = None
        self.last_action_result = None
        self.observation_history.clear()
        self.strategy_state.clear()


@dataclass(frozen=True)
class RunEvent:
    run_id: str
    sequence: int
    timestamp: float
    phase: str
    role: str
    component: str
    kind: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    step: int = 0
    node_id: str = ""
    duration_ms: Optional[float] = None
    call_id: str = ""
    node_path: str = ""
    activation_id: str = ""
    parent_activation_id: str = ""
    loop_path: str = ""
    loop_iteration: Optional[int] = None
    interaction_step: Optional[int] = None

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the event without live services or sensitive values.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible, recursively redacted event data.
        """
        result = {
            "run_id": self.run_id,
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "phase": self.phase,
            "role": self.role,
            "component": self.component,
            "kind": self.kind,
            "step": self.step,
            "node_id": self.node_id,
            "duration_ms": self.duration_ms,
            "call_id": self.call_id,
            "payload": redact_mapping(self.payload),
        }
        if self.node_path:
            result["node_path"] = self.node_path
        if self.activation_id:
            result["activation_id"] = self.activation_id
        if self.parent_activation_id:
            result["parent_activation_id"] = self.parent_activation_id
        if self.loop_path:
            result["loop_path"] = self.loop_path
        if self.loop_iteration is not None:
            result["loop_iteration"] = self.loop_iteration
        if self.interaction_step is not None:
            result["interaction_step"] = self.interaction_step
        return result


EventSink = Callable[[RunEvent], None]


@dataclass(frozen=True)
class ComponentInvocationTrace:
    """Run-scoped component invocation facts for explicit debug capture."""

    run_id: str
    node_path: str
    activation_id: str
    role: str
    component: str
    stage: str
    candidate_index: int = 0
    interaction_step: int = 0
    inputs: Mapping[str, Any] = field(default_factory=dict)
    outputs: Mapping[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None
    error_type: str = ""


DebugSink = Callable[[ComponentInvocationTrace], None]


@dataclass
class RuntimeContext:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    step: int = 0
    max_steps: int = 15
    max_activations: Optional[int] = None
    state: AgentState = field(default_factory=AgentState)
    device: Any = field(default=None, repr=False)
    event_sink: Optional[EventSink] = field(default=None, repr=False)
    debug_sink: Optional[DebugSink] = field(default=None, repr=False)
    cancellation: Any = field(default=None, repr=False)
    artifacts: Any = field(default=None, repr=False)
    metadata: dict[str, Any] = field(default_factory=dict)
    _event_sequence: int = field(default=0, init=False, repr=False)

    def emit(
        self,
        *,
        phase: str,
        role: str,
        component: str,
        kind: str,
        payload: Optional[Mapping[str, Any]] = None,
        node_id: str = "",
        duration_ms: Optional[float] = None,
        call_id: str = "",
        node_path: str = "",
        activation_id: str = "",
        parent_activation_id: str = "",
        loop_path: str = "",
        loop_iteration: Optional[int] = None,
        interaction_step: Optional[int] = None,
    ) -> RunEvent:
        """Emit one ordered, safe runtime event through the configured sink.

        Args:
            phase (str): Runtime phase that produced the event.
            role (str): Logical component role or runtime role.
            component (str): Non-sensitive component identifier.
            kind (str): Event kind such as start, complete, or fail.
            payload (Optional[Mapping[str, Any]]): Event details to redact.
            node_id (str): Stable AgentGraph logical node identifier.
            duration_ms (Optional[float]): Completed call duration in milliseconds.
            call_id (str): Correlation identifier shared by paired node events.
            node_path (str): Stable hierarchical logical node path.
            activation_id (str): Run-local node activation identifier.
            parent_activation_id (str): Parent subgraph or loop activation identifier.
            loop_path (str): Stable logical loop path.
            loop_iteration (Optional[int]): Zero-based local-loop iteration.
            interaction_step (Optional[int]): Physical interaction step identity.

        Raises:
            Exception: Propagates an exception raised by the user-provided event sink.

        Returns:
            RunEvent: The emitted event with a monotonic sequence number.
        """
        self._event_sequence += 1
        event = RunEvent(
            run_id=self.run_id,
            sequence=self._event_sequence,
            timestamp=time.time(),
            phase=phase,
            role=role,
            component=component,
            kind=kind,
            payload=redact_mapping(payload or {}),
            step=self.step,
            node_id=node_id,
            duration_ms=duration_ms,
            call_id=call_id,
            node_path=node_path,
            activation_id=activation_id,
            parent_activation_id=parent_activation_id,
            loop_path=loop_path,
            loop_iteration=loop_iteration,
            interaction_step=interaction_step,
        )
        if self.event_sink is not None:
            self.event_sink(event)
        return event

    def capture_debug(
        self,
        *,
        node_path: str,
        activation_id: str,
        role: str,
        component: str,
        stage: str,
        candidate_index: int = 0,
        interaction_step: int = 0,
        inputs: Optional[Mapping[str, Any]] = None,
        outputs: Optional[Mapping[str, Any]] = None,
        duration_ms: Optional[float] = None,
        error_type: str = "",
    ) -> None:
        """Send explicit component invocation facts to an optional debug sink.

        Args:
            node_path (str): Stable hierarchical graph node path.
            activation_id (str): Run-local activation identity.
            role (str): Node contract or component role.
            component (str): Selected component definition identity.
            stage (str): Invocation stage: start, complete, or fail.
            candidate_index (int): Zero-based selected candidate position.
            interaction_step (int): Current physical interaction identity.
            inputs (Optional[Mapping[str, Any]]): Typed logical input ports.
            outputs (Optional[Mapping[str, Any]]): Typed logical output ports.
            duration_ms (Optional[float]): Completed attempt duration.
            error_type (str): Safe exception type for failed attempts.

        Raises:
            Exception: Propagates failures from the configured debug sink.

        Returns:
            None.
        """
        if self.debug_sink is None:
            return
        self.debug_sink(
            ComponentInvocationTrace(
                run_id=self.run_id,
                node_path=node_path,
                activation_id=activation_id,
                role=role,
                component=component,
                stage=stage,
                candidate_index=candidate_index,
                interaction_step=interaction_step,
                inputs=dict(inputs or {}),
                outputs=dict(outputs or {}),
                duration_ms=duration_ms,
                error_type=str(error_type),
            )
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a serializable summary of run state and available services.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Redacted context summary without live service objects.
        """
        return {
            "run_id": self.run_id,
            "step": self.step,
            "max_steps": self.max_steps,
            "max_activations": self.max_activations,
            "state": {
                "step": self.state.step,
                "has_task": self.state.current_task is not None,
                "has_plan": self.state.plan is not None,
                "has_observation": self.state.last_observation is not None,
                "has_action": self.state.last_action is not None,
                "has_action_result": self.state.last_action_result is not None,
                "strategy_state": redact_mapping(self.state.strategy_state),
            },
            "services": {
                "device": self.device is not None,
                "event_sink": self.event_sink is not None,
                "debug_sink": self.debug_sink is not None,
                "cancellation": self.cancellation is not None,
                "artifacts": self.artifacts is not None,
            },
            "metadata": redact_mapping(self.metadata),
        }


@dataclass(frozen=True)
class RunResult:
    run_id: str
    status: RunStatus
    state: AgentState
    action_results: tuple[ActionResult, ...] = ()
    events: tuple[RunEvent, ...] = ()
    usage: Mapping[str, Any] = field(default_factory=dict)
    error: str = ""
    final_output: Any = None
    error_details: Mapping[str, Any] = field(default_factory=dict)
    step_count: Optional[int] = None
    kernel_status: str = ""
    activation_count: int = 0
    interaction_count: int = 0
    artifact_namespace: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize final execution evidence using safe summaries.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible result without runtime object leakage.
        """
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "steps": self.step_count if self.step_count is not None else self.state.step,
            "action_statuses": [result.status.value for result in self.action_results],
            "action_results": [result.to_safe_dict() for result in self.action_results],
            "events": [event.to_safe_dict() for event in self.events],
            "final_output": _safe_value(self.final_output),
            "state": RuntimeContext(state=self.state).to_safe_dict()["state"],
            "usage": redact_mapping(self.usage),
            "error": _redact_text(self.error),
            "error_details": redact_mapping(self.error_details),
            "kernel_status": self.kernel_status,
            "activation_count": self.activation_count,
            "interaction_count": self.interaction_count,
            "artifact_namespace": self.artifact_namespace,
        }


_SECRET_PARTS = (
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "credential",
    "token",
    "password",
    "secret",
    "authorization",
)
_DEVICE_ID_KEYS = {
    "adb_serial",
    "device_id",
    "device_serial",
    "raw_serial",
    "serial",
}
_MAX_SAFE_TEXT_LENGTH = 1000
_MAX_SAFE_COLLECTION_DEPTH = 6
_MAX_SAFE_COLLECTION_ITEMS = 50
_CREDENTIAL_URL_PATTERN = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)"
    r"(?P<userinfo>[^/\s:@]+:[^/\s@]+@)"
    r"(?P<target>[^\s'\"<>]+)",
    flags=re.IGNORECASE,
)
_LOCAL_PATH_PATTERN = re.compile(
    r"(?P<path>"
    r"(?:file://)?(?:/Users|/home|/tmp|/private|/var/folders|/opt)/"
    r"|(?:~|\.\.?)[/\\]"
    r"|(?<![A-Za-z0-9])[A-Za-z]:[/\\]"
    r")[^\s'\"<>]*",
)
_OMITTED_ITEMS_PATTERN = re.compile(r"<\d+ items omitted>")


def _is_secret_key(value: object) -> bool:
    """Return whether a mapping key is likely to identify secret material.

    Args:
        value (object): Candidate key.

    Raises:
        None.

    Returns:
        bool: True when the normalized key contains a sensitive marker.
    """
    normalized = str(value).lower().replace("-", "_")
    return any(part in normalized for part in _SECRET_PARTS)


def _is_device_identity_key(value: object) -> bool:
    """Return whether a mapping key carries raw device identity.

    Args:
        value: Candidate mapping key.

    Returns:
        ``True`` when the value must be replaced by a safe device reference.
    """
    normalized = str(value).lower().replace("-", "_")
    return normalized in _DEVICE_ID_KEYS


def _redact_text(value: object) -> str:
    """Bound text and hide secret markers, credential URLs, and local paths.

    Args:
        value (object): Value converted to text.

    Raises:
        None.

    Returns:
        str: Redacted or length-bounded text.
    """
    text = str(value)[:_MAX_SAFE_TEXT_LENGTH]
    lowered = text.lower()
    if any(part in lowered for part in _SECRET_PARTS):
        return "<redacted>"
    # URLs with embedded user information can leak credentials even when their
    # values do not contain conventional secret marker words.
    text = _CREDENTIAL_URL_PATTERN.sub(
        lambda match: (
            f"{match.group('scheme')}<redacted>@{match.group('target')}"
        ),
        text,
    )
    # Diagnostics should identify the failure, not expose a developer's home
    # directory, temporary checkout, or other machine-specific local path.
    return _LOCAL_PATH_PATTERN.sub("<local-path>", text)


def _safe_value(
    value: Any,
    *,
    depth: int = 0,
    ancestors: frozenset[int] = frozenset(),
) -> Any:
    """Convert a runtime value into a bounded JSON-compatible summary.

    Args:
        value (Any): Runtime value to summarize.
        depth (int): Current recursive collection depth.
        ancestors (frozenset[int]): Active collection identities for cycle
            detection.

    Raises:
        None.

    Returns:
        Any: Primitive, redacted collection, or stable type marker.
    """
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, Enum):
        return _safe_value(value.value, depth=depth, ancestors=ancestors)
    if isinstance(value, Mapping):
        return _safe_mapping(value, depth=depth, ancestors=ancestors)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        if depth >= _MAX_SAFE_COLLECTION_DEPTH:
            return "<max-depth>"
        identity = id(value)
        if identity in ancestors:
            return "<cycle>"
        child_ancestors = ancestors | {identity}
        item_limit = _MAX_SAFE_COLLECTION_ITEMS
        if (
            len(value) == _MAX_SAFE_COLLECTION_ITEMS + 1
            and isinstance(value[-1], str)
            and _OMITTED_ITEMS_PATTERN.fullmatch(value[-1])
        ):
            # Preserve an existing truncation marker when safe data passes
            # through a second serialization boundary.
            item_limit += 1
        items = [
            _safe_value(
                item,
                depth=depth + 1,
                ancestors=child_ancestors,
            )
            for item in value[:item_limit]
        ]
        omitted = len(value) - len(items)
        if omitted:
            items.append(f"<{omitted} items omitted>")
        return items
    return f"<{type(value).__module__}.{type(value).__qualname__}>"


def _safe_mapping(
    value: Mapping[str, Any],
    *,
    depth: int,
    ancestors: frozenset[int],
) -> dict[str, Any]:
    """Serialize one mapping with recursion, cycle, and item-count bounds.

    Args:
        value (Mapping[str, Any]): Mapping to summarize.
        depth (int): Current recursive collection depth.
        ancestors (frozenset[int]): Active collection identities for cycle
            detection.

    Raises:
        None.

    Returns:
        dict[str, Any]: Bounded and recursively sanitized mapping.
    """
    if depth >= _MAX_SAFE_COLLECTION_DEPTH:
        return {"__summary__": "<max-depth>"}
    identity = id(value)
    if identity in ancestors:
        return {"__summary__": "<cycle>"}
    child_ancestors = ancestors | {identity}
    result: dict[str, Any] = {}
    item_limit = _MAX_SAFE_COLLECTION_ITEMS
    if (
        isinstance(value, dict)
        and len(value) == _MAX_SAFE_COLLECTION_ITEMS + 1
        and next(reversed(value), None) == "__truncated_items__"
    ):
        # A previously sanitized mapping already carries its bounded omission
        # count, so a repeated safety pass must not replace that count with 1.
        item_limit += 1
    for index, (key, item) in enumerate(value.items()):
        if index >= item_limit:
            result["__truncated_items__"] = max(
                len(value) - _MAX_SAFE_COLLECTION_ITEMS,
                0,
            )
            break
        # Preserve conventional secret field labels for actionable output while
        # still sanitizing arbitrary path- or URL-shaped mapping keys.
        safe_key = (
            str(key)[:128]
            if _is_secret_key(key)
            else _redact_text(key)[:128]
        )
        result[safe_key] = (
            safe_device_reference(item)
            if _is_device_identity_key(key)
            else "<redacted>"
            if _is_secret_key(key)
            else _safe_value(
                item,
                depth=depth + 1,
                ancestors=child_ancestors,
            )
        )
    return result


def redact_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    """Return a bounded safe copy without traversing live service objects.

    Args:
        value (Mapping[str, Any]): Mapping that may contain sensitive data.

    Raises:
        None.

    Returns:
        dict[str, Any]: Recursively redacted JSON-compatible mapping.
    """
    return _safe_mapping(value, depth=0, ancestors=frozenset())


MemoryInputType = MemoryInput
MemoryResultType = MemoryResult
BenchmarkInitializerInput = BenchmarkInitInput
BenchmarkInitializerResult = BenchmarkInitResult
