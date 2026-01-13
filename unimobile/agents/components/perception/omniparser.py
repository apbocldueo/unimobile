import re
import ast
import io
import requests
import base64
import logging
from PIL import Image

from unimobile.core.interfaces import BasePerception
from unimobile.core.protocol import PerceptionResult, PerceptionInput
from unimobile.utils.registry import register_perception

logger = logging.getLogger(__name__)

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

@register_perception("omniparser")
class OmniParserPerception(BasePerception):
    def __init__(self, url, box_threshold=0.5, iou_threshold=0.5, use_paddleocr=False):
        self.url = url
        self.box_threshold = box_threshold
        self.iou_threshold = iou_threshold
        self.use_paddleocr = use_paddleocr

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        """Return the PerceptionResult object

        Args:
            perception_input (PerceptionInput): perception_input

        Returns:
            PerceptionResult: PerceptionResult(mode='omniparser', 
                original_screenshot_path='screenshots\\task_1766911506_step_10.png', 
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
        logger.info("#### OmniParserPerception ####")
        # width, height = 1080, 2340
        width = perception_input.width
        height = perception_input.height
        try:
            with Image.open(screenshot_path) as img:
                width, height = img.size
        except Exception as e:
            print(f"Failed to read the local screenshot: {e}")
        
        print(f"OmniParser width, height is: ({width}, {height})")

        try:
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
            print(f"OmniParser network error: {e}")
            return self._empty_result(screenshot_path, width, height)
        

        if result.get("code") == 200:
            print("OmniParser Request successful!")
            
            try:
                base64_str = result["data"]["processed_image"]
                img_bytes = base64.b64decode(base64_str)
                with open("temp/screenshots/last_omniparser_debug.png", "wb") as f:
                    f.write(img_bytes)
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

            print(f"OmniParser get {len(formatted_elements)} UI")
            
            prompt_text = self._get_prompt_context(formatted_elements)

            return PerceptionResult(
                mode="omniparser",
                original_screenshot_path=screenshot_path,
                elements=formatted_elements,
                metadata={"width": width, "height": height},
                
                prompt_representation=prompt_text,
                visual_representations=[screenshot_path]
            )
        
        else:
            print(f"OmniParser Server Error: {result}")
            return self._empty_result(screenshot_path, width, height)

    def _get_prompt_context(self, result: list) -> str:
        """
        Generate a Prompt based on formatted_elements
        """
        elements = result
        
        prompt = "--- Detected UI Elements (OmniParser) ---\n"
        prompt += "Format: ID | Text | Center Coordinates\n"
        
        for e in elements[:50]:
            prompt += f"ID: {e['index']} | Text: {e['text']} | Center: {e['coordinates']}\n"

        return prompt

    def _empty_result(self, path, w, h):
        return PerceptionResult(
            mode="omniparser",
            original_screenshot_path=path,
            elements=[],
            metadata={"width": w, "height": h}
        )
