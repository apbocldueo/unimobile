"""Stage 5.6B bounded layered-acceptance proof-ledger contracts."""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import replace
from pathlib import Path

import pytest
from pydantic import ValidationError

from scripts.studio_benchmark_layered_acceptance import (
    ACCEPTANCE_GATE_INVENTORY,
    REQUIRED_CLAIM_LIMITS,
    REQUIRED_SCENARIOS,
    REQUIRED_ZERO_CANARIES,
    AcceptanceCapabilityBoundary,
    AcceptanceCausalIdentities,
    AcceptanceCommandEvidence,
    AcceptanceScenarioEvidence,
    AcceptanceScenarioId,
    StudioBenchmarkLayeredAcceptanceSummaryV1,
    validate_summary_file,
    write_summary,
)
from tests.studio.benchmark_layered_acceptance_fixtures import (
    build_layered_acceptance_harness,
    reopen_layered_acceptance_harness,
)
from tests.studio.test_benchmark_event_stream import _open_sse
from tests.studio.test_benchmark_experiment_resource import _http_request
from tests.benchmark.test_experiment_runtime import (
    FakeBenchmarkDevice,
    FakeBenchmarkResolver,
    _agent,
    _plan,
    _task,
)
from zhixing.benchmark import (
    BenchmarkExperimentRuntime,
    BenchmarkOutcome,
    BenchmarkRunConfig,
    ExperimentProtocol,
    build_schedule,
    compile_benchmark_suite,
    load_experiment_report,
)
from zhixing.components import Action, ActionType
from zhixing.config.contracts import BenchmarkSuite
from zhixing.studio.benchmark_errors import StudioBenchmarkValidationError
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventSource,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkTaskRunLifecycle,
)


def _identity(prefix: str, salt: str) -> str:
    """Return one path-free deterministic opaque test identity.

    Args:
        prefix: Semantic identity kind.
        salt: Per-summary opaque suffix.

    Returns:
        Stable safe fixture identity.
    """
    return f"{prefix}-{salt}"


def _identities(
    scenario_id: AcceptanceScenarioId,
    *,
    salt: str,
) -> AcceptanceCausalIdentities:
    """Build the minimum causal closure required by one scenario.

    Args:
        scenario_id: Stable required scenario identity.
        salt: Per-summary opaque suffix.

    Returns:
        Strict causal identity collection.
    """
    requires_experiment = scenario_id not in {
        AcceptanceScenarioId.CORE_MULTI_CARDINALITY,
        AcceptanceScenarioId.STUDIO_CARDINALITY_REJECTED,
    }
    requires_task = scenario_id in {
        AcceptanceScenarioId.STUDIO_FAKE_PASS,
        AcceptanceScenarioId.STUDIO_FAKE_FAIL,
        AcceptanceScenarioId.STUDIO_CONTEXT_INVALID,
        AcceptanceScenarioId.STUDIO_CANCEL_ACTIVE,
        AcceptanceScenarioId.STUDIO_RECOVERY_INTERRUPTED,
        AcceptanceScenarioId.STUDIO_RECOVERY_PUBLICATION,
        AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
        AcceptanceScenarioId.ACTUAL_BACKEND_BROWSER,
    }
    requires_core = scenario_id in {
        AcceptanceScenarioId.STUDIO_FAKE_PASS,
        AcceptanceScenarioId.STUDIO_FAKE_FAIL,
        AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
    }
    requires_publication = scenario_id in {
        AcceptanceScenarioId.STUDIO_FAKE_PASS,
        AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
        AcceptanceScenarioId.ACTUAL_BACKEND_BROWSER,
    }
    core_ids = (
        tuple(_identity("core-task-run", f"{salt}-{index}") for index in range(8))
        if scenario_id is AcceptanceScenarioId.CORE_MULTI_CARDINALITY
        else ((_identity("core-task-run", salt),) if requires_core else ())
    )
    return AcceptanceCausalIdentities(
        experiment_id=_identity("experiment", salt) if requires_experiment else None,
        planned_task_run_ids=(
            (_identity("planned-task-run", salt),) if requires_task else ()
        ),
        core_task_run_ids=core_ids,
        agent_run_ids=((_identity("agent-run", salt),) if requires_core else ()),
        event_ids=(
            (_identity("event", salt),) if requires_experiment else ()
        ),
        replay_ids=((_identity("replay", salt),) if requires_publication else ()),
        report_identities=(
            (_identity("report", salt),) if requires_publication else ()
        ),
        trajectory_identities=(
            (_identity("trajectory", salt),) if requires_publication else ()
        ),
        manifest_identities=(
            (_identity("manifest", salt),) if requires_publication else ()
        ),
        bundle_identities=(
            (_identity("bundle", salt),) if requires_publication else ()
        ),
        managed_artifact_ids=(
            (_identity("artifact", salt),) if requires_publication else ()
        ),
    )


def _summary(*, salt: str = "first") -> StudioBenchmarkLayeredAcceptanceSummaryV1:
    """Create one complete strict no-device summary fixture.

    Args:
        salt: Opaque identity suffix allowed to vary between reruns.

    Returns:
        Complete validated summary.
    """
    scenarios = tuple(
        AcceptanceScenarioEvidence(
            scenario_id=scenario_id,
            verification="passed",
            suite_ids=("tests/studio/test_benchmark_layered_acceptance.py",),
            fixture_inputs={"seed": 42, "fixtureVersion": "v1"},
            identities=_identities(scenario_id, salt=f"{salt}-{index}"),
            facts={
                "scenario": scenario_id.value,
                "complete": True,
                "realDeviceEvidence": False,
            },
        )
        for index, scenario_id in enumerate(REQUIRED_SCENARIOS)
    )
    return StudioBenchmarkLayeredAcceptanceSummaryV1(
        scenarios=scenarios,
        commands=(
            AcceptanceCommandEvidence(
                suite_id="proof-ledger-contract",
                command="uv run pytest -q tests/studio/test_benchmark_layered_acceptance.py",
                verification="passed",
                observed="proof-ledger contract passed",
            ),
        ),
        zeroSideEffectCanaries={key: 0 for key in REQUIRED_ZERO_CANARIES},
        capabilityBoundary=AcceptanceCapabilityBoundary(
            core_multi_cardinality_verified=True,
            core_agents=2,
            core_tasks=2,
            core_repeats=2,
            studio_over_limit_rejected_before_effects=True,
        ),
        claimLimits=REQUIRED_CLAIM_LIMITS,
    )


def test_gate_inventory_covers_every_required_scenario_once() -> None:
    """Keep the permanent focused-gate inventory complete and ordered."""
    assert tuple(item.scenario_id for item in ACCEPTANCE_GATE_INVENTORY) == (
        REQUIRED_SCENARIOS
    )
    for item in ACCEPTANCE_GATE_INVENTORY:
        assert item.supporting_suites
        assert item.cross_layer_gap


def test_summary_is_bounded_canonical_and_round_trips(tmp_path: Path) -> None:
    """Write and read one complete causal proof ledger deterministically."""
    summary = _summary()
    destination = write_summary(summary, tmp_path / "evidence" / "summary.json")
    restored = validate_summary_file(destination)
    assert restored == summary
    assert destination.read_text(encoding="utf-8") == summary.canonical_json() + "\n"
    payload = json.loads(summary.canonical_json())
    assert payload["schemaVersion"] == 1
    assert payload["environment"] == "no_device"
    assert len(payload["scenarios"]) == len(REQUIRED_SCENARIOS)
    assert all(
        item["evidence_origin"]
        == {
            "acquisition": "contract_fixture",
            "environment": "fake_device",
            "realDeviceEvidence": False,
        }
        for item in payload["scenarios"]
    )


def test_semantic_rerun_allows_only_opaque_identity_changes() -> None:
    """Compare causal semantics without requiring regenerated opaque IDs."""
    first = _summary(salt="first")
    repeated = _summary(salt="repeated")
    assert first.canonical_json() != repeated.canonical_json()
    assert first.semantically_equals(repeated)
    changed = repeated.model_copy(
        update={
            "capability_boundary": repeated.capability_boundary.model_copy(
                update={"core_tasks": 3}
            )
        }
    )
    assert not first.semantically_equals(changed)


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_scenario",
        "duplicate_scenario",
        "nonzero_canary",
        "missing_canary",
        "real_device_claim",
        "significance_claim",
        "missing_publication_identity",
    ),
)
def test_summary_rejects_incomplete_or_strengthened_evidence(mutation: str) -> None:
    """Fail closed on incomplete scenarios, identities, and claim boundaries.

    Args:
        mutation: Controlled invalid summary mutation.
    """
    payload = json.loads(_summary().canonical_json())
    if mutation == "missing_scenario":
        payload["scenarios"].pop()
    elif mutation == "duplicate_scenario":
        payload["scenarios"][-1] = payload["scenarios"][0]
    elif mutation == "nonzero_canary":
        payload["zeroSideEffectCanaries"]["adb_discovery"] = 1
    elif mutation == "missing_canary":
        payload["zeroSideEffectCanaries"].pop("secret_resolution")
    elif mutation == "real_device_claim":
        payload["scenarios"][0]["evidence_origin"]["realDeviceEvidence"] = True
    elif mutation == "significance_claim":
        payload["capabilityBoundary"]["significance_claimed"] = True
    elif mutation == "missing_publication_identity":
        payload["scenarios"][0]["identities"]["replay_ids"] = []
    with pytest.raises((ValidationError, ValueError)):
        StudioBenchmarkLayeredAcceptanceSummaryV1.model_validate(payload)


@pytest.mark.parametrize(
    "field,value",
    (
        ("fact", "/Users/researcher/private/result.json"),
        ("fact", "authorization=Bearer hidden-value"),
        ("fact", "emulator-5554"),
        ("identity", "replay/../../neighbor"),
        ("suite", "/private/repository/test.py"),
    ),
)
def test_summary_rejects_private_paths_targets_and_secret_shapes(
    field: str,
    value: str,
) -> None:
    """Prevent unsafe values from entering any generated proof ledger.

    Args:
        field: Evidence location to mutate.
        value: Unsafe candidate value.
    """
    payload = json.loads(_summary().canonical_json())
    if field == "fact":
        payload["scenarios"][0]["facts"]["unsafe"] = value
    elif field == "identity":
        payload["scenarios"][0]["identities"]["replay_ids"] = [value]
    elif field == "suite":
        payload["scenarios"][0]["suite_ids"] = [value]
    with pytest.raises((ValidationError, ValueError)):
        StudioBenchmarkLayeredAcceptanceSummaryV1.model_validate(payload)


def test_actual_default_composition_executes_fake_pass_and_publishes(
    tmp_path: Path,
) -> None:
    """Traverse actual Studio/Core/publication boundaries on a fake PASS.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        TimeoutError: The actual worker does not become terminal.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(tmp_path / "actual-pass")
    try:
        assert harness.composition.experiments is not None
        created = harness.composition.experiments.create_experiment(
            harness.create_payload("acceptance-pass-request")
        )
        repeated = harness.composition.experiments.create_experiment(
            harness.create_payload("acceptance-pass-request")
        )
        assert created.created is True
        assert repeated.created is False
        assert repeated.experiment.experiment_id == created.experiment.experiment_id
        terminal = harness.wait_terminal(created.experiment.experiment_id)
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "completed"
        task = harness.composition.experiments.list_task_runs(
            created.experiment.experiment_id
        ).items[0]
        assert task.result is not None
        assert task.result.planned_task_run_id == task.task_run_id
        assert task.result.core_task_run_id == task.core_task_run_id
        assert task.result.agent_run_id == task.agent_run_id
        assert task.result.benchmark_outcome.value == "pass", task.result.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        )
        assert task.result.agent_status is not None
        assert task.result.agent_status.value == "success"
        assert harness.terminal_llm.calls == 1
        assert task.result.evidence_origin.acquisition == "contract_fixture"
        assert task.result.evidence_origin.environment == "fake_device"
        assert task.result.evidence_origin.real_device_evidence is False
        assert harness.composition.publications is not None
        publication = harness.composition.publications.get_publication(
            created.experiment.experiment_id
        )
        assert publication is not None
        assert publication.task_run_id == task.task_run_id
        assert publication.replay_id is not None
        assert publication.report_artifact_id is not None
        assert publication.bundle_artifact_id is not None
        assert publication.artifact_ids
        artifact_records = harness.composition.publications.list_artifacts(
            created.experiment.experiment_id
        )
        events = harness.composition.repository.list_events(
            created.experiment.experiment_id
        )
        assert [item.sequence for item in events] == list(
            range(1, len(events) + 1)
        )
        assert sum(item.kind == "experiment.terminal" for item in events) == 1
        assert any(call[0] == "push_file" for call in harness.device.calls)
        trajectory_ids = tuple(
            record.descriptor.artifact_id
            for record in artifact_records
            if record.descriptor.kind == "task_trajectory"
        )
        manifest_ids = tuple(
            record.descriptor.artifact_id
            for record in artifact_records
            if record.descriptor.kind
            in {"publication_manifest", "studio_publication_manifest"}
        )
        scenario = AcceptanceScenarioEvidence(
            scenario_id=AcceptanceScenarioId.STUDIO_FAKE_PASS,
            verification="passed",
            suite_ids=(
                "tests/studio/test_benchmark_layered_acceptance.py",
            ),
            fixture_inputs={"seed": 17, "fakeDevice": True},
            identities=AcceptanceCausalIdentities(
                experiment_id=created.experiment.experiment_id,
                planned_task_run_ids=(task.task_run_id,),
                core_task_run_ids=(task.core_task_run_id,),
                agent_run_ids=(task.agent_run_id,),
                event_ids=tuple(item.event_id for item in events),
                replay_ids=(publication.replay_id,),
                report_identities=(publication.report_artifact_id,),
                trajectory_identities=trajectory_ids,
                manifest_identities=manifest_ids,
                bundle_identities=(publication.bundle_artifact_id,),
                managed_artifact_ids=tuple(
                    record.descriptor.artifact_id
                    for record in artifact_records
                ),
            ),
            facts={
                "serviceTerminalReason": terminal.terminal_reason.value,
                "agentStatus": task.result.agent_status.value,
                "benchmarkOutcome": task.result.benchmark_outcome.value,
                "evaluationStatus": task.result.evaluation.status,
                "evaluationPass": task.result.evaluation.is_pass,
                "publicationComplete": publication.published_at > 0,
                "replayAvailability": task.replay_availability.value,
                "artifactIntegrityClosed": all(
                    record.descriptor.availability.value == "available"
                    and record.descriptor.sha256 is not None
                    and record.descriptor.sha256.startswith("sha256:")
                    for record in artifact_records
                ),
                "evidenceEnvironment": (
                    task.result.evidence_origin.environment
                ),
                "realDeviceEvidence": (
                    task.result.evidence_origin.real_device_evidence
                ),
            },
        )
        assert scenario.facts["serviceTerminalReason"] == "completed"
        assert scenario.facts["agentStatus"] == "success"
        assert scenario.facts["benchmarkOutcome"] == "pass"
        assert scenario.facts["evaluationPass"] is True
        assert scenario.facts["publicationComplete"] is True
        assert scenario.facts["artifactIntegrityClosed"] is True
        assert scenario.evidence_origin.real_device_evidence is False
    finally:
        harness.composition.shutdown()


def test_actual_default_composition_keeps_agent_success_independent_from_fail(
    tmp_path: Path,
) -> None:
    """Retain evaluation evidence for controlled fake Benchmark FAIL.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        TimeoutError: The actual worker does not become terminal.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "actual-fail",
        expose_pushed_files=False,
    )
    try:
        assert harness.composition.experiments is not None
        created = harness.composition.experiments.create_experiment(
            harness.create_payload("acceptance-fail-request")
        ).experiment
        terminal = harness.wait_terminal(created.experiment_id)
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "completed"
        task = harness.composition.experiments.list_task_runs(
            created.experiment_id
        ).items[0]
        assert task.result is not None
        assert task.result.agent_status is not None
        assert task.result.agent_status.value == "success"
        assert task.result.benchmark_outcome.value == "fail"
        assert task.result.evaluation is not None
        assert task.result.evaluation.is_pass is False
        assert task.result.evaluation.status == "success"
        assert harness.terminal_llm.calls == 1
        assert task.result.evidence_origin.real_device_evidence is False
    finally:
        harness.composition.shutdown()


def test_actual_context_invalid_stops_before_initializer_agent_and_evaluator(
    tmp_path: Path,
) -> None:
    """Fail incompatible fake-device context before effectful run phases.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        TimeoutError: The actual worker does not become terminal.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "actual-invalid",
        device_locale="fr-FR",
    )
    try:
        assert harness.composition.experiments is not None
        created = harness.composition.experiments.create_experiment(
            harness.create_payload("acceptance-invalid-request")
        ).experiment
        terminal = harness.wait_terminal(created.experiment_id)
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "completed"
        task = harness.composition.experiments.list_task_runs(
            created.experiment_id
        ).items[0]
        assert task.result is not None
        assert task.result.benchmark_outcome.value == "invalid"
        assert task.result.agent_status is None
        assert task.result.evaluation is None
        checks = {
            item.name: item.passed
            for item in task.result.evidence_origin.device_checks
        }
        assert checks["locale"] is False
        assert task.result.evidence_origin.environment == "fake_device"
        assert task.result.evidence_origin.real_device_evidence is False
        assert harness.device.calls == [
            ("shell", "pm path com.android.documentsui")
        ]
        assert harness.terminal_llm.calls == 0
    finally:
        harness.composition.shutdown()


def test_actual_active_cancellation_stops_at_cooperative_safe_boundary(
    tmp_path: Path,
) -> None:
    """Cancel an active fake run after one confirmed initializer effect.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        TimeoutError: Fake initialization or terminal transition times out.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "actual-cancel",
        block_push=True,
    )
    try:
        assert harness.composition.experiments is not None
        created = harness.composition.experiments.create_experiment(
            harness.create_payload("acceptance-active-cancel-request")
        ).experiment
        if not harness.device.push_started.wait(timeout=5):
            raise TimeoutError("actual fake initializer did not start")
        cancelling = harness.composition.experiments.cancel_experiment(
            created.experiment_id,
            {
                "schemaVersion": 1,
                "clientRequestId": "acceptance-active-cancel-command",
            },
        )
        assert cancelling.lifecycle.value == "cancelling"
        harness.device.release_push.set()
        terminal = harness.wait_terminal(created.experiment_id)
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "cancelled"
        task = harness.composition.experiments.list_task_runs(
            created.experiment_id
        ).items[0]
        assert task.result is not None
        assert task.result.benchmark_outcome.value == "skipped"
        assert harness.terminal_llm.calls == 0
        assert sum(call[0] == "push_file" for call in harness.device.calls) == 1
        assert harness.composition.repository is not None
        events = harness.composition.repository.list_events(created.experiment_id)
        assert sum(item.kind == "experiment.terminal" for item in events) == 1
    finally:
        harness.device.release_push.set()
        harness.composition.shutdown()


def test_actual_accepted_cancellation_has_one_terminal_fact(
    tmp_path: Path,
) -> None:
    """Cancel accepted work before scheduler ownership or device effects.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        AssertionError: Durable lifecycle facts are inconsistent.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "accepted-cancel"
    )
    try:
        service = harness.detached_experiment_service()
        created = service.create_experiment(
            harness.create_payload("acceptance-accepted-cancel-request")
        ).experiment
        terminal = service.cancel_experiment(
            created.experiment_id,
            {
                "schemaVersion": 1,
                "clientRequestId": "acceptance-accepted-cancel-command",
            },
        )
        assert terminal.lifecycle.value == "terminal"
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "cancelled"
        task = service.list_task_runs(created.experiment_id).items[0]
        assert task.terminal_reason is not None
        assert task.terminal_reason.value == "cancelled_before_start"
        assert task.result is None
        assert harness.device.calls == []
        assert harness.terminal_llm.calls == 0
        assert harness.composition.repository is not None
        events = harness.composition.repository.list_events(
            created.experiment_id
        )
        assert sum(item.kind == "experiment.terminal" for item in events) == 1
    finally:
        harness.composition.shutdown()


def test_actual_unknown_create_response_retry_is_one_durable_intent(
    tmp_path: Path,
) -> None:
    """Retry one committed create intent without duplicating its aggregate.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        sqlite3.Error: Durable authority count cannot be inspected.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(tmp_path / "create-retry")
    try:
        service = harness.detached_experiment_service()
        payload = harness.create_payload("acceptance-lost-create-response")
        first = service.create_experiment(payload)
        retried = service.create_experiment(payload)
        assert first.created is True
        assert retried.created is False
        assert retried.experiment.experiment_id == first.experiment.experiment_id
        assert len(service.list_task_runs(first.experiment.experiment_id).items) == 1
        assert harness.composition.repository is not None
        history = harness.composition.repository.list_experiments(limit=100)
        assert [item.experiment_id for item in history.items] == [
            first.experiment.experiment_id
        ]
        events = harness.composition.repository.list_events(
            first.experiment.experiment_id
        )
        assert sum(item.kind == "experiment.accepted" for item in events) == 1
        with sqlite3.connect(harness.database) as connection:
            binding_count = connection.execute(
                "SELECT COUNT(*) FROM studio_benchmark_experiment_bindings "
                "WHERE experiment_id = ?",
                (first.experiment.experiment_id,),
            ).fetchone()[0]
        assert binding_count == 1
        assert harness.device.calls == []
        assert harness.terminal_llm.calls == 0
    finally:
        harness.composition.shutdown()


def test_actual_http_sse_reconnect_and_slow_client_do_not_block_worker(
    tmp_path: Path,
) -> None:
    """Use actual HTTP/SSE while one subscriber deliberately stays slow.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        TimeoutError: Worker or server teardown exceeds its bound.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "actual-http",
        block_push=True,
    )
    server_fixture = harness.start_http_server()
    address = (
        "127.0.0.1",
        int(server_fixture.server.server_address[1]),
    )
    slow_connection = None
    try:
        bootstrap = json.dumps(server_fixture.bootstrap, sort_keys=True)
        assert server_fixture.bootstrap["warning"] == (
            "fake device only; not real Android evidence"
        )
        assert str(tmp_path) not in bootstrap
        status, created = _http_request(
            address,
            "POST",
            "/studio/benchmark-experiments",
            harness.create_payload("acceptance-http-create"),
        )
        assert status == 202
        experiment_id = created["experiment"]["experimentId"]
        if not harness.device.push_started.wait(timeout=5):
            raise TimeoutError("actual HTTP worker did not reach fake setup")
        path = (
            f"/studio/benchmark-experiments/{experiment_id}"
            "/events/stream?after=1"
        )
        slow_connection, slow_response = _open_sse(address, path)
        assert slow_response.status == 200
        harness.device.release_push.set()
        terminal = harness.wait_terminal(experiment_id)
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "completed"
        assert harness.composition.repository is not None
        page = harness.composition.repository.query_events(
            experiment_id,
            after=0,
            limit=500,
        )
        assert page.terminal is True
        assert [item.sequence for item in page.items] == list(
            range(1, page.high_water_mark + 1)
        )
        status, public_page = _http_request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/events"
            "?after=0&limit=500",
        )
        assert status == 200
        assert public_page["highWaterMark"] == page.high_water_mark
        reconnect, reconnect_response = _open_sse(
            address,
            (
                f"/studio/benchmark-experiments/{experiment_id}"
                "/events/stream"
            ),
            last_event_id=str(page.high_water_mark - 1),
        )
        assert reconnect_response.status == 200
        body = reconnect_response.read()
        reconnect.close()
        assert b"event: journal" in body
        assert f"id: {page.high_water_mark}\n".encode() in body
        assert b"experiment.terminal" in body
        assert harness.composition.publications is not None
        publication = harness.composition.publications.get_publication(
            experiment_id
        )
        assert publication is not None
        slow_connection.close()
        slow_connection = None
    finally:
        harness.device.release_push.set()
        if slow_connection is not None:
            slow_connection.close()
        server_fixture.close()


def test_actual_restart_interrupts_uncertain_running_without_replay(
    tmp_path: Path,
) -> None:
    """Recover a labeled running crash window without repeating effects.

    Args:
        tmp_path: Temporary durable workspace.

    Raises:
        AssertionError: Recovery does not remain interruption-only.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "recovery-interrupted"
    )
    reopened = None
    try:
        assert harness.composition.repository is not None
        service = harness.detached_experiment_service()
        created = service.create_experiment(
            harness.create_payload("acceptance-recovery-interrupted")
        ).experiment
        repository = harness.composition.repository
        crashed_owner = "benchmark-process-crashed-acceptance"
        assert repository.enroll_accepted_experiment(
            created.experiment_id,
            process_owner_id=crashed_owner,
        )
        claimed = repository.claim_experiment(
            created.experiment_id,
            process_owner_id=crashed_owner,
            timestamp=created.accepted_at + 1,
        )
        task_run_id = claimed.task_runs[0].task_run_id
        repository.transition_execution(
            created.experiment_id,
            task_run_id,
            process_owner_id=crashed_owner,
            experiment_lifecycle=StudioBenchmarkExperimentLifecycle.RUNNING,
            task_lifecycle=StudioBenchmarkTaskRunLifecycle.RUNNING,
            timestamp=created.accepted_at + 2,
            event=StudioBenchmarkEventDraftV1(
                event_id="benchmark-event-11111111111111111111111111111111",
                timestamp=created.accepted_at + 2,
                source=StudioBenchmarkEventSource.WORKER,
                kind="worker.execution_started",
                task_run_id=task_run_id,
                phase="runtime",
            ),
        )
        calls_before = tuple(harness.device.calls)
        llm_calls_before = harness.terminal_llm.calls
        harness.composition.shutdown()
        reopened = reopen_layered_acceptance_harness(harness)
        assert reopened.composition.recovery_summary is not None
        assert reopened.composition.recovery_summary.interrupted == 1
        terminal = reopened.composition.experiments.get_experiment(
            created.experiment_id
        )
        assert terminal.lifecycle.value == "terminal"
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "interrupted"
        task = reopened.composition.experiments.get_task_run(
            created.experiment_id,
            task_run_id,
        )
        assert task.terminal_reason is not None
        assert task.terminal_reason.value == "interrupted"
        assert task.result is None
        assert tuple(harness.device.calls) == calls_before
        assert harness.terminal_llm.calls == llm_calls_before
        assert reopened.composition.repository is not None
        events = reopened.composition.repository.list_events(
            created.experiment_id
        )
        assert sum(item.kind == "recovery.interrupted" for item in events) == 1
        assert sum(item.kind == "experiment.terminal" for item in events) == 1
    finally:
        if reopened is not None:
            reopened.composition.shutdown()
        else:
            harness.composition.shutdown()


def test_actual_restart_retries_only_finalizing_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recover publication after immutable result commit without rerunning Core.

    Args:
        tmp_path: Temporary durable workspace.
        monkeypatch: Scoped publisher failure injector.

    Raises:
        TimeoutError: The worker does not reach finalizing in time.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "recovery-publication"
    )
    reopened = None
    try:
        assert harness.composition.publisher is not None
        assert harness.composition.experiments is not None

        def fail_publication(
            experiment_id: str,
            task_run_id: str,
            *,
            timestamp: int,
        ) -> None:
            """Fail exactly at the managed publication boundary.

            Args:
                experiment_id: Owning Experiment identity.
                task_run_id: Committed TaskRun identity.
                timestamp: Publication-attempt timestamp.

            Raises:
                RuntimeError: Always, to model process loss.

            Returns:
                None.
            """
            del experiment_id, task_run_id, timestamp
            raise RuntimeError("injected finalizing publication crash")

        monkeypatch.setattr(
            harness.composition.publisher,
            "publish",
            fail_publication,
        )
        created = harness.composition.experiments.create_experiment(
            harness.create_payload("acceptance-recovery-publication")
        ).experiment
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            current = harness.composition.experiments.get_experiment(
                created.experiment_id
            )
            if current.lifecycle.value == "finalizing":
                break
            time.sleep(0.01)
        else:
            raise TimeoutError("actual worker did not stop in finalizing")
        before = harness.composition.experiments.list_task_runs(
            created.experiment_id
        ).items[0]
        assert before.result is not None
        assert before.result_fingerprint is not None
        result_fingerprint = before.result_fingerprint
        result_payload = before.result.model_dump(mode="json")
        device_calls = tuple(harness.device.calls)
        llm_calls = harness.terminal_llm.calls
        harness.composition.shutdown()
        reopened = reopen_layered_acceptance_harness(harness)
        assert reopened.composition.recovery_summary is not None
        assert reopened.composition.recovery_summary.publication_only == 1
        assert reopened.composition.experiments is not None
        terminal = reopened.composition.experiments.get_experiment(
            created.experiment_id
        )
        assert terminal.lifecycle.value == "terminal"
        assert terminal.terminal_reason is not None
        assert terminal.terminal_reason.value == "completed"
        after = reopened.composition.experiments.list_task_runs(
            created.experiment_id
        ).items[0]
        assert after.result_fingerprint == result_fingerprint
        assert after.result is not None
        assert after.result.model_dump(mode="json") == result_payload
        assert tuple(harness.device.calls) == device_calls
        assert harness.terminal_llm.calls == llm_calls
        assert after.replay_availability.value == "available"
        assert after.report_availability.value == "available"
        assert after.trajectory_availability.value == "available"
        assert after.bundle_availability.value == "available"
        assert reopened.composition.repository is not None
        events = reopened.composition.repository.list_events(
            created.experiment_id
        )
        assert sum(item.kind == "experiment.terminal" for item in events) == 1
    finally:
        if reopened is not None:
            reopened.composition.shutdown()
        else:
            harness.composition.shutdown()


def test_core_matrix_keeps_fairness_and_studio_limit_separate(
    tmp_path: Path,
) -> None:
    """Execute the deterministic 2x2x2 Core matrix with paired reporting.

    Args:
        tmp_path: Temporary Core artifact root.

    Raises:
        AssertionError: Schedule, outcomes, or reporting lose causal parity.

    Returns:
        None.
    """
    plan = _plan()
    protocol = ExperimentProtocol.model_validate(
        {
            "seed": 23,
            "repeats": 2,
            "isolation": {
                "reset": "before_each_task",
                "cleanup": "after_each_run",
                "require_verified_reset": True,
            },
            "budget": {
                "max_interactions": 3,
                "max_activations": 30,
                "timeout_seconds": 30,
            },
        }
    )
    agents = {
        "back": _agent(Action(ActionType.KEY, {"code": "back"})),
        "home": _agent(Action(ActionType.KEY, {"code": "home"})),
    }
    schedule = build_schedule(plan, protocol, list(agents))
    assert len(schedule) == 8
    assert schedule == build_schedule(plan, protocol, list(agents))
    assert all(
        entry.seed
        == next(
            other.seed
            for other in schedule
            if other.task_id == entry.task_id
            and other.repeat == entry.repeat
            and other.agent_id != entry.agent_id
        )
        for entry in schedule
    )
    result = BenchmarkExperimentRuntime().run(
        plan,
        protocol,
        agents,
        run_config=BenchmarkRunConfig(
            artifact_root=tmp_path,
            experiment_id="layered-core-matrix",
        ),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert result.counts == {
        "pass": 4,
        "fail": 4,
        "invalid": 0,
        "skipped": 0,
    }
    assert len({item.task_run_id for item in result.results}) == 8
    assert all(
        item.task_instance_identity
        == next(
            other.task_instance_identity
            for other in result.results
            if other.task_id == item.task_id
            and other.repeat == item.repeat
            and other.agent_id != item.agent_id
        )
        for item in result.results
    )
    assert "benchmark.protocol.shared_device_state_across_agents" in (
        result.fairness_warnings
    )
    report = load_experiment_report(
        tmp_path / result.experiment_id / "experiment-report.json"
    )
    assert len(report.agent_metrics) == 2
    for metrics in report.agent_metrics:
        assert metrics.eligible_count == 4
        assert metrics.success_rate_micro == 0.5
        assert metrics.success_rate_macro == 0.5
        assert metrics.counts["invalid"] == 0
        assert metrics.counts["skipped"] == 0
    comparison = report.comparisons[0]
    assert comparison.paired is True
    assert comparison.matched_count == 4
    assert comparison.unmatched_eligible_count == 0
    assert comparison.significance_claimed is False
    assert report.fairness_warnings == result.fairness_warnings


def test_core_cleanup_stop_preserves_evaluation_and_skips_only_remaining(
    tmp_path: Path,
) -> None:
    """Keep completed evaluation when cleanup policy stops later Core work.

    Args:
        tmp_path: Temporary Core artifact root.

    Raises:
        AssertionError: Cleanup failure erases or mislabels evidence.

    Returns:
        None.
    """
    first = _task("one")
    first["cleanup_initializer"][0]["params"]["fail"] = True
    compiled = compile_benchmark_suite(
        BenchmarkSuite.model_validate([first, _task("two")])
    )
    assert compiled.plan is not None
    protocol = ExperimentProtocol.model_validate(
        {
            "failure": {
                "initializer": {
                    "outcome": "invalidate",
                    "continue_suite": True,
                    "preserve_evidence": True,
                },
                "agent": {
                    "outcome": "evaluate_if_possible",
                    "continue_suite": True,
                    "preserve_evidence": True,
                },
                "evaluator": {
                    "outcome": "invalidate",
                    "continue_suite": True,
                    "preserve_evidence": True,
                },
                "cleanup": {
                    "outcome": "invalidate",
                    "continue_suite": False,
                    "preserve_evidence": True,
                },
            }
        }
    )
    result = BenchmarkExperimentRuntime().run(
        compiled.plan,
        protocol,
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert [item.outcome for item in result.results] == [
        BenchmarkOutcome.INVALID,
        BenchmarkOutcome.SKIPPED,
    ]
    assert result.results[0].evaluation is not None
    assert result.results[0].evaluation.is_pass is True
    assert result.results[1].evaluation is None


def test_studio_rejects_each_public_cardinality_before_any_effect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject Agent, Task, and repeat expansion before profile/runtime use.

    Args:
        tmp_path: Temporary durable workspace.
        monkeypatch: Scoped profile-boundary canary injector.

    Raises:
        AssertionError: A rejected definition reaches a later boundary.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "cardinality-public"
    )
    try:
        _agent_record, second_revision = (
            harness.application_service.create_agent(
                "Layered Acceptance Agent Two",
                initial_document=(
                    harness.application_service.get_revision(
                        harness.agent_id,
                        harness.revision_id,
                    ).document.to_json_dict()
                ),
            )
        )
        dimensions = []
        multiple_agents = json.loads(json.dumps(harness.definition))
        multiple_agents["agentRevisions"].append(
            {
                "agentId": second_revision.agent_id,
                "revisionId": second_revision.revision_id,
            }
        )
        dimensions.append(multiple_agents)
        multiple_tasks = json.loads(json.dumps(harness.definition))
        multiple_tasks["benchmark"]["taskIds"].append(
            "syntactically-valid-second-task"
        )
        dimensions.append(multiple_tasks)
        multiple_repeats = json.loads(json.dumps(harness.definition))
        multiple_repeats["protocol"]["repeats"] = 2
        dimensions.append(multiple_repeats)

        def forbidden_profile_lookup(profile_id: str) -> bool:
            """Reject any profile lookup after a cardinality violation.

            Args:
                profile_id: Unused candidate profile identity.

            Raises:
                AssertionError: Always, because cardinality must win first.

            Returns:
                Never returns.
            """
            del profile_id
            raise AssertionError("profile lookup crossed cardinality gate")

        monkeypatch.setattr(
            harness.composition.profiles,
            "contains",
            forbidden_profile_lookup,
        )
        service = harness.detached_experiment_service()
        for index, definition in enumerate(dimensions):
            with pytest.raises(StudioBenchmarkValidationError) as preview:
                harness.composition.service.preview(definition)
            assert preview.value.code == "benchmark.preview.unsupported_cardinality"
            with pytest.raises(StudioBenchmarkValidationError) as create:
                service.create_experiment(
                    {
                        "schemaVersion": 1,
                        "clientRequestId": f"cardinality-create-{index}",
                        "previewFingerprint": "sha256:" + "0" * 64,
                        "definition": definition,
                    }
                )
            assert create.value.code == "benchmark.preview.unsupported_cardinality"
        assert harness.composition.repository is not None
        assert harness.composition.repository.list_experiments(limit=100).items == ()
        assert harness.device.calls == []
        assert harness.terminal_llm.calls == 0
    finally:
        harness.composition.shutdown()


def test_worker_preflight_rejects_malformed_aggregate_without_truncation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reject a durable two-TaskRun aggregate before target or Core authority.

    Args:
        tmp_path: Temporary durable workspace.
        monkeypatch: Scoped target-resolution canary injector.

    Raises:
        AssertionError: Defensive preflight reaches target/runtime effects.

    Returns:
        None.
    """
    harness = build_layered_acceptance_harness(
        tmp_path / "cardinality-defensive"
    )
    try:
        service = harness.detached_experiment_service()
        created = service.create_experiment(
            harness.create_payload("cardinality-defensive-create")
        ).experiment
        assert harness.composition.repository is not None
        owner = "benchmark-process-cardinality-defensive"
        assert harness.composition.repository.enroll_accepted_experiment(
            created.experiment_id,
            process_owner_id=owner,
        )
        claimed = harness.composition.repository.claim_experiment(
            created.experiment_id,
            process_owner_id=owner,
            timestamp=created.accepted_at + 1,
        )
        malformed = replace(
            claimed,
            task_runs=(claimed.task_runs[0], claimed.task_runs[0]),
        )

        def forbidden_resolve(profile_id: str) -> object:
            """Reject any target resolution after malformed cardinality.

            Args:
                profile_id: Unused private profile identity.

            Raises:
                AssertionError: Always.

            Returns:
                Never returns.
            """
            del profile_id
            raise AssertionError("target resolution crossed cardinality gate")

        monkeypatch.setattr(
            harness.composition.profiles,
            "resolve",
            forbidden_resolve,
        )
        assert harness.composition.execution is not None
        with pytest.raises(Exception) as error:
            harness.composition.execution.prepare(malformed)
        assert getattr(error.value, "code", "") == (
            "benchmark.experiment.cardinality_unsupported"
        )
        assert harness.device.calls == []
        assert harness.terminal_llm.calls == 0
        assert service.list_task_runs(created.experiment_id).items[0].result is None
    finally:
        harness.composition.shutdown()
