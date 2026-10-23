"""Small source data operations; ordinary State and Router nodes own control flow."""

from dataclasses import replace

from zhixing.components import Action, ActionResult, ActionType, ExecutionStatus, RunStatus
from zhixing.core.factory import PluginRegistry
from .environment import environment
from .types import EcoFrame


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_initialize')
class EcoInitialize:
    """Initialize a portable task cursor without connecting any service."""

    def __init__(self, fix_protocol=True):
        """Retain provenance switch. Args: fix_protocol: Syntax repair flag. Raises: ValueError: Invalid flag. Returns: None."""
        if type(fix_protocol) is not bool:
            raise ValueError('EcoAgent protocol switch must be boolean')
        self.fix_protocol = fix_protocol

    def invoke(self, input, runtime):
        """Initialize state. Args: input: TaskInput; runtime: Unused. Returns: EcoFrame: Fresh cursor."""
        del runtime
        return EcoFrame(input, fix_protocol=self.fix_protocol)


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_resume')
class EcoResume:
    """Read previous run State and clear only per-round values."""

    def invoke(self, input, runtime):
        """Resume the next logical verification round.

        Args:
            input: Initial frame and optional previous loop frame.
            runtime: Unused context.
        Raises:
            TypeError: Saved state violates the source frame contract.
        Returns:
            EcoFrame: Current expectation index and original next step.
        """
        del runtime
        frame = input['previous'] or input['initial']
        if not isinstance(frame, EcoFrame):
            raise TypeError('Invalid EcoAgent State')
        next_step = frame.steps[frame.round + 1] if frame.round + 1 < len(frame.steps) else ''
        return replace(frame, next_step=next_step, summary='', description='', action_output='',
            selected_step='', prediction_ticket='', description_ticket='', summary_ticket='', reuse_prediction=False)


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_join')
class EcoJoin:
    """Record description after successful summary/description, then join unused prediction."""

    def invoke(self, input, runtime):
        """Preserve source context-manager completion before any plan branch.

        Args:
            input: Frame after summary and description collection.
            runtime: Owned I/O service.
        Returns:
            EcoFrame: Complete description history and all submitted work joined.
        """
        frame = replace(input, descriptions=(*input.descriptions, input.description))
        environment(runtime).jobs.join(input.round)
        return frame


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_continue')
class EcoContinue:
    """Project the verifier-accepted branch into next execution or source completion."""

    def invoke(self, input, runtime):
        """Select continuation data. Args: input: Accepted frame; runtime: Unused. Returns: EcoFrame: Selected next step."""
        del runtime
        done = not input.next_step
        return replace(input, selected_step=input.next_step, reuse_prediction=bool(input.prediction_ticket),
                       success=done, finished=done)


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_merge')
class EcoMerge:
    """Merge exactly one active graph branch, without inventing decision policy."""

    def invoke(self, input, runtime):
        """Select one value. Args: input: Active frames; runtime: Unused. Raises: ValueError: Not one. Returns: EcoFrame: Same frame."""
        del runtime
        if len(input) != 1:
            raise ValueError('EcoAgent merge requires exactly one active branch')
        return input[0]


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_commit')
class EcoCommit:
    """Advance the source logical round independently of physical device interactions."""

    def invoke(self, input, runtime):
        """Advance and save progress. Args: input: Selected frame; runtime: Artifacts. Raises: Exception: Publication. Returns: EcoFrame: Next cursor."""
        frame = replace(input, round=input.round + 1)
        runtime.artifacts.write_json(runtime.artifacts.namespace / 'ecoagent-progress.json', projection(frame))
        return frame


def projection(frame):
    """Project original Agent data without runtime resources, credentials or image bytes.

    Args:
        frame: Current portable EcoFrame.
    Returns:
        dict: Source-compatible online result and explicit comparison boundaries.
    """
    return {'source_commit': 'd9b16afb4ccaf3beb59664984dab2aa258b3cccf', 'profile': 'eco_ui-tars',
        'steps': list(frame.steps), 'expectations': list(frame.expectations), 'descriptions': list(frame.descriptions),
        'logical_rounds': frame.round, 'llm_calls': frame.cloud_calls, 'total_tokens': frame.cloud_tokens,
        'source_task_success': frame.success, 'summary': frame.summary, 'benchmark_evaluated': False,
        'compatibility_fixes': ['explicit target and run-owned artifacts', 'invalid plan fail-fast',
            'finite transport attempts and portable failure replies'] +
            (['JSON fence and point-tag syntax'] if frame.fix_protocol else [])}


@PluginRegistry.register(namespace='agent.memory', name='ecoagent_finish')
class EcoFinish:
    """Publish source success or logical budget exhaustion separately from evaluation."""

    def invoke(self, input, runtime):
        """Publish a nonphysical terminal result after the ordinary bounded loop.

        Args:
            input: Completed or exhausted source cursor.
            runtime: Evidence and typed terminal services.
        Raises:
            Exception: Final evidence cannot be written.
        Returns:
            tuple: Prior physical acknowledgments plus one terminal ActionResult.
        """
        payload = projection(input)
        path = runtime.artifacts.namespace / 'ecoagent-episode.json'
        runtime.artifacts.write_json(path, payload)
        ack = ActionResult(Action(ActionType.DONE if input.success else ActionType.FAIL), ExecutionStatus.TERMINAL,
            terminal_status=RunStatus.SUCCESS if input.success else RunStatus.STEP_LIMIT,
            metadata={'ecoagent': payload, 'artifact': runtime.artifacts.reference(path)})
        runtime.state.last_action, runtime.state.last_action_result = ack.action, ack
        return (*input.actions, ack)

