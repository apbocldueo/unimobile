import re
import time
import subprocess
from typing import List, Tuple, Optional, Union

from unimobile.devices.base import BaseDevice, DeviceInfo, ConnectionType, CommandResult, _execute_command, KeyCodeAndroid, SwipeDirection
from unimobile.utils.registry import register_device
from unimobile.config.timing import TIMING_CONFIG

@register_device("android_action")
class AndroidDevice(BaseDevice):
    def __init__(self, device_id: str = None):
        super().__init__(device_id)
        
        if not self.serial:
            devices = self.list_devices()
            if not devices:
                raise RuntimeError("No connected Android device was found. Please check the ADB connection")
            self.serial = devices[0].device_id
            print(f"Android automatic binding device: {self.serial}")

        self.w, self.h = self.display_size()

    def _adb_prefix(self) -> str:
        return f"adb -s {self.serial}" if self.serial else "adb"

    @classmethod
    def list_devices(cls) -> List[DeviceInfo]:
        try:
            result = _execute_command("adb devices -l")
            if result.exit_code != 0:
                return []

            devices = []
            lines = result.output.strip().split("\n")[1:]
            
            for line in lines:
                if not line.strip(): continue
                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status = parts[1]
                    
                    if "emulator" in device_id:
                        conn_type = ConnectionType.EMULATOR
                    elif ":" in device_id:
                        conn_type = ConnectionType.REMOTE
                    else:
                        conn_type = ConnectionType.USB
                    
                    model = "Unknown"
                    for p in parts:
                        if p.startswith("model:"):
                            model = p.split(":")[1]
                    
                    devices.append(DeviceInfo(
                        device_id=device_id,
                        platform="android",
                        status=status,
                        connection_type=conn_type,
                        model=model
                    ))
            return devices
        except Exception as e:
            print(f"Error listing android devices: {e}")
            return []

    def display_size(self) -> Tuple[int, int]:
        res = self.shell("wm size")
        match = re.search(r'Physical size: (\d+)x(\d+)', res.output)
        if match:
            return int(match.group(1)), int(match.group(2))
        return 1080, 2340

    def screenshot(self, path: str, method: str = "screencap") -> str:
        remote_path = "/sdcard/temp_screenshot.png"
        self.shell(f"screencap -p {remote_path}")
        
        cmd = f"{self._adb_prefix()} pull {remote_path} {path}"
        _execute_command(cmd)
        
        return path

    def shell(self, cmd: str, error_raise=True) -> CommandResult:
        full_cmd = f"{self._adb_prefix()} shell \"{cmd}\""
        return _execute_command(full_cmd)

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {x} {y}")
        time.sleep(TIMING_CONFIG.device.default_tap_delay)

    def swipe(self, direction: Union[SwipeDirection, str], scale: float = 0.8, box=None, speed=1600):
        if isinstance(direction, str):
            direction = direction.lower()
        
        w, h = self.w, self.h
        
        h_offset = int(w * (1 - scale) / 2)
        v_offset = int(h * (1 - scale) / 2)
        
        x1, y1, x2, y2 = 0, 0, 0, 0

        if direction == SwipeDirection.LEFT or direction == "left":
            x1, y1 = w - h_offset, h // 2
            x2, y2 = h_offset, h // 2
        elif direction == SwipeDirection.RIGHT or direction == "right":
            x1, y1 = h_offset, h // 2
            x2, y2 = w - h_offset, h // 2
        elif direction == SwipeDirection.UP or direction == "up":
            x1, y1 = w // 2, h - v_offset
            x2, y2 = w // 2, v_offset
        elif direction == SwipeDirection.DOWN or direction == "down":
            x1, y1 = w // 2, v_offset
            x2, y2 = w // 2, h - v_offset
        
        duration = 500
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration}")
        time.sleep(TIMING_CONFIG.device.default_swipe_delay)

    def input_text(self, text: str):
        safe_text = text.replace(" ", "%s").replace("'", "")
        self.shell(f"input text '{safe_text}'")
        time.sleep(TIMING_CONFIG.action.text_input_delay)

    def clear_text(self, num: int = 15) -> None:
        cmd = f"input keyevent {KeyCodeAndroid.DEL.value}"
        full_cmd = ";".join([cmd] * num)
        self.shell(full_cmd)
        time.sleep(TIMING_CONFIG.action.text_clear_delay)

    def go_home(self):
        self.shell(f"input keyevent {KeyCodeAndroid.HOME.value}")
        time.sleep(TIMING_CONFIG.device.default_home_delay)

    def go_back(self):
        self.shell(f"input keyevent {KeyCodeAndroid.BACK.value}")
        time.sleep(TIMING_CONFIG.device.default_back_delay)

    def enter(self):
        self.shell(f"input keyevent {KeyCodeAndroid.ENTER.value}")

    def get_app(self) -> List[str]:
        res = self.shell("pm list packages")
        packages = []
        for line in res.output.splitlines():
            if line.startswith("package:"):
                packages.append(line.replace("package:", "").strip())
        return packages
    
    def launch_app(self, package_name: str, delay: float = None):
        if delay is None:
            delay = TIMING_CONFIG.device.default_launch_delay
        
        self.shell(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        time.sleep(delay)