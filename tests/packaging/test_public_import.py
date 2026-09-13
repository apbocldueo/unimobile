from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import zhixing
from zhixing.config.contracts import AgentConfig, BenchmarkSuite, BenchmarkTask, ValidationIssue


ROOT = Path(__file__).resolve().parents[2]


def test_root_public_surface_is_deliberately_small():
    assert zhixing.AgentConfig is AgentConfig
    assert zhixing.BenchmarkTask is BenchmarkTask
    assert zhixing.BenchmarkSuite is BenchmarkSuite
    assert zhixing.ValidationIssue is ValidationIssue
    assert zhixing.__all__ == [
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


def test_root_import_has_no_optional_or_runtime_side_effects(tmp_path: Path):
    script = r"""
import pathlib
import sys
before = set(pathlib.Path('.').iterdir())
import zhixing
after = set(pathlib.Path('.').iterdir())
bad = sorted(name for name in sys.modules if name.split('.')[0] in {
    'torch', 'transformers', 'cv2', 'hmdriver2', 'openai', 'pyperclip', 'requests'
})
assert not bad, bad
assert before == after
assert not any(name.startswith(('zhixing.plugins', 'zhixing.devices')) for name in sys.modules)
"""
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
