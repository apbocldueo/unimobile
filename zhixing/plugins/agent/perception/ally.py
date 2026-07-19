"""
MobileAccessibilityPerception (mode="ally") — parse pre-dumped Android UIAutomator XML (offline only).

ADB dump/pull must be done **outside** this class. Pass the XML path via PerceptionInput.ui_path.

Usage:
    # 1. Outside: adb shell uiautomator dump ... && adb pull ... → step_10_ui.xml
    # 2. Inside:
    perception = MobileAccessibilityPerception()
    result: PerceptionResult = perception.perceive(PerceptionInput(
        screenshot_path="screenshots/step_10.png",
        width=1080,
        height=2340,
        ui_path="screenshots/step_10_ui.xml",  # required
    ))
    # result.elements          → list[dict]  (structured, for code)
    # result.prompt_representation → JSON str (for LLM prompt)
"""

from __future__ import annotations

import json
import os
import re
import xml.etree.ElementTree as ET
from typing import Any

from PIL import Image, ImageDraw

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionInput, PerceptionResult
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.perception.coordinates import (
    COORDINATE_SCALE_MAX,
    apply_coordinate_normalization_to_elements,
    build_coordinate_metadata,
    format_normalized_coordinate_instruction,
)

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def parse_hierarchy_xml_to_raw_elements(hierarchy_xml: str) -> list[dict[str, Any]]:
    """Parse uiautomator dump XML into a flat list of Android node attribute dicts."""
    elements: list[dict[str, Any]] = []

    try:
        root = ET.fromstring(hierarchy_xml)
    except ET.ParseError:
        return elements

    def _extract_element(node: ET.Element) -> None:
        element: dict[str, Any] = {}
        for attr_name, attr_value in node.attrib.items():
            if attr_name == "resource-id":
                element["resource-id"] = attr_value
            elif attr_name == "text":
                element["text"] = attr_value
            elif attr_name == "content-desc":
                element["content-desc"] = attr_value
                element["accessibilityText"] = attr_value
            elif attr_name == "bounds":
                element["bounds"] = attr_value
            elif attr_name == "class":
                element["class"] = attr_value
            elif attr_name == "package":
                element["package"] = attr_value
            elif attr_name in (
                "checkable",
                "checked",
                "clickable",
                "enabled",
                "focusable",
                "focused",
                "scrollable",
                "long-clickable",
                "password",
                "selected",
            ):
                element[attr_name] = attr_value
            else:
                element[attr_name] = attr_value

        if element:
            elements.append(element)

        for child in node:
            _extract_element(child)

    _extract_element(root)
    return elements


def load_ui_xml(xml_path: str) -> str:
    with open(xml_path, encoding="utf-8", errors="replace") as f:
        content = f.read()
    xml_start = content.find("<?xml")
    if xml_start > 0:
        content = content[xml_start:]
    return content


def parse_bounds_string(bounds_str: str | None) -> tuple[int, int, int, int] | None:
    if not bounds_str:
        return None
    match = _BOUNDS_RE.match(bounds_str.strip())
    if not match:
        return None
    return tuple(int(match.group(i)) for i in range(1, 5))  # type: ignore[return-value]


def raw_element_to_formatted(
    raw: dict[str, Any],
    index: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    text = (
        (raw.get("text") or "").strip()
        or (raw.get("content-desc") or "").strip()
        or (raw.get("accessibilityText") or "").strip()
    )
    class_name = raw.get("class") or "node"
    short_type = class_name.split(".")[-1] if "." in class_name else class_name

    bounds_str = raw.get("bounds") or ""
    parsed = parse_bounds_string(bounds_str)
    coordinates = [0, 0]
    bbox_norm = [0.0, 0.0, 0.0, 0.0]
    bbox_pixel = [0, 0, 0, 0]

    if parsed and width > 0 and height > 0:
        x1, y1, x2, y2 = parsed
        coordinates = [(x1 + x2) // 2, (y1 + y2) // 2]
        bbox_pixel = [x1, y1, x2, y2]
        bbox_norm = [x1 / width, y1 / height, x2 / width, y2 / height]

    return {
        "index": index,
        "text": text or short_type,
        "type": short_type,
        "coordinates": coordinates,
        "bbox": bbox_norm,
        "bbox_pixel": bbox_pixel,
        "bounds": bounds_str,
        "resource-id": raw.get("resource-id", ""),
        "clickable": raw.get("clickable") == "true",
        "enabled": raw.get("enabled", "true") == "true",
        "package": raw.get("package", ""),
    }


def format_raw_elements(
    raw_elements: list[dict[str, Any]],
    width: int,
    height: int,
    *,
    skip_empty: bool = True,
) -> list[dict[str, Any]]:
    formatted: list[dict[str, Any]] = []
    for raw in raw_elements:
        if skip_empty:
            has_bounds = bool(parse_bounds_string(raw.get("bounds")))
            has_text = bool(
                (raw.get("text") or "").strip()
                or (raw.get("content-desc") or "").strip()
            )
            if not has_bounds and not has_text:
                continue
        formatted.append(raw_element_to_formatted(raw, len(formatted), width, height))
    return formatted


def build_perception_json_payload(
    *,
    screenshot_path: str,
    ui_path: str,
    width: int,
    height: int,
    elements: list[dict[str, Any]],
    raw_elements: list[dict[str, Any]],
) -> dict[str, Any]:
    """Structured dict that is serialized into prompt_representation."""
    return {
        "source": "ally",
        "screenshot_path": screenshot_path,
        "ui_path": ui_path,
        "width": width,
        "height": height,
        "element_count": len(elements),
        "raw_node_count": len(raw_elements),
        "elements": elements,
    }


@PluginRegistry.register(namespace="agent.perception", name="ally_perception")
class AllyPerception(BasePerception):
    """
    Offline perception: read UI XML from PerceptionInput.ui_path only.

    This class does NOT run adb. Dump XML on the device and pull it before calling perceive().
    """

    def __init__(
        self,
        draw_marked_screenshot: bool = False,
        skip_empty_nodes: bool = True,
        json_indent: int = 2,
        normalize_coordinates_to_1000: bool = False,
        coordinate_scale_max: int = COORDINATE_SCALE_MAX,
        **kwargs: Any,
    ) -> None:
        self.draw_marked_screenshot = draw_marked_screenshot
        self.skip_empty_nodes = skip_empty_nodes
        self.json_indent = json_indent
        self.normalize_coordinates_to_1000 = normalize_coordinates_to_1000
        self.coordinate_scale_max = coordinate_scale_max
        super().__init__(**kwargs)
        self.logger.info(
            "AllyPerception initialized (offline XML only, no adb; "
            "normalize_coordinates_to_1000=%s, scale_max=%s)",
            self.normalize_coordinates_to_1000,
            self.coordinate_scale_max,
        )

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        """
        Returns:
            PerceptionResult with:
              - elements: parsed UI element list (list[dict], for programmatic use)
              - prompt_representation: JSON string of the full perception payload (for LLM)
              - data: same payload as dict (duplicate for pipelines that read .data)
              - visual_representations: screenshot path(s)
        """
        screenshot_path = perception_input.screenshot_path
        ui_path = perception_input.ui_path

        if not ui_path:
            raise ValueError(
                "PerceptionInput.ui_path is required. "
                "Run adb uiautomator dump + pull outside this class, then pass the XML path."
            )
        if not os.path.isfile(ui_path):
            raise FileNotFoundError(f"UI XML not found: {ui_path}")

        self.logger.info(
            f"Parsing accessibility XML: {os.path.basename(ui_path)} "
            f"(screenshot={os.path.basename(screenshot_path)})"
        )

        width = perception_input.width
        height = perception_input.height
        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
        except Exception as e:
            self.logger.warning(
                f"Could not read screenshot size from {screenshot_path}: {e}"
            )

        try:
            xml_content = load_ui_xml(ui_path)
            raw_elements = parse_hierarchy_xml_to_raw_elements(xml_content)
        except Exception as e:
            self.logger.error(f"Failed to parse UI XML: {e}", exc_info=True)
            return self._empty_result(screenshot_path, ui_path, width, height)

        formatted_elements = format_raw_elements(
            raw_elements,
            width,
            height,
            skip_empty=self.skip_empty_nodes,
        )
        if self.normalize_coordinates_to_1000:
            formatted_elements = apply_coordinate_normalization_to_elements(
                formatted_elements,
                width,
                height,
                scale_max=self.coordinate_scale_max,
            )
        self.logger.info(
            f"Parsed {len(raw_elements)} raw nodes → {len(formatted_elements)} elements"
        )

        coord_meta = self._coordinate_metadata()
        payload = build_perception_json_payload(
            screenshot_path=screenshot_path,
            ui_path=os.path.abspath(ui_path),
            width=width,
            height=height,
            elements=formatted_elements,
            raw_elements=raw_elements,
        )
        payload.update(coord_meta)
        prompt_json = self._get_prompt_context(payload)

        marked_screenshot_path: str | None = None
        if self.draw_marked_screenshot and formatted_elements:
            dir_name = os.path.dirname(screenshot_path) or "."
            base_name = os.path.basename(screenshot_path).rsplit(".", 1)[0]
            marked_path = os.path.join(dir_name, f"{base_name}_a11y.png")
            try:
                marked_screenshot_path = self._draw_marked_screenshot(
                    screenshot_path, marked_path, formatted_elements
                )
            except Exception as e:
                self.logger.warning(f"Could not draw marked screenshot: {e}")

        visual = [screenshot_path]
        if marked_screenshot_path and os.path.isfile(marked_screenshot_path):
            visual.append(marked_screenshot_path)

        return PerceptionResult(
            mode="ally",
            original_screenshot_path=screenshot_path,
            elements=formatted_elements,
            metadata={
                "width": width,
                "height": height,
                "platform": "android",
                "ui_path": os.path.abspath(ui_path),
                "element_count": len(formatted_elements),
                "raw_node_count": len(raw_elements),
                **coord_meta,
            },
            data={
                "accessibility": payload,
                "a11y_raw": raw_elements,
            },
            marked_screenshot_path=marked_screenshot_path,
            prompt_representation=prompt_json,
            visual_representations=visual,
        )

    def _coordinate_metadata(self) -> dict[str, Any]:
        return build_coordinate_metadata(
            normalize_coordinates_to_1000=self.normalize_coordinates_to_1000,
            coordinate_scale_max=self.coordinate_scale_max,
        )

    def _get_prompt_context(self, result: dict[str, Any]) -> str:
        """
        Compact text for the reasoning prompt (coordinate Tap mode uses x/y from Center).

        Full structured payload remains in ``PerceptionResult.data`` for programmatic use.
        """
        elements: list[dict[str, Any]] = result.get("elements") or []
        width = result.get("width", 0)
        height = result.get("height", 0)
        max_lines = 80
        coords_normalized = bool(result.get("coordinates_normalized"))
        scale_max = int(result.get("coordinate_scale_max", COORDINATE_SCALE_MAX))

        # Prefer interactive nodes; stable order by index for LLM grounding.
        ranked = sorted(
            elements,
            key=lambda e: (
                0 if e.get("clickable") else 1,
                0 if (e.get("text") or "").strip() else 1,
                e.get("index", 0),
            ),
        )

        lines = [
            "--- Detected UI Elements (Accessibility / ally) ---",
            f"Screen (device pixels): {width}x{height} | Nodes: {len(elements)} (showing up to {max_lines})",
        ]
        lines.append(
            format_normalized_coordinate_instruction(
                coordinates_normalized=coords_normalized,
                coordinate_scale_max=scale_max,
            )
        )
        lines.append("Format: ID | Text | Center (x, y) | Clickable")
        for e in ranked[:max_lines]:
            coords = e.get("coordinates") or [0, 0]
            clickable = "yes" if e.get("clickable") else "no"
            text = (e.get("text") or "").replace("\n", " ").strip()[:60]
            lines.append(
                f"ID: {e.get('index')} | Text: {text} | Center: {coords} | Clickable: {clickable}"
            )
        if len(elements) > max_lines:
            lines.append(f"... ({len(elements) - max_lines} more elements omitted)")
        return "\n".join(lines)

    def _draw_marked_screenshot(
        self,
        screenshot_path: str,
        marked_path: str,
        elements: list[dict[str, Any]],
    ) -> str:
        with Image.open(screenshot_path).convert("RGB") as img:
            draw = ImageDraw.Draw(img)
            for ele in elements:
                pixel = ele.get("bbox_pixel") or []
                if len(pixel) != 4:
                    continue
                x1, y1, x2, y2 = pixel
                if x2 <= x1 or y2 <= y1:
                    continue
                draw.rectangle([x1, y1, x2, y2], outline="lime", width=2)
            img.save(marked_path)
        return marked_path

    def _empty_result(
        self,
        screenshot_path: str,
        ui_path: str,
        width: int,
        height: int,
    ) -> PerceptionResult:
        coord_meta = self._coordinate_metadata()
        payload = build_perception_json_payload(
            screenshot_path=screenshot_path,
            ui_path=ui_path,
            width=width,
            height=height,
            elements=[],
            raw_elements=[],
        )
        payload.update(coord_meta)
        return PerceptionResult(
            mode="ally",
            original_screenshot_path=screenshot_path,
            elements=[],
            metadata={
                "width": width,
                "height": height,
                "platform": "android",
                "ui_path": ui_path,
                "element_count": 0,
                **coord_meta,
            },
            data={"accessibility": payload, "a11y_raw": []},
            prompt_representation=self._get_prompt_context(payload),
            visual_representations=[screenshot_path] if screenshot_path else [],
        )
