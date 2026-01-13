from typing import Dict, Any
from unimobile.core.interfaces import BasePerception
from unimobile.core.protocol import PerceptionResult # <--- 引入协议对象
from unimobile.utils.registry import register_perception

@register_perception("mock_perception")
class MockPerception(BasePerception):
    def perceive(self, screenshot_path: str) -> PerceptionResult:
        print(f"🙈 [MockPerception] 假装正在分析截图: {screenshot_path}")
        
        elements = [
            {"index": 0, "text": "微信", "type": "icon", "coordinates": [100, 200], "bbox": [0.1, 0.1, 0.2, 0.2]},
            {"index": 1, "text": "通讯录", "type": "icon", "coordinates": [500, 200], "bbox": [0.4, 0.1, 0.5, 0.2]},
            {"index": 2, "text": "发现", "type": "icon", "coordinates": [900, 200], "bbox": [0.8, 0.1, 0.9, 0.2]},
            {"index": 3, "text": "搜索框", "type": "text", "coordinates": [500, 100], "bbox": [0.2, 0.05, 0.8, 0.1]}
        ]

        return PerceptionResult(
            mode="omniparser",
            original_screenshot_path=screenshot_path,
            elements=elements,
            metadata={"width": 1080, "height": 2340},
            data={"omniparser": elements}
        )

    def get_prompt_context(self, result: PerceptionResult) -> str:
        return "Mock Data Ready."

    def parse_action_params(self, raw_params):
        return raw_params