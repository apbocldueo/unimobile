"""Strict, side-effect-free configuration contracts for ZhiXing."""

from .agent import AgentConfig
from .benchmark import BenchmarkSuite, BenchmarkTask
from .diagnostics import ContractValidationError, ValidationIssue
from .loaders import (
    load_agent_yaml,
    load_benchmark_json,
    parse_agent_config,
    parse_benchmark_suite,
)
from .semantic import validate_agent_semantics, validate_benchmark_semantics

__all__ = [
    "AgentConfig",
    "BenchmarkSuite",
    "BenchmarkTask",
    "ContractValidationError",
    "ValidationIssue",
    "load_agent_yaml",
    "load_benchmark_json",
    "parse_agent_config",
    "parse_benchmark_suite",
    "validate_agent_semantics",
    "validate_benchmark_semantics",
]
