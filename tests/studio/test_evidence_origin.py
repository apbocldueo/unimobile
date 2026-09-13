"""Compatibility tests for two-axis TaskResult and Replay provenance."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from zhixing.studio.benchmark_experiment_models import StudioBenchmarkTaskResultV1
from zhixing.studio.evidence_origin import (
    StudioExecutionEvidenceOriginV1,
    replay_import_origin,
)
from zhixing.studio.replay_models import ReplayEvidenceEnvelope, ReplayListItem
from zhixing.studio.run_safety import sanitize_runtime_value

from .test_benchmark_execution_worker import _result_for
from .test_benchmark_experiment_resource import _resource_service
from .test_replay_backend import _envelope


def test_fake_origin_keeps_acquisition_and_environment_independent() -> None:
    """Represent fake Contract evidence without granting real-device proof."""
    origin = StudioExecutionEvidenceOriginV1.from_runtime(
        acquisition="contract_fixture",
        environment="fake_device",
        device_profile_id="fake-device",
        device_provenance={
            "platform": "android",
            "locale": "en-US",
            "orientation": "portrait",
            "apps_verifiable": True,
            "checks": {
                "platform": True,
                "locale": True,
                "orientation": True,
                "apps": True,
            },
            "device_id": "must-be-dropped",
        },
    )
    encoded = json.dumps(origin.model_dump(mode="json", by_alias=True))
    assert origin.acquisition == "contract_fixture"
    assert origin.environment == "fake_device"
    assert origin.real_device_evidence is False
    assert "must-be-dropped" not in encoded
    assert [item.name for item in origin.device_checks] == [
        "platform",
        "locale",
        "orientation",
        "apps",
    ]


@pytest.mark.parametrize(
    "payload",
    (
        {"acquisition": "screenshot_guess", "environment": "unverified"},
        {"acquisition": "fresh_execution", "environment": "configured"},
        {
            "acquisition": "fresh_execution",
            "environment": "real_android",
            "realDeviceEvidence": False,
        },
        {
            "acquisition": "replay_projection",
            "environment": "real_android",
            "realDeviceEvidence": True,
        },
    ),
)
def test_origin_rejects_unknown_or_inferred_real_device_claims(
    payload: dict[str, object],
) -> None:
    """Reject unknown axes and booleans not derived from exact source facts."""
    with pytest.raises(ValidationError):
        StudioExecutionEvidenceOriginV1.model_validate(payload)


def test_task_result_round_trip_preserves_explicit_origin(tmp_path) -> None:
    """Keep safe origin in strict TaskResult JSON and restart-compatible parsing."""
    service, repository, payload = _resource_service(tmp_path)
    experiment = service.create_experiment(payload).experiment
    repository.enroll_accepted_experiment(
        experiment.experiment_id,
        process_owner_id="origin-owner",
    )
    claimed = repository.claim_experiment(
        experiment.experiment_id,
        process_owner_id="origin-owner",
        timestamp=experiment.accepted_at + 1,
    )
    result, _fingerprint = _result_for(claimed.task_runs[0])
    explicit = result.model_copy(
        update={
            "evidence_origin": StudioExecutionEvidenceOriginV1(
                acquisition="contract_fixture",
                environment="fake_device",
                device_profile_id="local-android",
            )
        }
    )
    reparsed = StudioBenchmarkTaskResultV1.model_validate_json(
        explicit.model_dump_json(by_alias=True)
    )
    assert reparsed.evidence_origin == explicit.evidence_origin
    assert reparsed.evidence_origin.real_device_evidence is False


def test_legacy_replay_envelope_and_list_item_derive_safe_origin() -> None:
    """Read old provenance labels while defaulting absent environment safely."""
    envelope = _envelope("legacy-origin-run")
    payload = envelope.model_dump(
        mode="json",
        by_alias=True,
        exclude={"evidence_origin"},
    )
    legacy = ReplayEvidenceEnvelope.model_validate(payload)
    assert legacy.provenance == "fake_contract_fixture"
    assert legacy.evidence_origin.acquisition == "contract_fixture"
    assert legacy.evidence_origin.environment == "fake_device"
    item = ReplayListItem.model_validate(
        {
            "runId": "native-old-run",
            "agentId": "agent-old",
            "agentStatus": "success",
            "provenance": "native_benchmark_task_run",
            "integrityState": "complete",
            "evidenceCompleteness": 100,
            "importedAt": 1,
        }
    )
    assert item.evidence_origin.acquisition == "replay_projection"
    assert item.evidence_origin.environment == "unverified"


def test_native_projection_and_import_change_only_acquisition() -> None:
    """Preserve source environment across Replay transport transformations."""
    source = StudioExecutionEvidenceOriginV1(
        acquisition="fresh_execution",
        environment="real_android",
        real_device_evidence=True,
    )
    projected = source.with_acquisition("replay_projection")
    assert projected.environment == "real_android"
    assert projected.real_device_evidence is False
    imported = replay_import_origin("legacy_benchmark_import")
    assert imported.acquisition == "imported_excerpt"
    assert imported.environment == "unverified"
    assert imported.real_device_evidence is False


def test_authority_canaries_are_redacted_by_shared_runtime_safety() -> None:
    """Remove private authority from diagnostics and nested runtime mappings."""

    class LiveHandle:
        """Represent an unsafe runtime-only target handle."""

        def __repr__(self) -> str:
            """Return a deliberately unsafe representation.

            Returns:
                Canary-bearing text that must never be consulted.
            """
            return "<live-handle-canary>"

    canaries = (
        "SERIAL-RAW-CANARY",
        "/private/config/profile-canary.json",
        "sha256:binding-fingerprint-canary",
        "adb -s SERIAL-RAW-CANARY shell getprop",
        "live-handle-canary",
    )
    safe = sanitize_runtime_value(
        {
            "serial": canaries[0],
            "configuration_path": canaries[1],
            "binding_fingerprint": canaries[2],
            "diagnostic": f"authority failed: {canaries[3]}",
            "device_handle": LiveHandle(),
        }
    )
    encoded = json.dumps(safe.value, sort_keys=True)
    assert safe.redacted is True
    for canary in canaries:
        assert canary not in encoded
