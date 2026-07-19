from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionInput, PerceptionResult
from zhixing.core.factory import PluginRegistry

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _load_ui_xml(xml_path: str) -> str:
    with open(xml_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    xml_start = content.find("<?xml")
    if xml_start > 0:
        content = content[xml_start:]
    return content


def _parse_bounds_string(bounds_str: str | None) -> tuple[int, int, int, int] | None:
    if not bounds_str:
        return None
    match = _BOUNDS_RE.match(bounds_str.strip())
    if not match:
        return None
    return tuple(int(match.group(i)) for i in range(1, 5))  # type: ignore[return-value]


def _parse_hierarchy_xml_to_raw_elements(hierarchy_xml: str) -> list[dict[str, Any]]:
    elements: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(hierarchy_xml)
    except ET.ParseError:
        return elements

    def walk(node: ET.Element) -> None:
        element = dict(node.attrib)
        if "content-desc" in element:
            element["accessibilityText"] = element["content-desc"]
        if element:
            elements.append(element)
        for child in node:
            walk(child)

    walk(root)
    return elements


@PluginRegistry.register(namespace="agent.perception", name="os_genesis_perception")
class OSGenesisPerception(BasePerception):
    """OS-Genesis accessibility-tree perception.

    It reproduces the AndroidWorld OS-Genesis observation style: a screenshot
    marked with accessibility element indices plus a compact JSON accessibility
    tree mapping element text/description to center coordinates.
    """

    mode_name = "os_genesis"

    def __init__(
        self,
        max_elements: int = 160,
        draw_marked_screenshot: bool = True,
        **kwargs: Any,
    ) -> None:
        self.max_elements = max_elements
        self.draw_marked_screenshot = draw_marked_screenshot
        super().__init__(**kwargs)

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        screenshot_path = perception_input.screenshot_path
        ui_path = perception_input.ui_path
        width = perception_input.width
        height = perception_input.height

        try:
            from PIL import Image

            with Image.open(screenshot_path) as img:
                width, height = img.size
        except Exception:
            pass

        if not ui_path:
            raise ValueError("OSGenesisPerception requires PerceptionInput.ui_path")
        if not os.path.isfile(ui_path):
            raise FileNotFoundError(f"UI XML not found: {ui_path}")

        raw_elements = _parse_hierarchy_xml_to_raw_elements(_load_ui_xml(ui_path))
        elements: list[dict[str, Any]] = []
        a11y_tree: dict[str, str] = {}

        for raw in raw_elements:
            parsed = _parse_bounds_string(raw.get("bounds"))
            if not parsed:
                continue
            x1, y1, x2, y2 = parsed
            if not self._valid_bbox(x1, y1, x2, y2, width, height):
                continue

            elem = self._format_element(raw, len(elements), x1, y1, x2, y2)
            elements.append(elem)
            label = self._clean_label(elem)
            if label:
                a11y_tree[label] = f"({elem['coordinates'][0]}, {elem['coordinates'][1]})"

            if len(elements) >= self.max_elements:
                break

        marked_path = screenshot_path
        if self.draw_marked_screenshot:
            marked_path = self._draw_marks(screenshot_path, elements)

        prompt = self._get_prompt_context({"a11y_tree": a11y_tree, "elements": elements})
        return PerceptionResult(
            mode=self.mode_name,
            original_screenshot_path=screenshot_path,
            marked_screenshot_path=marked_path,
            elements=elements,
            metadata={"width": width, "height": height, "a11y_tree": a11y_tree},
            data={"a11y_tree": a11y_tree, "elements": elements},
            visual_representations=[marked_path],
            prompt_representation=prompt,
        )

    @staticmethod
    def _valid_bbox(x1: int, y1: int, x2: int, y2: int, width: int, height: int) -> bool:
        return not (
            x1 >= x2
            or y1 >= y2
            or x1 >= width
            or x2 <= 0
            or y1 >= height
            or y2 <= 0
        )

    @staticmethod
    def _format_element(raw: dict[str, Any], index: int, x1: int, y1: int, x2: int, y2: int) -> dict[str, Any]:
        class_name = raw.get("class") or ""
        return {
            "index": index,
            "text": (raw.get("text") or "").strip(),
            "content_description": (raw.get("content-desc") or raw.get("accessibilityText") or "").strip(),
            "hint_text": (raw.get("hint_text") or raw.get("hint") or "").strip(),
            "tooltip": (raw.get("tooltip") or "").strip(),
            "class_name": class_name,
            "package_name": raw.get("package", ""),
            "resource_name": raw.get("resource-id", ""),
            "coordinates": [(x1 + x2) / 2, (y1 + y2) / 2],
            "bbox_pixel": [x1, y1, x2, y2],
            "is_clickable": raw.get("clickable") == "true",
            "is_long_clickable": raw.get("long-clickable") == "true",
            "is_editable": raw.get("password") == "true" or "edittext" in class_name.lower(),
            "is_enabled": raw.get("enabled", "true") == "true",
            "is_focused": raw.get("focused") == "true",
            "is_focusable": raw.get("focusable") == "true",
            "is_scrollable": raw.get("scrollable") == "true",
            "is_selected": raw.get("selected") == "true",
            "is_checked": raw.get("checked") == "true",
            "is_visible": True,
        }

    @staticmethod
    def _clean_label(elem: dict[str, Any]) -> str:
        label = (
            elem.get("text")
            or elem.get("content_description")
            or elem.get("hint_text")
            or elem.get("tooltip")
        )
        if label:
            return str(label)
        class_name = elem.get("class_name") or ""
        if class_name == "android.widget.Switch":
            return f"{class_name} Is_Checked: {elem.get('is_checked')}"
        names = [class_name, elem.get("package_name"), elem.get("resource_name")]
        return " ".join(str(v) for v in names if v)

    def _draw_marks(self, screenshot_path: str, elements: list[dict[str, Any]]) -> str:
        dir_name = os.path.dirname(screenshot_path)
        base_name = os.path.splitext(os.path.basename(screenshot_path))[0]
        marked_path = os.path.join(dir_name, f"{base_name}_os_genesis.png")
        try:
            from PIL import Image, ImageDraw, ImageFont

            image = Image.open(screenshot_path).convert("RGB")
        except Exception:
            return screenshot_path

        draw = ImageDraw.Draw(image, "RGBA")
        font = ImageFont.load_default()
        for elem in elements:
            x1, y1, x2, y2 = elem["bbox_pixel"]
            idx = str(elem["index"])
            draw.rectangle([x1, y1, x2, y2], outline=(0, 255, 0, 230), width=2)
            label_box = [x1 + 1, y1 + 1, x1 + 36, y1 + 25]
            draw.rectangle(label_box, fill=(255, 255, 255, 230))
            draw.text((x1 + 3, y1 + 5), idx, fill=(0, 0, 0, 255), font=font)

        image.save(marked_path)
        return marked_path

    def _get_prompt_context(self, result: Any) -> str:
        a11y_tree = result.get("a11y_tree", {})
        elements = result.get("elements", [])
        lines = [
            "Accessibility tree:",
            json.dumps(a11y_tree, ensure_ascii=False),
            "",
            "Detailed UI elements:",
        ]
        for elem in elements:
            parts = [f'UI element {elem["index"]}: {{"index": {elem["index"]}']
            for key in (
                "text",
                "content_description",
                "hint_text",
                "tooltip",
                "class_name",
                "resource_name",
            ):
                value = elem.get(key)
                if value:
                    parts.append(f'"{key}": "{value}"')
            parts.extend(
                [
                    f'"is_clickable": {elem.get("is_clickable")}',
                    f'"is_long_clickable": {elem.get("is_long_clickable")}',
                    f'"is_editable": {elem.get("is_editable")}',
                    f'"is_scrollable": {elem.get("is_scrollable")}',
                    f'"is_focusable": {elem.get("is_focusable")}',
                    f'"is_selected": {elem.get("is_selected")}',
                    f'"is_checked": {elem.get("is_checked")}',
                    f'"center": ({elem["coordinates"][0]}, {elem["coordinates"][1]})',
                ]
            )
            lines.append(", ".join(parts) + "}")
        return "\n".join(lines)
