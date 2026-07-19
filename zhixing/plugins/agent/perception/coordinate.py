from __future__ import annotations

import os
from typing import Any

from PIL import Image

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionInput, PerceptionResult
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.perception.ally import (
    load_ui_xml,
    parse_hierarchy_xml_to_raw_elements,
    parse_bounds_string,
)


@PluginRegistry.register(namespace="agent.perception", name="coordinate_perception")
class CoordinatePerception(BasePerception):
    """MobileAgent-style coordinate/content perception.

    It converts Android UI hierarchy nodes into compact lines of
    ``[x, y]; text/content/icon description`` for prompts that reason over raw
    pixel coordinates.
    """

    mode_name = "coordinate"

    def __init__(
        self,
        include_non_clickable_text: bool = True,
        max_elements: int = 120,
        keyboard_y_ratio: float = 0.9,
        **kwargs: Any,
    ) -> None:
        self.include_non_clickable_text = include_non_clickable_text
        self.max_elements = max_elements
        self.keyboard_y_ratio = keyboard_y_ratio
        super().__init__(**kwargs)

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        screenshot_path = perception_input.screenshot_path
        ui_path = perception_input.ui_path
        width = perception_input.width
        height = perception_input.height

        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
        except Exception:
            pass

        elements: list[dict[str, Any]] = []
        keyboard_active = False

        if ui_path and os.path.isfile(ui_path):
            raw_elements = parse_hierarchy_xml_to_raw_elements(load_ui_xml(ui_path))
            for raw in raw_elements:
                parsed = parse_bounds_string(raw.get("bounds"))
                if not parsed:
                    continue
                x1, y1, x2, y2 = parsed
                if x2 <= x1 or y2 <= y1:
                    continue

                text = (
                    (raw.get("text") or "").strip()
                    or (raw.get("content-desc") or "").strip()
                    or (raw.get("accessibilityText") or "").strip()
                )
                class_name = raw.get("class") or "node"
                short_type = class_name.split(".")[-1] if "." in class_name else class_name
                clickable = raw.get("clickable") == "true"
                focusable = raw.get("focusable") == "true"
                enabled = raw.get("enabled", "true") == "true"

                if not text and (clickable or focusable):
                    text = f"icon: {short_type}"
                elif text:
                    text = f"text: {text}"

                if not text:
                    continue
                if not self.include_non_clickable_text and not (clickable or focusable):
                    continue

                center = [(x1 + x2) // 2, (y1 + y2) // 2]
                if center[1] >= int(height * self.keyboard_y_ratio):
                    haystack = f"{text} {raw.get('resource-id', '')} {class_name}"
                    if "keyboard" in haystack.lower() or "ime" in haystack.lower():
                        keyboard_active = True

                elements.append(
                    {
                        "index": len(elements) + 1,
                        "text": text,
                        "type": short_type,
                        "coordinates": center,
                        "bbox_pixel": [x1, y1, x2, y2],
                        "resource-id": raw.get("resource-id", ""),
                        "clickable": clickable,
                        "focusable": focusable,
                        "enabled": enabled,
                    }
                )
                if len(elements) >= self.max_elements:
                    break

        prompt = self._get_prompt_context({"elements": elements, "keyboard_active": keyboard_active})
        return PerceptionResult(
            mode=self.mode_name,
            original_screenshot_path=screenshot_path,
            elements=elements,
            metadata={
                "width": width,
                "height": height,
                "keyboard_active": keyboard_active,
            },
            data={"elements": elements, "keyboard_active": keyboard_active},
            visual_representations=[screenshot_path],
            prompt_representation=prompt,
        )

    def _get_prompt_context(self, result: Any) -> str:
        elements = result.get("elements", [])
        keyboard_active = bool(result.get("keyboard_active"))
        lines = [
            "### Screenshot information ###",
            "The following information was extracted from system UI files.",
            "Each row has the format: [x, y]; content. Coordinates are absolute screen pixels.",
        ]
        for elem in elements:
            coords = elem.get("coordinates") or [0, 0]
            text = elem.get("text") or ""
            if text and text != "icon: None" and coords != [0, 0]:
                lines.append(f"{coords}; {text}")
        lines.extend(
            [
                "Please note that this information is not necessarily accurate. Combine it with the screenshot.",
                "",
                "### Keyboard status ###",
                (
                    "The keyboard has been activated and you can type."
                    if keyboard_active
                    else "The keyboard has not been activated and you can't type."
                ),
            ]
        )
        return "\n".join(lines)
