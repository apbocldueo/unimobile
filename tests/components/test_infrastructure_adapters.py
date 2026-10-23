from __future__ import annotations

import sys

import pytest

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionType,
    BenchmarkInitInput,
    BenchmarkInitKind,
    ComponentInputError,
    DeviceOperation,
    DeviceRequest,
    EvalResult,
    EvaluationInput,
    ExecutionStatus,
    LLMInput,
    LLMResult,
    LLMUsage,
    LegacyActionExecutor,
    RuntimeContext,
    adapt_component,
)


class FakeDevice:
    w = 100
    h = 200
    platform = "android"

    def __init__(self):
        self.calls = []

    def screenshot(self, path, method="snapshot_display"):
        self.calls.append(("screenshot", path))
        return path

    def get_xml(self, path):
        self.calls.append(("xml", path))

    def display_size(self):
        return self.w, self.h

    def tap(self, x, y):
        self.calls.append(("tap", x, y))

    def long_press(self, x, y, duration_ms=1000):
        self.calls.append(("long_press", x, y, duration_ms))

    def swipe(self, direction, scale=0.8, **kwargs):
        self.calls.append(("swipe", direction, scale))

    def input_text(self, text):
        self.calls.append(("text", text))

    def clear_text(self, num=15):
        self.calls.append(("clear",))

    def go_home(self):
        self.calls.append(("home",))

    def go_back(self):
        self.calls.append(("back",))

    def enter(self):
        self.calls.append(("enter",))

    def start_app(self, app, page=""):
        self.calls.append(("start_app", app))

    def wait(self, seconds):
        self.calls.append(("wait", seconds))

    def shell(self, command):
        self.calls.append(("shell", command))
        return "ok"


def test_llm_adapters_normalize_text_usage_and_reverse_generate():
    plugin_modules_before = {
        name for name in sys.modules if name.startswith("zhixing.plugins.llm")
    }

    class LegacyLLM:
        model = "fake"

        def generate(self, prompt, images=None):
            return "answer", {"prompt_tokens": 2, "completion_tokens": 3, "total_tokens": 5}

    result = adapt_component("llm", LegacyLLM()).invoke(
        LLMInput("question", ("shot.png",)), RuntimeContext()
    )
    assert result == LLMResult("answer", LLMUsage(2, 3, 5), "fake")

    class NewLLM:
        def invoke(self, input, runtime):
            return LLMResult(input.prompt.upper())

    legacy = adapt_component("llm", NewLLM(), "legacy")
    assert legacy.generate("hello") == "HELLO"
    plugin_modules_after = {
        name for name in sys.modules if name.startswith("zhixing.plugins.llm")
    }
    assert plugin_modules_after == plugin_modules_before


def test_device_adapter_observation_operations_bounds_and_execution_failure(tmp_path):
    device = FakeDevice()
    adapted = adapt_component("device", device)
    observation = adapted.invoke(
        DeviceRequest(
            DeviceOperation.OBSERVE,
            {"screenshot_path": str(tmp_path / "shot.png"), "ui_path": str(tmp_path / "tree.xml")},
        ),
        RuntimeContext(),
    ).observation
    assert observation.width == 100
    assert observation.height == 200
    assert observation.platform == "android"
    assert device.calls[:2] == [
        ("screenshot", str(tmp_path / "shot.png")),
        ("xml", str(tmp_path / "tree.xml")),
    ]

    assert adapted.invoke(DeviceRequest(DeviceOperation.TAP, {"x": 10, "y": 20}), RuntimeContext()).success
    with pytest.raises(ComponentInputError, match="out of bounds"):
        adapted.invoke(DeviceRequest(DeviceOperation.TAP, {"x": 100, "y": 20}), RuntimeContext())

    class BrokenDevice(FakeDevice):
        def tap(self, x, y):
            raise RuntimeError("device offline")

    failed = adapt_component("device", BrokenDevice()).invoke(
        DeviceRequest(DeviceOperation.TAP, {"x": 1, "y": 1}), RuntimeContext()
    )
    assert not failed.success
    assert failed.error == "device offline"


@pytest.mark.parametrize(
    ("action", "expected"),
    [
        (Action(ActionType.TAP, {"x": 1, "y": 2}), ("tap", 1, 2)),
        (Action(ActionType.LONG_PRESS, {"x": 1, "y": 2, "duration_ms": 500}), ("long_press", 1, 2, 500)),
        (Action(ActionType.TEXT, {"text": "hello"}), ("text", "hello")),
        (Action(ActionType.SWIPE, {"direction": "up", "dist": "short"}), ("swipe", "up", 0.4)),
        (Action(ActionType.KEY, {"code": "back"}), ("back",)),
        (Action(ActionType.START_APP, {"app": "settings"}), ("start_app", "settings")),
        (Action(ActionType.WAIT, {"seconds": 0}), ("wait", 0.5)),
    ],
)
def test_action_executor_matches_runner_action_mapping(action, expected):
    device = FakeDevice()
    result = LegacyActionExecutor().invoke(
        ActionExecutionInput(action), RuntimeContext(device=device)
    )
    assert result.status is ExecutionStatus.SUCCESS
    assert expected in device.calls


def test_action_executor_terminal_failure_precise_swipe_and_device_failure():
    executor = LegacyActionExecutor()
    device = FakeDevice()
    runtime = RuntimeContext(device=device)
    done = executor.invoke(ActionExecutionInput(Action(ActionType.DONE)), runtime)
    failed = executor.invoke(ActionExecutionInput(Action(ActionType.FAIL, thought="bad")), runtime)
    swipe = executor.invoke(
        ActionExecutionInput(
            Action(
                ActionType.SWIPE,
                {"start_x": 1, "start_y": 2, "end_x": 3, "end_y": 4, "duration_ms": 300},
            )
        ),
        runtime,
    )
    missing = executor.invoke(
        ActionExecutionInput(Action(ActionType.TAP, {"x": 1, "y": 2})), RuntimeContext()
    )
    assert done.status is ExecutionStatus.TERMINAL
    assert failed.status is ExecutionStatus.FAILURE
    assert swipe.status is ExecutionStatus.SUCCESS
    assert ("shell", "input swipe 1 2 3 4 300") in device.calls
    assert missing.status is ExecutionStatus.DEVICE_FAILURE


def test_benchmark_initializer_variants_are_strict_and_bidirectional():
    class TaskGenerator:
        def generate(self, params):
            return params["seed"] * 2

    class EnvironmentInitializer:
        def execute(self, meta, params):
            return meta["ready"] and params["enabled"]

    runtime = RuntimeContext()
    task = adapt_component("benchmark_initializer", TaskGenerator())
    assert task.invoke(
        BenchmarkInitInput(BenchmarkInitKind.TASK_PARAMETER, {"seed": 3}), runtime
    ).value == 6
    with pytest.raises(ComponentInputError, match="cannot accept environment"):
        task.invoke(BenchmarkInitInput(BenchmarkInitKind.ENVIRONMENT), runtime)

    environment = adapt_component("benchmark_initializer", EnvironmentInitializer())
    assert environment.invoke(
        BenchmarkInitInput(
            BenchmarkInitKind.ENVIRONMENT,
            params={"enabled": True},
            meta={"ready": True},
        ),
        runtime,
    ).success

    class NewInitializer:
        def invoke(self, input, runtime):
            from zhixing.components import BenchmarkInitResult

            return BenchmarkInitResult(input.kind, True, value="new")

    reverse_task = adapt_component(
        "benchmark_initializer",
        NewInitializer(),
        "legacy",
        initializer_kind=BenchmarkInitKind.TASK_PARAMETER,
    )
    reverse_env = adapt_component(
        "benchmark_initializer",
        NewInitializer(),
        "legacy",
        initializer_kind=BenchmarkInitKind.ENVIRONMENT,
    )
    assert reverse_task.generate({}) == "new"
    assert reverse_env.execute({}, {}) is True


def test_evaluator_adapters_preserve_eval_result_and_current_entry_point():
    class LegacyEvaluator:
        def evaluate(self, context):
            return EvalResult(context["pass"], "checked", 2.0)

    result = adapt_component("evaluator", LegacyEvaluator()).invoke(
        EvaluationInput({"pass": True}), RuntimeContext()
    )
    assert result == EvalResult(True, "checked", 2.0)

    class NewEvaluator:
        def invoke(self, input, runtime):
            return EvalResult(bool(input.context["pass"]), "new", 0.0)

    reverse = adapt_component("evaluator", NewEvaluator(), "legacy")
    assert reverse.evaluate({"pass": True}) == EvalResult(True, "new", 0.0)


def test_registry_hook_preserves_conforming_instances_and_does_not_double_wrap():
    from zhixing.core.factory import PluginRegistry

    class NewLLM:
        def invoke(self, input, runtime):
            return LLMResult("ok")

    instance = NewLLM()
    assert PluginRegistry.adapt_instance("llm", instance) is instance
    legacy = PluginRegistry.adapt_instance("llm", instance, "legacy")
    assert legacy.generate("x") == "ok"
