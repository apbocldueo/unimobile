"""Source direct/decoded actions and waits inside an explicit device boundary."""

from dataclasses import replace
import re
import shlex

from zhixing.components import Action, ActionResult, ActionType, DeviceEffectKind, ExecutionStatus, DeviceExecutionError
from zhixing.core.factory import PluginRegistry
from .environment import environment
from .protocol import commands


def direct_commands(step):
    """Preserve direct INPUT, ten deletes and exact navigation shortcuts.

    Args:
        step: Original high-level instruction.
    Raises:
        ValueError: Caller selected a non-direct step without model output.
    Returns:
        tuple: Decoder-shaped checked commands and portable action type.
    """
    match = re.match(r'INPUT \[(.*)\]', step)
    if step.startswith('DELETE TEXT'):
        return ('adb shell input keyevent 67',) * 10, ActionType.KEY
    if match:
        return (shlex.join(['adb', 'shell', 'am', 'broadcast', '-a', 'ADB_INPUT_TEXT', '--es', 'msg', match.group(1)]),), ActionType.TEXT
    if step in ('PRESS_BACK', 'PRESS_HOME'):
        return ('adb shell input keyevent ' + ('KEYCODE_BACK' if step == 'PRESS_BACK' else 'KEYCODE_HOME'),), ActionType.KEY
    raise ValueError('EcoAgent non-direct step requires action-model output')


@PluginRegistry.register(namespace='agent.action_executor', name='ecoagent_execute')
class EcoExecute:
    """Execute one high-level step; decoder finished does not end the Agent."""

    def __init__(self, fix_protocol=True, home=False, wait_seconds=2.0):
        """Retain explicit source settings.

        Args:
            fix_protocol: Enable the separately recorded point-tag syntax repair.
            home: Startup Home operation, with no post-action source wait.
            wait_seconds: Source post-action wait, independent of device primitive waits.
        Raises:
            ValueError: Wait is outside the supported finite interval.
        Returns:
            None.
        """
        if type(fix_protocol) is not bool or type(home) is not bool or not 0 <= wait_seconds <= 60:
            raise ValueError('Invalid EcoAgent executor settings')
        self.fix_protocol, self.home, self.wait_seconds = fix_protocol, home, wait_seconds

    def invoke(self, input, runtime):
        """Apply only the selected instruction and publish a typed physical acknowledgment.

        Args:
            input: Portable selected action frame.
            runtime: Explicit target, wait and evidence services.
        Raises:
            Exception: Checked direct execution, transport, wait or evidence write fails.
        Returns:
            dict: Updated frame and physical acknowledgment for generic Kernel counting.
        """
        boundary = environment(runtime)
        step = 'PRESS_HOME' if self.home else input.selected_step
        checked = self.home or not input.action_output
        if checked:
            planned, kind = direct_commands(step)
        else:
            planned = commands(input.action_output, fix_protocol=self.fix_protocol)
            first = planned[0] if planned else ''
            kind = (ActionType.TAP if 'input tap' in first else ActionType.SWIPE if 'input swipe' in first
                    else ActionType.TEXT if 'input text' in first else ActionType.KEY)
        completed = []
        try:
            for command in planned:
                completed.append(boundary.execute_command(command, check=checked))
        except Exception:
            ack = ActionResult(Action(kind, metadata={'ecoagent_step': step}), ExecutionStatus.DEVICE_FAILURE,
                error='EcoAgent device command failed', effect_performed=any(completed),
                effect_kind=DeviceEffectKind.UI_INPUT if any(completed) else DeviceEffectKind.NONE,
                metadata={'completed_commands': len(completed), 'effect_completion': 'unknown'})
            runtime.state.last_action, runtime.state.last_action_result = ack.action, ack
            runtime.artifacts.write_action(runtime.step, ack.to_safe_dict())
            raise DeviceExecutionError('ecoagent_execute', 'EcoAgent device command failed') from None
        performed = any(completed)
        ack = ActionResult(Action(kind, metadata={'ecoagent_step': step}),
            ExecutionStatus.SUCCESS if completed and all(completed) else ExecutionStatus.FAILURE if completed else ExecutionStatus.SKIPPED,
            effect_performed=performed, effect_kind=DeviceEffectKind.UI_INPUT if performed else DeviceEffectKind.NONE,
            metadata={'source_round': input.round, 'source_step': step, 'startup_home': self.home,
                'commands': list(planned), 'command_results': completed,
                'effect_completion': 'completed' if all(completed) else 'unknown'})
        runtime.state.last_action, runtime.state.last_action_result = ack.action, ack
        runtime.artifacts.write_action(runtime.step, ack.to_safe_dict())
        if not self.home:
            boundary.sleep(self.wait_seconds)
        return {'result': replace(input, actions=(*input.actions, ack)), 'ack': ack}
