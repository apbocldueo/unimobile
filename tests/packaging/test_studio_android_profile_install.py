"""Clean-wheel acceptance for the Stage 5.6A profile boundary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.packaging_acceptance
def test_installed_wheel_starts_empty_and_fake_profile_services(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Start installed Studio with empty and explicit fake profile authority.

    Args:
        isolated_install: Isolated Python, unrelated workdir, and clean env.

    Raises:
        AssertionError: Wheel isolation, HTTP contracts, or side-effect bounds fail.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "studio-android-profile"
    scenario.mkdir()
    script = r"""
import json
import pathlib
import socket
import sys
import threading

import zhixing
import zhixing.studio.device_profiles as device_profile_module
import zhixing.studio.run_execution as run_execution
from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.benchmark_composition import (
    build_default_studio_benchmark_composition,
)
from zhixing.studio.device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    load_android_device_profiles,
    resolve_exact_android_session,
)
from zhixing.studio.httpd import create_http_server


workdir = pathlib.Path(sys.argv[1])
installed_root = pathlib.Path(sys.prefix).resolve()
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(installed_root)
calls = {"adb": 0, "model_secret": 0, "network": 0}


def forbidden(name):
    '''Build one side-effect canary.

    Args:
        name: Counter key to increment if a forbidden boundary is crossed.

    Returns:
        A callable that always fails after recording the invocation.
    '''
    def canary(*args, **kwargs):
        '''Reject one forbidden installed-wheel side effect.'''
        del args, kwargs
        calls[name] += 1
        raise AssertionError(f"forbidden {name} side effect")

    return canary


def request_profiles(profiles, suffix):
    '''Start one installed HTTP service and read its safe profile directory.

    Args:
        profiles: Explicit server-owned profile resolver.
        suffix: Isolated database/workspace suffix.

    Returns:
        Decoded safe device-profile page.
    '''
    workspace = workdir / suffix
    workspace.mkdir()
    database = workspace / "studio.sqlite3"
    repository = SQLiteAgentDocumentRepository(database)
    catalog = build_studio_component_catalog()
    authoring = StudioApplicationService(catalog=catalog, repository=repository)
    composition = build_default_studio_benchmark_composition(
        workspace,
        agents=repository,
        profiles=profiles,
        contract_catalog=catalog.node_contract_catalog(),
        sources=(),
        include_installed=False,
        database_path=database,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        benchmark_composition=composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        return composition.service.device_profiles().model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        composition.shutdown()


device_profile_module.AndroidDevice.list_device_states = classmethod(
    forbidden("adb")
)
run_execution.ProductionComponentResolverFactory.create = forbidden(
    "model_secret"
)
socket.create_connection = forbidden("network")

empty = request_profiles(AndroidDeviceProfileResolver(), "empty")
assert empty == {"schemaVersion": 1, "items": []}

config = workdir / "trusted-device-profiles.json"
config.write_text(
    json.dumps(
        {
            "schemaVersion": 1,
            "profiles": [
                {
                    "deviceProfileId": "configured-android",
                    "label": "Configured Android",
                    "platform": "android",
                    "target": {"kind": "adb_serial", "serial": "SERIAL-CANARY-1"},
                }
            ],
        }
    ),
    encoding="utf-8",
)
loaded = load_android_device_profiles(config)
assert loaded.safe_profiles()[0].device_profile_id == "configured-android"

fake_device = object()
fake_profiles = AndroidDeviceProfileResolver(
    {
        "fake-contract": AndroidDeviceProfile(
            "fake-contract",
            label="Fake Contract",
            device=fake_device,
        )
    }
)
fake = request_profiles(fake_profiles, "fake")
assert fake["items"] == [
    {
        "deviceProfileId": "fake-contract",
        "label": "Fake Contract",
        "platform": "android",
        "availability": "configured",
    }
]
session = resolve_exact_android_session(fake_profiles.resolve("fake-contract"))
assert session.device is fake_device
assert session.environment_candidate == "fake_device"
serialized = json.dumps({"empty": empty, "fake": fake}, sort_keys=True)
assert "SERIAL-CANARY-1" not in serialized
assert str(config) not in serialized
assert calls == {"adb": 0, "model_secret": 0, "network": 0}
print(
    json.dumps(
        {
            "adbCalls": calls["adb"],
            "emptyProfiles": len(empty["items"]),
            "fakeEnvironment": session.environment_candidate,
            "fakeProfiles": len(fake["items"]),
            "modelSecretCalls": calls["model_secret"],
            "networkCalls": calls["network"],
            "sourceIsInstalledWheel": True,
        },
        sort_keys=True,
    )
)
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(scenario)],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert json.loads(completed.stdout) == {
        "adbCalls": 0,
        "emptyProfiles": 0,
        "fakeEnvironment": "fake_device",
        "fakeProfiles": 1,
        "modelSecretCalls": 0,
        "networkCalls": 0,
        "sourceIsInstalledWheel": True,
    }
