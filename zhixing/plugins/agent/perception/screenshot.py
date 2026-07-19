from __future__ import annotations

from typing import Any

from PIL import Image

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionInput, PerceptionResult
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="agent.perception", name="screenshot_perception")
class ScreenshotPerception(BasePerception):
    """Visual-only perception for agents that reason directly from screenshots."""

    mode_name = "screenshot"

    def __init__(self, prompt_note: str = "", **kwargs: Any) -> None:
        self.prompt_note = prompt_note
        super().__init__(**kwargs)

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        screenshot_path = perception_input.screenshot_path
        width = perception_input.width
        height = perception_input.height
        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
        except Exception:
            pass

        prompt = self._get_prompt_context({"width": width, "height": height})
        return PerceptionResult(
            mode=self.mode_name,
            original_screenshot_path=screenshot_path,
            elements=[],
            metadata={"width": width, "height": height},
            data={},
            visual_representations=[screenshot_path],
            prompt_representation=prompt,
        )

    def _get_prompt_context(self, result: Any) -> str:
        width = result.get("width", 0)
        height = result.get("height", 0)
        lines = [
            "The screen observation is the attached screenshot.",
            f"The screenshot width is {width} pixels and height is {height} pixels.",
        ]
        if self.prompt_note:
            lines.append(self.prompt_note)
        return "\n".join(lines)
