"""Safe runtime contracts for executing BenchmarkPlan experiments."""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol

from zhixing.components import EvaluationResultV2, RunResult
from zhixing.components.models import redact_mapping


class BenchmarkStageStatus(str, Enum):
    """Stable status for one observable Benchmark lifecycle stage."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    UNVERIFIED = "unverified"


class BenchmarkOutcome(str, Enum):
    """Final task-level evaluation outcome independent of Agent RunStatus."""

    PASS = "pass"
    FAIL = "fail"
    INVALID = "invalid"
    SKIPPED = "skipped"


class BenchmarkPublicationPolicy(str, Enum):
    """Runtime-only policy for Benchmark artifact finalization."""

    PUBLISH = "publish"
    DEFER = "defer"


class BenchmarkCancellationSignal(Protocol):
    """Minimal cooperative cancellation boundary accepted by Benchmark Core."""

    def is_cancelled(self) -> bool:
        """Return whether new work must stop at the next safe boundary."""
        ...


@dataclass(frozen=True)
class CompositeCancellation:
    """Combine caller cancellation with the Protocol deadline signal."""

    signals: tuple[BenchmarkCancellationSignal, ...]

    def is_cancelled(self) -> bool:
        """Return whether any constituent signal requests cancellation.

        Returns:
            bool: True when at least one signal is cancelled.
        """
        return any(signal.is_cancelled() for signal in self.signals)


@dataclass(frozen=True)
class BenchmarkLifecycleEvent:
    """One safe ordered event emitted by the Benchmark orchestration layer."""

    experiment_id: str
    sequence: int
    phase: str
    kind: str
    task_run_id: str = ""
    task_id: str = ""
    agent_id: str = ""
    repeat: int = 0
    timestamp: float = field(default_factory=time.time)
    duration_ms: float | None = None
    payload: Mapping[str, Any] = field(default_factory=dict)

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the event without live objects or sensitive values.

        Returns:
            dict[str, Any]: Bounded JSON-compatible event.
        """
        return {
            "experiment_id": self.experiment_id,
            "sequence": self.sequence,
            "phase": self.phase,
            "kind": self.kind,
            "task_run_id": self.task_run_id,
            "task_id": self.task_id,
            "agent_id": self.agent_id,
            "repeat": self.repeat,
            "timestamp": self.timestamp,
            "duration_ms": self.duration_ms,
            "payload": redact_mapping(self.payload),
        }


@dataclass(frozen=True)
class BenchmarkStageResult:
    """Structured result for one lifecycle phase."""

    phase: str
    status: BenchmarkStageStatus
    duration_ms: float = 0.0
    error_code: str = ""
    message: str = ""
    evidence: Mapping[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the phase result safely.

        Returns:
            dict[str, Any]: Bounded phase result.
        """
        return {
            "phase": self.phase,
            "status": self.status.value,
            "duration_ms": round(max(0.0, self.duration_ms), 3),
            "error_code": self.error_code,
            "message": self.message[:1000],
            "evidence": redact_mapping(self.evidence),
            "artifact_refs": list(self.artifact_refs[:50]),
        }


@dataclass(frozen=True)
class EvaluationNodeResult:
    """Evidence retained for one leaf or composite Evaluator Tree node."""

    path: str
    name: str
    status: BenchmarkStageStatus
    is_pass: bool | None
    reason: str = ""
    token: float | None = None
    score: float | None = None
    duration_ms: float = 0.0
    evidence: Mapping[str, Any] = field(default_factory=dict)
    aggregation: Mapping[str, Any] = field(default_factory=dict)
    evaluator_result: EvaluationResultV2 | None = None
    children: tuple["EvaluationNodeResult", ...] = ()
    short_circuited: bool = False

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize one evaluation node and its bounded descendants.

        Returns:
            dict[str, Any]: Safe evaluator evidence tree.
        """
        return {
            "path": self.path,
            "name": self.name,
            "status": self.status.value,
            "is_pass": self.is_pass,
            "reason": self.reason[:1000],
            "token": self.token,
            "score": self.score,
            "duration_ms": round(max(0.0, self.duration_ms), 3),
            "evidence": redact_mapping(self.evidence),
            "aggregation": redact_mapping(self.aggregation),
            "evaluator_result": (
                self.evaluator_result.to_safe_dict()
                if self.evaluator_result is not None
                else None
            ),
            "short_circuited": self.short_circuited,
            "children": [item.to_safe_dict() for item in self.children[:50]],
        }


@dataclass(frozen=True)
class BenchmarkTaskResult:
    """Complete result for one Agent and one materialized task instance."""

    experiment_id: str
    task_run_id: str
    task_id: str
    repeat: int
    agent_id: str
    agent_graph_identity: str
    benchmark_plan_identity: str
    experiment_protocol_identity: str
    task_instance_identity: str
    outcome: BenchmarkOutcome
    stages: tuple[BenchmarkStageResult, ...]
    lifecycle_events: tuple[BenchmarkLifecycleEvent, ...] = ()
    agent_result: RunResult | None = field(default=None, repr=False)
    evaluation: EvaluationNodeResult | None = None
    usage: Mapping[str, Any] = field(default_factory=dict)
    artifact_namespace: str = ""
    fairness_warnings: tuple[str, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize a task result without host paths or runtime services.

        Returns:
            dict[str, Any]: Stable safe task manifest.
        """
        return {
            "experiment_id": self.experiment_id,
            "task_run_id": self.task_run_id,
            "task_id": self.task_id,
            "repeat": self.repeat,
            "agent_id": self.agent_id,
            "identities": {
                "agent_graph": self.agent_graph_identity,
                "benchmark_plan": self.benchmark_plan_identity,
                "experiment_protocol": self.experiment_protocol_identity,
                "task_instance": self.task_instance_identity,
            },
            "outcome": self.outcome.value,
            "stages": [item.to_safe_dict() for item in self.stages],
            "lifecycle_events": [
                item.to_safe_dict() for item in self.lifecycle_events[:500]
            ],
            "agent_result": (
                self.agent_result.to_safe_dict()
                if self.agent_result is not None
                else None
            ),
            "evaluation": (
                self.evaluation.to_safe_dict()
                if self.evaluation is not None
                else None
            ),
            "usage": redact_mapping(self.usage),
            "artifact_namespace": self.artifact_namespace,
            "fairness_warnings": list(self.fairness_warnings),
        }


@dataclass(frozen=True)
class BenchmarkSuiteResult:
    """Ordered results and counts for one Benchmark experiment."""

    experiment_id: str
    benchmark_plan_identity: str
    experiment_protocol_identity: str
    results: tuple[BenchmarkTaskResult, ...]
    lifecycle_events: tuple[BenchmarkLifecycleEvent, ...] = ()
    fairness_warnings: tuple[str, ...] = ()
    device_provenance: Mapping[str, Any] = field(default_factory=dict)
    artifact_refs: tuple[str, ...] = ()
    reporting_error_code: str = ""

    @property
    def counts(self) -> dict[str, int]:
        """Count task outcomes without conflating FAIL and INVALID.

        Returns:
            dict[str, int]: Count keyed by stable outcome value.
        """
        values = {item.value: 0 for item in BenchmarkOutcome}
        for result in self.results:
            values[result.outcome.value] += 1
        return values

    @property
    def is_success(self) -> bool:
        """Report whether every scheduled task passed.

        Returns:
            bool: True only when at least one result exists and all pass.
        """
        return bool(self.results) and all(
            item.outcome is BenchmarkOutcome.PASS for item in self.results
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize a suite result for CLI and durable manifests.

        Returns:
            dict[str, Any]: Stable safe suite result.
        """
        return {
            "experiment_id": self.experiment_id,
            "benchmark_plan_identity": self.benchmark_plan_identity,
            "experiment_protocol_identity": self.experiment_protocol_identity,
            "counts": self.counts,
            "is_success": self.is_success,
            "fairness_warnings": list(self.fairness_warnings),
            "device_provenance": redact_mapping(self.device_provenance),
            "artifact_refs": list(self.artifact_refs),
            "reporting_error_code": self.reporting_error_code,
            "lifecycle_events": [
                item.to_safe_dict() for item in self.lifecycle_events[:1000]
            ],
            "results": [item.to_safe_dict() for item in self.results],
        }


@dataclass(frozen=True)
class BenchmarkRunConfig:
    """Runtime-only bindings that do not affect semantic identities."""

    artifact_root: Path = Path("temp/benchmarks")
    serial: str | None = None
    task_ids: tuple[str, ...] = ()
    strict_preflight: bool = True
    persist_manifests: bool = True
    publication_policy: BenchmarkPublicationPolicy = (
        BenchmarkPublicationPolicy.PUBLISH
    )
    experiment_id: str = field(default_factory=lambda: uuid.uuid4().hex)

    def __post_init__(self) -> None:
        """Normalize runtime paths and validate selection values.

        Raises:
            ValueError: Experiment identity, task selector, or publication
                policy is invalid.

        Returns:
            None.
        """
        if not self.experiment_id.strip():
            raise ValueError("experiment_id must not be blank")
        if any(not item.strip() for item in self.task_ids):
            raise ValueError("task_ids must not contain blank values")
        if not isinstance(self.publication_policy, BenchmarkPublicationPolicy):
            object.__setattr__(
                self,
                "publication_policy",
                BenchmarkPublicationPolicy(self.publication_policy),
            )
        object.__setattr__(self, "artifact_root", Path(self.artifact_root))

    def safe_device_id(self) -> str:
        """Return a non-reversible device reference suitable for reports.

        Returns:
            str: Empty string or short SHA-256 reference.
        """
        if not self.serial:
            return ""
        return "device-sha256:" + hashlib.sha256(
            self.serial.encode("utf-8")
        ).hexdigest()[:16]


@dataclass
class DeadlineCancellation:
    """Cooperative cancellation signal backed by a monotonic deadline."""

    deadline: float
    _cancelled: bool = False

    @classmethod
    def after(cls, seconds: float) -> "DeadlineCancellation":
        """Create a signal that expires after a positive duration.

        Args:
            seconds (float): Relative timeout in seconds.

        Raises:
            ValueError: Duration is not positive.

        Returns:
            DeadlineCancellation: Configured signal.
        """
        if seconds <= 0:
            raise ValueError("seconds must be positive")
        return cls(deadline=time.monotonic() + seconds)

    def cancel(self) -> None:
        """Request cancellation explicitly.

        Returns:
            None.
        """
        self._cancelled = True

    def is_cancelled(self) -> bool:
        """Check explicit cancellation or deadline expiry.

        Returns:
            bool: True when execution should stop cooperatively.
        """
        return self._cancelled or time.monotonic() >= self.deadline
