"""Run the golden AgentGraph through fake components without a device or API key."""

from __future__ import annotations

import json
from pathlib import Path

from zhixing.components import (
    Action,
    ActionType,
    PerceptionResult,
    PlanResult,
    TaskInput,
    VerifierResult,
)
from zhixing.graph import load_graph_yaml
from zhixing.runtime import MappingComponentResolver, run_agent_graph
from zhixing.runtime.testing import (
    FakeActionExecutor,
    FakeObservationProvider,
    ScriptedComponent,
    observation,
)


def build_fake_components() -> dict[str, object]:
    """Create deterministic components matching the golden graph bindings.

    Args:
        None.

    Raises:
        None.

    Returns:
        dict[str, object]: Explicit components keyed by declarative plugin name.
    """
    return {
        "test_planner": ScriptedComponent([PlanResult("Inspect the UI and complete the task")]),
        "test_perception": ScriptedComponent(
            [
                PerceptionResult("fake", "pre-step-0.png"),
                PerceptionResult("fake", "pre-step-1.png"),
            ]
        ),
        "test_reasoning": ScriptedComponent(
            [
                Action(ActionType.TAP, {"x": 10, "y": 20}),
                Action(ActionType.TAP, {"x": 30, "y": 40}),
            ]
        ),
        "test_action_executor": FakeActionExecutor(),
        "test_verifier": ScriptedComponent(
            [
                VerifierResult(False, feedback="The first target did not open", should_retry=True),
                VerifierResult(True, feedback="The second target completed the task"),
            ]
        ),
    }


def main() -> int:
    """Compile, bind, run, and print a deterministic feedback execution.

    Args:
        None.

    Raises:
        RuntimeError: The checked-in golden graph cannot be compiled.

    Returns:
        int: Zero when the fake run succeeds, otherwise one.
    """
    graph_path = Path(__file__).resolve().parent / "agent_graph" / "agent_graph_v1.yaml"
    compilation = load_graph_yaml(graph_path)
    if not compilation.is_success or compilation.graph is None:
        raise RuntimeError(json.dumps(compilation.to_safe_dict(), ensure_ascii=False))
    provider = FakeObservationProvider(
        [
            observation("pre-step-0"),
            observation("post-step-0"),
            observation("pre-step-1"),
            observation("post-step-1"),
        ]
    )
    result = run_agent_graph(
        compilation,
        TaskInput("Open the fake target and verify completion"),
        provider,
        resolver=MappingComponentResolver(build_fake_components()),
    )
    print(f"canonical_hash={compilation.graph.canonical_hash()}")
    print("node_events:")
    for event in result.events:
        if event.kind in {"start", "complete", "fail", "feedback_latched"}:
            print(
                f"  seq={event.sequence:02d} step={event.step} "
                f"node={event.node_id or '-'} kind={event.kind}"
            )
    print("run_result:")
    print(json.dumps(result.to_safe_dict(), ensure_ascii=False, indent=2))
    return 0 if result.status.value == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
