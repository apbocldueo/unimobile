"""Lazy adapter for the original AndroidWorld multimodal wrapper, without policy changes."""

from __future__ import annotations

from typing import Any

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.m3a.types import M3AReply


def model_reply(client: Any, prompt: str, images: tuple[str, ...]) -> M3AReply:
    """Call one explicit M3A model dependency and discard its live response object.

    Args:
        client: generate_m3a adapter or original predict_mm wrapper.
        prompt: Unmodified source prompt.
        images: Ordered lossless image paths.
    Raises:
        TypeError: The dependency does not implement either explicit protocol.
        Exception: The original model call fails outside its own error handling.
    Returns:
        M3AReply: Text, source safety flag and original response truthiness.
    """
    if callable(getattr(client, "generate_m3a", None)):
        result = client.generate_m3a(prompt, images)
        if not isinstance(result, M3AReply):
            raise TypeError("generate_m3a must return M3AReply")
        return result
    if not callable(getattr(client, "predict_mm", None)):
        raise TypeError("M3A model requires generate_m3a or original predict_mm")
    from zhixing.plugins.agent.m3a.perception import load_pixels

    text, safe, response = client.predict_mm(prompt, [load_pixels(path) for path in images])
    return M3AReply(text, safe, bool(response))


@PluginRegistry.register(namespace="llm", name="m3a_llm")
class M3ALLM:
    """Reuse the official Gpt4Wrapper, including its original transport/retry semantics."""

    def __init__(self, model: str = "gpt-4-turbo-2024-04-09", max_retry: int = 3,
                 temperature: float = 0.0) -> None:
        """Remember public configuration without importing AndroidWorld or reading keys.

        Args:
            model: Explicit original-compatible model identifier.
            max_retry: Original Gpt4Wrapper retry setting.
            temperature: Original sampling temperature.
        Returns:
            None.
        """
        self.model, self.max_retry, self.temperature = model, max_retry, temperature
        self._client = None

    def generate_m3a(self, prompt: str, images: tuple[str, ...]) -> M3AReply:
        """Load the original wrapper only for an actual model invocation.

        Args:
            prompt: Source action or summary prompt.
            images: Ordered original RGB image artifacts.
        Raises:
            ImportError: Official AndroidWorld and its dependencies are unavailable.
            Exception: Source wrapper initialization or request fails.
        Returns:
            M3AReply: Portable source result without credentials or HTTP objects.
        """
        if self._client is None:
            from android_world.agents.infer import Gpt4Wrapper

            self._client = Gpt4Wrapper(self.model, max_retry=self.max_retry, temperature=self.temperature)
        return model_reply(self._client, prompt, images)
