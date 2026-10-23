"""Task-local evaluator aggregation helpers."""

from __future__ import annotations

from typing import Iterable


def normalized_weighted_score(
    scores: Iterable[float],
    weights: Iterable[float],
) -> tuple[float, tuple[float, ...]]:
    """Compute normalized weighted score and per-child contributions.

    Args:
        scores (Iterable[float]): Child scores normalized to ``[0, 1]``.
        weights (Iterable[float]): Positive finite weights.

    Raises:
        ValueError: Lengths differ or a value is outside its valid range.

    Returns:
        tuple[float, tuple[float, ...]]: Aggregate and normalized contributions.
    """
    score_values = tuple(float(value) for value in scores)
    weight_values = tuple(float(value) for value in weights)
    if len(score_values) != len(weight_values) or not score_values:
        raise ValueError("scores and weights must have equal non-zero length")
    if any(not 0.0 <= value <= 1.0 for value in score_values):
        raise ValueError("scores must be normalized")
    if any(value <= 0.0 for value in weight_values):
        raise ValueError("weights must be positive")
    total = sum(weight_values)
    contributions = tuple(
        score * weight / total
        for score, weight in zip(score_values, weight_values, strict=True)
    )
    return sum(contributions), contributions


__all__ = ["normalized_weighted_score"]
