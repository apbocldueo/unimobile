"""Exact-target and cross-product authority tests for Studio execution."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import pytest

from zhixing.devices.base import ConnectionType, DeviceInfo
from zhixing.runtime import SimpleCancellationSignal
from zhixing.studio import benchmark_execution, device_profiles
from zhixing.studio.benchmark_evidence import LocalStudioBenchmarkEvidenceStore
from zhixing.studio.benchmark_execution import StudioBenchmarkExecutionAdapter
from zhixing.studio.device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    ResolvedAndroidDeviceSession,
    resolve_exact_android_session,
)
from zhixing.studio.run_execution import (
    DeviceLeaseRegistry,
    ProductionComponentResolverFactory,
)

from .test_benchmark_execution_worker import FakeBenchmarkDevice
from .test_benchmark_experiment_resource import _resource_service


def _state(serial: str, status: str) -> DeviceInfo:
    """Build one exact ADB state fixture.

    Args:
        serial: Private device identifier.
        status: ADB readiness state.

    Raises:
        None.

    Returns:
        Typed device-state fixture.
    """
    return DeviceInfo(
        device_id=serial,
        platform="android",
        status=status,
        connection_type=ConnectionType.USB,
    )


@pytest.mark.parametrize(
    ("states", "expected"),
    (
        ((), "studio.device.target_missing"),
        ((_state("exact-device", "offline"),), "studio.device.target_offline"),
        (
            (_state("exact-device", "unauthorized"),),
            "studio.device.target_unauthorized",
        ),
        ((_state("exact-device", "recovery"),), "studio.device.target_invalid"),
    ),
)
def test_exact_target_rejects_unready_states_without_leaking_serial(
    monkeypatch: pytest.MonkeyPatch,
    states: tuple[DeviceInfo, ...],
    expected: str,
) -> None:
    """Map exact-target state to bounded safe authority codes."""
    monkeypatch.setattr(
        device_profiles.AndroidDevice,
        "list_device_states",
        classmethod(lambda cls: list(states)),
    )
    profile = AndroidDeviceProfile("local-android", serial="exact-device")
    with pytest.raises(Exception) as unavailable:
        resolve_exact_android_session(profile)
    assert getattr(unavailable.value, "code", "") == expected
    assert "exact-device" not in str(unavailable.value)


def test_exact_target_ignores_other_ready_devices_and_constructs_pinned_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Construct only the exact serial when several unrelated devices are ready."""

    class ExactSession:
        """Minimal Android constructor spy for authority verification."""

        created: list[str] = []

        @classmethod
        def list_device_states(cls) -> list[DeviceInfo]:
            """Return two ready devices without invoking ADB.

            Returns:
                Two deterministic ready states.
            """
            return [
                _state("other-device", "device"),
                _state("exact-device", "device"),
            ]

        def __init__(self, serial: str) -> None:
            """Record the exact constructor target.

            Args:
                serial: Explicit target selected by authority.

            Returns:
                None.
            """
            self.serial = serial
            self.created.append(serial)

    monkeypatch.setattr(device_profiles, "AndroidDevice", ExactSession)
    profile = AndroidDeviceProfile("local-android", serial="exact-device")
    session = resolve_exact_android_session(profile)
    assert session.serial == "exact-device"
    assert ExactSession.created == ["exact-device"]


def test_binding_drift_and_missing_historical_binding_precede_runtime(
    tmp_path: Path,
) -> None:
    """Fail accepted work before fake device/Core actions on authority loss."""
    service, repository, payload = _resource_service(tmp_path)
    original_device = FakeBenchmarkDevice()
    original_profiles = AndroidDeviceProfileResolver(
        {
            "local-android": AndroidDeviceProfile(
                "local-android",
                device=original_device,
            )
        }
    )
    service.definitions.profiles = original_profiles
    created = service.create_experiment(payload).experiment
    owner = "authority-test-owner"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    changed_device = FakeBenchmarkDevice()
    changed_profiles = AndroidDeviceProfileResolver(
        {
            "local-android": AndroidDeviceProfile(
                "local-android",
                device=changed_device,
            )
        }
    )
    drifted = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=ProductionComponentResolverFactory(),
        evidence=LocalStudioBenchmarkEvidenceStore(tmp_path / "drift-evidence"),
        profiles=changed_profiles,
    )
    with pytest.raises(Exception) as drift:
        drifted.execute(
            drifted.prepare(claimed),
            cancellation=SimpleCancellationSignal(),
            event_sink=lambda event: None,
        )
    assert getattr(drift.value, "code", "") == "studio.device.binding_drifted"
    assert changed_device.calls == []

    second_service, second_repository, second_payload = _resource_service(
        tmp_path / "historical"
    )
    historical = second_service.create_experiment(second_payload).experiment
    with sqlite3.connect(second_repository.database_path) as connection:
        connection.execute(
            "DELETE FROM studio_benchmark_experiment_bindings "
            "WHERE experiment_id = ?",
            (historical.experiment_id,),
        )
    second_repository.enroll_accepted_experiment(
        historical.experiment_id,
        process_owner_id=owner,
    )
    unbound = second_repository.claim_experiment(
        historical.experiment_id,
        process_owner_id=owner,
        timestamp=historical.accepted_at + 1,
    )
    adapter = StudioBenchmarkExecutionAdapter(
        definitions=second_service.definitions,
        components=ProductionComponentResolverFactory(),
        evidence=LocalStudioBenchmarkEvidenceStore(tmp_path / "unbound-evidence"),
        profiles=second_service.definitions.profiles,
    )
    with pytest.raises(Exception) as missing:
        adapter.execute(
            adapter.prepare(unbound),
            cancellation=SimpleCancellationSignal(),
            event_sink=lambda event: None,
        )
    assert getattr(missing.value, "code", "") == "studio.device.profile_unbound"


def test_target_aliases_contend_across_run_and_benchmark_owners() -> None:
    """Use one private target key regardless of public product/profile names."""
    fake = object()
    profiles = AndroidDeviceProfileResolver(
        {
            "run-profile": AndroidDeviceProfile("run-profile", device=fake),
            "benchmark-profile": AndroidDeviceProfile(
                "benchmark-profile",
                device=fake,
            ),
        }
    )
    registry = DeviceLeaseRegistry()
    run_key = profiles.resolve("run-profile").target_key
    benchmark_key = profiles.resolve("benchmark-profile").target_key
    assert run_key == benchmark_key
    with registry.acquire(run_key, "run-owner"):
        with pytest.raises(Exception) as busy:
            with registry.acquire(benchmark_key, "benchmark-owner"):
                pass
    assert getattr(busy.value, "code", "") == "studio.device.target_busy"


def test_cancellation_after_session_construction_precedes_core(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recheck cancellation after authority but before Benchmark Runtime."""
    service, repository, payload = _resource_service(tmp_path)
    device = FakeBenchmarkDevice()
    profiles = AndroidDeviceProfileResolver(
        {"local-android": AndroidDeviceProfile("local-android", device=device)}
    )
    service.definitions.profiles = profiles
    created = service.create_experiment(payload).experiment
    owner = "authority-cancel-owner"
    repository.enroll_accepted_experiment(
        created.experiment_id,
        process_owner_id=owner,
    )
    claimed = repository.claim_experiment(
        created.experiment_id,
        process_owner_id=owner,
        timestamp=created.accepted_at + 1,
    )
    adapter = StudioBenchmarkExecutionAdapter(
        definitions=service.definitions,
        components=ProductionComponentResolverFactory(),
        evidence=LocalStudioBenchmarkEvidenceStore(tmp_path / "cancel-evidence"),
        profiles=profiles,
    )
    signal = SimpleCancellationSignal()

    def cancel_during_authority(
        profile: AndroidDeviceProfile,
        *,
        pinned_binding_fingerprint: str | None = None,
    ) -> ResolvedAndroidDeviceSession:
        """Resolve the fake session and win cancellation at the boundary.

        Args:
            profile: Current fake authority.
            pinned_binding_fingerprint: Accepted authority identity.

        Returns:
            Resolved fake session after requesting cancellation.
        """
        del pinned_binding_fingerprint
        signal.cancel()
        return ResolvedAndroidDeviceSession(
            profile_id=profile.profile_id,
            target_key=profile.target_key,
            serial=None,
            device=profile.device,
            environment_candidate="fake_device",
        )

    monkeypatch.setattr(
        benchmark_execution,
        "resolve_exact_android_session",
        cancel_during_authority,
    )
    with pytest.raises(Exception, match="cancelled before Benchmark Runtime"):
        adapter.execute(
            adapter.prepare(claimed),
            cancellation=signal,
            event_sink=lambda event: None,
        )
    assert device.calls == []
