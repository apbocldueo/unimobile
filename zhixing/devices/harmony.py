import re
import json
import uuid
import time
import socket
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Union, List, Tuple
from hmdriver2.driver import Driver
from zhixing.devices.base import KeyCode, _execute_command, CommandResult, SwipeDirection, BaseDevice
from zhixing.devices.base import DeviceInfo, ConnectionType
from zhixing.config.timing import TIMING_CONFIG
# from zhixing.utils.registry import register_device
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

@dataclass
class HypiumResponse:
    """
    Example:
    {"result":"On#1"}
    {"result":null}
    {"result":null,"exception":"Can not connect to AAMS, RET_ERR_CONNECTION_EXIST"}
    {"exception":{"code":401,"message":"(PreProcessing: APiCallInfoChecker)Illegal argument count"}}
    """
    result: Union[List, bool, str, None] = None
    exception: Union[List, bool, str, None] = None

@PluginRegistry.register(namespace="device", name="harmony")
class HarmonyDevice(BaseDevice):
    def __init__(self, serial: str = None, language: str = "cn") -> None:
        super().__init__(serial, language)
        
        self.platform = "harmony"
        self.hdc_prefix = 'hdc'
        if serial:
            self.serial = serial
        else:
            devices = self.list_devices()
            if not devices:
                raise RuntimeError(
                    "No HarmonyOS device was found (hdc list targets). "
                    "Connect the device, enable USB debugging / HDC, run `hdc list targets`, "
                    "or set device.params.serial in config."
                )
            self.serial = devices[0].device_id
            logger.info("No serial in config; auto-selected first hdc target serial=%s", self.serial)

        self._assert_target_device_ready()
        self.d = Driver(self.serial)

        self.app_package_names = {
            "wechat": "com.tencent.wechat"
        }

        logger.info("HarmonyDevice ready serial=%s", self.serial)

    def _assert_target_device_ready(self) -> None:
        """Fail fast when YAML/secrets pin a serial that HDC cannot reach (before hmdriver2.Driver)."""
        result = _execute_command(["hdc", "-t", self.serial, "shell", "echo", "zhixing_hdc_ok"])
        if result.exit_code != 0:
            raise RuntimeError(
                f"HarmonyOS device serial={self.serial!r} is not reachable via HDC "
                f"(shell probe exit_code={result.exit_code}, stderr={result.error!r}). "
                "Connect the device, run `hdc list targets`, and ensure the target is online."
            )

    def display_size(self) -> Tuple[int, int]:
        return self.d.display_size()

    def shell(self, cmd: str, error_raise=True) -> CommandResult:
        if cmd[0] != '\"':
            cmd = '\"' + cmd
        if cmd[-1] != '\"':
            cmd += '\"'
        result = _execute_command(f"{self.hdc_prefix} -t {self.serial} shell {cmd}")
        if result.exit_code != 0 and error_raise:
            raise Exception("HDC shell error", f"{cmd}\n{result.output}\n{result.error}")
        return result

    def get_app(self) -> List[str]:
        """Used to obtain the ids of all the existing apps on the mobile phone

        Returns:
            List[str]: _description_
        """
        result = _execute_command(f"{self.hdc_prefix} -t {self.serial} shell bm dump -a")
        output = result.output
        pattern = r'\b[a-zA-Z0-9_]+\.[a-zA-Z0-9_]+\.[a-zA-Z0-9_.]+\b'

        package_list = re.findall(pattern, output)

        package_list = list(set(package_list))
        logger.debug("bm dump -a parsed %d package id(s)", len(package_list))
        return package_list

    def screenshot(self, path: str) -> str:
        self.d.screenshot(path)
    
    def tap(self, x: int, y: int) -> None:
        self.d.click(x, y)
        logger.debug("tap (%s, %s)", x, y)

    def swipe(self
              , direction: Union[SwipeDirection, str]
              , scale: float = 0.8
              , box: Union[Tuple, None] = None
              , speed=1600):
        """
        Args:
            direction (str): one of "left", "right", "up", "bottom" or SwipeDirection.LEFT
            scale (float): percent of swipe, range (0, 1.0]
            box (Tuple): None or (x1, x1, y1, x2, y2)
            speed (int, optional): The swipe speed in pixels per second. Default is 2000. Range: 200-40000. If not within the range, set to default value of 2000.
        Raises:
            ValueError
        """
        self.d.swipe_ext(direction, scale=scale, speed=speed, box=box)
        

    def input_text(self, text):
        """
        Inputs text into the currently focused input field.

        Note: The input field must have focus before calling this method.

        Args:
            text (str): input value
        """
        logger.debug("input_text len=%d", len(text or ""))
        self.d.input_text(text=text)

    def clear_text(self, num=15) -> None:
        key_code = KeyCode.DEL.value
        for i in range(num):
            if i == num - 1:
                logger.debug("clear_text sent %d DEL key events", num)
                return self.shell(f"uitest uiInput keyEvent {key_code}")
            self.shell(f"uitest uiInput keyEvent {key_code}")
        
    def enter(self):
        logger.debug("key ENTER")
        self.d.press_key(KeyCode.ENTER.value)
    
    def go_home(self):
        logger.debug("key HOME")
        self.d.press_key(KeyCode.HOME.value)

    def go_back(self):
        logger.debug("key BACK")
        self.d.press_key(KeyCode.BACK.value)
    
    @classmethod
    def list_devices(cls) -> List[DeviceInfo]:
        """
        List all connected Harmony devices.
        hdc list targets
        """
        try:
            result = _execute_command("hdc list targets")
            
            if result.exit_code != 0:
                return []

            devices = []
            lines = result.output.strip().split("\n")
            
            for line in lines:
                device_id = line.strip()
                if not device_id:
                    continue
                low = device_id.lower()
                if "list of devices" in low or low.endswith("attached"):
                    continue
                if device_id.startswith("[") or low in ("empty", "[empty]"):
                    continue
                if "fail" in low or "error" in low:
                    continue

                if ":" in device_id:
                    conn_type = ConnectionType.REMOTE
                else:
                    conn_type = ConnectionType.USB

                devices.append(
                    DeviceInfo(
                        device_id=device_id,
                        platform="harmony",
                        status="device",
                        connection_type=conn_type,
                        model=None
                    )
                )
            return devices

        except Exception as e:
            logger.error("list_devices failed: %s", e, exc_info=True)
            return []
        
    def get_xml(self, save_dir):
        result = self.d.dump_hierarchy()
        with open(save_dir, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=2)

    def start_app(self, app: str, page: str=""):
        package_name = self.app_package_names.get(app.lower())
        if page:
            self.d.start_app(package_name, page)
        else:
            self.d.start_app(package_name)