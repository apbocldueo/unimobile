"""Runtime contract tests for external catalog binding."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

from zhixing.catalog import (
    CatalogComponentResolver,
    ComponentCatalog,
    empty_component_environment,
)
from zhixing.components import (
    BaseComponent,
    ComponentBundle,
    ComponentCategory,
    ComponentSpec,
    RuntimeContext,
)
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    ContractPort,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    InvocationAdapterKind,
    NodeContract,
    NodeContractRef,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    PortDirection,
)
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan


class _TextConfig(BaseModel):
    """Strict configuration for the external text fixture."""

    model_config = ConfigDict(extra="forbid")
    prefix: str = ""


class _ExternalText(BaseComponent[str, str]):
    """Custom typed component with one explicitly injected dependency."""

    component_category = ComponentCategory.EXTENSION
    input_type = str
    output_type = str

    def __init__(self, prefix: str, suffix_service: str) -> None:
        """Store validated configuration and injected service.

        Args:
            prefix (str): Declarative text prefix.
            suffix_service (str): Explicit run-scoped dependency.
        """
        self.prefix = prefix
        self.suffix_service = suffix_service

    def invoke(self, input: str, runtime: RuntimeContext) -> str:
        """Decorate the input while proving RuntimeContext propagation.

        Args:
            input (str): Graph input text.
            runtime (RuntimeContext): Shared runtime context.

        Returns:
            str: Decorated text containing the run ID.
        """
        return f"{self.prefix}{input}{self.suffix_service}:{runtime.run_id}"


class _WrongExternalText(_ExternalText):
    """Fixture that deliberately violates its declared output type."""

    def invoke(self, input: str, runtime: RuntimeContext) -> str:
        """Return an invalid runtime value for output validation.

        Args:
            input (str): Graph input text.
            runtime (RuntimeContext): Shared runtime context.

        Returns:
            str: Annotation is formal, while the runtime value is intentionally wrong.
        """
        del input, runtime
        return 42  # type: ignore[return-value]


def _contract() -> NodeContract:
    """Create the custom typed tool contract.

    Returns:
        NodeContract: Exact text-to-text contract.
    """
    return NodeContract(
        ref=NodeContractRef(id="fixture.external.text", version="1.0"),
        ports=(
            ContractPort(
                id="value",
                direction=PortDirection.INPUT,
                data_types=("text",),
                required=True,
            ),
            ContractPort(
                id="result",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )


def _spec(implementation: type[_ExternalText] = _ExternalText) -> ComponentSpec:
    """Create a formal external component specification.

    Args:
        implementation (type[_ExternalText]): Component implementation class.

    Returns:
        ComponentSpec: Valid formal definition.
    """
    return ComponentSpec(
        namespace="fixture.external",
        name="text_tool",
        version="1.0.0",
        contract=_contract(),
        implementation=implementation,
        category=ComponentCategory.EXTENSION,
        config_model=_TextConfig,
        input_type=str,
        output_type=str,
    )


def _graph(*, prefix: str = "pre-") -> AgentGraph:
    """Build one input/component/output AgentGraph using the external identity.

    Args:
        prefix (str): Declarative component parameter.

    Returns:
        AgentGraph: Valid custom-contract graph.
    """
    return AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            GraphNode(
                id="external",
                kind=NodeKind.COMPONENT,
                lifecycle=NodeLifecycle.PER_STEP,
                contract=_contract().ref,
                component=ComponentBinding(
                    candidates=(
                        GraphComponentRef(
                            namespace="fixture.external",
                            name="text_tool",
                            version="1.0.0",
                            params={"prefix": prefix},
                            dependencies={"suffix_service": "declarative-default"},
                        ),
                    )
                ),
            ),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            ),
        ),
        edges=(
            GraphEdge(
                source=PortAddress(node="input", port="value"),
                target=PortAddress(node="external", port="value"),
                kind=EdgeKind.DATA,
            ),
            GraphEdge(
                source=PortAddress(node="external", port="result"),
                target=PortAddress(node="output", port="result"),
                kind=EdgeKind.DATA,
            ),
        ),
    )


def _catalog(implementation: type[_ExternalText] = _ExternalText) -> ComponentCatalog:
    """Create the fixture catalog.

    Args:
        implementation (type[_ExternalText]): Component implementation class.

    Returns:
        ComponentCatalog: Immutable external catalog.
    """
    return ComponentCatalog(
        (("fixture-provider", ComponentBundle((_spec(implementation),))),)
    )


def test_catalog_resolver_constructs_fresh_component_with_explicit_dependency() -> None:
    """Bind and execute a custom typed tool through the generic Kernel boundary."""
    catalog = _catalog()
    resolver = CatalogComponentResolver(
        catalog,
        dependency_provider={"suffix_service": "-injected"},
    )
    events = []
    runtime = RuntimeContext(run_id="external-run", event_sink=events.append)
    result = GraphExecutionKernel().run(
        bind_execution_plan(
            _graph(),
            resolver,
            contract_catalog=catalog.contract_catalog,
        ),
        {"value": "task"},
        runtime=runtime,
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": "pre-task-injected:external-run"}
    component_events = [event.kind for event in events if event.node_id == "external"]
    assert component_events == ["start", "complete"]


def test_external_parameter_preflight_is_structured() -> None:
    """Reject unknown component parameters before the scheduler starts."""
    catalog = _catalog()
    with pytest.raises(Exception) as captured:
        bind_execution_plan(
            _graph(prefix=42),  # type: ignore[arg-type]
            CatalogComponentResolver(catalog),
            contract_catalog=catalog.contract_catalog,
        )
    assert captured.value.info.code == "component.config_invalid"
    assert captured.value.info.phase == "component_preflight"


def test_external_runtime_output_type_is_enforced() -> None:
    """Reject a loaded external component that returns the wrong runtime type."""
    catalog = _catalog(_WrongExternalText)
    result = GraphExecutionKernel().run(
        bind_execution_plan(
            _graph(),
            CatalogComponentResolver(
                catalog,
                dependency_provider={"suffix_service": "-injected"},
            ),
            contract_catalog=catalog.contract_catalog,
        ),
        {"value": "task"},
    )
    assert result.status is KernelStatus.FAILURE
    assert result.error_code == "runtime.output_type"


def test_empty_environment_creation_performs_no_discovery() -> None:
    """Provide a low-level explicit empty environment for pure compilation."""
    environment = empty_component_environment()
    assert environment.catalog.providers() == ()
    assert environment.report.candidates == ()
