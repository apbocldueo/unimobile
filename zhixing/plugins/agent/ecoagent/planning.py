"""Original initial and remaining-plan requests, separated from graph control flow."""

from dataclasses import replace
import json

from zhixing.core.factory import PluginRegistry
from .io_jobs import account
from .protocol import parse_plan
from .prompts import PLANNING_PROMPT, REPLANNING_PROMPT


@PluginRegistry.register(namespace='agent.planner', name='ecoagent_plan')
class EcoPlan:
    """Create or replace the source plan with explicit expectations and prefix retention."""

    def __init__(self, planner_llm, fix_protocol=True, replan=False):
        """Bind one operation. Args: planner_llm: Model; fix_protocol: Syntax repair; replan: Mode. Raises: ValueError: Invalid switches. Returns: None."""
        if type(fix_protocol) is not bool or type(replan) is not bool:
            raise ValueError('EcoAgent planning switches must be booleans')
        self.llm, self.fix_protocol, self.replan = planner_llm, fix_protocol, replan

    def invoke(self, input, runtime):
        """Request one initial plan or one cloud reflection, without a hidden loop.

        Args:
            input: Current portable EcoFrame.
            runtime: Unused context; model/device live services are never stored in State.
        Raises:
            Exception: Transport or validated plan parsing fails.
        Returns:
            EcoFrame: Selected next step, or exact final no-replan success.
        """
        del runtime
        frame = input
        if self.replan:
            prompt = REPLANNING_PROMPT.format(goal=frame.task.instruction,
                original_plan=json.dumps({'steps': list(frame.steps), 'expectations': list(frame.expectations)}),
                descriptions=list(frame.descriptions), summary=frame.summary, description=frame.description)
        else:
            prompt = PLANNING_PROMPT.format(instruction=frame.task.instruction)
        result = account(self.llm.complete('replanning' if self.replan else 'planning', prompt, (frame.after,)))
        frame = replace(frame, cloud_calls=frame.cloud_calls + 1, cloud_tokens=frame.cloud_tokens + result.total_tokens)
        if self.replan and result.text == 'No need to replan.':
            done = not frame.next_step
            return replace(frame, selected_step=frame.next_step, reuse_prediction=bool(frame.prediction_ticket),
                           finished=done, success=done)
        steps, expectations = parse_plan(result.text, fix_protocol=self.fix_protocol)
        if self.replan:
            steps, expectations = frame.steps[:frame.round + 1] + steps, frame.expectations[:frame.round + 1] + expectations
        return replace(frame, steps=steps, expectations=expectations,
            selected_step=steps[frame.round + 1] if self.replan else steps[0], reuse_prediction=False)
