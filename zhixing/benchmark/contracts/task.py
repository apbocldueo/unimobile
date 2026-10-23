"""Benchmark task-template and materialized-instance contracts."""

from zhixing.config.contracts import BenchmarkSuite, BenchmarkTask

from .models import BenchmarkSuiteMap, TaskInstance

__all__ = [
    "BenchmarkSuite",
    "BenchmarkSuiteMap",
    "BenchmarkTask",
    "TaskInstance",
]
