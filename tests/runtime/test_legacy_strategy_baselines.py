from __future__ import annotations

from types import MethodType
from typing import Any

from zhixing.components import Action, ActionType, PerceptionResult
from zhixing.engine.agent.modular_agent import AgentRuntimeState, ModularAgent
from zhixing.engine.agent.multi_agent import MultiAgent
from zhixing.engine.agent.reflection_agent import ReflectionAgent
from zhixing.engine.agent.uground_agent import UGroundAgent


class _Logger:
    """No-op logger used by isolated strategy-order tests."""

    def __getattr__(self, name: str):
        """Return a no-op logging method.

        Args:
            name (str): Requested logging method name.

        Raises:
            None.

        Returns:
            Any: Callable accepting arbitrary log arguments.
        """
        del name
        return lambda *args, **kwargs: None


def _base(agent: Any) -> list[str]:
    """Install the minimum mutable legacy strategy state.

    Args:
        agent (Any): Uninitialized legacy strategy instance.

    Raises:
        None.

    Returns:
        list[str]: Shared call-order recorder.
    """
    calls: list[str] = []
    agent.logger = _Logger()
    agent.verbose = False
    agent.state = AgentRuntimeState()
    agent.current_task = "task"
    agent.current_plan = "plan"
    agent._start_app_catalog_text = ""
    agent.memory = None
    agent.verifier = None
    return calls


def test_modular_agent_baseline_is_perception_then_reasoning() -> None:
    """Freeze the legacy ModularAgent single-step call order.

    Args:
        None.

    Raises:
        AssertionError: Legacy order or Action changes.

    Returns:
        None.
    """
    agent = object.__new__(ModularAgent)
    calls = _base(agent)

    class Perception:
        """Fake legacy perception component."""

        def perceive(self, input_value: Any) -> PerceptionResult:
            """Record and return one perception result.

            Args:
                input_value (Any): Legacy PerceptionInput.

            Raises:
                None.

            Returns:
                PerceptionResult: Deterministic observation.
            """
            calls.append("perception")
            return PerceptionResult("fake", input_value.screenshot_path)

    class Reasoning:
        """Fake legacy reasoning component."""

        def think(self, **kwargs: Any):
            """Record and return one terminal action.

            Args:
                **kwargs (Any): Legacy reasoning keyword inputs.

            Raises:
                None.

            Returns:
                tuple[Action, str]: Terminal action and raw response.
            """
            del kwargs
            calls.append("reasoning")
            return Action(ActionType.DONE), "done"

    agent.perceptions = [Perception()]
    agent.reasoning = Reasoning()
    action = agent.step("shot.png", 10, 20, "tree.xml")
    assert action.type is ActionType.DONE
    assert calls == ["perception", "reasoning"]


def test_reflection_agent_baseline_reflects_before_actor() -> None:
    """Freeze the legacy ReflectionAgent reflect/perceive/actor order.

    Args:
        None.

    Raises:
        AssertionError: Legacy order or Action changes.

    Returns:
        None.
    """
    agent = object.__new__(ReflectionAgent)
    calls = _base(agent)
    agent.use_experience_cache = False
    agent._reflect_previous_action = MethodType(
        lambda self, path: calls.append("reflect") or None,
        agent,
    )
    agent._perceive_current_screen = MethodType(
        lambda self, *args: calls.append("perception") or PerceptionResult("fake", "shot.png"),
        agent,
    )
    agent._think_with_reasoning = MethodType(
        lambda self, value: calls.append("actor") or (Action(ActionType.DONE), "done"),
        agent,
    )
    agent._commit_action = MethodType(
        lambda self, *args: calls.append("commit"),
        agent,
    )
    action = agent.step("shot.png", 10, 20, "tree.xml")
    assert action.type is ActionType.DONE
    assert calls == ["reflect", "perception", "actor", "commit"]


def test_multi_agent_baseline_is_critic_perception_manager_operator() -> None:
    """Freeze the legacy sequential MultiAgent collaboration order.

    Args:
        None.

    Raises:
        AssertionError: Legacy collaboration order changes.

    Returns:
        None.
    """
    agent = object.__new__(MultiAgent)
    calls = _base(agent)
    agent._reflect_previous_action = MethodType(
        lambda self, path: calls.append("critic") or None,
        agent,
    )
    agent._perceive_current_screen = MethodType(
        lambda self, *args: calls.append("perception") or PerceptionResult("fake", "shot.png"),
        agent,
    )
    agent._run_manager_step = MethodType(
        lambda self, path: calls.append("manager"),
        agent,
    )
    agent._think_with_reasoning = MethodType(
        lambda self, value: calls.append("operator") or (Action(ActionType.DONE), "done"),
        agent,
    )
    agent._commit_action = MethodType(
        lambda self, *args: calls.append("commit"),
        agent,
    )
    action = agent.step("shot.png", 10, 20, "tree.xml")
    assert action.type is ActionType.DONE
    assert calls == ["critic", "perception", "manager", "operator", "commit"]


def test_uground_agent_baseline_is_summary_reasoning_grounding() -> None:
    """Freeze the legacy UGroundAgent two-stage grounding order.

    Args:
        None.

    Raises:
        AssertionError: Legacy grounding order or Action changes.

    Returns:
        None.
    """
    agent = object.__new__(UGroundAgent)
    calls = _base(agent)
    agent._summarize_previous_step_if_needed = MethodType(
        lambda self, path: calls.append("summary"),
        agent,
    )
    agent._perceive_current_screen = MethodType(
        lambda self, *args: calls.append("perception") or PerceptionResult("fake", "shot.png"),
        agent,
    )
    semantic_action = Action(
        ActionType.TAP,
        metadata={"needs_grounding": True, "grounding_description": "button"},
    )
    agent._think_with_reasoning = MethodType(
        lambda self, value: calls.append("reasoning") or (semantic_action, "raw"),
        agent,
    )
    agent._ground_action_if_needed = MethodType(
        lambda self, action, *args: calls.append("grounder") or action,
        agent,
    )
    agent._commit_action = MethodType(
        lambda self, *args: calls.append("commit"),
        agent,
    )
    agent._is_verifiable_action = MethodType(lambda self, action: False, agent)
    action = agent.step("shot.png", 10, 20, "tree.xml")
    assert action.type is ActionType.TAP
    assert calls == ["summary", "perception", "reasoning", "grounder", "commit"]
