import cv2
import os
import numpy as np
from typing import Tuple
from unimobile.core.interfaces import BasePerception
from unimobile.core.protocol import PerceptionResult, PerceptionInput
from unimobile.utils.registry import register_perception

@register_perception("grid")
class GridPerception(BasePerception):
    def __init__(self, **kwargs):
        pass

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        screenshot_path = perception_input.screenshot_path

        dir_name = os.path.dirname(screenshot_path)
        base_name = os.path.basename(screenshot_path).split('.')[0]
        marked_path = os.path.join(dir_name, f"{base_name}_grid.png")
        
        # draw grid
        rows, cols = self._draw_grid(screenshot_path, marked_path)
        
        img = cv2.imread(screenshot_path)
        if img is None:
            h, w = 2340, 1080 
        else:
            h, w = img.shape[:2]
        
        result = PerceptionResult(
            mode="grid",
            original_screenshot_path=screenshot_path,
            marked_screenshot_path=marked_path,
            elements=[],
            metadata={"width": w, "height": h, "rows": rows, "cols": cols},
            visual_representations=[marked_path]
        )
        
        result.prompt_representation = self._get_prompt_context(result)
    
        return result

    def _get_prompt_context(self, result: PerceptionResult) -> str:
        """
        Generate a Prompt description dedicated to the Grid mode
        """
        rows = result.metadata.get("rows", 0)
        cols = result.metadata.get("cols", 0)
        
        prompt = "--- Grid Overlay View ---\n"
        prompt += f"The image is overlaid with a {rows}x{cols} grid.\n"
        prompt += "Each cell has a numeric ID. You can tap a cell by outputting its ID (area).\n"
        
        return prompt

    def _draw_grid(self, img_path, output_path) -> Tuple[int, int]:
        def get_unit_len(n):
            for i in range(1, n + 1):
                if n % i == 0 and 120 <= i <= 180:
                    return i
            return -1

        image = cv2.imread(img_path)
        if image is None:
            return 0, 0
            
        height, width, _ = image.shape
        color = (255, 116, 113)
        
        unit_height = get_unit_len(height)
        if unit_height < 0: unit_height = 120
        
        unit_width = get_unit_len(width)
        if unit_width < 0: unit_width = 120
            
        thick = int(unit_width // 50)
        rows = height // unit_height
        cols = width // unit_width
        
        for i in range(rows):
            for j in range(cols):
                label = i * cols + j + 1
                left = int(j * unit_width)
                top = int(i * unit_height)
                right = int((j + 1) * unit_width)
                bottom = int((i + 1) * unit_height)
                cv2.rectangle(image, (left, top), (right, bottom), color, thick // 2)
                
                text_pos = (left + int(unit_width * 0.05) + 3, top + int(unit_height * 0.3) + 3)
                cv2.putText(image, str(label), text_pos, 0, int(0.01 * unit_width), (0, 0, 0), thick)
                
                text_pos_2 = (left + int(unit_width * 0.05), top + int(unit_height * 0.3))
                cv2.putText(image, str(label), text_pos_2, 0, int(0.01 * unit_width), color, thick)
                
        cv2.imwrite(output_path, image)
        return rows, cols