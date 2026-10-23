"""AndroidDevice feature tests that never connect to a real device."""

from __future__ import annotations

import subprocess

import pytest

from zhixing.devices import android as android_module
from zhixing.devices.android import AndroidDevice
from zhixing.devices.base import (
    BaseDevice,
    CommandResult,
    ConnectionType,
    DeviceCommandError,
    _execute_command,
)


def _device() -> AndroidDevice:
    """Create an AndroidDevice without running its ADB constructor.

    Args:
        None.

    Raises:
        None.

    Returns:
        AndroidDevice: Serial-bound in-memory test instance.
    """
    device = object.__new__(AndroidDevice)
    BaseDevice.__init__(device, "fake-serial", "cn")
    device.platform = "android"
    device.w = 100
    device.h = 200
    device.app_package_names = {"settings": "com.android.settings"}
    return device


def test_execute_command_uses_argv_and_normalizes_timeout(monkeypatch) -> None:
    """Verify bounded argv execution and timeout diagnostics.

    Args:
        monkeypatch (pytest.MonkeyPatch): Process replacement fixture.

    Raises:
        AssertionError: Execution loses argv or timeout semantics.

    Returns:
        None.
    """
    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["shell"] = kwargs["shell"]
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", fake_run)
    result = _execute_command(["adb", "devices"], timeout=0.5)
    assert captured["command"][-1] == "devices"
    assert captured["shell"] is False
    assert result.exit_code == -1
    assert result.timed_out


def test_android_device_lists_all_states_and_filters_ready(monkeypatch) -> None:
    """Parse ready, offline, and unauthorized ADB entries.

    Args:
        monkeypatch (pytest.MonkeyPatch): Command replacement fixture.

    Raises:
        AssertionError: Device state parsing or filtering differs.

    Returns:
        None.
    """
    output = (
        "List of devices attached\n"
        "emulator-5554 device product:sdk model:Pixel_8\n"
        "usb-1 offline model:Phone\n"
        "usb-2 unauthorized model:Phone\n"
    )
    monkeypatch.setattr(
        android_module,
        "_execute_command",
        lambda *args, **kwargs: CommandResult(output, "", 0),
    )
    states = AndroidDevice.list_device_states()
    assert [(item.device_id, item.status) for item in states] == [
        ("emulator-5554", "device"),
        ("usb-1", "offline"),
        ("usb-2", "unauthorized"),
    ]
    assert states[0].connection_type is ConnectionType.EMULATOR
    assert [item.device_id for item in AndroidDevice.list_devices()] == ["emulator-5554"]


def test_android_device_raises_on_nonzero_adb_result(monkeypatch) -> None:
    """Prevent a failed ADB action from being reported as success.

    Args:
        monkeypatch (pytest.MonkeyPatch): Command replacement fixture.

    Raises:
        AssertionError: DeviceCommandError is not raised.

    Returns:
        None.
    """
    device = _device()
    monkeypatch.setattr(
        android_module,
        "_execute_command",
        lambda *args, **kwargs: CommandResult("", "device offline", 1),
    )
    with pytest.raises(DeviceCommandError, match="tap failed"):
        device.tap(10, 20)


def test_android_device_validates_coordinates_package_and_paths() -> None:
    """Reject unsafe device parameters before any command executes.

    Args:
        None.

    Raises:
        AssertionError: Unsafe values are accepted.

    Returns:
        None.
    """
    device = _device()
    with pytest.raises(ValueError, match="outside"):
        device._validate_coordinate(100, 20)
    with pytest.raises(ValueError, match="package"):
        device._validate_package("com.android.settings;rm")
    with pytest.raises(ValueError, match="remote path"):
        device._validate_remote_path("/sdcard/../secret")
    with pytest.raises(ValueError, match="serial"):
        device._validate_serial("emulator-5554;whoami")


def test_android_device_rejects_missing_launch_activity(monkeypatch) -> None:
    """Map Android package-resolution failure to DeviceCommandError.

    Args:
        monkeypatch (pytest.MonkeyPatch): Device command replacement fixture.

    Raises:
        AssertionError: A missing package is reported as launched.

    Returns:
        None.
    """
    device = _device()
    calls: list[tuple[str, ...]] = []

    def fake_shell(args, *, operation, error_raise=True):
        del operation, error_raise
        calls.append(tuple(args))
        return CommandResult("No activity found\n", "", 0)

    monkeypatch.setattr(device, "_shell_args", fake_shell)
    with pytest.raises(DeviceCommandError, match="resolve_app failed"):
        device.start_app("com.zhixing.smoke.missing")
    assert len(calls) == 1
    assert calls[0][:3] == ("cmd", "package", "resolve-activity")


def test_android_device_xml_rejects_failed_pull(monkeypatch, tmp_path) -> None:
    """Surface UI dump pull failure instead of reading stale XML.

    Args:
        monkeypatch (pytest.MonkeyPatch): Device method replacement fixture.
        tmp_path (pathlib.Path): Isolated artifact directory.

    Raises:
        AssertionError: Failed pull is hidden.

    Returns:
        None.
    """
    device = _device()
    monkeypatch.setattr(
        device,
        "_shell_args",
        lambda *args, **kwargs: CommandResult("", "", 0),
    )

    def failed_pull(*args, **kwargs):
        raise DeviceCommandError("pull", CommandResult("", "offline", 1))

    monkeypatch.setattr(device, "pull", failed_pull)
    with pytest.raises(DeviceCommandError, match="pull failed"):
        device.get_xml(str(tmp_path / "stale.xml"))


def test_android_device_screenshot_rejects_empty_fallback(monkeypatch, tmp_path) -> None:
    """Reject an empty screenshot produced by a seemingly successful pull.

    Args:
        monkeypatch (pytest.MonkeyPatch): Screenshot method replacement fixture.
        tmp_path (pathlib.Path): Isolated artifact directory.

    Raises:
        AssertionError: Empty screenshots are accepted.

    Returns:
        None.
    """
    device = _device()
    monkeypatch.setattr(device, "_screenshot_via_exec_out", lambda path: False)
    monkeypatch.setattr(
        device,
        "_shell_args",
        lambda *args, **kwargs: CommandResult("", "", 0),
    )

    def empty_pull(remote, local, error_raise=True):
        del remote, error_raise
        (tmp_path / "empty.png").write_bytes(b"")
        return CommandResult("", "", 0)

    monkeypatch.setattr(device, "pull", empty_pull)
    with pytest.raises(DeviceCommandError, match="missing or empty"):
        device.screenshot(str(tmp_path / "empty.png"))
