"""Build and execute the example external component through public SDK APIs."""

from __future__ import annotations

import json
from pathlib import Path

from zhixing import ExecutableAgent, compile_agent, load_agent
from zhixing.catalog import discover_components
from zhixing.components import RuntimeContext
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    NodeContractRef,
    NodeKind,
    NodeLifecycle,
    PortAddress,
)
from zhixing.runtime import (
    GraphExecutionKernel,
    bind_execution_plan,
)


PROVIDER_ID = "zhixing-example"
COMPONENT_NAMESPACE = "example.external"
COMPONENT_NAME = "run_labeler"
COMPONENT_VERSION = "1.0.0"
CONTRACT = NodeContractRef(id="example.external.run_labeler", version="1.0")


def build_graph() -> AgentGraph:
    """Build the SDK graph equivalent to ``agents/run-labeler.yaml``.

    Args:
        None.

    Raises:
        ValueError: Public AgentGraph validation rejects the definition.

    Returns:
        AgentGraph: Input → external component → output graph.
    """
    return AgentGraph(
        contract_version="1.1",
        profile="mobile_agent",
        nodes=(
            GraphNode(
                id="input",
                kind=NodeKind.INPUT,
                lifecycle=NodeLifecycle.ON_RUN_START,
            ),
            GraphNode(
                id="label",
                kind=NodeKind.COMPONENT,
                lifecycle=NodeLifecycle.PER_STEP,
                contract=CONTRACT,
                component=ComponentBinding(
                    candidates=(
                        GraphComponentRef(
                            namespace=COMPONENT_NAMESPACE,
                            name=COMPONENT_NAME,
                            version=COMPONENT_VERSION,
                            params={"prefix": "demo"},
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
                target=PortAddress(node="label", port="value"),
                kind=EdgeKind.DATA,
            ),
            GraphEdge(
                source=PortAddress(node="label", port="result"),
                target=PortAddress(node="output", port="result"),
                kind=EdgeKind.DATA,
            ),
        ),
        policies=GraphPolicies(
            max_steps=3,
            max_feedback_iterations=1,
        ),
    )


def execute_examples(
    yaml_path: Path | None = None,
    *,
    value: str = "hello",
) -> dict[str, object]:
    """Compile equivalent SDK/YAML graphs and execute the discovered component.

    Args:
        yaml_path (Path | None): Optional graph YAML path.
        value (str): Text delivered to the example component.

    Raises:
        AssertionError: YAML and SDK graphs do not share one canonical identity.
        GraphRuntimeError: Binding or Kernel execution fails.

    Returns:
        dict[str, object]: Safe identity, result, and node-event summary.
    """
    selected_yaml = yaml_path or (
        Path(__file__).resolve().parent / "agents" / "run-labeler.yaml"
    )
    environment = discover_components(allowlist=(PROVIDER_ID,))
    sdk_agent = compile_agent(
        build_graph(),
        component_environment=environment,
    )
    yaml_agent = load_agent(
        selected_yaml,
        plugin_allowlist=(PROVIDER_ID,),
    )
    assert sdk_agent.canonical_hash == yaml_agent.canonical_hash
    sdk_execution = _execute_agent(sdk_agent, value=value)
    yaml_execution = _execute_agent(yaml_agent, value=value)
    assert sdk_execution == yaml_execution
    return {
        "canonical_hash": sdk_agent.canonical_hash,
        "status": sdk_execution["status"],
        "result": sdk_execution["result"],
        "events": sdk_execution["events"],
        "executions": {
            "sdk": sdk_execution,
            "yaml": yaml_execution,
        },
    }


def _execute_agent(
    agent: ExecutableAgent,
    *,
    value: str,
) -> dict[str, object]:
    """Bind and execute one compiled external-component AgentGraph.

    Args:
        agent (ExecutableAgent): SDK- or YAML-compiled executable graph.
        value (str): Text delivered through the graph input port.

    Raises:
        GraphRuntimeError: Binding or Kernel execution fails.

    Returns:
        dict[str, object]: Comparable status, output, and label-node events.
    """
    events = []
    runtime = RuntimeContext(
        run_id="external-plugin-example",
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
    return {
        "status": result.status.value,
        "result": result.outputs["result"],
        "events": [
            event.kind for event in events if event.node_id == "label"
        ],
    }


def main() -> int:
    """Run the installed-plugin example and print its safe result.

    Args:
        None.

    Raises:
        None.

    Returns:
        int: Zero when the external node completes successfully.
    """
    payload = execute_examples()
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if payload["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
