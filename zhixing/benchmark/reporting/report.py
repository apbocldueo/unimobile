"""Versioned run and experiment report derivation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from ..runtime.models import BenchmarkSuiteResult, BenchmarkTaskResult
from .metrics import (
    AgentComparison,
    AgentMetricSummary,
    build_agent_comparisons,
    build_agent_metrics,
)
from .safety import safe_export

REPORT_SCHEMA_VERSION = "1.0"


class ReportSchemaError(ValueError):
    """Raised when a durable report uses an unsupported schema."""


@dataclass(frozen=True)
class BenchmarkRunReport:
    """Reader-facing summary derived from one immutable task result."""

    task_run_id: str
    experiment_id: str
    task_id: str
    agent_id: str
    repeat: int
    outcome: str
    identities: Mapping[str, str]
    stages: tuple[Mapping[str, Any], ...]
    evaluation: Mapping[str, Any] | None
    usage: Mapping[str, Any]
    artifact_namespace: str
    schema_version: str = REPORT_SCHEMA_VERSION

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the run report with recursive safety enforcement.

        Returns:
            dict[str, Any]: Safe versioned report.
        """
        return safe_export(
            {
                "schema_version": self.schema_version,
                "kind": "benchmark_run_report",
                "task_run_id": self.task_run_id,
                "experiment_id": self.experiment_id,
                "task_id": self.task_id,
                "agent_id": self.agent_id,
                "repeat": self.repeat,
                "outcome": self.outcome,
                "identities": dict(self.identities),
                "stages": list(self.stages),
                "evaluation": self.evaluation,
                "usage": dict(self.usage),
                "artifact_namespace": self.artifact_namespace,
            }
        )

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BenchmarkRunReport":
        """Load one supported run report document.

        Args:
            value (Mapping[str, Any]): Decoded JSON mapping.

        Raises:
            ReportSchemaError: Schema version or kind is unsupported.
            ValueError: Required report fields are invalid.

        Returns:
            BenchmarkRunReport: Typed report.
        """
        if value.get("schema_version") != REPORT_SCHEMA_VERSION:
            raise ReportSchemaError("unsupported Benchmark run report schema")
        if value.get("kind") != "benchmark_run_report":
            raise ReportSchemaError("document is not a Benchmark run report")
        return cls(
            task_run_id=str(value["task_run_id"]),
            experiment_id=str(value["experiment_id"]),
            task_id=str(value["task_id"]),
            agent_id=str(value["agent_id"]),
            repeat=int(value["repeat"]),
            outcome=str(value["outcome"]),
            identities=dict(value.get("identities") or {}),
            stages=tuple(value.get("stages") or ()),
            evaluation=value.get("evaluation"),
            usage=dict(value.get("usage") or {}),
            artifact_namespace=str(value.get("artifact_namespace") or ""),
        )


@dataclass(frozen=True)
class BenchmarkExperimentReport:
    """Reader-facing metrics and comparisons for one suite result."""

    experiment_id: str
    benchmark_plan_identity: str
    experiment_protocol_identity: str
    counts: Mapping[str, int]
    agent_metrics: tuple[AgentMetricSummary, ...]
    comparisons: tuple[AgentComparison, ...]
    run_summaries: tuple[Mapping[str, Any], ...]
    fairness_warnings: tuple[str, ...]
    schema_version: str = REPORT_SCHEMA_VERSION

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the experiment report without duplicating trajectories.

        Returns:
            dict[str, Any]: Safe versioned experiment report.
        """
        return safe_export(
            {
                "schema_version": self.schema_version,
                "kind": "benchmark_experiment_report",
                "experiment_id": self.experiment_id,
                "benchmark_plan_identity": self.benchmark_plan_identity,
                "experiment_protocol_identity": self.experiment_protocol_identity,
                "counts": dict(self.counts),
                "agent_metrics": [
                    item.to_safe_dict() for item in self.agent_metrics
                ],
                "comparisons": [
                    item.to_safe_dict() for item in self.comparisons
                ],
                "run_summaries": list(self.run_summaries),
                "fairness_warnings": list(self.fairness_warnings),
                "significance_claimed": False,
            }
        )

    @classmethod
    def from_dict(
        cls,
        value: Mapping[str, Any],
    ) -> "BenchmarkExperimentReport":
        """Load one supported experiment report document.

        Args:
            value (Mapping[str, Any]): Decoded JSON mapping.

        Raises:
            ReportSchemaError: Schema version or kind is unsupported.

        Returns:
            BenchmarkExperimentReport: Typed report.
        """
        if value.get("schema_version") != REPORT_SCHEMA_VERSION:
            raise ReportSchemaError("unsupported Benchmark experiment report schema")
        if value.get("kind") != "benchmark_experiment_report":
            raise ReportSchemaError("document is not a Benchmark experiment report")
        metrics = tuple(
            AgentMetricSummary(
                agent_id=str(item["agent_id"]),
                counts=dict(item["counts"]),
                eligible_count=int(item["eligible_count"]),
                success_rate_micro=item.get("success_rate_micro"),
                success_rate_macro=item.get("success_rate_macro"),
                duration_mean_ms=item.get("duration_mean_ms"),
                duration_median_ms=item.get("duration_median_ms"),
                duration_sample_variance=item.get(
                    "duration_sample_variance"
                ),
                wilson_interval_95=(
                    tuple(item["wilson_interval_95"])
                    if item.get("wilson_interval_95") is not None
                    else None
                ),
                usage_available_runs=int(item["usage_available_runs"]),
            )
            for item in value.get("agent_metrics") or ()
        )
        comparisons = tuple(
            AgentComparison(
                left_agent_id=str(item["left_agent_id"]),
                right_agent_id=str(item["right_agent_id"]),
                paired=bool(item["paired"]),
                matched_count=int(item["matched_count"]),
                unmatched_eligible_count=int(item["unmatched_eligible_count"]),
                left_wins=int(item["left_wins"]),
                right_wins=int(item["right_wins"]),
                ties=int(item["ties"]),
                significance_claimed=bool(item.get("significance_claimed", False)),
            )
            for item in value.get("comparisons") or ()
        )
        return cls(
            experiment_id=str(value["experiment_id"]),
            benchmark_plan_identity=str(value["benchmark_plan_identity"]),
            experiment_protocol_identity=str(
                value["experiment_protocol_identity"]
            ),
            counts=dict(value.get("counts") or {}),
            agent_metrics=metrics,
            comparisons=comparisons,
            run_summaries=tuple(value.get("run_summaries") or ()),
            fairness_warnings=tuple(value.get("fairness_warnings") or ()),
        )


def build_run_report(result: BenchmarkTaskResult) -> BenchmarkRunReport:
    """Derive a task-run report without mutating the runtime result.

    Args:
        result (BenchmarkTaskResult): Immutable execution facts.

    Raises:
        None.

    Returns:
        BenchmarkRunReport: Reader-facing run report.
    """
    return BenchmarkRunReport(
        task_run_id=result.task_run_id,
        experiment_id=result.experiment_id,
        task_id=result.task_id,
        agent_id=result.agent_id,
        repeat=result.repeat,
        outcome=result.outcome.value,
        identities={
            "agent_graph": result.agent_graph_identity,
            "benchmark_plan": result.benchmark_plan_identity,
            "experiment_protocol": result.experiment_protocol_identity,
            "task_instance": result.task_instance_identity,
        },
        stages=tuple(stage.to_safe_dict() for stage in result.stages),
        evaluation=(
            result.evaluation.to_safe_dict()
            if result.evaluation is not None
            else None
        ),
        usage=result.usage,
        artifact_namespace=result.artifact_namespace,
    )


def build_experiment_report(
    result: BenchmarkSuiteResult,
) -> BenchmarkExperimentReport:
    """Derive metrics and comparisons from immutable suite facts.

    Args:
        result (BenchmarkSuiteResult): Structured suite result.

    Raises:
        None.

    Returns:
        BenchmarkExperimentReport: Reader-facing experiment report.
    """
    return BenchmarkExperimentReport(
        experiment_id=result.experiment_id,
        benchmark_plan_identity=result.benchmark_plan_identity,
        experiment_protocol_identity=result.experiment_protocol_identity,
        counts=result.counts,
        agent_metrics=build_agent_metrics(result.results),
        comparisons=build_agent_comparisons(result.results),
        run_summaries=tuple(
            {
                "task_run_id": item.task_run_id,
                "task_id": item.task_id,
                "agent_id": item.agent_id,
                "repeat": item.repeat,
                "outcome": item.outcome.value,
                "report_ref": f"runs/{item.task_run_id}/run-report.json",
                "trajectory_ref": f"runs/{item.task_run_id}/trajectory.jsonl",
            }
            for item in result.results
        ),
        fairness_warnings=result.fairness_warnings,
    )


__all__ = [
    "BenchmarkExperimentReport",
    "BenchmarkRunReport",
    "REPORT_SCHEMA_VERSION",
    "ReportSchemaError",
    "build_experiment_report",
    "build_run_report",
]
