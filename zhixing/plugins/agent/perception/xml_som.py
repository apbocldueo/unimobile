from __future__ import annotations

import ast
import os
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionInput, PerceptionResult
from zhixing.core.factory import PluginRegistry

_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


@dataclass
class _UiElement:
    uid: str
    bbox: tuple[int, int, int, int]
    attrib_kind: str
    raw: dict[str, str]


def _parse_bounds(bounds: str | None) -> tuple[int, int, int, int] | None:
    if not bounds:
        return None
    match = _BOUNDS_RE.match(bounds.strip())
    if not match:
        return None
    return tuple(int(match.group(i)) for i in range(1, 5))  # type: ignore[return-value]


def _element_uid(elem: ET.Element) -> str:
    bbox = _parse_bounds(elem.attrib.get("bounds")) or (0, 0, 0, 0)
    elem_w, elem_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    if elem.attrib.get("resource-id"):
        elem_id = elem.attrib["resource-id"].replace(":", ".").replace("/", "_")
    else:
        elem_id = f"{elem.attrib.get('class', 'node')}_{elem_w}_{elem_h}"

    content_desc = elem.attrib.get("content-desc", "")
    if content_desc and len(content_desc) < 20:
        elem_id += "_" + content_desc.replace("/", "_").replace(" ", "").replace(":", "_")
    return elem_id


def _traverse_tree(xml_path: str, attrib: str, min_dist: int, add_index: bool = True) -> list[_UiElement]:
    elements: list[_UiElement] = []
    path: list[ET.Element] = []

    for event, elem in ET.iterparse(xml_path, ["start", "end"]):
        if event == "start":
            path.append(elem)
            if elem.attrib.get(attrib) != "true":
                continue

            bbox = _parse_bounds(elem.attrib.get("bounds"))
            if not bbox:
                continue

            x1, y1, x2, y2 = bbox
            center = ((x1 + x2) // 2, (y1 + y2) // 2)
            parent_prefix = _element_uid(path[-2]) if len(path) > 1 else ""
            uid = _element_uid(elem)
            if parent_prefix:
                uid = parent_prefix + "_" + uid
            if add_index:
                uid += f"_{elem.attrib.get('index', '0')}"

            if _is_close_to_existing(center, elements, min_dist):
                continue

            elements.append(_UiElement(uid=uid, bbox=bbox, attrib_kind=attrib, raw=dict(elem.attrib)))

        elif event == "end":
            path.pop()

    return elements


def _is_close_to_existing(center: tuple[int, int], elements: list[_UiElement], min_dist: int) -> bool:
    for elem in elements:
        x1, y1, x2, y2 = elem.bbox
        elem_center = ((x1 + x2) // 2, (y1 + y2) // 2)
        dist = ((center[0] - elem_center[0]) ** 2 + (center[1] - elem_center[1]) ** 2) ** 0.5
        if dist <= min_dist:
            return True
    return False


@PluginRegistry.register(namespace="agent.perception", name="xml_som_perception")
class XmlSomPerception(BasePerception):
    """AppAgent-style SoM perception from Android UIAutomator XML.

    It labels clickable/focusable nodes directly from the XML tree and returns
    mode="appagent_som", matching parsers that use numeric UI tags.
    """

    mode_name = "appagent_som"

    def __init__(
        self,
        min_dist: int = 30,
        dark_mode: bool = False,
        docs_dir: str = "",
        max_elements: int = 80,
        **kwargs: Any,
    ) -> None:
        self.min_dist = min_dist
        self.dark_mode = dark_mode
        self.docs_dir = docs_dir
        self.max_elements = max_elements
        super().__init__(**kwargs)

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        screenshot_path = perception_input.screenshot_path
        ui_path = perception_input.ui_path
        if not ui_path:
            raise ValueError("XmlSomPerception requires PerceptionInput.ui_path")
        if not os.path.isfile(ui_path):
            raise FileNotFoundError(f"UI XML not found: {ui_path}")

        clickable = _traverse_tree(ui_path, "clickable", self.min_dist)
        focusable = _traverse_tree(ui_path, "focusable", self.min_dist)
        merged = clickable.copy()
        for elem in focusable:
            x1, y1, x2, y2 = elem.bbox
            center = ((x1 + x2) // 2, (y1 + y2) // 2)
            if not _is_close_to_existing(center, clickable, self.min_dist):
                merged.append(elem)

        merged = merged[: self.max_elements]
        width, height = perception_input.width, perception_input.height
        marked_path = self._draw_labels(screenshot_path, merged)
        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
        except Exception:
            pass

        elements = []
        for idx, elem in enumerate(merged, start=1):
            x1, y1, x2, y2 = elem.bbox
            raw = elem.raw
            text = (
                raw.get("text", "").strip()
                or raw.get("content-desc", "").strip()
                or raw.get("class", "node").split(".")[-1]
            )
            elements.append(
                {
                    "index": idx,
                    "uid": elem.uid,
                    "text": text,
                    "type": raw.get("class", "node").split(".")[-1],
                    "coordinates": [(x1 + x2) // 2, (y1 + y2) // 2],
                    "bbox_pixel": [x1, y1, x2, y2],
                    "bounds": raw.get("bounds", ""),
                    "resource-id": raw.get("resource-id", ""),
                    "clickable": raw.get("clickable") == "true",
                    "focusable": raw.get("focusable") == "true",
                    "long-clickable": raw.get("long-clickable") == "true",
                    "enabled": raw.get("enabled", "true") == "true",
                }
            )

        prompt = self._get_prompt_context(elements)
        return PerceptionResult(
            mode=self.mode_name,
            original_screenshot_path=screenshot_path,
            elements=elements,
            metadata={"width": width, "height": height},
            marked_screenshot_path=marked_path,
            visual_representations=[marked_path],
            prompt_representation=prompt,
            data={"elements": elements},
        )

    def _draw_labels(self, screenshot_path: str, elements: list[_UiElement]) -> str:
        dir_name = os.path.dirname(screenshot_path)
        base_name = os.path.splitext(os.path.basename(screenshot_path))[0]
        marked_path = os.path.join(dir_name, f"{base_name}_xml_som.png")
        try:
            image = Image.open(screenshot_path).convert("RGB")
        except Exception:
            return screenshot_path

        draw = ImageDraw.Draw(image, "RGBA")
        font = ImageFont.load_default()
        text_color = (10, 10, 10, 255) if self.dark_mode else (255, 250, 250, 255)
        bg_color = (255, 250, 250, 180) if self.dark_mode else (10, 10, 10, 180)
        outline = (255, 116, 113, 230)

        for idx, elem in enumerate(elements, start=1):
            x1, y1, x2, y2 = elem.bbox
            draw.rectangle([x1, y1, x2, y2], outline=outline, width=3)
            label = str(idx)
            label_x = (x1 + x2) // 2 + 8
            label_y = (y1 + y2) // 2 + 8
            text_box = draw.textbbox((label_x, label_y), label, font=font)
            pad = 5
            draw.rounded_rectangle(
                [text_box[0] - pad, text_box[1] - pad, text_box[2] + pad, text_box[3] + pad],
                radius=4,
                fill=bg_color,
            )
            draw.text((label_x, label_y), label, fill=text_color, font=font)

        image.save(marked_path)
        return marked_path

    def _get_prompt_context(self, elements: list[dict[str, Any]]) -> str:
        lines = [
            "The attached image is labeled with numeric tags for clickable and focusable UI elements.",
            "Use tap(<tag>), long_press(<tag>), swipe(<tag>, \"up|down|left|right\", \"short|medium|long\"), text(\"...\") or grid.",
            "If the numeric element tags are not sufficient for precise targeting, output Action: grid.",
            "",
            "Interactive elements:",
        ]

        for elem in elements:
            flags = []
            if elem.get("clickable"):
                flags.append("clickable")
            if elem.get("focusable"):
                flags.append("focusable")
            if elem.get("long-clickable"):
                flags.append("long-clickable")
            flag_text = ", ".join(flags) or "interactive"
            rid = elem.get("resource-id") or ""
            rid_text = f" resource-id={rid}" if rid else ""
            lines.append(
                f"- {elem['index']}: {elem.get('text', '')} ({elem.get('type', 'node')}; {flag_text}; "
                f"center={elem.get('coordinates')}{rid_text})"
            )

        docs = self._build_ui_docs(elements)
        if docs:
            lines.extend(["", docs])
        return "\n".join(lines)

    def _build_ui_docs(self, elements: list[dict[str, Any]]) -> str:
        if not self.docs_dir or not os.path.isdir(self.docs_dir):
            return ""

        ui_doc = ""
        for elem in elements:
            doc_path = os.path.join(self.docs_dir, f"{elem.get('uid', '')}.txt")
            if not os.path.exists(doc_path):
                continue
            try:
                doc_content = ast.literal_eval(open(doc_path, encoding="utf-8").read())
            except Exception:
                continue

            ui_doc += f"Documentation of UI element labeled with the numeric tag '{elem['index']}':\n"
            if doc_content.get("tap"):
                ui_doc += f"This UI element is clickable. {doc_content['tap']}\n\n"
            if doc_content.get("text"):
                ui_doc += (
                    "This UI element can receive text input. The text input is used for the "
                    f"following purposes: {doc_content['text']}\n\n"
                )
            if doc_content.get("long_press"):
                ui_doc += f"This UI element is long clickable. {doc_content['long_press']}\n\n"
            if doc_content.get("v_swipe"):
                ui_doc += (
                    "This element can be swiped directly without tapping. You can swipe vertically "
                    f"on this UI element. {doc_content['v_swipe']}\n\n"
                )
            if doc_content.get("h_swipe"):
                ui_doc += (
                    "This element can be swiped directly without tapping. You can swipe horizontally "
                    f"on this UI element. {doc_content['h_swipe']}\n\n"
                )

        if not ui_doc:
            return ""
        return (
            "You also have access to the following documentations that describe the "
            "functionalities of UI elements you can interact with on the screen. "
            "Prioritize these documented elements for interaction:\n"
            + ui_doc
        )
