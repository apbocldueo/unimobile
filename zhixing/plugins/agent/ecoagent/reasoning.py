"""Only model action inference lives here; graph routers select plan branches."""

from dataclasses import replace
from functools import partial
import re

from zhixing.core.factory import PluginRegistry
from .environment import environment
from .io_jobs import account
from .prompts import ACTION_PROMPT_UITARS
from .protocol import needs_model


def direct_step(step):
    """Match actual _execute_action shortcuts, which are narrower than prediction prefixes.

    Args:
        step: Source instruction text.
    Returns:
        bool: True only if no action-model call occurs during real execution.
    """
    return bool(step.startswith('DELETE TEXT') or re.match(r'INPUT \[(.*)\]', step)
                or step in ('PRESS_BACK', 'PRESS_HOME'))


@PluginRegistry.register(namespace='agent.reasoning', name='ecoagent_predict')
class EcoPredict:
    """Submit optional next-step inference without performing any device effect."""

    def __init__(self, executor_llm):
        """Bind executor. Args: executor_llm: Explicit action model. Returns: None."""
        self.llm = executor_llm

    def invoke(self, input, runtime):
        """Prefetch only for the original needs_ui_tars condition.

        Args:
            input: Frame containing the next high-level step.
            runtime: Run-owned jobs service.
        Raises:
            Exception: Submission or ownership validation fails.
        Returns:
            EcoFrame: Optional portable prediction ticket.
        """
        if not input.next_step or not needs_model(input.next_step):
            return input
        ticket = environment(runtime).jobs.submit(runtime.run_id, input.round, 'action',
            partial(self.llm.complete, 'action', ACTION_PROMPT_UITARS.format(goal=input.next_step), (input.after,)))
        return replace(input, prediction_ticket=ticket)


@PluginRegistry.register(namespace='agent.reasoning', name='ecoagent_action')
class EcoAction:
    """Infer the selected action once, or consume exactly the selected old prediction."""

    def __init__(self, executor_llm):
        """Bind executor. Args: executor_llm: Explicit action model. Returns: None."""
        self.llm = executor_llm

    def invoke(self, input, runtime):
        """Use cached inference only when the graph selected continuation of the old plan.

        Args:
            input: Selected original/new high-level step and explicit reuse flag.
            runtime: Current run I/O service.
        Raises:
            Exception: A consumed prediction or synchronous request fails.
        Returns:
            EcoFrame: Raw action text for Executor, or a direct-action shortcut.
        """
        if input.reuse_prediction:
            value = environment(runtime).jobs.collect(runtime.run_id, input.round, input.prediction_ticket)
        elif direct_step(input.selected_step):
            return replace(input, action_output='')
        else:
            value = account(self.llm.complete('action', ACTION_PROMPT_UITARS.format(goal=input.selected_step), (input.after,)))
        return replace(input, action_output=value.text)
