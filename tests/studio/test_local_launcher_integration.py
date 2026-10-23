"""Opt-in real API/Vite lifecycle smoke with isolated storage and inert configuration.

Run with ZHIXING_TEST_LOCAL_STARTUP=1; Node dependencies must already be installed.
No Agent, Experiment, model request, ADB command, or browser navigation is initiated.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.skipif(
    os.environ.get("ZHIXING_TEST_LOCAL_STARTUP") != "1" or os.name != "posix",
    reason="Opt-in local API/Vite smoke requires loopback access and Node dependencies",
)


def free_port() -> int:
    """Return an ephemeral loopback port; child strict binding still handles races."""
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def request(url: str) -> bytes:
    """Read a bounded local HTTP response without inheriting system proxy settings.

    Args:
        url: Isolated test API or frontend URL.
    Raises:
        URLError: Service is unavailable or returns an HTTP error.
    Returns:
        At most one MiB of response data.
    """
    with build_opener(ProxyHandler({})).open(url, timeout=2) as response:
        assert response.status == 200
        return response.read(1024 * 1024)


@pytest.mark.parametrize("stop_signal", [signal.SIGINT, signal.SIGTERM])
def test_real_stack_and_proxy_cleanup(tmp_path, stop_signal):
    """Exercise custom ports, changed cwd, occupied-port refusal and both stop signals."""
    backend_port, frontend_port = free_port(), free_port()
    while frontend_port == backend_port:
        frontend_port = free_port()
    secret_file = tmp_path / "secrets.yaml"
    secret_file.write_text("api_key: inert-launcher-test-key\n")
    profile_file = tmp_path / "profiles.json"
    profile_file.write_text(json.dumps({"schemaVersion": 1, "profiles": [{
        "deviceProfileId": "launcher-test", "label": "Launcher test", "platform": "android",
        "target": {"kind": "adb_serial", "serial": "not-a-real-device"},
    }]}))
    command = [sys.executable, str(ROOT / "run_studio.py"), "--no-browser",
               "--database", str(tmp_path / "studio.sqlite3"),
               "--secrets", str(secret_file), "--device-profile-config", str(profile_file),
               "--backend-port", str(backend_port), "--frontend-port", str(frontend_port)]
    env = dict(os.environ)
    env.update(VITE_STUDIO_API_BASE="http://stale.invalid", ZHIXING_STUDIO_PROXY_TARGET="http://stale.invalid")
    for name in ("ZHIXING_STUDIO_BENCHMARK_PACKAGES", "ZHIXING_STUDIO_BENCHMARK_CATALOG_ROOTS"):
        env.pop(name, None)
    api_url = f"http://127.0.0.1:{backend_port}/studio/runtime-readiness"
    ui_url = f"http://127.0.0.1:{frontend_port}"
    log_path = tmp_path / "launcher.log"
    with log_path.open("w") as log:
        process = subprocess.Popen(command, cwd=tmp_path, env=env, stdout=log, stderr=subprocess.STDOUT)
    try:
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            assert process.poll() is None, log_path.read_text()
            if "Studio 已启动" in log_path.read_text():
                break
            time.sleep(0.1)
        assert "Studio 已启动" in log_path.read_text(), log_path.read_text()
        assert b"<html" in request(ui_url)
        readiness = json.loads(request(api_url))
        proxied = json.loads(request(ui_url + "/zhixing-studio/studio/runtime-readiness"))
        assert readiness == proxied
        # A real browser sends Origin on writes; GET-only smoke misses this gate.
        for origin, expected in ((ui_url, 400), ("http://untrusted.invalid", 403)):
            write_request = Request(
                ui_url + "/zhixing-studio/studio/agents",
                data=b"{}", method="POST",
                headers={"Origin": origin, "Content-Type": "application/json"},
            )
            with pytest.raises(HTTPError) as error:
                build_opener(ProxyHandler({})).open(write_request, timeout=3)
            assert error.value.code == expected
        assert readiness["deviceProfiles"][0]["deviceProfileId"] == "launcher-test"
        assert {item["secretRef"] for item in readiness["secrets"]} == {"api_key"}
        assert "inert-launcher-test-key" not in log_path.read_text()
        assert "not-a-real-device" not in log_path.read_text()
        # A second invocation must leave the first instance serving normally.
        second = subprocess.run(command + ["--check"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
        assert second.returncode == 1
        assert "被占用" in second.stderr
        assert process.poll() is None
        assert json.loads(request(api_url)) == readiness
        process.send_signal(stop_signal)
        assert process.wait(timeout=15) == 0, log_path.read_text()
        for url in (api_url, ui_url):
            with pytest.raises((URLError, OSError)):
                request(url)
        restart_check = subprocess.run(command + ["--check"], cwd=tmp_path, env=env, capture_output=True, text=True, timeout=15)
        assert restart_check.returncode == 0, restart_check.stderr
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            process.wait(timeout=15)
