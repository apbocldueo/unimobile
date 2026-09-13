from __future__ import annotations

from zhixing.components import (
    Action,
    ActionType,
    ExecutionStatus,
    MemoryOperation,
    MemoryResult,
    PerceptionResult,
    PlanResult,
    ReasoningInput,
    RunStatus,
    RuntimeContext,
    TaskInput,
    VerifierResult,
)
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    FeedbackExhaustedPolicy,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    PortAddress,
)
from zhixing.runtime import MappingComponentResolver, SimpleCancellationSignal, bind_agent_graph, run_agent_graph
from zhixing.runtime.testing import (
    FakeActionExecutor,
    FakeObservationProvider,
    ScriptedComponent,
    observation,
)

from tests.graph.helpers import make_golden_graph


def _binding(role: GraphRole, name: str) -> ComponentBinding:
    return ComponentBinding(
        candidates=(GraphComponentRef(namespace=f"agent.{role.value}", name=name),)
    )


def _component(node_id: str, role: GraphRole, lifecycle: NodeLifecycle, *, primary=False):
    return GraphNode(
        id=node_id,
        kind=NodeKind.COMPONENT,
        role=role,
        lifecycle=lifecycle,
        primary=primary,
        component=_binding(role, node_id),
    )


def _edge(source_node, source_port, target_node, target_port, kind=EdgeKind.DATA):
    return GraphEdge(
        source=PortAddress(node=source_node, port=source_port),
        target=PortAddress(node=target_node, port=target_port),
        kind=kind,
    )


def _minimal_graph(max_steps=3):
    return AgentGraph(
        nodes=(
            GraphNode(id="input", kind=NodeKind.INPUT, lifecycle=NodeLifecycle.ON_RUN_START),
            _component("perception", GraphRole.PERCEPTION, NodeLifecycle.PER_STEP),
            _component("reasoning", GraphRole.REASONING, NodeLifecycle.PER_STEP),
            _component("action_executor", GraphRole.ACTION_EXECUTOR, NodeLifecycle.PER_STEP, primary=True),
            GraphNode(id="output", kind=NodeKind.OUTPUT, lifecycle=NodeLifecycle.TERMINAL),
        ),
        edges=(
            _edge("input", "observation", "perception", "observation"),
            _edge("input", "task", "reasoning", "task"),
            _edge("perception", "perception", "reasoning", "perception"),
            _edge("reasoning", "action", "action_executor", "action"),
            _edge("input", "observation", "action_executor", "observation"),
            _edge("action_executor", "result", "output", "result"),
        ),
        policies=GraphPolicies(max_steps=max_steps),
    )


def _golden_components(verifier_outputs):
    return {
        "test_planner": ScriptedComponent([PlanResult("plan")]),
        "test_perception": ScriptedComponent(
            [PerceptionResult("fake", "pre-0.png"), PerceptionResult("fake", "pre-1.png")]
        ),
        "test_reasoning": ScriptedComponent(
            [Action(ActionType.TAP, {"x": 1, "y": 2}), Action(ActionType.TAP, {"x": 3, "y": 4})]
        ),
        "test_action_executor": FakeActionExecutor(),
        "test_verifier": ScriptedComponent(verifier_outputs),
    }


def test_minimal_graph_reobserves_until_explicit_done_and_preserves_context_identity():
    graph = _minimal_graph()
    perception = ScriptedComponent(
        [PerceptionResult("fake", "s0.png"), PerceptionResult("fake", "s1.png")]
    )
    reasoning = ScriptedComponent(
        [Action(ActionType.TAP, {"x": 1, "y": 2}), Action(ActionType.DONE)]
    )
    executor = FakeActionExecutor()
    resolver = MappingComponentResolver(
        {"perception": perception, "reasoning": reasoning, "action_executor": executor}
    )
    provider = FakeObservationProvider([observation("s0"), observation("s1", sequence=1)])
    context = RuntimeContext(run_id="minimal", max_steps=3)
    result = run_agent_graph(
        graph,
        TaskInput("open settings"),
        provider,
        resolver=resolver,
        runtime=context,
    )
    assert result.status is RunStatus.SUCCESS
    assert result.step_count == 2
    assert result.to_safe_dict()["steps"] == 2
    assert [call for call in provider.calls] == [(0, "pre_action"), (1, "pre_action")]
    assert [item.action.type for item in result.action_results] == [ActionType.TAP, ActionType.DONE]
    component_contexts = [runtime for _, runtime in perception.calls + reasoning.calls + executor.calls]
    assert all(item is context for item in component_contexts)
    assert [call[0].verification for call in reasoning.calls] == [None, None]


def test_feedback_is_cross_step_reobserves_and_has_priority_over_output():
    graph = make_golden_graph()
    components = _golden_components(
        [VerifierResult(False, feedback="retry", should_retry=True), VerifierResult(True)]
    )
    provider = FakeObservationProvider(
        [observation("pre0"), observation("post0"), observation("pre1"), observation("post1")]
    )
    context = RuntimeContext(run_id="feedback", max_steps=4)
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        provider,
        resolver=MappingComponentResolver(components),
        runtime=context,
    )
    assert result.status is RunStatus.SUCCESS
    assert provider.calls == [
        (0, "pre_action"),
        (0, "post_action"),
        (1, "pre_action"),
        (1, "post_action"),
    ]
    assert len(components["test_perception"].calls) == 2
    second_reasoning = components["test_reasoning"].calls[1][0]
    assert isinstance(second_reasoning, ReasoningInput)
    assert second_reasoning.verification.feedback == "retry"
    feedback_events = [event for event in result.events if event.kind == "feedback_latched"]
    assert feedback_events[0].payload["source_step"] == 0
    assert feedback_events[0].payload["target_step"] == 1


def test_condition_false_without_feedback_returns_failure():
    graph = make_golden_graph()
    graph = graph.model_copy(
        update={"edges": tuple(edge for edge in graph.edges if edge.kind is not EdgeKind.FEEDBACK)}
    )
    components = _golden_components([VerifierResult(False, feedback="not complete")])
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("pre"), observation("post")]),
        resolver=MappingComponentResolver(components),
    )
    assert result.status is RunStatus.FAILURE
    assert any(event.kind == "complete" and event.role == "condition" for event in result.events)


def test_feedback_exhausted_policies_are_normalized():
    expected = {
        FeedbackExhaustedPolicy.FAIL: RunStatus.FAILURE,
        FeedbackExhaustedPolicy.CONTINUE: RunStatus.FAILURE,
        FeedbackExhaustedPolicy.TERMINATE: RunStatus.FAILURE,
    }
    for policy, status in expected.items():
        graph = make_golden_graph()
        edges = []
        for edge in graph.edges:
            if edge.kind is EdgeKind.FEEDBACK:
                edges.append(
                    edge.model_copy(
                        update={
                            "feedback": edge.feedback.model_copy(
                                update={"max_iterations": 1, "on_exhausted": policy}
                            )
                        }
                    )
                )
            else:
                edges.append(edge)
        graph = graph.model_copy(update={"edges": tuple(edges)})
        components = _golden_components([VerifierResult(False), VerifierResult(False)])
        result = run_agent_graph(
            graph,
            TaskInput("task"),
            FakeObservationProvider(
                [observation("a"), observation("b"), observation("c"), observation("d")]
            ),
            resolver=MappingComponentResolver(components),
        )
        assert result.status is status
        assert any(event.kind == "feedback_exhausted" for event in result.events)


def test_node_failure_has_start_fail_pair_and_redacted_error():
    graph = _minimal_graph()
    perception = ScriptedComponent([RuntimeError("api_key=must-not-leak")])
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("s")]),
        resolver=MappingComponentResolver(
            {
                "perception": perception,
                "reasoning": ScriptedComponent([Action(ActionType.DONE)]),
                "action_executor": FakeActionExecutor(),
            }
        ),
    )
    assert result.status is RunStatus.FAILURE
    events = [event for event in result.events if event.node_id == "perception"]
    assert [event.kind for event in events if event.kind in {"start", "complete", "fail"}] == [
        "start",
        "fail",
    ]
    assert events[-1].duration_ms >= 0
    assert "must-not-leak" not in str(result.to_safe_dict())


def test_step_limit_and_cancellation_stop_future_nodes():
    graph = _minimal_graph(max_steps=1)
    resolver = MappingComponentResolver(
        {
            "perception": ScriptedComponent([PerceptionResult("fake", "s.png")]),
            "reasoning": ScriptedComponent([Action(ActionType.TAP)]),
            "action_executor": FakeActionExecutor(),
        }
    )
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("s")]),
        resolver=resolver,
    )
    assert result.status is RunStatus.STEP_LIMIT

    cancelled = SimpleCancellationSignal(True)
    context = RuntimeContext(cancellation=cancelled)
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("unused")]),
        resolver=resolver,
        runtime=context,
    )
    assert result.status is RunStatus.CANCELLED


def test_observation_and_action_device_failures_have_distinct_status():
    class BrokenObservationProvider:
        def observe(self, runtime, *, phase):
            raise RuntimeError("device offline")

    graph = _minimal_graph(max_steps=1)
    components = {
        "perception": ScriptedComponent([PerceptionResult("fake", "s.png")]),
        "reasoning": ScriptedComponent([Action(ActionType.TAP)]),
        "action_executor": FakeActionExecutor(),
    }
    observed = run_agent_graph(
        graph,
        TaskInput("task"),
        BrokenObservationProvider(),
        resolver=MappingComponentResolver(components),
    )
    assert observed.status is RunStatus.DEVICE_FAILURE
    assert observed.error_details["code"] == "runtime.observation_failed"

    executor = FakeActionExecutor(statuses=[ExecutionStatus.DEVICE_FAILURE])
    executed = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("s")]),
        resolver=MappingComponentResolver({**components, "action_executor": executor}),
    )
    assert executed.status is RunStatus.DEVICE_FAILURE
    assert len(executor.calls) == 1


def test_sticky_fallback_uses_backup_without_retrying_primary():
    graph = _minimal_graph(max_steps=2)
    perception = next(node for node in graph.nodes if node.id == "perception")
    perception = perception.model_copy(
        update={
            "component": ComponentBinding(
                policy="fallback",
                candidates=(
                    GraphComponentRef(namespace="agent.perception", name="broken"),
                    GraphComponentRef(namespace="agent.perception", name="backup"),
                ),
            )
        }
    )
    graph = graph.model_copy(
        update={"nodes": tuple(perception if node.id == "perception" else node for node in graph.nodes)}
    )
    broken = ScriptedComponent([RuntimeError("offline")])
    backup = ScriptedComponent(
        [PerceptionResult("fake", "a.png"), PerceptionResult("fake", "b.png")]
    )
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("a"), observation("b")]),
        resolver=MappingComponentResolver(
            {
                "broken": broken,
                "backup": backup,
                "reasoning": ScriptedComponent([Action(ActionType.TAP), Action(ActionType.DONE)]),
                "action_executor": FakeActionExecutor(),
            }
        ),
    )
    assert result.status is RunStatus.SUCCESS
    assert len(broken.calls) == 1
    assert len(backup.calls) == 2
    assert any(event.kind == "fallback_selected" for event in result.events)


def test_action_executor_does_not_automatically_fallback_after_side_effect_boundary():
    graph = _minimal_graph(max_steps=1)
    action_node = next(node for node in graph.nodes if node.id == "action_executor")
    action_node = action_node.model_copy(
        update={
            "component": ComponentBinding(
                policy="fallback",
                candidates=(
                    GraphComponentRef(namespace="agent.action_executor", name="first_action"),
                    GraphComponentRef(namespace="agent.action_executor", name="second_action"),
                ),
            )
        }
    )
    graph = graph.model_copy(
        update={
            "nodes": tuple(
                action_node if node.id == "action_executor" else node for node in graph.nodes
            )
        }
    )
    second = FakeActionExecutor()
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("a")]),
        resolver=MappingComponentResolver(
            {
                "perception": ScriptedComponent([PerceptionResult("fake", "a.png")]),
                "reasoning": ScriptedComponent([Action(ActionType.TAP)]),
                "first_action": ScriptedComponent([RuntimeError("uncertain side effect")]),
                "second_action": second,
            }
        ),
    )
    assert result.status is RunStatus.FAILURE
    assert second.calls == []


def test_planner_and_memory_lifecycle_are_run_scoped():
    class Memory:
        def __init__(self):
            self.fragments = []
            self.operations = []

        def invoke(self, input, runtime):
            self.operations.append(input.operation)
            if input.operation is MemoryOperation.RESET:
                self.fragments.clear()
            elif input.operation is MemoryOperation.APPEND:
                self.fragments.append(input.fragment)
            return MemoryResult(input.operation, fragments=tuple(self.fragments))

    graph = _minimal_graph(max_steps=1)
    nodes = list(graph.nodes)
    nodes.insert(1, _component("planner", GraphRole.PLANNER, NodeLifecycle.ON_RUN_START))
    nodes.insert(3, _component("memory", GraphRole.MEMORY, NodeLifecycle.STATEFUL))
    edges = list(graph.edges)
    edges.extend(
        [
            _edge("input", "task", "planner", "task"),
            _edge("planner", "plan", "reasoning", "plan"),
            _edge("input", "task", "memory", "write"),
            _edge("planner", "plan", "memory", "write"),
            _edge("memory", "context", "reasoning", "memory"),
        ]
    )
    graph = graph.model_copy(update={"nodes": tuple(nodes), "edges": tuple(edges)})
    planner = ScriptedComponent([PlanResult("one plan")])
    memory = Memory()
    reasoning = ScriptedComponent([Action(ActionType.DONE)])
    result = run_agent_graph(
        graph,
        TaskInput("task"),
        FakeObservationProvider([observation("s")]),
        resolver=MappingComponentResolver(
            {
                "planner": planner,
                "memory": memory,
                "perception": ScriptedComponent([PerceptionResult("fake", "s.png")]),
                "reasoning": reasoning,
                "action_executor": FakeActionExecutor(),
            }
        ),
    )
    assert result.status is RunStatus.SUCCESS
    assert len(planner.calls) == 1
    assert memory.operations[0] is MemoryOperation.RESET
    assert memory.operations.count(MemoryOperation.APPEND) == 2
    assert len(reasoning.calls[0][0].memory_context) == 2
