"""Differential gates execute legacy controllers and actual concise YAML graphs."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
from pathlib import Path

import pytest
import yaml
from PIL import Image

from zhixing.catalog import BUILTIN_COMPONENT_CATALOG
from zhixing.components import Action, ActionExecutionInput, ActionType, LegacyActionExecutor, RunStatus, RuntimeContext
from zhixing.core.agent.protocol import VerifierResult
from zhixing.engine.agent.modular_agent import ModularAgent
from zhixing.engine.agent.reflection_agent import ReflectionAgent
from zhixing.engine.agent.multi_agent import MultiAgent
from zhixing.engine.agent.uground_agent import UGroundAgent
from zhixing.graph import load_graph_yaml
from zhixing.plugins.agent.workflow_compat import WorkflowOperation
from zhixing.sdk import AgentRunConfig, compile_agent


ROOT = Path(__file__).resolve().parents[2]


class Model:
    """Replace only external model responses, retaining production prompts/parsers."""

    def __init__(self, responses):
        """Store script. Args: responses: Text/exception sequence. Returns: None."""
        self.responses, self.calls = list(responses), []

    def generate(self, prompt, images=None):
        """Record exact prompts and image pixels. Args: prompt,images: Model input. Raises: Exception: Scripted failure. Returns: str."""
        self.calls.append((prompt, tuple(hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in (images or []))))
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class Android:
    """Deterministic observation provider and physical-effect recorder."""

    platform, serial, w, h = "android", "migration-fake", 120, 240

    def __init__(self, *, unchanged=False):
        """Initialize state. Args: unchanged: Keep the first action's screen unchanged. Returns: None."""
        self.effects, self.images, self.unchanged = [], [], unchanged

    def screenshot(self, path):
        """Create observed PNG. Args: path: Runtime destination. Returns: str."""
        n = len(self.images)
        color = 0 if self.unchanged and n == 1 else (n * 80) % 255
        Image.new("RGB", (self.w, self.h), (color, color, color)).save(path)
        self.images.append(str(path))
        return path

    def get_xml(self, path):
        """Write one real UI element. Args: path: Runtime XML destination. Returns: str."""
        Path(path).write_text('<hierarchy><node clickable="true" enabled="true" text="Button" '
            'class="android.widget.Button" bounds="[10,20][50,60]" /></hierarchy>')
        return path

    def tap(self, x, y):
        """Record tap. Args: x,y: Pixels. Returns: None."""
        self.effects.append(("tap", x, y))

    def input_text(self, text):
        """Record typing. Args: text: Exact text. Returns: None."""
        self.effects.append(("text", text))

    def go_back(self):
        """Record BACK. Returns: None."""
        self.effects.append(("back",))

    def go_home(self):
        """Record HOME. Returns: None."""
        self.effects.append(("home",))

    def shell(self, command):
        """Record device command. Args: command: Executor command. Returns: str."""
        self.effects.append(("shell", command))
        return ""

    def wait(self, seconds):
        """Record a wait without sleeping. Args: seconds: Requested delay. Returns: None."""
        self.effects.append(("wait", seconds))

    def enter(self):
        """Record ENTER. Returns: None."""
        self.effects.append(("enter",))


def action_data(action):
    """Normalize decisions without hiding semantic metadata. Args: action: Decision. Returns: dict or None."""
    return asdict(action) if action is not None else None


def legacy_agent(source, model, device, available_apps=""):
    """Construct real configured components, then run the original controller methods.

    Args:
        source: Original YAML path.
        model: Deterministic external model.
        device: Fake device boundary.
        available_apps: Explicit catalogue text supplied by the execution caller.
    Returns:
        ModularAgent: Original class with original configured production delegates.
    """
    document = yaml.safe_load(source.read_text())
    config = document["agent"]
    cls = {"multi_agent": MultiAgent, "reflection_agent": ReflectionAgent, "uground_agent": UGroundAgent}.get(document["agent_type"], ModularAgent)
    agent = object.__new__(cls)
    agent.use_experience_cache = config.get("strategy", {}).get("use_experience_cache", True)
    agent.manager_each_step = config.get("strategy", {}).get("manager_each_step", True)
    import logging
    agent.logger, agent.verbose, agent.device = logging.getLogger("migration-test"), False, device
    agent.components, agent.config = {}, config
    for role, references in config["components"].items():
        many = isinstance(references, list)
        refs = references if many else [references]
        instances = []
        for ref in refs:
            cls = BUILTIN_COMPONENT_CATALOG.ensure("agent." + role, ref["name"])
            params = dict(ref.get("params", {}))
            if ref.get("llm"):
                params["llm_client"] = model
            instances.append(cls(**params))
        agent.components[role] = instances if many else instances[0]
    perception = agent.components["perception"]
    agent.perceptions = perception if isinstance(perception, list) else [perception]
    for role in ("reasoning", "memory", "planner", "verifier"):
        setattr(agent, role, agent.components.get(role))
    if isinstance(agent, UGroundAgent):
        agent.grounder = agent.components["grounder"]
        strategy = config.get("strategy", {})
        agent.summarize_steps = strategy.get("summarize_steps", True)
        agent.summary_prompt_file = strategy.get("summary_prompt_file", "summary_seeact_uground.md")
        agent.hide_automation_ui_on_reset = strategy.get("hide_automation_ui_on_reset", True)
    agent.reset({"instruction": "Press the button", "start_app_catalog_text": available_apps})
    return agent


def run_legacy(source, destination, responses, *, unchanged=False, available_apps=""):
    """Execute original reset/step against shared executor semantics.

    Args:
        source: Legacy YAML.
        destination: Isolated observation directory.
        responses: Deterministic external responses.
        unchanged: Controlled visual verification failure.
        available_apps: Exact caller-supplied catalogue text.
    Returns:
        tuple: Agent, model, device and decisions for differential comparison.
    """
    destination.mkdir()
    model, device = Model(deepcopy(responses)), Android(unchanged=unchanged)
    agent = legacy_agent(source, model, device, available_apps)
    executor, actions = LegacyActionExecutor(device=device), []
    for i in range(12):
        png, xml = destination / f"shot-{i}.png", destination / f"shot-{i}.xml"
        device.screenshot(png)
        device.get_xml(xml)
        action = agent.step(str(png), device.w, device.h, str(xml))
        actions.append(action_data(action))
        if action.type in {ActionType.DONE, ActionType.FAIL}:
            break
        executor.invoke(ActionExecutionInput(action=action), RuntimeContext(device=device))
    else:
        raise AssertionError("legacy reference did not terminate")
    return agent, model, device, actions


@pytest.mark.parametrize("case,responses", [
    ("normal", ["Action: tap(1)\nSummary: button", 'Action: text("ABC")\nSummary: typed', "Action: FINISH\nSummary: done"]),
    ("grid_hint", ["Action: grid()\nSummary: grid", 'Action: tap(1, "center")\nSummary: button', "Action: FINISH\nSummary: done"]),
    ("unchanged", ["Action: tap(1)\nSummary: button", 'Action: tap(1, "center")\nSummary: grid', "Action: FINISH\nSummary: done"]),
    ("perception_error", ['Action: tap(1, "center")\nSummary: grid', "Action: FINISH\nSummary: done"]),
    ("all_perception_error", []),
    ("reason_error", [RuntimeError("controlled")]*4),
    ("parse_retry", ["invalid", "Action: FINISH\nSummary: repaired"]),
    ("correction", ["Action: tap(1)\nSummary: button", "Action: FINISH\nSummary: done"]),
])
def test_appagent_differential(tmp_path, monkeypatch, case, responses):
    """Compare real legacy and graph flows including failure branches.

    Args:
        tmp_path: Isolated artifacts.
        monkeypatch: Inject only controlled boundary failures and capture outputs.
        case: Differential scenario.
        responses: Finite model script.
    Raises:
        AssertionError: Any decision, prompt, memory, call-order or effect differs.
    Returns:
        None.
    """
    from zhixing.plugins.agent.perception.xml_som import XmlSomPerception
    from zhixing.plugins.agent.perception.grid import GridPerception
    from zhixing.plugins.agent.verifier.screen_diff import ScreenDiffVerifier
    calls = []
    for cls, method in ((XmlSomPerception, "perceive"), (GridPerception, "perceive"), (ScreenDiffVerifier, "verify")):
        original = getattr(cls, method)

        def traced(self, value, _original=original, _name=cls.__name__):
            """Trace a delegate boundary. Args: self,value,_original,_name: Call. Returns: Original output."""
            calls.append(_name)
            if case == "all_perception_error" or (case == "perception_error" and _name == "XmlSomPerception" and calls.count(_name) == 1):
                raise RuntimeError("controlled perception failure")
            if case == "correction" and _name == "ScreenDiffVerifier":
                return VerifierResult(False, "correct", correction_suggestion=Action(ActionType.KEY, params={"code": "back"}))
            return _original(self, value)

        monkeypatch.setattr(cls, method, traced)
    source = ROOT / "examples/agent_appagent.yaml"
    old, old_model, old_device, old_actions = run_legacy(source, tmp_path / "old", responses, unchanged=case == "unchanged")
    old_calls = calls[:]
    calls.clear()
    frames = []
    original_invoke = WorkflowOperation.invoke

    def capture(self, value, runtime):
        """Capture only the final data frame. Args: self,value,runtime: Invocation. Returns: Production output."""
        if self.operation == "finish":
            frames.append(value)
        return original_invoke(self, value, runtime)

    monkeypatch.setattr(WorkflowOperation, "invoke", capture)
    model, device = Model(deepcopy(responses)), Android(unchanged=case == "unchanged")
    result = compile_agent(load_graph_yaml(ROOT / "examples/graphs/appagent.yaml"), dependencies={"llm": model}).run(
        "Press the button", AgentRunConfig(artifact_root=tmp_path / "new", include_ui_tree=True), device=device)
    assert result.status in {RunStatus.SUCCESS, RunStatus.FAILURE}, (result.error, result.error_details)
    assert frames, result
    assert calls == old_calls
    assert model.calls == old_model.calls
    assert device.effects == old_device.effects
    assert [action_data(item.action) for item in result.action_results] == old_actions
    frame = frames[0]
    assert frame.index == old.state.current_strategy_idx
    assert action_data(frame.last_action) == action_data(old.state.last_action)
    assert [f for f in frame.fragments if f.role == "system"] == old.memory.system_buffer
    assert [f for f in frame.fragments if f.role != "system"] == old.memory.history_buffer


def test_appagent_graph_is_explicit_and_legacy_file_is_retained():
    """Guard against wrapping Agent.step or hiding the graph behind an exporter.

    Raises:
        AssertionError: Native services, ports or retained configuration are absent.
    Returns:
        None.
    """
    source = ROOT / "examples/graphs/appagent.yaml"
    compiled = load_graph_yaml(source)
    assert compiled.is_success, compiled.diagnostics
    body = compiled.graph.nodes[2].loop.body.graph if compiled.graph.nodes[2].id == "workflow" else next(
        node.loop.body.graph for node in compiled.graph.nodes if node.id == "workflow")
    assert {node.id for node in body.nodes} >= {"dispatch", "verify", "perceive_0", "perceive_1", "reason", "observe", "execute"}
    assert (ROOT / "examples/agent_appagent.yaml").exists()
    production = (ROOT / "zhixing/plugins/agent/workflow_compat.py").read_text()
    assert "zhixing.engine.agent" not in production and ".step(" not in production


MODULAR_CASES = [
    ("mobile_agent_v2_migrated", "agent_mobile_agent_v2.yaml", ["### Action ###\nTap (30,40)", "### Answer ###\nA", "### Action ###\nStop"]),
    ("mobile_agent", "agent_mobileagent.yaml", ["### Action ###\nTap (30,40)", "### Answer ###\nA", "### Action ###\nStop"]),
    ("gui_schema_cn", "agent_gui_schema_cn.yaml", ['{"POINT":[250,500]}', '{"TYPE":"Ab C"}', '{"STATUS":"finish"}']),
    ("os_genesis", "agent_os_genesis.yaml", ['{"action_type":"click","x":30,"y":40}', '{"action_type":"navigate_back"}', '{"action_type":"status","goal_status":"successful"}']),
    ("showui", "agent_showui.yaml", ['{"action":"TAP","position":[0.25,0.5]}', '{"action":"INPUT","value":"Ab C"}', '{"action":"ANSWER","value":"done"}']),
    ("guicourse", "agent_guicourse.yaml", ["tap, <point> 250 500</point>", "input, Ab C", "answer, task complete"]),
]


@pytest.mark.parametrize("name,legacy,responses", MODULAR_CASES)
@pytest.mark.parametrize("case", ["normal", "parse_retry", "reason_error", "perception_error", "app_catalog", "memory_window"])
def test_modular_migration(tmp_path, monkeypatch, name, legacy, responses, case):
    """Compare each sequentially admitted example with its actual legacy step.

    Args:
        tmp_path: Isolated capture/artifact directories.
        monkeypatch: Boundary failure injection and final frame capture.
        name: Independently generated graph identifier.
        legacy: Retained original configuration filename.
        responses: Source-protocol model script.
        case: Normal, parsing, model or perception scenario.
    Raises:
        AssertionError: Exact model input, decisions, effects or memory differ.
    Returns:
        None.
    """
    source = ROOT / "examples" / legacy
    if case == "memory_window":
        reflection = yaml.safe_load(source.read_text())["agent_type"] == "reflection_agent"
        responses = ([responses[0], "### Answer ###\nA"] * 9 if reflection else [responses[0]] * 9) + [responses[-1]]
    if case == "parse_retry":
        responses = ["invalid", *responses]
    if case == "reason_error":
        responses = [RuntimeError("controlled")]*4
    config = yaml.safe_load(source.read_text())["agent"]["components"]
    perception = config["perception"]
    cls = BUILTIN_COMPONENT_CATALOG.ensure("agent.perception", perception["name"])
    original = cls.perceive
    calls = []

    def perceive(self, value):
        """Record perception inputs. Args: self,value: Delegate call. Raises: RuntimeError: Injected. Returns: PerceptionResult."""
        calls.append((value.width, value.height, bool(value.ui_path)))
        if case == "perception_error":
            raise RuntimeError("controlled perception")
        return original(self, value)

    monkeypatch.setattr(cls, "perceive", perceive)
    available_apps = "- Notes: org.example.notes" if case == "app_catalog" else ""
    old, old_model, old_device, old_actions = run_legacy(source, tmp_path / "old", responses, available_apps=available_apps)
    old_calls = calls[:]
    calls.clear()
    frames = []
    original_invoke = WorkflowOperation.invoke

    def capture(self, value, runtime):
        """Capture final state. Args: self,value,runtime: Invocation. Returns: Production output."""
        if self.operation == "finish":
            frames.append(value)
        return original_invoke(self, value, runtime)

    monkeypatch.setattr(WorkflowOperation, "invoke", capture)
    model, device = Model(deepcopy(responses)), Android()
    result = compile_agent(load_graph_yaml(ROOT / "examples/graphs" / (name + ".yaml")), dependencies={"llm": model}).run(
        "Press the button", AgentRunConfig(artifact_root=tmp_path / "new", include_ui_tree=True,
            metadata={"available_apps": available_apps}), device=device)
    assert frames, (result.error, result.error_details)
    assert calls == old_calls
    assert model.calls == old_model.calls
    assert device.effects == old_device.effects
    assert [action_data(item.action) for item in result.action_results] == old_actions
    assert [f for f in frames[0].fragments if f.role == "system"] == old.memory.system_buffer
    assert [f for f in frames[0].fragments if f.role != "system"] == old.memory.history_buffer
    if isinstance(old, UGroundAgent):
        assert frames[0].summary_pending == old._last_action_summary_pending
        assert frames[0].last_response == old._last_action_response


@pytest.mark.parametrize("answer", ["A", "B", "C", "D", "unclear"])
@pytest.mark.parametrize("name,legacy", [("mobile_agent", "agent_mobileagent.yaml"), ("mobile_agent_v2_migrated", "agent_mobile_agent_v2.yaml")])
def test_mobile_agent_reflection_routes(tmp_path, monkeypatch, answer, name, legacy):
    """Exercise real reflection parsing and correction short circuits.

    Args:
        tmp_path: Isolated artifacts.
        monkeypatch: Test-owned boundary capture.
        answer: Scripted external reflection response.
        name: Selected independently migrated graph.
        legacy: Exact original configuration filename.
    Raises:
        AssertionError: Disabled cache is queried or either pipeline differs.
    Returns:
        None.
    """
    from zhixing.plugins.agent.memory.sliding_window import SlidingWindowMemory

    def forbidden_cache(self, screenshot_path, task):
        """Reject a disabled path. Args: self,screenshot_path,task: Call. Raises: AssertionError: Always. Returns: None."""
        raise AssertionError("reflection configuration disables the experience cache")

    monkeypatch.setattr(SlidingWindowMemory, "retrieve_experience", forbidden_cache)
    test_modular_migration(tmp_path, monkeypatch, name, legacy,
        ["### Action ###\nTap (30,40)", "### Thought ###\nchecked\n### Answer ###\n" + answer,
         "### Action ###\nStop"], "normal")


@pytest.mark.parametrize("case", ["normal", "critic_correction", "critic_feedback", "manager_error", "operator_error", "parse_retry", "take_note"])
def test_mobile_use_migration(tmp_path, monkeypatch, case):
    """Keep initial planning, per-step Manager and Critic short circuits ordered.

    Args:
        tmp_path: Isolated artifacts.
        monkeypatch: Test-owned boundary capture.
        case: Distinct role order/failure scenario.
    Raises:
        AssertionError: Prompts, role call count, memory or decisions differ.
    Returns:
        None.
    """
    tap = '<tool_call>{"name":"mobile_use","arguments":{"action":"click","coordinate":[30,40]}}</tool_call>'
    done = '<tool_call>{"name":"mobile_use","arguments":{"action":"answer","text":"done"}}</tool_call>'
    plan = "### Plan ###\npress then finish"
    manager = RuntimeError("manager controlled") if case == "manager_error" else plan
    actor = [RuntimeError("operator controlled")]*4 if case == "operator_error" else [tap]
    if case == "parse_retry":
        actor.insert(0, "invalid")
    if case == "take_note":
        actor = ['<tool_call>{"name":"mobile_use","arguments":{"action":"take_note","text":"remember"}}</tool_call>']
    responses = [plan, manager, *actor]
    if case != "operator_error":
        if case != "take_note":
            answer = "B" if case == "critic_correction" else "C" if case == "critic_feedback" else "A"
            responses.append("### Thought ###\nreviewed\n### Answer ###\n" + answer)
        responses.extend([plan, done])
    test_modular_migration(tmp_path, monkeypatch, "mobile_use", "agent_mobile_use_multi.yaml", responses, "normal")


@pytest.mark.parametrize("case", ["normal", "ground_error", "summary_error", "empty_summary", "explicit_xy", "input_text", "double_tap", "key", "reason_error", "parse_error", "reset_error"])
def test_uground_migration(tmp_path, monkeypatch, case):
    """Compare real summary and grounding models including noncommit WAIT recovery.

    Args:
        tmp_path: Isolated artifacts.
        monkeypatch: Test-owned reset failure injection and final frame capture.
        case: Source-specific model/side-effect branch.
    Raises:
        AssertionError: Model images, prompts, memory, actions or reset effects differ.
    Returns:
        None.
    """
    import json
    action = {"action_type": "click", "element": "Button"}
    if case == "input_text":
        action = {"action_type": "input_text", "element": "Button", "text": "Ab C"}
    if case == "double_tap":
        action["action_type"] = "double_tap"
    if case == "explicit_xy":
        action = {"action_type": "click", "x": 30, "y": 40}
    if case == "key":
        action = {"action_type": "navigate_back"}
    responses = ["Reason: choose button\nAction: " + json.dumps(action)]
    if case not in {"key", "explicit_xy"}:
        responses.append("not a point" if case == "ground_error" else "(250, 500)")
    if case not in {"ground_error", "key"}:
        responses.append(RuntimeError("controlled summary") if case == "summary_error" else "" if case == "empty_summary" else "pressed")
    responses.append('Reason: done\nAction: {"action_type":"status","goal_status":"complete"}')
    if case == "reason_error":
        responses = [RuntimeError("controlled planner")]
    if case == "parse_error":
        responses = ["invalid"]
    if case == "reset_error":
        def failed_shell(self, command):
            """Fail optional reset. Args: self,command: Call. Raises: RuntimeError: Controlled. Returns: None."""
            self.effects.append(("shell", command))
            raise RuntimeError("controlled reset")

        monkeypatch.setattr(Android, "shell", failed_shell)
    test_modular_migration(tmp_path, monkeypatch, "uground", "agent_uground.yaml", responses, "normal")


def test_role_restrictions_and_frame_types():
    """Reject misplaced device effects and incorrectly typed opaque frames.

    Raises:
        AssertionError: A data operation can execute setup or accepts an untyped value.
    Returns:
        None.
    """
    with pytest.raises(ValueError, match="unknown workflow operation"):
        WorkflowOperation("setup")
    with pytest.raises(TypeError, match="WorkflowFrame"):
        WorkflowOperation("select").invoke({"index": 0}, RuntimeContext())


def test_two_runs_have_fresh_memory_and_control_state(tmp_path):
    """Reuse a recipe while checking run-local memory, fallback and evidence.

    Args:
        tmp_path: Isolated native artifact root.
    Raises:
        AssertionError: A previous run changes the next run's prompt or decisions.
    Returns:
        None.
    """
    model = Model(["tap, <point> 250 500</point>", "answer, complete"] * 2)
    recipe = compile_agent(load_graph_yaml(ROOT / "examples/graphs/guicourse.yaml"), dependencies={"llm": model})
    results = []
    for i in range(2):
        result = recipe.run("Press the button", AgentRunConfig(artifact_root=tmp_path, include_ui_tree=True), device=Android())
        assert result.status is RunStatus.SUCCESS, result.error
        results.append(result)
    assert model.calls[:2] == model.calls[2:]
    assert results[0].run_id != results[1].run_id


def test_native_interaction_budget_stops_device_effects(tmp_path):
    """Keep native physical-interaction limits explicit rather than emulating Runner.

    Args:
        tmp_path: Isolated native artifact root.
    Raises:
        AssertionError: More than one physical input passes the configured budget.
    Returns:
        None.
    """
    model, device = Model(["tap, <point> 250 500</point>"] * 4), Android()
    result = compile_agent(load_graph_yaml(ROOT / "examples/graphs/guicourse.yaml"), dependencies={"llm": model}).run(
        "Press the button", AgentRunConfig(artifact_root=tmp_path, include_ui_tree=True, max_steps=1), device=device)
    assert result.status is RunStatus.STEP_LIMIT, (result.status, result.error)
    assert len(device.effects) == 1
