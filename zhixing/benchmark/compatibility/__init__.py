"""Explicit compatibility bridges for legacy Benchmark behavior."""

from .legacy import build_legacy_evaluator_context, normalize_evaluation_result

__all__ = ["build_legacy_evaluator_context", "normalize_evaluation_result"]
