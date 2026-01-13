import os
from typing import Tuple, List, Union
from PIL import Image

from unimobile.devices.base import BaseDevice, CommandResult, SwipeDirection
from unimobile.utils.registry import register_device

@register_device("mock")
class MockDevice(BaseDevice):
    def __init__(self):
        super().__init__()
        self.w = 1080
        self.h = 2340
        print("MockDevice: The virtual device has been started (1080x2340)")

    def display_size(self) -> Tuple[int, int]:
        return (self.w, self.h)

    def screenshot(self, path: str, method: str = "snapshot_display") -> str:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        try:
            img = Image.new('RGB', (self.w, self.h), color='white')
            img.save(path)
            print(f"MockDevice: The fake screenshot has been saved: {path}")
        except Exception as e:
            print(f"MockDevice Image generation failed: {e}")
            with open(path, 'wb') as f:
                f.write(b'\x00' * 100)

        return path

    def shell(self, cmd: str, error_raise=True) -> CommandResult:
        return CommandResult(output="mock output", error="", exit_code=0)

    def tap(self, x: int, y: int) -> None:
        print(f"MockDevice: Tap: ({x}, {y})")

    def swipe(self, direction: Union[SwipeDirection, str], scale: float = 0.8, box=None, speed=1600):
        print(f"MockDevice: Swipe: {direction}, Scale: {scale}")

    def input_text(self, text: str):
        print(f"MockDevice: Input Text: '{text}'")

    def clear_text(self, num: int = 15) -> None:
        print(f"MockDevice: Clear Text {num}")

    def go_home(self):
        print("MockDevice: Press Home")

    def go_back(self):
        print("MockDevice: Press Back")

    def enter(self):
        print("MockDevice: Press Enter ")

    def get_app(self) -> List[str]:
        return ["com.tencent.mm", "com.android.settings"]