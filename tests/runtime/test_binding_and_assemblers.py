from __future__ import annotations

import pytest

from zhixing.components import (
    Action,
    ActionResult,
    ActionType,
    DeviceObservation,
    ExecutionStatus,
    MemoryFragment,
    PerceptionResult,
    PlanResult,
    ReasoningInput,
    RuntimeContext,
    TaskInput,
    VerifierResult,
)
from zhixing.core.agent.protocol import FragmentType
from zhixing.graph import (
    AgentGraph,
    BindingPolicy,
    ComponentBinding,
    GraphComponentRef,
    GraphRole,
    SecretRef,
)
from zhixing.runtime import (
    GraphBindingError,
    MappingComponentResolver,
    RegistryComponentResolver,
    StepFrame,
    bind_agent_graph,
)
from zhixing.runtime.assemblers import assemble_role_input, invoke_role

from tests.graph.helpers import make_golden_graph


class InvokeValue:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def invoke(self, input, runtime):
        self.calls.append((input, runtime))
        if isinstance(self.value, BaseException):
            raise self.value
        return self.value


def test_invalid_graph_is_rejected_before_resolver_calls():
    graph = make_golden_graph()
    invalid = graph.model_copy(
        update={"nodes": tuple(node for node in graph.nodes if node.id != "reasoning")}
    )
    resolver = MappingComponentResolver({})
    with pytest.raises(GraphBindingError) as caught:
        bind_agent_graph(invalid, resolver)
    assert caught.value.info.code == "runtime.graph_invalid"
    assert resolver.calls == []


def test_binding_preserves_node_identity_candidate_order_and_protocol_adapter():
    graph = make_golden_graph()
    perception_node = next(node for node in graph.nodes if node.id == "perception")
    fallback = perception_node.model_copy(
        update={
            "component": ComponentBinding(
                policy=BindingPolicy.FALLBACK,
                candidates=(
                    GraphComponentRef(namespace="agent.perception", name="first"),
                    GraphComponentRef(namespace="agent.perception", name="second"),
                ),
            )
        }
    )
    graph = graph.model_copy(
        update={
            "nodes": tuple(fallback if node.id == "perception" else node for node in graph.nodes)
        }
    )
    components = {
        "test_planner": InvokeValue(PlanResult("plan")),
        "first": InvokeValue(RuntimeError("offline")),
        "second": InvokeValue(PerceptionResult("fake", "shot.png")),
        "test_reasoning": InvokeValue(Action(ActionType.DONE)),
        "test_action_executor": InvokeValue(
            ActionResult(Action(ActionType.DONE), ExecutionStatus.TERMINAL)
        ),
        "test_verifier": InvokeValue(VerifierResult(True)),
    }
    bound = bind_agent_graph(graph, MappingComponentResolver(components))
    assert bound.graph is graph
    assert bound.components["perception"].node_id == "perception"
    assert [item.reference.name for item in bound.components["perception"].candidates] == [
        "first",
        "second",
    ]


def test_registry_resolver_resolves_secrets_without_mutating_graph_reference():
    captured = {}

    class Plugin:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, input, runtime):
            return input

    class Registry:
        @classmethod
        def get_plugin(cls, namespace, name):
            assert (namespace, name) == ("agent.reasoning", "secret_reasoner")
            return Plugin

    reference = GraphComponentRef(
        namespace="agent.reasoning",
        name="secret_reasoner",
        params={"api_key": SecretRef(secret_ref="model_key"), "temperature": 0.1},
    )
    resolver = RegistryComponentResolver(
        registry=Registry,
        secret_provider={"model_key": "private-value"},
    )
    resolver.resolve(reference, GraphRole.REASONING)
    assert captured["api_key"] == "private-value"
    assert "private-value" not in reference.model_dump_json()


def test_reasoning_assembler_supports_empty_plan_memory_and_feedback():
    task = TaskInput("open settings")
    perception = PerceptionResult("fake", "before.png")
    verification = VerifierResult(False, feedback="try another control")
    value = assemble_role_input(
        GraphRole.REASONING,
        {"task": task, "perception": perception, "verification": verification},
        StepFrame(step=1),
        RuntimeContext(step=1),
        "reasoning",
    )
    assert isinstance(value, ReasoningInput)
    assert value.plan == PlanResult("")
    assert value.memory_context == ()
    assert value.verification is verification


def test_verifier_assembler_uses_distinct_frame_observations_and_action_result():
    action = Action(ActionType.TAP, {"x": 1, "y": 2})
    result = ActionResult(action, ExecutionStatus.SUCCESS)
    before = DeviceObservation("before.png", 10, 20)
    after = DeviceObservation("after.png", 10, 20)
    value = assemble_role_input(
        GraphRole.VERIFIER,
        {"task": TaskInput("task"), "action": action, "action_result": result},
        StepFrame(0, pre_observation=before, post_observation=after, action_result=result),
        RuntimeContext(),
        "verifier",
    )
    assert value.screenshot_before == "before.png"
    assert value.screenshot_after == "after.png"
    assert value.action_result is result
    assert value.metadata["before"] is before
    assert value.metadata["after"] is after


def test_memory_assembler_maps_all_supported_write_types():
    class Memory:
        def __init__(self):
            self.fragments = []

        def invoke(self, input, runtime):
            from zhixing.components import MemoryOperation, MemoryResult

            if input.operation is MemoryOperation.APPEND:
                self.fragments.append(input.fragment)
            return MemoryResult(input.operation, fragments=tuple(self.fragments))

    graph = make_golden_graph()
    memory_node = next(
        node for node in AgentGraph.model_validate(
            {
                **graph.model_dump(mode="python"),
                "nodes": [
                    *graph.model_dump(mode="python")["nodes"],
                    {
                        "id": "memory",
                        "kind": "component",
                        "role": "memory",
                        "lifecycle": "stateful",
                        "component": {
                            "policy": "single",
                            "candidates": [{"namespace": "agent.memory", "name": "memory"}],
                        },
                    },
                ],
            }
        ).nodes
        if node.id == "memory"
    )
    from zhixing.runtime.models import BoundCandidate, BoundComponent

    component = BoundComponent(
        memory_node,
        (BoundCandidate(memory_node.component.candidates[0], Memory()),),
    )
    action = Action(ActionType.TAP)
    writes = [
        TaskInput("task"),
        PlanResult("plan"),
        action,
        ActionResult(action, ExecutionStatus.SUCCESS),
        VerifierResult(False, feedback="bad"),
    ]
    result = invoke_role(
        component,
        {"write": writes},
        StepFrame(0),
        RuntimeContext(),
    )
    assert len(result.output) == 5
    assert all(isinstance(item, MemoryFragment) for item in result.output)
    assert [item.type for item in result.output] == [
        FragmentType.TEXT,
        FragmentType.PLAN,
        FragmentType.ACTION,
        FragmentType.ACTION,
        FragmentType.ERROR,
    ]
