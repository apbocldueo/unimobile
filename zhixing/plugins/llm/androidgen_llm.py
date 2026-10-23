"""Lazy original AndroidGen GPT transport; independent actor/planner dependencies."""

from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="llm", name="androidgen_llm")
class AndroidGenLLM:
    """Preserve original GPT messages, image bytes, sampling and backoff semantics."""

    def __init__(self, model: str = "gpt-4o-2024-08-06", temperature: float = 0.5,
                 top_p: float = 0.5, rate_limit: int = -1) -> None:
        """Remember public configuration without importing OpenAI or reading keys.

        Args:
            model: Original-compatible GPT identifier.
            temperature: Original default sampling temperature.
            top_p: Original default nucleus sampling value.
            rate_limit: Original wrapper option; source computes but does not sleep on it.
        Returns:
            None.
        """
        self.params = dict(model=model, temperature=temperature, top_p=top_p, rate_limit=rate_limit)
        self._client = None

    def generate(self, prompt, system_prompt=None, history=None):
        """Call the original transport only when a graph model node is activated.

        Args:
            prompt: Source text or text/image_url dictionary.
            system_prompt: Original system prompt string.
            history: Exact ordered role/content dictionaries, or None for planning.
        Raises:
            ImportError: OpenAI/backoff optional dependencies are unavailable.
            Exception: Original engine construction or request fails.
        Returns:
            str: Original unmodified response text.
        """
        if self._client is None:
            from zhixing.plugins.agent.androidgen._gpt import OpenaiEngine

            self._client = OpenaiEngine(**self.params)
        return self._client.generate(prompt=prompt, system_prompt=system_prompt, history=history or [])
