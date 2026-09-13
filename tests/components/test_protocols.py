from __future__ import annotations

import inspect
import os
import subprocess
import sys
from pathlib import Path

import zhixing
from zhixing.components import (
    Action,
    ActionExecutor,
    BenchmarkInitializer,
    Component,
    ComponentRole,
    Device,
    DeviceObservation,
    Evaluator,
    Grounder,
    LLM,
    Memory,
    Perception,
    Planner,
    Reasoning,
    RuntimeContext,
    Verifier,
    get_role_descriptor,
)


ROOT = Path(__file__).resolve().parents[2]


class ExternalPerception:
    def invoke(self, input: DeviceObservation, runtime: RuntimeContext):
        from zhixing.components import PerceptionResult

        return PerceptionResult("external", input.screenshot_path)


def test_external_component_is_structural_and_synchronous():
    external = ExternalPerception()
    assert isinstance(external, Component)
    assert isinstance(external, Perception)
    result = external.invoke(DeviceObservation("recorded.png", 10, 20), RuntimeContext())
    assert result.mode == "external"
    assert not inspect.isawaitable(result)
    assert not inspect.isgenerator(result)


def test_role_catalog_covers_all_eleven_typed_roles():
    protocols = {
        ComponentRole.PERCEPTION: Perception,
        ComponentRole.PLANNER: Planner,
        ComponentRole.REASONING: Reasoning,
        ComponentRole.MEMORY: Memory,
        ComponentRole.VERIFIER: Verifier,
        ComponentRole.GROUNDER: Grounder,
        ComponentRole.LLM: LLM,
        ComponentRole.DEVICE: Device,
        ComponentRole.ACTION_EXECUTOR: ActionExecutor,
        ComponentRole.BENCHMARK_INITIALIZER: BenchmarkInitializer,
        ComponentRole.EVALUATOR: Evaluator,
    }
    assert len(protocols) == 11
    for role, protocol in protocols.items():
        descriptor = get_role_descriptor(role.value)
        assert descriptor.role is role
        assert descriptor.input_type is not object
        assert descriptor.output_type is not object
        invoke = inspect.getattr_static(protocol, "invoke")
        assert "input" in inspect.signature(invoke).parameters
        assert "runtime" in inspect.signature(invoke).parameters
    assert get_role_descriptor(ComponentRole.REASONING).output_type is Action


def test_public_import_has_no_optional_or_runtime_side_effects(tmp_path: Path):
    script = r"""
import pathlib
import sys
before = set(pathlib.Path('.').iterdir())
import zhixing
root_exports = list(zhixing.__all__)
import zhixing.components as components
after = set(pathlib.Path('.').iterdir())
bad = sorted(name for name in sys.modules if name.split('.')[0] in {
    'torch', 'transformers', 'cv2', 'hmdriver2', 'openai', 'pyperclip', 'requests'
})
assert not bad, bad
assert before == after
assert root_exports == [
    'AgentConfig',
    'AgentGraphBuilder',
    'AgentRunConfig',
    'BenchmarkSuite',
    'BenchmarkTask',
    'ExecutableAgent',
    'ValidationIssue',
    '__version__',
    'compile_agent',
    'load_agent',
    'predicate',
]
assert not any(name.startswith('zhixing.plugins') for name in sys.modules)
assert len(components.ComponentRole) == 11
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
