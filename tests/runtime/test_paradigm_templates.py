from __future__ import annotations

import ast
import inspect
from dataclasses import dataclass, field
from typing import Any

from zhixing.components import DeviceObservation, GroundingResult, RuntimeContext
from zhixing.graph import PARADIGM_TEMPLATES, modular_template
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan
from zhixing.runtime import kernel as kernel_module
from zhixing.runtime.engine import GraphRuntime


@dataclass
class FakeComponent:
    """Scriptable mapping-friendly component for golden paradigm execution."""

    name: str
    outputs: list[Any] = field(default_factory=list)
    calls: list[Any] = field(default_factory=list)

    def invoke(self, value: Any, runtime: RuntimeContext) -> Any:
        """Record input and return a scripted or identity result.

        Args:
            value (Any): Typed adapter input.
            runtime (RuntimeContext): Shared run context.

        Raises:
            None.

        Returns:
            Any: Scripted output or a structural identity value.
        """
        self.calls.append((value, runtime.run_id))
        if self.outputs:
            return self.outputs.pop(0)
        return {"component": self.name, "input": value}


def _components_for(name: str) -> dict[str, FakeComponent]:
    """Create all explicit fake bindings needed by one template.

    Args:
        name (str): Paradigm template name.

    Raises:
        KeyError: The name is not a known test template.

    Returns:
        dict[str, FakeComponent]: Candidate-name component mapping.
    """
    if name == "modular":
        names = ("perception", "planner", "reasoning", "memory", "action")
        return {item: FakeComponent(item) for item in names}
    if name == "reflection":
        return {
            "actor": FakeComponent("actor", [{"draft": 1}]),
            "critique": FakeComponent("critique", [{"needs_revision": False}]),
            "correction": FakeComponent("correction"),
            "revised_action": FakeComponent("revised_action"),
            "perception": FakeComponent("perception", [{"screen": "observed"}]),
            "accepted_action": FakeComponent("accepted_action", [{"accepted": True}]),
        }
    if name == "react":
        return {
            "react_reasoning": FakeComponent("react_reasoning", [{"tool": "inspect"}, {"tool": "inspect"}]),
            "react_tool": FakeComponent(
                "react_tool",
                [
                    {"done": False, "kind": "tool"},
                    {"done": True, "kind": "finish"},
                ],
            ),
            "react_action": FakeComponent("react_action"),
            "finish": FakeComponent("finish", [{"finished": True}]),
        }
    if name == "planner_and_execute":
        return {
            "planner": FakeComponent("planner", [{"steps": ["a", "b"]}]),
            "execute_step": FakeComponent(
                "execute_step",
                [
                    {"done": False, "step": 1, "replan": False},
                    {"done": True, "step": 2, "replan": False},
                ],
            ),
            "replanner": FakeComponent("replanner", [{"steps": ["c"]}]),
            "replan_action": FakeComponent("replan_action", [{"replanned": True}]),
            "plan_action": FakeComponent("plan_action", [{"executed": True}]),
        }
    if name == "uground":
        return {
            "step_summary": FakeComponent("step_summary", [{"history": "summarized"}]),
            "uground_perception": FakeComponent("uground_perception", [{"screen": "observed"}]),
            "semantic_reasoning": FakeComponent("semantic_reasoning", ["submit button"]),
            "grounder": FakeComponent("grounder", [GroundingResult(x=10, y=20)]),
            "grounded_action": FakeComponent("grounded_action", [{"tapped": True}]),
        }
    if name == "multi_agent":
        return {
            "manager_component": FakeComponent("manager", [{"plan": "p"}]),
            "operator_component": FakeComponent("operator", [{"proposal": "tap"}]),
            "critic_component": FakeComponent("critic", [{"decision": "execute"}]),
            "revision": FakeComponent("revision", [{"proposal": "swipe"}]),
            "revised_multi_action": FakeComponent(
                "revised_multi_action",
                [{"executed": "revised"}],
            ),
            "multi_action": FakeComponent("multi_action", [{"executed": True}]),
            "multi_finish": FakeComponent("multi_finish", [{"finished": True}]),
        }
    raise KeyError(name)


def test_all_six_templates_validate_and_use_one_kernel() -> None:
    """Validate representative paradigms without adding specialized runtimes.

    Args:
        None.

    Raises:
        AssertionError: A template is invalid or Kernel embeds a paradigm branch.

    Returns:
        None.
    """
    assert set(PARADIGM_TEMPLATES) == {
        "modular",
        "reflection",
        "react",
        "planner_and_execute",
        "uground",
        "multi_agent",
    }
    for template in PARADIGM_TEMPLATES.values():
        assert template.build().validate_graph().is_valid
    tree = ast.parse(inspect.getsource(kernel_module.GraphExecutionKernel))
    literals = {
        node.value.lower()
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for forbidden in ("react", "uground", "planner_and_execute", "multi_agent", "reflection"):
        assert forbidden not in literals
    module_source = inspect.getsource(kernel_module)
    for forbidden_dependency in (
        "ModularAgent",
        "ReflectionAgent",
        "MultiAgent",
        "UGroundAgent",
        "AgentRunner",
        "_execute_on_device",
    ):
        assert forbidden_dependency not in module_source


def test_all_six_templates_execute_with_fake_components() -> None:
    """Execute every golden template through the same generalized Kernel.

    Args:
        None.

    Raises:
        AssertionError: A template fails or loses expected hierarchy/counters.

    Returns:
        None.
    """
    results = {}
    for name, template in PARADIGM_TEMPLATES.items():
        graph = template.build()
        components = _components_for(name)
        inputs = {"value": {"task": name}}
        if name == "uground":
            inputs["observation"] = DeviceObservation(
                screenshot_path="fake.png",
                width=100,
                height=200,
            )
        result = GraphExecutionKernel().run(
            bind_execution_plan(graph, components),
            inputs,
            runtime=RuntimeContext(run_id=f"run-{name}"),
        )
        assert result.status is KernelStatus.SUCCESS, (name, result.error_code, result.error)
        assert result.outputs
        assert any(event.kind == "complete" for event in result.events)
        results[name] = result
    assert results["react"].interaction_steps == 0
    react_event_paths = {event.node_path for event in results["react"].events}
    assert "tool_loop/tool_router" in react_event_paths
    assert "tool_loop/tool_history" in react_event_paths
    assert results["planner_and_execute"].interaction_steps == 1
    assert results["uground"].interaction_steps == 1
    multi_paths = {event.node_path for event in results["multi_agent"].events}
    assert "manager/manager_component" in multi_paths
    assert "operator/operator_component" in multi_paths
    assert "critic/critic_component" in multi_paths


def test_planner_and_execute_replan_branch_is_graph_driven() -> None:
    """Select the explicit replan route without a Kernel paradigm branch.

    Args:
        None.

    Raises:
        AssertionError: Replanning is not selected or invokes the execute exit.

    Returns:
        None.
    """
    components = _components_for("planner_and_execute")
    components["execute_step"] = FakeComponent(
        "execute_step",
        [{"done": True, "replan": True}],
    )
    result = GraphExecutionKernel().run(
        bind_execution_plan(PARADIGM_TEMPLATES["planner_and_execute"].build(), components),
        {"value": {"task": "replan"}},
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": {"replanned": True}}
    assert len(components["replanner"].calls) == 1
    assert len(components["replan_action"].calls) == 1
    assert not components["plan_action"].calls


def test_multi_agent_revision_branch_is_graph_driven() -> None:
    """Select the explicit revision route after sequential agent subgraphs.

    Args:
        None.

    Raises:
        AssertionError: Revision routing or root action arbitration is incorrect.

    Returns:
        None.
    """
    components = _components_for("multi_agent")
    components["critic_component"] = FakeComponent(
        "critic",
        [{"decision": "revise"}],
    )
    result = GraphExecutionKernel().run(
        bind_execution_plan(PARADIGM_TEMPLATES["multi_agent"].build(), components),
        {"value": {"task": "revise"}},
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.outputs == {"result": {"executed": "revised"}}
    assert len(components["revision"].calls) == 1
    assert len(components["revised_multi_action"].calls) == 1
    assert not components["multi_action"].calls
    assert not components["multi_finish"].calls


def test_modular_template_feedback_reactivates_next_interaction_path() -> None:
    """Use explicit bounded feedback without a paradigm-specific scheduler.

    Args:
        None.

    Raises:
        AssertionError: Feedback fails to reactivate the bounded path.

    Returns:
        None.
    """
    graph = modular_template(
        include_planner=False,
        include_memory=False,
        include_verifier=True,
    )
    components = {
        "perception": FakeComponent("perception", [{"screen": "observed"}]),
        "reasoning": FakeComponent(
            "reasoning",
            [{"action": "first"}, {"action": "corrected"}],
        ),
        "action": FakeComponent(
            "action",
            [{"executed": "first"}, {"executed": "corrected"}],
        ),
        "verifier": FakeComponent(
            "verifier",
            [{"retry": True}, {"retry": False}],
        ),
    }
    result = GraphExecutionKernel().run(
        bind_execution_plan(graph, components),
        {"value": {"task": "feedback"}},
    )
    assert result.status is KernelStatus.SUCCESS
    assert result.interaction_steps == 2
    assert len(components["reasoning"].calls) == 2
    assert len(components["action"].calls) == 2
    assert any(event.kind == "feedback_latched" for event in result.events)


def test_legacy_graph_runtime_facade_delegates_without_scheduler_copy() -> None:
    """Keep the public V1 facade thin while preserving compatibility helpers.

    Args:
        None.

    Raises:
        AssertionError: The facade contains a second scheduler.

    Returns:
        None.
    """
    source = inspect.getsource(GraphRuntime.run)
    assert "GraphExecutionKernel().run_compatibility" in source
    tree = ast.parse(inspect.cleandoc(source))
    assert not any(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree))
