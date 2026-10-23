"""The two source M3A model operations, independently scheduled by AgentGraph."""

from dataclasses import replace

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.llm.m3a_llm import model_reply

from . import source
from .perception import label_before, mark_target
from .types import M3AFrame, M3AStep


@PluginRegistry.register(namespace="agent.reasoning", name="m3a_select")
class M3ASelect:
    """One original action-selection call; parse errors never resample in this node."""

    def __init__(self, llm_client, additional_guidelines: list[str] | None = None) -> None:
        """Bind the shared model dependency and optional source task guidelines.

        Args:
            llm_client: Original-compatible multimodal model dependency.
            additional_guidelines: Source task-specific guideline strings.
        Returns:
            None.
        """
        self.llm = llm_client
        self.guidelines = additional_guidelines

    def invoke(self, input, runtime) -> M3AFrame:
        """Build the exact source prompt, call once, parse and choose a graph route.

        Args:
            input: Frame, before view and reusable Memory context ports.
            runtime: Unused context; this operation has no device access.
        Raises:
            RuntimeError: Action model has no valid response or history was truncated.
            Exception: Source parsing/annotation raises outside its conversion guard.
        Returns:
            M3AFrame: Terminal, feedback-only or executable source decision.
        """
        del runtime
        frame, view = input["frame"], input["view"]
        fragments = [item for item in input["memory"] if item.metadata.get("source") == "m3a.summary"]
        if len(fragments) != len(frame.history):
            raise RuntimeError("M3A Memory must retain the complete episode history")
        prompt = source._action_selection_prompt(frame.task.instruction,
            [f"Step {index + 1}- {fragment.content}" for index, fragment in enumerate(fragments)],
            view.ui_description, self.guidelines)
        reply = model_reply(self.llm, prompt, (view.raw, view.som))
        output = reply.text
        if reply.is_safe == False:  # Source explicitly treats None differently from False.
            output = (f"Reason: {source.TRIGGER_SAFETY_CLASSIFIER}\n"
                      'Action: {"action_type": "status", "goal_status": "infeasible"}')
        if not reply.has_response:
            raise RuntimeError("Error calling LLM in action selection phase.")
        step = M3AStep(raw_screenshot=view.raw, before_screenshot_with_som=view.som,
            before_ui_elements=tuple(view.observation.metadata["m3a"]["ui_elements"]),
            action_prompt=prompt, action_output=output, action_raw_response=True)
        frame = replace(frame, before=view, step=step, append_history=True, route="feedback", done=False)
        reason, action_text = source.parse_reason_action_output(output)
        if not reason or not action_text:
            return replace(frame, step=replace(step, summary="Output for action selection is not in the correct format, so no action is performed."))
        step = replace(step, action_reason=reason)
        try:
            action = source.JSONAction(**source.extract_action_json(action_text))
            step = replace(step, action_output_json=action.as_dict())
        except Exception:
            return replace(frame, step=replace(step, summary="Can not parse the output to a valid action. Please make sure to pick the action from the list with required parameters (if any) in the correct JSON format!"))
        index = action.index
        if action.action_type in ("click", "long_press", "input_text", "scroll") and index is not None:
            if index >= len(step.before_ui_elements):
                return replace(frame, step=replace(step, summary="The parameter index is out of range. Remember the index must be in the UI element list!"))
            step = replace(step, raw_screenshot=mark_target(view, index))
        if action.action_type == "status":
            return replace(frame, step=replace(step, summary="Agent thinks the request has been completed."),
                           action_text=action_text, done=True, goal_status=action.goal_status, route="terminal")
        return replace(frame, step=step, action_text=action_text, route="execute")


@PluginRegistry.register(namespace="agent.reasoning", name="m3a_summary")
class M3ASummary:
    """One source after-action summary call; no separate verifier or recovery policy."""

    def __init__(self, llm_client) -> None:
        """Bind the original-compatible model dependency.

        Args:
            llm_client: Dependency used for exactly one summary invocation.
        Returns:
            None.
        """
        self.llm = llm_client

    def invoke(self, input, runtime) -> M3AFrame:
        """Compare original before/after images and create the next history entry.

        Args:
            input: Executed frame and encoded after view.
            runtime: Unused context; no device effects or retry decisions occur here.
        Raises:
            Exception: Original image handling or model invocation itself raises.
        Returns:
            M3AFrame: Source summary or the source missing-response feedback.
        """
        del runtime
        frame, after = input["frame"], input["view"]
        step, before = frame.step, frame.before
        step = replace(step, before_screenshot_with_som=label_before(before),
                       after_screenshot_with_som=after.som)
        prompt = source._summarize_prompt(frame.action_text, step.action_reason,
            frame.task.instruction, before.ui_description, after.ui_description)
        # The original labels a saved copy, but sends the unlabelled before SoM.
        reply = model_reply(self.llm, prompt, (before.som, after.som))
        summary = "Summary triggered LLM safety classifier." if reply.is_safe == False else reply.text
        if not reply.has_response:
            return replace(frame, step=replace(step,
                summary="Some error occurred calling LLM during summarization phase: %s" % summary))
        return replace(frame, step=replace(step, summary_prompt=prompt, summary_raw_response=True,
            summary=f"Action selected: {frame.action_text}. {summary}"))
