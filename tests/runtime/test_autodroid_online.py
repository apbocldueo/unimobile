"""Production AutoDroid components, graph execution and failure boundaries."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from PIL import Image

from zhixing.autodroid import build_autodroid_graph
from zhixing.catalog import BuiltInComponentResolver
from zhixing.components import (
    Action, ActionResult, ActionType, DeviceObservation, ExecutionStatus,
    MemoryFragment, MemoryInput, MemoryOperation, PlanResult, ReasoningInput,
    RunStatus, RuntimeContext, TaskInput,
)
from zhixing.core.agent.protocol import FragmentType
from zhixing.graph import load_graph_yaml
from zhixing.knowledge.autodroid import AppMemoryIndex, InstructorEncoder, load_app_memory
from zhixing.plugins.agent.autodroid_types import AppMemory, Guide, GuideHit, MemoryEntry, Target, UIState
from zhixing.plugins.agent.memory.autodroid import AutoDroidMemory
from zhixing.plugins.agent.parsers.autodroid_action_parser import AutoDroidActionParser
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
from zhixing.plugins.agent.perception.autodroid import AutoDroidPerception
from zhixing.plugins.agent.reasoning.autodroid import AutoDroidReasoning
from zhixing.sdk import AgentRunConfig, ExecutableAgent, compile_agent


APP = "org.example.notes"


class Encoder:
    """Deterministic vectors with explicit query recording."""

    def __init__(self, vector=(1.0, 0.0)):
        """Store a test vector and an empty call log.

        Args:
            vector: Deterministic embedding vector returned by the fake encoder.

        Returns:
            None.
        """
        self.vector, self.calls = vector, []

    def encode(self, texts, instruction):
        """Return one configured vector per sentence and record the convention.

        Args:
            texts: Test input sentences.
            instruction: Expected retrieval instruction.
        Returns:
            list: Fixed vectors; no model or network is used.
        """
        self.calls.append((tuple(texts), instruction))
        return [self.vector for _ in texts]


class Model:
    """Return scripted choices or select the last collected page by its text."""

    def __init__(self, responses=None):
        """Store scripted responses and an empty prompt log.

        Args:
            responses: Optional ordered model response script.

        Returns:
            None.
        """
        self.responses, self.prompts = list(responses or []), []

    def generate(self, prompt, images=None):
        """Choose a deterministic action without accessing the fake device.

        Args:
            prompt: Actual AutoDroid prompt from the production Reasoning.
            images: Expected to be None for the text-based online policy.
        Returns:
            str: Scripted or target-selecting decision JSON.
        """
        assert images is None
        self.prompts.append(prompt)
        if self.responses:
            return self.responses.pop(0)
        if len(self.prompts) > 1:
            return '{"Finished":"Yes","id":-1}'
        match = re.search(r"<button id=(\d+)[^>]*>Page 4</button>", prompt)
        assert match, prompt
        return json.dumps({"Finished": "No", "id": int(match[1]), "action": "tap"})


class Android:
    """Five-page Android-compatible fake behind the production device boundary."""

    platform, serial, w, h = "android", "autodroid-fake", 100, 200

    def __init__(self, pages=5, page=0, broken=False, shift_revisited=False):
        """Configure scroll bounds, initial page and action failure injection.

        Args:
            pages: Number of scroll pages.
            page: Initial page index.
            broken: Inject failure at the next device operation.
            shift_revisited: Move the last page's target after scan collection.
        Returns:
            None.
        """
        self.pages, self.page, self.broken = pages, page, broken
        self.shift_revisited, self.visits = shift_revisited, {}
        self.calls = []

    def screenshot(self, path):
        """Write an actual PNG for the production observation service.

        Args:
            path: Service-owned artifact destination.
        Returns:
            str: Written PNG path.
        """
        Image.new("RGB", (self.w, self.h), "white").save(path)
        self.calls.append(("observe", self.page))
        return path

    def get_xml(self, path):
        """Write a page with stable semantic identity and changing coordinates.

        Args:
            path: Service-owned XML destination.
        Returns:
            str: Valid Android hierarchy text.
        """
        self.visits[self.page] = self.visits.get(self.page, 0) + 1
        top = 20 + self.page * 10
        if self.shift_revisited and self.page == self.pages - 1 and self.visits[self.page] >= 3:
            top += 20
        child = (f'<node package="{APP}" resource-id="row" class="Button" clickable="true" '
                 f'text="Page {self.page}" bounds="[10,{top}][90,{top + 20}]"/>')
        xml = f'<hierarchy><node package="{APP}" resource-id="list" class="List" scrollable="true" bounds="[0,0][100,180]">{child}</node></hierarchy>'
        Path(path).write_text(xml, encoding="utf-8")
        return xml

    def shell(self, command):
        """Apply one precise swipe; clamp at the synthetic scroll boundaries.

        Args:
            command: Canonical executor's input swipe command.
        Raises:
            RuntimeError: Controlled device failure is enabled.
        Returns:
            str: Empty shell output.
        """
        if self.broken:
            raise RuntimeError("controlled fake device failure")
        parts = command.split()
        assert parts[:2] == ["input", "swipe"]
        self.calls.append(("swipe", self.page, command))
        self.page = min(self.pages - 1, max(0, self.page + (1 if int(parts[3]) > int(parts[5]) else -1)))
        return ""

    def tap(self, x, y):
        """Record the page and exact current-frame coordinates of a tap.

        Args:
            x: Horizontal pixel coordinate.
            y: Vertical pixel coordinate.
        Raises:
            RuntimeError: Controlled action failure is enabled.
        Returns:
            None.
        """
        if self.broken:
            raise RuntimeError("controlled fake device failure")
        self.calls.append(("tap", self.page, x, y))


def memory_file(tmp_path, path=()):
    """Write one normalized memory with cached embeddings.

    Args:
        tmp_path: Test-owned directory.
        path: Optional shortcut navigation steps.
    Returns:
        Path: Read-only input for the production Memory.
    """
    target = tmp_path / "memory.json"
    target.write_text(AppMemory(app_id=APP, entries=(MemoryEntry(
        id="task", task="Select Page 4", function="Open the target page", path=path, embedding=(1, 0),
    ),)).model_dump_json(), encoding="utf-8")
    return target


def perceive(tmp_path, xml):
    """Encode a supplied XML through the actual Perception component.

    Args:
        tmp_path: Test directory.
        xml: Android UI tree.
    Returns:
        PerceptionResult: Typed production result.
    """
    path = tmp_path / "ui.xml"
    path.write_text(xml, encoding="utf-8")
    return AutoDroidPerception().invoke(DeviceObservation(screenshot_path="screen", ui_path=str(path), width=100, height=200), RuntimeContext())


def reason_input(perception, guide=None):
    """Build the standard six-role ReasoningInput with a typed memory fragment.

    Args:
        perception: Production perception result.
        guide: Optional test retrieval result.
    Returns:
        ReasoningInput: Existing public component contract.
    """
    guide = guide or Guide(app_id=APP)
    fragment = MemoryFragment("system", FragmentType.RAG_DOC, guide.model_dump(mode="json"),
                              {"source": "autodroid.app_memory"})
    return ReasoningInput(TaskInput("Select Page 4"), PlanResult(""), perception, (fragment,))


@pytest.mark.parametrize("response", [
    '{"id":true}', '{"id":1.2}', '{"id":-2}', '{"id":1,"action":"scroll"}',
    '{"Finished":"No","id":-1}', '{"Finished":"Yes","id":1}', '{"Finished":"Yes","id":-1.0}',
    '{"id":1,"action":"input","input_text":""}', 'garbage',
])
def test_invalid_output_is_never_completion(response):
    """Reject malformed, contradictory and unsupported model choices.

    Args:
        response: Model response under examination.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    with pytest.raises(ActionParseError):
        AutoDroidActionParser().parse(response)


@pytest.mark.parametrize("response,identifier,operation,text", [
    ('```json\n{"Finished":"No","id":2,"action":"input","input_text":"hello"}\n```', 2, "input", "hello"),
    ("{'id': 3, 'action': 'click'}", 3, "tap", ""),
    ('id=4 action=input input text="hello world"', 4, "input", "hello world"),
    ('{"Finished":"Yes","id":-1}', -1, "tap", ""),
])
def test_supported_decision_formats(response, identifier, operation, text):
    """Support upstream JSON/Python dictionaries and the paper's choice form.

    Args:
        response: Model response under examination.
        identifier: Expected parsed UI choice id.
        operation: Expected canonical choice operation.
        text: Expected input text.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    choice = AutoDroidActionParser().parse(response)
    assert (choice.choice_id, choice.operation, choice.text) == (identifier, operation, text)


def test_hierarchy_merges_owned_labels_but_keeps_nested_controls(tmp_path):
    """Retain independent inputs and checkboxes inside a clickable ancestor.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    result = perceive(tmp_path, f'''<hierarchy><node package="{APP}" clickable="true" class="Row" bounds="[0,0][100,100]">
      <node text="Title" content-desc="Icon label" bounds="[0,0][40,20]"/>
      <node text="Subtitle" bounds="[0,20][40,40]"/>
      <node class="EditText" text="Draft" bounds="[40,0][100,40]"/>
      <node checkable="true" checked="true" text="Enabled" bounds="[40,40][100,80]"/>
    </node></hierarchy>''')
    ui = UIState.model_validate(result.data["autodroid"])
    assert [item.tag for item in ui.candidates] == ["button", "input", "checkbox", "button"]
    assert ui.candidates[0].text == "Title<br>Subtitle"
    assert ui.candidates[0].label == "Icon label"
    assert "Title<br>Subtitle" in result.prompt_representation
    assert ui.candidates[2].checked
    assert "Enabled" not in ui.candidates[0].text


def test_semantic_cosine_retrieval_and_invalid_dimensions():
    """Rank by dense cosine similarity and reject incompatible vectors.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    memory = AppMemory(app_id=APP, entries=(
        MemoryEntry(id="b", task="first", embedding=(1, 0)),
        MemoryEntry(id="a", task="second", embedding=(1, 0)),
        MemoryEntry(id="c", task="third", embedding=(0, 1)),
    ))
    encoder = Encoder()
    guide = AppMemoryIndex(memory, encoder).retrieve("test", 2)
    assert [hit.entry.id for hit in guide.hits] == ["a", "b"]
    assert encoder.calls == [(("test",), memory.embedding_instruction)]
    with pytest.raises(ValueError, match="dimensions"):
        AppMemoryIndex(memory, Encoder((1, 0, 0))).retrieve("test")
    with pytest.raises(ValueError, match="finite and nonzero"):
        AppMemoryIndex(memory, Encoder((0, 0))).retrieve("test")


def test_upstream_memory_parallel_tables(tmp_path):
    """Load original table layout without claiming DroidBot hash equivalence.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    tables = {
        "node_filtered_elements.json": {APP: {"state": {"path": ["<button>Start</button>"], "elements": ["<button>Finish</button>"]}}},
        "element_description.json": {APP: {"state": ["Open the target"]}},
        "embedded_elements_desc.json": {APP: {"state": [[1, 0]]}},
    }
    for name, table in tables.items():
        (tmp_path / name).write_text(json.dumps(table), encoding="utf-8")
    memory = load_app_memory(tmp_path, APP)
    encoder = Encoder()
    guide = AppMemoryIndex(memory, encoder).retrieve("Open the target")
    assert len(guide.hits[0].entry.path) == 2
    assert encoder.calls == [(("task: Open the target",), "")]
    for name, table in tables.items():
        (tmp_path / name).write_text(json.dumps({"notes": table[APP]}), encoding="utf-8")
    assert load_app_memory(tmp_path, APP, "notes").app_id == APP
    for name, table in tables.items():
        (tmp_path / name).write_text(json.dumps(table), encoding="utf-8")
    (tmp_path / "element_description.json").write_text(json.dumps({APP: {"state": []}}))
    with pytest.raises(ValueError, match="lengths"):
        load_app_memory(tmp_path, APP)


def test_memory_state_is_owned_by_runtime_and_reset(tmp_path):
    """Reuse a component across contexts without sharing task history or guide.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    component = AutoDroidMemory(str(memory_file(tmp_path)), embedding=Encoder())
    contexts = [RuntimeContext(), RuntimeContext()]
    for index, context in enumerate(contexts):
        component.invoke(MemoryInput(MemoryOperation.APPEND, MemoryFragment("user", FragmentType.TEXT, f"task {index}")), context)
        component.invoke(MemoryInput(MemoryOperation.APPEND, MemoryFragment("assistant", FragmentType.TEXT, str(index))), context)
    assert component.invoke(MemoryInput(MemoryOperation.READ), contexts[0]).fragments[-1].content == "0"
    assert component.invoke(MemoryInput(MemoryOperation.READ), contexts[1]).fragments[-1].content == "1"
    component.invoke(MemoryInput(MemoryOperation.RESET), contexts[0])
    with pytest.raises(ValueError, match="TaskInput"):
        component.invoke(MemoryInput(MemoryOperation.READ), contexts[0])


def test_hints_shortcut_and_lookup_fallback(tmp_path):
    """Replay matching memory, then let the model judge completion; miss falls back.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    perception = perceive(tmp_path, f'<hierarchy><node package="{APP}" text="Target" clickable="true" bounds="[0,0][80,60]"/></hierarchy>')
    ui = UIState.model_validate(perception.data["autodroid"])
    entry = MemoryEntry(id="path", task="target", function="Open target functionality",
                        path=(Target(key=ui.candidates[0].key),))
    guide = Guide(app_id=APP, hits=(GuideHit(entry=entry, score=1),))
    model, context = Model(['{"id":-1}']), RuntimeContext()
    reasoning = AutoDroidReasoning(model)
    value = reason_input(perception, guide)
    assert reasoning.invoke(value, context).type is ActionType.TAP
    assert model.prompts == []
    assert reasoning.invoke(value, context).type is ActionType.DONE
    assert "onclick='Open target functionality'" in model.prompts[0]
    assert reasoning._target_action(Target(description="<button>go back</button>"), ui, "shortcut").type is ActionType.KEY
    # Same component, fresh context: no pending navigation or shortcut cursor leaks.
    assert reasoning.invoke(value, RuntimeContext()).type is ActionType.TAP
    missing = entry.model_copy(update={"path": (Target(key="absent"),)})
    fallback = AutoDroidReasoning(Model(['{"id":-1}']))
    assert fallback.invoke(reason_input(perception, Guide(app_id=APP, hits=(GuideHit(entry=missing, score=1),))), RuntimeContext()).type is ActionType.DONE


def test_ambiguous_target_and_execution_failure_are_explicit(tmp_path):
    """Never guess among duplicate identities or continue after a failed effect.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    node = f'<node package="{APP}" text="Same" clickable="true" bounds="[0,0][50,50]"/>'
    perception = perceive(tmp_path, "<hierarchy>" + node + node + "</hierarchy>")
    reasoning = AutoDroidReasoning(Model(['{"id":0}']), shortcut_enabled=False)
    assert reasoning.invoke(reason_input(perception), RuntimeContext()).type is ActionType.FAIL
    context = RuntimeContext()
    context.state.last_action_result = ActionResult(Action(ActionType.TAP), ExecutionStatus.FAILURE)
    assert reasoning.invoke(reason_input(perception), context).metadata["autodroid.error"] == "previous_action_failed"


@pytest.mark.fake_device_integration
def test_sdk_graph_scans_more_than_ten_actions_through_android_services(tmp_path, monkeypatch):
    """Scan, restore, replay and tap through the production graph and executor.

    Args:
        tmp_path: Isolated test input and artifact directory.
        monkeypatch: Fixture for bounded dependency substitution.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    monkeypatch.setattr(InstructorEncoder, "encode", Encoder.encode)
    # The fake encoder method needs only these injected recording attributes.
    monkeypatch.setattr(InstructorEncoder, "vector", (1, 0), raising=False)
    monkeypatch.setattr(InstructorEncoder, "calls", [], raising=False)
    model, device = Model(), Android(shift_revisited=True)
    graph = build_autodroid_graph(memory_path=str(memory_file(tmp_path)), max_steps=30,
                                 reasoning_params={"shortcut_enabled": False})
    agent = compile_agent(graph, dependencies={"llm": model})
    result = agent.run("Select Page 4", AgentRunConfig(artifact_root=tmp_path / "runs", max_steps=30, include_ui_tree=True), device=device)
    assert result.status is RunStatus.SUCCESS, result
    assert result.interaction_count > 10
    # Collection saw (50, 70); the re-observed target has moved to (50, 90).
    assert [call for call in device.calls if call[0] == "tap"] == [("tap", 4, 50, 90)]
    assert len(model.prompts) == 2
    assert all(f"Page {index}" in model.prompts[0] for index in range(5))
    phases = [item.action.metadata.get("autodroid.phase") for item in result.action_results]
    assert phases.count("scan") == 24
    assert phases.count("decision") == 6
    assert sum(item.effect_performed for item in result.action_results) == result.interaction_count
    assert any("Page 4" in text for text in model.prompts[1].splitlines() if "<button id=" in text)
    assert (tmp_path / "runs" / result.run_id / "manifest.json").is_file()


def test_sdk_and_yaml_have_the_same_semantic_identity():
    """Keep editable graph YAML equivalent to the packaged SDK template.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    compiled = load_graph_yaml(Path(__file__).resolve().parents[2] / "examples/graphs/autodroid_online.yaml")
    assert compiled.is_success, compiled.diagnostics
    assert compiled.graph.canonical_hash() == build_autodroid_graph().canonical_hash()


@pytest.mark.parametrize("decision,expected,params", [
    ('{"id":0,"action":"input","input_text":"hello"}', ActionType.TEXT, {"x": 50, "y": 30, "text": "hello"}),
    ('{"id":1}', ActionType.KEY, {"code": "back"}),
    ('{"id":99}', ActionType.FAIL, {}),
    ('not a decision', ActionType.FAIL, {}),
])
def test_text_back_and_invalid_selections_use_canonical_actions(tmp_path, decision, expected, params):
    """Map only valid current-frame selections to standard executor actions.

    Args:
        tmp_path: Isolated test input and artifact directory.
        decision: Scripted model decision.
        expected: Expected action type or execution status.
        params: Expected canonical action parameters.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    perception = perceive(tmp_path, f'<hierarchy><node package="{APP}" class="EditText" text="" bounds="[0,0][100,60]"/></hierarchy>')
    action = AutoDroidReasoning(Model([decision]), shortcut_enabled=False).invoke(reason_input(perception), RuntimeContext())
    assert action.type is expected
    assert action.params == params


def test_xml_bounds_and_lazy_constructor(tmp_path):
    """Reject malformed/oversized/deep inputs and defer all memory I/O.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="malformed"):
        perceive(tmp_path, "<hierarchy>")
    with pytest.raises(ValueError, match="depth"):
        perceive(tmp_path, '<node clickable="true" bounds="[0,0][10,10]">' + "<node>" * 110 + "</node>" * 111)
    path = tmp_path / "ui.xml"
    with pytest.raises(ValueError, match="limit"):
        AutoDroidPerception(max_xml_bytes=1).invoke(DeviceObservation("screen", 100, 200, str(path)), RuntimeContext())
    AutoDroidMemory(str(tmp_path / "absent.json"))
    assert build_autodroid_graph(memory_path=str(tmp_path / "absent.json"))


def test_missing_embeddings_are_encoded_once_per_index():
    """Cache synthesized memory vectors while encoding each new query.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    memory = AppMemory(app_id=APP, entries=(MemoryEntry(id="a", task="create note"),))
    encoder = Encoder()
    index = AppMemoryIndex(memory, encoder)
    index.retrieve("first")
    index.retrieve("second")
    assert [call[0] for call in encoder.calls] == [("create note",), ("first",), ("second",)]


def test_instructor_backend_is_lazy_and_preserves_encoding_convention(monkeypatch):
    """Exercise the optional backend adapter with an in-process model double.

    Args:
        monkeypatch: Fixture for bounded dependency substitution.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    import sys
    from types import SimpleNamespace

    calls = []

    class Backend:
        """Record checkpoint construction and sentence encoding inputs."""

        def __init__(self, model, device):
            """Record the selected checkpoint and embedding device.

            Args:
                model: Checkpoint identifier recorded by the backend double.
                device: Embedding device recorded by the backend double.

            Returns:
                None.
            """
            calls.append((model, device))

        def encode(self, sentences, show_progress_bar):
            """Return an array-shaped result after recording the public API call.

            Args:
                sentences: INSTRUCTOR instruction/text pairs or legacy sentences.
                show_progress_bar: Disabled for library operation.
            Returns:
                object: Array-like vectors.
            """
            calls.append((sentences, show_progress_bar))
            return SimpleNamespace(tolist=lambda: [[1, 0] for _ in sentences])

    monkeypatch.setitem(sys.modules, "InstructorEmbedding", SimpleNamespace(INSTRUCTOR=Backend))
    encoder = InstructorEncoder("local-checkpoint")
    assert calls == []
    assert encoder.encode(["task"], "instruction") == [[1, 0]]
    encoder.encode(["task: target"], "")
    assert calls == [("local-checkpoint", "cpu"), ([["instruction", "task"]], False), (["task: target"], False)]


def test_equivalent_groups_are_explicit_and_state_scoped(tmp_path):
    """Compress declared equivalent controls while leaving undeclared ones alone.

    Args:
        tmp_path: Isolated test input and artifact directory.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    perception = perceive(tmp_path, f'<hierarchy><node package="{APP}" text="A" clickable="true" bounds="[0,0][30,30]"/><node package="{APP}" text="B" clickable="true" bounds="[40,0][70,30]"/></hierarchy>')
    ui = UIState.model_validate(perception.data["autodroid"])
    group = tuple(candidate.key for candidate in ui.candidates[:2])
    guide = Guide(app_id=APP, equivalent_groups={ui.state_id: (group,)})
    text, candidates = AutoDroidReasoning._prompt_ui(ui.candidates, guide, ui)
    assert len(candidates) == 2
    assert "A<br>B" in text
    unrelated = guide.model_copy(update={"equivalent_groups": {"other-state": (group,)}})
    assert len(AutoDroidReasoning._prompt_ui(ui.candidates, unrelated, ui)[1]) == 3


@pytest.mark.fake_device_integration
def test_shortcut_executes_and_reaches_model_without_silent_completion(tmp_path, monkeypatch):
    """Replay a cached semantic path through the same executor and result ledger.

    Args:
        tmp_path: Isolated test input and artifact directory.
        monkeypatch: Fixture for bounded dependency substitution.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    monkeypatch.setattr(InstructorEncoder, "encode", lambda self, texts, instruction: [(1, 0) for _ in texts])
    path = memory_file(tmp_path, (Target(description="<button>Page 0</button>"),))
    graph = build_autodroid_graph(memory_path=str(path), max_steps=4,
                                 reasoning_params={"scan_enabled": False})
    model, device = Model(['{"id":-1}']), Android(pages=1)
    result = compile_agent(graph, dependencies={"llm": model}).run("Select Page 4",
        AgentRunConfig(artifact_root=tmp_path / "runs", max_steps=4, include_ui_tree=True), device=device)
    assert result.status is RunStatus.SUCCESS
    assert result.interaction_count == 1
    assert [item.action.type for item in result.action_results] == [ActionType.TAP, ActionType.DONE]
    assert result.action_results[0].action.metadata["autodroid.phase"] == "shortcut"
    assert len(model.prompts) == 1
    assert "Page 0" in model.prompts[0].split("Current UI state:")[0]


@pytest.mark.fake_device_integration
@pytest.mark.parametrize("mode,expected", [("budget", RunStatus.STEP_LIMIT), ("device", RunStatus.DEVICE_FAILURE), ("parse", RunStatus.FAILURE)])
def test_graph_failure_and_budget_boundaries(tmp_path, monkeypatch, mode, expected):
    """Normalize bounded scanning, broken devices and invalid model output.

    Args:
        tmp_path: Isolated test input and artifact directory.
        monkeypatch: Fixture for bounded dependency substitution.
        mode: Failure or budget scenario to inject.
        expected: Expected action type or execution status.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    monkeypatch.setattr(InstructorEncoder, "encode", lambda self, texts, instruction: [(1, 0) for _ in texts])
    model = Model(["invalid"])
    graph = build_autodroid_graph(memory_path=str(memory_file(tmp_path)), max_steps=4,
                                 reasoning_params={"shortcut_enabled": False, "scan_enabled": mode != "parse"})
    device = Android(broken=mode == "device")
    agent = ExecutableAgent(graph, lambda: BuiltInComponentResolver(dependency_provider={"llm": model}))
    result = agent.run("Select Page 4", AgentRunConfig(artifact_root=tmp_path / "runs", max_steps=4, include_ui_tree=True), device=device)
    assert result.status is expected, result
    assert result.interaction_count <= 4
    assert not any(item.action.type is ActionType.DONE for item in result.action_results)
    if mode != "parse":
        assert model.prompts == []


@pytest.mark.fake_device_integration
def test_yaml_executes_twice_with_fresh_memory_history_and_policy(tmp_path, monkeypatch):
    """Execute the editable YAML using fresh contexts and model bindings.

    Args:
        tmp_path: Isolated test input and artifact directory.
        monkeypatch: Fixture for bounded dependency substitution.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    monkeypatch.setattr(InstructorEncoder, "encode", lambda self, texts, instruction: [(1, 0) for _ in texts])
    compiled = load_graph_yaml(Path(__file__).resolve().parents[2] / "examples/graphs/autodroid_online.yaml")
    # Bind the default example's path to an actual test fixture without modifying YAML.
    target = tmp_path / "examples" / "autodroid"
    target.mkdir(parents=True)
    memory_file(target).rename(target / "app_memory.json")
    monkeypatch.chdir(tmp_path)
    model = Model(['{"id":0}', '{"id":-1}', '{"id":0}', '{"id":-1}'])
    agent = ExecutableAgent(compiled.graph, lambda: BuiltInComponentResolver(dependency_provider={"llm": model}))
    for _ in range(2):
        device = Android(pages=1)
        result = agent.run("Select Page 4", AgentRunConfig(artifact_root=tmp_path / "runs", max_steps=20, include_ui_tree=True), device=device)
        assert result.status is RunStatus.SUCCESS, result
        assert sum(call[0] == "tap" for call in device.calls) == 1
    assert model.prompts[0] == model.prompts[2]
    assert model.prompts[1] == model.prompts[3]
    assert "Page 0" in model.prompts[1].split("Current UI state:")[0]
