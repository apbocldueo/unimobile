from __future__ import annotations

from zhixing.components import (
    Action,
    ActionResult,
    ActionType,
    AgentState,
    BenchmarkInitInput,
    BenchmarkInitKind,
    DeviceObservation,
    DeviceOperation,
    DeviceRequest,
    EvalResult,
    EvaluationResult,
    ExecutionStatus,
    MemoryFragment,
    PerceptionInput,
    PerceptionResult,
    PlanInput,
    PlanResult,
    ReasoningInput,
    RunResult,
    RunStatus,
    RuntimeContext,
    TaskInput,
    VerifierInput,
    VerifierResult,
    redact_mapping,
)
from zhixing.core.agent import protocol as legacy_agent
from zhixing.core.benchmark.protocol import EvalResult as LegacyEvalResult


def test_existing_protocol_objects_keep_canonical_identity():
    assert Action is legacy_agent.Action
    assert PerceptionInput is legacy_agent.PerceptionInput
    assert PerceptionResult is legacy_agent.PerceptionResult
    assert PlanInput is legacy_agent.PlanInput
    assert PlanResult is legacy_agent.PlanResult
    assert MemoryFragment is legacy_agent.MemoryFragment
    assert VerifierInput is legacy_agent.VerifierInput
    assert VerifierResult is legacy_agent.VerifierResult
    assert EvalResult is LegacyEvalResult
    assert EvaluationResult is LegacyEvalResult


def test_runtime_values_have_independent_defaults_and_explicit_data_flow():
    first = TaskInput("open settings")
    second = TaskInput("open calendar")
    assert first.metadata is not second.metadata

    observation = DeviceObservation("shot.png", 1080, 2400, "tree.xml", platform="android")
    legacy = observation.to_legacy()
    assert DeviceObservation.from_legacy(legacy).screenshot_path == "shot.png"

    perception = PerceptionResult("grid", "shot.png")
    reasoning = ReasoningInput(
        task=first,
        plan=PlanResult("tap settings"),
        perception=perception,
        available_apps="- settings",
    )
    assert reasoning.task.instruction == "open settings"
    assert reasoning.plan.content == "tap settings"
    assert reasoning.perception is perception

    assert DeviceRequest(DeviceOperation.TAP).params == {}
    assert BenchmarkInitInput(BenchmarkInitKind.TASK_PARAMETER).params == {}


def test_agent_state_reset_isolated_between_runs():
    action = Action(ActionType.TAP, {"x": 1, "y": 2})
    state = AgentState(
        current_task=TaskInput("old"),
        plan=PlanResult("old plan"),
        step=3,
        last_observation=DeviceObservation("old.png", 10, 20),
        last_action=action,
        last_action_result=ActionResult(action, ExecutionStatus.SUCCESS),
        strategy_state={"index": 2},
    )
    state.reset(TaskInput("new"))
    assert state.current_task.instruction == "new"
    assert state.plan is None
    assert state.step == 0
    assert state.last_observation is None
    assert state.last_action is None
    assert state.last_action_result is None
    assert state.strategy_state == {}
    assert AgentState().strategy_state is not AgentState().strategy_state


def test_context_events_are_ordered_and_services_are_not_serialized():
    class SecretDevice:
        api_key = "must-not-leak"

        def __repr__(self):
            return "SecretDevice(api_key=must-not-leak)"

    events = []
    runtime = RuntimeContext(
        run_id="run-1",
        device=SecretDevice(),
        event_sink=events.append,
        metadata={"safe": "yes", "api_key": "sk-secret"},
    )
    first = runtime.emit(
        phase="decision",
        role="reasoning",
        component="fake",
        kind="start",
        payload={"token": "secret", "count": 1},
    )
    second = runtime.emit(
        phase="decision",
        role="reasoning",
        component="fake",
        kind="complete",
    )
    assert [event.sequence for event in events] == [1, 2]
    assert first.to_safe_dict()["payload"]["token"] == "<redacted>"
    assert second.run_id == "run-1"
    safe = runtime.to_safe_dict()
    assert safe["services"]["device"] is True
    assert safe["metadata"]["api_key"] == "<redacted>"
    assert "must-not-leak" not in repr(runtime)
    assert "must-not-leak" not in str(safe)


def test_run_result_and_action_result_distinguish_terminal_states():
    action = Action(ActionType.DONE)
    result = ActionResult(action, ExecutionStatus.TERMINAL)
    run = RunResult(
        run_id="run-limit",
        status=RunStatus.STEP_LIMIT,
        state=AgentState(step=15),
        action_results=(result,),
        usage={"total_tokens": 42, "auth_token": "hidden"},
        error="",
    )
    safe = run.to_safe_dict()
    assert result.succeeded
    assert safe["status"] == "step_limit"
    assert safe["steps"] == 15
    assert safe["action_statuses"] == ["terminal"]
    assert safe["usage"]["auth_token"] == "<redacted>"


def test_runtime_safe_dicts_hash_raw_device_identity() -> None:
    """Keep raw target authority out of observations and action evidence."""
    raw = "RAW_DEVICE_AUTHORITY_CANARY"
    observation = DeviceObservation("shot.png", 10, 20, device_id=raw)
    action = ActionResult(
        Action(ActionType.TAP, {"x": 1, "y": 2}),
        ExecutionStatus.SUCCESS,
        device_id=raw,
    )
    run = RunResult(
        run_id="run-device-safe",
        status=RunStatus.SUCCESS,
        state=AgentState(),
        error_details={"device_id": raw},
    )
    observation_id = observation.to_safe_dict()["device_id"]
    action_id = action.to_safe_dict()["device_id"]
    assert observation_id == action_id
    assert observation_id.startswith("device-sha256:")
    assert raw not in str(observation.to_safe_dict())
    assert raw not in str(action.to_safe_dict())
    assert run.to_safe_dict()["error_details"]["device_id"] == observation_id


def test_recursive_redaction_does_not_traverse_unknown_objects():
    class Client:
        def __repr__(self):
            return "Client(password=leak)"

    safe = redact_mapping(
        {
            "nested": {"password": "leak", "values": [1, {"secret": "x"}]},
            "client": Client(),
        }
    )
    assert safe["nested"]["password"] == "<redacted>"
    assert safe["nested"]["values"][1]["secret"] == "<redacted>"
    assert safe["client"].endswith(".Client>")
    assert "leak" not in str(safe)


def test_safe_redaction_bounds_collections_and_hides_machine_paths():
    """Bound nested diagnostic data and hide local or credential-bearing paths.

    Args:
        None.

    Raises:
        AssertionError: Safe serialization leaks or emits unbounded data.

    Returns:
        None.
    """
    nested = {"level": {"level": {"level": {"level": {"level": {"level": {}}}}}}}
    values = list(range(75))
    safe = redact_mapping(
        {
            "nested": nested,
            "values": values,
            "home": "/Users/alice/private/plugin.py",
            "url": "https://alice:hunter2@example.test/components",
        }
    )

    assert "<max-depth>" in str(safe["nested"])
    assert len(safe["values"]) == 51
    assert safe["values"][-1] == "<25 items omitted>"
    assert safe["home"] == "<local-path>"
    assert "hunter2" not in safe["url"]
    assert safe["url"].startswith("https://<redacted>@")


def test_safe_redaction_handles_cycles_and_limits_mapping_items():
    """Summarize cyclic and oversized mappings without recursive failure.

    Args:
        None.

    Raises:
        AssertionError: Cycles or oversized mappings are not bounded.

    Returns:
        None.
    """
    cyclic: dict[str, object] = {}
    cyclic["self"] = cyclic
    oversized = {f"field-{index}": index for index in range(75)}

    safe = redact_mapping({"cyclic": cyclic, "oversized": oversized})

    assert safe["cyclic"]["self"] == {"__summary__": "<cycle>"}
    assert safe["oversized"]["__truncated_items__"] == 25
    assert len(safe["oversized"]) == 51
