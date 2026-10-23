"""SDK/YAML integration tests for explicit external discovery environments."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from tests.runtime.test_external_catalog_binding import _graph, _spec
from zhixing.catalog import (
    ComponentCatalog,
    DiscoveredComponentEnvironment,
    DiscoveryReport,
    PluginLoadFailure,
    PluginOrigin,
    empty_component_environment,
)
from zhixing.components import ComponentBundle, RuntimeContext
from zhixing.runtime import (
    GraphBindingError,
    GraphExecutionKernel,
    KernelStatus,
    bind_execution_plan,
)
from zhixing.sdk import ExecutableAgent, compile_agent, load_agent


def _environment(*, source_kind: str = "index") -> DiscoveredComponentEnvironment:
    """Create one explicit environment with simulated installed provenance.

    Args:
        source_kind (str): Safe provenance category.

    Returns:
        DiscoveredComponentEnvironment: External fixture environment.
    """
    origin = PluginOrigin(
        distribution="fixture-plugin",
        version="1.0.0",
        source_kind=source_kind,
        vcs="git" if source_kind == "vcs" else "",
        commit_id="abcdef" if source_kind == "vcs" else "",
    )
    catalog = ComponentCatalog(
        (("fixture-provider", ComponentBundle((_spec(),))),),
        origins={"fixture-provider": origin},
    )
    return DiscoveredComponentEnvironment(
        catalog=catalog,
        report=DiscoveryReport((), ("fixture-provider",), (), ("fixture-provider",), ()),
    )


def _write_yaml(path: Path) -> None:
    """Serialize the SDK graph through the public graph-native YAML envelope.

    Args:
        path (Path): Destination YAML file.

    Returns:
        None: Writes the semantic graph definition.
    """
    payload = _graph().model_dump(mode="json", exclude_none=True)
    payload["kind"] = "agent_graph"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _execute_external_agent(
    agent: ExecutableAgent,
    *,
    value: str,
) -> tuple[KernelStatus, str, tuple[str, ...]]:
    """Bind and execute one SDK- or YAML-compiled external graph.

    Args:
        agent (ExecutableAgent): Compiled graph with an external resolver factory.
        value (str): Input value supplied to the graph.

    Raises:
        GraphBindingError: External component binding fails.

    Returns:
        tuple[KernelStatus, str, tuple[str, ...]]: Status, output, and component
            lifecycle events.
    """
    events = []
    runtime = RuntimeContext(
        run_id="sdk-yaml-equivalence",
        event_sink=events.append,
    )
    plan = bind_execution_plan(
        agent.graph,
        agent.resolver_factory(),
        contract_catalog=agent.contract_catalog,
    )
    result = GraphExecutionKernel().run(
        plan,
        {"value": value},
        runtime=runtime,
    )
    return (
        result.status,
        result.outputs["result"],
        tuple(
            event.kind
            for event in events
            if event.node_id == "external"
        ),
    )


def test_yaml_and_python_sdk_share_external_component_canonical_hash(tmp_path) -> None:
    """Compile the same external graph from SDK and YAML to one identity."""
    environment = _environment()
    path = tmp_path / "external-agent.yaml"
    _write_yaml(path)
    sdk_agent = compile_agent(_graph(), component_environment=environment)
    yaml_agent = load_agent(path, component_environment=environment)
    assert sdk_agent.graph.canonical_mapping(
        contract_catalog=environment.contract_catalog
    ) == yaml_agent.graph.canonical_mapping(
        contract_catalog=environment.contract_catalog
    )
    assert sdk_agent.canonical_hash == yaml_agent.canonical_hash


def test_external_yaml_and_sdk_execute_equivalently_through_graph_kernel(
    tmp_path: Path,
) -> None:
    """Run equivalent SDK and YAML graphs without Android or model services.

    Args:
        tmp_path (Path): Temporary YAML output directory.

    Raises:
        AssertionError: Compilation, output, or RunEvent parity is broken.

    Returns:
        None.
    """
    environment = _environment()
    path = tmp_path / "external-agent.yaml"
    _write_yaml(path)
    sdk_agent = compile_agent(
        _graph(),
        component_environment=environment,
        dependencies={"suffix_service": "-fake"},
    )
    yaml_agent = load_agent(
        path,
        component_environment=environment,
        dependencies={"suffix_service": "-fake"},
    )
    sdk_result = _execute_external_agent(sdk_agent, value="shared-task")
    yaml_result = _execute_external_agent(yaml_agent, value="shared-task")
    assert sdk_result == yaml_result
    assert sdk_result[0] is KernelStatus.SUCCESS
    assert sdk_result[1] == "pre-shared-task-fake:sdk-yaml-equivalence"
    assert sdk_result[2] == ("start", "complete")


def test_distribution_provenance_does_not_change_agent_identity() -> None:
    """Keep wheel/editable/Git origin metadata outside canonical semantics."""
    index_agent = compile_agent(_graph(), component_environment=_environment())
    local_agent = compile_agent(
        _graph(),
        component_environment=_environment(source_kind="local"),
    )
    git_agent = compile_agent(
        _graph(),
        component_environment=_environment(source_kind="vcs"),
    )
    assert index_agent.canonical_hash == local_agent.canonical_hash == git_agent.canonical_hash


def test_compile_agent_does_not_enumerate_installed_plugins(monkeypatch) -> None:
    """Keep the low-level SDK compiler pure unless an environment is supplied."""

    def forbidden(*args, **kwargs):
        """Fail if low-level compilation touches installed metadata."""
        del args, kwargs
        raise AssertionError("unexpected Entry Point enumeration")

    monkeypatch.setattr(
        "zhixing.catalog.external.importlib_metadata.entry_points",
        forbidden,
    )
    with pytest.raises(GraphBindingError) as captured:
        compile_agent(_graph())
    assert captured.value.info.code == "sdk.graph_invalid"


def test_load_agent_exposes_discovery_controls(monkeypatch, tmp_path) -> None:
    """Use explicit high-level discovery and forward allow/deny policy."""
    path = tmp_path / "external-agent.yaml"
    _write_yaml(path)
    environment = _environment()
    calls = []

    def fake_discover(*, allowlist, denylist):
        """Capture high-level discovery policy.

        Args:
            allowlist (tuple[str, ...] | None): Selected provider IDs.
            denylist (tuple[str, ...]): Disabled provider IDs.

        Returns:
            DiscoveredComponentEnvironment: Fixture environment.
        """
        calls.append((allowlist, denylist))
        return environment

    monkeypatch.setattr("zhixing.sdk.discover_components", fake_discover)
    agent = load_agent(
        path,
        plugin_allowlist=("fixture-provider",),
        plugin_denylist=("disabled",),
    )
    assert calls == [(("fixture-provider",), ("disabled",))]
    assert agent.discovery_report is environment.report

    with pytest.raises(GraphBindingError) as disabled:
        load_agent(path, discover_external=False)
    assert disabled.value.info.code == "sdk.compilation_failed"


def test_executable_agent_factory_creates_isolated_component_instances() -> None:
    """Construct new external component instances for every binding/run."""
    environment = _environment()
    agent = compile_agent(
        _graph(),
        component_environment=environment,
        dependencies={"suffix_service": "-runtime"},
    )
    first = bind_execution_plan(
        agent.graph,
        agent.resolver_factory(),
        contract_catalog=agent.contract_catalog,
    )
    second = bind_execution_plan(
        agent.graph,
        agent.resolver_factory(),
        contract_catalog=agent.contract_catalog,
    )
    assert first.nodes["external"].candidates[0].instance is not second.nodes["external"].candidates[0].instance


def test_failed_provider_is_distinguished_when_referenced_component_is_missing() -> None:
    """Block execution preflight with provider failure evidence, not plain unknown."""
    empty = empty_component_environment()
    environment = DiscoveredComponentEnvironment(
        catalog=empty.catalog,
        report=DiscoveryReport(
            (),
            ("broken-provider",),
            (),
            (),
            (
                PluginLoadFailure(
                    provider_id="broken-provider",
                    stage="load",
                    code="plugin.provider_load_failed",
                    error_type="ImportError",
                    message="Provider loading failed (ImportError).",
                ),
            ),
        ),
    )
    with pytest.raises(GraphBindingError) as captured:
        compile_agent(_graph(), component_environment=environment)
    assert captured.value.info.code == "sdk.component_discovery_failed"
    assert captured.value.info.details["provider_failures"][0]["provider_id"] == "broken-provider"
