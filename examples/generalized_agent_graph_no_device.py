"""Run generalized AgentGraph paradigms with deterministic fake components."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zhixing.components import RuntimeContext
from zhixing.graph import planner_execute_template, react_template
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan


@dataclass
class FakeComponent:
    """Small fake component used by the executable documentation."""

    name: str
    outputs: list[Any] = field(default_factory=list)
    calls: int = 0

    def invoke(self, value: Any, runtime: RuntimeContext) -> Any:
        """Return a deterministic value while preserving RuntimeContext identity.

        Args:
            value (Any): Logical input assembled by the contract adapter.
            runtime (RuntimeContext): Shared run context.

        Raises:
            None.

        Returns:
            Any: Next scripted output or an identity mapping.
        """
        self.calls += 1
        if self.outputs:
            return self.outputs.pop(0)
        return {"component": self.name, "input": value, "run_id": runtime.run_id}


def run_react() -> dict[str, Any]:
    """Execute two local ReAct tool iterations without a device.

    Args:
        None.

    Raises:
        AssertionError: The generalized Kernel does not complete successfully.

    Returns:
        dict[str, Any]: Safe summary for terminal display.
    """
    components = {
        "react_reasoning": FakeComponent(
            "reasoning",
            [{"tool": "inspect"}, {"tool": "inspect"}],
        ),
        "react_tool": FakeComponent(
            "tool",
            [
                {"done": False, "kind": "tool", "observation": "first"},
                {"done": True, "kind": "finish", "observation": "second"},
            ],
        ),
        "react_action": FakeComponent("action"),
        "finish": FakeComponent("finish", [{"finished": True}]),
    }
    result = GraphExecutionKernel().run(
        bind_execution_plan(react_template(), components),
        {"value": {"task": "inspect fake UI"}},
        runtime=RuntimeContext(run_id="example-react"),
    )
    assert result.status is KernelStatus.SUCCESS, (result.error_code, result.error)
    return {
        "status": result.status.value,
        "outputs": dict(result.outputs),
        "activations": result.activation_count,
        "interaction_steps": result.interaction_steps,
        "loop_iterations": [
            event.loop_iteration
            for event in result.events
            if event.kind == "loop_iteration"
        ],
    }


def run_planner_execute() -> dict[str, Any]:
    """Execute plan state and a bounded execute subgraph loop.

    Args:
        None.

    Raises:
        AssertionError: The generalized Kernel does not complete successfully.

    Returns:
        dict[str, Any]: Safe summary for terminal display.
    """
    components = {
        "planner": FakeComponent("planner", [{"steps": ["open", "confirm"]}]),
        "execute_step": FakeComponent(
            "execute_step",
            [
                {"done": False, "step": "open", "replan": False},
                {"done": True, "step": "confirm", "replan": False},
            ],
        ),
        "replanner": FakeComponent("replanner", [{"steps": ["retry"]}]),
        "replan_action": FakeComponent("replan_action", [{"replanned": True}]),
        "plan_action": FakeComponent("action", [{"executed": True}]),
    }
    result = GraphExecutionKernel().run(
        bind_execution_plan(planner_execute_template(), components),
        {"value": {"task": "complete fake plan"}},
        runtime=RuntimeContext(run_id="example-planner"),
    )
    assert result.status is KernelStatus.SUCCESS, (result.error_code, result.error)
    return {
        "status": result.status.value,
        "outputs": dict(result.outputs),
        "activations": result.activation_count,
        "interaction_steps": result.interaction_steps,
        "event_paths": sorted({event.node_path for event in result.events}),
    }


def main() -> None:
    """Print deterministic generalized runtime evidence.

    Args:
        None.

    Raises:
        AssertionError: An example graph fails.

    Returns:
        None.
    """
    print("ReAct:", run_react())
    print("Planner-and-Execute:", run_planner_execute())


if __name__ == "__main__":
    main()
