"""Honest descriptive metrics for Benchmark experiments."""

from __future__ import annotations

import math
import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Any, Iterable

from ..runtime.models import BenchmarkOutcome, BenchmarkTaskResult


@dataclass(frozen=True)
class AgentMetricSummary:
    """Outcome, duration, and uncertainty metrics for one Agent."""

    agent_id: str
    counts: dict[str, int]
    eligible_count: int
    success_rate_micro: float | None
    success_rate_macro: float | None
    duration_mean_ms: float | None
    duration_median_ms: float | None
    duration_sample_variance: float | None
    wilson_interval_95: tuple[float, float] | None
    usage_available_runs: int

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize explicit metrics and denominators.

        Returns:
            dict[str, Any]: Safe metric summary.
        """
        return {
            "agent_id": self.agent_id,
            "counts": dict(self.counts),
            "eligible_count": self.eligible_count,
            "success_rate_micro": self.success_rate_micro,
            "success_rate_macro": self.success_rate_macro,
            "duration_mean_ms": self.duration_mean_ms,
            "duration_median_ms": self.duration_median_ms,
            "duration_sample_variance": self.duration_sample_variance,
            "wilson_interval_95": (
                list(self.wilson_interval_95)
                if self.wilson_interval_95 is not None
                else None
            ),
            "usage_available_runs": self.usage_available_runs,
        }


@dataclass(frozen=True)
class AgentComparison:
    """Descriptive comparison for one pair of Agents."""

    left_agent_id: str
    right_agent_id: str
    paired: bool
    matched_count: int
    unmatched_eligible_count: int
    left_wins: int
    right_wins: int
    ties: int
    significance_claimed: bool = False

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize comparison facts without unsupported inference.

        Returns:
            dict[str, Any]: Safe comparison summary.
        """
        return {
            "left_agent_id": self.left_agent_id,
            "right_agent_id": self.right_agent_id,
            "paired": self.paired,
            "matched_count": self.matched_count,
            "unmatched_eligible_count": self.unmatched_eligible_count,
            "left_wins": self.left_wins,
            "right_wins": self.right_wins,
            "ties": self.ties,
            "significance_claimed": self.significance_claimed,
        }


def wilson_interval(passed: int, total: int, *, z: float = 1.96) -> tuple[float, float] | None:
    """Compute a Wilson score interval for eligible binary outcomes.

    Args:
        passed (int): Number of PASS results.
        total (int): PASS plus FAIL denominator.
        z (float): Normal critical value, defaulting to 95 percent.

    Raises:
        ValueError: Counts are inconsistent.

    Returns:
        tuple[float, float] | None: Bounded interval or None for no samples.
    """
    if passed < 0 or total < 0 or passed > total:
        raise ValueError("passed and total counts are inconsistent")
    if total == 0:
        return None
    proportion = passed / total
    denominator = 1.0 + (z * z / total)
    center = (proportion + z * z / (2.0 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1.0 - proportion) / total
            + z * z / (4.0 * total * total)
        )
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def _duration_ms(result: BenchmarkTaskResult) -> float:
    """Sum observable stage durations for one task run.

    Args:
        result (BenchmarkTaskResult): Structured task result.

    Raises:
        None.

    Returns:
        float: Non-negative total stage duration.
    """
    return sum(max(0.0, stage.duration_ms) for stage in result.stages)


def build_agent_metrics(
    results: Iterable[BenchmarkTaskResult],
) -> tuple[AgentMetricSummary, ...]:
    """Aggregate per-Agent metrics with explicit eligibility rules.

    Args:
        results (Iterable[BenchmarkTaskResult]): Experiment task results.

    Raises:
        None.

    Returns:
        tuple[AgentMetricSummary, ...]: Agent summaries sorted by identity.
    """
    grouped: dict[str, list[BenchmarkTaskResult]] = {}
    for result in results:
        grouped.setdefault(result.agent_id, []).append(result)
    summaries: list[AgentMetricSummary] = []
    for agent_id, agent_results in sorted(grouped.items()):
        counts = {outcome.value: 0 for outcome in BenchmarkOutcome}
        for result in agent_results:
            counts[result.outcome.value] += 1
        eligible = [
            result
            for result in agent_results
            if result.outcome in {BenchmarkOutcome.PASS, BenchmarkOutcome.FAIL}
        ]
        passed = sum(
            result.outcome is BenchmarkOutcome.PASS for result in eligible
        )
        task_rates: list[float] = []
        task_groups: dict[str, list[BenchmarkTaskResult]] = {}
        for result in eligible:
            task_groups.setdefault(result.task_id, []).append(result)
        for task_results in task_groups.values():
            task_rates.append(
                sum(
                    result.outcome is BenchmarkOutcome.PASS
                    for result in task_results
                )
                / len(task_results)
            )
        durations = [_duration_ms(result) for result in eligible]
        summaries.append(
            AgentMetricSummary(
                agent_id=agent_id,
                counts=counts,
                eligible_count=len(eligible),
                success_rate_micro=passed / len(eligible) if eligible else None,
                success_rate_macro=(
                    statistics.fmean(task_rates) if task_rates else None
                ),
                duration_mean_ms=(
                    statistics.fmean(durations) if durations else None
                ),
                duration_median_ms=(
                    statistics.median(durations) if durations else None
                ),
                duration_sample_variance=(
                    statistics.variance(durations)
                    if len(durations) >= 2
                    else None
                ),
                wilson_interval_95=wilson_interval(passed, len(eligible)),
                usage_available_runs=sum(bool(result.usage) for result in eligible),
            )
        )
    return tuple(summaries)


def build_agent_comparisons(
    results: Iterable[BenchmarkTaskResult],
) -> tuple[AgentComparison, ...]:
    """Compare Agents only on matching eligible TaskInstance conditions.

    Args:
        results (Iterable[BenchmarkTaskResult]): Experiment task results.

    Raises:
        None.

    Returns:
        tuple[AgentComparison, ...]: Stable pairwise descriptive comparisons.
    """
    eligible = [
        result
        for result in results
        if result.outcome in {BenchmarkOutcome.PASS, BenchmarkOutcome.FAIL}
    ]
    by_agent: dict[str, list[BenchmarkTaskResult]] = {}
    for result in eligible:
        by_agent.setdefault(result.agent_id, []).append(result)
    comparisons: list[AgentComparison] = []
    for left_id, right_id in combinations(sorted(by_agent), 2):
        left = {
            (
                item.benchmark_plan_identity,
                item.experiment_protocol_identity,
                item.task_id,
                item.task_instance_identity,
                item.repeat,
            ): item
            for item in by_agent[left_id]
        }
        right = {
            (
                item.benchmark_plan_identity,
                item.experiment_protocol_identity,
                item.task_id,
                item.task_instance_identity,
                item.repeat,
            ): item
            for item in by_agent[right_id]
        }
        keys = sorted(set(left) & set(right))
        left_wins = right_wins = ties = 0
        for key in keys:
            left_pass = left[key].outcome is BenchmarkOutcome.PASS
            right_pass = right[key].outcome is BenchmarkOutcome.PASS
            if left_pass == right_pass:
                ties += 1
            elif left_pass:
                left_wins += 1
            else:
                right_wins += 1
        comparisons.append(
            AgentComparison(
                left_agent_id=left_id,
                right_agent_id=right_id,
                paired=bool(keys),
                matched_count=len(keys),
                unmatched_eligible_count=(
                    len(left) + len(right) - 2 * len(keys)
                ),
                left_wins=left_wins,
                right_wins=right_wins,
                ties=ties,
            )
        )
    return tuple(comparisons)


__all__ = [
    "AgentComparison",
    "AgentMetricSummary",
    "build_agent_comparisons",
    "build_agent_metrics",
    "wilson_interval",
]
