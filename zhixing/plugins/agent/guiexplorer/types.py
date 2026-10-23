"""Portable GUI-explorer values extending the existing M3A episode contracts."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from zhixing.plugins.agent.m3a.types import M3AStep, M3AView


@dataclass(frozen=True)
class GUIExplorerReply:
    """Model content and original response-presence fact, without a live response."""

    text: str
    has_response: bool = True


@dataclass(frozen=True)
class GUIExplorerView(M3AView):
    """Original raw/SoM images plus ordered element crops for knowledge retrieval."""

    crop_indices: tuple[int, ...] = ()
    crop_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeEntry:
    """Retrieved hints mapped back to one original full-list UI index."""

    index: int
    hints: tuple[str, ...]

    def source_value(self) -> dict:
        """Return the original ranker/prompt shape without changing hint order.

        Returns:
            dict: Original index and insertion-ordered hint_1, hint_2, ... values.
        """
        return {"index": self.index, "hints": {f"hint_{i + 1}": value for i, value in enumerate(self.hints)}}


@dataclass(frozen=True)
class GUIExplorerKnowledge:
    """Retrieval/ranking result, containing no clients, tensors or device handles."""

    view: GUIExplorerView
    entries: tuple[KnowledgeEntry, ...]
    prompt_tokens: int = 0
    completion_tokens: int = 0


@dataclass(frozen=True)
class GUIExplorerStep(M3AStep):
    """Source-specific evidence retained by the unchanged M3ACommit operation."""

    goal: str = ""
    before_screenshot: str | None = None
    after_screenshot: str | None = None
    converted_action: str | Mapping[str, Any] = "error_retry"
    actual_action_coordinates: tuple[int, ...] | None = None
    top_app_package_name: str | None = None
    target_element: Mapping[str, Any] | None = None
    ranker_usage: Mapping[str, int] = field(default_factory=lambda: {"prompt_tokens": 0, "completion_tokens": 0})
    logical_screen_size: tuple[int, int] | None = None
