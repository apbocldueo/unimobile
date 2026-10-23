"""Explicit source observation/action/wait operations scheduled by AgentGraph."""

from dataclasses import replace

from zhixing.components import Action, ActionResult, ActionType, DeviceEffectKind, ExecutionStatus
from zhixing.core.factory import PluginRegistry

from .environment import environment
from .perception import source_ui
from .source import JSONAction


@PluginRegistry.register(namespace="agent.perception", name="guiexplorer_observe")
class GUIExplorerObserve:
    """Keep all source device reads outside model and pure perception components."""

    def __init__(self, after: bool = False):
        """Choose before or after source observation ordering.

        Args:
            after: Capture the source fresh post-action UI state.
        Returns:
            None.
        """
        self.after = after

    def invoke(self, input, runtime):
        """Acquire one source observation at its explicit graph activation.

        Args:
            input: Scheduling-only upstream frame.
            runtime: Explicit device and artifact services.
        Raises:
            Exception: Original observation fails.
        Returns:
            DeviceObservation: Source UI, pixels and geometry.
        """
        del input
        return environment(runtime).observe(runtime, after=self.after)


@PluginRegistry.register(namespace="agent.perception", name="guiexplorer_wait_round")
class GUIExplorerWaitRound:
    """Preserve the otherwise easy-to-miss official run-loop stability read."""

    def invoke(self, input, runtime):
        """Wait after nonterminal rounds, including feedback and execution errors.

        Args:
            input: Committed common episode frame.
            runtime: Explicit source device boundary.
        Raises:
            Exception: Original stable-state read fails.
        Returns:
            M3AFrame: Unmodified frame, including the final memory-only flush.
        """
        if not input.done and not input.finished:
            environment(runtime).wait_round()
        return input


@PluginRegistry.register(namespace="agent.action_executor", name="guiexplorer_execute")
class GUIExplorerExecute:
    """Execute the complete source dispatcher and expose its recoverable error route."""

    def invoke(self, input, runtime):
        """Acknowledge the source action without turning execution failure into history.

        Args:
            input: Executable common frame with source-specific step/view.
            runtime: Explicit device, state and artifact services.
        Raises:
            Exception: Artifact publication fails outside the source device-error guard.
        Returns:
            dict: Updated frame and typed device acknowledgment.
        """
        action = JSONAction(**input.step.action_output_json)
        names = {"click": ActionType.TAP, "double_tap": ActionType.TAP, "long_press": ActionType.LONG_PRESS,
            "input_text": ActionType.TEXT, "scroll": ActionType.SWIPE, "swipe": ActionType.SWIPE,
            "navigate_home": ActionType.KEY, "navigate_back": ActionType.KEY,
            "keyboard_enter": ActionType.KEY, "open_app": ActionType.START_APP}
        record = Action(names.get(action.action_type, ActionType.WAIT),
            params=dict(input.step.action_output_json), thought=input.step.action_reason,
            metadata={"guiexplorer.action_type": action.action_type})
        env = environment(runtime)
        try:
            data = input.before.observation.metadata["guiexplorer"]
            coordinates = env.execute(action, source_ui(data["ui_elements"]), data["logical_screen_size"])
        except Exception:
            frame = replace(input, append_history=False, route="execution_error", step=replace(input.step,
                summary="Can not execute the action, make sure to select the action with the required parameters (if any) in the correct JSON format!",
                converted_action="error_retry"))
            ack = ActionResult(record, ExecutionStatus.FAILURE, error="GUI-explorer original action execution failed")
        else:
            effect = DeviceEffectKind.NONE
            if env.effects:
                effect = DeviceEffectKind.WAIT if action.action_type == "wait" else DeviceEffectKind.APP_LAUNCH if action.action_type == "open_app" else DeviceEffectKind.SHELL if action.action_type == "answer" else DeviceEffectKind.UI_INPUT
            ack = ActionResult(record, ExecutionStatus.SUCCESS, effect_performed=bool(env.effects), effect_kind=effect)
            frame = replace(input, route="executed", step=replace(input.step,
                actual_action_coordinates=tuple(coordinates) if coordinates is not None else None))
        reference = runtime.artifacts.write_action(runtime.step, ack.to_safe_dict())
        ack = replace(ack, metadata={"artifact": reference})
        frame = replace(frame, actions=(*frame.actions, ack))
        runtime.state.last_action, runtime.state.last_action_result = record, ack
        return {"result": frame, "ack": ack}
