from __future__ import annotations

from zhixing.components import (
    BasePerception,
    ComponentCategory,
    ComponentRole,
    ComponentSpec,
    DeviceObservation,
    PerceptionResult,
    RuntimeContext,
    component,
)
from zhixing.graph import (
    AgentGraph,
    BUILTIN_NODE_CONTRACT_CATALOG,
    ComponentBinding,
    ContractPort,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphRole,
    InvocationAdapterKind,
    NodeContract,
    NodeContractCatalog,
    NodeContractRef,
    NodeKind,
    NodeLifecycle,
    PortAddress,
    PortDirection,
    contract_ref_for_role,
)
from zhixing.runtime import (
    GraphExecutionKernel,
    KernelStatus,
    bind_execution_plan,
)


def _binding(name: str) -> ComponentBinding:
    """Create one explicit formal-component binding.

    Args:
        name (str): Component candidate name.

    Raises:
        ValueError: Binding model validation fails.

    Returns:
        ComponentBinding: Single-candidate binding.
    """
    return ComponentBinding(
        candidates=(
            GraphComponentRef(namespace="tests", name=name),
        )
    )


def _edge(
    source: str,
    source_port: str,
    target: str,
    target_port: str,
) -> GraphEdge:
    """Create one data edge for the formal-component graph.

    Args:
        source (str): Source node ID.
        source_port (str): Source port ID.
        target (str): Target node ID.
        target_port (str): Target port ID.

    Raises:
        ValueError: Edge model validation fails.

    Returns:
        GraphEdge: Typed data edge.
    """
    return GraphEdge(
        source=PortAddress(node=source, port=source_port),
        target=PortAddress(node=target, port=target_port),
        kind="data",
    )


class FormalPerception(BasePerception):
    """Formal core component that records the shared RuntimeContext."""

    seen_runtime: RuntimeContext | None = None

    def invoke(
        self,
        input: DeviceObservation,
        runtime: RuntimeContext,
    ) -> PerceptionResult:
        """Convert one fake observation into a typed perception result.

        Args:
            input (DeviceObservation): Fake-device observation.
            runtime (RuntimeContext): Shared graph runtime context.

        Raises:
            None.

        Returns:
            PerceptionResult: Deterministic perception output.
        """
        type(self).seen_runtime = runtime
        return PerceptionResult(
            mode="formal",
            original_screenshot_path=input.screenshot_path,
            prompt_representation="camera preview",
        )


class WrongFormalPerception(BasePerception):
    """Formal core component with an intentionally wrong dynamic output."""

    def invoke(
        self,
        input: DeviceObservation,
        runtime: RuntimeContext,
    ) -> PerceptionResult:
        """Return an invalid value despite a correct annotation.

        Args:
            input (DeviceObservation): Fake-device observation.
            runtime (RuntimeContext): Shared graph runtime context.

        Raises:
            None.

        Returns:
            PerceptionResult: Declared type intentionally violated at runtime.
        """
        del input, runtime
        return "invalid"  # type: ignore[return-value]


def _perception_spec(
    implementation: type[BasePerception],
    name: str,
) -> ComponentSpec:
    """Build one formal Perception ComponentSpec.

    Args:
        implementation (type[BasePerception]): Formal implementation class.
        name (str): Stable component name.

    Raises:
        AssertionError: Built-in Perception contract is absent.
        ComponentDefinitionError: Basic specification fields are invalid.

    Returns:
        ComponentSpec: Strict formal component definition.
    """
    contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(
        contract_ref_for_role(GraphRole.PERCEPTION)
    )
    assert contract is not None
    return ComponentSpec(
        namespace="tests",
        name=name,
        version="1.0.0",
        contract=contract,
        implementation=implementation,
        category=ComponentCategory.CORE_AGENT,
        role=ComponentRole.PERCEPTION,
    )


def test_formal_core_and_custom_tool_run_in_one_fake_graph() -> None:
    """Run a formal core role and decorated Tool through the same kernel.

    Args:
        None.

    Raises:
        AssertionError: Binding, context, output, or event semantics regress.

    Returns:
        None.
    """
    summary_ref = NodeContractRef(id="tests.perception_summary", version="1.0")
    summary_contract = NodeContract(
        ref=summary_ref,
        ports=(
            ContractPort(
                id="input",
                direction=PortDirection.INPUT,
                data_types=("perception_result",),
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
    tool_runtimes: list[RuntimeContext] = []

    @component(
        namespace="tests",
        name="summary_tool",
        contract=summary_contract,
        input_type=PerceptionResult,
        output_type=str,
    )
    def summary_tool(
        input: PerceptionResult,
        runtime: RuntimeContext,
    ) -> str:
        """Summarize a formal perception result.

        Args:
            input (PerceptionResult): Upstream typed output.
            runtime (RuntimeContext): Shared run context.

        Raises:
            None.

        Returns:
            str: Deterministic summary.
        """
        tool_runtimes.append(runtime)
        return input.prompt_representation

    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            GraphNode(
                id="perception",
                kind=NodeKind.COMPONENT,
                role=GraphRole.PERCEPTION,
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("formal_perception"),
            ),
            GraphNode(
                id="summary",
                kind=NodeKind.COMPONENT,
                contract=summary_ref,
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("summary_tool"),
            ),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            ),
        ),
        edges=(
            _edge("input", "observation", "perception", "observation"),
            _edge("perception", "perception", "summary", "input"),
            _edge("summary", "result", "output", "result"),
        ),
    )
    runtime = RuntimeContext(run_id="formal-graph-runtime")
    plan = bind_execution_plan(
        graph,
        {
            "formal_perception": _perception_spec(
                FormalPerception,
                "formal_perception",
            ),
            "summary_tool": summary_tool,
        },
        contract_catalog=NodeContractCatalog((summary_contract,)),
    )
    result = GraphExecutionKernel().run(
        plan,
        {
            "observation": DeviceObservation(
                screenshot_path="fixture://camera.png",
                width=1080,
                height=1920,
                platform="fake",
            )
        },
        runtime=runtime,
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": "camera preview"}
    assert FormalPerception.seen_runtime is runtime
    assert tool_runtimes == [runtime]
    component_events = [
        (event.node_path, event.kind)
        for event in result.events
        if event.node_path in {"perception", "summary"}
    ]
    assert component_events == [
        ("perception", "start"),
        ("perception", "complete"),
        ("summary", "start"),
        ("summary", "complete"),
    ]


def test_formal_dynamic_output_failure_keeps_specific_error() -> None:
    """Return a stable output-type error without loose fallback.

    Args:
        None.

    Raises:
        AssertionError: Formal output failure is hidden or execution succeeds.

    Returns:
        None.
    """
    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            GraphNode(
                id="perception",
                kind=NodeKind.COMPONENT,
                role=GraphRole.PERCEPTION,
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("wrong_perception"),
            ),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            ),
        ),
        edges=(
            _edge("input", "observation", "perception", "observation"),
            _edge("perception", "perception", "output", "result"),
        ),
    )
    plan = bind_execution_plan(
        graph,
        {
            "wrong_perception": _perception_spec(
                WrongFormalPerception,
                "wrong_perception",
            )
        },
    )
    result = GraphExecutionKernel().run(
        plan,
        {
            "observation": DeviceObservation(
                screenshot_path="fixture://bad.png",
                width=10,
                height=10,
                platform="fake",
            )
        },
    )
    assert result.status is KernelStatus.FAILURE
    assert result.error_code == "runtime.output_type"
    assert all(event.node_path != "output" for event in result.events)


def test_formal_multi_output_requires_declared_mapping_shape() -> None:
    """Reject a scalar returned for a formal multi-output contract.

    Args:
        None.

    Raises:
        AssertionError: Multi-output normalization accepts an invalid scalar.

    Returns:
        None.
    """
    reference = NodeContractRef(id="tests.multi_runtime", version="1.0")
    contract = NodeContract(
        ref=reference,
        ports=(
            ContractPort(
                id="input",
                direction=PortDirection.INPUT,
                data_types=("text",),
                required=True,
            ),
            ContractPort(
                id="left",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
            ContractPort(
                id="right",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )

    @component(
        namespace="tests",
        name="multi_runtime",
        contract=contract,
        input_type=str,
        output_type=dict,
    )
    def multi_runtime(
        input: str,
        runtime: RuntimeContext,
    ) -> dict:
        """Return an intentionally invalid scalar.

        Args:
            input (str): Text fixture.
            runtime (RuntimeContext): Shared runtime.

        Raises:
            None.

        Returns:
            dict: Declared mapping intentionally violated at runtime.
        """
        del input, runtime
        return "invalid"  # type: ignore[return-value]

    graph = AgentGraph(
        contract_version="1.1",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            GraphNode(
                id="multi",
                kind=NodeKind.COMPONENT,
                contract=reference,
                lifecycle=NodeLifecycle.PER_STEP,
                component=_binding("multi_runtime"),
            ),
            GraphNode(
                id="output",
                kind=NodeKind.OUTPUT,
                lifecycle=NodeLifecycle.TERMINAL,
            ),
        ),
        edges=(
            _edge("input", "value", "multi", "input"),
            _edge("multi", "left", "output", "result"),
        ),
    )
    result = GraphExecutionKernel().run(
        bind_execution_plan(
            graph,
            {"multi_runtime": multi_runtime},
            contract_catalog=NodeContractCatalog((contract,)),
        ),
        {"value": "fixture"},
    )
    assert result.status is KernelStatus.FAILURE
    assert result.error_code == "runtime.output_mapping_required"
