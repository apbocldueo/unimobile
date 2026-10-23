"""Source-backed Aguvis contracts and actual graph execution with fake I/O."""

from __future__ import annotations

import ast
from contextlib import nullcontext
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from PIL import Image

from zhixing.aguvis import build_aguvis_graph
from zhixing.components import RunStatus, RuntimeContext
from zhixing.graph import GraphRole, load_graph_yaml
from zhixing.plugins.agent.aguvis_types import AguvisRequest
from zhixing.plugins.agent.parsers.aguvis_action_parser import AguvisActionParser
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
from zhixing.plugins.llm.aguvis_llm import AguvisLLM, request_messages, source_protocol
from zhixing.sdk import AgentRunConfig, compile_agent


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/aguvis"
SIZE = {"width": 100, "height": 200}


class Model:
    """Script only external predictions and retain typed production requests."""

    def __init__(self, responses):
        """Store ordered replies. Args: responses: Strings/errors. Returns: None."""
        self.responses, self.calls = list(responses), []

    def generate_aguvis(self, request):
        """Return one external reply without implementing any Agent logic.

        Args:
            request: Actual typed request assembled by production Reasoning.
        Raises:
            Exception: Scripted external failure or exhausted reply script.
        Returns:
            str: One continuation.
        """
        self.calls.append(request)
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value


class Android:
    """Record actual shared executor calls behind the explicit device boundary."""

    platform, serial, w, h = "android", "aguvis-fake", 100, 200

    def __init__(self, fail_tap=False):
        """Initialize logs. Args: fail_tap: Inject tap failure. Returns: None."""
        self.effects, self.images, self.fail_tap = [], [], fail_tap

    def screenshot(self, path):
        """Write a fresh PNG. Args: path: Artifact destination. Returns: str: Path."""
        Image.new("RGB", (self.w, self.h), (len(self.images), 0, 0)).save(path)
        self.images.append(str(path))
        return path

    def get_xml(self, path):
        """Reject XML. Args: path: Unexpected destination. Raises: AssertionError: Unexpected effect. Returns: None."""
        raise AssertionError("Aguvis default graph must not capture XML")

    def tap(self, x, y):
        """Record a tap. Args: x,y: Pixel. Raises: RuntimeError: Injected failure. Returns: None."""
        if self.fail_tap:
            raise RuntimeError("controlled device failure")
        self.effects.append(("tap", x, y))

    def input_text(self, text):
        """Record exact typing. Args: text: Literal text. Returns: None."""
        self.effects.append(("text", text))

    def enter(self):
        """Record explicit Enter. Returns: None."""
        self.effects.append(("enter",))

    def go_home(self):
        """Record Home. Returns: None."""
        self.effects.append(("home",))

    def go_back(self):
        """Record Back. Returns: None."""
        self.effects.append(("back",))

    def shell(self, command):
        """Record a validated shared swipe/key call. Args: command: Command. Returns: str: Empty output."""
        self.effects.append(("shell", command))
        return ""

    def long_press(self, x, y, duration_ms):
        """Record long press. Args: x,y,duration_ms: Validated settings. Returns: None."""
        self.effects.append(("long", x, y, duration_ms))

    def start_app(self, app):
        """Record shared app resolution boundary. Args: app: Name/package. Returns: None."""
        if app != "Settings":
            raise ValueError("unregistered app")
        self.effects.append(("app", app))

    def wait(self, seconds):
        """Record wait without sleeping. Args: seconds: Bounded duration. Returns: None."""
        self.effects.append(("wait", seconds))


def run_graph(tmp_path, responses, *, yaml=False, device=None, **options):
    """Run the production SDK/YAML graph with scripted external I/O only.

    Args:
        tmp_path: Isolated run artifact root.
        responses: External reply sequence.
        yaml: Select the actual user-editable YAML file.
        device: Optional failure-injecting fake Android.
        **options: Factory decision/command/interaction bounds.
    Returns:
        tuple: Actual RunResult, external model log, device log and runtime.
    """
    graph = load_graph_yaml(ROOT / "examples/graphs/aguvis_online.yaml") if yaml else build_aguvis_graph(**options)
    model, android = Model(responses), device or Android()
    context = RuntimeContext(max_steps=options.get("max_steps", 30))
    result = compile_agent(graph, dependencies={"llm": model}).run("Open settings",
        AgentRunConfig(artifact_root=tmp_path, max_steps=options.get("max_steps", 30)), device=android, runtime=context)
    return result, model, android, context


@pytest.mark.parametrize("mode,low", [
    ("self-plan", None), ("force-plan", None), ("grounding", None),
    ("self-plan", "Tap search"), ("grounding", "Tap search"),
])
def test_model_pipeline_matches_unmodified_official_function(tmp_path, mode, low):
    """Compare production messages, processor/generate args and decoding to source.

    Args:
        tmp_path: Real screenshot fixture directory.
        mode: Published generation mode.
        low: Optional low-level instruction taking prefill precedence.
    Raises:
        AssertionError: Source and implementation protocol diverge.
    Returns:
        None.
    """
    path = tmp_path / "screen.png"
    Image.new("RGB", (100, 200)).save(path)
    source = (FIXTURES / "official_cli.py.txt").read_text()
    provenance = json.loads((FIXTURES / "provenance.json").read_text())
    assert hashlib.sha256(source.encode()).hexdigest() == provenance["cli_sha256"]
    values = json.loads((FIXTURES / "source_protocol.json").read_text())
    assert source_protocol() == values
    module = ast.parse(source)
    function = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "generate_response")
    original = ast.fix_missing_locations(ast.Module(body=[ast.ImportFrom(module="__future__",
        names=[ast.alias(name="annotations")], level=0), function], type_ignores=[]))
    inputs = MagicMock()
    inputs.keys.return_value = ["input_ids"]
    inputs.__getitem__.return_value = [[1, 2, 3]]
    inputs.input_ids, inputs.to.return_value = [[1, 2, 3]], inputs
    processor = MagicMock(return_value=inputs)
    processor.apply_chat_template.return_value = "EXACT-SOURCE-TEMPLATE"
    model = MagicMock(device="fake")
    model.generate.return_value.tolist.return_value = [[1, 2, 3, 9, 10]]
    processor.tokenizer.decode.return_value = "  os\nmobile.back()" + values["until"][0] + "ignored  "
    vision = MagicMock(return_value=(["image-placeholder"], None))
    namespace = {**values, "process_vision_info": vision}
    exec(compile(original, "official_cli.py.txt", "exec"), namespace)
    image = Image.open(path).convert("RGB")
    history = ["Step 1: Open app", "Step 2: Find search"]
    expected = namespace["generate_response"](model, processor, processor.tokenizer, image,
        "Open settings", history, low, mode)
    expected_text = processor.call_args.kwargs["text"]
    expected_messages = processor.apply_chat_template.call_args.args[0]
    expected_generate = model.generate.call_args
    processor.reset_mock(); model.reset_mock()
    backend = AguvisLLM()
    backend._model, backend._processor = model, processor
    backend._vision = SimpleNamespace(process_vision_info=vision)
    backend._torch = SimpleNamespace(inference_mode=nullcontext)
    actual = backend.generate_aguvis(AguvisRequest("Open settings", str(path), tuple(history), mode, low))
    actual_messages = processor.apply_chat_template.call_args.args[0]
    assert actual == expected == "os\nmobile.back()"
    assert processor.call_args.kwargs["text"] == expected_text
    assert actual_messages[0] == expected_messages[0]
    assert actual_messages[1]["content"][1] == expected_messages[1]["content"][1]
    assert actual_messages[1]["content"][0]["image"].tobytes() == image.tobytes()
    assert model.generate.call_args == expected_generate
    processor.tokenizer.decode.assert_called_once_with([9, 10], skip_special_tokens=True)


@pytest.mark.parametrize("code,kind,params", [
    ("pyautogui.click(x=0.25,y=0.75)", "tap", {"x":25,"y":150}),
    ("pyautogui.click(1,0)", "tap", {"x":99,"y":0}),
    ("pyautogui.write(message='Ab C')", "text", {"text":"Ab C"}),
    ("pyautogui.press('backspace')", "key", {"code":"KEYCODE_DEL"}),
    ("mobile.long_press(0.5,0.5)", "long_press", {"x":50,"y":100,"duration_ms":1000}),
    ("mobile.swipe([0.5,0.8],[0.5,0.2])", "swipe", {"start_x":50,"start_y":160,"end_x":50,"end_y":40,"duration_ms":400}),
    ("pyautogui.scroll(page=-0.1)", "swipe", {"start_x":50,"start_y":110,"end_x":50,"end_y":90,"duration_ms":400}),
    ("mobile.wait(seconds=2)", "wait", {"seconds":2}),
    ("mobile.open_app(app_name='Settings')", "start_app", {"app":"Settings"}),
    ("mobile.terminate(status='infeasible')", "fail", {}),
])
def test_literal_mobile_protocol(code, kind, params):
    """Verify source examples plus explicitly declared adaptation mappings.

    Args:
        code: Literal input command.
        kind: Expected shared ActionType value.
        params: Expected explicit device parameters.
    Raises:
        AssertionError: A command changes units, text or side effects.
    Returns:
        None.
    """
    action = AguvisActionParser().parse(code, SIZE).commands[0].action
    assert action.type.value == kind and action.params == params


@pytest.mark.parametrize("code", [
    "", "not an action", "os.system('payload')", "pyautogui.click(-1,0.5)",
    "pyautogui.click(500,500)", "pyautogui.click(True,0.5)", "pyautogui.click(1e999,0)",
    "pyautogui.click(x=0.5,x=0.2,y=0.5)", "pyautogui.click(**{'x':0.5,'y':0.5})",
    "pyautogui.click(float('nan'),0.5)", "pyautogui.click(0.5,0.5); __import__('os').system('x')",
    "x=pyautogui.click(0.5,0.5)", "pyautogui.moveTo(0.5,0.5)", "pyautogui.hotkey('ctrl','c')",
    "pyautogui.press('unsupported')", "pyautogui.scroll(200)", "pyautogui.scroll(page=0)",
    "mobile.wait(100)", "pyautogui.write(123)", "terminate(status='maybe')",
    "mobile.terminate(); mobile.back()", "mobile.back()\nfor i in range(2): mobile.home()",
    "unsupported()\nmobile.back()",
    pytest.param("x" * 32769, id="oversized"),
])
def test_invalid_calls_fail_before_any_device_effect(code):
    """Reject expressions and unsupported semantics instead of guessing.

    Args:
        code: Malformed, unsafe or unsupported command block.
    Raises:
        AssertionError: An invalid command is accepted.
    Returns:
        None.
    """
    with pytest.raises(ActionParseError):
        AguvisActionParser().parse(code, SIZE)


@pytest.mark.fake_device_integration
@pytest.mark.parametrize("yaml", [False, True])
def test_online_graph_multi_command_history_and_answer(tmp_path, yaml):
    """Run shared components, exact history and ordered effects through both entries.

    Args:
        tmp_path: Isolated run artifacts.
        yaml: Exercise user YAML or SDK factory.
    Raises:
        AssertionError: Runtime ordering, history, answers or effects differ.
    Returns:
        None.
    """
    replies = ["all\nThought: Find settings\nAction: Open settings\nassistantos\nmobile.open_app(app_name='Settings')",
        "all\nThought: Fill field\nAction: Enter a query\nassistantos\npyautogui.click(0.25,0.75)\npyautogui.write('Ab C')\npyautogui.press('enter')",
        "os\npyautogui.scroll(page=-0.1)",
        "all\nAction: Reply and finish\nassistantos\nanswer('Found it')\nmobile.terminate(status='success')"]
    result, model, device, context = run_graph(tmp_path, replies, yaml=yaml)
    assert result.status is RunStatus.SUCCESS, result
    assert result.interaction_count == 5
    assert device.effects == [("app","Settings"),("tap",25,150),("text","Ab C"),("enter",),
                              ("shell","input swipe 50 110 50 90 400")]
    assert len(device.images) == len(model.calls) == 4
    assert model.calls[0].previous_actions == ()
    assert model.calls[1].previous_actions == ("Step 1: Open settings",)
    assert model.calls[2].previous_actions == ("Step 1: Open settings","Step 2: Enter a query")
    assert model.calls[3].previous_actions[-1] == "Step 3: pyautogui.scroll(page=-0.1)"
    assert [request.screenshot_path for request in model.calls] == device.images
    assert any(event.kind == "answer" and event.payload["text"] == "Found it" for event in result.events)
    assert (tmp_path/result.run_id/"manifest.json").is_file()


@pytest.mark.parametrize("fault,expected", [
    ("parse", RunStatus.FAILURE), ("model", RunStatus.FAILURE),
    ("device", RunStatus.DEVICE_FAILURE), ("decision_budget", RunStatus.FAILURE),
    ("physical_budget", RunStatus.STEP_LIMIT), ("too_many", RunStatus.FAILURE),
])
def test_failure_and_independent_budgets(tmp_path, fault, expected):
    """Stop failed batches without re-sampling or executing the remaining suffix.

    Args:
        tmp_path: Artifact directory.
        fault: Injected failure/budget condition.
        expected: Shared Runtime outcome.
    Raises:
        AssertionError: An effect/retry escapes its bound.
    Returns:
        None.
    """
    replies = {"parse":["mobile.back(); unsupported()"],
        "model":[RuntimeError("api_key=private-canary")],
        "device":["mobile.home(); pyautogui.click(0.5,0.5); mobile.back()"],
        "too_many":["mobile.back(); mobile.home(); mobile.back()"]}.get(fault,
            ["pyautogui.click(0.5,0.5)"]*3)
    result, model, device, _ = run_graph(tmp_path, replies,
        max_decisions=2 if fault=="decision_budget" else 30,
        max_steps=2 if fault=="physical_budget" else 30,
        max_commands=2 if fault=="too_many" else 16, device=Android(fail_tap=fault=="device"))
    assert result.status is expected, result
    assert len(model.calls) == (2 if fault.endswith("budget") else 1)
    assert device.effects == ([("home",)] if fault=="device" else
                              [("tap",50,100)]*2 if fault.endswith("budget") else [])
    assert "private-canary" not in json.dumps(result.to_safe_dict())


def test_answer_only_is_bounded_and_same_executable_has_fresh_history(tmp_path):
    """Keep answer separate from success and isolate consecutive runs.

    Args:
        tmp_path: Artifact directory.
    Raises:
        AssertionError: Answer implies completion or task history leaks.
    Returns:
        None.
    """
    result, model, device, _ = run_graph(tmp_path, ["answer('hello')"]*3, max_decisions=2)
    assert result.status is RunStatus.FAILURE and result.interaction_count == 0
    assert len(model.calls) == 2 and device.effects == []
    model = Model(["mobile.back()","terminate('success')"]*2)
    agent = compile_agent(build_aguvis_graph(), dependencies={"llm":model})
    for _ in range(2):
        assert agent.run("Open settings", AgentRunConfig(artifact_root=tmp_path), device=Android()).status is RunStatus.SUCCESS
    assert model.calls[0].previous_actions == model.calls[2].previous_actions == ()
    assert model.calls[1].previous_actions == model.calls[3].previous_actions == ("Step 1: mobile.back()",)


def test_yaml_and_sdk_identity_and_unmodified_default_memory_contract():
    """Keep the example fully editable and existing role contracts stable.

    Raises:
        AssertionError: Authoring paths differ or an old default is replaced.
    Returns:
        None.
    """
    from zhixing.graph.contracts import contract_ref_for_role
    graph = build_aguvis_graph()
    assert graph.canonical_hash() == load_graph_yaml(ROOT/"examples/graphs/aguvis_online.yaml").graph.canonical_hash()
    assert contract_ref_for_role(GraphRole.MEMORY).id == "zhixing.core.memory"
    assert contract_ref_for_role(GraphRole.MEMORY).version == "1.0"


def test_lazy_model_loading_is_cached_and_uses_pinned_processor(monkeypatch):
    """Check actual backend initialization without importing the optional stack.

    Args:
        monkeypatch: Replace only optional module imports with external mocks.
    Raises:
        AssertionError: Configuration, load order or cache behavior diverges.
    Returns:
        None.
    """
    import zhixing.plugins.llm.aguvis_llm as module
    model_class, processor_class = MagicMock(), MagicMock()
    modules = {"torch":object(),"qwen_vl_utils":object(),"transformers":SimpleNamespace(
        Qwen2VLForConditionalGeneration=model_class,Qwen2VLProcessor=processor_class)}
    importer = MagicMock(side_effect=modules.__getitem__)
    monkeypatch.setattr(module,"import_module",importer)
    backend = AguvisLLM(model_path="missing-local-model")
    assert importer.call_count == 0 and backend._model is None
    backend._load(); backend._load()
    options={"local_files_only":True,"revision":"6dd54127b5b84b9ee89172a5065ab6be576f0db9"}
    model_class.from_pretrained.assert_called_once_with("missing-local-model",**options)
    processor_class.from_pretrained.assert_called_once_with("missing-local-model",**options)
    model_class.from_pretrained.return_value.to.assert_called_once_with("cuda")
    model_class.from_pretrained.return_value.tie_weights.assert_called_once_with()
    assert importer.call_count == 3


def test_compile_and_configuration_never_access_optional_models(monkeypatch):
    """Keep authoring usable even when all optional runtime imports would fail.

    Args:
        monkeypatch: Install an optional-import canary.
    Raises:
        AssertionError: Compile or configuration triggers inference dependencies.
    Returns:
        None.
    """
    import zhixing.plugins.llm.aguvis_llm as module
    importer=MagicMock(side_effect=AssertionError("optional import during authoring"))
    monkeypatch.setattr(module,"import_module",importer)
    AguvisLLM("missing-local-model")
    compile_agent(build_aguvis_graph(model_params={"model_path":"missing-local-model"}))
    assert importer.call_count == 0


def test_physical_budget_stops_inside_batch_and_retains_prefix(tmp_path):
    """Prevent batch execution from bypassing the shared physical-action limit.

    Args:
        tmp_path: Artifact directory.
    Raises:
        AssertionError: An unbudgeted suffix or second model call executes.
    Returns:
        None.
    """
    result,model,device,_=run_graph(tmp_path,["mobile.home(); mobile.back(); mobile.home()"],max_steps=2)
    assert result.status is RunStatus.STEP_LIMIT
    assert len(model.calls)==1 and device.effects==[("home",),("back",)]
    assert len(result.action_results)==2


def test_explicit_wheel_conversion_and_custom_gesture_settings():
    """Make extra action semantics configurable rather than silently guessing.

    Raises:
        AssertionError: Configuration is ignored or typing gets an extra Enter.
    Returns:
        None.
    """
    parser=AguvisActionParser(gesture_duration_ms=500,long_press_ms=1200,scroll_pixels_per_click=2)
    scroll=parser.parse("pyautogui.scroll(-10)",SIZE).commands[0].action
    assert scroll.params=={"start_x":50,"start_y":110,"end_x":50,"end_y":90,"duration_ms":500}
    assert parser.parse("mobile.long_press(0.5,0.5)",SIZE).commands[0].action.params["duration_ms"]==1200
    assert parser.parse("pyautogui.write('a')",SIZE).commands[0].action.params=={"text":"a"}


def test_request_empty_history_and_prefilled_instruction():
    """Keep the grounding system while low-level text controls the prefill.

    Raises:
        AssertionError: Empty history or prefill placement differs from source.
    Returns:
        None.
    """
    request=AguvisRequest("Goal","screen.png",mode="grounding",low_level_instruction="Tap search")
    messages,prefix=request_messages(request,object())
    assert messages[0]["content"]==source_protocol()["grounding_system_message"]
    assert "Previous actions:\nNone" in messages[1]["content"][1]["text"]
    assert "Tap search" not in messages[1]["content"][1]["text"]
    assert prefix.endswith("all\nAction: Tap search\n")
    with pytest.raises(ValueError):
        request_messages(AguvisRequest("Goal","screen.png",previous_actions="wrong-shape"),object())


def test_exact_fragment_extension_does_not_reformat_metadata():
    """Pass explicit fragments through the generic assembler unchanged.

    Raises:
        AssertionError: The shared adapter changes content or metadata.
    Returns:
        None.
    """
    from zhixing.runtime.assemblers import _memory_fragment
    from zhixing.core.agent.protocol import MemoryFragment, FragmentType
    fragment=MemoryFragment("assistant",FragmentType.TEXT,"Step 2: Tap search",{"source":"aguvis.low_level"})
    assert _memory_fragment(fragment,99) is fragment


def test_scroll_adapter_never_emits_out_of_bounds_on_small_screen():
    """Keep normalized page gestures valid at the smallest supported extent.

    Raises:
        AssertionError: A generated swipe endpoint exceeds screenshot dimensions.
    Returns:
        None.
    """
    for page in (-0.8,0.8):
        action=AguvisActionParser().parse(f"pyautogui.scroll(page={page})",{"width":2,"height":2}).commands[0].action
        assert all(0<=action.params[key]<2 for key in ("start_x","start_y","end_x","end_y"))


@pytest.mark.parametrize("options", [
    {"mode":"unknown"}, {"max_decisions":True}, {"max_commands":0},
    {"parser_params":{"unexpected":1}}, {"max_decisions":1000,"max_commands":32},
])
def test_invalid_graph_configuration_is_side_effect_free(options):
    """Reject invalid authoring bounds before any binding or execution.

    Args:
        options: Invalid factory configuration.
    Raises:
        AssertionError: Invalid configuration is accepted.
    Returns:
        None.
    """
    with pytest.raises(ValueError):
        build_aguvis_graph(**options)
