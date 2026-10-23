"""Canonical parity tests for contract 1.1 Studio authoring."""

from __future__ import annotations

import pytest

from tests.runtime.test_external_catalog_binding import _graph, _spec
from zhixing.catalog import (
    CatalogComponentResolver,
    ComponentCatalog,
    DiscoveredComponentEnvironment,
    DiscoveryReport,
)
from zhixing.components import ComponentBundle, RuntimeContext
from zhixing.graph import (
    compile_graph_yaml_data,
    compile_studio_flow_document,
    planner_execute_template,
    react_template,
)
from zhixing.studio import build_studio_component_catalog
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan

from .helpers import graph_with_exact_component_versions, studio_document_from_graph


@pytest.mark.parametrize(
    "factory",
    [react_template, planner_execute_template],
)
def test_python_yaml_and_studio_schema2_have_canonical_parity(factory) -> None:
    """Compile representative control/composition graphs to one identity."""
    direct = graph_with_exact_component_versions(factory())
    yaml_mapping = direct.model_dump(mode="json", exclude_none=True)
    yaml_mapping["kind"] = "agent_graph"
    yaml_result = compile_graph_yaml_data(yaml_mapping)
    studio_result = compile_studio_flow_document(
        studio_document_from_graph(direct)
    )
    assert yaml_result.is_success, yaml_result.to_safe_dict()
    assert studio_result.is_success, studio_result.to_safe_dict()
    assert yaml_result.graph is not None
    assert studio_result.graph is not None
    assert direct.canonical_mapping() == yaml_result.graph.canonical_mapping()
    assert direct.canonical_mapping() == studio_result.graph.canonical_mapping()
    assert {
        direct.canonical_hash(),
        yaml_result.graph.canonical_hash(),
        studio_result.graph.canonical_hash(),
    } == {direct.canonical_hash()}


def test_nested_studio_source_map_keeps_canvas_path() -> None:
    """Retain nested Loop/Subgraph canvas paths in source mappings."""
    direct = graph_with_exact_component_versions(planner_execute_template())
    result = compile_studio_flow_document(studio_document_from_graph(direct))
    assert result.is_success, result.to_safe_dict()
    nested = [item for item in result.source_map if item.canvas_path]
    assert nested
    assert all(item.document_id for item in nested)
    assert any(len(item.logical_node_path) > 1 for item in nested)


def test_unknown_contract_does_not_produce_runnable_graph() -> None:
    """Reject an exact component contract absent from explicit catalogs."""
    direct = graph_with_exact_component_versions(react_template())
    document = studio_document_from_graph(direct)
    component = next(
        item
        for item in document["semantic"]["nodes"]
        if item["kind"] == "component"
    )
    component["contract"] = {
        "id": "research.missing.contract",
        "version": "1.0",
    }
    result = compile_studio_flow_document(document)
    assert result.graph is None
    assert any(
        item.code == "graph.contract.unknown"
        for item in result.diagnostics
    )


def test_external_component_python_and_studio_have_canonical_parity() -> None:
    """Compile one explicit external component without Studio-specific logic."""
    direct = _graph()
    external = ComponentCatalog(
        (("fixture-provider", ComponentBundle((_spec(),))),)
    )
    environment = DiscoveredComponentEnvironment(
        catalog=external,
        report=DiscoveryReport(
            (),
            ("fixture-provider",),
            (),
            ("fixture-provider",),
            (),
        ),
    )
    studio_catalog = build_studio_component_catalog(
        external_environment=environment
    )
    result = compile_studio_flow_document(
        studio_document_from_graph(direct),
        component_catalog=studio_catalog,
        contract_catalog=studio_catalog.node_contract_catalog(),
    )
    assert result.is_success, result.to_safe_dict()
    assert result.graph is not None
    contract_catalog = studio_catalog.node_contract_catalog()
    assert result.graph.canonical_mapping(
        contract_catalog=contract_catalog
    ) == direct.canonical_mapping(contract_catalog=contract_catalog)


def test_studio_compiled_graph_runs_through_generic_fake_runtime() -> None:
    """Execute a Studio-authored graph without a Studio-specific Kernel branch."""
    direct = _graph()
    external = ComponentCatalog(
        (("fixture-provider", ComponentBundle((_spec(),))),)
    )
    environment = DiscoveredComponentEnvironment(
        catalog=external,
        report=DiscoveryReport(
            (),
            ("fixture-provider",),
            (),
            ("fixture-provider",),
            (),
        ),
    )
    studio_catalog = build_studio_component_catalog(
        external_environment=environment
    )
    compiled = compile_studio_flow_document(
        studio_document_from_graph(direct),
        component_catalog=studio_catalog,
        contract_catalog=studio_catalog.node_contract_catalog(),
    )
    assert compiled.is_success, compiled.to_safe_dict()
    assert compiled.graph is not None
    runtime = RuntimeContext(run_id="studio-fake-runtime")
    result = GraphExecutionKernel().run(
        bind_execution_plan(
            compiled.graph,
            CatalogComponentResolver(
                external,
                dependency_provider={"suffix_service": "-injected"},
            ),
            contract_catalog=external.contract_catalog,
        ),
        {"value": "task"},
        runtime=runtime,
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {
        "result": "pre-task-injected:studio-fake-runtime"
    }
