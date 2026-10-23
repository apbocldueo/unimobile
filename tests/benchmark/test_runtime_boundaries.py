"""Static architecture guards for the graph-native Benchmark Runtime."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _python_sources(root: Path) -> tuple[Path, ...]:
    """Return Python files under an architecture boundary.

    Args:
        root (Path): Package directory to inspect.

    Raises:
        None.

    Returns:
        tuple[Path, ...]: Stable ordered Python source paths.
    """
    return tuple(sorted(root.rglob("*.py")))


def test_benchmark_runtime_does_not_import_or_call_agent_runner() -> None:
    """Prove the new orchestration package has no AgentRunner dependency."""
    runtime_root = ROOT / "zhixing" / "benchmark" / "runtime"
    for source in _python_sources(runtime_root):
        tree = ast.parse(source.read_text(encoding="utf-8"))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, (ast.Import, ast.ImportFrom))
            for alias in node.names
        }
        called_names = {
            node.func.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "AgentRunner" not in imported_names
        assert "AgentRunner" not in called_names


def test_graph_kernel_has_no_benchmark_specific_dependency_or_branch() -> None:
    """Keep Benchmark, evaluator, dataset, and task routing above the Kernel."""
    source = ROOT / "zhixing" / "runtime" / "kernel.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imported_modules = {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any("benchmark" in name.lower() for name in imported_modules)
    string_literals = {
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    forbidden = ("benchmark", "dataset", "evaluator", "benchmarktask")
    assert not any(
        marker in literal
        for marker in forbidden
        for literal in string_literals
    )
