"""Source setup, observation and Python actions through the explicit device bridge."""

from dataclasses import replace

from zhixing.components import Action, ActionResult, ActionType, DeviceEffectKind, ExecutionStatus
from zhixing.core.factory import PluginRegistry

from .environment import environment
from .types import AndroidGenSeed


@PluginRegistry.register(namespace="agent.action_executor", name="androidgen_setup")
class AndroidGenSetup:
    """Perform original environment initialization once per graph run."""

    def invoke(self, input, runtime):
        """Prepare the explicit environment and retain only its initial App data.

        Args:
            input: TaskInput for the episode.
            runtime: Explicit AndroidGen environment services.
        Raises:
            Exception: Original initialization fails.
        Returns:
            AndroidGenSeed: Task and original init_state.
        """
        return AndroidGenSeed(input, environment(runtime).setup())


@PluginRegistry.register(namespace="agent.perception", name="androidgen_observe")
class AndroidGenObserve:
    """Read a stable original observation once per decision round."""

    def invoke(self, input, runtime):
        """Read pixels and original UI only when activated by the continue branch.

        Args:
            input: Scheduling dependency; not used as a device object.
            runtime: Explicit environment and artifact services.
        Raises:
            Exception: Source observation fails.
        Returns:
            DeviceObservation: Full source UI and geometry.
        """
        del input
        return environment(runtime).observe(runtime)


@PluginRegistry.register(namespace="agent.action_executor", name="androidgen_execute")
class AndroidGenExecute:
    """Keep original validations inside execution, including effects before failures."""

    def invoke(self, input, runtime):
        """Execute one whole original code block and acknowledge observed effects.

        Args:
            input: Source frame with extracted Python code.
            runtime: Explicit source execution and evidence services.
        Raises:
            Exception: An exception escapes source guards or artifact writing fails.
        Returns:
            dict: Updated frame and one code-block acknowledgment. Multiple external
                calls are retained in metadata; this is not a primitive-call counter.
        """
        boundary = environment(runtime)
        result = boundary.interact(input.code, runtime)
        operation = result.get('operation') if result is not None else None
        performed = any(action['action_type'] != 'answer' for action in boundary.completed) or boundary.shell_completed > 0
        source_names = {'Click': ActionType.TAP, 'Long_press': ActionType.LONG_PRESS,
            'Input_text': ActionType.TEXT, 'Scroll': ActionType.SWIPE, 'Swipe': ActionType.SWIPE,
            'Navigate Home': ActionType.KEY, 'Navigate Back': ActionType.KEY, 'Press Enter': ActionType.KEY}
        kind = ActionType.START_APP if operation == 'open_app' else source_names.get(
            result.get('action') if result is not None else None, ActionType.WAIT)
        action = Action(kind, params={"code": input.code}, metadata={"androidgen.operation": operation})
        effect = DeviceEffectKind.NONE
        if boundary.shell_completed:
            effect = DeviceEffectKind.SHELL
        elif performed:
            effect = DeviceEffectKind.WAIT if all(item['action_type'] == 'wait' for item in boundary.completed) else (
                DeviceEffectKind.APP_LAUNCH if all(item['action_type'] == 'open_app' for item in boundary.completed) else DeviceEffectKind.UI_INPUT)
        ack = ActionResult(action, ExecutionStatus.FAILURE if operation == 'fail' else ExecutionStatus.SUCCESS,
            error=result['kwargs']['message'] if operation == 'fail' else None,
            effect_performed=performed, effect_kind=effect,
            metadata={"androidgen": {"result": result, "attempted_actions": tuple(boundary.attempts),
                "completed_actions": tuple(boundary.completed), "shell_attempts": boundary.shell_attempts,
                "shell_completed": boundary.shell_completed,
                "failed_call_effect_unknown": len(boundary.attempts) > len(boundary.completed)}})
        reference = runtime.artifacts.write_action(runtime.step, ack.to_safe_dict())
        ack = replace(ack, metadata={**ack.metadata, "artifact": reference})
        runtime.state.last_action, runtime.state.last_action_result = action, ack
        return {"result": replace(input, previous_result=result, actions=(*input.actions, ack)), "ack": ack}
