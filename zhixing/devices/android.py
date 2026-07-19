import os
import re
import time
import subprocess
import uuid
import xml.etree.ElementTree as ET
from typing import List, Dict, Any
from typing import List, Tuple, Optional, Union

import logging

from zhixing.devices.base import BaseDevice, DeviceInfo, ConnectionType, CommandResult, _execute_command, KeyCodeAndroid, SwipeDirection
# from zhixing.utils.registry import register_device
from zhixing.core.factory import PluginRegistry
from zhixing.config.timing import TIMING_CONFIG

_log = logging.getLogger(__name__)

# Canonical short-name → package map (keep in sync with agent prompts via `ANDROID_APP_PACKAGE_NAMES`).
ANDROID_APP_PACKAGE_NAMES: dict[str, str] = {
    "broccoli": "com.flauschcode.broccoli",
    "clock": "com.android.deskclock",
    "contacts": "com.android.contacts",
    "calendar": "com.simplemobiletools.calendar.pro",
    "chrome": "com.android.chrome",
    "camera": "com.android.camera2",
    "photos": "com.google.android.apps.photos",
    "files": "com.android.documentsui",
    "file manager": "com.android.documentsui",
    "joplin": "net.cozic.joplin",
    "myrecorder": "myrecorder.voicerecorder.voicememos.audiorecorder.recordingapp",
    "messages": "com.google.android.apps.messaging",
    "maps": "com.google.android.apps.maps",
    "gmail": "com.google.android.gm",
    "retromusic": "code.name.monkey.retromusic",
    "osmand": "net.osmand",
    "x": "com.twitter.android",
    "tiktok": "com.zhiliaoapp.musically",
    "espn": "com.espn.score_center",
    "yelp": "com.yelp.android",
    "youtube": "com.google.android.youtube",
    "markor": "net.gsantner.markor",
    "settings": "com.android.settings",
    "audio recorder": "com.dimowner.audiorecorder",
    "pro expense": "com.arduia.expense",
    "arduia pro": "com.arduia.expense",
    "arduia pro expense": "com.arduia.expense",
    "booking.com": "com.booking",
    "vlc": "org.videolan.vlc",
    "simple calendar pro": "com.simplemobiletools.calendar.pro",
    "simple gallery pro": "com.simplemobiletools.gallery.pro",
    "opentracks": "de.dennisguse.opentracks",
    "activity tracker": "de.dennisguse.opentracks",
    "tasks": "org.tasks",
    "telegram": "org.telegram.messenger",
    "temu": "com.einnovation.temu",
    "spotify": "com.spotify.music",
}


@PluginRegistry.register(namespace="device", name="android")
class AndroidDevice(BaseDevice):
    def __init__(self, serial: str = None, language: str = "cn"):
        super().__init__(serial, language)
        
        if not self.serial:
            devices = self.list_devices()
            if not devices:
                raise RuntimeError(
                    "No Android device in the 'device' state was found (adb devices). "
                    "Connect the phone, enable USB debugging, authorize this PC, or fix the serial in config."
                )
            self.serial = devices[0].device_id
            _log.info("No serial in config; auto-selected first adb device serial=%s", self.serial)

        self._assert_target_device_ready()

        self.app_package_names = dict(ANDROID_APP_PACKAGE_NAMES)

        self.w, self.h = self.display_size()

    def _assert_target_device_ready(self) -> None:
        """Fail fast when YAML/secrets pin a serial that is offline, missing, or unauthorized."""
        result = _execute_command(["adb", "-s", self.serial, "get-state"])
        state = (result.output or "").strip().lower()
        if result.exit_code != 0 or state != "device":
            raise RuntimeError(
                f"Android device serial={self.serial!r} is not reachable via ADB "
                f"(get-state={state!r}, exit_code={result.exit_code}). "
                "Connect the device, run `adb devices`, and ensure status is 'device'."
            )

    def _adb_prefix(self) -> str:
        return " ".join(self._adb_cmd())

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
                    if status != "device":
                        continue
                    
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
        """Capture screen to a local file without leaving images on shared storage."""
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        if self._screenshot_via_exec_out(path):
            return path
        self._screenshot_via_device_tmp(path)
        return path

    def _screenshot_via_exec_out(self, path: str) -> bool:
        """Stream PNG over adb exec-out (no file written on the device)."""
        cmd = [*self._adb_cmd(), "exec-out", "screencap", "-p"]
        try:
            with open(path, "wb") as out:
                result = subprocess.run(cmd, stdout=out, stderr=subprocess.PIPE, check=False)
            if result.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) < 64:
                return False
            return True
        except OSError:
            return False

    def _screenshot_via_device_tmp(self, path: str) -> None:
        """Fallback: write under /data/local/tmp, pull, then delete (not MediaStore-visible)."""
        remote_path = f"/data/local/tmp/zhixing_screenshot_{uuid.uuid4().hex}.png"
        try:
            cap = self.shell(f"screencap -p {remote_path}", error_raise=False)
            if cap.exit_code != 0:
                raise RuntimeError(f"screencap failed: {cap.error or cap.output}")
            pull = self.pull(remote_path, path, error_raise=False)
            if pull.exit_code != 0 or not os.path.isfile(path):
                raise RuntimeError(f"adb pull failed: {pull.error or pull.output}")
        finally:
            self.shell(f"rm -f {remote_path}", error_raise=False)
        # Legacy path from older builds; remove so gallery/tasks are not affected.
        self.shell("rm -f /sdcard/temp_screenshot.png", error_raise=False)

    def _adb_cmd(self) -> List[str]:
        return ["adb", "-s", self.serial] if self.serial else ["adb"]

    def shell(self, cmd: str, error_raise=True) -> CommandResult:
        full_cmd = f"{self._adb_prefix()} shell \"{cmd}\""
        return _execute_command(full_cmd)
    
    def pull(self, remote_path: str, local_path: str, error_raise=True) -> CommandResult:
        full_cmd = f"{self._adb_prefix()} pull {remote_path} {local_path}"
        return _execute_command(full_cmd)

    def tap(self, x: int, y: int) -> None:
        self.shell(f"input tap {x} {y}")
        time.sleep(TIMING_CONFIG.device.default_tap_delay)

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        """Long-press via swipe from (x,y) to (x,y) with duration (ms)."""
        d = max(300, min(int(duration_ms), 5000))
        self.shell(f"input swipe {x} {y} {x} {y} {d}")
        time.sleep(TIMING_CONFIG.device.default_long_press_delay)

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

    def wait(self, seconds: float = 2.0) -> None:
        """Wait for UI/network loading without touching the screen."""
        duration = max(1.5, min(float(seconds), 30.0))
        _log.debug("wait %.1fs", duration)
        time.sleep(duration)

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

    def get_xml(self, xml_path: str) -> str:
        """
        Dump UI hierarchy to device, pull to xml_path on host.
        Returns the XML string (and writes to xml_path).
        """
        xml_path = os.path.abspath(xml_path)
        os.makedirs(os.path.dirname(xml_path) or ".", exist_ok=True)

        remote = f"/sdcard/ui_dump_{self.serial}.xml"  # 或 tempfile 名
        dump_command = f"adb -s {self.serial} shell uiautomator dump {remote}"
        pull_command = f"adb -s {self.serial} pull {remote} {xml_path}"

        _execute_command(dump_command)
        _execute_command(pull_command)

        with open(xml_path, encoding="utf-8") as f:
            return f.read()
    
    def start_app(self, app: str, page: str=""):
        """Start an application by app name"""
        package_name = self.app_package_names.get(app.lower())
        if not package_name:
            package_name = app
        
        if page:
            result = self.shell(f"am start -n {package_name}/{page}")
        else:
            result = self.shell(f"monkey -p {package_name} -c android.intent.category.LAUNCHER 1")
        time.sleep(1)
        return result

    def push_file(self, local_path: str, remote_path: str) -> bool:
        """
        将本地文件推送到安卓设备指定路径（适配类内逻辑，替代原push_file_to_android函数）
        Args:
            local_path: 本地文件绝对路径（如 "/Users/xxx/task.html"）
            remote_path: 安卓设备目标路径（如 "/sdcard/Download/task.html"）
        Returns:
            bool: 推送成功返回True，失败返回False
        """
        try:
            # 1. 检查本地文件是否存在
            if not os.path.exists(local_path):
                return False
            
            # 2. 构建ADB推送命令（复用类的_adb_prefix处理设备ID）
            push_cmd = f"{self._adb_prefix()} push {local_path} {remote_path}"
            
            # 3. 执行推送命令（复用_execute_command保持和类内其他命令一致的执行方式）
            result = _execute_command(push_cmd)
            
            # 4. 检查执行结果
            if result.exit_code == 0:
                return True
            else:
                return False
        except Exception as e:
            return False
    
    def extract_android_ui_elements(self) -> List[Dict[str, Any]]:
        """
        Extract UI elements from an Android device using uiautomator dump.

        Returns structured UI elements including text, content-desc,
        resource-id, bounds and center coordinates.
        """
        import tempfile

        fd, xml_path = tempfile.mkstemp(suffix=".xml", prefix="ui_dump_")
        os.close(fd)
        try:
            self.get_xml(xml_path)
            tree = ET.parse(xml_path)
            root = tree.getroot()
        finally:
            try:
                os.remove(xml_path)
            except OSError:
                pass

        elements: List[Dict[str, Any]] = []
        for idx, node in enumerate(root.iter("node")):
            text = node.attrib.get("text", "")
            content_desc = node.attrib.get("content-desc", "")
            resource_id = node.attrib.get("resource-id", "")
            class_name = node.attrib.get("class", "")
            clickable = node.attrib.get("clickable", "false")
            bounds = node.attrib.get("bounds", "")

            match = re.findall(r"\d+", bounds)
            if len(match) == 4:
                x1, y1, x2, y2 = map(int, match)
                center_x = (x1 + x2) // 2
                center_y = (y1 + y2) // 2
            else:
                x1 = y1 = x2 = y2 = center_x = center_y = None

            label = text or content_desc or resource_id
            elements.append({
                "id": idx,
                "text": text,
                "content_desc": content_desc,
                "label": label,
                "resource_id": resource_id,
                "class": class_name,
                "clickable": clickable == "true",
                "bounds": [x1, y1, x2, y2],
                "center": [center_x, center_y],
            })

        return elements
