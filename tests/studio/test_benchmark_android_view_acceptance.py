"""No-device contracts for Stage 5.6C-2 Android browser acceptance."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import scripts.studio_benchmark_android_view_acceptance_server as server_launcher

from scripts.studio_benchmark_android_view_acceptance import (
    REQUIRED_CLAIM_LIMITS,
    AndroidViewScenarioEvidence,
    AndroidViewScenarioId,
    BrowserArtifactFact,
    BrowserCausalIdentities,
    BrowserCommandEvidence,
    BrowserDeviceCheck,
    BrowserEventContinuity,
    BrowserNetworkObservation,
    BrowserObservation,
    BrowserOutcomeAxes,
    BrowserPrerequisiteEvidence,
    BrowserProvenanceEvidence,
    BrowserSecurityEvidence,
    BrowserSurface,
    BrowserSurfaceFacts,
    StudioBenchmarkAndroidViewAcceptanceSummaryV1,
    _assert_safe_json,
    prerequisite_from_service_summary,
    start_after_prerequisite,
    validate_prerequisite_file,
    validate_summary_file,
    write_summary,
)
from scripts.studio_benchmark_android_service_acceptance import (
    SafeEvidenceOrigin,
    write_summary as write_service_summary,
)
from scripts.studio_benchmark_android_view_acceptance_server import (
    AndroidViewCampaignServer,
    AndroidViewCampaignInputs,
    CompositeReadOnlyAgentRepository,
    SequentialBrowserCampaignLLM,
    _safe_bootstrap,
    launch_campaign_server,
)
from tests.studio.test_benchmark_android_service_acceptance import (
    _summary as service_summary_fixture,
)


def _origin(
    *,
    acquisition: str,
    environment: str,
    real: bool,
    profile_id: str | None,
) -> BrowserProvenanceEvidence:
    """Build one strict provenance fixture with bounded context checks.

    Args:
        acquisition: Source acquisition axis.
        environment: Source environment axis.
        real: Whether this resource is fresh device evidence.
        profile_id: Safe public device profile identity.

    Returns:
        Complete strict provenance evidence.
    """
    return BrowserProvenanceEvidence(
        origin=SafeEvidenceOrigin(
            acquisition=acquisition,
            environment=environment,
            realDeviceEvidence=real,
        ),
        deviceProfileId=profile_id,
        deviceChecks=(
            BrowserDeviceCheck(name="platform", passed=True, observed="android"),
            BrowserDeviceCheck(name="locale", passed=True, observed="en-US"),
            BrowserDeviceCheck(
                name="orientation",
                passed=True,
                observed="portrait",
            ),
        ),
    )


def _observations(*, salt: str) -> tuple[BrowserObservation, ...]:
    """Build exact coverage of every required browser surface.

    Args:
        salt: Scenario-specific safe route identity.

    Returns:
        Seven bounded surface observations.
    """
    routes = {
        BrowserSurface.CATALOG: "/studio/benchmark-catalog",
        BrowserSurface.COMPOSER: "/studio/benchmark-experiments/new",
        BrowserSurface.MONITOR: f"/studio/benchmark-experiments/experiment-{salt}",
        BrowserSurface.REPORT: (
            f"/studio/benchmark-experiments/experiment-{salt}/report"
        ),
        BrowserSurface.EVIDENCE: (
            f"/studio/benchmark-experiments/experiment-{salt}/report"
            f"?taskRunId=task-run-{salt}"
        ),
        BrowserSurface.REPLAY: f"/studio/replays/replay-{salt}",
        BrowserSurface.EXPORT: (
            f"/studio/benchmark-experiments/experiment-{salt}/report"
        ),
    }
    return tuple(
        BrowserObservation(
            surface=surface,
            route=route,
            assertion=f"{surface.value} retained authoritative identities",
            verification="passed",
            screenshotReference=f"capture-{salt}-{surface.value}.png",
        )
        for surface, route in routes.items()
    )


def _scenario(
    scenario_id: AndroidViewScenarioId,
    prerequisite: BrowserPrerequisiteEvidence,
) -> AndroidViewScenarioEvidence:
    """Build one valid browser scenario joined to its C-1 Agent revision.

    Args:
        scenario_id: Positive or controlled-negative identity.
        prerequisite: Valid C-1 receipt providing Agent/profile selections.

    Returns:
        Complete browser scenario evidence.
    """
    positive = scenario_id is AndroidViewScenarioId.POSITIVE
    salt = "positive" if positive else "control"
    selected = next(
        item for item in prerequisite.scenarios
        if item.scenario_id.value == scenario_id.value
    )
    return AndroidViewScenarioEvidence(
        scenarioId=scenario_id,
        verification="passed",
        identities=BrowserCausalIdentities(
            experimentId=f"experiment-{salt}",
            taskRunId=f"task-run-{salt}",
            coreTaskRunId=f"core-task-run-{salt}",
            agentRunId=f"agent-run-{salt}",
            agentId=selected.agent_id,
            agentRevisionId=selected.agent_revision_id,
            replayId=f"replay-{salt}",
            reportRoute=f"/studio/benchmark-experiments/experiment-{salt}/report",
            replayRoute=f"/studio/replays/replay-{salt}",
        ),
        outcome=BrowserOutcomeAxes(
            experimentLifecycle="terminal",
            experimentTerminalReason="completed",
            taskRunLifecycle="terminal",
            taskRunTerminalReason="completed",
            agentStatus="success",
            benchmarkOutcome="pass" if positive else "fail",
            evaluatorPass=positive,
            invalidCount=0,
        ),
        sourceProvenance=_origin(
            acquisition="fresh_execution",
            environment="real_android",
            real=True,
            profile_id=prerequisite.selection.device_profile_id,
        ),
        replayProvenance=_origin(
            acquisition="replay_projection",
            environment="real_android",
            real=False,
            profile_id=prerequisite.selection.device_profile_id,
        ),
        continuity=BrowserEventContinuity(
            committedCursor=1,
            reconnectCursor=2,
            terminalHighWater=4,
            observedEventIds=(1, 2, 3, 4),
            lastEventIdUsed=True,
            terminalDrainVerified=True,
            initializerCount=1,
            agentCount=1,
            evaluatorCount=1,
            workerSourceCount=1,
            sourceEffectCountBeforeReload=8,
            sourceEffectCountAfterReload=8,
        ),
        surfaces=BrowserSurfaceFacts(
            evaluationVisible=True,
            evidenceExactScope=True,
            replayReloaded=True,
            replayReadOnly=True,
            exportPrepared=True,
            exportHandedOff=True,
            exportCompletionClaimed=False,
        ),
        artifacts=(
            BrowserArtifactFact(
                artifactId=f"artifact-{salt}",
                taskRunId=f"task-run-{salt}",
                kind="task_report",
                availability="available",
                exactScopeVerified=True,
                headVerified=True,
            ),
        ),
        observations=_observations(salt=salt),
    )


def _summary() -> StudioBenchmarkAndroidViewAcceptanceSummaryV1:
    """Build one complete bounded browser proof ledger fixture.

    Returns:
        Strict valid C-2 summary.
    """
    prerequisite = prerequisite_from_service_summary(service_summary_fixture())
    return StudioBenchmarkAndroidViewAcceptanceSummaryV1(
        prerequisite=prerequisite,
        scenarios=tuple(
            _scenario(item, prerequisite) for item in AndroidViewScenarioId
        ),
        fakeFixtureProvenance=_origin(
            acquisition="contract_fixture",
            environment="fake_device",
            real=False,
            profile_id="acceptance-fake",
        ),
        security=BrowserSecurityEvidence(
            consoleObservations=("no unexpected console errors",),
            networkObservations=(
                BrowserNetworkObservation(
                    method="GET",
                    route="/api/studio/benchmark-experiments/experiment-positive",
                    status=200,
                    contentType="application/json",
                ),
            ),
            screenshotReferences=("capture-positive-monitor.png",),
            scannedDocuments=25,
            privateValuesFound=0,
        ),
        commands=(
            BrowserCommandEvidence(
                suiteId="actual-browser-real-android-matrix",
                command=(
                    "uv run python scripts/studio_benchmark_android_view_"
                    "acceptance.py validate <summary>"
                ),
                observed="positive PASS and controlled evaluator FAIL",
                verification="passed",
            ),
        ),
        claimLimits=REQUIRED_CLAIM_LIMITS,
    )


def test_prerequisite_and_browser_ledger_are_canonical_and_round_trip(
    tmp_path: Path,
) -> None:
    """Validate the exact C-1 receipt and complete C-2 ledger.

    Args:
        tmp_path: Isolated summary destinations.
    """
    service_path = write_service_summary(
        service_summary_fixture(),
        tmp_path / "service-summary.json",
    )
    receipt = validate_prerequisite_file(service_path)
    assert receipt.completion == "passed"
    assert len(receipt.scenarios) == 2

    summary = _summary()
    destination = write_summary(summary, tmp_path / "browser-summary.json")
    assert validate_summary_file(destination) == summary
    assert destination.read_text(encoding="utf-8") == summary.canonical_json() + "\n"


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("scenarios", 0, "publication", "reportGetHeadVerified"), False),
        (("scenarios", 0, "restart", "identitiesStable"), False),
        (("scenarios", 0, "restart", "sourceEffectCountAfter"), 18),
        (("privateValuesFound",), 1),
    ),
)
def test_prerequisite_rejects_incomplete_closure_restart_and_redaction(
    tmp_path: Path,
    path: tuple[str | int, ...],
    value: object,
) -> None:
    """Fail before C-2 when any strict C-1 completion gate changes.

    Args:
        tmp_path: Isolated malformed summary destination.
        path: Nested C-1 field to replace.
        value: Invalid replacement value.
    """
    payload = json.loads(service_summary_fixture().canonical_json())
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    destination = tmp_path / "incomplete.json"
    destination.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises((ValidationError, ValueError)):
        validate_prerequisite_file(destination)


def test_gate_rejects_before_any_effectful_starter(tmp_path: Path) -> None:
    """Prove invalid C-1 evidence cannot reach profile/backend/device setup.

    Args:
        tmp_path: Isolated malformed prerequisite destination.
    """
    invalid = tmp_path / "missing-scenario.json"
    payload = json.loads(service_summary_fixture().canonical_json())
    payload["scenarios"].pop()
    invalid.write_text(json.dumps(payload), encoding="utf-8")
    effects: list[str] = []
    with pytest.raises((ValidationError, ValueError)):
        start_after_prerequisite(
            confirm_real_android=True,
            service_summary=invalid,
            device_profile_id="pixel-safe-profile",
            starter=lambda _receipt: effects.append("profile/server/device"),
        )
    assert effects == []


def test_server_launcher_validates_prerequisite_before_private_inputs(
    tmp_path: Path,
) -> None:
    """Keep config/workspace/profile/server work behind the C-1 gate.

    Args:
        tmp_path: Isolated malformed prerequisite destination.
    """
    invalid = tmp_path / "invalid.json"
    payload = json.loads(service_summary_fixture().canonical_json())
    payload["scenarios"].pop()
    invalid.write_text(json.dumps(payload), encoding="utf-8")
    effects: list[AndroidViewCampaignInputs] = []
    with pytest.raises((ValidationError, ValueError)):
        launch_campaign_server(
            confirm_real_android=True,
            service_summary=invalid,
            device_profile_id="pixel-safe-profile",
            device_profile_config=tmp_path / "missing-private-config.json",
            workspace=tmp_path / "would-be-workspace",
            port=0,
            x=10,
            y=20,
            starter=lambda inputs: effects.append(inputs),  # type: ignore[arg-type,return-value]
        )
    assert effects == []


def test_server_launcher_emits_only_safe_loopback_bootstrap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bind a valid receipt to private inputs without serializing authority.

    Args:
        tmp_path: Isolated no-device input paths.
        monkeypatch: Scoped disposable-workspace relaxation for the unit test.
    """
    service_path = write_service_summary(
        service_summary_fixture(),
        tmp_path / "service-summary.json",
    )
    config = tmp_path / "trusted-private-config.json"
    config.write_text("private-canary", encoding="utf-8")
    monkeypatch.setattr(
        server_launcher,
        "_safe_disposable_workspace",
        lambda path: path.resolve(),
    )
    captured: list[AndroidViewCampaignInputs] = []

    def starter(inputs: AndroidViewCampaignInputs):
        """Capture gated private inputs and return a server-shaped sentinel."""
        captured.append(inputs)
        return "started"  # type: ignore[return-value]

    result = launch_campaign_server(
        confirm_real_android=True,
        service_summary=service_path,
        device_profile_id="pixel-safe-profile",
        device_profile_config=config,
        workspace=tmp_path / "campaign",
        port=0,
        x=10,
        y=20,
        starter=starter,
    )
    assert result == "started"
    assert len(captured) == 1
    receipt = captured[0].receipt
    bootstrap = _safe_bootstrap(
        api_base_url="http://127.0.0.1:8765",
        receipt=receipt,
        catalog_entry_id="catalog-safe",
    )
    serialized = json.dumps(bootstrap, sort_keys=True)
    assert "private-canary" not in serialized
    assert str(config) not in serialized
    assert bootstrap["deviceProfileId"] == "pixel-safe-profile"
    assert len(bootstrap["agents"]) == 2


def test_composite_repository_preserves_exact_agents_and_rejects_writes() -> None:
    """Expose two C-1 repositories without copying or rebinding identities."""
    from zhixing.studio.repository import AgentRecord

    service = service_summary_fixture()

    class Repository:
        """Minimal repository-shaped immutable fixture."""

        def __init__(self, scenario_index: int) -> None:
            """Create records matching one C-1 scenario."""
            scenario = service.scenarios[scenario_index]
            self.agent = AgentRecord(
                agentId=scenario.identities.agent_id,
                name=f"Scenario {scenario_index}",
                currentRevisionId=scenario.identities.agent_revision_id,
                createdAt=scenario_index,
                updatedAt=scenario_index,
            )
            self.revision = type(
                "Revision",
                (),
                {
                    "agent_id": scenario.identities.agent_id,
                    "revision_id": scenario.identities.agent_revision_id,
                    "compile_snapshot": type(
                        "Snapshot",
                        (),
                        {"status": "valid"},
                    )(),
                },
            )()

        def list_agents(self, *, limit: int = 50, cursor: str | None = None):
            """Return the single immutable Agent."""
            del limit, cursor
            return type(
                "Page",
                (),
                {"items": (self.agent,), "next_cursor": None},
            )()

        def get_revision(self, agent_id: str, revision_id: str):
            """Return the exact immutable revision."""
            assert agent_id == self.revision.agent_id
            assert revision_id == self.revision.revision_id
            return self.revision

    composite = CompositeReadOnlyAgentRepository(
        (Repository(0), Repository(1)),
    )
    page = composite.list_agents(limit=2)
    assert {item.agent_id for item in page.items} == {
        scenario.identities.agent_id for scenario in service.scenarios
    }
    selected = service.scenarios[0]
    assert composite.get_revision(
        selected.identities.agent_id,
        selected.identities.agent_revision_id,
    ).revision_id == selected.identities.agent_revision_id
    with pytest.raises(ValueError, match="read-only"):
        composite.rename_agent(selected.identities.agent_id, "mutated")


def test_campaign_llm_fails_closed_on_retry_or_reexecution() -> None:
    """Allow exactly four positive decisions and one controlled finish."""
    llm = SequentialBrowserCampaignLLM(x=10, y=20)
    actions = [json.loads(llm.generate("prompt"))["action"] for _ in range(5)]
    assert actions == ["start_app", "wait", "tap", "wait", "DONE"]
    with pytest.raises(RuntimeError, match="second execution or parser retry"):
        llm.generate("unexpected retry")


def test_campaign_server_teardown_stops_transport_before_worker() -> None:
    """Close HTTP subscribers and listener before stopping the composition."""
    calls: list[str] = []

    class HTTPServer:
        """Record bounded transport teardown calls."""

        def shutdown(self) -> None:
            """Record subscriber/listener shutdown."""
            calls.append("server.shutdown")

        def server_close(self) -> None:
            """Record socket close."""
            calls.append("server.close")

    class Thread:
        """Record bounded server-thread join."""

        def join(self, timeout: int) -> None:
            """Record one bounded join timeout."""
            calls.append(f"thread.join:{timeout}")

        def is_alive(self) -> bool:
            """Report successful termination."""
            return False

    class Composition:
        """Record Worker and repository shutdown."""

        def shutdown(self, *, wait: bool) -> None:
            """Record deterministic composition shutdown."""
            calls.append(f"composition.shutdown:{wait}")

    campaign = AndroidViewCampaignServer(
        server=HTTPServer(),
        thread=Thread(),  # type: ignore[arg-type]
        composition=Composition(),
        bootstrap={"schemaVersion": 1},
        llm=SequentialBrowserCampaignLLM(x=1, y=1),
    )
    campaign.close()
    assert calls == [
        "server.shutdown",
        "server.close",
        "thread.join:5",
        "composition.shutdown:True",
    ]


@pytest.mark.parametrize(
    "unsafe",
    (
        {"serial": "private-target"},
        {"adbArguments": ["-s", "private-target"]},
        {"configPath": "trusted/device-profile.json"},
        {"message": "/Users/operator/private/profile.json"},
        {"message": "adb -s private-target shell input tap 1 2"},
        {"responseBody": {"secret": "do-not-retain"}},
        {"message": "file:///private/profile.json"},
        {"message": "<object at 0x1234>"},
    ),
)
def test_browser_evidence_rejects_private_authority_and_unsafe_bodies(
    unsafe: object,
) -> None:
    """Reject private target authority in every JSON-compatible shape.

    Args:
        unsafe: Candidate unsafe retained evidence.
    """
    with pytest.raises(ValueError):
        _assert_safe_json(unsafe)


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (("scenarios", 0, "outcome", "benchmarkOutcome"), "fail"),
        (("scenarios", 1, "outcome", "agentStatus"), "failed"),
        (("scenarios", 0, "continuity", "observedEventIds"), [1, 2, 2, 4]),
        (("scenarios", 0, "continuity", "sourceEffectCountAfterReload"), 9),
        (("scenarios", 0, "surfaces", "exportCompletionClaimed"), True),
        (("scenarios", 0, "artifacts", 0, "exactScopeVerified"), False),
        (("fakeFixtureProvenance", "origin", "environment"), "real_android"),
    ),
)
def test_browser_ledger_rejects_outcome_continuity_scope_and_provenance_drift(
    path: tuple[str | int, ...],
    value: object,
) -> None:
    """Reject stale/cross-owned facts and provenance upgrades.

    Args:
        path: Nested browser ledger field to replace.
        value: Invalid replacement value.
    """
    payload = json.loads(_summary().canonical_json())
    target: object = payload
    for key in path[:-1]:
        target = target[key]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    with pytest.raises((ValidationError, ValueError)):
        StudioBenchmarkAndroidViewAcceptanceSummaryV1.model_validate(payload)


def test_write_scans_exact_runtime_canaries_before_persistence(tmp_path: Path) -> None:
    """Reject private runtime values even when their key looks harmless.

    Args:
        tmp_path: Isolated ledger destination.
    """
    with pytest.raises(ValueError):
        write_summary(
            _summary(),
            tmp_path / "summary.json",
            forbidden_values=("capture-positive-monitor.png",),
        )
    assert not (tmp_path / "summary.json").exists()
