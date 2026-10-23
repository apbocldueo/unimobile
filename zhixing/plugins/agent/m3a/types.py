"""Data-only values crossing M3A graph boundaries; no clients or device handles."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any, Mapping

from zhixing.components import ActionResult, DeviceObservation, TaskInput


@dataclass(frozen=True)
class M3AReply:
    """Model text and the two source control facts, without a raw HTTP response."""

    text: str
    is_safe: bool | None = None
    has_response: bool = True


@dataclass(frozen=True)
class M3AView:
    """One original observation, full ordered UI list, and lossless rendered images."""

    observation: DeviceObservation
    raw: str
    som: str
    ui_description: str


@dataclass(frozen=True)
class M3AStep:
    """Portable counterpart of official step_data, with response-presence flags."""

    raw_screenshot: str | None = None
    before_screenshot_with_som: str | None = None
    before_ui_elements: tuple[Mapping[str, Any], ...] = ()
    after_screenshot_with_som: str | None = None
    action_prompt: str | None = None
    action_output: str | None = None
    action_output_json: Mapping[str, Any] | None = None
    action_reason: str | None = None
    action_raw_response: bool = False
    summary_prompt: str | None = None
    summary: str | None = None
    summary_raw_response: bool = False

    def evidence(self) -> dict[str, Any]:
        """Return serializable source step fields without live response objects.

        Returns:
            dict: Exact text, portable UI data, image paths and response flags.
        """
        return asdict(self)


@dataclass(frozen=True)
class M3AFrame:
    """Run-owned episode cursor shared by explicit graph stages."""

    task: TaskInput
    round_number: int = 0
    step: M3AStep | None = None
    before: M3AView | None = None
    action_text: str = ""
    append_history: bool = False
    done: bool = False
    goal_status: str | None = None
    route: str = "execute"
    history: tuple[M3AStep, ...] = ()
    episode: tuple[M3AStep, ...] = ()
    actions: tuple[ActionResult, ...] = ()
    finished: bool = False
    environment_done: bool = False


def portable_ui(elements: Any) -> tuple[dict[str, Any], ...]:
    """Copy official UI dataclasses to JSON-only data before leaving the boundary.

    Args:
        elements: Ordered source UIElement dataclasses.
    Raises:
        TypeError: An input is not a dataclass or its semantic fields are non-JSON.
    Returns:
        tuple: Elements in unchanged source order, including invalid/invisible ones.
    """
    import json

    # M3A never reads UIElement.metadata. Keep opaque upstream internals out of
    # trajectories, even when they happen to be JSON-serializable credentials.
    result = []
    for element in elements:
        values = {field.name: None if field.name == "metadata" else getattr(element, field.name)
                  for field in fields(element)}
        for key in ("bbox", "bbox_pixels"):
            if values.get(key) is not None:
                values[key] = asdict(values[key])
        result.append(json.loads(json.dumps(values)))
    return tuple(result)


def source_ui(elements: Any) -> list[Any]:
    """Reconstruct the source UI shape without importing AndroidWorld/protobuf.

    Args:
        elements: JSON-only ordered UIElement dictionaries.
    Raises:
        TypeError: A dictionary does not follow the source dataclass signature.
    Returns:
        list: Source-compatible elements with source bounding-box objects.
    """
    from .source import BoundingBox, UIElement

    result = []
    for element in elements:
        values = dict(element)
        for key in ("bbox", "bbox_pixels"):
            if values.get(key) is not None:
                values[key] = BoundingBox(**values[key])
        result.append(UIElement(**values))
    return result
