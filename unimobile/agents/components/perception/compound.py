from typing import Dict
from unimobile.core.interfaces import BasePerception
from unimobile.core.protocol import PerceptionResult

class CompoundPerception(BasePerception):
    def __init__(self, perceptions: Dict[str, BasePerception]):
        self.children = perceptions

    def perceive(self, screenshot_path: str) -> PerceptionResult:
        final_result = PerceptionResult(
            mode="composite",
            original_screenshot_path=screenshot_path
        )
        
        for name, p_instance in self.children.items():
            
            sub_res = p_instance.perceive(screenshot_path)
            
            if final_result.width == 0:
                final_result.width = sub_res.get("width", 0)
                final_result.height = sub_res.get("height", 0)

            if sub_res.get("marked_screenshot_path"):
                final_result.marked_images[name] = sub_res["marked_screenshot_path"]

            if sub_res.get("elements"):
                final_result.data[name] = sub_res["elements"]

        return final_result