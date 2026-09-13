import os
import re
import time
import subprocess
import uuid
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Tuple, Optional, Union, Sequence

import logging

from zhixing.devices.base import (
    BaseDevice,
    DeviceInfo,
    ConnectionType,
    CommandResult,
    DeviceCommandError,
    _execute_command,
    _resolve_executable,
    KeyCodeAndroid,
    SwipeDirection,
)
# from zhixing.utils.registry import register_device
from zhixing.core.factory import PluginRegistry
from zhixing.config.timing import TIMING_CONFIG

_log = logging.getLogger(__name__)
_SERIAL_PATTERN = re.compile(r"^[A-Za-z0-9._:-]+$")
_PACKAGE_PATTERN = re.compile(r"^[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)+$")
_COMPONENT_PATTERN = re.compile(r"^[A-Za-z0-9_.$/]+$")
_REMOTE_PATH_PATTERN = re.compile(r"^/[A-Za-z0-9_./-]+$")
_DEFAULT_COMMAND_TIMEOUT = 30.0

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
        """Create a serial-bound Android device session.

        Args:
            serial (str): Explicit ADB serial. A unique ready device is selected
                only when this value is omitted.
            language (str): Device language used by higher-level components.

        Raises:
            RuntimeError: No unique ready Android device is available.
            ValueError: The serial format is unsafe.

        Returns:
            None: Initializes the device and reads its display size.
        """
        super().__init__(serial, language)
        self.platform = "android"
        if not self.serial:
            devices = self.list_devices()
            if not devices:
                raise RuntimeError(
                    "No Android device in the 'device' state was found (adb devices). "
                    "Connect the phone, enable USB debugging, authorize this PC, or fix the serial in config."
                )
            if len(devices) > 1:
                candidates = ", ".join(device.device_id for device in devices)
                raise RuntimeError(
                    "Multiple Android devices are ready; pass an explicit serial "
                    f"instead of guessing ({candidates})."
                )
            self.serial = devices[0].device_id
            _log.info("No serial in config; selected the only ready adb device serial=%s", self.serial)

        self._validate_serial(self.serial)
        self._assert_target_device_ready()

        self.app_package_names = dict(ANDROID_APP_PACKAGE_NAMES)

        self.w, self.h = self.display_size()

    def _assert_target_device_ready(self) -> None:
        """Fail fast when a serial is offline, missing, or unauthorized.

        Args:
            None.

        Raises:
            RuntimeError: ADB does not report the target in the device state.

        Returns:
            None: The target is ready for commands.
        """
        result = _execute_command(
            ["adb", "-s", self.serial, "get-state"],
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )
        state = (result.output or "").strip().lower()
        if result.exit_code != 0 or state != "device":
            raise RuntimeError(
                f"Android device serial={self.serial!r} is not reachable via ADB "
                f"(get-state={state!r}, exit_code={result.exit_code}). "
                "Connect the device, run `adb devices`, and ensure status is 'device'."
            )

    @staticmethod
    def _validate_serial(serial: str) -> None:
        """Validate an ADB serial before it reaches a command.

        Args:
            serial (str): Candidate serial.

        Raises:
            ValueError: The serial is blank or contains shell control syntax.

        Returns:
            None: The serial is safe to use as one argv entry.
        """
        if not serial or not _SERIAL_PATTERN.fullmatch(serial):
            raise ValueError("Android serial contains unsupported characters")

    @classmethod
    def list_device_states(cls) -> List[DeviceInfo]:
        """List Android devices including offline and unauthorized entries.

        Args:
            None.

        Raises:
            None: ADB discovery failures return an empty list.

        Returns:
            List[DeviceInfo]: Parsed device states in ADB output order.
        """
        result = _execute_command(["adb", "devices", "-l"], timeout=_DEFAULT_COMMAND_TIMEOUT)
        if result.exit_code != 0:
            _log.warning("Unable to list Android devices: %s", result.error or result.output)
            return []
        devices: list[DeviceInfo] = []
        for line in result.output.strip().splitlines()[1:]:
            parts = line.split()
            if len(parts) < 2:
                continue
            device_id, status = parts[0], parts[1]
            if "emulator" in device_id:
                connection = ConnectionType.EMULATOR
            elif ":" in device_id:
                connection = ConnectionType.REMOTE
            else:
                connection = ConnectionType.USB
            model = next(
                (part.split(":", 1)[1] for part in parts if part.startswith("model:")),
                "Unknown",
            )
            devices.append(
                DeviceInfo(
                    device_id=device_id,
                    platform="android",
                    status=status,
                    connection_type=connection,
                    model=model,
                )
            )
        return devices

    @classmethod
    def list_devices(cls) -> List[DeviceInfo]:
        """List only Android devices ready for runtime use.

        Args:
            None.

        Raises:
            None.

        Returns:
            List[DeviceInfo]: Devices whose ADB status is exactly ``device``.
        """
        return [device for device in cls.list_device_states() if device.status == "device"]

    def display_size(self) -> Tuple[int, int]:
        """Read the physical or override display size from Android.

        Args:
            None.

        Raises:
            DeviceCommandError: ADB cannot read a valid screen size.

        Returns:
            Tuple[int, int]: Width and height in pixels.
        """
        result = self._shell_args(["wm", "size"], operation="display_size")
        match = re.search(r"(?:Physical|Override) size: (\d+)x(\d+)", result.output)
        if match:
            return int(match.group(1)), int(match.group(2))
        raise DeviceCommandError(
            "display_size",
            CommandResult("", f"Unexpected wm size output: {result.output[:200]}", -1),
        )

    def screenshot(self, path: str, method: str = "screencap") -> str:
        """Capture the current screen into a verified local PNG.

        Args:
            path (str): Destination path on the host.
            method (str): Compatibility method name; Android uses screencap.

        Raises:
            DeviceCommandError: Both bounded screenshot strategies fail.

        Returns:
            str: Absolute or caller-provided path containing a non-empty PNG.
        """
        del method
        os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        if self._screenshot_via_exec_out(path):
            return path
        self._screenshot_via_device_tmp(path)
        if not os.path.isfile(path) or os.path.getsize(path) < 64:
            raise DeviceCommandError(
                "screenshot",
                CommandResult("", "Screenshot artifact is missing or empty", -1),
            )
        return path

    def _screenshot_via_exec_out(self, path: str) -> bool:
        """Stream a bounded PNG over adb exec-out.

        Args:
            path (str): Local destination.

        Raises:
            None: Failure returns False so the verified fallback can run.

        Returns:
            bool: True only when a non-empty PNG-like artifact was written.
        """
        cmd = [*self._adb_cmd(), "exec-out", "screencap", "-p"]
        cmd[0] = _resolve_executable(cmd[0])
        try:
            with open(path, "wb") as out:
                result = subprocess.run(
                    cmd,
                    stdout=out,
                    stderr=subprocess.PIPE,
                    check=False,
                    timeout=_DEFAULT_COMMAND_TIMEOUT,
                )
            if result.returncode != 0 or not os.path.isfile(path) or os.path.getsize(path) < 64:
                try:
                    os.remove(path)
                except OSError:
                    pass
                return False
            return True
        except (OSError, subprocess.TimeoutExpired):
            try:
                os.remove(path)
            except OSError:
                pass
            return False

    def _screenshot_via_device_tmp(self, path: str) -> None:
        """Capture through device-local temporary storage and verify the pull.

        Args:
            path (str): Local destination.

        Raises:
            DeviceCommandError: Capture, pull, or artifact validation fails.

        Returns:
            None: Writes the screenshot to ``path``.
        """
        remote_path = f"/data/local/tmp/zhixing_screenshot_{uuid.uuid4().hex}.png"
        try:
            self._shell_args(
                ["screencap", "-p", remote_path],
                operation="screenshot_capture",
            )
            self.pull(remote_path, path)
            if not os.path.isfile(path) or os.path.getsize(path) < 64:
                raise DeviceCommandError(
                    "screenshot_pull",
                    CommandResult("", "Pulled screenshot is missing or empty", -1),
                )
        finally:
            self._shell_args(
                ["rm", "-f", remote_path],
                operation="screenshot_cleanup",
                error_raise=False,
            )

    def _adb_cmd(self) -> List[str]:
        """Return the serial-bound ADB argv prefix.

        Args:
            None.

        Raises:
            None.

        Returns:
            List[str]: ADB executable and serial selection arguments.
        """
        return ["adb", "-s", self.serial] if self.serial else ["adb"]

    def shell(self, cmd: str, error_raise=True) -> CommandResult:
        """Execute a bounded legacy Android shell command.

        Args:
            cmd (str): Remote shell command retained for compatibility.
            error_raise (bool): Raise DeviceCommandError on failure when true.

        Raises:
            ValueError: The command is blank or contains line/NUL separators.
            DeviceCommandError: ADB reports failure and ``error_raise`` is true.

        Returns:
            CommandResult: Normalized command result.
        """
        if not cmd.strip() or any(character in cmd for character in ("\x00", "\n", "\r")):
            raise ValueError("Android shell command must be one non-empty line")
        return self._run_adb(
            ["shell", cmd],
            operation="shell",
            error_raise=error_raise,
        )

    def _shell_args(
        self,
        args: Sequence[str],
        *,
        operation: str,
        error_raise: bool = True,
    ) -> CommandResult:
        """Execute a structured Android shell argv sequence.

        Args:
            args (Sequence[str]): Remote command arguments.
            operation (str): Safe logical operation name.
            error_raise (bool): Raise on failure when true.

        Raises:
            ValueError: No remote command is provided.
            DeviceCommandError: ADB reports failure and ``error_raise`` is true.

        Returns:
            CommandResult: Normalized command result.
        """
        if not args:
            raise ValueError("Android shell args cannot be empty")
        return self._run_adb(
            ["shell", *[str(value) for value in args]],
            operation=operation,
            error_raise=error_raise,
        )

    def _run_adb(
        self,
        args: Sequence[str],
        *,
        operation: str,
        error_raise: bool = True,
    ) -> CommandResult:
        """Execute one serial-bound bounded ADB operation.

        Args:
            args (Sequence[str]): ADB arguments after the serial prefix.
            operation (str): Safe operation name for diagnostics.
            error_raise (bool): Raise DeviceCommandError on failure.

        Raises:
            DeviceCommandError: ADB reports failure and ``error_raise`` is true.

        Returns:
            CommandResult: Normalized command result.
        """
        result = _execute_command(
            [*self._adb_cmd(), *[str(value) for value in args]],
            timeout=_DEFAULT_COMMAND_TIMEOUT,
        )
        if error_raise and result.exit_code != 0:
            raise DeviceCommandError(operation, result)
        return result

    def pull(self, remote_path: str, local_path: str, error_raise=True) -> CommandResult:
        """Pull one validated remote file to a host path.

        Args:
            remote_path (str): Absolute device path.
            local_path (str): Host destination passed as one argv value.
            error_raise (bool): Raise on ADB failure when true.

        Raises:
            ValueError: The remote path is unsafe.
            DeviceCommandError: ADB pull fails and ``error_raise`` is true.

        Returns:
            CommandResult: Normalized pull result.
        """
        self._validate_remote_path(remote_path)
        os.makedirs(os.path.dirname(os.path.abspath(local_path)) or ".", exist_ok=True)
        return self._run_adb(
            ["pull", remote_path, local_path],
            operation="pull",
            error_raise=error_raise,
        )

    def tap(self, x: int, y: int) -> None:
        """Tap one validated screen coordinate.

        Args:
            x (int): Horizontal pixel.
            y (int): Vertical pixel.

        Raises:
            ValueError: The coordinate is out of bounds.
            DeviceCommandError: ADB input fails.

        Returns:
            None: The tap is confirmed by command success.
        """
        self._validate_coordinate(x, y)
        self._shell_args(["input", "tap", str(x), str(y)], operation="tap")
        time.sleep(TIMING_CONFIG.device.default_tap_delay)

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        """Long-press one validated screen coordinate.

        Args:
            x (int): Horizontal pixel.
            y (int): Vertical pixel.
            duration_ms (int): Bounded press duration.

        Raises:
            ValueError: The coordinate is out of bounds.
            DeviceCommandError: ADB input fails.

        Returns:
            None: The long press is confirmed by command success.
        """
        self._validate_coordinate(x, y)
        d = max(300, min(int(duration_ms), 5000))
        self._shell_args(
            ["input", "swipe", str(x), str(y), str(x), str(y), str(d)],
            operation="long_press",
        )
        time.sleep(TIMING_CONFIG.device.default_long_press_delay)

    def swipe(self, direction: Union[SwipeDirection, str], scale: float = 0.8, box=None, speed=1600):
        """Swipe in one cardinal direction within the display bounds.

        Args:
            direction (Union[SwipeDirection, str]): left/right/up/down.
            scale (float): Fraction of the screen traversed.
            box (Any): Reserved compatibility parameter.
            speed (int): Reserved compatibility speed.

        Raises:
            ValueError: Direction or scale is invalid.
            DeviceCommandError: ADB input fails.

        Returns:
            None: The swipe command succeeded.
        """
        del box, speed
        if isinstance(direction, str):
            direction = direction.lower()
        if direction not in {
            SwipeDirection.LEFT,
            SwipeDirection.RIGHT,
            SwipeDirection.UP,
            SwipeDirection.DOWN,
            "left",
            "right",
            "up",
            "down",
        }:
            raise ValueError(f"Unsupported swipe direction: {direction}")
        scale = float(scale)
        if not 0.0 < scale <= 1.0:
            raise ValueError("Swipe scale must be in (0, 1]")

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
        self._shell_args(
            ["input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration)],
            operation="swipe",
        )
        time.sleep(TIMING_CONFIG.device.default_swipe_delay)

    def input_text(self, text: str):
        """Enter bounded single-line text through Android input.

        Args:
            text (str): Text to type.

        Raises:
            ValueError: Text contains NUL/newline characters.
            DeviceCommandError: ADB input fails.

        Returns:
            None: The input command succeeded.
        """
        if any(character in text for character in ("\x00", "\n", "\r")):
            raise ValueError("Android text input must be one line")
        encoded = text.replace("%", "%25").replace(" ", "%s")
        self._shell_args(["input", "text", encoded], operation="input_text")
        time.sleep(TIMING_CONFIG.action.text_input_delay)

    def clear_text(self, num: int = 15) -> None:
        """Delete a bounded number of characters from the focused field.

        Args:
            num (int): Number of delete key events.

        Raises:
            ValueError: The requested count is negative or excessive.
            DeviceCommandError: Any key event fails.

        Returns:
            None: All delete events succeeded.
        """
        count = int(num)
        if count < 0 or count > 500:
            raise ValueError("clear_text count must be between 0 and 500")
        for _ in range(count):
            self._shell_args(
                ["input", "keyevent", str(KeyCodeAndroid.DEL.value)],
                operation="clear_text",
            )
        time.sleep(TIMING_CONFIG.action.text_clear_delay)

    def go_home(self):
        """Send the Android HOME key.

        Args:
            None.

        Raises:
            DeviceCommandError: The key command fails.

        Returns:
            None: The command succeeded.
        """
        self._shell_args(
            ["input", "keyevent", str(KeyCodeAndroid.HOME.value)],
            operation="go_home",
        )
        time.sleep(TIMING_CONFIG.device.default_home_delay)

    def go_back(self):
        """Send the Android BACK key.

        Args:
            None.

        Raises:
            DeviceCommandError: The key command fails.

        Returns:
            None: The command succeeded.
        """
        self._shell_args(
            ["input", "keyevent", str(KeyCodeAndroid.BACK.value)],
            operation="go_back",
        )
        time.sleep(TIMING_CONFIG.device.default_back_delay)

    def enter(self):
        """Send the Android ENTER key.

        Args:
            None.

        Raises:
            DeviceCommandError: The key command fails.

        Returns:
            None: The command succeeded.
        """
        self._shell_args(
            ["input", "keyevent", str(KeyCodeAndroid.ENTER.value)],
            operation="enter",
        )

    def wait(self, seconds: float = 2.0) -> None:
        """Wait for UI/network loading without touching the screen."""
        duration = max(1.5, min(float(seconds), 30.0))
        _log.debug("wait %.1fs", duration)
        time.sleep(duration)

    def get_app(self) -> List[str]:
        """List installed Android package identifiers.

        Args:
            None.

        Raises:
            DeviceCommandError: Package discovery fails.

        Returns:
            List[str]: Installed package identifiers.
        """
        res = self._shell_args(["pm", "list", "packages"], operation="get_app")
        packages = []
        for line in res.output.splitlines():
            if line.startswith("package:"):
                packages.append(line.replace("package:", "").strip())
        return packages

    def launch_app(self, package_name: str, delay: float = None):
        """Launch one validated Android package.

        Args:
            package_name (str): Full package identifier.
            delay (float): Optional bounded settle delay.

        Raises:
            ValueError: Package identifier is invalid.
            DeviceCommandError: Launch command fails.

        Returns:
            None: The launch command succeeded.
        """
        self._validate_package(package_name)
        if delay is None:
            delay = TIMING_CONFIG.device.default_launch_delay
        self._shell_args(
            ["monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
            operation="launch_app",
        )
        time.sleep(max(0.0, min(float(delay), 30.0)))

    def get_xml(self, xml_path: str) -> str:
        """Dump and verify the current Android UI hierarchy.

        Args:
            xml_path (str): Host destination for the XML artifact.

        Raises:
            DeviceCommandError: Dump, pull, or XML validation fails.

        Returns:
            str: Verified XML text written to ``xml_path``.
        """
        xml_path = os.path.abspath(xml_path)
        os.makedirs(os.path.dirname(xml_path) or ".", exist_ok=True)
        try:
            os.remove(xml_path)
        except FileNotFoundError:
            pass
        remote = f"/data/local/tmp/zhixing_ui_{uuid.uuid4().hex}.xml"
        try:
            self._shell_args(
                ["uiautomator", "dump", remote],
                operation="ui_dump",
            )
            self.pull(remote, xml_path)
        finally:
            self._shell_args(
                ["rm", "-f", remote],
                operation="ui_dump_cleanup",
                error_raise=False,
            )
        if not os.path.isfile(xml_path) or os.path.getsize(xml_path) == 0:
            raise DeviceCommandError(
                "ui_dump",
                CommandResult("", "UI XML artifact is missing or empty", -1),
            )
        try:
            with open(xml_path, encoding="utf-8") as stream:
                content = stream.read()
            ET.fromstring(content)
            return content
        except (OSError, ET.ParseError) as error:
            raise DeviceCommandError(
                "ui_dump",
                CommandResult("", f"Invalid UI XML: {error}", -1),
            ) from error

    def start_app(self, app: str, page: str=""):
        """Start an application by registered alias or full package.

        Args:
            app (str): Registered alias or package identifier.
            page (str): Optional Android component page.

        Raises:
            ValueError: Package or page identifier is invalid.
            DeviceCommandError: Launch command fails.

        Returns:
            CommandResult: Successful ADB command result.
        """
        package_name = self.app_package_names.get(app.lower())
        if not package_name:
            package_name = app
        self._validate_package(package_name)
        if page:
            if not _COMPONENT_PATTERN.fullmatch(page):
                raise ValueError("Android activity page contains unsupported characters")
            result = self._shell_args(
                ["am", "start", "-n", f"{package_name}/{page}"],
                operation="start_app",
            )
        else:
            resolved = self._shell_args(
                [
                    "cmd",
                    "package",
                    "resolve-activity",
                    "--brief",
                    "-c",
                    "android.intent.category.LAUNCHER",
                    package_name,
                ],
                operation="resolve_app",
            )
            resolved_activity = (resolved.output or "").strip()
            if (
                not resolved_activity
                or "no activity found" in resolved_activity.lower()
            ):
                raise DeviceCommandError(
                    "resolve_app",
                    CommandResult(
                        "",
                        f"No launchable activity for {package_name}",
                        -1,
                    ),
                )
            result = self._shell_args(
                ["monkey", "-p", package_name, "-c", "android.intent.category.LAUNCHER", "1"],
                operation="start_app",
            )
        time.sleep(1)
        return result

    def push_file(self, local_path: str, remote_path: str) -> bool:
        """Push one host file to a validated Android path.

        Args:
            local_path (str): Existing host file.
            remote_path (str): Validated absolute Android destination.

        Raises:
            ValueError: The remote path is unsafe.

        Returns:
            bool: True only when ADB confirms a successful push.
        """
        if not os.path.isfile(local_path):
            return False
        self._validate_remote_path(remote_path)
        result = self._run_adb(
            ["push", local_path, remote_path],
            operation="push",
            error_raise=False,
        )
        return result.exit_code == 0

    @staticmethod
    def _validate_package(package_name: str) -> None:
        """Validate one Android package identifier.

        Args:
            package_name (str): Candidate package identifier.

        Raises:
            ValueError: The identifier is malformed.

        Returns:
            None: The package is safe to use as argv.
        """
        if not _PACKAGE_PATTERN.fullmatch(package_name):
            raise ValueError(f"Invalid Android package identifier: {package_name!r}")

    @staticmethod
    def _validate_remote_path(path: str) -> None:
        """Validate a bounded absolute Android path.

        Args:
            path (str): Candidate remote path.

        Raises:
            ValueError: Path is relative or contains unsafe characters.

        Returns:
            None: The path is safe to pass as one argv value.
        """
        if not _REMOTE_PATH_PATTERN.fullmatch(path) or ".." in path.split("/"):
            raise ValueError("Android remote path contains unsupported characters")

    def _validate_coordinate(self, x: int, y: int) -> None:
        """Validate one coordinate against the current display.

        Args:
            x (int): Horizontal pixel.
            y (int): Vertical pixel.

        Raises:
            ValueError: A coordinate is outside the display.

        Returns:
            None: The coordinate is valid.
        """
        if int(x) < 0 or int(y) < 0 or int(x) >= self.w or int(y) >= self.h:
            raise ValueError(f"Android coordinate ({x}, {y}) is outside {self.w}x{self.h}")

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
