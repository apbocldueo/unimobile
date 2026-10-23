"""Original two-image expectation summary and literal not-word gate."""

from dataclasses import replace
from functools import partial
import re

from zhixing.core.factory import PluginRegistry
from .environment import environment
from .prompts import SUMARRY_PROMPT


@PluginRegistry.register(namespace='agent.verifier', name='ecoagent_summary')
class EcoSummary:
    """Preserve source judgment, including its acceptance of No without the word not."""

    def __init__(self, summary_llm=None, collect=False):
        """Bind mode. Args: summary_llm: Submit model; collect: Collection mode. Raises: ValueError: Missing model or invalid switch. Returns: None."""
        if type(collect) is not bool or not collect and summary_llm is None:
            raise ValueError('EcoAgent summary submission requires a model')
        self.llm, self.collect = summary_llm, collect

    def invoke(self, input, runtime):
        """Submit summary or consume it before description and speculative action errors.

        Args:
            input: Portable round frame with source expectation index.
            runtime: Explicit run-owned I/O services.
        Raises:
            Exception: Expectation or selected model request is unavailable.
        Returns:
            EcoFrame: Summary ticket, or text and original acceptance judgment.
        """
        jobs = environment(runtime).jobs
        if self.collect:
            value = jobs.collect(runtime.run_id, input.round, input.summary_ticket)
            return replace(input, summary=value.text, accepted=not bool(re.search(r'\bnot\b', value.text.lower())))
        ticket = jobs.submit(runtime.run_id, input.round, 'summary', partial(self.llm.complete, 'summary',
            SUMARRY_PROMPT.format(expectation=input.expectations[input.round]), (input.before, input.after)))
        return replace(input, summary_ticket=ticket)
