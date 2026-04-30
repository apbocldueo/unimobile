from zhixing.core.agent.interfaces import BaseAgent
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.utils.registry import register_strategy

# TODO 
@register_strategy("reflection_agent")
class ReflectionStrategy(BaseAgent):
    """
    It reuses the perception and thinking abilities of the parent class, but adds a "self-check" step.
    """

    def step(self, screenshot_path: str) -> Action:
        """Reflection Strategy: learn"""
        pass