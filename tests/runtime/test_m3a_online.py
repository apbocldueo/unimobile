"""Differential online tests against pinned, unchanged official M3A definitions."""

from __future__ import annotations

import abc
import ast
import copy
import dataclasses
import hashlib
import json
import logging
import math
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Optional

import cv2
import numpy as np
import pytest
from PIL import Image

from zhixing.components import RunStatus, RuntimeContext
from zhixing.m3a import build_m3a_graph
from zhixing.graph import load_graph_yaml
from zhixing.plugins.agent.m3a import source
from zhixing.plugins.agent.m3a.environment import M3AEnvironment
from zhixing.plugins.agent.m3a.types import M3AReply
from zhixing.sdk import AgentRunConfig, compile_agent


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/m3a"
GOAL = "Open settings and inspect the button"


def original(filename, namespace, names=None):
    """Load original definitions unchanged, replacing only external imports.

    Args:
        filename: Pinned fixture filename without .txt.
        namespace: Explicit external libraries and service doubles.
        names: Optional source definition selection.
    Raises:
        Exception: The unmodified definitions do not compile or initialize.
    Returns:
        SimpleNamespace: Executable original definitions, without network/device imports.
    """
    tree = ast.parse((FIXTURES / (filename + ".txt")).read_text())
    body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
            and (names is None or getattr(node, "name", None) in names)]
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *body], type_ignores=[])),
                 "official/" + filename, "exec"), namespace)
    return SimpleNamespace(**namespace)


class AdbSpy:
    """Record only the external device primitives reached by original actuation."""

    def __init__(self, env):
        """Bind the recorder. Args: env: Fake external environment. Returns: None."""
        self.env = env

    def __getattr__(self, name):
        """Produce a recorder. Args: name: Original helper name. Returns: Callable: Spy."""
        def call(*args, **kwargs):
            """Record safe primitive arguments. Args: args,kwargs: Source call. Returns: Any: Command for generators."""
            values = args[:-1] if args and args[-1] is self.env.controller else args
            self.env.events.append((name, values, kwargs))
            return (name, *values, kwargs) if name.startswith("generate_") else None
        return call


class FakeEnv:
    """Only external AndroidWorld I/O is fake; execution uses the original method."""

    logical_screen_size = (240, 400)
    orientation = 0
    physical_frame_boundary = (0, 0, 240, 400)

    def __init__(self, *, fail_actions=(), orientation=0):
        """Prepare deterministic observations. Args: fail_actions: Calls to fail; orientation: Source geometry. Returns: None."""
        self.events, self.actions, self.snapshots = [], [], []
        self.fail_actions = set(fail_actions)
        self.orientation = orientation
        self.controller = object()
        self.interaction_cache = ""
        adb = AdbSpy(self)
        clock = SimpleNamespace(sleep=self.sleep)
        self.actuation = original("actuation.py", {"copy": copy, "logging": logging,
            "time": clock, "adb_utils": adb, "json_action": source}, {"execute_adb_action"})
        module = ast.parse((FIXTURES / "interface.py.txt").read_text())
        cls = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "AsyncAndroidEnv")
        method = next(node for node in cls.body if isinstance(node, ast.FunctionDef) and node.name == "execute_action")
        future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
        ns = {"json_action": source, "actuation": self.actuation}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[future, method], type_ignores=[])), "official/interface.py", "exec"), ns)
        self.original_execute = ns["execute_action"]

    def sleep(self, seconds):
        """Record source timing. Args: seconds: Pause. Returns: None."""
        self.events.append(("sleep", seconds))

    def reset(self, go_home=False):
        """Reset external state. Args: go_home: Source setting. Returns: None."""
        self.events.append(("reset", go_home))
        self.interaction_cache = ""

    def hide_automation_ui(self):
        """Record original overlay setup. Returns: None."""
        self.events.append(("hide",))

    def display_message(self, message, header=""):
        """Record source answer display. Args: message,header: Original strings. Returns: None."""
        self.events.append(("display", message, header))

    def get_state(self, wait_to_stabilize=False):
        """Return a fresh ordered UI/pixel state. Args: wait_to_stabilize: Source policy. Returns: State: Portable test state."""
        index = len(self.snapshots)
        self.events.append(("observe", wait_to_stabilize))
        # Invisible index 0 remains in the source list. Fresh execution state
        # moves index 1, exposing accidental use of the stale before coordinates.
        elements = [source.UIElement(text="hidden", is_visible=False,
                        bbox_pixels=source.BoundingBox(5, 20, 5, 20)),
                    source.UIElement(text=f'Button {index}', content_description='control',
                        hint_text='Search', tooltip='Help', is_visible=True, is_clickable=True,
                        is_editable=True, is_long_clickable=True, is_scrollable=True,
                        is_focusable=True, is_selected=False, is_checked=False,
                        bbox_pixels=source.BoundingBox(30 + index, 120 + index, 50, 130)),
                    source.UIElement(text="offscreen", is_visible=True,
                        bbox_pixels=source.BoundingBox(300, 340, 20, 40)),
                    source.UIElement(text="no bounds", is_visible=True)]
        pixels = np.zeros((400, 240, 3), dtype=np.uint8)
        pixels[:, :, 0] = index % 255
        pixels[:, :, 1] = np.arange(240, dtype=np.uint8)[None, :]
        state = SimpleNamespace(pixels=pixels, ui_elements=elements)
        self.snapshots.append(state)
        return state

    def execute_action(self, action):
        """Invoke original AsyncEnv execution. Args: action: Source JSONAction. Raises: ValueError: Injected error. Returns: None."""
        self.actions.append(action.as_dict())
        if len(self.actions) in self.fail_actions:
            raise ValueError("external device action failed")
        return self.original_execute(self, action)


class ScriptedModel:
    """The external model alone is scripted; image and prompt construction are real."""

    def __init__(self, replies):
        """Copy replies. Args: replies: M3AReply sequence. Returns: None."""
        self.replies, self.calls = list(replies), []

    def predict_mm(self, prompt, images):
        """Record exact inputs. Args: prompt,images: Source multimodal request. Raises: AssertionError: Extra call. Returns: tuple: Original wrapper result."""
        self.calls.append((prompt, [image.copy() for image in images]))
        assert self.replies, "unexpected extra model call"
        reply = self.replies.pop(0)
        # This private object must never appear in evidence or diagnostics.
        return reply.text, reply.is_safe, ({"Authorization": "private-response-sentinel"} if reply.has_response else None)


def run_original(replies, *, max_rounds=5, env=None, pause=1.0, after=2.0, guidelines=None, start_on_home_screen=False):
    """Execute the untouched original Agent and episode runner with external doubles.

    Args:
        replies: Scripted external model replies.
        max_rounds: Official step budget.
        env: Optional failure-injecting external environment.
        pause: Original transition_pause.
        after: Original wait_after_action_seconds.
        guidelines: Optional original task guidelines.
        start_on_home_screen: Original reset setting.
    Returns:
        tuple: Source episode result or exception, Agent, model, environment.
    """
    env, model = env or FakeEnv(), ScriptedModel(replies)
    clock = SimpleNamespace(sleep=env.sleep, time=lambda: 0)
    common = {"abc": abc, "dataclasses": dataclasses, "logging": logging, "time": clock,
              "Any": Any, "Optional": Optional, "Callable": Callable}
    base = original("base_agent.py", dict(common), {"AgentInteractionResult", "EnvironmentInteractingAgent"})
    ui = original("representation_utils.py", dict(common), {"BoundingBox", "UIElement"})
    utils = original("m3a_utils.py", {**common, "ast": ast, "json": json, "re": re,
        "math": math, "np": np, "cv2": cv2, "representation_utils": ui})
    agent_utils = original("agent_utils.py", {**common, "ast": ast, "json": json, "re": re}, {"extract_json"})
    json_action = original("json_action.py", {**common, "json": json})
    module = original("m3a.py", {**common, "base_agent": base, "m3a_utils": utils,
        "agent_utils": agent_utils, "json_action": json_action, "representation_utils": ui})
    agent = module.M3A(env, model, wait_after_action_seconds=after)
    agent.transition_pause = pause
    agent.set_task_guidelines(guidelines)
    runner = original("episode_runner.py", {**common, "base_agent": base,
        "constants": SimpleNamespace(STEP_NUMBER="step_number"),
        "termcolor": SimpleNamespace(colored=lambda text, *args: text)})
    try:
        result = runner.run_episode(GOAL, agent, max_n_steps=max_rounds,
            start_on_home_screen=start_on_home_screen, print_fn=lambda text: None)
    except Exception as error:
        result = error
    return result, agent, model, env


def run_graph(tmp_path, replies, *, max_rounds=5, env=None, pause=1.0, after=2.0, guidelines=None, graph=None, start_on_home_screen=False):
    """Run production SDK and kernel with original-compatible external services.

    Args:
        tmp_path: Real artifact destination.
        replies: Scripted external model replies.
        max_rounds: Independent official decision budget.
        env: Optional controlled external environment.
        pause: Original transition_pause.
        after: Original post-action pause.
        guidelines: Optional original prompt guidelines.
        graph: Optional actual YAML-compiled graph.
        start_on_home_screen: Original reset setting.
    Returns:
        tuple: Actual RunResult, model, environment and RuntimeContext.
    """
    env, model = env or FakeEnv(), ScriptedModel(replies)
    graph = graph or build_m3a_graph(max_rounds=max_rounds, transition_pause=pause,
        wait_after_action_seconds=after, additional_guidelines=guidelines, start_on_home_screen=start_on_home_screen)
    context = RuntimeContext(max_steps=max_rounds + 1)
    result = compile_agent(graph, dependencies={"llm": model}).run(GOAL,
        AgentRunConfig(artifact_root=tmp_path, max_steps=max_rounds + 1, include_ui_tree=False),
        device=M3AEnvironment(env, sleep=env.sleep), runtime=context)
    return result, model, env, context


def decision(action, reason="perform the action"):
    """Build a source reply. Args: action: JSON fields; reason: Model text. Returns: M3AReply: Scripted reply."""
    return M3AReply("Reason: " + reason + "\nAction: " + json.dumps(action))


COMPLETE = decision({"action_type": "status", "goal_status": "complete"})
CLICK = decision({"action_type": "click", "index": 1})


def assert_parity(tmp_path, replies, **options):
    """Compare full source calls, state transitions, images and history to the graph.

    Args:
        tmp_path: Real graph artifact root.
        replies: Shared external model script.
        **options: Shared source timing, bounds or guideline settings.
    Raises:
        AssertionError: Any externally observable online behavior differs.
    Returns:
        tuple: Production result, source Agent, source model and graph context.
    """
    expected, agent, model, env = run_original(replies, **options)
    actual, actual_model, actual_env, context = run_graph(tmp_path, replies, **options)
    assert actual_env.events == env.events
    assert actual_env.actions == env.actions
    assert actual_env.interaction_cache == env.interaction_cache
    assert len(actual_model.calls) == len(model.calls)
    for (prompt, images), (expected_prompt, expected_images) in zip(actual_model.calls, model.calls):
        assert prompt == expected_prompt
        assert len(images) == len(expected_images)
        for image, expected_image in zip(images, expected_images):
            np.testing.assert_array_equal(image, expected_image)
    if isinstance(expected, Exception):
        assert actual.status is RunStatus.FAILURE
        return actual, agent, model, context
    assert actual.status is (RunStatus.SUCCESS if expected.done and agent.history[-1]['action_output_json'].goal_status == 'complete'
                             else RunStatus.FAILURE if expected.done else RunStatus.STEP_LIMIT), actual.error
    payload = context.state.last_action_result.metadata["m3a"]
    assert payload["episode_done"] == expected.done
    assert payload["decision_rounds"] == len(expected.step_data.get("action_prompt", []))
    assert len(payload["history"]) == len(agent.history)
    for index, item in enumerate(payload["episode"]):
        for key in ("action_prompt", "action_output", "action_reason", "summary_prompt", "summary"):
            assert item[key] == expected.step_data[key][index]
        action = expected.step_data['action_output_json'][index]
        assert item['action_output_json'] == (action.as_dict() if action else None)
        for key in ("raw_screenshot", "before_screenshot_with_som", "after_screenshot_with_som"):
            pixels = expected.step_data[key][index]
            if pixels is not None:
                with Image.open(item[key]) as image:
                    np.testing.assert_array_equal(np.array(image), pixels)
    assert [item['summary'] for item in payload['history']] == [item['summary'] for item in agent.history]
    evidence = (context.artifacts.namespace / "m3a-episode.json").read_text()
    assert "private-response-sentinel" not in evidence
    assert "Authorization" not in evidence
    return actual, agent, model, context


@pytest.mark.fake_device_integration
def test_normal_complete_matches_source(tmp_path):
    """Compare two model phases, refreshed targets, copy quirks and terminal history. Args: tmp_path: Artifacts. Returns: None."""
    assert_parity(tmp_path, [CLICK, M3AReply("Opened settings."), COMPLETE], max_rounds=3)


@pytest.mark.parametrize("action", [
    {"action_type": "answer", "text": "Here is the answer"},
    {"action_type": "input_text", "index": 1, "text": "hello", "clear_text": True},
    {"action_type": "input_text", "text": ""},
    {"action_type": "scroll", "index": 1, "direction": "down"},
    {"action_type": "scroll", "index": 0, "direction": "up"},
    {"action_type": "long_press", "index": 1},
    {"action_type": "double_tap", "x": 20, "y": 30},
    {"action_type": "swipe", "direction": "right"},
    {"action_type": "navigate_home"}, {"action_type": "navigate_back"},
    {"action_type": "keyboard_enter"}, {"action_type": "open_app", "app_name": "Settings"},
    {"action_type": "wait"}, {"action_type": "unknown"},
])
def test_original_action_semantics(tmp_path, action):
    """Compare each supported source action through original execution. Args: tmp_path: Artifacts; action: Source action. Returns: None."""
    assert_parity(tmp_path, [decision(action), M3AReply("Step done."), COMPLETE], max_rounds=3)


@pytest.mark.parametrize("reply", [
    M3AReply("wrong format"), M3AReply('Reason: x\nAction: {bad}'),
    decision({"action_type": "not_supported"}), decision({"action_type": "click", "index": 999}),
    M3AReply('Reason: \nAction: {"action_type":"wait"}'),
    decision({"action_type": "scroll", "direction": "invalid"}),
])
def test_invalid_output_feedback_continues_without_resampling(tmp_path, reply):
    """Preserve source fixed feedback and next-round history. Args: tmp_path: Artifacts; reply: Invalid prediction. Returns: None."""
    assert_parity(tmp_path, [reply, COMPLETE], max_rounds=2)


@pytest.mark.parametrize("reply", [
    decision({"action_type": "status", "goal_status": "infeasible"}),
    M3AReply("blocked", is_safe=False),
    decision({"action_type": "status"}),
])
def test_source_termination_including_permissive_status(tmp_path, reply):
    """Preserve source stopping while separately mapping agent infeasibility. Args: tmp_path: Artifacts; reply: Terminal prediction. Returns: None."""
    assert_parity(tmp_path, [reply], max_rounds=2)


@pytest.mark.parametrize("summary", [M3AReply("error", has_response=False), M3AReply("blocked", is_safe=False), M3AReply("")])
def test_summary_fallback_and_safety(tmp_path, summary):
    """Preserve original summary failure/safety handling. Args: tmp_path: Artifacts; summary: External reply. Returns: None."""
    assert_parity(tmp_path, [CLICK, summary, COMPLETE], max_rounds=2)


@pytest.mark.parametrize("action", [{"action_type": "click", "index": -1}, {"action_type": "click"}])
def test_execution_failure_does_not_enter_history(tmp_path, action):
    """Compare real source actuation validation and history omission. Args: tmp_path: Artifacts; action: Invalid execution input. Returns: None."""
    assert_parity(tmp_path, [decision(action), COMPLETE], max_rounds=2)


def test_source_decision_response_failure_is_fatal(tmp_path):
    """Distinguish transport failure from valid empty output. Args: tmp_path: Artifacts. Returns: None."""
    assert_parity(tmp_path, [M3AReply("error", has_response=False)], max_rounds=2)


@pytest.mark.parametrize("pause,orientation", [(None, 0), (0.0, 1), (1.0, 2), (1.0, 3)])
def test_geometry_timing_and_guidelines_match_source(tmp_path, pause, orientation):
    """Compare orientation and original timing/guidelines. Args: tmp_path: Artifacts; pause,orientation: Source settings. Returns: None."""
    expected, agent, model, env = run_original([CLICK, M3AReply("Done."), COMPLETE], max_rounds=2,
        env=FakeEnv(orientation=orientation), pause=pause, guidelines=["Use the named app."])
    actual, actual_model, actual_env, _ = run_graph(tmp_path, [CLICK, M3AReply("Done."), COMPLETE], max_rounds=2,
        env=FakeEnv(orientation=orientation), pause=pause, guidelines=["Use the named app."])
    assert actual.status is RunStatus.SUCCESS, actual.error
    assert actual_env.events == env.events
    for (prompt, images), (expected_prompt, expected_images) in zip(actual_model.calls, model.calls):
        assert prompt == expected_prompt
        for image, expected_image in zip(images, expected_images):
            np.testing.assert_array_equal(image, expected_image)


@pytest.mark.parametrize("rounds", [0, 1, 3])
def test_decision_budget_finishes_last_summary_and_flushes_memory(tmp_path, rounds):
    """Verify budget counts full rounds and source zero budget skips reset. Args: tmp_path: Artifacts; rounds: Bound. Returns: None."""
    assert_parity(tmp_path, [CLICK, M3AReply("Same result.")] * rounds, max_rounds=rounds)


def test_long_history_is_not_default_ten_round_window(tmp_path):
    """Ensure the reused Memory preserves all source summaries. Args: tmp_path: Artifacts. Returns: None."""
    assert_parity(tmp_path, [decision({"action_type": "wait"}), M3AReply("Repeated.")] * 12 + [COMPLETE], max_rounds=13)


def test_pinned_source_provenance():
    """Verify every original fixture. Raises: AssertionError: Hash drift. Returns: None."""
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    for path, item in provenance["files"].items():
        assert hashlib.sha256((FIXTURES / (Path(path).name + ".txt")).read_bytes()).hexdigest() == item["sha256"]


def test_selected_algorithms_preserve_original_executable_statements():
    """Compare all selected algorithm ASTs independently of behavioral examples.

    Raises:
        AssertionError: Any executable statement other than lazy imports/name differs.
    Returns:
        None.
    """
    production = ast.parse(Path(source.__file__).read_text())
    definitions = {getattr(node, "name", None) or (node.targets[0].id if isinstance(node, ast.Assign)
        and isinstance(node.targets[0], ast.Name) else None): node for node in production.body}
    provenance = json.loads((FIXTURES / "provenance.json").read_text())

    class Normalize(ast.NodeTransformer):
        """Remove only supplemental docstrings and lazy OpenCV imports."""
        def visit_FunctionDef(self, node):
            """Normalize one definition. Args: node: Function AST. Returns: AST: Comparison form."""
            self.generic_visit(node)
            node.body = [item for item in node.body if not isinstance(item, ast.Import)]
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
                node.body.pop(0)
            return node

    for path, item in provenance["files"].items():
        if not item["definitions"]:
            continue
        tree = ast.parse((FIXTURES / (Path(path).name + ".txt")).read_text())
        for node in tree.body:
            name = getattr(node, "name", None) or (node.targets[0].id if isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Name) else None)
            if name not in item["definitions"]:
                continue
            mapped = "extract_action_json" if path.endswith("agents/agent_utils.py") and name == "extract_json" else name
            expected = copy.deepcopy(node)
            if isinstance(expected, ast.FunctionDef):
                expected.name = mapped
            assert ast.dump(Normalize().visit(copy.deepcopy(definitions[mapped]))) == ast.dump(Normalize().visit(expected)), (path, name)


def test_yaml_same_graph_and_actual_execution(tmp_path):
    """Compile the editable YAML and execute its full online path. Args: tmp_path: Artifacts. Returns: None."""
    compiled = load_graph_yaml(ROOT / "examples/graphs/m3a_online.yaml")
    assert compiled.is_success
    assert compiled.graph.canonical_hash() == build_m3a_graph().canonical_hash()
    result, model, env, context = run_graph(tmp_path, [CLICK, M3AReply("Opened."), COMPLETE], max_rounds=30, graph=compiled.graph)
    assert result.status is RunStatus.SUCCESS, result.error
    assert len(model.calls) == 3
    assert len(context.state.last_action_result.metadata["m3a"]["history"]) == 2


def test_run_isolation_and_original_environment_hook(tmp_path):
    """Run one compiled graph twice and test original external termination timing. Args: tmp_path: Artifacts. Returns: None."""
    graph = build_m3a_graph(max_rounds=2)
    for index in range(2):
        env, model, hook_calls = FakeEnv(), ScriptedModel([CLICK, M3AReply("Done.")]), []
        def stop(environment):
            """Stop after one full round. Args: environment: Original AsyncEnv. Returns: bool: Stop."""
            hook_calls.append((len(environment.actions), len(model.calls)))
            return True
        result = compile_agent(graph, dependencies={"llm": model}).run(GOAL,
            AgentRunConfig(artifact_root=tmp_path / str(index), max_steps=3),
            device=M3AEnvironment(env, sleep=env.sleep, termination_fn=stop))
        assert result.status is RunStatus.SUCCESS, result.error
        assert hook_calls == [(1, 2)]
        assert "You just started, no action has been performed yet." in model.calls[0][0]


@pytest.mark.parametrize("options", [
    {"max_rounds": True}, {"max_rounds": -1}, {"max_rounds": 1000},
    {"transition_pause": float("nan")}, {"wait_after_action_seconds": None},
    {"additional_guidelines": "wrong"}, {"model_params": {"api_key": "must-not-be-config"}},
])
def test_factory_rejects_invalid_configuration(options):
    """Reject invalid bounds and secret-bearing model config. Args: options: Invalid config. Returns: None."""
    with pytest.raises(ValueError):
        build_m3a_graph(**options)


def test_default_model_adapter_is_lazy_and_reuses_original_wrapper(tmp_path, monkeypatch):
    """Verify default adapter delegation without importing the optional package. Args: tmp_path: Image; monkeypatch: Module injection. Returns: None."""
    import sys
    from zhixing.plugins.llm.m3a_llm import M3ALLM

    backend = M3ALLM(model="explicit-model", max_retry=2, temperature=0.0)
    assert backend._client is None
    created = []
    class Wrapper(ScriptedModel):
        """Stand in only for the original external model wrapper."""
        def __init__(self, model_name, **kwargs):
            """Record source constructor arguments. Args: model_name,kwargs: Public config. Returns: None."""
            super().__init__([M3AReply("answer", is_safe=None)])
            created.append((model_name, kwargs))
    monkeypatch.setitem(sys.modules, "android_world.agents.infer", SimpleNamespace(Gpt4Wrapper=Wrapper))
    path = tmp_path / "image.png"
    Image.new("RGB", (20, 30), "red").save(path)
    assert backend.generate_m3a("prompt", (str(path), str(path))) == M3AReply("answer")
    assert created == [("explicit-model", {"max_retry": 2, "temperature": 0.0})]
    assert backend._client.calls[0][0] == "prompt"
    assert len(backend._client.calls[0][1]) == 2


def test_start_on_home_screen_matches_source(tmp_path):
    """Compare original Home reset option. Args: tmp_path: Artifacts. Returns: None."""
    assert_parity(tmp_path, [COMPLETE], max_rounds=1, start_on_home_screen=True)


def test_compiled_agent_reuse_clears_episode_memory(tmp_path):
    """Verify one compiled Agent creates fresh Memory per run. Args: tmp_path: Artifacts. Returns: None."""
    model = ScriptedModel([CLICK, M3AReply("Opened."), COMPLETE, COMPLETE])
    compiled = compile_agent(build_m3a_graph(max_rounds=2), dependencies={"llm": model})
    for index in range(2):
        env = FakeEnv()
        result = compiled.run(GOAL, AgentRunConfig(artifact_root=tmp_path / str(index), max_steps=3),
                              device=M3AEnvironment(env, sleep=env.sleep))
        assert result.status is RunStatus.SUCCESS
    assert "You just started, no action has been performed yet." in model.calls[3][0]
    assert "Step 1-" not in model.calls[3][0]


def test_opaque_ui_metadata_is_not_copied_or_serialized():
    """Exclude unused upstream handles/secrets before copying metadata. Returns: None."""
    from zhixing.plugins.agent.m3a.types import portable_ui
    class Private:
        """Represent an opaque environment handle."""
        def __deepcopy__(self, memo):
            """Forbid copying. Args: memo: Copy state. Raises: AssertionError: Any access. Returns: None."""
            raise AssertionError("opaque environment metadata must not be copied")
    value = source.UIElement(text="button", metadata={"api_key": "private-ui-sentinel", "handle": Private()})
    assert portable_ui([value])[0]["metadata"] is None


def test_generic_android_device_is_not_silently_substituted(tmp_path):
    """Reject incompatible observation semantics. Args: tmp_path: Artifacts. Returns: None."""
    class GenericDevice:
        """Expose no official environment boundary."""
        platform = "android"
    result = compile_agent(build_m3a_graph(max_rounds=1), dependencies={"llm": ScriptedModel([COMPLETE])}).run(
        GOAL, AgentRunConfig(artifact_root=tmp_path, max_steps=2), device=GenericDevice())
    assert result.status is RunStatus.FAILURE
