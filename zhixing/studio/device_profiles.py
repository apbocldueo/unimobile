"""Trusted Android profile configuration and private target authority."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Mapping

from pydantic import Field, field_validator, model_validator

from .benchmark_models import StudioDeviceProfileV1
from .models import StudioModel
from .run_errors import StudioRunValidationError
from zhixing.devices.android import AndroidDevice


MAX_DEVICE_PROFILE_CONFIG_BYTES = 64 * 1024
MAX_DEVICE_PROFILES = 64
DEVICE_PROFILE_CONFIG_ENV = "ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG"
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_ADB_SERIAL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class DeviceAuthorityCode(str, Enum):
    """Stable public-safe codes for private target authority failures."""

    PROFILE_UNKNOWN = "studio.device.profile_unknown"
    PROFILE_UNBOUND = "studio.device.profile_unbound"
    BINDING_DRIFTED = "studio.device.binding_drifted"
    TARGET_MISSING = "studio.device.target_missing"
    TARGET_OFFLINE = "studio.device.target_offline"
    TARGET_UNAUTHORIZED = "studio.device.target_unauthorized"
    TARGET_BUSY = "studio.device.target_busy"
    TARGET_INVALID = "studio.device.target_invalid"


class AndroidProfileConfigurationError(ValueError):
    """Reject an unsafe local profile file with a bounded diagnostic."""

    def __init__(self, code: str, message: str) -> None:
        """Create a configuration error without retaining source data.

        Args:
            code: Stable machine-readable configuration error code.
            message: Bounded path/content-free reader message.

        Raises:
            None.

        Returns:
            None.
        """
        safe_message = str(message).replace("\r", " ").replace("\n", " ")[:500]
        super().__init__(safe_message)
        self.code = str(code)[:160]
        self.message = safe_message


class AndroidAdbSerialTargetV1(StudioModel):
    """Strict production target containing one exact private ADB serial."""

    kind: Literal["adb_serial"] = "adb_serial"
    serial: str = Field(min_length=1, max_length=128)

    @field_validator("serial")
    @classmethod
    def _safe_serial(cls, value: str) -> str:
        """Validate an exact ADB serial without normalizing its identity.

        Args:
            value: Candidate private ADB serial.

        Raises:
            ValueError: The value is blank, path-like, or command-like.

        Returns:
            The exact validated serial.
        """
        if _ADB_SERIAL.fullmatch(value) is None:
            raise ValueError("invalid exact ADB serial")
        return value


class AndroidProfileConfigEntryV1(StudioModel):
    """One safe public profile identity and its private production target."""

    device_profile_id: str
    label: str = Field(min_length=1, max_length=255)
    platform: Literal["android"] = "android"
    target: AndroidAdbSerialTargetV1

    @field_validator("device_profile_id")
    @classmethod
    def _stable_profile_id(cls, value: str) -> str:
        """Validate one safe browser-facing profile identity.

        Args:
            value: Candidate opaque profile identity.

        Raises:
            ValueError: The identity is unstable or serial-like.

        Returns:
            The validated identity.
        """
        if _STABLE_ID.fullmatch(value) is None:
            raise ValueError("device profile identity must be stable")
        if value.lower().replace("-", "_") in {
            "serial",
            "adb_serial",
            "device_serial",
        }:
            raise ValueError("raw serial is not a profile identity")
        return value


class AndroidProfileConfigFileV1(StudioModel):
    """Bounded version-1 trusted Android profile configuration."""

    schema_version: Literal[1] = 1
    profiles: tuple[AndroidProfileConfigEntryV1, ...] = Field(
        default=(),
        max_length=MAX_DEVICE_PROFILES,
    )

    @model_validator(mode="after")
    def _unique_authority(self) -> "AndroidProfileConfigFileV1":
        """Reject duplicate public identities and private exact targets.

        Args:
            None.

        Raises:
            ValueError: A profile ID or normalized target is repeated.

        Returns:
            The validated configuration.
        """
        profile_ids = [item.device_profile_id for item in self.profiles]
        targets = [item.target.serial for item in self.profiles]
        if len(profile_ids) != len(set(profile_ids)):
            raise ValueError("device profile identities must be unique")
        if len(targets) != len(set(targets)):
            raise ValueError("exact device targets must be unique")
        return self


@dataclass(frozen=True)
class AndroidPrivateBinding:
    """Server-private exact target authority that is never serialized publicly."""

    profile_id: str
    target_kind: Literal["adb_serial", "injected_device"]
    environment_candidate: Literal["real_android", "fake_device"]
    binding_fingerprint: str
    target_key: str
    serial: str | None = None
    device: Any | None = None


@dataclass(frozen=True)
class ResolvedAndroidDeviceSession:
    """Lease-scoped exact runtime session with safe authority coordinates."""

    profile_id: str
    target_key: str
    serial: str | None
    device: Any
    environment_candidate: Literal["real_android", "fake_device"]


@dataclass(frozen=True)
class AndroidDeviceProfile:
    """Internal profile joining safe metadata to one private exact binding."""

    profile_id: str
    serial: str | None = None
    device: Any | None = None
    label: str = ""
    platform: Literal["android"] = "android"
    binding_fingerprint: str = ""
    target_key: str = ""
    environment_candidate: Literal["real_android", "fake_device"] | None = None

    def __post_init__(self) -> None:
        """Validate and derive private identities for programmatic profiles.

        Args:
            None.

        Raises:
            ValueError: Safe identity or private target is invalid.

        Returns:
            None.
        """
        if _STABLE_ID.fullmatch(self.profile_id) is None:
            raise ValueError("device profile identity must be stable")
        if self.platform != "android":
            raise ValueError("only Android device profiles are supported")
        if self.device is None and self.serial is None:
            raise ValueError("production device profile requires an exact target")
        # Programmatic profiles are a compatibility/test composition surface.
        # Production file entries are validated by AndroidAdbSerialTargetV1;
        # exact runtime authority validates again before constructing a device.
        if self.serial is not None and (not self.serial or len(self.serial) > 256):
            raise ValueError("invalid programmatic exact target")
        environment = self.environment_candidate or (
            "fake_device" if self.device is not None else "real_android"
        )
        target_kind: Literal["adb_serial", "injected_device"] = (
            "injected_device" if self.device is not None else "adb_serial"
        )
        private_target = (
            f"object:{id(self.device)}"
            if self.device is not None
            else str(self.serial)
        )
        if not self.binding_fingerprint:
            object.__setattr__(
                self,
                "binding_fingerprint",
                _private_digest(
                    {
                        "schemaVersion": 1,
                        "profileId": self.profile_id,
                        "platform": self.platform,
                        "targetKind": target_kind,
                        "target": private_target,
                    }
                ),
            )
        if not self.target_key:
            object.__setattr__(
                self,
                "target_key",
                _private_digest(
                    {
                        "schemaVersion": 1,
                        "targetKind": target_kind,
                        "target": private_target,
                    }
                ),
            )
        object.__setattr__(self, "environment_candidate", environment)

    @property
    def private_binding(self) -> AndroidPrivateBinding:
        """Return the non-serializable authority view for persistence/execution.

        Args:
            None.

        Raises:
            None.

        Returns:
            The exact private binding for this profile.
        """
        return AndroidPrivateBinding(
            profile_id=self.profile_id,
            target_kind=(
                "injected_device" if self.device is not None else "adb_serial"
            ),
            environment_candidate=self.environment_candidate or "fake_device",
            binding_fingerprint=self.binding_fingerprint,
            target_key=self.target_key,
            serial=self.serial,
            device=self.device,
        )


class AndroidDeviceProfileResolver:
    """Resolve safe identities to trusted private target authority."""

    def __init__(
        self,
        profiles: Mapping[str, AndroidDeviceProfile] | None = None,
    ) -> None:
        """Configure explicit profiles without device discovery.

        Args:
            profiles: Complete explicit profile mapping; omitted means empty.

        Raises:
            ValueError: A key disagrees with its profile or authority aliases.

        Returns:
            None.
        """
        selected = dict(profiles) if profiles is not None else {}
        if any(key != profile.profile_id for key, profile in selected.items()):
            raise ValueError("Android device profile key is inconsistent")
        # Trusted JSON rejects aliases. Programmatic/test composition keeps
        # them so target-key leasing can prove defense-in-depth across names.
        self._profiles = selected

    def resolve(self, profile_id: str) -> AndroidDeviceProfile:
        """Resolve one profile without serializing its private target.

        Args:
            profile_id: Browser-facing safe profile identity.

        Raises:
            StudioRunValidationError: The profile is unknown.

        Returns:
            Internal exact profile authority.
        """
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise StudioRunValidationError(
                DeviceAuthorityCode.PROFILE_UNKNOWN.value,
                "Selected Android device profile is unavailable",
            )
        return profile

    def binding_authority(self, profile_id: str) -> AndroidPrivateBinding:
        """Return private static binding facts for accepted-work pinning.

        Args:
            profile_id: Safe selected profile identity.

        Raises:
            StudioRunValidationError: The profile is unknown.

        Returns:
            Private immutable binding authority.
        """
        profile = self._profiles.get(profile_id)
        if profile is None:
            raise StudioRunValidationError(
                DeviceAuthorityCode.PROFILE_UNKNOWN.value,
                "Selected Android device profile is unavailable",
            )
        return profile.private_binding

    def contains(self, profile_id: str) -> bool:
        """Report whether static authority exists without runtime resolution.

        Args:
            profile_id: Browser-facing safe profile identity.

        Raises:
            None.

        Returns:
            True when the trusted mapping contains the identity.
        """
        return profile_id in self._profiles

    def safe_profiles(self) -> tuple[StudioDeviceProfileV1, ...]:
        """Project only safe descriptors without ADB or private target facts.

        Args:
            None.

        Raises:
            ValueError: A descriptor violates the public DTO.

        Returns:
            Stable safe descriptors ordered by profile identity.
        """
        return tuple(
            StudioDeviceProfileV1(
                device_profile_id=profile.profile_id,
                label=profile.label or profile.profile_id,
                platform=profile.platform,
            )
            for profile in sorted(
                self._profiles.values(),
                key=lambda item: item.profile_id,
            )
        )


def _private_digest(value: Mapping[str, object]) -> str:
    """Derive a private canonical SHA-256 identity.

    Args:
        value: Private normalized identity facts.

    Raises:
        TypeError: A fact is not JSON serializable.

    Returns:
        Prefixed lowercase SHA-256 identity.
    """
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _configured_profile(entry: AndroidProfileConfigEntryV1) -> AndroidDeviceProfile:
    """Build one private production profile from validated configuration.

    Args:
        entry: Strict validated profile configuration.

    Raises:
        ValueError: Derived profile invariants fail.

    Returns:
        Internal exact production profile.
    """
    serial = entry.target.serial
    return AndroidDeviceProfile(
        profile_id=entry.device_profile_id,
        serial=serial,
        label=entry.label,
        platform=entry.platform,
        environment_candidate="real_android",
        binding_fingerprint=_private_digest(
            {
                "schemaVersion": 1,
                "profileId": entry.device_profile_id,
                "platform": entry.platform,
                "targetKind": entry.target.kind,
                "target": serial,
            }
        ),
        target_key=_private_digest(
            {
                "schemaVersion": 1,
                "targetKind": entry.target.kind,
                "target": serial,
            }
        ),
    )


def load_android_device_profiles(
    path: str | os.PathLike[str] | None,
) -> AndroidDeviceProfileResolver:
    """Load a bounded trusted profile file without touching ADB or devices.

    Args:
        path: Trusted local JSON path; ``None`` yields an empty resolver.

    Raises:
        AndroidProfileConfigurationError: The file or strict schema is invalid.

    Returns:
        Explicit static profile resolver.
    """
    if path is None:
        return AndroidDeviceProfileResolver()
    candidate = Path(path).expanduser()
    try:
        if not candidate.is_file():
            raise AndroidProfileConfigurationError(
                "studio.device.config_not_regular_file",
                "Android profile configuration must be a regular file",
            )
        size = candidate.stat().st_size
        if size > MAX_DEVICE_PROFILE_CONFIG_BYTES:
            raise AndroidProfileConfigurationError(
                "studio.device.config_too_large",
                "Android profile configuration exceeds the size limit",
            )
        raw = candidate.read_bytes()
    except AndroidProfileConfigurationError:
        raise
    except OSError as error:
        raise AndroidProfileConfigurationError(
            "studio.device.config_unreadable",
            "Android profile configuration cannot be read",
        ) from error
    try:
        config = AndroidProfileConfigFileV1.model_validate_json(raw)
    except Exception as error:
        raise AndroidProfileConfigurationError(
            "studio.device.config_invalid",
            "Android profile configuration is invalid",
        ) from error
    profiles = {
        entry.device_profile_id: _configured_profile(entry)
        for entry in config.profiles
    }
    return AndroidDeviceProfileResolver(profiles)


def resolve_device_profile_config_path(
    cli_path: Path | None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    """Apply CLI-over-environment precedence without logging private paths.

    Args:
        cli_path: Explicit command-line path, when supplied.
        environment: Environment mapping override for deterministic tests.

    Raises:
        None.

    Returns:
        Selected path or ``None`` when neither source is configured.
    """
    if cli_path is not None:
        return cli_path
    values = environment if environment is not None else os.environ
    raw = values.get(DEVICE_PROFILE_CONFIG_ENV, "").strip()
    return Path(raw) if raw else None


def resolve_exact_android_session(
    profile: AndroidDeviceProfile,
    *,
    pinned_binding_fingerprint: str | None = None,
) -> ResolvedAndroidDeviceSession:
    """Verify and construct only the selected exact target inside its lease.

    Args:
        profile: Current trusted profile authority.
        pinned_binding_fingerprint: Accepted-work authority to compare, if any.

    Raises:
        StudioRunValidationError: Authority drifted or target is not ready.

    Returns:
        Lease-scoped exact device session.
    """
    if (
        pinned_binding_fingerprint is not None
        and profile.binding_fingerprint != pinned_binding_fingerprint
    ):
        raise StudioRunValidationError(
            DeviceAuthorityCode.BINDING_DRIFTED.value,
            "Selected Android device binding changed after acceptance",
        )
    if profile.device is not None:
        return ResolvedAndroidDeviceSession(
            profile_id=profile.profile_id,
            target_key=profile.target_key,
            serial=None,
            device=profile.device,
            environment_candidate="fake_device",
        )
    serial = profile.serial
    if serial is None:
        raise StudioRunValidationError(
            DeviceAuthorityCode.PROFILE_UNBOUND.value,
            "Selected Android device profile has no exact target",
        )
    if _ADB_SERIAL.fullmatch(serial) is None:
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_INVALID.value,
            "Selected Android device target is invalid",
        )
    try:
        states = AndroidDevice.list_device_states()
    except Exception as error:
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_MISSING.value,
            "Selected Android device target is unavailable",
        ) from error
    target = next((item for item in states if item.device_id == serial), None)
    if target is None:
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_MISSING.value,
            "Selected Android device target is unavailable",
        )
    if target.status == "offline":
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_OFFLINE.value,
            "Selected Android device target is offline",
        )
    if target.status == "unauthorized":
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_UNAUTHORIZED.value,
            "Selected Android device target is unauthorized",
        )
    if target.status != "device":
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_INVALID.value,
            "Selected Android device target is not ready",
        )
    try:
        device = AndroidDevice(serial=serial)
    except Exception as error:
        raise StudioRunValidationError(
            DeviceAuthorityCode.TARGET_INVALID.value,
            "Selected Android device session could not be constructed",
        ) from error
    return ResolvedAndroidDeviceSession(
        profile_id=profile.profile_id,
        target_key=profile.target_key,
        serial=serial,
        device=device,
        environment_candidate="real_android",
    )


__all__ = [
    "AndroidAdbSerialTargetV1",
    "AndroidDeviceProfile",
    "AndroidDeviceProfileResolver",
    "AndroidPrivateBinding",
    "AndroidProfileConfigEntryV1",
    "AndroidProfileConfigFileV1",
    "AndroidProfileConfigurationError",
    "DEVICE_PROFILE_CONFIG_ENV",
    "DeviceAuthorityCode",
    "MAX_DEVICE_PROFILE_CONFIG_BYTES",
    "MAX_DEVICE_PROFILES",
    "ResolvedAndroidDeviceSession",
    "load_android_device_profiles",
    "resolve_device_profile_config_path",
    "resolve_exact_android_session",
]
