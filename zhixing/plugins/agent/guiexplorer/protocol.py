"""Explicit model/session protocols replacing only source external I/O."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from typing import Any

from .types import GUIExplorerReply


def send_message(*args, **kwargs) -> None:
    """Preserve the official non-demo no-op without reading demo environment state.

    Args:
        args, kwargs: Original optional display-message arguments.
    Returns:
        None: No demo server is contacted by the non-demo graph.
    """


async def ranking_ask(prompt: str, session: Any, usage: dict[str, int]) -> str:
    """Call one explicit comparison service from unchanged source sorting helpers.

    Args:
        prompt: Original ranking prompt.
        session: Explicit ranking session implementing async ask.
        usage: Source token accumulator, updated by the session.
    Raises:
        Exception: The injected comparison service fails outside its source fallback.
    Returns:
        str: Original comparison response, including its permissive '2' test.
    """
    return await session.ask(prompt, usage)


def model_reply(client: Any, prompt: str, images: tuple[str, ...]) -> GUIExplorerReply:
    """Call the source-aware model without treating empty content as no response.

    Args:
        client: Explicit generate_guiexplorer dependency.
        prompt: Unmodified source text.
        images: Ordered lossless source image paths.
    Raises:
        TypeError: The service/result does not implement the explicit protocol.
        Exception: The external model service fails.
    Returns:
        GUIExplorerReply: Content and response-presence fact only.
    """
    reply = client.generate_guiexplorer(prompt, images)
    if not isinstance(reply, GUIExplorerReply):
        raise TypeError("generate_guiexplorer must return GUIExplorerReply")
    return reply


def rank_entries(client: Any, goal: str, entries: list[dict], usage: dict[str, int]) -> list[dict]:
    """Run unchanged async comparison/merge helpers inside a synchronous component.

    Args:
        client: Service exposing an async ranking_session context manager.
        goal: Original task instruction.
        entries: Original ordered index/hints dictionaries.
        usage: Original token accumulator.
    Raises:
        Exception: Source sorting or external comparison fails.
    Returns:
        list: Complete knowledge ordering, never just one selected item.
    """
    from .source import AsyncRanker

    async def run():
        """Own one original shared comparison session and await its bounded sort.

        Returns:
            list: Original recursive merge result.
        """
        async with client.ranking_session() as session:
            return await AsyncRanker(goal, entries, session, usage)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run())
    # Avoid nest_asyncio/private-loop mutation when an embedding application
    # already owns an event loop. Only this comparison session moves threads.
    with ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(copy_context().run, lambda: asyncio.run(run())).result()
