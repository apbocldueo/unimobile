"""Harmony device command-boundary tests that never connect to a real device."""

from __future__ import annotations

from zhixing.devices import harmony as harmony_module
from zhixing.devices.base import BaseDevice, CommandResult
from zhixing.devices.harmony import HarmonyDevice


def _device() -> HarmonyDevice:
    """Create a HarmonyDevice without running its HDC or driver constructor.

    Args:
        None.

    Raises:
        None.

    Returns:
        HarmonyDevice: Serial-bound in-memory test instance.
    """
    device = object.__new__(HarmonyDevice)
    BaseDevice.__init__(device, "serial with spaces", "cn")
    device.platform = "harmony"
    device.hdc_prefix = "hdc"
    return device


def test_harmony_shell_uses_argv_instead_of_host_shell(monkeypatch) -> None:
    """Keep legacy shell calls out of the host shell execution path.

    Args:
        monkeypatch (pytest.MonkeyPatch): Command replacement fixture.

    Raises:
        AssertionError: The command is flattened into a host-shell string.

    Returns:
        None.
    """
    device = _device()
    captured: list[list[str]] = []

    def fake_execute(command, **kwargs):
        del kwargs
        captured.append(command)
        return CommandResult("ok", "", 0)

    monkeypatch.setattr(harmony_module, "_execute_command", fake_execute)

    result = device.shell("echo value; whoami")

    assert result.output == "ok"
    assert captured == [["hdc", "-t", "serial with spaces", "shell", "echo value; whoami"]]


def test_harmony_internal_commands_keep_arguments_separate(monkeypatch) -> None:
    """Use structured argv for package discovery and device discovery.

    Args:
        monkeypatch (pytest.MonkeyPatch): Command replacement fixture.

    Raises:
        AssertionError: Internal commands are flattened or parsed incorrectly.

    Returns:
        None.
    """
    device = _device()
    captured: list[list[str]] = []

    def fake_execute(command, **kwargs):
        del kwargs
        captured.append(command)
        if command[-4:] == ["shell", "bm", "dump", "-a"]:
            return CommandResult("com.example.one\n", "", 0)
        return CommandResult("device-1\n", "", 0)

    monkeypatch.setattr(harmony_module, "_execute_command", fake_execute)

    assert device.get_app() == ["com.example.one"]
    assert [item.device_id for item in HarmonyDevice.list_devices()] == ["device-1"]
    assert captured[0] == ["hdc", "-t", "serial with spaces", "shell", "bm", "dump", "-a"]
    assert captured[1] == ["hdc", "list", "targets"]
