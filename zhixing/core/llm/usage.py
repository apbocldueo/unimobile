"""Per-task LLM token accounting via contextvars.

Any code path that calls ``BaseLLM.generate()`` records usage here when a task
scope is active (``reset_task_usage`` at task start). No per-component wiring.
"""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class TokenUsageSnapshot:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    call_count: int = 0

    def add(self, *, prompt_tokens: int = 0, completion_tokens: int = 0, total_tokens: int = 0) -> None:
        p = int(prompt_tokens or 0)
        c = int(completion_tokens or 0)
        t = int(total_tokens or 0)
        if t <= 0 and (p > 0 or c > 0):
            t = p + c
        self.prompt_tokens += p
        self.completion_tokens += c
        self.total_tokens += t
        self.call_count += 1

    def to_dict(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "call_count": self.call_count,
        }


_task_usage: ContextVar[Optional[TokenUsageSnapshot]] = ContextVar("llm_task_usage", default=None)


def reset_task_usage() -> TokenUsageSnapshot:
    """Start (or restart) token accounting for one benchmark / agent task."""
    snap = TokenUsageSnapshot()
    _task_usage.set(snap)
    return snap


def record_usage(
    *,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    snap = _task_usage.get()
    if snap is not None:
        snap.add(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
        )


def get_task_usage() -> TokenUsageSnapshot:
    snap = _task_usage.get()
    return snap if snap is not None else TokenUsageSnapshot()


def get_task_usage_dict() -> Dict[str, int]:
    return get_task_usage().to_dict()


def usage_from_openai_response(usage: Any) -> Optional[Dict[str, int]]:
    """Extract token fields from an OpenAI ``CompletionUsage`` (or similar)."""
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    total = getattr(usage, "total_tokens", None)
    if prompt is None and completion is None and total is None and isinstance(usage, dict):
        prompt = usage.get("prompt_tokens")
        completion = usage.get("completion_tokens")
        total = usage.get("total_tokens")
    if prompt is None and completion is None and total is None:
        return None
    p = int(prompt or 0)
    c = int(completion or 0)
    t = int(total or 0)
    if t <= 0 and (p > 0 or c > 0):
        t = p + c
    return {"prompt_tokens": p, "completion_tokens": c, "total_tokens": t}
