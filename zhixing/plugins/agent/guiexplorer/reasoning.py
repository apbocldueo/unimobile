"""Original knowledge ranking, action selection and summary as separate graph nodes."""

from dataclasses import asdict, replace
from pathlib import Path

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.m3a.perception import load_pixels, save_pixels

from . import source
from .perception import marked_target
from .protocol import model_reply, rank_entries
from .types import GUIExplorerStep


@PluginRegistry.register(namespace="agent.reasoning", name="guiexplorer_rank")
class GUIExplorerRank:
    """Retain the complete original model-based pairwise knowledge ordering."""

    def __init__(self, llm_client):
        """Bind an explicit source comparison model.

        Args:
            llm_client: Service with an async ranking_session boundary.
        Returns:
            None.
        """
        self.llm = llm_client

    def invoke(self, input, runtime):
        """Run original recursive comparisons without introducing an Agent task loop.

        Args:
            input: Common frame and current retrieved image knowledge.
            runtime: Unused context; this operation has no device access.
        Raises:
            Exception: Source sorting or the comparison service fails.
        Returns:
            GUIExplorerKnowledge: All entries in source ranking order and usage.
        """
        del runtime
        bundle = input["knowledge"]
        entries = [entry.source_value() for entry in bundle.entries]
        usage = {"prompt_tokens": 0, "completion_tokens": 0}
        ranked = rank_entries(self.llm, input["frame"].task.instruction, entries, usage)
        by_index = {entry.index: entry for entry in bundle.entries}
        return replace(bundle, entries=tuple(by_index[item["index"]] for item in ranked),
            prompt_tokens=usage["prompt_tokens"], completion_tokens=usage["completion_tokens"])


@PluginRegistry.register(namespace="agent.reasoning", name="guiexplorer_select")
class GUIExplorerSelect:
    """One official action decision; feedback retries occur only in the graph loop."""

    def __init__(self, llm_client):
        """Bind a source-aware multimodal model dependency.

        Args:
            llm_client: Service returning GUIExplorerReply.
        Returns:
            None.
        """
        self.llm = llm_client

    def invoke(self, input, runtime):
        """Build the original knowledge/history prompt, parse once and choose a route.

        Args:
            input: Common frame, ranked knowledge/view and complete shared Memory context.
            runtime: Unused context; no device operations are permitted here.
        Raises:
            RuntimeError: Original response is absent or complete history was truncated.
            Exception: Original target annotation/indexing fails outside its action guard.
        Returns:
            M3AFrame: Source-specific terminal, feedback-only or executable decision.
        """
        del runtime
        frame, bundle = input["frame"], input["knowledge"]
        view = bundle.view
        fragments = [item for item in input["memory"] if item.metadata.get("source") == "guiexplorer.summary"]
        if len(fragments) != len(frame.history):
            raise RuntimeError("GUI-explorer Memory must retain the complete episode history")
        knowledge = ""
        for entry in bundle.entries:
            hints = entry.source_value()["hints"]
            knowledge += f'\nUI element {entry.index}: {hints["hint_1"] if len(hints) == 1 else hints}'
        if knowledge:
            knowledge = f"\nHere are some tips for you:{knowledge}\n"
        prompt = source._action_selection_prompt(frame.task.instruction,
            [f"Step {index + 1}- {fragment.content}" for index, fragment in enumerate(fragments)],
            view.ui_description, knowledge_prompt=knowledge)
        reply = model_reply(self.llm, prompt, (view.raw, view.som))
        if not reply.has_response:
            raise RuntimeError("Error calling LLM in action selection phase.")
        data = view.observation.metadata["guiexplorer"]
        step = GUIExplorerStep(goal=frame.task.instruction, raw_screenshot=view.raw,
            before_screenshot=view.raw, before_screenshot_with_som=view.som,
            before_ui_elements=tuple(data["ui_elements"]), top_app_package_name=data["top_app_package_name"],
            logical_screen_size=tuple(data["logical_screen_size"]), action_prompt=prompt,
            action_output=reply.text, action_raw_response=True,
            ranker_usage={"prompt_tokens": bundle.prompt_tokens, "completion_tokens": bundle.completion_tokens})
        frame = replace(frame, before=view, step=step, append_history=True, route="feedback", done=False)
        reason, action_text = source.parse_reason_action_output(reply.text)
        if not reason or not action_text:
            return replace(frame, step=replace(step,
                summary="Output for action selection is not in the correct format, so no action is performed."))
        step = replace(step, action_reason=reason)
        try:
            action = source.JSONAction(**source.extract_json(action_text))
            values = asdict(action)
            step = replace(step, action_output_json=values, converted_action=values)
        except Exception:
            return replace(frame, step=replace(step,
                summary="Can not parse the output to a valid action. Please make sure to pick the action from the list with required parameters (if any) in the correct JSON format!"))
        index = action.index
        if action.action_type in ("click", "long_press", "input_text", "scroll") and index is not None:
            if index >= len(step.before_ui_elements):
                return replace(frame, step=replace(step, converted_action="error_retry",
                    summary="The parameter index is out of range. Remember the index must be in the UI element list!"))
            step = replace(step, raw_screenshot=marked_target(view, index), target_element=dict(step.before_ui_elements[index]))
        if action.action_type == "status":
            summary = "Agent thinks the mission is infeasible and stopped." if action.goal_status == "infeasible" else "Agent thinks the request has been completed."
            return replace(frame, step=replace(step, summary=summary), action_text=action_text,
                done=True, goal_status=action.goal_status, route="terminal")
        # The original prints answer.text before entering its execution guard.
        if action.action_type == "answer" and action.text is None:
            raise TypeError("original answer requires text before execution")
        return replace(frame, step=step, action_text=action_text, route="execute")


@PluginRegistry.register(namespace="agent.reasoning", name="guiexplorer_summary")
class GUIExplorerSummary:
    """One official execution-after summary, without an added success verifier."""

    def __init__(self, llm_client):
        """Bind the source-aware action/summary model service.

        Args:
            llm_client: Service returning source text and response-presence facts.
        Returns:
            None.
        """
        self.llm = llm_client

    def invoke(self, input, runtime):
        """Preserve source image-copy quirks and summary response error history.

        Args:
            input: Executed common frame and source post-action view.
            runtime: Unused context; device reads already occurred upstream.
        Raises:
            Exception: Source drawing, persistence or model service fails.
        Returns:
            M3AFrame: Exact source summary or source missing-response feedback.
        """
        del runtime
        frame, after = input["frame"], input["view"]
        before, step = frame.before, frame.step
        pixels = load_pixels(before.som)
        source.add_screenshot_label(pixels, "before")
        labelled = save_pixels(pixels, Path(before.som).with_name(Path(before.som).stem + "-before.png"))
        step = replace(step, before_screenshot_with_som=labelled,
            after_screenshot=after.raw, after_screenshot_with_som=after.som)
        prompt = source._summarize_prompt(frame.action_text, step.action_reason, frame.task.instruction,
            before.ui_description, after.ui_description)
        # Source labels its evidence copy, but sends the original unlabelled before SoM.
        reply = model_reply(self.llm, prompt, (before.som, after.som))
        if not reply.has_response:
            return replace(frame, step=replace(step,
                summary="Some error occurred calling LLM during summarization phase."))
        return replace(frame, step=replace(step, summary_prompt=prompt, summary_raw_response=True,
            summary=f"Action selected: {frame.action_text}. {reply.text}"))
