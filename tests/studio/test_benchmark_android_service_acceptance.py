"""No-device contracts for Stage 5.6C-1 Android service acceptance."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest
from pydantic import ValidationError

import scripts.studio_benchmark_android_service_acceptance as acceptance
from scripts.studio_benchmark_android_service_acceptance import (
    REQUIRED_ARTIFACT_KINDS,
    REQUIRED_CLAIM_LIMITS,
    ROOT,
    HTTPResponse,
    AcceptanceCommandEvidence,
    AndroidDeviceDeltaEvidence,
    AndroidServiceCausalIdentities,
    AndroidServiceEffectCounters,
    AndroidServiceOutcomeEvidence,
    AndroidServiceScenarioEvidence,
    AndroidServiceScenarioId,
    ManagedArtifactEvidence,
    ManagedPublicationEvidence,
    SafeAcceptanceSelection,
    SafeEvidenceOrigin,
    StudioBenchmarkAndroidServiceAcceptanceSummaryV1,
    TerminalRestartEvidence,
    _assert_safe_json,
    _assert_unchanged_profile_authority,
    _build_scenario_runtime,
    _contains_host_absolute_path,
    _effect_counters,
    _parser,
    _safe_disposable_root,
    _scan_campaign,
    _verify_binary_resource,
    assert_forbidden_values_absent,
    validate_summary_file,
    write_summary,
    run_campaign,
)
from zhixing.benchmark.identity import canonical_hash
from zhixing.studio import SQLiteAgentDocumentRepository
from zhixing.studio.device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
)


def _digest(index: int) -> str:
    """Return one valid deterministic SHA-256 fixture identity.

    Args:
        index: Small deterministic hexadecimal suffix.

    Returns:
        Prefixed 64-character digest.
    """
    return f"sha256:{index:064x}"


def _identities(*, salt: str) -> AndroidServiceCausalIdentities:
    """Create one complete safe causal identity fixture.

    Args:
        salt: Scenario-specific stable suffix.

    Returns:
        Strict identity closure.
    """
    return AndroidServiceCausalIdentities(
        experimentId=f"experiment-{salt}",
        plannedTaskRunId=f"task-run-{salt}",
        coreTaskRunId=f"core-task-run-{salt}",
        agentRunId=f"agent-run-{salt}",
        agentId=f"agent-{salt}",
        agentRevisionId=f"revision-{salt}",
        agentGraphIdentity=_digest(1 if salt == "positive" else 2),
        benchmarkPlanIdentity=_digest(3),
        experimentProtocolIdentity=_digest(4),
        taskInstanceIdentity=_digest(5),
        replayId=f"replay-{salt}",
    )


def _publication(*, salt: str) -> ManagedPublicationEvidence:
    """Create one integrity-closed managed publication fixture.

    Args:
        salt: Scenario-specific safe identity suffix.

    Returns:
        Complete strict publication evidence.
    """
    artifacts = tuple(
        ManagedArtifactEvidence(
            artifactId=f"artifact-{salt}-{index}",
            taskRunId=f"task-run-{salt}",
            kind=kind,
            contentType=(
                "application/zip"
                if kind == "experiment_bundle"
                else "application/json"
            ),
            size=100 + index,
            sha256=_digest(10 + index),
            getVerified=True,
            headVerified=True,
        )
        for index, kind in enumerate(REQUIRED_ARTIFACT_KINDS)
    )
    return ManagedPublicationEvidence(
        artifacts=artifacts,
        reportGetHeadVerified=True,
        bundleGetHeadVerified=True,
        replayResourceVerified=True,
        replayBundleVerified=True,
    )


def _scenario(
    scenario_id: AndroidServiceScenarioId,
) -> AndroidServiceScenarioEvidence:
    """Build one valid positive or controlled-negative scenario.

    Args:
        scenario_id: Required scenario identity.

    Returns:
        Complete validated scenario evidence.
    """
    positive = scenario_id is AndroidServiceScenarioId.POSITIVE
    salt = "positive" if positive else "control"
    return AndroidServiceScenarioEvidence(
        scenarioId=scenario_id,
        verification="passed",
        identities=_identities(salt=salt),
        outcome=AndroidServiceOutcomeEvidence(
            experimentLifecycle="terminal",
            experimentTerminalReason="completed",
            taskRunLifecycle="terminal",
            taskRunTerminalReason="completed",
            agentStatus="success",
            benchmarkOutcome="pass" if positive else "fail",
            evaluatorPass=positive,
            invalidCount=0,
        ),
        effectCounters=AndroidServiceEffectCounters(
            initializerCount=1,
            agentCount=1,
            evaluatorCount=1,
            actionCount=4 if positive else 0,
        ),
        deviceDelta=AndroidDeviceDeltaEvidence(
            addedCount=1 if positive else 0,
            conclusive=True,
        ),
        sourceOrigin=SafeEvidenceOrigin(
            acquisition="fresh_execution",
            environment="real_android",
            realDeviceEvidence=True,
        ),
        replayOrigin=SafeEvidenceOrigin(
            acquisition="replay_projection",
            environment="real_android",
            realDeviceEvidence=False,
        ),
        publication=_publication(salt=salt),
        restart=TerminalRestartEvidence(
            identitiesStable=True,
            eventHighWaterStable=True,
            uniqueTerminalEvent=True,
            sourceEffectCountBefore=17,
            sourceEffectCountAfter=17,
            restartMediaAddedCount=0,
        ),
    )


def _summary() -> StudioBenchmarkAndroidServiceAcceptanceSummaryV1:
    """Build one complete bounded service-level acceptance ledger.

    Returns:
        Strict valid summary fixture.
    """
    return StudioBenchmarkAndroidServiceAcceptanceSummaryV1(
        selection=SafeAcceptanceSelection(deviceProfileId="pixel-safe-profile"),
        scenarios=tuple(_scenario(item) for item in AndroidServiceScenarioId),
        commands=(
            AcceptanceCommandEvidence(
                suiteId="real-android-service-matrix",
                command=(
                    "uv run python scripts/"
                    "studio_benchmark_android_service_acceptance.py run "
                    "--confirm-real-android --device-profile-id <safe-profile-id>"
                ),
                observed="positive PASS and controlled evaluator FAIL",
                verification="passed",
            ),
        ),
        scannedDocuments=24,
        privateValuesFound=0,
        claimLimits=REQUIRED_CLAIM_LIMITS,
    )


def test_summary_is_canonical_bounded_and_round_trips(tmp_path: Path) -> None:
    """Persist and restore the exact two-scenario evidence contract.

    Args:
        tmp_path: Isolated summary destination.
    """
    summary = _summary()
    destination = write_summary(summary, tmp_path / "summary.json")
    assert validate_summary_file(destination) == summary
    assert destination.read_text(encoding="utf-8") == summary.canonical_json() + "\n"
    payload = json.loads(summary.canonical_json())
    assert [item["scenarioId"] for item in payload["scenarios"]] == [
        "real_android_positive",
        "real_android_controlled_fail",
    ]
    assert payload["selection"]["repeats"] == 1


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("selection", "taskId"), "AndroidWorld_7"),
        (("selection", "protocolSeed"), 41),
        (("scenarios", 0, "deviceDelta", "addedCount"), 0),
        (("scenarios", 0, "outcome", "benchmarkOutcome"), "fail"),
        (("scenarios", 1, "outcome", "agentStatus"), "fail"),
        (("scenarios", 1, "outcome", "benchmarkOutcome"), "invalid"),
        (("scenarios", 1, "outcome", "invalidCount"), 1),
        (("scenarios", 1, "deviceDelta", "conclusive"), False),
        (("scenarios", 1, "deviceDelta", "addedCount"), 1),
        (("scenarios", 0, "effectCounters", "initializerCount"), 0),
        (("scenarios", 0, "effectCounters", "actionCount"), 0),
    ),
)
def test_summary_rejects_selection_outcome_and_probe_substitutes(
    path: tuple[str | int, ...],
    value: object,
) -> None:
    """Reject drift, infrastructure substitutes, and inconclusive probes.

    Args:
        path: Nested fixture field to replace.
        value: Invalid replacement value.
    """
    payload = json.loads(_summary().canonical_json())
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("scenarios", 0, "sourceOrigin", "acquisition"), "replay_projection"),
        (("scenarios", 0, "sourceOrigin", "realDeviceEvidence"), False),
        (("scenarios", 0, "replayOrigin", "acquisition"), "fresh_execution"),
        (("scenarios", 0, "replayOrigin", "realDeviceEvidence"), True),
        (("scenarios", 0, "restart", "identitiesStable"), False),
        (("scenarios", 0, "restart", "eventHighWaterStable"), False),
        (("scenarios", 0, "restart", "uniqueTerminalEvent"), False),
        (("scenarios", 0, "restart", "sourceEffectCountAfter"), 18),
        (("scenarios", 0, "restart", "restartMediaAddedCount"), 1),
        (("scenarios", 0, "publication", "reportGetHeadVerified"), False),
        (("scenarios", 0, "publication", "replayBundleVerified"), False),
    ),
)
def test_summary_rejects_provenance_publication_and_restart_drift(
    path: tuple[str | int, ...],
    value: object,
) -> None:
    """Fail closed when source truth, closure, or non-replay proof changes.

    Args:
        path: Nested fixture field to replace.
        value: Invalid replacement value.
    """
    payload = json.loads(_summary().canonical_json())
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)


def test_publication_requires_every_kind_and_unique_exact_artifacts() -> None:
    """Reject an incomplete inventory and duplicate managed identity."""
    payload = json.loads(_summary().canonical_json())
    artifacts = payload["scenarios"][0]["publication"]["artifacts"]
    artifacts.pop()
    with pytest.raises(ValidationError):
        StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)

    payload = json.loads(_summary().canonical_json())
    artifacts = payload["scenarios"][0]["publication"]["artifacts"]
    artifacts[1]["artifactId"] = artifacts[0]["artifactId"]
    with pytest.raises(ValidationError):
        StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)


def test_campaign_requires_stable_order_and_distinct_agent_revisions() -> None:
    """Keep positive/control order and independent immutable Agents explicit."""
    payload = json.loads(_summary().canonical_json())
    payload["scenarios"].reverse()
    with pytest.raises(ValidationError):
        StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)

    payload = json.loads(_summary().canonical_json())
    payload["scenarios"][1]["identities"]["agentRevisionId"] = payload[
        "scenarios"
    ][0]["identities"]["agentRevisionId"]
    with pytest.raises(ValidationError):
        StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)


def test_effect_counters_are_derived_from_events_and_result_phase() -> None:
    """Count fixed source stages and Agent interactions without device access."""
    events = (
        {"kind": "benchmark.setup.start"},
        {"kind": "benchmark.agent.start"},
        {"kind": "benchmark.evaluation.start"},
    )
    task = {
        "result": {
            "phases": [
                {"phase": "agent", "evidence": {"interaction_count": 4}}
            ]
        }
    }
    assert _effect_counters(events, task).model_dump(by_alias=True) == {
        "initializerCount": 1,
        "agentCount": 1,
        "evaluatorCount": 1,
        "actionCount": 4,
    }
    task["result"]["phases"][0]["evidence"] = {"interactionCount": 3}
    assert _effect_counters(events, task).action_count == 3
    with pytest.raises(RuntimeError):
        _effect_counters(events, {"result": {"phases": []}})


@pytest.mark.skipif(
    not (ROOT / "benchmarks/android_world/benchmark.yaml").is_file(),
    reason="Upstream Benchmark assets are omitted from the public release pending redistribution review",
)
def test_runner_builds_two_actual_studio_agents_without_device_resolution(
    tmp_path: Path,
) -> None:
    """Compile both immutable revisions through the production Studio service.

    Args:
        tmp_path: Scenario-isolated durable workspaces.
    """
    profiles = AndroidDeviceProfileResolver(
        {
            "other-profile": AndroidDeviceProfile(
                profile_id="other-profile",
                device=object(),
            ),
            "selected-profile": AndroidDeviceProfile(
                profile_id="selected-profile",
                device=object(),
            ),
        }
    )
    positive = _build_scenario_runtime(
        tmp_path / "positive",
        scenario_id=AndroidServiceScenarioId.POSITIVE,
        profiles=profiles,
        device_profile_id="selected-profile",
        x=10,
        y=20,
    )
    try:
        assert positive.definition["deviceProfileId"] == "selected-profile"
        assert positive.definition["benchmark"]["taskIds"] == ["AndroidWorld_6"]
        assert positive.definition["protocol"]["seed"] == 42
        assert positive.definition["protocol"]["repeats"] == 1
        assert positive.definition["agentRevisions"] == [
            {
                "agentId": positive.agent_id,
                "revisionId": positive.revision_id,
            }
        ]
        revision = SQLiteAgentDocumentRepository(positive.database).get_revision(
            positive.agent_id,
            positive.revision_id,
        )
        graph = revision.compile_snapshot.agent_graph
        assert graph is not None
        serialized = json.dumps(graph, sort_keys=True)
        assert '"api_key": {"secret_ref": "api_key"}' in serialized
        assert '"base_url": {"secret_ref": "base_url"}' in serialized
        assert "sk-" not in serialized
        assert "api.openai.com" not in serialized
        assert canonical_hash(graph).startswith("sha256:")
    finally:
        positive.close()

    control = _build_scenario_runtime(
        tmp_path / "control",
        scenario_id=AndroidServiceScenarioId.CONTROLLED_FAIL,
        profiles=profiles,
        device_profile_id="selected-profile",
        x=10,
        y=20,
    )
    try:
        assert control.definition["deviceProfileId"] == "selected-profile"
        assert control.agent_id != positive.agent_id
        assert control.revision_id != positive.revision_id
    finally:
        control.close()


def test_redaction_allows_service_and_device_paths_but_rejects_host_paths() -> None:
    """Distinguish public links/Android paths from workstation authority."""
    assert not _contains_host_absolute_path("GET /studio/replays/replay-safe")
    assert not _contains_host_absolute_path("query /storage/emulated/0/Pictures")
    assert not _contains_host_absolute_path("query /data/data/app/database.db")
    assert _contains_host_absolute_path("opened /Users/private/operator/config.json")
    assert _contains_host_absolute_path("opened C:\\Users\\operator\\secret.json")
    _assert_safe_json({"target": "camera-button", "tokenCount": 4})
    _assert_safe_json({"taskText": "line one\nline two\tvalue"})
    for unsafe in (
        {"serial": "private-target"},
        {"configPath": "relative-but-private"},
        {"message": "/Users/private/operator/config.json"},
        {"message": "adb -s private-target shell input tap 1 2"},
        {"message": "<object at 0x1234>"},
    ):
        with pytest.raises(ValueError):
            _assert_safe_json(unsafe)


def test_exact_private_canaries_are_rejected_in_json_text_and_bytes() -> None:
    """Reject private authority regardless of serialization form."""
    forbidden = ("raw-device-canary", "private-binding-canary")
    for candidate in (
        {"message": "raw-device-canary"},
        "prefix private-binding-canary suffix",
        b"raw-device-canary",
    ):
        with pytest.raises(ValueError):
            assert_forbidden_values_absent(
                candidate,
                forbidden_values=forbidden,
                field="malicious fixture",
            )


def test_campaign_scan_covers_documents_files_and_zip_members(
    tmp_path: Path,
) -> None:
    """Scan safe evidence and catch injected secrets inside managed archives.

    Args:
        tmp_path: Isolated fake durable evidence tree.
    """
    root = tmp_path / "scenario"
    root.mkdir()
    (root / "safe.json").write_text(
        json.dumps(
            {
                "link": "/studio/benchmark-experiments/experiment-safe",
                "devicePath": "/storage/emulated/0/Pictures",
            }
        ),
        encoding="utf-8",
    )
    archive_path = root / "bundle.zip"
    (root / "studio.sqlite3").write_text(
        "private-canary belongs only to private authority storage",
        encoding="utf-8",
    )
    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", '{"status":"safe"}')
    count = _scan_campaign(
        (root,),
        ({"link": "/studio/replays/replay-safe"},),
        forbidden_values=("private-canary",),
    )
    assert count >= 4

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("manifest.json", '{"value":"private-canary"}')
    with pytest.raises(ValueError):
        _scan_campaign(
            (root,),
            (),
            forbidden_values=("private-canary",),
        )


def test_managed_resource_verification_closes_media_type_and_head(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify GET bytes and matching HEAD metadata against the descriptor.

    Args:
        monkeypatch: Scoped local HTTP request replacement.
    """
    body = b"verified managed bytes"
    digest = acceptance._sha256_bytes(body)
    replies = iter(
        (
            HTTPResponse(
                200,
                {
                    "content-length": str(len(body)),
                    "content-type": "application/json",
                },
                body,
            ),
            HTTPResponse(
                200,
                {
                    "content-length": str(len(body)),
                    "content-type": "application/json",
                },
                b"",
            ),
        )
    )
    monkeypatch.setattr(acceptance, "_request", lambda *_args, **_kwargs: next(replies))
    assert _verify_binary_resource(
        ("127.0.0.1", 1),
        "/studio/managed/artifact-safe",
        expected_size=len(body),
        expected_sha256=digest,
        expected_content_type="application/json",
    ) == body

    monkeypatch.setattr(
        acceptance,
        "_request",
        lambda *_args, **_kwargs: HTTPResponse(
            200,
            {
                "content-length": str(len(body)),
                "content-type": "text/plain",
            },
            body,
        ),
    )
    with pytest.raises(RuntimeError, match="Content-Type"):
        _verify_binary_resource(
            ("127.0.0.1", 1),
            "/studio/managed/artifact-safe",
            expected_content_type="application/json",
            require_head=False,
        )


def test_cli_requires_explicit_confirmation_and_has_no_raw_serial_input() -> None:
    """Keep real-device execution opt-in and profile-only at the command edge."""
    parser = _parser()
    base = [
        "run",
        "--device-profile-id",
        "pixel-safe-profile",
        "--device-profile-config",
        "profile.json",
        "--workspace-root",
        "temp/campaign",
    ]
    with pytest.raises(SystemExit):
        parser.parse_args(base)
    with pytest.raises(SystemExit):
        parser.parse_args([*base, "--confirm-real-android", "--serial", "raw"])
    parsed = parser.parse_args([*base, "--confirm-real-android"])
    assert parsed.confirm_real_android is True
    assert not hasattr(parsed, "serial")


def test_workspace_must_be_a_new_child_of_repository_temp() -> None:
    """Reject repository, broad temp, and outside output destinations."""
    safe = ROOT / "temp" / "studio-benchmark-android-service" / "campaign-safe"
    assert _safe_disposable_root(safe) == safe.resolve()
    for unsafe in (ROOT, ROOT / "temp", ROOT / "docs" / "campaign"):
        with pytest.raises(ValueError):
            _safe_disposable_root(unsafe)


def test_unsafe_workspace_fails_before_profile_or_device_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject an unsafe output boundary before reading target authority.

    Args:
        monkeypatch: Scoped profile-load side-effect canary.
    """
    import zhixing.studio.device_profiles as device_profiles

    monkeypatch.setattr(
        device_profiles,
        "load_android_device_profiles",
        lambda _path: (_ for _ in ()).throw(
            AssertionError("profile config must not be read")
        ),
    )
    with pytest.raises(ValueError, match="repository temp"):
        run_campaign(
            device_profile_id="safe-profile",
            device_profile_config=Path("profile.json"),
            workspace_root=ROOT / "docs" / "unsafe-campaign",
            x=1,
            y=1,
            timeout_seconds=1,
        )


def test_profile_identity_equal_to_raw_target_fails_before_adb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a serial-disguised profile before exact session construction.

    Args:
        monkeypatch: Scoped trusted-profile and ADB boundary replacements.
    """
    import zhixing.studio.device_profiles as device_profiles

    raw = "raw-target-canary"
    resolver = AndroidDeviceProfileResolver(
        {raw: AndroidDeviceProfile(profile_id=raw, serial=raw)}
    )
    monkeypatch.setattr(
        device_profiles,
        "load_android_device_profiles",
        lambda _path: resolver,
    )
    monkeypatch.setattr(
        device_profiles,
        "resolve_exact_android_session",
        lambda _profile: (_ for _ in ()).throw(
            AssertionError("ADB session must not be resolved")
        ),
    )
    with pytest.raises(ValueError, match="private authority"):
        run_campaign(
            device_profile_id=raw,
            device_profile_config=Path("profile.json"),
            workspace_root=ROOT / "temp" / "raw-target-test-campaign",
            x=1,
            y=1,
            timeout_seconds=1,
        )


def test_terminal_restart_rejects_private_profile_authority_drift() -> None:
    """Compare private binding fingerprints without constructing a device."""
    original = AndroidDeviceProfileResolver(
        {
            "selected-profile": AndroidDeviceProfile(
                profile_id="selected-profile",
                serial="target-one",
            )
        }
    )
    same = AndroidDeviceProfileResolver(
        {
            "selected-profile": AndroidDeviceProfile(
                profile_id="selected-profile",
                serial="target-one",
            )
        }
    )
    drifted = AndroidDeviceProfileResolver(
        {
            "selected-profile": AndroidDeviceProfile(
                profile_id="selected-profile",
                serial="target-two",
            )
        }
    )
    _assert_unchanged_profile_authority(
        original,
        same,
        device_profile_id="selected-profile",
    )
    with pytest.raises(RuntimeError, match="authority drifted"):
        _assert_unchanged_profile_authority(
            original,
            drifted,
            device_profile_id="selected-profile",
        )
