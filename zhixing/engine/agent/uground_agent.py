from __future__ import annotations

import os
from typing import Any, Dict

from zhixing.core.agent.protocol import Action, ActionType, FragmentType, MemoryFragment
from zhixing.core.factory import PluginRegistry
from zhixing.engine.agent.modular_agent import ModularAgent
from zhixing.utils.utils import get_plugin_logger


@PluginRegistry.register(namespace="agent.type", name="uground_agent")
class UGroundAgent(ModularAgent):
    """SeeAct-V / UGround two-stage mobile-agent strategy.

    Flow:
        1. At the start of a step, summarize the previous action with before/after screenshots.
        2. Perceive the current screenshot.
        3. Planner/reasoning emits `Reason:` and a JSON action with a target element description.
        4. UGround resolves the element description to x/y.
        5. Return the executable action to the runner.
    """

    _pipeline_phase = "📍 UGround Agent"

    def __init__(self, config: Dict[str, Any], device: Any, context: Dict[str, Any] = None):
        super().__init__(config=config, device=device, context=context)
        namespace = getattr(self.__class__, "__plugin_namespace__", "agent.type")
        name = getattr(self.__class__, "__plugin_name__", self.__class__.__name__)
        self.logger = get_plugin_logger(phase=self._pipeline_phase, namespace=namespace, plugin_name=name)
        self.grounder = self.components.get("grounder")
        strategy_config = config.get("strategy", {})
        self.summarize_steps = bool(strategy_config.get("summarize_steps", True))
        self.summary_prompt_file = strategy_config.get("summary_prompt_file", "summary_seeact_uground.md")
        self.hide_automation_ui_on_reset = bool(strategy_config.get("hide_automation_ui_on_reset", True))
        self._last_action_response = ""
        self._last_action_summary_pending = False

    def reset(self, runner_input: Dict[str, Any]) -> None:
        super().reset(runner_input)
        self._last_action_response = ""
        self._last_action_summary_pending = False
        if self.hide_automation_ui_on_reset and hasattr(self.device, "shell"):
            try:
                self.device.shell("settings put system pointer_location 0")
            except Exception as e:
                self.logger.debug("hide automation UI failed: %s", e)

    def step(self, screenshot_path: str, width: int, height: int, xml_path: str) -> Action:
        self._summarize_previous_step_if_needed(screenshot_path)

        try:
            perception_result = self._perceive_current_screen(screenshot_path, width, height, xml_path)
        except Exception as e:
            return Action(type=ActionType.FAIL, thought=f"All perception strategies crashed: {e}")

        try:
            action, response = self._think_with_reasoning(perception_result)
        except Exception as e:
            self.logger.error("UGround planner reasoning failed: %s", e, exc_info=True)
            return Action(type=ActionType.FAIL, thought=f"Planner Error: {e}")

        try:
            action = self._ground_action_if_needed(action, screenshot_path, width, height)
        except Exception as e:
            self.logger.error("UGround grounding failed: %s", e, exc_info=True)
            feedback = (
                "Can not ground the described target element. "
                "Describe a visible target differently in the next action."
            )
            if self.memory:
                self.memory.add(MemoryFragment(
                    role="system",
                    type=FragmentType.ERROR,
                    content=f"{feedback} Reason: {e}",
                    metadata={"source": "uground_grounder"},
                ))
            return Action(type=ActionType.WAIT, params={"seconds": 1.0}, thought=feedback, metadata={"raw_response": response})

        self._commit_action(action, response, "seeact_planner", screenshot_path)
        self._last_action_response = response
        self._last_action_summary_pending = self._is_verifiable_action(action)

        if self.verbose:
            self.logger.info("UGroundAgent decision: %s %s", action.type.value, action.params)

        return action

    def _ground_action_if_needed(self, action: Action, screenshot_path: str, width: int, height: int) -> Action:
        metadata = action.metadata or {}
        if not metadata.get("needs_grounding"):
            return action
        if not self.grounder:
            raise RuntimeError("Action needs grounding, but no grounder component is configured.")

        description = metadata.get("grounding_description", "")
        x, y = self.grounder.ground(screenshot_path, description, width, height)
        action.params["x"] = x
        action.params["y"] = y
        action.metadata = {**metadata, "grounded_x": x, "grounded_y": y}
        return action

    def _summarize_previous_step_if_needed(self, current_screenshot_path: str) -> None:
        if not (
            self.summarize_steps
            and self._last_action_summary_pending
            and self.state.last_screenshot_path
            and self.state.last_action
            and self.reasoning
            and getattr(self.reasoning, "llm", None)
        ):
            return

        try:
            prompt = self._load_summary_prompt(self.summary_prompt_file)
            prompt = (
                prompt.replace("{task}", self.current_task)
                .replace("{action}", self._format_action_for_summary(self.state.last_action))
                .replace("{reason}", self.state.last_action.thought or "")
            )
            summary = self.reasoning.llm.generate(
                prompt,
                images=[self.state.last_screenshot_path, current_screenshot_path],
            )
            summary = (summary or "").strip()
            if not summary:
                return
            if self.memory:
                self.memory.add(MemoryFragment(
                    role="system",
                    type=FragmentType.TEXT,
                    content=f"Step summary: Action selected: {self._format_action_for_summary(self.state.last_action)}. {summary}",
                    metadata={"source": "seeact_step_summary"},
                ))
            self.logger.info("UGround step summary: %s", summary[:300])
        except Exception as e:
            self.logger.warning("UGround step summarization failed: %s", e)
        finally:
            self._last_action_summary_pending = False

    @staticmethod
    def _format_action_for_summary(action: Action) -> str:
        raw = (action.metadata or {}).get("seeact_action")
        if raw:
            return str(raw)
        return f"{action.type.value} {action.params}"

    @staticmethod
    def _load_summary_prompt(filename: str) -> str:
        if os.path.exists(filename):
            path = filename
        else:
            path = os.path.join(os.getcwd(), "zhixing", "prompts", filename)
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
