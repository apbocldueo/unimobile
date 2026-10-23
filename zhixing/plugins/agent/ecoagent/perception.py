"""Explicit screenshots and the original screen-description request."""

from dataclasses import replace
from functools import partial

from zhixing.core.factory import PluginRegistry
from zhixing.components import DeviceExecutionError
from .environment import environment
from .prompts import DESCRIPTION_PROMPT


@PluginRegistry.register(namespace='agent.perception', name='ecoagent_observe')
class EcoObserve:
    """Capture after startup Home and after each executed high-level action."""

    def invoke(self, input, runtime):
        """Shift the previous after image into before, then capture a new after image.

        Args:
            input: Source frame after an optional action.
            runtime: Explicit device/artifact services.
        Raises:
            Exception: Capture or evidence persistence fails.
        Returns:
            EcoFrame: Immutable before/after observation references.
        """
        boundary = environment(runtime)
        try:
            return replace(input, before=input.after, after=boundary.capture(runtime))
        except Exception:
            raise DeviceExecutionError('ecoagent_capture', 'EcoAgent screenshot capture failed') from None


@PluginRegistry.register(namespace='agent.perception', name='ecoagent_description')
class EcoDescription:
    """Submit and collect one description in separate ordinary graph activations."""

    def __init__(self, description_llm=None, collect=False):
        """Bind mode. Args: description_llm: Model on submit; collect: Collection mode. Raises: ValueError: Missing model or invalid switch. Returns: None."""
        if type(collect) is not bool or not collect and description_llm is None:
            raise ValueError('EcoAgent description submission requires a model')
        self.llm, self.collect = description_llm, collect

    def invoke(self, input, runtime):
        """Submit quickly or collect only after the source summary was consumed.

        Args:
            input: Portable round frame.
            runtime: Explicit run-owned job boundary.
        Raises:
            Exception: Selected model request or ticket fails.
        Returns:
            EcoFrame: Description ticket or description text, without a Future.
        """
        jobs = environment(runtime).jobs
        if self.collect:
            value = jobs.collect(runtime.run_id, input.round, input.description_ticket)
            return replace(input, description=value.text)
        ticket = jobs.submit(runtime.run_id, input.round, 'description',
            partial(self.llm.complete, 'description', DESCRIPTION_PROMPT, (input.after,)))
        return replace(input, description_ticket=ticket)
