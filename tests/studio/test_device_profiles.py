"""Contract tests for trusted Studio Android profile configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from zhixing.devices.android import AndroidDevice
from zhixing.studio.device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    AndroidProfileConfigFileV1,
    AndroidProfileConfigurationError,
    MAX_DEVICE_PROFILE_CONFIG_BYTES,
    load_android_device_profiles,
    resolve_device_profile_config_path,
)


def _write_config(path: Path, profiles: list[dict[str, object]]) -> Path:
    """Write one JSON fixture through the test-owned filesystem boundary.

    Args:
        path: Destination fixture path.
        profiles: Strict profile entries.

    Raises:
        OSError: The temporary fixture cannot be written.

    Returns:
        The written path.
    """
    path.write_text(
        json.dumps({"schemaVersion": 1, "profiles": profiles}),
        encoding="utf-8",
    )
    return path


def _entry(
    profile_id: str = "local-android",
    serial: str = "emulator-5554",
) -> dict[str, object]:
    """Build one valid strict configuration entry.

    Args:
        profile_id: Safe public identity.
        serial: Private exact ADB target.

    Raises:
        None.

    Returns:
        JSON-compatible configuration entry.
    """
    return {
        "deviceProfileId": profile_id,
        "label": "Local Android",
        "platform": "android",
        "target": {"kind": "adb_serial", "serial": serial},
    }


def test_valid_profile_file_is_static_safe_and_side_effect_free(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load/list one exact target without invoking any ADB discovery."""
    monkeypatch.setattr(
        AndroidDevice,
        "list_device_states",
        lambda: (_ for _ in ()).throw(AssertionError("ADB must remain unused")),
    )
    resolver = load_android_device_profiles(
        _write_config(tmp_path / "profiles.json", [_entry()])
    )
    safe = resolver.safe_profiles()
    assert [item.model_dump(mode="json", by_alias=True) for item in safe] == [
        {
            "deviceProfileId": "local-android",
            "label": "Local Android",
            "platform": "android",
            "availability": "configured",
        }
    ]
    private = resolver.binding_authority("local-android")
    assert private.serial == "emulator-5554"
    assert private.environment_candidate == "real_android"
    assert private.binding_fingerprint.startswith("sha256:")
    assert "emulator-5554" not in private.binding_fingerprint
    assert "emulator-5554" not in private.target_key


def test_no_config_and_empty_mapping_publish_no_implicit_profile() -> None:
    """Keep no-device serving empty instead of synthesizing local-android."""
    assert load_android_device_profiles(None).safe_profiles() == ()
    assert AndroidDeviceProfileResolver({}).safe_profiles() == ()
    with pytest.raises(Exception) as unknown:
        AndroidDeviceProfileResolver().resolve("local-android")
    assert getattr(unknown.value, "code", "") == "studio.device.profile_unknown"


@pytest.mark.parametrize(
    "payload",
    (
        {"schemaVersion": 2, "profiles": []},
        {"schemaVersion": 1, "profiles": [], "unknown": True},
        {"schemaVersion": 1, "profiles": [{**_entry(), "platform": "harmonyos"}]},
        {
            "schemaVersion": 1,
            "profiles": [
                {
                    "deviceProfileId": "local-android",
                    "label": "Local Android",
                    "platform": "android",
                    "target": {"kind": "implicit"},
                }
            ],
        },
        {"schemaVersion": 1, "profiles": [{**_entry(), "extra": "rejected"}]},
    ),
)
def test_strict_schema_rejects_unknown_or_unsupported_values(
    payload: dict[str, object],
) -> None:
    """Reject schema drift, Harmony, implicit targets, and unknown keys."""
    with pytest.raises(ValidationError):
        AndroidProfileConfigFileV1.model_validate(payload)


def test_loader_rejects_duplicate_ids_targets_and_unsafe_serials(
    tmp_path: Path,
) -> None:
    """Reject all ambiguous authorities with path/content-free diagnostics."""
    fixtures = (
        [_entry(), _entry(serial="device-2")],
        [_entry(), _entry(profile_id="alias")],
        [_entry(serial="/private/device")],
        [_entry(serial="device;adb-shell")],
    )
    for index, entries in enumerate(fixtures):
        path = _write_config(tmp_path / f"invalid-{index}.json", entries)
        with pytest.raises(AndroidProfileConfigurationError) as invalid:
            load_android_device_profiles(path)
        assert invalid.value.code == "studio.device.config_invalid"
        assert str(path) not in invalid.value.message
        assert "emulator-5554" not in invalid.value.message


def test_loader_rejects_non_regular_and_oversized_inputs(tmp_path: Path) -> None:
    """Bound file shape and bytes before parsing trusted configuration."""
    with pytest.raises(AndroidProfileConfigurationError) as directory:
        load_android_device_profiles(tmp_path)
    assert directory.value.code == "studio.device.config_not_regular_file"
    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b" " * (MAX_DEVICE_PROFILE_CONFIG_BYTES + 1))
    with pytest.raises(AndroidProfileConfigurationError) as too_large:
        load_android_device_profiles(oversized)
    assert too_large.value.code == "studio.device.config_too_large"


def test_fake_injection_is_typed_and_target_aliases_share_target_key() -> None:
    """Preserve fake aliases while sharing authority by live object target."""
    fake = object()
    profile = AndroidDeviceProfile("fake-device", device=fake)
    resolver = AndroidDeviceProfileResolver({"fake-device": profile})
    binding = resolver.binding_authority("fake-device")
    assert binding.environment_candidate == "fake_device"
    assert binding.serial is None
    aliases = AndroidDeviceProfileResolver(
        {
            "fake-a": AndroidDeviceProfile("fake-a", device=fake),
            "fake-b": AndroidDeviceProfile("fake-b", device=fake),
        }
    )
    assert aliases.resolve("fake-a").target_key == aliases.resolve(
        "fake-b"
    ).target_key


def test_cli_path_takes_precedence_over_environment_without_normalization(
    tmp_path: Path,
) -> None:
    """Resolve only the configured path source and leave it private."""
    cli = tmp_path / "cli.json"
    environment = {"ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG": "/private/env.json"}
    assert resolve_device_profile_config_path(cli, environment=environment) == cli
    assert resolve_device_profile_config_path(None, environment=environment) == Path(
        "/private/env.json"
    )
    assert resolve_device_profile_config_path(None, environment={}) is None
