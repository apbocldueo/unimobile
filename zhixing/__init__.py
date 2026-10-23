"""Stable public surface for the ZhiXing Python distribution."""

from importlib.metadata import PackageNotFoundError, version

from zhixing.config.contracts import (
    AgentConfig,
    BenchmarkSuite,
    BenchmarkTask,
    ValidationIssue,
)
from zhixing.graph import AgentGraphBuilder, predicate
from zhixing.sdk import AgentRunConfig, ExecutableAgent, compile_agent, load_agent

try:
    __version__ = version("zhixing")
except PackageNotFoundError:  # Source checkout without an installed distribution.
    __version__ = "0+unknown"

__all__ = [
    "AgentConfig",
    "AgentGraphBuilder",
    "AgentRunConfig",
    "BenchmarkSuite",
    "BenchmarkTask",
    "ExecutableAgent",
    "ValidationIssue",
    "__version__",
    "compile_agent",
    "load_agent",
    "predicate",
]
