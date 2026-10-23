"""End-to-end tests for the public graph-native Python SDK."""

from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

import pytest

from zhixing import AgentRunConfig, compile_agent, load_agent
from zhixing.agents import build_builtin_mobile_agent_graph
from zhixing.components import ActionType, RunStatus
from zhixing.graph import compile_agent_yaml
from zhixing.catalog import BuiltInComponentResolver
from zhixing.runtime import GraphBindingError
from examples.sdk.android_content_verified_agent import (
    build_android_content_verified_agent,
)


class ScriptedLLM:
    """Emit one physical action followed by DONE for every fresh run."""

    def __init__(self) -> None:
        """Initialize a fresh per-run response cursor.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.index = 0

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Return the next parser-compatible action.

        Args:
            prompt (str): Rendered UniversalReason prompt.
            images (list[str] | None): Current screenshot.

        Raises:
            None.

        Returns:
            str: HOME on the first call and DONE on the second.
        """
        del prompt, images
        self.index += 1
        if self.index == 1:
            return '{"action":"home","arguments":{},"thought":"first action"}'
        return '{"action":"done","arguments":{},"thought":"task complete"}'


class ScriptedContentLLM:
    """Launch an app and tap once; the Verifier produces terminal DONE."""

    def __init__(self) -> None:
        """Initialize the deterministic response cursor.

        Args:
            None.

        Raises:
            None.

        Returns:
            None: Initializes the scripted model.
        """
        self.index = 0

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Return one setup action followed by one content-changing action.

        Args:
            prompt (str): Rendered reasoning prompt.
            images (list[str] | None): Current screenshot path.

        Raises:
            AssertionError: The graph asks the model for an unnecessary third action.

        Returns:
            str: Parser-compatible START_APP or TAP response.
        """
        del prompt, images
        self.index += 1
        if self.index == 1:
            return (
                '{"action":"start_app","arguments":{"app":"com.android.camera2"},'
                '"thought":"open target app"}'
            )
        if self.index == 2:
            return (
                '{"action":"tap","arguments":{"x":50,"y":150},'
                '"thought":"create one content item"}'
            )
        raise AssertionError("Verifier should terminate without a third model call")


@dataclass(frozen=True)
class FakeShellResult:
    """Represent one successful fake Android shell response."""

    output: str
    exit_code: int = 0


class FakeAndroidDevice:
    """Write observable artifacts and record Android actions."""

    serial = "fake-sdk-android"
    platform = "android"
    w = 100
    h = 200

    def __init__(self, content_outputs: list[str] | None = None) -> None:
        """Initialize call recording.

        Args:
            content_outputs (list[str] | None): Optional content-query results.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls: list[tuple[object, ...]] = []
        self.content_outputs = list(content_outputs or [])

    def screenshot(self, path: str) -> str:
        """Write a screenshot-shaped test artifact.

        Args:
            path (str): Host artifact destination.

        Raises:
            OSError: Test storage cannot be written.

        Returns:
            str: Destination path.
        """
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        self.calls.append(("screenshot", path))
        return path

    def go_home(self) -> None:
        """Record one physical HOME action.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("home",))

    def wait(self, seconds: float) -> None:
        """Record a requested device wait.

        Args:
            seconds (float): Wait duration.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("wait", seconds))

    def start_app(self, app: str) -> None:
        """Record one application launch.

        Args:
            app (str): Application package or stable identifier.

        Raises:
            None.

        Returns:
            None: Records the fake device effect.
        """
        self.calls.append(("start_app", app))

    def tap(self, x: int, y: int) -> None:
        """Record one coordinate tap.

        Args:
            x (int): Horizontal coordinate.
            y (int): Vertical coordinate.

        Raises:
            None.

        Returns:
            None: Records the fake device effect.
        """
        self.calls.append(("tap", x, y))

    def shell(self, command: str) -> FakeShellResult:
        """Return the next content-provider query response.

        Args:
            command (str): Validated Android shell command.

        Raises:
            AssertionError: A non-content query or exhausted script is used.

        Returns:
            FakeShellResult: Deterministic provider output.
        """
        assert command.startswith("content query --uri ")
        assert self.content_outputs
        self.calls.append(("shell", command))
        return FakeShellResult(self.content_outputs.pop(0))


def _resolver_factory() -> BuiltInComponentResolver:
    """Create fresh components and a fresh scripted model for one run.

    Args:
        None.

    Raises:
        None.

    Returns:
        BuiltInComponentResolver: Run-scoped built-in resolver.
    """
    return BuiltInComponentResolver(
        dependency_provider={"llm": ScriptedLLM()},
    )


def _content_resolver_factory() -> BuiltInComponentResolver:
    """Create run-scoped components for content-verified graph tests.

    Args:
        None.

    Raises:
        None.

    Returns:
        BuiltInComponentResolver: Resolver with deterministic action decisions.
    """
    return BuiltInComponentResolver(
        dependency_provider={"llm": ScriptedContentLLM()},
    )


def test_yaml_and_sdk_define_the_same_executable_agentgraph() -> None:
    """Fix the golden semantic identity across both authoring surfaces.

    Args:
        None.

    Raises:
        AssertionError: Compilation or canonical equivalence fails.

    Returns:
        None.
    """
    compiled = compile_agent_yaml("examples/graphs/builtin_android_agent.yaml")
    assert compiled.is_success
    assert compiled.graph is not None
    sdk_graph = build_builtin_mobile_agent_graph()
    assert compiled.graph.canonical_mapping() == sdk_graph.canonical_mapping()
    assert (
        compiled.graph.canonical_hash()
        == sdk_graph.canonical_hash()
        == "sha256:4f60da0883b13c82accbc1a13ee4f10e1f56407cde8904efd1cae291fe5123e6"
    )


def test_content_verified_yaml_and_sdk_share_canonical_hash() -> None:
    """Keep the GUI/YAML graph and Python authoring surface semantically equal.

    Args:
        None.

    Raises:
        AssertionError: Compilation or canonical equivalence fails.

    Returns:
        None.
    """
    compiled = compile_agent_yaml(
        "examples/graphs/android_content_verified_agent.yaml"
    )
    assert compiled.is_success
    assert compiled.graph is not None
    sdk_graph = build_android_content_verified_agent()
    assert compiled.graph.canonical_mapping() == sdk_graph.canonical_mapping()
    assert compiled.graph.canonical_hash() == sdk_graph.canonical_hash()


@pytest.mark.fake_device_integration
def test_content_verifier_terminates_graph_after_confirmed_delta(tmp_path) -> None:
    """Stop through Verifier and DONE after one independently observed addition.

    Args:
        tmp_path (pathlib.Path): Isolated artifact root.

    Raises:
        AssertionError: Verifier feedback or deterministic termination is broken.

    Returns:
        None.
    """
    device = FakeAndroidDevice(
        content_outputs=[
            "Row: 0 _id=7",
            "Row: 0 _id=7\nRow: 1 _id=8",
        ]
    )
    agent = compile_agent(
        build_android_content_verified_agent(),
        resolver_factory=_content_resolver_factory,
    )
    result = agent.run(
        "create one media item",
        AgentRunConfig(
            artifact_root=tmp_path,
            max_steps=5,
            metadata={
                "android_content_baselines": {
                    "target_content": ["7"],
                }
            },
        ),
        device=device,
    )
    assert result.status is RunStatus.SUCCESS
    assert [item.action.type for item in result.action_results] == [
        ActionType.START_APP,
        ActionType.TAP,
        ActionType.DONE,
    ]
    completed = [event.node_id for event in result.events if event.kind == "complete"]
    assert completed.count("verifier") == 2
    assert completed.count("terminal_action") == 1
    assert [call[0] for call in device.calls].count("shell") == 2


@pytest.mark.fake_device_integration
def test_executable_agent_runs_full_feedback_loop_on_fake_android(tmp_path) -> None:
    """Execute observe-perceive-reason-act-reobserve-DONE via the public SDK.

    Args:
        tmp_path (pathlib.Path): Isolated artifact root.

    Raises:
        AssertionError: The production topology or evidence is incomplete.

    Returns:
        None.
    """
    device = FakeAndroidDevice()
    agent = compile_agent(
        build_builtin_mobile_agent_graph(),
        resolver_factory=_resolver_factory,
    )
    result = agent.run(
        "返回桌面后结束",
        AgentRunConfig(artifact_root=tmp_path, max_steps=3),
        device=device,
    )
    assert result.status is RunStatus.SUCCESS
    assert [item.action.type for item in result.action_results] == [
        ActionType.KEY,
        ActionType.DONE,
    ]
    assert [call[0] for call in device.calls] == [
        "screenshot",
        "home",
        "screenshot",
    ]
    completed = [event.node_id for event in result.events if event.kind == "complete"]
    for node_id in (
        "observe",
        "perception",
        "reasoning",
        "action_request",
        "action_executor",
    ):
        assert completed.count(node_id) == 2
    assert len(
        result.state.strategy_state["runtime.memory.seen.memory"]
    ) == 2
    assert (tmp_path / result.run_id / "manifest.json").is_file()


@pytest.mark.fake_device_integration
def test_executable_agent_rebinds_memory_and_fallback_state_per_run(tmp_path) -> None:
    """Run one compiled Agent twice without leaking transient state.

    Args:
        tmp_path (pathlib.Path): Isolated artifact root.

    Raises:
        AssertionError: A second run inherits model, Memory, or run identity.

    Returns:
        None.
    """
    agent = compile_agent(
        build_builtin_mobile_agent_graph(),
        resolver_factory=_resolver_factory,
    )
    first = agent.run(
        "first",
        AgentRunConfig(artifact_root=tmp_path),
        device=FakeAndroidDevice(),
    )
    second = agent.run(
        "second",
        AgentRunConfig(artifact_root=tmp_path),
        device=FakeAndroidDevice(),
    )
    assert first.run_id != second.run_id
    assert [item.action.type for item in first.action_results] == [
        ActionType.KEY,
        ActionType.DONE,
    ]
    assert [item.action.type for item in second.action_results] == [
        ActionType.KEY,
        ActionType.DONE,
    ]
    assert first.state.current_task.instruction == "first"
    assert second.state.current_task.instruction == "second"


def test_load_agent_and_binding_failure_are_explicit_and_secret_safe(tmp_path) -> None:
    """Load YAML normally and normalize a missing-secret binding failure.

    Args:
        tmp_path (pathlib.Path): Isolated artifact root.

    Raises:
        AssertionError: YAML loading or safe failure normalization differs.

    Returns:
        None.
    """
    agent = load_agent("examples/graphs/builtin_android_agent.yaml")
    result = agent.run(
        "task",
        AgentRunConfig(artifact_root=tmp_path),
        device=FakeAndroidDevice(),
    )
    assert result.status is RunStatus.FAILURE
    assert result.kernel_status == "not_started"
    assert result.error_details["code"] == "sdk.binding_failed"
    assert "openai_api_key" not in result.error


def test_load_agent_rejects_unsupported_legacy_strategy_yaml() -> None:
    """Direct legacy AgentConfig users to the preserved old entry point.

    Args:
        None.

    Raises:
        AssertionError: The legacy config is silently approximated as contract 1.1.

    Returns:
        None.
    """
    with pytest.raises(GraphBindingError, match="run.py"):
        load_agent("examples/agent_android_classic.yaml")
