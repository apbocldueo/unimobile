import logging
from typing import Any
from unimobile.core.interfaces import BasePerception
from unimobile.core.protocol import PerceptionResult, PerceptionInput
from unimobile.utils.registry import register_perception

logger = logging.getLogger(__name__)

@register_perception("example_preception")
class ExamplePerception(BasePerception):

    def __init__(self) -> None:
        super().__init__()

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        """Perception core: 

        Args:
            perception_input (PerceptionInput): _description_

        Returns:
            PerceptionResult: _description_
        """
        logger.info(f"[ExamplePreception] pretend to analying screenshot: {perception_input.screenshot_path}")
        
        # False Data
        elements = [
            {"index": 0, "text": "微信", "type": "icon", "coordinates": [100, 200], "bbox": [0.1, 0.1, 0.2, 0.2]},
            {"index": 1, "text": "通讯录", "type": "icon", "coordinates": [500, 200], "bbox": [0.4, 0.1, 0.5, 0.2]},
            {"index": 2, "text": "发现", "type": "icon", "coordinates": [900, 200], "bbox": [0.8, 0.1, 0.9, 0.2]},
            {"index": 3, "text": "搜索框", "type": "text", "coordinates": [500, 100], "bbox": [0.2, 0.05, 0.8, 0.1]}
        ]

        prompt_text = self._get_prompt_context(elements)

        return PerceptionResult(
            mode="example",
            original_screenshot_path=perception_input.screenshot_path,
            elements=elements,
            metadata={"width": 1080, "height": 2340},
            prompt_representation=prompt_text,
            data={"example": elements},
            visual_representations=[perception_input.screenshot_path]
        )
    
    def _get_prompt_context(self, result: Any) -> str:
        elements = result
        
        prompt = "--- Detected UI Elements (OmniParser) ---\n"
        prompt += "Format: ID | Text | Center Coordinates\n"
        
        for e in elements:
            prompt += f"ID: {e['index']} | {e['type']}: {e['text']} | Center: {e['coordinates']}\n"

        return prompt
