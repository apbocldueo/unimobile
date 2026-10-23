"""A single Aguvis prediction; all loops and device effects remain in the graph."""

from zhixing.components import Action, ActionType
from zhixing.core.agent.protocol import FragmentType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.aguvis_types import AguvisCommand, AguvisDecision, AguvisRequest
from zhixing.plugins.agent.parsers.aguvis_action_parser import AguvisActionParser


@PluginRegistry.register(namespace="agent.reasoning", name="aguvis_reasoning")
class AguvisReasoning:
    """Preserve raw images and exact external TEXT history for one model call."""

    def __init__(self, llm_client, mode="self-plan", low_level_instruction=None,
                 max_commands=16, gesture_duration_ms=400, long_press_ms=1000,
                 scroll_pixels_per_click=None):
        """Bind a typed model dependency and explicit parser/gesture policy.

        Args:
            llm_client: Backend exposing generate_aguvis(AguvisRequest).
            mode: Published CLI generation mode.
            low_level_instruction: Optional prefilled atomic instruction.
            max_commands: Maximum ordered commands in one decision.
            gesture_duration_ms: Adapter swipe duration.
            long_press_ms: Adapter long-press duration.
            scroll_pixels_per_click: Optional explicit wheel-unit conversion.
        Raises:
            TypeError: The dependency lacks the typed prediction method.
            ValueError: Mode, low-level text or parser settings are invalid.
        Returns:
            None.
        """
        if not callable(getattr(llm_client, "generate_aguvis", None)):
            raise TypeError("Aguvis requires generate_aguvis(request)")
        if mode not in ("self-plan", "force-plan", "grounding") or (
                low_level_instruction is not None and not isinstance(low_level_instruction, str)):
            raise ValueError("invalid Aguvis reasoning configuration")
        self.llm, self.mode, self.low_level_instruction = llm_client, mode, low_level_instruction
        self.parser = AguvisActionParser(max_commands, gesture_duration_ms, long_press_ms, scroll_pixels_per_click)

    def invoke(self, input, runtime) -> AguvisDecision:
        """Issue one prediction without role-label/history/prompt contamination.

        Args:
            input: Explicit task, raw perception and fragment context ports.
            runtime: Unused runtime context; no model/device handles are stored.
        Raises:
            ValueError: Inputs violate the declared raw-image/TEXT contract.
        Returns:
            AguvisDecision: Parsed commands or one explicit FAIL, without retries.
        """
        del runtime
        perception, history = input["perception"], input["memory"]
        if perception.mode != "screenshot" or not perception.original_screenshot_path:
            raise ValueError("Aguvis requires screenshot perception")
        if any(fragment.type is not FragmentType.TEXT or fragment.metadata.get("source") != "aguvis.low_level"
               or not isinstance(fragment.content, str) for fragment in history):
            raise ValueError("Aguvis requires exact low-level TEXT history")
        step = len(history) + 1
        request = AguvisRequest(input["task"].instruction, perception.original_screenshot_path,
            tuple(fragment.content for fragment in history), self.mode, self.low_level_instruction)
        try:
            response = self.llm.generate_aguvis(request)
        except Exception:
            error = "model_failed"
        else:
            try:
                return self.parser.parse(response, dict(perception.metadata), step=step,
                                         low_level_instruction=self.low_level_instruction)
            except Exception:
                error = "invalid_response"
        return AguvisDecision((AguvisCommand(action=Action(ActionType.FAIL,
            thought="Aguvis prediction failed", metadata={"aguvis.error": error})),), "", step)
