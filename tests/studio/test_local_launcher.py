"""Local startup contracts without devices, model calls, or user database writes."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest

# Load the repository-only script without adding it to the installed package API.
_SPEC = importlib.util.spec_from_file_location("studio_local_launcher", Path(__file__).resolve().parents[2] / "run_studio.py")
launcher = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(launcher)


@pytest.fixture
def environment(monkeypatch, tmp_path):
    """Provide an isolated launcher workspace with no inherited private configuration."""
    for name in ("ZHIXING_STUDIO_SECRETS", "ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(launcher, "check_dependencies", Mock(return_value="/node"))
    monkeypatch.setattr(launcher, "check_ports", Mock())
    monkeypatch.setattr(launcher, "validate_configuration", Mock())
    monkeypatch.setattr(launcher, "stop_children", Mock())
    monkeypatch.setattr(launcher.webbrowser, "open", Mock(return_value=True))
    monkeypatch.setattr(launcher, "wait_for_services", Mock())
    monkeypatch.setattr(launcher, "ensure_children_alive", Mock(side_effect=KeyboardInterrupt))
    return tmp_path


def test_priority_and_fixed_workspace(tmp_path, monkeypatch):
    """Preserve explicit invalid selections and resolve all defaults against the root."""
    (tmp_path / "secrets.yaml").write_text("api_key: placeholder\n")
    (tmp_path / "secrets.local.yaml").write_text("api_key: preferred\n")
    monkeypatch.chdir(tmp_path.parent)
    defaults = ("secrets.local.yaml", "secrets.yaml")
    select = launcher.configuration_path
    assert select(None, {}, "KEY", defaults, tmp_path) == tmp_path / defaults[0]
    assert select(None, {"KEY": "external.yaml"}, "KEY", defaults, tmp_path) == tmp_path / "external.yaml"
    assert select(Path("missing.yaml"), {"KEY": "external.yaml"}, "KEY", defaults, tmp_path) == tmp_path / "missing.yaml"
    assert select(None, {}, "KEY", ("absent",), tmp_path) is None


def test_invalid_configuration_has_no_private_output(tmp_path, capsys):
    """Invalid explicit configuration fails without leaking parser input or fallback."""
    secrets = tmp_path / "secret.yaml"
    secrets.write_text("api_key: [PRIVATE_TEST_SENTINEL]\n")
    with pytest.raises(launcher.LaunchError) as error:
        launcher.validate_configuration(secrets, None)
    assert "PRIVATE_TEST_SENTINEL" not in str(error.value)
    assert "PRIVATE_TEST_SENTINEL" not in str(capsys.readouterr())


def test_valid_configuration_only_prints_presence(tmp_path, capsys):
    """Loading does not disclose credentials, serials, or claim a live connection."""
    secrets = tmp_path / "secret.yaml"
    secrets.write_text("api_key: PRIVATE_TEST_SENTINEL\n")
    profiles = tmp_path / "profiles.json"
    profiles.write_text(json.dumps({"schemaVersion": 1, "profiles": [{"deviceProfileId": "local", "label": "Local", "platform": "android", "target": {"kind": "adb_serial", "serial": "PRIVATE_SERIAL_SENTINEL"}}]}))
    launcher.validate_configuration(secrets, profiles)
    output = capsys.readouterr().out
    assert "SENTINEL" not in output
    assert "未测试接口连接" in output
    assert "未检查在线状态" in output


def test_absent_configuration_is_authoring_only(capsys):
    """Missing local configuration permits startup with explicit repair guidance."""
    launcher.validate_configuration(None, None)
    output = capsys.readouterr().out
    assert "可编辑 Agent" in output
    assert "studio/device-profiles.json" in output


def test_check_does_not_spawn_or_open_browser(environment, monkeypatch):
    """Check mode avoids any child processes or browser navigation."""
    spawn = Mock()
    monkeypatch.setattr(launcher, "spawn", spawn)
    assert launcher.launch(launcher.parser().parse_args(["--check"]), environment) == 0
    spawn.assert_not_called()
    launcher.webbrowser.open.assert_not_called()


def test_custom_ports_proxy_config_and_workspace(environment, monkeypatch):
    """A single launch pins both workspace and frontend API despite stale environment."""
    monkeypatch.setenv("VITE_STUDIO_API_BASE", "http://wrong.invalid")
    monkeypatch.setenv("ZHIXING_STUDIO_PROXY_TARGET", "http://wrong.invalid")
    spawn = Mock(side_effect=[Mock(), Mock()])
    monkeypatch.setattr(launcher, "spawn", spawn)
    args = launcher.parser().parse_args(["--backend-port", "9876", "--frontend-port", "5432", "--secrets", "secret.yaml", "--device-profile-config", "profiles.json"])
    assert launcher.launch(args, environment) == 0
    backend, frontend = spawn.call_args_list
    command, cwd, env = backend.args
    assert command[0] == sys.executable
    assert command[command.index("--workspace") + 1] == str(environment)
    assert command[command.index("--frontend-port") + 1] == "5432"
    assert command[command.index("--secrets") + 1] == str(environment / "secret.yaml")
    assert cwd == environment
    assert frontend.args[1] == environment / "studio"
    assert "--strictPort" in frontend.args[0]
    assert env["ZHIXING_STUDIO_PROXY_TARGET"] == "http://127.0.0.1:9876"
    assert env["VITE_STUDIO_API_BASE"] == "/zhixing-studio"
    assert os.environ["VITE_STUDIO_API_BASE"] == "http://wrong.invalid"
    launcher.webbrowser.open.assert_called_once_with("http://127.0.0.1:5432")
    assert len(launcher.stop_children.call_args.args[0]) == 2


@pytest.mark.parametrize("failure", [OSError("spawn failed"), launcher.LaunchError("startup failed")])
def test_partial_startup_cleans_owned_children(environment, monkeypatch, failure):
    """Second-process or HTTP-startup failure cleans up the already-spawned service."""
    first = Mock()
    if isinstance(failure, OSError):
        monkeypatch.setattr(launcher, "spawn", Mock(side_effect=[first, failure]))
    else:
        monkeypatch.setattr(launcher, "spawn", Mock(side_effect=[first, Mock()]))
        launcher.wait_for_services.side_effect = failure
    with pytest.raises(type(failure)):
        launcher.launch(launcher.parser().parse_args([]), environment)
    assert first in launcher.stop_children.call_args.args[0]
    launcher.webbrowser.open.assert_not_called()


def test_no_browser_and_signal_handler_restoration(environment, monkeypatch):
    """Headless startup and interrupt cleanup preserve the caller's signal handlers."""
    previous = signal.getsignal(signal.SIGINT)
    monkeypatch.setattr(launcher, "spawn", Mock(side_effect=[Mock(), Mock()]))
    launcher.launch(launcher.parser().parse_args(["--no-browser"]), environment)
    launcher.webbrowser.open.assert_not_called()
    assert signal.getsignal(signal.SIGINT) == previous


@pytest.mark.parametrize("ports", [(8765, 8765), (0, 5173), (8765, 65536)])
def test_invalid_ports(ports):
    """Reject ambiguous or invalid ports before touching any service."""
    with pytest.raises(launcher.LaunchError):
        launcher.check_ports(ports)


def test_frontend_origin_allowlist_is_exact():
    """Custom ports allow only named loopback hosts and retain default origins."""
    from zhixing.studio.httpd import local_frontend_origins

    defaults = local_frontend_origins(None)
    assert local_frontend_origins(5432) - defaults == {
        "http://127.0.0.1:5432", "http://localhost:5432",
    }


@pytest.mark.parametrize("port", [True, 0, -1, 65536, "5432"])
def test_invalid_frontend_origin_port(port):
    """Invalid ports cannot become allowlist entries or reach database composition."""
    from zhixing.studio.httpd import run_httpd

    with pytest.raises(ValueError, match="frontend_port"):
        run_httpd(frontend_port=port)


def test_occupied_port_fails_without_spawning(environment, monkeypatch):
    """Port preflight failure cannot terminate or reuse an existing service."""
    launcher.check_ports.side_effect = launcher.LaunchError("occupied")
    spawn = Mock()
    monkeypatch.setattr(launcher, "spawn", spawn)
    with pytest.raises(launcher.LaunchError):
        launcher.launch(launcher.parser().parse_args([]), environment)
    spawn.assert_not_called()
    launcher.stop_children.assert_not_called()


def test_http_ready_false_is_valid_startup(monkeypatch):
    """HTTP availability must not require a configured device or model."""
    api, ui = Mock(), Mock()
    api.__enter__ = Mock(return_value=api)
    api.__exit__ = Mock()
    api.read.return_value = b'{"schemaVersion":1,"ready":false}'
    api.status = 200
    ui.__enter__ = Mock(return_value=ui)
    ui.__exit__ = Mock()
    ui.read.return_value = b"<html></html>"
    ui.status = 200
    opener = Mock()
    opener.open.side_effect = [api, ui]
    monkeypatch.setattr(launcher, "build_opener", Mock(return_value=opener))
    monkeypatch.setattr(launcher.time, "sleep", Mock())
    launcher.wait_for_services([Mock(poll=Mock(return_value=None))], "http://127.0.0.1:8765", "http://127.0.0.1:5173")
    assert opener.open.call_count == 2


def test_startup_timeout_and_exited_child():
    """A bounded timeout and unexpected successful child exit both fail startup."""
    with pytest.raises(launcher.LaunchError, match="超时"):
        launcher.wait_for_services([], "http://127.0.0.1:8765", "http://127.0.0.1:5173", timeout=0)
    with pytest.raises(launcher.LaunchError, match="退出码 0"):
        launcher.ensure_children_alive([Mock(poll=Mock(return_value=0))])


@pytest.mark.parametrize("command", [["serve", "--port", "9000"], ["replay-import", "--help"]])
def test_backend_command_compatibility(command, monkeypatch):
    """Explicit old subcommands still delegate without local-launcher defaults."""
    import zhixing.studio.__main__ as backend
    entry = Mock()
    monkeypatch.setattr(backend, "main", entry)
    assert launcher.main(command) == 0
    entry.assert_called_once_with(command)


@pytest.mark.skipif(os.name != "posix", reason="POSIX process-group lifecycle")
def test_owned_group_cleanup_preserves_unrelated_process(tmp_path):
    """Real cleanup kills a stubborn grandchild but preserves unrelated processes."""
    marker = tmp_path / "grandchild.pid"
    code = "import os,signal,time; from pathlib import Path; signal.signal(signal.SIGTERM,signal.SIG_IGN); Path(" + repr(str(marker)) + ").write_text(str(os.getpid())); time.sleep(60)"
    parent = "import subprocess,sys,time; subprocess.Popen([sys.executable,'-c'," + repr(code) + "]); time.sleep(60)"
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True)
    child = launcher.spawn([sys.executable, "-c", parent], tmp_path, os.environ)
    try:
        deadline = time.monotonic() + 5
        while not marker.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        grandchild = int(marker.read_text())
        launcher.stop_children([child])
        assert child.poll() is not None
        assert unrelated.poll() is None
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = subprocess.run(["ps", "-o", "stat=", "-p", str(grandchild)], capture_output=True, text=True).stdout.strip()
            if not state or state.startswith("Z"):
                break
            time.sleep(0.02)
        assert not state or state.startswith("Z")
    finally:
        launcher.stop_children([child])
        unrelated.terminate()
        unrelated.wait(timeout=5)


@pytest.mark.parametrize("version", ["v20.19.0\n", "v22.11.0\n", "not-a-version"])
def test_rejects_old_or_unrecognized_node(tmp_path, monkeypatch, version):
    """Reject unsupported tools before launching either service."""
    monkeypatch.setattr(launcher.shutil, "which", Mock(return_value="/node"))
    monkeypatch.setattr(launcher.subprocess, "run", Mock(return_value=Mock(stdout=version)))
    with pytest.raises(launcher.LaunchError, match="22.12"):
        launcher.check_dependencies(tmp_path)


def test_missing_frontend_dependencies(tmp_path, monkeypatch):
    """Missing installation yields an npm ci instruction without executing npm."""
    monkeypatch.setattr(launcher.shutil, "which", Mock(return_value="/node"))
    command = Mock(return_value=Mock(stdout="v24.15.0\n"))
    monkeypatch.setattr(launcher.subprocess, "run", command)
    with pytest.raises(launcher.LaunchError, match="npm ci"):
        launcher.check_dependencies(tmp_path)
    assert command.call_args.args[0] == ["/node", "--version"]
