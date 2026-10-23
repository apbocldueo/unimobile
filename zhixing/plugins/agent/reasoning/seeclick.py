"""Single-prediction SeeClick policy; all device effects remain in the graph."""

from __future__ import annotations

from zhixing.components import Action, ActionType, BaseReasoning, ReasoningInput, RuntimeContext
from zhixing.core.agent.protocol import FragmentType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
from zhixing.plugins.agent.parsers.seeclick_action_parser import SeeClickActionParser
from zhixing.resources import read_prompt


@PluginRegistry.register(namespace="agent.reasoning", name="seeclick_reasoning")
class SeeClickReasoning(BaseReasoning):
    """Use the original mobile prompt and external four-action history."""

    def __init__(self, llm_client) -> None:
        """Store a model dependency without loading resources or checkpoints.

        Args:
            llm_client: Existing generate(prompt, images) model interface.
        Raises:
            TypeError: The dependency does not expose generate.
        Returns:
            None.
        """
        if not callable(getattr(llm_client, "generate", None)):
            raise TypeError("SeeClick requires a model generate interface")
        self.llm = llm_client
        self.parser = SeeClickActionParser()

    def invoke(self, input: ReasoningInput, runtime: RuntimeContext) -> Action:
        """Predict once from the current raw screenshot and previous actions.

        Args:
            input: Task, screenshot Perception and exact history fragments.
            runtime: Shared context; never used to access a device or model handle.
        Raises:
            ValueError: Perception or history is incompatible with this policy.
        Returns:
            Action: Parsed decision or a bounded explicit inference/parse FAIL.
        """
        del runtime
        perception = input.perception
        if perception.mode != "screenshot" or not perception.original_screenshot_path:
            raise ValueError("SeeClick requires raw screenshot Perception")
        history = []
        for fragment in input.memory_context:
            if (fragment.type is not FragmentType.TEXT or fragment.metadata.get("source") != "seeclick.action"
                    or not isinstance(fragment.content, str)):
                raise ValueError("SeeClick requires original action history")
            history.append(fragment.content)
        previous = "".join(f"Step{index}: {raw}. " for index, raw in enumerate(history[-4:]))
        # Strip only the resource's final newline; do not add perception notes,
        # action definitions, plan, role labels, or a chat conversation history.
        template = read_prompt("reasoning_seeclick_aitw.md").removesuffix("\n")
        prompt = template.format(instruction=input.task.instruction, previous_actions=previous)
        try:
            response = self.llm.generate(prompt, images=[perception.original_screenshot_path])
        except Exception:
            return Action(ActionType.FAIL, thought="SeeClick model call failed",
                          metadata={"seeclick.error": "model_failed"})
        try:
            return self.parser.parse(response, dict(perception.metadata))
        except ActionParseError:
            return Action(ActionType.FAIL, thought="Invalid SeeClick decision",
                          metadata={"seeclick.error": "invalid_response"})
