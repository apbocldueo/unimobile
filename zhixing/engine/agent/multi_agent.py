from __future__ import annotations

from typing import Any, Dict

from zhixing.core.factory import PluginRegistry
from zhixing.core.agent.protocol import Action, ActionType, FragmentType, MemoryFragment, PlanInput
from zhixing.engine.agent.reflection_agent import ReflectionAgent
from zhixing.utils.utils import get_plugin_logger


@PluginRegistry.register(namespace="agent.type", name="multi_agent")
class MultiAgent(ReflectionAgent):
    """Manager/operator/critic strategy for mobile-use style agents.

    Flow:
        1. Critic: verify/reflect on the previous action, optionally returning a correction.
        2. Perception: observe the current screen.
        3. Manager: update the high-level plan for the current step.
        4. Operator: emit the next executable action/tool call.

    This is intentionally not just ``ReflectionAgent`` with another name:
    the planner is used as an active manager during the loop, not only once
    during ``reset()``.
    """

    _pipeline_phase = "👥 Multi Agent"

    def __init__(self, config: Dict[str, Any], device: Any, context: Dict[str, Any] = None):
        super().__init__(config=config, device=device, context=context)
        namespace = getattr(self.__class__, "__plugin_namespace__", "agent.type")
        name = getattr(self.__class__, "__plugin_name__", self.__class__.__name__)
        self.logger = get_plugin_logger(phase=self._pipeline_phase, namespace=namespace, plugin_name=name)
        strategy_config = config.get("strategy", {})
        self.manager_each_step = bool(strategy_config.get("manager_each_step", True))

    def step(self, screenshot_path: str, width: int, height: int, xml_path: str) -> Action:
        """Run one manager/operator/critic interaction cycle."""
        correction = self._reflect_previous_action(screenshot_path)
        if correction is not None:
            self._commit_action(correction, correction.thought or "Critic correction", "critic", screenshot_path)
            return correction

        try:
            perception_result = self._perceive_current_screen(screenshot_path, width, height, xml_path)
        except Exception as e:
            return Action(type=ActionType.FAIL, thought=f"All perception strategies crashed: {e}")

        self._run_manager_step(screenshot_path)

        if self.verbose:
            self.logger.info("MultiAgent operator reasoning...")

        try:
            action, response = self._think_with_reasoning(perception_result)
        except Exception as e:
            self.logger.error("multi-agent operator reasoning failed: %s", e, exc_info=True)
            return Action(type=ActionType.FAIL, thought=f"Operator Error: {e}")

        self._commit_action(action, response, "operator", screenshot_path)

        if self.verbose:
            self.logger.info("MultiAgent operator decision: %s %s", action.type.value, action.params)

        return action

    def _run_manager_step(self, screenshot_path: str) -> None:
        """Refresh the manager plan before the operator acts."""
        if not (self.planner and self.manager_each_step):
            return

        try:
            plan_input = PlanInput(task=self.current_task, screenshot_path=screenshot_path)
            plan_result = self.planner.make_plan(plan_input)
            self.current_plan = getattr(plan_result, "content", str(plan_result))
            preview = self.current_plan
            if len(preview) > 300:
                preview = preview[:300] + "…"
            self.logger.info("Manager updated plan (%d chars): %s", len(self.current_plan), preview)

            if self.memory:
                metadata = dict(getattr(plan_result, "data", {}) or {})
                metadata["source"] = "manager_step"
                self.memory.add(MemoryFragment(
                    role="system",
                    type=FragmentType.PLAN,
                    content=f"Manager plan: {self.current_plan}",
                    metadata=metadata,
                ))
        except Exception as e:
            self.logger.error("manager planning failed: %s", e, exc_info=True)
            if self.memory:
                self.memory.add(MemoryFragment(
                    role="system",
                    type=FragmentType.ERROR,
                    content=f"Manager planning failed, continue with previous plan. Reason: {e}",
                    metadata={"source": "manager_step"},
                ))
