"""Explicit M3A environment operations, with source exception boundaries."""

from dataclasses import replace

from zhixing.components import Action, ActionResult, ActionType, DeviceEffectKind, ExecutionStatus
from zhixing.core.factory import PluginRegistry

from .environment import environment
from .source import JSONAction


@PluginRegistry.register(namespace="agent.perception", name="m3a_termination")
class M3ATermination:
    """Optional original environment hook, distinct from Agent/Benchmark success."""

    def invoke(self, input, runtime):
        """Evaluate the hook once per real round, never on the final history flush.

        Args:
            input: Committed round or finished flush frame.
            runtime: Explicit original environment boundary.
        Raises:
            Exception: The source environment hook fails.
        Returns:
            M3AFrame: Source environment termination fact without a goal-status rewrite.
        """
        return input if input.finished else replace(input, environment_done=environment(runtime).should_terminate())


@PluginRegistry.register(namespace="agent.action_executor", name="m3a_setup")
class M3ASetup:
    """Run the original episode reset once, outside the decision loop."""

    def __init__(self, start_on_home_screen: bool = False, skip_reset: bool = False) -> None:
        """Configure the original optional Home navigation.

        Args:
            start_on_home_screen: Pass through to the official reset.
            skip_reset: Preserve the source zero-round return without resetting.
        Returns:
            None.
        """
        self.go_home = start_on_home_screen
        self.skip_reset = skip_reset

    def invoke(self, input, runtime):
        """Reset through the explicit device boundary and pass through the task.

        Args:
            input: TaskInput for this episode.
            runtime: Run context containing M3AEnvironment.
        Raises:
            Exception: Original environment setup fails.
        Returns:
            TaskInput: Unmodified task.
        """
        if not self.skip_reset:
            environment(runtime).reset(self.go_home)
        return input


@PluginRegistry.register(namespace="agent.perception", name="m3a_observe")
class M3AObserve:
    """Device-read service; encoding is delegated to the separate Perception node."""

    def __init__(self, pause: float | None = 1.0) -> None:
        """Configure a source observation pause without connecting to a device.

        Args:
            pause: Seconds before capture, or None for source stable-state polling.
        Raises:
            ValueError: A finite nonnegative pause of at most 60 seconds is required.
        Returns:
            None.
        """
        import math

        if pause is not None and (not isinstance(pause, (float, int)) or
                not math.isfinite(pause) or not 0 <= pause <= 60):
            raise ValueError("invalid M3A observation pause")
        self.pause = pause

    def invoke(self, input, runtime):
        """Acquire one original observation only when the graph activates this node.

        Args:
            input: Upstream frame used as the scheduling dependency.
            runtime: Explicit device and artifact services.
        Raises:
            Exception: Original observation or artifact capture fails.
        Returns:
            DeviceObservation: Original UI and pixels, without an XML fallback.
        """
        del input
        return environment(runtime).observe(runtime, self.pause)


@PluginRegistry.register(namespace="agent.action_executor", name="m3a_execute")
class M3AExecute:
    """Delegate complete original actions, never a simplified local action mapping."""

    def invoke(self, input, runtime):
        """Execute once and expose the original recoverable execution-error branch.

        Args:
            input: Executable M3AFrame, including the source JSONAction fields.
            runtime: Explicit AndroidWorld execution and artifact services.
        Raises:
            Exception: Artifact publication fails after execution.
        Returns:
            dict: Updated frame plus direct typed acknowledgment for framework evidence.
        """
        action = JSONAction(**input.step.action_output_json)
        names = {"click": ActionType.TAP, "double_tap": ActionType.TAP,
                 "long_press": ActionType.LONG_PRESS, "input_text": ActionType.TEXT,
                 "scroll": ActionType.SWIPE, "swipe": ActionType.SWIPE,
                 "navigate_home": ActionType.KEY, "navigate_back": ActionType.KEY,
                 "keyboard_enter": ActionType.KEY, "open_app": ActionType.START_APP}
        record = Action(names.get(action.action_type, ActionType.WAIT),
            params=action.as_dict(), thought=input.step.action_reason,
            metadata={"m3a.action_type": action.action_type, "m3a.source_action": action.as_dict()})
        try:
            environment(runtime).execute(action)
        except Exception:
            # Official M3A returns this step to the episode log, not its history.
            frame = replace(input, append_history=False, route="execution_error",
                step=replace(input.step, summary="Can not execute the action, make sure to select the action with the required parameters (if any) in the correct JSON format!"))
            ack = ActionResult(record, ExecutionStatus.FAILURE, error="M3A original action execution failed")
        else:
            performed = action.action_type in names and not (action.action_type == "input_text" and not action.text)
            effect = DeviceEffectKind.APP_LAUNCH if action.action_type == "open_app" else DeviceEffectKind.UI_INPUT
            if action.action_type == "wait":
                effect = DeviceEffectKind.WAIT
            if action.action_type in ("answer", "unknown"):
                effect = DeviceEffectKind.NONE
            ack = ActionResult(record, ExecutionStatus.SUCCESS, effect_performed=performed, effect_kind=effect)
            frame = replace(input, route="executed")
        reference = runtime.artifacts.write_action(runtime.step, ack.to_safe_dict())
        ack = replace(ack, metadata={"artifact": reference})
        frame = replace(frame, actions=(*frame.actions, ack))
        runtime.state.last_action, runtime.state.last_action_result = record, ack
        return {"result": frame, "ack": ack}
