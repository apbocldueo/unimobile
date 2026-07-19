import os
import re
import ast
import io
import requests
import base64
import logging
from PIL import Image

from typing import Any

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionResult, PerceptionInput
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.perception.coordinates import (
    COORDINATE_SCALE_MAX,
    apply_coordinate_normalization_to_elements,
    build_coordinate_metadata,
    format_normalized_coordinate_instruction,
    normalized_coordinate_to_pixel,
    pixel_to_normalized_coordinate,
)
# from zhixing.utils.registry import register_perception

def omniparser_text_to_list(text_result: str) -> list[dict]:
    """Parse the string returned by OmniParser

    Returns:
        _type_: _description_
    """
    if not text_result:
        return []
    lines = [line.strip() for line in text_result.split('\n') if line.strip()]
    dict_list = []
    for line in lines:
        match = re.search(r'\{.*\}', line, re.DOTALL)
        if match:
            dict_str = match.group()
            try:
                item_dict = ast.literal_eval(dict_str)
                dict_list.append(item_dict)
            except (SyntaxError, ValueError) as e:
                print(f"OmniParser Warning Parsing failed：{line}, Error {e}")
    return dict_list

# @register_perception("omniparser_perception")
@PluginRegistry.register(namespace="agent.perception", name="omniparser_perception")
class OmniParserPerception(BasePerception):
    def __init__(
        self,
        url="http://127.0.0.1:10002/process-image",
        box_threshold=0.5,
        iou_threshold=0.5,
        use_paddleocr=False,
        normalize_coordinates_to_1000: bool = True,
        coordinate_scale_max: int = COORDINATE_SCALE_MAX,
        **kwargs,
    ):
        self.url = url
        self.box_threshold = box_threshold
        self.iou_threshold = iou_threshold
        self.use_paddleocr = use_paddleocr
        self.normalize_coordinates_to_1000 = normalize_coordinates_to_1000
        self.coordinate_scale_max = coordinate_scale_max
        super().__init__(**kwargs)
        self.logger.info(
            "OmniParserPerception initialized (URL: %s, Threshold: %s, "
            "normalize_coordinates_to_1000=%s, scale_max=%s)",
            self.url,
            self.box_threshold,
            self.normalize_coordinates_to_1000,
            self.coordinate_scale_max,
        )

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        """Return the PerceptionResult object

        Args:
            perception_input (PerceptionInput): perception_input

        Returns:
            PerceptionResult: PerceptionResult(mode='omniparser', 
                original_screenshot_path='screenshots\\task_1766911506\\AndroidWorld_1\\step_10.png', 
                elements=[
                    {
                        'index': 0, 
                        'text': '美团', 
                        'type': 'text', 
                        'coordinates': [148, 294], 
                        'bbox': [0.06457564234733582, 0.10157545655965805, 0.20940959453582764, 0.1426202356815338]
                    }
                    ...
                ],
                metadata={'width': 1084, 'height': 2412},
                marked_screenshot_path=None,
                data={"omniparser": elements}
        """
        screenshot_path = perception_input.screenshot_path
        self.logger.info(f"Analyzing UI elements via OmniParser: {os.path.basename(screenshot_path)}")

        dir_name = os.path.dirname(screenshot_path)
        base_name = os.path.basename(screenshot_path).rsplit('.', 1)[0]
        # 生成与原图在同一目录下的标注图路径
        marked_path = os.path.join(dir_name, f"{base_name}_omniparser.png")
    
        # width, height = 1080, 2340
        width = perception_input.width
        height = perception_input.height
        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
            self.logger.debug(f"Input image resolution: {width}x{height}")
        except Exception as e:
            self.logger.warning(f"Could not read image header at {screenshot_path}, using input dimensions. Error: {e}")
        
        try:
            self.logger.debug(f"Sending request to OmniParser server: {self.url}")
            files = {"image": open(screenshot_path, "rb")}
            data = {
                "box_threshold": self.box_threshold,
                "iou_threshold": self.iou_threshold,
                "use_paddleocr": self.use_paddleocr,
                "imagsz": (width, height)
            }
            
            response = requests.post(self.url, files=files, data=data)
            result = response.json()
        except Exception as e:
            self.logger.error(f"OmniParser service connection failed: {str(e)}", exc_info=True)
            return self._empty_result(screenshot_path, width, height)
        
        if result.get("code") == 200:
            self.logger.info("OmniParser server returned results successfully.")
            try:
                base64_str = result["data"]["processed_image"]
                img_bytes = base64.b64decode(base64_str)
                with open(marked_path, "wb") as f:
                    f.write(img_bytes)
                self.logger.debug(f"OmniParser debug image saved to {marked_path}")
            except Exception:
                pass

            text_result_str = result["data"]["text_result"]
            raw_list = omniparser_text_to_list(text_result_str)
            
            formatted_elements = []
            for i, item in enumerate(raw_list):
                bbox = item.get('bbox', [0, 0, 0, 0])
                content = item.get('content', 'unknown')
                
                center_x = int(((bbox[0] + bbox[2]) / 2) * width)
                center_y = int(((bbox[1] + bbox[3]) / 2) * height)

                formatted_elements.append({
                    "index": i,
                    "text": content,
                    "type": item.get('type', 'icon'),
                    "coordinates": [center_x, center_y],
                    "bbox": bbox
                })

            self.logger.info(f"OmniParser detected {len(formatted_elements)} UI elements.")

            if self.normalize_coordinates_to_1000:
                formatted_elements = apply_coordinate_normalization_to_elements(
                    formatted_elements,
                    width,
                    height,
                    scale_max=self.coordinate_scale_max,
                )

            coord_meta = self._coordinate_metadata()
            prompt_text = self._get_prompt_context(
                formatted_elements, width, height, coord_meta
            )

            self.logger.debug(f"OmniParser Prompt Context:\n{prompt_text}")

            return PerceptionResult(
                mode="omniparser",
                original_screenshot_path=screenshot_path,
                elements=formatted_elements,
                metadata={"width": width, "height": height, **coord_meta},
                data={"omniparser": formatted_elements, **coord_meta},
                prompt_representation=prompt_text,
                visual_representations=[screenshot_path],
                marked_screenshot_path=marked_path if os.path.isfile(marked_path) else None,
            )
        
        else:
            self.logger.warning(f"OmniParser server error code: {result.get('code')}. Returning empty perception.")
            return self._empty_result(screenshot_path, width, height)

    def _coordinate_metadata(self) -> dict[str, Any]:
        return build_coordinate_metadata(
            normalize_coordinates_to_1000=self.normalize_coordinates_to_1000,
            coordinate_scale_max=self.coordinate_scale_max,
        )

    def _get_prompt_context(
        self,
        elements: list[dict[str, Any]],
        width: int,
        height: int,
        coord_meta: dict[str, Any],
    ) -> str:
        """Generate prompt text for reasoning (Center coords match metadata scale)."""
        coords_normalized = bool(coord_meta.get("coordinates_normalized"))
        scale_max = int(coord_meta.get("coordinate_scale_max", COORDINATE_SCALE_MAX))
        max_lines = 50

        lines = [
            "--- Detected UI Elements (OmniParser) ---",
            f"Screen (device pixels): {width}x{height} | Nodes: {len(elements)} (showing up to {max_lines})",
            format_normalized_coordinate_instruction(
                coordinates_normalized=coords_normalized,
                coordinate_scale_max=scale_max,
                pixel_mode_line=(
                    "Use Tap/Long_press with absolute pixel x,y from the Center column (not element index)."
                ),
            ),
            "Format: ID | Text | Center (x, y)",
        ]
        for e in elements[:max_lines]:
            text = (e.get("text") or "").replace("\n", " ").strip()[:60]
            lines.append(
                f"ID: {e.get('index')} | Text: {text} | Center: {e.get('coordinates')}"
            )
        if len(elements) > max_lines:
            lines.append(f"... ({len(elements) - max_lines} more elements omitted)")
        return "\n".join(lines)

    def _empty_result(self, path, w, h):
        coord_meta = self._coordinate_metadata()
        return PerceptionResult(
            mode="omniparser",
            original_screenshot_path=path,
            elements=[],
            metadata={"width": w, "height": h, **coord_meta},
            data={"omniparser": [], **coord_meta},
            prompt_representation=self._get_prompt_context([], w, h, coord_meta),
            visual_representations=[path] if path else [],
        )


    def _filter(self, perception_input: PerceptionInput, perception_result: PerceptionResult):
        elements = perception_result.elements
        l = len(elements)
        i = 0
        added_count = 0
        width = perception_result.metadata.get("width") or perception_input.width
        height = perception_result.metadata.get("height") or perception_input.height
        coords_normalized = bool(
            perception_result.metadata.get("coordinates_normalized")
        )
        scale_max = int(
            perception_result.metadata.get("coordinate_scale_max", COORDINATE_SCALE_MAX)
        )

        for ele in elements:
            text_val = ele.get('text', '').strip()
            if text_val == "M0,0L9,0 4.5,5z":
                ele['text'] = "search input box"
            elif text_val == "搜索":
                cx, cy = int(ele["coordinates"][0]), int(ele["coordinates"][1])
                if coords_normalized and width > 0 and height > 0:
                    cx, cy = normalized_coordinate_to_pixel(
                        cx, cy, width, height, scale_max=scale_max
                    )
                px = int(cx - perception_input.width / 5)
                py = int(cy)
                if coords_normalized and width > 0 and height > 0:
                    px, py = pixel_to_normalized_coordinate(
                        px, py, width, height, scale_max=scale_max
                    )
                insert_item = {
                    'index': l + i,
                    'text': 'search input box',
                    'type': 'text',
                    'coordinates': [px, py],
                    'bbox': [],
                }
                elements.insert(l+i, insert_item)
                i += 1
                added_count += 1

        if added_count > 0:
            self.logger.debug(f"Filter applied: Adjusted/Added {added_count} elements in OmniParser results.")

        return perception_result