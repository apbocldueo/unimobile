from __future__ import annotations

import pytest

from zhixing.components import (
    Action,
    ActionType,
    ComponentInputError,
    ComponentProtocolError,
    ComponentRole,
    DeviceObservation,
    GroundingInput,
    GroundingResult,
    MemoryFragment,
    MemoryInput,
    MemoryOperation,
    MemoryResult,
    PerceptionInput,
    PerceptionResult,
    PlanInput,
    PlanResult,
    RAW_RESPONSE_METADATA_KEY,
    ReasoningInput,
    RuntimeContext,
    TaskInput,
    VerifierInput,
    VerifierResult,
    adapt_component,
)
from zhixing.core.agent.protocol import FragmentType


class LegacyPerception:
    def perceive(self, value):
        assert isinstance(value, PerceptionInput)
        return PerceptionResult("legacy", value.screenshot_path)


class LegacyPlanner:
    def make_plan(self, value):
        return PlanResult(f"plan:{value.task}")


class LegacyReasoner:
    def think(self, task, plan, perception_result, memory_context, *, available_apps=""):
        assert plan == "do it"
        return Action(ActionType.TAP, {"x": 1, "y": 2}), "raw answer"


class ActionOnlyReasoner(LegacyReasoner):
    def think(self, *args, **kwargs):
        return Action(ActionType.DONE)


class LegacyMemory:
    def __init__(self):
        self.values = []
        self.queries = []

    def add(self, value):
        self.values.append(value)

    def get_working_context(self):
        return list(self.values)

    def clear(self):
        self.values.clear()

    def load_knowledge(self, query):
        self.queries.append(query)

    def retrieve_experience(self, screenshot_path, task):
        return Action(ActionType.KEY, {"code": "back"})


class LegacyVerifier:
    def verify(self, value):
        return VerifierResult(True, metadata={"input": value})


class LegacyGrounder:
    def ground(self, screenshot_path, description, width, height):
        assert (screenshot_path, description, width, height) == ("shot.png", "button", 10, 20)
        return 4, 7


def _reasoning_input():
    return ReasoningInput(
        TaskInput("task"),
        PlanResult("do it"),
        PerceptionResult("grid", "shot.png"),
    )


def test_legacy_agent_roles_adapt_to_invoke_without_identity_drift():
    runtime = RuntimeContext()
    observation = DeviceObservation("shot.png", 10, 20)
    perception = adapt_component("perception", LegacyPerception()).invoke(observation, runtime)
    assert perception.mode == "legacy"

    plan = adapt_component("planner", LegacyPlanner()).invoke(PlanInput("task"), runtime)
    assert isinstance(plan, PlanResult)

    action = adapt_component("reasoning", LegacyReasoner()).invoke(_reasoning_input(), runtime)
    assert isinstance(action, Action)
    assert action.metadata[RAW_RESPONSE_METADATA_KEY] == "raw answer"

    verifier_input = VerifierInput("task", "a.png", "b.png", action)
    verified = adapt_component("verifier", LegacyVerifier()).invoke(verifier_input, runtime)
    assert isinstance(verified, VerifierResult)
    assert verified.metadata["input"] is verifier_input

    grounded = adapt_component("grounder", LegacyGrounder()).invoke(
        GroundingInput(observation, "button"), runtime
    )
    assert grounded == GroundingResult(4, 7)


def test_reasoning_normalizes_action_only_and_reverse_tuple():
    runtime = RuntimeContext()
    action = adapt_component(ComponentRole.REASONING, ActionOnlyReasoner()).invoke(
        _reasoning_input(), runtime
    )
    assert action.type is ActionType.DONE

    class NewReasoner:
        def invoke(self, input, runtime):
            return Action(
                ActionType.DONE,
                metadata={RAW_RESPONSE_METADATA_KEY: "new raw"},
            )

    legacy = adapt_component("reasoning", NewReasoner(), "legacy", runtime=runtime)
    result, raw = legacy.think(
        "task",
        "plan string",
        PerceptionResult("grid", "shot.png"),
        [],
    )
    assert result.type is ActionType.DONE
    assert raw == "new raw"


def test_memory_tagged_operations_and_reverse_adapter():
    runtime = RuntimeContext()
    legacy = LegacyMemory()
    memory = adapt_component("memory", legacy)
    fragment = MemoryFragment("user", FragmentType.TEXT, "hello")
    memory.invoke(MemoryInput(MemoryOperation.APPEND, fragment=fragment), runtime)
    assert memory.invoke(MemoryInput(MemoryOperation.READ), runtime).fragments == (fragment,)
    memory.invoke(MemoryInput(MemoryOperation.LOAD_KNOWLEDGE, query="settings"), runtime)
    assert legacy.queries == ["settings"]
    cached = memory.invoke(
        MemoryInput(
            MemoryOperation.RETRIEVE_EXPERIENCE,
            screenshot_path="shot.png",
            task="task",
        ),
        runtime,
    )
    assert cached.action.type is ActionType.KEY
    memory.invoke(MemoryInput(MemoryOperation.RESET), runtime)
    assert legacy.values == []
    with pytest.raises(ComponentInputError, match="requires fragment"):
        memory.invoke(MemoryInput(MemoryOperation.APPEND), runtime)

    class NewMemory:
        def __init__(self):
            self.fragments = []

        def invoke(self, input, runtime):
            if input.operation is MemoryOperation.APPEND:
                self.fragments.append(input.fragment)
            if input.operation is MemoryOperation.RESET:
                self.fragments.clear()
            return MemoryResult(input.operation, fragments=tuple(self.fragments))

    reverse = adapt_component("memory", NewMemory(), "legacy")
    reverse.add(fragment)
    assert reverse.get_working_context() == [fragment]
    reverse.clear()
    assert reverse.get_working_context() == []


def test_new_components_work_through_current_legacy_entry_points():
    class NewPerception:
        def invoke(self, input, runtime):
            assert isinstance(input, DeviceObservation)
            return PerceptionResult("new", input.screenshot_path)

    class NewPlanner:
        def invoke(self, input, runtime):
            return PlanResult(input.task)

    class NewVerifier:
        def invoke(self, input, runtime):
            return VerifierResult(True)

    class NewGrounder:
        def invoke(self, input, runtime):
            return GroundingResult(2, 3)

    assert adapt_component("perception", NewPerception(), "legacy").perceive(
        PerceptionInput("x.png", 5, 6)
    ).mode == "new"
    assert adapt_component("planner", NewPlanner(), "legacy").make_plan(PlanInput("task")).content == "task"
    assert adapt_component("verifier", NewVerifier(), "legacy").verify(object()).is_success
    assert adapt_component("grounder", NewGrounder(), "legacy").ground("x.png", "x", 5, 6) == (2, 3)


def test_adaptation_diagnostics_are_sanitized_and_execution_errors_propagate():
    class Bad:
        def __repr__(self):
            return "Bad(api_key=secret)"

    with pytest.raises(ComponentProtocolError) as caught:
        adapt_component("perception", Bad())
    message = str(caught.value)
    assert "perception" in message
    assert "invoke(input, runtime)" in message
    assert "secret" not in message

    class BrokenPerception:
        def perceive(self, input):
            raise RuntimeError("domain failure")

    with pytest.raises(RuntimeError, match="domain failure"):
        adapt_component("perception", BrokenPerception()).invoke(
            DeviceObservation("x", 1, 1), RuntimeContext()
        )

