from zhixing.agents.strategies.modular import ModularAgent
from zhixing.core.protocol import Action, ActionType
from zhixing.utils.registry import register_strategy

# TODO 
@register_strategy("reflection_agent")
class ReflectionStrategy(ModularAgent):
    """
    It reuses the perception and thinking abilities of the parent class, but adds a "self-check" step.
    """

    def step(self, screenshot_path: str) -> Action:
        """Reflection Strategy: learn"""
        pass