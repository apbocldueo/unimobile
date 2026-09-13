from __future__ import annotations

from typing import Any, Dict

from zhixing.core.factory import PluginRegistry
from zhixing.core.agent.protocol import Action, ActionType, FragmentType, MemoryFragment, VerifierInput
from zhixing.engine.agent.modular_agent import ModularAgent
from zhixing.utils.utils import get_plugin_logger


@PluginRegistry.register(namespace="agent.type", name="reflection_agent")
class ReflectionAgent(ModularAgent):
    """Agent strategy with an explicit reflect-then-act loop.

    Flow:
        1. Reflect on the previously executed physical action using the new screenshot.
        2. If reflection proposes a correction, return that correction immediately.
        3. Otherwise observe the current screen and ask the actor/reasoning component
           for the next action.

    Unlike ``modular_agent``, this strategy does not use the experience-cache
    fast path by default: reflection-style agents should normally reason from
    the latest screen plus reflection feedback instead of replaying old traces.
    """

    _pipeline_phase = "🪞 Reflection Agent"

    def __init__(self, config: Dict[str, Any], device: Any, context: Dict[str, Any] = None):
        super().__init__(config=config, device=device, context=context)
        namespace = getattr(self.__class__, "__plugin_namespace__", "agent.type")
        name = getattr(self.__class__, "__plugin_name__", self.__class__.__name__)
        self.logger = get_plugin_logger(phase=self._pipeline_phase, namespace=namespace, plugin_name=name)
        strategy_config = config.get("strategy", {})
        self.use_experience_cache = bool(strategy_config.get("use_experience_cache", False))

    def step(self, screenshot_path: str, width: int, height: int, xml_path: str) -> Action:
        """Run one MobileAgent-style reflection cycle."""
        correction = self._reflect_previous_action(screenshot_path)
        if correction is not None:
            self._commit_action(correction, correction.thought or "Reflection correction", "reflection", screenshot_path)
            return correction

        try:
            perception_result = self._perceive_current_screen(screenshot_path, width, height, xml_path)
        except Exception as e:
            return Action(type=ActionType.FAIL, thought=f"All perception strategies crashed: {e}")

        if self.use_experience_cache:
            cached_action = self._get_cached_action(screenshot_path)
            if cached_action:
                self.logger.info("ReflectionAgent experience-cache hit: %s", cached_action.type.value)
                self._commit_action(cached_action, "Loaded from cache", "memory_cache", screenshot_path)
                return cached_action

        if self.verbose:
            self.logger.info("ReflectionAgent actor reasoning...")

        try:
            action, response = self._think_with_reasoning(perception_result)
        except Exception as e:
            self.logger.error("reflection actor reasoning failed: %s", e, exc_info=True)
            return Action(type=ActionType.FAIL, thought=f"Brain Error: {e}")

        self._commit_action(action, response, "actor", screenshot_path)

        if self.verbose:
            self.logger.info("ReflectionAgent decision: %s %s", action.type.value, action.params)

        return action

    def _reflect_previous_action(self, screenshot_path: str) -> Action | None:
        """Judge the previous action and optionally produce a correction action."""
        if not (self.verifier and self.state.last_screenshot_path and self.state.last_action):
            return None

        if not self._is_verifiable_action(self.state.last_action):
            return None

        verify_input = VerifierInput(
            task=self.current_task,
            screenshot_before=self.state.last_screenshot_path,
            screenshot_after=screenshot_path,
            action=self.state.last_action,
        )
        verify_result = self.verifier.verify(verify_input)
        self._record_verifier_result(verify_result)

        if verify_result.is_success:
            if self.verbose:
                self.logger.info("✅ [Reflection] Previous action succeeded: %s", verify_result.feedback)
            progress = (verify_result.metadata or {}).get("progress")
            if progress and self.memory:
                self.memory.add(MemoryFragment(
                    role="system",
                    type=FragmentType.TEXT,
                    content=f"Completed contents: {progress}",
                    metadata={"source": "reflection_progress"},
                ))
            if self.state.current_strategy_idx != 0:
                self.logger.info("Reflection succeeded; reverting to primary perception strategy.")
                self.state.current_strategy_idx = 0
            return None

        feedback = verify_result.feedback or "Previous action did not make expected progress."
        self.logger.warning("❌ [Reflection] Previous action failed: %s", feedback)
        if self.memory:
            self.memory.add(MemoryFragment(
                role="system",
                type=FragmentType.ERROR,
                content=f"Reflection feedback: {feedback}. Do not repeat the same failed action.",
                metadata={"source": "reflection"},
            ))

        if verify_result.correction_suggestion is not None:
            correction = verify_result.correction_suggestion
            self.logger.info(
                "🔁 [Reflection] Returning correction action: %s %s",
                correction.type.value,
                correction.params,
            )
            return correction

        return None
