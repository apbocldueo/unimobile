"""Lazy original-compatible WEBP and pairwise-ranking transports with bounded errors."""

from contextlib import asynccontextmanager
import os
import time

from zhixing.core.factory import PluginRegistry
from zhixing.core.llm.usage import record_usage


def _record(usage):
    """Forward only public token counts to the existing task usage collector.

    Args:
        usage: Original OpenAI-style usage dictionary.
    Returns:
        None.
    """
    if usage:
        record_usage(prompt_tokens=usage.get("prompt_tokens", 0), completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0))


class _RankingSession:
    """One shared original aiohttp session, owned by a single ranking activation."""

    def __init__(self, owner, session):
        """Bind private transport state without exposing it in graph outputs.

        Args:
            owner: Source model configuration service.
            session: Live caller-scoped aiohttp session.
        Returns:
            None.
        """
        self.owner, self.session = owner, session

    async def ask(self, prompt, usage):
        """Preserve the source three-attempt comparison and permissive '1' fallback.

        Args:
            prompt: Unmodified pairwise knowledge prompt.
            usage: Source mutable token accumulator.
        Returns:
            str: Original model content, or '1' after three failures.
        """
        import asyncio

        url, key, _ = self.owner.settings()
        data = {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "temperature": 0.0}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        for _ in range(3):
            try:
                async with self.session.post(url + "/chat/completions", json=data, headers=headers) as response:
                    result = await response.json()
                    content = result.get("choices", [{}])[0].get("message", {}).get("content", "1")
                    counts = result.get("usage", {})
                    usage["prompt_tokens"] += counts.get("prompt_tokens", 0)
                    usage["completion_tokens"] += counts.get("completion_tokens", 0)
                    _record(counts)
                    return content
            except Exception:
                await asyncio.sleep(1)
        return "1"


@PluginRegistry.register(namespace="llm", name="guiexplorer_llm")
class GUIExplorerLLM:
    """Keep original model/image settings and response presence without import-time I/O."""

    def __init__(self, model: str | None = None, base_url: str | None = None,
                 api_key: str | None = None, low_resolution: bool | None = None):
        """Remember explicit runtime configuration; environment resolution remains lazy.

        Args:
            model: Source OPENAI_API_MODEL override.
            base_url: Source OPENAI_BASE_URL override.
            api_key: Runtime-only key supplied by SecretRef/provider or environment.
            low_resolution: Original optional resize-to-1000 switch.
        Returns:
            None.
        """
        self.model, self.base_url, self.api_key, self.low_resolution = model, base_url, api_key, low_resolution

    def settings(self):
        """Resolve private transport settings only at an actual external invocation.

        Returns:
            tuple: Endpoint, credential and source model; never used as graph data.
        """
        return ((self.base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/"),
                self.api_key if self.api_key is not None else os.getenv("OPENAI_API_KEY"),
                self.model if self.model is not None else os.getenv("OPENAI_API_MODEL"))

    def generate_guiexplorer(self, prompt, images):
        """Send original ordered WEBP images and return source response-presence facts.

        Args:
            prompt: Original action or summary text.
            images: Ordered raw/SoM or before/after lossless image paths.
        Raises:
            Exception: Source image loading/encoding fails before the request guard.
        Returns:
            GUIExplorerReply: Source text and response fact; HTTP errors are bounded.
        """
        import requests
        from zhixing.plugins.agent.guiexplorer import source
        from zhixing.plugins.agent.guiexplorer.types import GUIExplorerReply
        from zhixing.plugins.agent.m3a.perception import load_pixels

        url, key, model = self.settings()
        low = self.low_resolution if self.low_resolution is not None else os.getenv("LOW_RESOLUTION", "False").lower() == "true"
        content = [{"type": "text", "text": prompt}]
        for path in images:
            pixels = load_pixels(path)
            if low:
                pixels = source.resize_ndarray_image(pixels, 1000)
            content.append({"type": "image_url", "image_url": {"url": "data:image/webp;base64," + source.ndarray_to_webp_base64(pixels)}})
        payload = {"model": model, "temperature": 0.0, "messages": [{"role": "user", "content": content}], "max_tokens": 1000}
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}"}
        for attempt in range(5):
            try:
                response = requests.post(url + "/chat/completions", headers=headers, json=payload, timeout=60)
                result = response.json()
                if response.ok and "choices" in result:
                    text = result["choices"][0]["message"]["content"]
                    _record(result.get("usage"))
                    return GUIExplorerReply(text)
            except Exception:
                pass
            # Compatibility repair: HTTP failures also consume the five-attempt
            # budget. The official non-OK branch can otherwise loop forever.
            time.sleep(2 ** attempt)
        return GUIExplorerReply("Error calling LLM", has_response=False)

    @asynccontextmanager
    async def ranking_session(self):
        """Own one bounded HTTP session without changing original ranking responses.

        Yields:
            _RankingSession: Explicit async pairwise-model service.
        Raises:
            Exception: Creating/closing the optional aiohttp transport fails.
        """
        import aiohttp

        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=300)) as session:
            yield _RankingSession(self, session)
