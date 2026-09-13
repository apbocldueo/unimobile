from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from zhixing.components import (
    Action,
    ActionType,
    PerceptionResult,
    PlanResult,
    RunStatus,
    RuntimeContext,
    TaskInput,
    VerifierResult,
)
from zhixing.graph import (
    EdgeKind,
    GraphEdge,
    GraphRole,
    NodeLifecycle,
    PortAddress,
    compile_studio_flow_document,
    load_graph_yaml,
)
from zhixing.runtime import BoundAgentGraph, GraphRuntime, MappingComponentResolver, StepFrame, ValueStore, bind_agent_graph, evaluate_predicate, run_agent_graph
from zhixing.runtime.testing import FakeActionExecutor, FakeObservationProvider, ScriptedComponent, observation

from tests.graph.helpers import make_golden_graph
from tests.graph.test_compilers import _studio_document


ROOT = Path(__file__).resolve().parents[2]


def _components():
    return {
        "test_planner": ScriptedComponent([PlanResult("plan")]),
        "test_perception": ScriptedComponent([PerceptionResult("fake", "pre.png")]),
        "test_reasoning": ScriptedComponent([Action(ActionType.TAP)]),
        "test_action_executor": FakeActionExecutor(),
        "test_verifier": ScriptedComponent([VerifierResult(True)]),
    }


def _trace(result):
    return [
        (event.step, event.node_id, event.kind, event.payload.get("branch"))
        for event in result.events
        if event.kind in {"start", "complete", "fail"}
    ]


def test_python_yaml_and_studio_graphs_use_the_same_runtime_trace():
    direct = make_golden_graph()
    yaml_result = load_graph_yaml(ROOT / "examples/agent_graph/agent_graph_v1.yaml")
    studio_result = compile_studio_flow_document(_studio_document())
    graphs = [direct, yaml_result.graph, studio_result.graph]
    assert len({graph.canonical_hash() for graph in graphs}) == 1
    results = []
    for graph in graphs:
        results.append(
            run_agent_graph(
                graph,
                TaskInput("same task"),
                FakeObservationProvider([observation("pre"), observation("post")]),
                resolver=MappingComponentResolver(_components()),
            )
        )
    assert [result.status for result in results] == [RunStatus.SUCCESS] * 3
    assert _trace(results[0]) == _trace(results[1]) == _trace(results[2])


def test_required_port_readiness_and_missing_predicate_field_are_explicit():
    graph = make_golden_graph()
    bound = bind_agent_graph(graph, MappingComponentResolver(_components()))
    runtime = GraphRuntime()
    reasoning = next(node for node in graph.nodes if node.role is GraphRole.REASONING)
    assert not runtime._ready(bound, ValueStore(), 0, reasoning)
    predicate = next(node.predicate for node in graph.nodes if node.id == "verified")
    try:
        evaluate_predicate(predicate, {"other": True})
    except Exception as error:
        assert error.info.code == "runtime.predicate_field_missing"
    else:
        raise AssertionError("missing predicate field must fail")


def test_every_executed_node_has_correlated_start_and_terminal_event():
    result = run_agent_graph(
        make_golden_graph(),
        TaskInput("task"),
        FakeObservationProvider([observation("pre"), observation("post")]),
        resolver=MappingComponentResolver(_components()),
    )
    calls = {}
    for event in result.events:
        if event.kind not in {"start", "complete", "fail"}:
            continue
        calls.setdefault(event.call_id, []).append(event)
    assert "" not in calls
    assert calls
    for events in calls.values():
        assert [event.kind for event in events] in (["start", "complete"], ["start", "fail"])
        assert events[-1].duration_ms is not None
        assert events[-1].duration_ms >= 0


def test_run_result_is_json_serializable_and_uses_safe_observation_summaries():
    result = run_agent_graph(
        make_golden_graph(),
        TaskInput("task", metadata={"api_key": "hidden"}),
        FakeObservationProvider([observation("pre"), observation("post")]),
        resolver=MappingComponentResolver(_components()),
    )
    serialized = json.dumps(result.to_safe_dict())
    assert "hidden" not in serialized
    assert "DeviceObservation(" not in serialized
    assert '"status": "success"' in serialized


def test_runtime_import_does_not_discover_plugins_or_connect_devices():
    code = (
        "import sys; import zhixing.runtime; "
        "assert not any(n.startswith('zhixing.plugins.') for n in sys.modules); "
        "assert 'zhixing.devices.android' not in sys.modules"
    )
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)


def test_graph_runtime_source_never_calls_legacy_runner_mapping():
    source = (ROOT / "zhixing/runtime/engine.py").read_text(encoding="utf-8")
    assert "_execute_on_device" not in source
    assert "AgentRunner" not in source


def test_inactive_control_branch_emits_skip_without_fake_start_event():
    graph = make_golden_graph()
    bound = bind_agent_graph(graph, MappingComponentResolver(_components()))
    blocked_edge = GraphEdge(
        source=PortAddress(node="verified", port="true"),
        target=PortAddress(node="perception", port="control"),
        kind=EdgeKind.CONTROL,
    )
    modified = BoundAgentGraph(
        graph=graph.model_copy(update={"edges": (*graph.edges, blocked_edge)}),
        components=bound.components,
    )
    events = []
    context = RuntimeContext(event_sink=events.append)
    GraphRuntime()._run_phase(
        modified,
        ValueStore(),
        StepFrame(0),
        context,
        {NodeLifecycle.PER_STEP},
        set(),
    )
    perception = [event for event in events if event.node_id == "perception"]
    assert [event.kind for event in perception] == ["node_skipped"]
    result = run_agent_graph(
        modified,
        TaskInput("blocked task"),
        FakeObservationProvider([observation("blocked")]),
    )
    assert result.status is RunStatus.FAILURE
    assert result.error_details["code"] == "runtime.deadlock"
