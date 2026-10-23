"""Policy, lowering, persistence, and execution-gate tests for Studio schema 3."""

from __future__ import annotations

from copy import deepcopy
import json
import sqlite3

import pytest
from pydantic import ValidationError

from zhixing.graph import compile_studio_flow_document
from zhixing.studio import (
    STUDIO_CAPABILITY_AUTHORING_POLICY,
    STUDIO_CAPABILITY_LOWERING_PROFILE,
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    StudioCapabilityDocument,
    build_studio_component_catalog,
)
from zhixing.studio.eligibility import evaluate_revision_eligibility
from zhixing.studio.flow_template_loader import get_flow_template_document
from zhixing.studio.run_errors import StudioRunValidationError
from zhixing.studio.run_events import DurableRunEventService
from zhixing.studio.run_artifacts import LocalStudioRunArtifactStore
from zhixing.studio.run_execution import AndroidStudioRunExecutionAdapter
from zhixing.studio.run_repository import SQLiteStudioRunRepository
from zhixing.studio.run_service import StudioRunApplicationService
from zhixing.studio import repository as studio_repository

from .test_documents_catalog_compiler import _planner_document


def _capability_service(database) -> tuple[StudioApplicationService, object]:
    """Build one side-effect-free Studio authoring service.

    Args:
        database: Temporary SQLite path.

    Raises:
        sqlite3.Error: Database migration fails.

    Returns:
        Application service and its exact safe Catalog.
    """
    catalog = build_studio_component_catalog()
    return (
        StudioApplicationService(
            catalog=catalog,
            repository=SQLiteAgentDocumentRepository(database),
        ),
        catalog,
    )


def test_schema3_hash_and_round_trip_exclude_presentation() -> None:
    """Keep capability identity stable across presentation-only changes."""
    raw = get_flow_template_document("modular_baseline")
    parsed = StudioCapabilityDocument.model_validate(raw)
    encoded = parsed.to_json_dict()
    feedback = next(
        item["feedback"] for item in encoded["relations"] if item["kind"] == "feedback"
    )
    assert feedback["maxIterations"] == 10
    assert feedback["onExhausted"] == "fail"
    assert "max_iterations" not in feedback
    assert StudioCapabilityDocument.model_validate(encoded) == parsed
    changed = deepcopy(encoded)
    changed["presentation"]["nodes"]["tpl_reasoning"]["x"] += 250
    changed["authoring"]["updatedAt"] += 1
    assert StudioCapabilityDocument.model_validate(changed).semantic_hash() == parsed.semantic_hash()


def test_schema3_rejects_forbidden_shape_identity_output_and_unsafe_values() -> None:
    """Reject raw graph objects, generated IDs, invalid Output edges, and secrets."""
    raw = get_flow_template_document("modular_baseline")
    forbidden = deepcopy(raw)
    forbidden["semantic"] = {"nodes": [{"kind": "router"}]}
    with pytest.raises(ValidationError):
        StudioCapabilityDocument.model_validate(forbidden)

    generated = deepcopy(raw)
    generated["capabilities"][0]["logicalId"] = "studio_generated.memory"
    with pytest.raises(ValidationError):
        StudioCapabilityDocument.model_validate(generated)

    output = deepcopy(raw)
    output["relations"][-1]["kind"] = "data"
    with pytest.raises(ValidationError):
        StudioCapabilityDocument.model_validate(output)

    unsafe = deepcopy(raw)
    unsafe["capabilities"][0]["implementation"]["candidates"][0]["params"] = {
        "api_key": "resolved-value",
        "source_path": "/private/runtime",
    }
    with pytest.raises(ValidationError):
        StudioCapabilityDocument.model_validate(unsafe)


def test_catalog_has_exact_authoring_placements_and_synthetic_executor() -> None:
    """Expose only core/approved capability entries as canvas-authorable."""
    catalog = build_studio_component_catalog()
    families = {item.family: item for item in catalog.capability_families}
    assert set(families) == {
        "perception", "planner", "reasoning", "memory",
        "action_executor", "verifier", "grounder", "tool",
    }
    llm = next(item for item in catalog.components if item.namespace == "llm")
    assert llm.placement == "dependency_only"
    runtime = next(
        item for item in catalog.components
        if item.namespace == "zhixing.runtime" and item.name == "action_executor"
    )
    assert runtime.placement == "runtime_internal"
    synthetic = next(
        item for item in catalog.components
        if item.namespace == "studio.capability" and item.name == "action_executor"
    )
    assert synthetic.placement == "agent_capability"
    assert synthetic.capability_family == "action_executor"
    legacy = next(item for item in catalog.components if item.name == "legacy_action_executor")
    assert legacy.placement == "runtime_internal"


def test_schema3_lowering_is_deterministic_complete_and_hides_glue() -> None:
    """Generate ordinary executable glue while keeping it out of authoring JSON."""
    catalog = build_studio_component_catalog()
    raw = get_flow_template_document("modular_baseline")
    serialized = json.dumps(raw, sort_keys=True)
    for forbidden in (
        "device_observe", "action_request", '"kind": "condition"',
        '"kind": "router"',
    ):
        assert forbidden not in serialized.lower()
    first = compile_studio_flow_document(
        raw,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    second = compile_studio_flow_document(
        deepcopy(raw),
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert first.is_success and first.graph is not None
    assert second.is_success and second.graph is not None
    assert first.graph.model_dump(mode="json") == second.graph.model_dump(mode="json")
    assert first.projection_map == second.projection_map
    assert first.capability_hash == second.capability_hash
    projected = {(item.graph_kind, item.graph_id) for item in first.projection_map}
    expected = {
        *(('node', node.id) for node in first.graph.nodes),
        *(("edge", f"edge.{index:04d}") for index, _ in enumerate(first.graph.edges)),
    }
    assert projected == expected
    assert any(node.id.endswith(".observe") for node in first.graph.nodes)
    assert any(node.id.endswith(".action_request") for node in first.graph.nodes)
    assert any(node.id.endswith(".terminal") for node in first.graph.nodes)


def test_multiple_perception_instances_receive_distinct_observation_boundaries() -> None:
    """Lower every visible Perception instance without generated-ID collision."""
    catalog = build_studio_component_catalog()
    raw = get_flow_template_document("modular_baseline")
    second = deepcopy(next(item for item in raw["capabilities"] if item["family"] == "perception"))
    second.update({"canvasId": "tpl_perception_second", "logicalId": "perception_second"})
    raw["capabilities"].append(second)
    raw["presentation"]["nodes"]["tpl_perception_second"] = {
        "x": 720, "y": 70, "label": "Perception 2", "renderMode": "card",
    }
    result = compile_studio_flow_document(
        raw,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert result.is_success, result.to_safe_dict()
    assert result.graph is not None
    observe_ids = {node.id for node in result.graph.nodes if node.id.endswith(".observe")}
    assert observe_ids == {
        "studio_generated.perception.observe",
        "studio_generated.perception_second.observe",
    }


def test_schema3_revision_persists_identity_closure_and_revalidates_on_restart(tmp_path) -> None:
    """Persist and reconstruct all four schema-3 identity-closure fields."""
    database = tmp_path / "studio.sqlite3"
    service, catalog = _capability_service(database)
    agent, revision = service.create_agent(
        "Capability Agent",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    snapshot = revision.compile_snapshot
    assert snapshot.authoring_policy == STUDIO_CAPABILITY_AUTHORING_POLICY
    assert snapshot.lowering_profile == STUDIO_CAPABILITY_LOWERING_PROFILE
    assert snapshot.capability_hash == revision.document.semantic_hash()
    assert snapshot.canonical_hash is not None
    assert snapshot.projection_map
    restarted = SQLiteAgentDocumentRepository(database).get_revision(
        agent.agent_id, revision.revision_id,
    )
    assert restarted == revision
    eligibility = evaluate_revision_eligibility(restarted, catalog=catalog)
    assert eligibility.graph_valid is True
    assert eligibility.history_readable is True
    assert eligibility.current_policy_eligible is True
    assert eligibility.environment_ready is None


def test_projection_serialization_failure_leaves_current_revision_unchanged(
    tmp_path,
    monkeypatch,
) -> None:
    """Fail before the transaction when projection JSON cannot be serialized.

    Args:
        tmp_path: Isolated SQLite root.
        monkeypatch: Pytest mutation fixture.

    Raises:
        sqlite3.Error: Fixture persistence or history reads fail.

    Returns:
        None.
    """
    database = tmp_path / "studio.sqlite3"
    service, _catalog = _capability_service(database)
    agent, revision = service.create_agent(
        "Projection rollback",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    changed = revision.document.to_json_dict()
    changed["presentation"]["nodes"]["tpl_reasoning"]["x"] += 40
    parsed = StudioCapabilityDocument.model_validate(changed)
    repository = SQLiteAgentDocumentRepository(database)
    original_json_text = studio_repository._json_text
    calls = 0

    def fail_projection_json(value) -> str:
        """Raise only when the fifth revision payload reaches serialization."""
        nonlocal calls
        calls += 1
        if calls == 5:
            raise TypeError("injected projection serialization failure")
        return original_json_text(value)

    monkeypatch.setattr(studio_repository, "_json_text", fail_projection_json)
    with pytest.raises(TypeError, match="projection serialization"):
        repository.save_revision(
            agent.agent_id,
            base_revision_id=revision.revision_id,
            document=parsed,
            snapshot=revision.compile_snapshot,
        )
    restarted = SQLiteAgentDocumentRepository(database)
    loaded = restarted.get_agent(agent.agent_id)
    current = restarted.get_revision(agent.agent_id, revision.revision_id)
    assert loaded.current_revision_id == revision.revision_id
    assert current == revision


def test_partial_schema3_revision_insert_rolls_back_atomically(
    tmp_path,
    monkeypatch,
) -> None:
    """Roll back a schema-3 revision inserted before an injected transaction error.

    Args:
        tmp_path: Isolated SQLite root.
        monkeypatch: Pytest mutation fixture.

    Raises:
        sqlite3.Error: Fixture persistence or history reads fail.

    Returns:
        None.
    """
    database = tmp_path / "studio.sqlite3"
    service, _catalog = _capability_service(database)
    agent, revision = service.create_agent(
        "Atomic rollback",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    changed = revision.document.to_json_dict()
    changed["presentation"]["nodes"]["tpl_reasoning"]["x"] += 80
    parsed = StudioCapabilityDocument.model_validate(changed)
    repository = SQLiteAgentDocumentRepository(database)
    original_insert = SQLiteAgentDocumentRepository._insert_revision

    def insert_then_fail(connection, **kwargs) -> None:
        """Persist the candidate row and then inject a transactional failure."""
        original_insert(connection, **kwargs)
        raise sqlite3.OperationalError("injected post-insert failure")

    monkeypatch.setattr(
        SQLiteAgentDocumentRepository,
        "_insert_revision",
        staticmethod(insert_then_fail),
    )
    with pytest.raises(sqlite3.OperationalError, match="post-insert"):
        repository.save_revision(
            agent.agent_id,
            base_revision_id=revision.revision_id,
            document=parsed,
            snapshot=revision.compile_snapshot,
        )
    restarted = SQLiteAgentDocumentRepository(database)
    loaded = restarted.get_agent(agent.agent_id)
    current = restarted.get_revision(agent.agent_id, revision.revision_id)
    assert loaded.current_revision_id == revision.revision_id
    assert current == revision
    with sqlite3.connect(database) as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM studio_agent_revisions WHERE agent_id = ?",
            (agent.agent_id,),
        ).fetchone()[0]
    assert count == 1


def test_eligibility_rejects_policy_projection_and_catalog_drift_without_mutation(
    tmp_path,
) -> None:
    """Fail closed on every immutable closure authority without changing history.

    Args:
        tmp_path: Isolated SQLite root.

    Raises:
        sqlite3.Error: Fixture persistence or history reads fail.

    Returns:
        None.
    """
    database = tmp_path / "studio.sqlite3"
    service, catalog = _capability_service(database)
    agent, revision = service.create_agent(
        "Closure drift",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    original = revision.model_dump_json()

    unsupported = revision.model_copy(
        update={
            "compile_snapshot": revision.compile_snapshot.model_copy(
                update={"authoring_policy": "studio.unsupported@9"}
            )
        }
    )
    unsupported_result = evaluate_revision_eligibility(unsupported, catalog=catalog)
    assert unsupported_result.current_policy_eligible is False
    assert any(
        item.code == "studio.policy.authoring_policy_unsupported"
        for item in unsupported_result.diagnostics
    )

    projection = list(revision.compile_snapshot.projection_map)
    projection.pop()
    tampered = revision.model_copy(
        update={
            "compile_snapshot": revision.compile_snapshot.model_copy(
                update={"projection_map": tuple(projection)}
            )
        }
    )
    tampered_result = evaluate_revision_eligibility(tampered, catalog=catalog)
    assert tampered_result.current_policy_eligible is False
    assert {
        item.code for item in tampered_result.diagnostics
    } & {
        "studio.policy.projection_edge_mismatch",
        "studio.policy.lowered_projection_mismatch",
    }

    selected = {
        (
            candidate.namespace,
            candidate.name,
            candidate.version,
        )
        for node in revision.document.capabilities
        for candidate in node.implementation.candidates
    }
    drifted_catalog = catalog.model_copy(
        update={
            "components": tuple(
                item
                for item in catalog.components
                if (item.namespace, item.name, item.version) not in selected
            )
        }
    )
    drift_result = evaluate_revision_eligibility(revision, catalog=drifted_catalog)
    assert drift_result.current_policy_eligible is False
    assert any(
        item.code == "studio.policy.catalog_component_missing"
        for item in drift_result.diagnostics
    )

    persisted = SQLiteAgentDocumentRepository(database).get_revision(
        agent.agent_id,
        revision.revision_id,
    )
    assert persisted.model_dump_json() == original


def test_run_accepts_schema3_but_legacy_revision_creates_no_run_or_event(tmp_path) -> None:
    """Apply policy before ordinary Run persistence while retaining legacy history."""
    database = tmp_path / "studio.sqlite3"
    service, catalog = _capability_service(database)
    current_agent, current_revision = service.create_agent(
        "Current",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    legacy_agent, legacy_revision = service.create_agent(
        "Legacy",
        initial_document=_planner_document(),
    )
    legacy_before = legacy_revision.model_dump_json()
    agents = SQLiteAgentDocumentRepository(database)
    runs = SQLiteStudioRunRepository(database)
    run_service = StudioRunApplicationService(
        agents=agents,
        runs=runs,
        events=DurableRunEventService(runs),
        process_owner_id="test-owner",
        component_catalog=catalog,
    )
    accepted, created = run_service.create_run({
        "clientRequestId": "schema3-request",
        "agentId": current_agent.agent_id,
        "revisionId": current_revision.revision_id,
        "task": {"text": "inspect"},
        "deviceProfileId": "fake-device",
    })
    assert created is True
    assert runs.get_run(accepted.run_id).snapshot.capability_document["schemaVersion"] == 3
    with pytest.raises(StudioRunValidationError) as captured:
        run_service.create_run({
            "clientRequestId": "legacy-request",
            "agentId": legacy_agent.agent_id,
            "revisionId": legacy_revision.revision_id,
            "task": {"text": "must not start"},
            "deviceProfileId": "fake-device",
        })
    assert captured.value.code == "studio.policy.legacy_revision_ineligible"
    connection = sqlite3.connect(database)
    try:
        run_count = connection.execute("SELECT COUNT(*) FROM studio_runs").fetchone()[0]
        event_count = connection.execute("SELECT COUNT(*) FROM studio_run_events").fetchone()[0]
    finally:
        connection.close()
    assert run_count == 1
    assert event_count == 1
    assert agents.get_revision(
        legacy_agent.agent_id,
        legacy_revision.revision_id,
    ).model_dump_json() == legacy_before


def test_run_worker_rejects_tampered_projection_before_binding_or_profile(
    tmp_path,
) -> None:
    """Revalidate immutable worker policy before component and device boundaries.

    Args:
        tmp_path: Isolated SQLite and managed-artifact fixture root.

    Raises:
        StudioRunValidationError: Expected for the tampered projection.

    Returns:
        None.
    """
    database = tmp_path / "studio.sqlite3"
    service, catalog = _capability_service(database)
    agent, revision = service.create_agent(
        "Worker policy",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    agents = SQLiteAgentDocumentRepository(database)
    runs = SQLiteStudioRunRepository(database)
    run_service = StudioRunApplicationService(
        agents=agents,
        runs=runs,
        events=DurableRunEventService(runs),
        process_owner_id="worker-policy-owner",
        component_catalog=catalog,
    )
    accepted, _created = run_service.create_run({
        "clientRequestId": "worker-policy-request",
        "agentId": agent.agent_id,
        "revisionId": revision.revision_id,
        "task": {"text": "inspect"},
        "deviceProfileId": "must-not-resolve",
    })
    record = runs.get_run(accepted.run_id)
    tampered_snapshot = record.snapshot.model_copy(
        update={"projection_map": record.snapshot.projection_map[:-1]}
    )

    class BindingCanary:
        """Fail if policy preflight reaches component resolver construction."""

        def create(self):
            """Reject forbidden binding work.

            Raises:
                AssertionError: Always; policy must fail first.

            Returns:
                Never returns.
            """
            raise AssertionError("component resolver must not be constructed")

    adapter = AndroidStudioRunExecutionAdapter(
        components=BindingCanary(),  # type: ignore[arg-type]
        artifacts=LocalStudioRunArtifactStore(tmp_path / "artifacts", runs),
        component_catalog=catalog,
    )
    with pytest.raises(StudioRunValidationError) as captured:
        adapter.prepare(record.model_copy(update={"snapshot": tampered_snapshot}))
    assert captured.value.code in {
        "studio.policy.lowered_projection_mismatch",
        "studio.policy.projection_edge_mismatch",
    }
