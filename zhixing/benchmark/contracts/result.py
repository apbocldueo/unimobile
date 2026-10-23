"""Runtime result compatibility exports.

The dedicated result module gives callers a stable ownership boundary while
runtime and reporting schemas evolve independently.
"""

from ..runtime.models import (
    BenchmarkLifecycleEvent,
    BenchmarkOutcome,
    BenchmarkStageResult,
    BenchmarkStageStatus,
    BenchmarkSuiteResult,
    BenchmarkTaskResult,
    EvaluationNodeResult,
)

__all__ = [
    "BenchmarkLifecycleEvent",
    "BenchmarkOutcome",
    "BenchmarkStageResult",
    "BenchmarkStageStatus",
    "BenchmarkSuiteResult",
    "BenchmarkTaskResult",
    "EvaluationNodeResult",
]
