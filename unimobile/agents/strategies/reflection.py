from unimobile.agents.strategies.modular import ModularAgent
from unimobile.core.protocol import Action, ActionType
from unimobile.utils.registry import register_strategy

# TODO 
@register_strategy("reflection")
class ReflectionStrategy(ModularAgent):
    """
    It reuses the perception and thinking abilities of the parent class, but adds a "self-check" step.
    """

    def step(self, screenshot_path: str) -> Action:
        pass