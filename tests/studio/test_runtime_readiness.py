"""Static runtime readiness and pre-accept Studio Run gate contracts."""

from __future__ import annotations

import json
import sqlite3
import threading
import urllib.request
from copy import deepcopy
from pathlib import Path

import pytest

from zhixing.graph import AgentGraph

from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.device_profiles import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
)
from zhixing.studio.flow_template_loader import get_flow_template_document
from zhixing.studio.readiness import (
    StudioRuntimeReadinessService,
    analyze_studio_android_topology,
)
from zhixing.studio.httpd import create_http_server
from zhixing.studio.revision_verifier import verify_immutable_agent_revision
from zhixing.studio.run_errors import StudioRunValidationError
from zhixing.studio.run_events import DurableRunEventService
from zhixing.studio.run_execution import ProductionComponentResolverFactory
from zhixing.studio.run_repository import SQLiteStudioRunRepository
from zhixing.studio.run_service import StudioRunApplicationService

from .test_documents_catalog_compiler import _planner_document
from .test_run_models_repository import _request


class DeviceSideEffectCanary:
    """Raise if static readiness accidentally touches a device method."""

    def __getattr__(self, name: str) -> object:
        """Reject every accidental device interaction.

        Args:
            name: Requested attribute.

        Raises:
            AssertionError: Readiness crossed the device boundary.

        Returns:
            object: This method never returns.
        """
        raise AssertionError(f"static readiness touched device attribute {name}")


class ModelSideEffectCanary:
    """Count and reject any model invocation before Run acceptance."""

    def __init__(self) -> None:
        """Initialize a zero-call canary.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls = 0

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Reject a model call that crosses the readiness boundary.

        Args:
            prompt (str): Unsafe premature model prompt.
            images (list[str] | None): Unsafe premature image inputs.

        Raises:
            AssertionError: Always, because readiness must not call a model.

        Returns:
            str: Never returned.
        """
        del prompt, images
        self.calls += 1
        raise AssertionError("readiness invoked the model")


class ReadinessHTTPComposition:
    """Expose readiness to the HTTP layer without owning execution workers."""

    def __init__(self, readiness: StudioRuntimeReadinessService) -> None:
        """Store the side-effect-free readiness service.

        Args:
            readiness: Shared readiness application service.

        Raises:
            None.

        Returns:
            None.
        """
        self.readiness = readiness

    def shutdown(self, *, wait: bool = True) -> None:
        """Satisfy the HTTP server ownership protocol without worker state.

        Args:
            wait: Ignored compatibility flag.

        Raises:
            None.

        Returns:
            None.
        """
        del wait


def _readiness_fixture(
    database: Path,
    *,
    secrets: dict[str, str],
    with_profile: bool = True,
) -> tuple[
    StudioRuntimeReadinessService,
    SQLiteAgentDocumentRepository,
    str,
    str,
    AndroidDeviceProfileResolver,
]:
    """Create one valid saved Planner revision and static authorities.

    Args:
        database: Temporary SQLite database.
        secrets: Mutable process SecretRef mapping.
        with_profile: Whether a safe fake-device authority exists.

    Raises:
        ValueError: Fixture graph or profile contracts are invalid.

    Returns:
        tuple: Readiness service, repository, identities, and profiles.
    """
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents)
    agent, revision = authoring.create_agent(
        "Readiness fixture",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    profiles = AndroidDeviceProfileResolver(
        {
            "safe-android": AndroidDeviceProfile(
                "safe-android",
                device=DeviceSideEffectCanary(),
                label="Research Android",
            )
        }
        if with_profile
        else {}
    )
    components = ProductionComponentResolverFactory(secret_provider=secrets)
    readiness = StudioRuntimeReadinessService(
        agents=agents,
        catalog=catalog,
        components=components,
        profiles=profiles,
        secrets=secrets,
        contract_catalog=catalog.node_contract_catalog(),
    )
    return readiness, agents, agent.agent_id, revision.revision_id, profiles


def test_readiness_is_ready_without_constructing_component_or_device(tmp_path: Path) -> None:
    """Prove static exact readiness closes metadata and SecretRef authority only."""
    readiness, _agents, agent_id, revision_id, _profiles = _readiness_fixture(
        tmp_path / "studio.sqlite3",
        secrets={
            "api_key": "secret-canary-value",
            "base_url": "url-canary-value",
        },
    )
    process = readiness.process_readiness()
    exact = readiness.revision_readiness(
        agent_id, revision_id, "safe-android"
    )
    assert process.ready is True
    assert exact.ready is True
    encoded = str(
        {
            "process": process.model_dump(mode="json", by_alias=True),
            "exact": exact.model_dump(mode="json", by_alias=True),
        }
    )
    assert "secret-canary-value" not in encoded
    assert "target_key" not in encoded
    assert "serial" not in encoded


def test_process_readiness_lists_loaded_secret_identities_without_values(
    tmp_path: Path,
) -> None:
    """Project configured file identities instead of one hard-coded alias."""
    readiness, _agents, _agent_id, _revision_id, _profiles = _readiness_fixture(
        tmp_path / "studio.sqlite3",
        secrets={"api_key": "secret-canary-value", "base_url": "url-canary-value"},
    )
    process = readiness.process_readiness()
    assert {(item.secret_ref, item.configured) for item in process.secrets} == {
        ("api_key", True),
        ("base_url", True),
    }
    encoded = str(process.model_dump(mode="json", by_alias=True))
    assert "secret-canary-value" not in encoded
    assert "url-canary-value" not in encoded


def test_readiness_reports_missing_secret_and_profile_with_safe_identities(
    tmp_path: Path,
) -> None:
    """Return stable remediation diagnostics without private configuration facts."""
    readiness, _agents, agent_id, revision_id, _profiles = _readiness_fixture(
        tmp_path / "studio.sqlite3",
        secrets={},
        with_profile=False,
    )
    exact = readiness.revision_readiness(agent_id, revision_id, "stale-profile")
    assert exact.ready is False
    assert {(item.code, item.subject_identity) for item in exact.diagnostics} == {
        ("studio.device.profile_unknown", "stale-profile"),
        ("studio.readiness.secret_missing", "api_key"),
        ("studio.readiness.secret_missing", "base_url"),
    }


def test_readiness_rejects_malformed_historical_secret_ref(tmp_path: Path) -> None:
    """Keep an old malformed snapshot blocked without resolving any value."""
    readiness, agents, agent_id, revision_id, _profiles = _readiness_fixture(
        tmp_path / "studio.sqlite3",
        secrets={
            "api_key": "secret-canary-value",
            "base_url": "url-canary-value",
        },
    )
    snapshot = verify_immutable_agent_revision(
        agents,
        agent_id,
        revision_id,
        contract_catalog=readiness.contract_catalog,
    )
    raw = deepcopy(snapshot.agent_graph)
    reasoning = next(node for node in raw["nodes"] if node["id"] == "reasoning")
    reasoning["component"]["candidates"][0]["dependencies"]["llm"][
        "params"
    ]["api_key"] = {"secret_ref": ""}
    graph = AgentGraph.model_validate(raw)
    historical = snapshot.model_copy(
        update={"agent_graph": raw, "canonical_hash": graph.canonical_hash()}
    )
    result = readiness.snapshot_readiness(historical, "safe-android")
    assert result.ready is False
    assert any(
        item.code == "studio.readiness.secret_ref_invalid"
        for item in result.diagnostics
    )


def test_standard_template_has_explicit_android_topology_facts(
    tmp_path: Path,
) -> None:
    """Derive the closed loop without binding components or touching a device.

    Args:
        tmp_path: Isolated Studio database directory.

    Raises:
        AssertionError: The shipped template loses a required topology fact.

    Returns:
        None.
    """
    readiness, agents, agent_id, revision_id, _profiles = _readiness_fixture(
        tmp_path / "studio.sqlite3",
        secrets={"api_key": "key", "base_url": "url"},
    )
    snapshot = verify_immutable_agent_revision(
        agents,
        agent_id,
        revision_id,
        contract_catalog=readiness.contract_catalog,
    )
    facts, diagnostics = analyze_studio_android_topology(
        AgentGraph.model_validate(snapshot.agent_graph)
    )
    assert diagnostics == ()
    assert facts.observe_node_ids == ("studio_generated.perception.observe",)
    assert facts.action_request_node_ids == (
        "studio_generated.action_executor.action_request",
    )
    assert facts.action_executor_node_ids == ("action_executor",)
    assert facts.terminal_node_ids == (
        "studio_generated.action_executor.terminal",
    )
    assert facts.has_typed_action_request is True
    assert facts.has_terminal_gated_output is True
    assert facts.has_nonterminal_feedback is True
    assert facts.policies_bounded is True


def test_old_linear_revision_is_readable_but_run_blocked_without_effects(
    tmp_path: Path,
) -> None:
    """Block legacy Studio topology before Run persistence or device access.

    Args:
        tmp_path: Isolated Studio database directory.

    Raises:
        AssertionError: Readiness mutates history or allows a durable Run.

    Returns:
        None.
    """
    database = tmp_path / "studio.sqlite3"
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents)
    agent, revision = authoring.create_agent(
        "Legacy linear",
        initial_document=_planner_document(),
    )
    profiles = AndroidDeviceProfileResolver(
        {
            "safe-android": AndroidDeviceProfile(
                "safe-android",
                device=DeviceSideEffectCanary(),
                label="Research Android",
            )
        }
    )
    model_canary = ModelSideEffectCanary()
    readiness = StudioRuntimeReadinessService(
        agents=agents,
        catalog=catalog,
        components=ProductionComponentResolverFactory(
            secret_provider={"api_key": "key", "base_url": "url"},
            dependency_provider={"llm": model_canary},
        ),
        profiles=profiles,
        secrets={"api_key": "key", "base_url": "url"},
        contract_catalog=catalog.node_contract_catalog(),
    )
    exact = readiness.revision_readiness(
        agent.agent_id,
        revision.revision_id,
        "safe-android",
    )
    assert exact.ready is False
    assert {item.category for item in exact.diagnostics} == {"revision"}
    assert {item.code for item in exact.diagnostics} == {
        "studio.policy.legacy_revision_ineligible",
    }
    persisted = agents.get_revision(agent.agent_id, revision.revision_id)
    assert persisted.compile_snapshot.status == "valid"

    runs = SQLiteStudioRunRepository(database)
    service = StudioRunApplicationService(
        agents=agents,
        runs=runs,
        events=DurableRunEventService(runs),
        process_owner_id="topology-readiness-test",
        readiness=readiness,
    )
    request = _request(agent.agent_id, revision.revision_id)
    request["deviceProfileId"] = "safe-android"
    with pytest.raises(StudioRunValidationError) as captured:
        service.create_run(request)
    assert captured.value.code == "studio.policy.legacy_revision_ineligible"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM studio_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM studio_run_events").fetchone()[0] == 0
    assert model_canary.calls == 0


def test_new_unready_run_is_rejected_before_any_durable_side_effect(
    tmp_path: Path,
) -> None:
    """Keep known configuration mistakes out of Run and event history."""
    database = tmp_path / "studio.sqlite3"
    readiness, agents, agent_id, revision_id, _profiles = _readiness_fixture(
        database,
        secrets={},
    )
    runs = SQLiteStudioRunRepository(database)
    service = StudioRunApplicationService(
        agents=agents,
        runs=runs,
        events=DurableRunEventService(runs),
        process_owner_id="readiness-test",
        readiness=readiness,
    )
    request = _request(agent_id, revision_id)
    request["deviceProfileId"] = "safe-android"
    with pytest.raises(StudioRunValidationError) as captured:
        service.create_run(request)
    assert captured.value.code == "studio.readiness.secret_missing"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM studio_runs").fetchone()[0] == 0
        assert connection.execute("SELECT COUNT(*) FROM studio_run_events").fetchone()[0] == 0


def test_existing_idempotent_run_wins_after_environment_drift(tmp_path: Path) -> None:
    """Return a prior accepted identity before consulting changed readiness."""
    database = tmp_path / "studio.sqlite3"
    secrets = {
        "api_key": "secret-canary-value",
        "base_url": "url-canary-value",
    }
    readiness, agents, agent_id, revision_id, _profiles = _readiness_fixture(
        database,
        secrets=secrets,
    )
    runs = SQLiteStudioRunRepository(database)
    service = StudioRunApplicationService(
        agents=agents,
        runs=runs,
        events=DurableRunEventService(runs),
        process_owner_id="readiness-test",
        readiness=readiness,
    )
    request = _request(agent_id, revision_id)
    request["deviceProfileId"] = "safe-android"
    first, created = service.create_run(request)
    assert created is True
    secrets.clear()
    repeated, created_again = service.create_run(request)
    assert created_again is False
    assert repeated.run_id == first.run_id


def test_readiness_http_resources_are_safe_and_exact(tmp_path: Path) -> None:
    """Serve both readiness projections without exposing configured values."""
    database = tmp_path / "studio.sqlite3"
    secret_value = "http-secret-canary-value"
    readiness, agents, agent_id, revision_id, _profiles = _readiness_fixture(
        database,
        secrets={"api_key": secret_value, "base_url": "url-canary-value"},
    )
    authoring = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=agents,
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=authoring,
        run_composition=ReadinessHTTPComposition(readiness),  # type: ignore[arg-type]
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    try:
        with urllib.request.urlopen(
            f"http://{host}:{port}/studio/runtime-readiness",
            timeout=2,
        ) as response:
            process_body = response.read().decode("utf-8")
            assert response.headers["Cache-Control"] == "private, no-store"
        with urllib.request.urlopen(
            (
                f"http://{host}:{port}/studio/agents/{agent_id}/revisions/"
                f"{revision_id}/run-readiness?deviceProfileId=safe-android"
            ),
            timeout=2,
        ) as response:
            exact_body = response.read().decode("utf-8")
        assert json.loads(process_body)["ready"] is True
        assert json.loads(exact_body)["ready"] is True
        assert secret_value not in process_body + exact_body
        assert "serial" not in process_body + exact_body
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
