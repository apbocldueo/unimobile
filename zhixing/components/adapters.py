"""Explicit compatibility adapters between legacy methods and ``invoke``."""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Optional

from zhixing.core.agent.protocol import Action, ActionType, PerceptionInput, PlanResult
from zhixing.core.benchmark.protocol import EvalResult

from .errors import ComponentInputError, ComponentProtocolError
from .models import (
    ActionExecutionInput,
    ActionResult,
    BenchmarkInitInput,
    BenchmarkInitKind,
    BenchmarkInitResult,
    DeviceObservation,
    DeviceEffectKind,
    DeviceOperation,
    DeviceRequest,
    DeviceResult,
    EvaluationInput,
    ExecutionStatus,
    GroundingInput,
    GroundingResult,
    LLMInput,
    LLMResult,
    LLMUsage,
    MemoryInput,
    MemoryOperation,
    MemoryResult,
    ReasoningInput,
    RuntimeContext,
    RunStatus,
    TaskInput,
)
from .protocols import ComponentRole, get_role_descriptor


RAW_RESPONSE_METADATA_KEY = "zhixing.legacy.raw_response"


def _runtime(runtime: Optional[RuntimeContext]) -> RuntimeContext:
    return runtime if runtime is not None else RuntimeContext()


class LegacyPerceptionAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: DeviceObservation, runtime: RuntimeContext):
        if not isinstance(input, DeviceObservation):
            raise ComponentInputError("Perception expects DeviceObservation")
        return self.legacy.perceive(input.to_legacy())


class InvokePerceptionAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def perceive(self, perception_input: PerceptionInput):
        return self.component.invoke(DeviceObservation.from_legacy(perception_input), self.runtime)


class LegacyPlannerAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: Any, runtime: RuntimeContext) -> PlanResult:
        return self.legacy.make_plan(input)


class InvokePlannerAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def make_plan(self, plan_input: Any) -> PlanResult:
        return self.component.invoke(plan_input, self.runtime)


class LegacyReasoningAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: ReasoningInput, runtime: RuntimeContext) -> Action:
        if not isinstance(input, ReasoningInput):
            raise ComponentInputError("Reasoning expects ReasoningInput")
        result = self.legacy.think(
            task=input.task.instruction,
            plan=input.plan.content,
            perception_result=input.perception,
            memory_context=list(input.memory_context),
            available_apps=input.available_apps,
        )
        if isinstance(result, tuple):
            if len(result) != 2 or not isinstance(result[0], Action):
                raise ComponentInputError("Legacy Reasoning tuple must be (Action, raw_response)")
            action, raw_response = result
            action.metadata = dict(action.metadata or {})
            action.metadata[RAW_RESPONSE_METADATA_KEY] = str(raw_response or "")
            return action
        if not isinstance(result, Action):
            raise ComponentInputError("Legacy Reasoning must return Action or (Action, raw_response)")
        return result


class InvokeReasoningAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def think(
        self,
        task: str,
        plan: Any,
        perception_result: Any,
        memory_context: list[Any],
        *,
        available_apps: str = "",
    ) -> tuple[Action, str]:
        plan_value = plan if isinstance(plan, PlanResult) else PlanResult(content=str(plan))
        action = self.component.invoke(
            ReasoningInput(
                task=TaskInput(instruction=task),
                plan=plan_value,
                perception=perception_result,
                memory_context=tuple(memory_context),
                available_apps=available_apps,
            ),
            self.runtime,
        )
        if not isinstance(action, Action):
            raise ComponentInputError("Canonical Reasoning must return Action")
        return action, str((action.metadata or {}).get(RAW_RESPONSE_METADATA_KEY, ""))


class LegacyMemoryAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: MemoryInput, runtime: RuntimeContext) -> MemoryResult:
        if not isinstance(input, MemoryInput):
            raise ComponentInputError("Memory expects MemoryInput")
        if input.operation is MemoryOperation.APPEND:
            if input.fragment is None:
                raise ComponentInputError("Memory append requires fragment")
            self.legacy.add(input.fragment)
            return MemoryResult(input.operation)
        if input.operation is MemoryOperation.READ:
            return MemoryResult(input.operation, fragments=tuple(self.legacy.get_working_context()))
        if input.operation is MemoryOperation.RESET:
            self.legacy.clear()
            return MemoryResult(input.operation)
        if input.operation is MemoryOperation.LOAD_KNOWLEDGE:
            if not hasattr(self.legacy, "load_knowledge"):
                raise ComponentInputError("Legacy Memory does not support load_knowledge")
            self.legacy.load_knowledge(input.query)
            return MemoryResult(input.operation)
        if input.operation is MemoryOperation.RETRIEVE_EXPERIENCE:
            if not hasattr(self.legacy, "retrieve_experience"):
                raise ComponentInputError("Legacy Memory does not support retrieve_experience")
            action = self.legacy.retrieve_experience(input.screenshot_path, input.task)
            return MemoryResult(input.operation, action=action)
        raise ComponentInputError(f"Unsupported Memory operation: {input.operation}")


class InvokeMemoryAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def add(self, fragment: Any) -> None:
        self.component.invoke(MemoryInput(MemoryOperation.APPEND, fragment=fragment), self.runtime)

    def get_working_context(self) -> list[Any]:
        return list(self.component.invoke(MemoryInput(MemoryOperation.READ), self.runtime).fragments)

    def clear(self) -> None:
        self.component.invoke(MemoryInput(MemoryOperation.RESET), self.runtime)

    def load_knowledge(self, query: str) -> None:
        self.component.invoke(MemoryInput(MemoryOperation.LOAD_KNOWLEDGE, query=query), self.runtime)

    def retrieve_experience(self, screenshot_path: str, task: str) -> Optional[Action]:
        return self.component.invoke(
            MemoryInput(
                MemoryOperation.RETRIEVE_EXPERIENCE,
                screenshot_path=screenshot_path,
                task=task,
            ),
            self.runtime,
        ).action


class LegacyVerifierAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: Any, runtime: RuntimeContext):
        return self.legacy.verify(input)


class InvokeVerifierAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def verify(self, input_data: Any):
        return self.component.invoke(input_data, self.runtime)


class LegacyGrounderAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: GroundingInput, runtime: RuntimeContext) -> GroundingResult:
        if not isinstance(input, GroundingInput):
            raise ComponentInputError("Grounder expects GroundingInput")
        obs = input.observation
        result = self.legacy.ground(
            obs.screenshot_path,
            input.description,
            obs.width,
            obs.height,
        )
        if isinstance(result, GroundingResult):
            return result
        try:
            x, y = result
        except (TypeError, ValueError) as error:
            raise ComponentInputError("Legacy Grounder must return (x, y)") from error
        return GroundingResult(x=int(x), y=int(y))


class InvokeGrounderAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def ground(self, screenshot_path: str, description: str, width: int, height: int) -> tuple[int, int]:
        result = self.component.invoke(
            GroundingInput(DeviceObservation(screenshot_path, width, height), description),
            self.runtime,
        )
        return result.x, result.y


def _normalize_usage(value: Any) -> Optional[LLMUsage]:
    if value is None:
        return None
    if isinstance(value, LLMUsage):
        return value
    if isinstance(value, Mapping):
        return LLMUsage(
            prompt_tokens=int(value.get("prompt_tokens", 0) or 0),
            completion_tokens=int(value.get("completion_tokens", 0) or 0),
            total_tokens=int(value.get("total_tokens", 0) or 0),
        )
    return None


class LegacyLLMAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: LLMInput, runtime: RuntimeContext) -> LLMResult:
        result = self.legacy.generate(input.prompt, images=list(input.images) or None)
        if isinstance(result, LLMResult):
            return result
        if isinstance(result, tuple) and len(result) == 2:
            return LLMResult(
                text=str(result[0] or ""),
                usage=_normalize_usage(result[1]),
                model=getattr(self.legacy, "model", None),
            )
        return LLMResult(text=str(result or ""), model=getattr(self.legacy, "model", None))


class InvokeLLMAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def generate(self, prompt: str, images: Optional[list[str]] = None) -> str:
        return self.component.invoke(LLMInput(prompt, tuple(images or ())), self.runtime).text


def _coordinate(device: Any, params: Mapping[str, Any], name: str) -> int:
    try:
        value = int(params[name])
    except (KeyError, TypeError, ValueError) as error:
        raise ComponentInputError(f"Device operation requires integer '{name}'") from error
    limit = getattr(device, "w" if name.endswith("x") or name == "x" else "h", 0)
    if value < 0 or (int(limit or 0) > 0 and value >= int(limit)):
        raise ComponentInputError(f"Device coordinate '{name}' is out of bounds")
    return value


class LegacyDeviceAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: DeviceRequest, runtime: RuntimeContext) -> DeviceResult:
        if not isinstance(input, DeviceRequest):
            raise ComponentInputError("Device expects DeviceRequest")
        op, params = input.operation, input.params
        try:
            if op is DeviceOperation.OBSERVE:
                path = str(params.get("screenshot_path") or "")
                if not path:
                    raise ComponentInputError("Device observe requires screenshot_path")
                self.legacy.screenshot(path)
                ui_path = params.get("ui_path")
                if ui_path and hasattr(self.legacy, "get_xml"):
                    self.legacy.get_xml(str(ui_path))
                width = int(params.get("width") or getattr(self.legacy, "w", 0))
                height = int(params.get("height") or getattr(self.legacy, "h", 0))
                if (not width or not height) and hasattr(self.legacy, "display_size"):
                    width, height = self.legacy.display_size()
                observation = DeviceObservation(
                    path,
                    width,
                    height,
                    str(ui_path) if ui_path else None,
                    platform=str(getattr(self.legacy, "platform", "unknown")),
                )
                return DeviceResult(op, True, observation=observation)
            if op is DeviceOperation.TAP:
                self.legacy.tap(_coordinate(self.legacy, params, "x"), _coordinate(self.legacy, params, "y"))
            elif op is DeviceOperation.LONG_PRESS:
                self.legacy.long_press(
                    _coordinate(self.legacy, params, "x"),
                    _coordinate(self.legacy, params, "y"),
                    duration_ms=int(params.get("duration_ms", 1000)),
                )
            elif op is DeviceOperation.SWIPE:
                self.legacy.swipe(
                    direction=str(params.get("direction", "left")),
                    scale=float(params.get("scale", 0.6)),
                )
            elif op is DeviceOperation.TEXT:
                self.legacy.input_text(str(params.get("text", "")))
            elif op is DeviceOperation.KEY:
                _execute_key(self.legacy, str(params.get("code", "")))
            elif op is DeviceOperation.START_APP:
                app = str(params.get("app", "")).strip()
                if not app:
                    raise ComponentInputError("Device start_app requires app")
                self.legacy.start_app(app)
            elif op is DeviceOperation.WAIT:
                self.legacy.wait(float(params.get("seconds", 2.0)))
            elif op is DeviceOperation.SHELL:
                return DeviceResult(op, True, value=self.legacy.shell(str(params.get("command", ""))))
            else:
                raise ComponentInputError(f"Unsupported Device operation: {op}")
            return DeviceResult(op, True)
        except ComponentInputError:
            raise
        except Exception as error:
            return DeviceResult(op, False, error=_safe_error(error))


class InvokeDeviceAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def _call(self, operation: DeviceOperation, **params: Any) -> DeviceResult:
        return self.component.invoke(DeviceRequest(operation, params), self.runtime)

    def screenshot(self, path: str, method: str = "snapshot_display") -> str:
        result = self._call(DeviceOperation.OBSERVE, screenshot_path=path, method=method)
        return result.observation.screenshot_path if result.observation else path

    def tap(self, x: int, y: int) -> None:
        self._call(DeviceOperation.TAP, x=x, y=y)

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        self._call(DeviceOperation.LONG_PRESS, x=x, y=y, duration_ms=duration_ms)

    def swipe(self, direction: str, scale: float = 0.8, box: Any = None, speed: int = 1600) -> None:
        self._call(DeviceOperation.SWIPE, direction=direction, scale=scale, box=box, speed=speed)

    def input_text(self, text: str) -> None:
        self._call(DeviceOperation.TEXT, text=text)

    def wait(self, seconds: float = 2.0) -> None:
        self._call(DeviceOperation.WAIT, seconds=seconds)

    def start_app(self, app: str, page: str = "") -> None:
        self._call(DeviceOperation.START_APP, app=app, page=page)

    def shell(self, command: str) -> Any:
        return self._call(DeviceOperation.SHELL, command=command).value

    def go_home(self) -> None:
        self._call(DeviceOperation.KEY, code="home")

    def go_back(self) -> None:
        self._call(DeviceOperation.KEY, code="back")

    def enter(self) -> None:
        self._call(DeviceOperation.KEY, code="enter")

    def clear_text(self, num: int = 15) -> None:
        self._call(DeviceOperation.KEY, code="clear", num=num)


def _execute_key(device: Any, code: str) -> None:
    code = code.lower()
    if code == "home":
        device.go_home()
    elif code == "back":
        device.go_back()
    elif code == "enter":
        device.enter()
    elif code in {"del", "clear"}:
        device.clear_text()
    elif code in {"menu", "appselect", "recent", "recents"}:
        device.shell("input keyevent KEYCODE_APP_SWITCH")
    elif code:
        device.shell(f"input keyevent {code.upper()}")
    else:
        raise ComponentInputError("KEY action requires code")


def _safe_error(error: Exception) -> str:
    text = str(error).replace("\n", " ")[:500]
    lowered = text.lower()
    if any(word in lowered for word in ("api_key", "token", "password", "secret")):
        return "<redacted>"
    return text


class LegacyActionExecutor:
    """Compatibility executor matching the current AgentRunner action mapping."""

    def __init__(self, device: Any = None) -> None:
        """Create an executor with an optional fallback device.

        Args:
            device (Any): Device used when RuntimeContext has no device.

        Raises:
            None.

        Returns:
            None: Initializes the compatibility executor.
        """
        self.device = device

    def invoke(self, input: ActionExecutionInput, runtime: RuntimeContext) -> ActionResult:
        """Execute one typed action and report confirmed device effects.

        Args:
            input (ActionExecutionInput): Action and optional observation.
            runtime (RuntimeContext): Run-scoped device and state.

        Raises:
            None: Input and device failures are normalized as ActionResult.

        Returns:
            ActionResult: Status, terminal semantics, and confirmed effect.
        """
        action = input.action
        selected_device = runtime.device or self.device
        device_id = str(getattr(selected_device, "serial", "") or "")
        if action.type is ActionType.DONE:
            return ActionResult(
                action,
                ExecutionStatus.TERMINAL,
                "Agent completed",
                terminal_status=RunStatus.SUCCESS,
                device_id=device_id,
            )
        if action.type is ActionType.FAIL:
            return ActionResult(
                action,
                ExecutionStatus.FAILURE,
                error=action.thought or "Agent failed",
                terminal_status=RunStatus.FAILURE,
                device_id=device_id,
            )
        device = selected_device
        if device is None:
            return ActionResult(action, ExecutionStatus.DEVICE_FAILURE, error="No Device in RuntimeContext")
        if action.type is ActionType.WAIT:
            try:
                seconds = max(0.5, min(float(action.params.get("seconds", 2.0)), 30.0))
                device.wait(seconds)
                return ActionResult(
                    action,
                    ExecutionStatus.SUCCESS,
                    metadata={"seconds": seconds},
                    effect_kind=DeviceEffectKind.WAIT,
                    device_id=device_id,
                )
            except Exception as error:
                return ActionResult(
                    action,
                    ExecutionStatus.DEVICE_FAILURE,
                    error=_safe_error(error),
                    device_id=device_id,
                )
        try:
            self._execute(device, action)
            return ActionResult(
                action,
                ExecutionStatus.SUCCESS,
                effect_performed=True,
                effect_kind=_effect_kind(action),
                device_id=device_id,
            )
        except ComponentInputError as error:
            return ActionResult(
                action,
                ExecutionStatus.FAILURE,
                error=str(error),
                device_id=device_id,
            )
        except Exception as error:
            return ActionResult(
                action,
                ExecutionStatus.DEVICE_FAILURE,
                error=_safe_error(error),
                device_id=device_id,
            )

    @staticmethod
    def _execute(device: Any, action: Action) -> None:
        """Dispatch one supported non-terminal action to a device.

        Args:
            device (Any): Concrete device exposing normalized primitives.
            action (Action): Validated action to execute.

        Raises:
            ComponentInputError: Action parameters or type are unsupported.
            Exception: Concrete device command failures propagate to ``invoke``.

        Returns:
            None: The device primitive completed successfully.
        """
        params = action.params
        if action.type is ActionType.TAP:
            x, y = _coordinate(device, params, "x"), _coordinate(device, params, "y")
            device.tap(x, y)
            if (action.metadata or {}).get("repeat_tap") == 2:
                time.sleep(0.1)
                device.tap(x, y)
        elif action.type is ActionType.LONG_PRESS:
            device.long_press(
                _coordinate(device, params, "x"),
                _coordinate(device, params, "y"),
                duration_ms=int(params.get("duration_ms", 1000)),
            )
        elif action.type is ActionType.TEXT:
            if "x" in params and "y" in params:
                device.tap(_coordinate(device, params, "x"), _coordinate(device, params, "y"))
            device.input_text(str(params.get("text", "")))
            if params.get("press_enter_after"):
                device.enter()
        elif action.type is ActionType.SWIPE:
            _execute_swipe(device, params)
        elif action.type is ActionType.KEY:
            _execute_key(device, str(params.get("code", "")))
        elif action.type is ActionType.START_APP:
            app = str(params.get("app", "")).strip()
            if not app:
                raise ComponentInputError("START_APP action requires app")
            device.start_app(app)
        else:
            raise ComponentInputError(f"Unsupported executable ActionType: {action.type.value}")


def _effect_kind(action: Action) -> DeviceEffectKind:
    """Map one executed action to its physical effect category.

    Args:
        action (Action): Successfully executed non-terminal action.

    Raises:
        None.

    Returns:
        DeviceEffectKind: Stable effect category for metrics and events.
    """
    if action.type is ActionType.START_APP:
        return DeviceEffectKind.APP_LAUNCH
    return DeviceEffectKind.UI_INPUT


class InvokeActionExecutorAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def execute(self, action: Action) -> ActionResult:
        return self.component.invoke(ActionExecutionInput(action), self.runtime)


def _execute_swipe(device: Any, params: Mapping[str, Any]) -> None:
    if all(key in params for key in ("start_x", "start_y", "end_x", "end_y")):
        start_x = _coordinate(device, params, "start_x")
        start_y = _coordinate(device, params, "start_y")
        end_x = _coordinate(device, params, "end_x")
        end_y = _coordinate(device, params, "end_y")
        duration_ms = int(params.get("duration_ms", 400))
        if not hasattr(device, "shell"):
            raise ComponentInputError("Precise swipe requires Device.shell")
        device.shell(f"input swipe {start_x} {start_y} {end_x} {end_y} {duration_ms}")
        return
    direction = str(params.get("direction", "left")).lower()
    dist = str(params.get("dist", "medium")).lower()
    scale = {"short": 0.4, "medium": 0.6, "long": 0.8}.get(dist, 0.6)
    if "x" in params and "y" in params and hasattr(device, "shell"):
        x, y = _coordinate(device, params, "x"), _coordinate(device, params, "y")
        unit = int(getattr(device, "w", 1080) / 10)
        unit *= 3 if dist == "long" else 2 if dist == "medium" else 1
        dx, dy = {
            "up": (0, -2 * unit),
            "down": (0, 2 * unit),
            "left": (-unit, 0),
            "right": (unit, 0),
        }.get(direction, (-unit, 0))
        device.shell(f"input swipe {x} {y} {x + dx} {y + dy} 400")
        return
    device.swipe(direction=direction, scale=scale)


class LegacyBenchmarkInitializerAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: BenchmarkInitInput, runtime: RuntimeContext) -> BenchmarkInitResult:
        if input.kind is BenchmarkInitKind.TASK_PARAMETER:
            if not hasattr(self.legacy, "generate"):
                raise ComponentInputError("Environment initializer cannot accept task_parameter input")
            value = self.legacy.generate(dict(input.params))
            return BenchmarkInitResult(input.kind, True, value=value)
        if input.kind is BenchmarkInitKind.ENVIRONMENT:
            if not hasattr(self.legacy, "execute"):
                raise ComponentInputError("Task initializer cannot accept environment input")
            success = bool(self.legacy.execute(dict(input.meta), dict(input.params)))
            return BenchmarkInitResult(input.kind, success)
        raise ComponentInputError(f"Unsupported Benchmark initializer kind: {input.kind}")


class InvokeTaskInitializerAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def generate(self, params: dict[str, Any]) -> Any:
        return self.component.invoke(
            BenchmarkInitInput(BenchmarkInitKind.TASK_PARAMETER, params=params), self.runtime
        ).value


class InvokeEnvironmentInitializerAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def execute(self, meta: dict[str, Any], params: dict[str, Any]) -> bool:
        return self.component.invoke(
            BenchmarkInitInput(BenchmarkInitKind.ENVIRONMENT, params=params, meta=meta), self.runtime
        ).success


class LegacyEvaluatorAdapter:
    def __init__(self, legacy: Any) -> None:
        self.legacy = legacy

    def invoke(self, input: EvaluationInput, runtime: RuntimeContext) -> EvalResult:
        return self.legacy.evaluate(dict(input.context))


class InvokeEvaluatorAdapter:
    def __init__(self, component: Any, runtime: Optional[RuntimeContext] = None) -> None:
        self.component = component
        self.runtime = _runtime(runtime)

    def pre_evaluate(self, context: dict[str, Any]) -> None:
        hook = getattr(self.component, "pre_evaluate", None)
        if callable(hook):
            hook(EvaluationInput(context), self.runtime)

    def evaluate(self, context: dict[str, Any]) -> EvalResult:
        return self.component.invoke(EvaluationInput(context), self.runtime)


_TO_INVOKE = {
    ComponentRole.PERCEPTION: LegacyPerceptionAdapter,
    ComponentRole.PLANNER: LegacyPlannerAdapter,
    ComponentRole.REASONING: LegacyReasoningAdapter,
    ComponentRole.MEMORY: LegacyMemoryAdapter,
    ComponentRole.VERIFIER: LegacyVerifierAdapter,
    ComponentRole.GROUNDER: LegacyGrounderAdapter,
    ComponentRole.LLM: LegacyLLMAdapter,
    ComponentRole.DEVICE: LegacyDeviceAdapter,
    ComponentRole.BENCHMARK_INITIALIZER: LegacyBenchmarkInitializerAdapter,
    ComponentRole.EVALUATOR: LegacyEvaluatorAdapter,
}

_TO_LEGACY = {
    ComponentRole.PERCEPTION: InvokePerceptionAdapter,
    ComponentRole.PLANNER: InvokePlannerAdapter,
    ComponentRole.REASONING: InvokeReasoningAdapter,
    ComponentRole.MEMORY: InvokeMemoryAdapter,
    ComponentRole.VERIFIER: InvokeVerifierAdapter,
    ComponentRole.GROUNDER: InvokeGrounderAdapter,
    ComponentRole.LLM: InvokeLLMAdapter,
    ComponentRole.DEVICE: InvokeDeviceAdapter,
    ComponentRole.ACTION_EXECUTOR: InvokeActionExecutorAdapter,
    ComponentRole.EVALUATOR: InvokeEvaluatorAdapter,
}


def adapt_component(
    role: ComponentRole | str,
    instance: Any,
    target: str = "invoke",
    *,
    runtime: Optional[RuntimeContext] = None,
    initializer_kind: Optional[BenchmarkInitKind] = None,
) -> Any:
    """Adapt one already-instantiated component without discovery or execution.

    Args:
        role (ComponentRole | str): Expected public component role.
        instance (Any): Explicitly supplied component instance.
        target (str): Desired interface, either ``invoke`` or ``legacy``.
        runtime (Optional[RuntimeContext]): Optional runtime for reverse adapters.
        initializer_kind (Optional[BenchmarkInitKind]): Benchmark initializer mode.

    Raises:
        ComponentDefinitionError: A formal component violates its declared role.
        ComponentProtocolError: The object cannot satisfy the requested interface.
        ValueError: The target mode or role is invalid.

    Returns:
        Any: Original component or a compatibility adapter.
    """
    selected = ComponentRole(role)
    descriptor = get_role_descriptor(selected)
    if target == "invoke":
        # A formal definition must satisfy its declared role before the legacy
        # compatibility branch is considered; strict components never downgrade.
        from .authoring import get_component_spec, validate_component_spec

        specification = get_component_spec(instance)
        if specification is not None:
            validate_component_spec(specification, expected_role=selected)
        if callable(getattr(instance, "invoke", None)):
            return instance
        if selected is ComponentRole.ACTION_EXECUTOR:
            if callable(getattr(instance, "execute", None)):
                raise ComponentProtocolError(
                    role=selected.value,
                    instance=instance,
                    expected="invoke(input, runtime)",
                    discovered=("execute",),
                )
            return LegacyActionExecutor(instance)
        adapter = _TO_INVOKE.get(selected)
        methods = tuple(name for name in descriptor.legacy_methods if callable(getattr(instance, name, None)))
        if adapter is not None and methods:
            if selected is ComponentRole.MEMORY and not all(
                callable(getattr(instance, name, None)) for name in ("add", "get_working_context", "clear")
            ):
                methods = ()
            if methods:
                return adapter(instance)
        raise ComponentProtocolError(
            role=selected.value,
            instance=instance,
            expected="invoke(input, runtime)",
            discovered=methods,
        )
    if target == "legacy":
        methods = tuple(name for name in descriptor.legacy_methods if callable(getattr(instance, name, None)))
        if methods and selected is not ComponentRole.BENCHMARK_INITIALIZER:
            return instance
        if selected is ComponentRole.BENCHMARK_INITIALIZER:
            expected = (
                "generate"
                if initializer_kind is BenchmarkInitKind.TASK_PARAMETER
                else "execute"
                if initializer_kind is BenchmarkInitKind.ENVIRONMENT
                else ""
            )
            if expected and callable(getattr(instance, expected, None)):
                return instance
        if not callable(getattr(instance, "invoke", None)):
            raise ComponentProtocolError(
                role=selected.value,
                instance=instance,
                expected="legacy role method",
                discovered=methods,
            )
        if selected is ComponentRole.BENCHMARK_INITIALIZER:
            if initializer_kind is BenchmarkInitKind.TASK_PARAMETER:
                return InvokeTaskInitializerAdapter(instance, runtime)
            if initializer_kind is BenchmarkInitKind.ENVIRONMENT:
                return InvokeEnvironmentInitializerAdapter(instance, runtime)
            raise ComponentInputError("BenchmarkInitializer legacy target requires initializer_kind")
        adapter = _TO_LEGACY.get(selected)
        if adapter is None:
            raise ComponentProtocolError(
                role=selected.value,
                instance=instance,
                expected="legacy role adapter",
                discovered=("invoke",),
            )
        return adapter(instance, runtime)
    raise ComponentInputError("target must be 'invoke' or 'legacy'")


__all__ = [
    "RAW_RESPONSE_METADATA_KEY",
    "LegacyActionExecutor",
    "adapt_component",
]
