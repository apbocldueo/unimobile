"""One ReflectPlan attempt per activation; generic Graph Loop owns retries."""

import re
from dataclasses import replace

from zhixing.core.factory import PluginRegistry

from .prompts import plan_system_prompt, update_plan_system_prompt
from .types import format_plan


def parse_plan(output: str) -> tuple[tuple[str, bool], ...]:
    """Parse valid lines with the original regex and skip all malformed lines.

    Args:
        output: Original model response.
    Returns:
        tuple: Original ordered statement/completion pairs.
    """
    plan = []
    for stmt in output.strip().split('\n'):
        if stmt:
            try:
                stmt, state = re.match(r'(\d+\. *.+) State: \[?(Done|Todo)\]?', stmt).groups()
                plan.append((stmt, state == 'Done'))
            except Exception:
                continue
    return tuple(plan)


@PluginRegistry.register(namespace="agent.planner", name="androidgen_reflect_plan")
class AndroidGenReflectPlan:
    """Original initial/update distinction, with no hidden retry loop or device call."""

    def __init__(self, planner_llm, enabled: bool = True, model_type: str = "text") -> None:
        """Bind the independent original planning model.

        Args:
            planner_llm: Original generate-compatible planning dependency.
            enabled: Source reflectplan switch.
            model_type: Source text/image input selection for the planner.
        Raises:
            ValueError: The model input type is unsupported.
        Returns:
            None.
        """
        if model_type not in ("text", "image"):
            raise ValueError("planner model_type must be text or image")
        self.llm, self.enabled, self.model_type = planner_llm, enabled, model_type

    def invoke(self, input, runtime):
        """Generate once or update once using all previous assistant responses.

        Args:
            input: Initial frame and optional prior attempt from run-scoped State.
            runtime: Unused context.
        Raises:
            Exception: Source model request fails.
        Returns:
            AndroidGenFrame: Ready after initial generation, or after a valid update.
        """
        del runtime
        frame, previous = input["frame"], input["previous"]
        # Nested-loop State survives outer iterations; round identity discards old attempts.
        if previous is not None and previous.round_number == frame.round_number:
            frame = previous
        if not self.enabled:
            return replace(frame, planning_done=True)
        state = frame.view.state[self.model_type]
        if frame.plan:
            actions = '\n\n'.join(message['content']['text'] for message in frame.messages if message['role'] == 'assistant')
            prompt = '# Current State: %s\n\n# User Instruction: %s\n\n# Action History: %s\n\n# User Plan: %s' % (
                state['text'], frame.task.instruction, actions, format_plan(frame.plan))
            system = update_plan_system_prompt
        else:
            prompt = '# Current State: %s\n\n# User Instruction: %s' % (state['text'], frame.task.instruction)
            system = plan_system_prompt
        if self.model_type == 'image':
            prompt = {"text": prompt, "image_url": state['image_url']}
        plan = parse_plan(self.llm.generate(prompt=prompt, system_prompt=system))
        # Empty INITIAL generation proceeds to the actor; empty UPDATE repeats
        # against the same old plan, observation and prompt in the generic Loop.
        return replace(frame, plan=plan if plan else frame.plan,
            planning_done=not frame.plan or bool(plan), planning_attempts=frame.planning_attempts + 1,
            output={**(frame.output or {}), "plan": format_plan(plan if plan else frame.plan)})
