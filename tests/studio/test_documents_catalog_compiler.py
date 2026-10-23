"""Contract tests for Studio schema 2, migration, Catalog, and compilation."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from tests.catalog.test_external_plugins import _spec
from zhixing.catalog import (
    ComponentCatalog,
    DiscoveredComponentEnvironment,
    DiscoveryReport,
    PluginLoadFailure,
)
from zhixing.catalog.builtins import BuiltInComponentCatalog, BuiltInComponentSpec
from zhixing.components import (
    ComponentBundle,
    ComponentCategory,
    ComponentDependencySlot,
)
from zhixing.graph import EdgeKind, NodeKind, compile_studio_flow_document
from zhixing.studio import (
    StudioFlowDocument,
    build_studio_component_catalog,
    migrate_studio_flow_document,
)
from zhixing.studio.flow_template_loader import (
    get_flow_template_document,
    list_flow_templates,
)


def _planner_document() -> dict:
    """Return a minimal valid Catalog-backed schema 2 graph.

    Args:
        None.

    Raises:
        None.

    Returns:
        dict: StudioFlowDocument JSON mapping.
    """
    return {
        "schemaVersion": 2,
        "contractVersion": "1.1",
        "documentId": "document-1",
        "agentId": "agent-1",
        "name": "Planner",
        "semantic": {
            "profile": "mobile_agent",
            "policies": {
                "max_steps": 15,
                "max_feedback_iterations": 3,
            },
            "nodes": [
                {
                    "canvasId": "canvas-input",
                    "logicalId": "input",
                    "kind": "input",
                    "lifecycle": "on_run_start",
                },
                {
                    "canvasId": "canvas-planner",
                    "logicalId": "planner",
                    "kind": "component",
                    "lifecycle": "on_run_start",
                    "role": "planner",
                    "contract": {
                        "id": "zhixing.core.planner",
                        "version": "1.0",
                    },
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": "agent.planner",
                                "name": "universal_planner",
                                "version": "1",
                                "params": {"preset": "manager_style"},
                                "dependencies": {"llm": _llm_dependency()},
                            }
                        ],
                    },
                },
                {
                    "canvasId": "canvas-output",
                    "logicalId": "output",
                    "kind": "output",
                    "lifecycle": "terminal",
                },
            ],
            "edges": [
                {
                    "canvasId": "edge-task",
                    "source": {"canvasId": "canvas-input", "portId": "task"},
                    "target": {"canvasId": "canvas-planner", "portId": "task"},
                    "kind": "data",
                },
                {
                    "canvasId": "edge-result",
                    "source": {"canvasId": "canvas-planner", "portId": "plan"},
                    "target": {"canvasId": "canvas-output", "portId": "result"},
                    "kind": "data",
                },
            ],
        },
        "presentation": {
            "nodes": {
                "canvas-input": {"x": 0, "y": 0, "label": "Input"},
                "canvas-planner": {"x": 200, "y": 0, "label": "Planner"},
                "canvas-output": {"x": 400, "y": 0, "label": "Output"},
            },
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        "authoring": {
            "description": "test",
            "createdAt": 1,
            "updatedAt": 1,
        },
    }


def _llm_dependency() -> dict:
    """Return one valid unresolved LLM dependency reference.

    Args:
        None.

    Raises:
        None.

    Returns:
        dict: Catalog-backed LLM reference containing only a SecretRef identity.
    """
    return {
        "namespace": "llm",
        "name": "openai_llm",
        "version": "1",
        "params": {
            "api_key": {"secret_ref": "api_key"},
            "base_url": {"secret_ref": "base_url"},
            "model": "gpt-4o",
        },
    }


def test_schema2_compile_is_catalog_backed_and_presentation_invariant() -> None:
    """Compile exact component/contract refs without hashing presentation."""
    catalog = build_studio_component_catalog()
    document = _planner_document()
    first = compile_studio_flow_document(
        document,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
        catalog_version=catalog.catalog_version,
        expected_catalog_version=catalog.catalog_version,
    )
    assert first.is_success, first.to_safe_dict()
    assert first.graph is not None
    assert first.graph.contract_version == "1.1"
    changed = deepcopy(document)
    changed["presentation"]["nodes"]["canvas-planner"]["x"] = 999
    changed["presentation"]["viewport"] = {"x": 40, "y": -20, "zoom": 1.5}
    second = compile_studio_flow_document(
        changed,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert second.is_success, second.to_safe_dict()
    assert second.graph is not None
    assert second.graph.canonical_hash() == first.graph.canonical_hash()


def test_schema2_invalid_port_returns_enriched_source_mapping_without_graph() -> None:
    """Return an authoritative diagnostic that maps to the canvas edge/port."""
    catalog = build_studio_component_catalog()
    document = _planner_document()
    document["semantic"]["edges"][0]["target"]["portId"] = "missing"
    result = compile_studio_flow_document(
        document,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert result.graph is None
    issue = next(
        item
        for item in result.diagnostics
        if item.code == "graph.edge.target_port_unknown"
    )
    assert issue.source_id is not None
    assert "edge:edge-task" in issue.source_id
    mapping = next(
        item
        for item in result.source_map
        if item.canvas_edge_id == "edge-task"
        and item.contract_port_id == "missing"
    )
    assert mapping.document_id == "document-1"
    assert mapping.canvas_node_id == "canvas-planner"


def test_catalog_is_deterministic_and_exposes_secret_ref_schema() -> None:
    """Build identical safe payloads without component construction."""
    first = build_studio_component_catalog()
    second = build_studio_component_catalog()
    assert first.catalog_version == second.catalog_version
    assert first.to_safe_dict() == second.to_safe_dict()
    llm = next(
        item
        for item in first.components
        if item.namespace == "llm" and item.name == "openai_llm"
    )
    secret = llm.config_schema["properties"]["api_key"]
    assert secret["x-zhixing-secret-ref"] is True
    assert "default" not in secret
    planner = next(
        item
        for item in first.components
        if item.namespace == "agent.planner"
        and item.name == "universal_planner"
    )
    assert planner.dependency_slots == (
        {
            "name": "llm",
            "required": True,
            "acceptedNamespaces": ["llm"],
            "acceptedCategories": ["runtime_service"],
            "configSchema": {
                "type": "object",
                "required": ["name", "params"],
                "properties": {
                    "namespace": {"type": "string", "const": "llm"},
                    "name": {"type": "string", "minLength": 1},
                    "version": {"type": ["string", "null"]},
                    "params": {"type": "object"},
                },
                "additionalProperties": False,
            },
        },
    )


def test_catalog_propagates_external_dependency_slots_without_values() -> None:
    """Expose formal external slot metadata without implementations or defaults."""
    slot = ComponentDependencySlot(
        name="provider",
        required=True,
        accepted_namespaces=("llm",),
        accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
        config_schema={
            "type": "object",
            "properties": {
                "token": {"type": "string", "default": "not-public"}
            },
        },
    )
    specification = replace(_spec(), dependency_slots=(slot,))
    external = ComponentCatalog(
        (("fixture-provider", ComponentBundle((specification,))),)
    )
    environment = DiscoveredComponentEnvironment(
        catalog=external,
        report=DiscoveryReport(
            (), ("fixture-provider",), (), ("fixture-provider",), ()
        ),
    )
    catalog = build_studio_component_catalog(external_environment=environment)
    descriptor = next(
        item for item in catalog.components if item.identifier == specification.identifier
    )
    encoded = str(descriptor.model_dump(mode="json"))
    assert descriptor.dependency_slots[0]["name"] == "provider"
    assert "not-public" not in encoded
    assert "implementation" not in encoded


def test_schema2_dependency_validation_is_source_mapped_and_secret_safe() -> None:
    """Diagnose missing/malformed LLM refs while accepting unresolved SecretRefs."""
    catalog = build_studio_component_catalog()
    valid = _planner_document()
    success = compile_studio_flow_document(
        valid,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert success.is_success, success.to_safe_dict()

    missing = deepcopy(valid)
    missing["semantic"]["nodes"][1]["component"]["candidates"][0][
        "dependencies"
    ] = {}
    missing_result = compile_studio_flow_document(
        missing,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    issue = next(
        item
        for item in missing_result.diagnostics
        if item.code == "graph.studio.component_dependency_required"
    )
    assert issue.path[-1] == "llm"
    assert issue.node_id == "planner"
    assert "canvas-planner" in str(issue.source_id)

    malformed = deepcopy(valid)
    malformed["semantic"]["nodes"][1]["component"]["candidates"][0][
        "dependencies"
    ]["llm"]["params"]["api_key"] = {"secret_ref": ""}
    malformed_result = compile_studio_flow_document(
        malformed,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert malformed_result.graph is None
    assert any(
        item.code == "graph.studio.component_dependency_config_invalid"
        and item.path[-1] == "secret_ref"
        for item in malformed_result.diagnostics
    )


def test_modular_template_compiles_as_explicit_bounded_mobile_loop() -> None:
    """Lower the capability-only template to a bounded internal graph."""
    catalog = build_studio_component_catalog()
    assert [item.template_id for item in list_flow_templates()] == [
        "modular_baseline"
    ]
    document = get_flow_template_document("modular_baseline")
    document_before = deepcopy(document)
    result = compile_studio_flow_document(
        document,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert result.is_success, result.to_safe_dict()
    assert result.graph is not None
    candidates = [
        candidate
        for node in document["capabilities"]
        for candidate in node["implementation"]["candidates"]
        if candidate["name"] == "universal_reasoning"
    ]
    assert len(candidates) == 1
    assert all(
        candidate["dependencies"]["llm"]["params"]["api_key"]
        == {"secret_ref": "api_key"}
        and candidate["dependencies"]["llm"]["params"]["base_url"]
        == {"secret_ref": "base_url"}
        for candidate in candidates
    )
    nodes = {node.id: node for node in result.graph.nodes}
    assert (
        nodes["studio_generated.perception.observe"].contract.id
        == "zhixing.service.device_observe"
    )
    assert nodes["action_executor"].contract.id == "zhixing.service.action_executor"
    assert nodes["studio_generated.action_executor.terminal"].kind is NodeKind.CONDITION
    assert nodes["output"].kind is NodeKind.OUTPUT
    feedback = next(
        edge for edge in result.graph.edges if edge.kind is EdgeKind.FEEDBACK
    )
    assert feedback.source.node == "action_executor"
    assert feedback.target.node == "memory"
    assert feedback.feedback is not None
    assert feedback.feedback.predicate.field == "terminal_status"
    assert feedback.feedback.predicate.operator.value == "falsy"
    assert feedback.feedback.max_iterations == 10
    assert any(
        edge.kind is EdgeKind.CONTROL
        and edge.source.node == "studio_generated.action_executor.terminal"
        and edge.source.port == "true"
        and edge.target.node == "output"
        and edge.target.port == "control"
        for edge in result.graph.edges
    )
    assert document == document_before
    render_modes = {
        canvas_id: presentation["renderMode"]
        for canvas_id, presentation in document["presentation"]["nodes"].items()
    }
    assert render_modes == {
        "tpl_input": "boundary",
        "tpl_memory": "card",
        "tpl_perception": "card",
        "tpl_reasoning": "card",
        "tpl_action_executor": "card",
        "tpl_output": "boundary",
    }

    moved = deepcopy(document)
    moved["presentation"]["nodes"]["tpl_perception"]["x"] += 173
    moved_result = compile_studio_flow_document(
        moved,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert moved_result.is_success and moved_result.graph is not None
    assert moved_result.graph.canonical_hash(
        contract_catalog=catalog.node_contract_catalog()
    ) == result.graph.canonical_hash(
        contract_catalog=catalog.node_contract_catalog()
    )

    display_changed = deepcopy(document)
    display_changed["presentation"]["nodes"]["tpl_perception"]["renderMode"] = "inline"
    display_changed_result = compile_studio_flow_document(
        display_changed,
        component_catalog=catalog,
        contract_catalog=catalog.node_contract_catalog(),
    )
    assert display_changed_result.is_success
    assert display_changed_result.graph is not None
    assert display_changed_result.graph.canonical_hash(
        contract_catalog=catalog.node_contract_catalog()
    ) == result.graph.canonical_hash(
        contract_catalog=catalog.node_contract_catalog()
    )


def test_studio_render_mode_is_strict_optional_and_round_trips() -> None:
    """Keep one-canvas renderer intent strict and presentation-only."""
    document = _planner_document()
    document["presentation"]["nodes"]["canvas-planner"]["renderMode"] = "inline"

    parsed = StudioFlowDocument.model_validate(document)

    assert parsed.presentation.nodes["canvas-planner"].render_mode == "inline"
    assert (
        parsed.to_json_dict()["presentation"]["nodes"]["canvas-planner"]["renderMode"]
        == "inline"
    )
    without_mode = StudioFlowDocument.model_validate(_planner_document())
    assert without_mode.presentation.nodes["canvas-planner"].render_mode is None

    invalid = deepcopy(document)
    invalid["presentation"]["nodes"]["canvas-planner"]["renderMode"] = "compact"
    try:
        StudioFlowDocument.model_validate(invalid)
    except ValueError as error:
        assert "presentation.nodes.canvas-planner.renderMode" in str(error)
    else:
        raise AssertionError("invalid renderMode must be rejected")


def test_catalog_reports_external_provider_failure_and_missing_dependency() -> None:
    """Merge explicit external metadata and isolate bounded provider failures."""
    external = ComponentCatalog(
        (("fixture-provider", ComponentBundle((_spec(),))),)
    )
    failure = PluginLoadFailure(
        provider_id="broken-provider",
        stage="load",
        code="plugin.provider_load_failed",
        error_type="ImportError",
        message="Provider could not be loaded.",
    )
    environment = DiscoveredComponentEnvironment(
        catalog=external,
        report=DiscoveryReport(
            (),
            ("fixture-provider", "broken-provider"),
            (),
            ("fixture-provider",),
            (failure,),
        ),
    )
    catalog = build_studio_component_catalog(
        external_environment=environment
    )
    assert any(
        item.identifier == "example.external:verifier@1.0.0"
        for item in catalog.components
    )
    assert catalog.provider_report.failures[0]["providerId"] == "broken-provider"
    assert any(
        item.code == "plugin.provider_load_failed"
        for item in catalog.diagnostics
    )

    unavailable = build_studio_component_catalog(
        built_in_catalog=BuiltInComponentCatalog(
            (
                BuiltInComponentSpec(
                    "llm",
                    "openai_llm",
                    "zhixing.plugins.llm.openai_llm",
                    extra="openai",
                    required_modules=("fixture_dependency_that_does_not_exist",),
                ),
            )
        )
    )
    descriptor = unavailable.components[0]
    assert descriptor.availability.available is False
    assert descriptor.availability.error_type == "optional_dependency_missing"


def test_schema1_migration_is_pure_and_rejects_wildcard_edges() -> None:
    """Preserve caller input and diagnose semantics that cannot be inferred."""
    legacy = {
        "schemaVersion": 1,
        "contractVersion": "1.0",
        "flowId": "legacy-doc",
        "flowName": "Legacy",
        "nodes": [],
        "edges": [],
    }
    before = deepcopy(legacy)
    migrated = migrate_studio_flow_document(legacy, agent_id="agent-legacy")
    assert migrated.is_success, migrated.to_safe_dict()
    assert legacy == before
    assert migrated.document is not None
    assert migrated.document.schema_version == 2

    unsafe = deepcopy(legacy)
    unsafe["nodes"] = [
        {
            "nodeId": "input-node",
            "logicalId": "input",
            "nodeType": "input",
            "data": {"ports": [{"portId": "out", "portRole": "out_task"}]},
        },
        {
            "nodeId": "output-node",
            "logicalId": "output",
            "nodeType": "output",
            "data": {"ports": [{"portId": "in", "portRole": "in_result"}]},
        },
    ]
    unsafe["edges"] = [
        {
            "edgeId": "edge-1",
            "sourceNodeId": "input-node",
            "sourcePortId": "out",
            "targetNodeId": "output-node",
            "targetPortId": "in",
            "dataType": "verifiedPlan",
        }
    ]
    result = migrate_studio_flow_document(unsafe, agent_id="agent-legacy")
    assert result.document is None
    assert {
        item.code for item in result.diagnostics
    } == {"studio.migration.edge_semantics_unsafe"}


def test_schema2_round_trip_uses_stable_camel_case_identities() -> None:
    """Parse and serialize schema 2 without changing authoring identities."""
    parsed = StudioFlowDocument.model_validate(_planner_document())
    serialized = parsed.to_json_dict()
    assert serialized["documentId"] == "document-1"
    assert serialized["semantic"]["nodes"][1]["canvasId"] == "canvas-planner"
    assert serialized["semantic"]["nodes"][1]["logicalId"] == "planner"
    assert serialized["semantic"]["edges"][0]["canvasId"] == "edge-task"
