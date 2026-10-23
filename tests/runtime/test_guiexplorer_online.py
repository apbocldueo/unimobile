"""Full production-graph differential tests against unchanged official online execution."""

import dataclasses
import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from zhixing.components import RunStatus, RuntimeContext
from zhixing.graph import load_graph_yaml
from zhixing.guiexplorer import build_guiexplorer_graph
from zhixing.plugins.agent.guiexplorer.environment import GUIExplorerEnvironment
from zhixing.plugins.agent.guiexplorer.types import GUIExplorerReply
from zhixing.sdk import AgentRunConfig, compile_agent

from tests.runtime.guiexplorer_support import Device, GOAL, Model, Retrieval, run_original


ROOT = Path(__file__).resolve().parents[2]


def decision(action, reason="perform the requested operation"):
    """Produce one external source-format decision without Agent logic.

    Args:
        action: Original JSONAction fields.
        reason: Source reasoning text.
    Returns:
        GUIExplorerReply: Scripted original model response.
    """
    return GUIExplorerReply("Reasoning: " + reason + "\nAction: " + json.dumps(action))


CLICK = decision({"action_type": "click", "index": 2})
COMPLETE = decision({"action_type": "status", "goal_status": "complete"})


def assert_parity(tmp_path, replies, *, max_rounds=3, orientation=0, fail_click=False,
                  results=None, comparison="2", top_k=1, threshold=0.9, graph=None):
    """Compare all observable source phases, pixels, RAG queries, history and results.

    Args:
        tmp_path: Real artifact destination.
        replies: Shared external action/summary response script.
        max_rounds: Independent source decision budget.
        orientation, fail_click: Controlled external device conditions.
        results: Controlled original retrieval response, including empty/short results.
        comparison: Controlled pairwise model result.
        top_k, threshold: Shared original retrieval settings.
        graph: Optional actual YAML graph for production execution.
    Raises:
        AssertionError: Production online behavior differs from the original source.
    Returns:
        tuple: Production RunResult, portable episode payload and external services.
    """
    expected, agent, expected_model, expected_device, expected_rag = run_original(replies,
        max_rounds=max_rounds, device=Device(orientation, fail_click), retrieval=Retrieval(results),
        comparison=comparison, top_k=top_k, threshold=threshold)
    device, rag, model = Device(orientation, fail_click), Retrieval(results), Model(replies, comparison)
    context = RuntimeContext(max_steps=max_rounds + 1)
    graph = graph or build_guiexplorer_graph(max_rounds=max_rounds, top_k=top_k, threshold=threshold)
    actual = compile_agent(graph, dependencies={"llm": model, "retrieval": rag}).run(GOAL,
        AgentRunConfig(artifact_root=tmp_path, max_steps=max_rounds + 1, include_ui_tree=False),
        device=GUIExplorerEnvironment(device, sleep=device.sleep), runtime=context)
    assert device.events == expected_device.events
    assert model.rank_calls == expected_model.rank_calls
    assert len(model.calls) == len(expected_model.calls)
    for (prompt, images), (expected_prompt, expected_images) in zip(model.calls, expected_model.calls):
        assert prompt == expected_prompt
        assert len(images) == len(expected_images) == 2
        for pixels, expected_pixels in zip(images, expected_images):
            np.testing.assert_array_equal(pixels, expected_pixels)
    assert len(rag.calls) == len(expected_rag.calls)
    for (crops, *settings), (expected_crops, *expected_settings) in zip(rag.calls, expected_rag.calls):
        assert settings == expected_settings
        assert len(crops) == len(expected_crops)
        for pixels, expected_pixels in zip(crops, expected_crops):
            np.testing.assert_array_equal(pixels, expected_pixels)
    if isinstance(expected, Exception):
        assert actual.status is RunStatus.FAILURE, actual.error
        return actual, None, model, device, rag
    payload = context.state.last_action_result.metadata["guiexplorer"]
    assert payload["decision_rounds"] == len(expected)
    assert len(payload["episode"]) == len(expected)
    assert [row["summary"] for row in payload["history"]] == [row["summary"] for row in agent.history]
    for row, expected_row in zip(payload["episode"], expected):
        for key in ("goal", "action_prompt", "action_output", "summary_prompt", "summary", "top_app_package_name", "target_element", "ranker_usage"):
            assert row[key] == expected_row[key], key
        assert row["before_ui_elements"] == tuple(expected_row["ui_elements"])
        converted = expected_row["converted_action"]
        assert row["converted_action"] == (dataclasses.asdict(converted) if dataclasses.is_dataclass(converted) else converted)
        coordinates = expected_row["actual_action_coordinates"]
        assert row["actual_action_coordinates"] == (tuple(coordinates) if coordinates else None)
        for key in ("raw_screenshot", "before_screenshot", "before_screenshot_with_som", "after_screenshot", "after_screenshot_with_som"):
            if expected_row[key] is not None:
                with Image.open(row[key]) as image:
                    np.testing.assert_array_equal(np.array(image), expected_row[key])
    last_action = expected[-1]["converted_action"] if expected else None
    done = bool(dataclasses.is_dataclass(last_action) and last_action.action_type == "status")
    expected_status = RunStatus.STEP_LIMIT if not done else RunStatus.FAILURE if last_action.goal_status == "infeasible" else RunStatus.SUCCESS
    assert actual.status is expected_status, actual.error
    assert payload["benchmark_evaluated"] is False
    evidence = (context.artifacts.namespace / "guiexplorer-episode.json").read_text()
    assert "private-response-sentinel" not in evidence
    return actual, payload, model, device, rag


@pytest.mark.fake_device_integration
def test_complete_online_matches_official_source(tmp_path):
    """Compare full ranking, dual-image decisions, source execution and summaries.

    Args:
        tmp_path: Isolated artifact directory.
    Returns:
        None.
    """
    assert_parity(tmp_path, [CLICK, GUIExplorerReply("Opened target settings."), COMPLETE])


@pytest.mark.parametrize("action", [
    {"action_type": "click", "index": 0}, {"action_type": "click", "x": 20, "y": 30},
    {"action_type": "double_tap", "index": 2}, {"action_type": "long_press", "index": 2},
    {"action_type": "input_text", "index": 2, "text": "hello"},
    {"action_type": "input_text", "text": ""},
    {"action_type": "scroll", "index": 0, "direction": "up"},
    {"action_type": "scroll", "index": 2, "direction": "down"},
    {"action_type": "swipe", "direction": "left"},
    {"action_type": "open_app", "app_name": "settings"},
    {"action_type": "open_app", "app_name": "browser"},
    {"action_type": "open_app", "app_name": "unmapped application"},
    {"action_type": "navigate_home"}, {"action_type": "navigate_back"},
    {"action_type": "keyboard_enter"}, {"action_type": "wait"},
    {"action_type": "answer", "text": "Here is the information"}, {"action_type": "unknown"},
])
def test_original_action_dispatch(tmp_path, action):
    """Exercise the actual source dispatcher for each advertised action family.

    Args:
        tmp_path: Isolated artifact directory.
        action: Original action JSON.
    Returns:
        None.
    """
    assert_parity(tmp_path, [decision(action), GUIExplorerReply("Step observed."), COMPLETE])


@pytest.mark.parametrize("reply", [
    GUIExplorerReply("wrong format"), GUIExplorerReply("Reasoning: x\nAction: {broken}"),
    GUIExplorerReply(""), GUIExplorerReply('Reason: x\nAction: {"action_type":"wait"}'),
    decision({"action_type": "not_supported"}), decision({"action_type": "click", "index": 999}),
    decision({"action_type": "scroll", "direction": "wrong"}),
])
def test_parse_feedback_is_a_new_round(tmp_path, reply):
    """Keep original feedback/history instead of resampling inside a component.

    Args:
        tmp_path: Isolated artifacts.
        reply: External malformed response.
    Returns:
        None.
    """
    assert_parity(tmp_path, [reply, COMPLETE], max_rounds=2)


@pytest.mark.parametrize("action", [
    {"action_type": "status", "goal_status": "infeasible"},
    {"action_type": "status"}, {"action_type": "status", "goal_status": "other"},
])
def test_original_permissive_termination(tmp_path, action):
    """Preserve complete/infeasible stop semantics without inventing Benchmark evidence.

    Args:
        tmp_path: Isolated artifacts.
        action: Source terminal JSON.
    Returns:
        None.
    """
    assert_parity(tmp_path, [decision(action)])


@pytest.mark.parametrize("action", [{"action_type": "click", "index": -1}, {"action_type": "click"}, {"action_type": "input_text", "text": "hello"}])
def test_execution_error_skips_history(tmp_path, action):
    """Keep original target indexing and missing-parameter execution-error behavior.

    Args:
        tmp_path: Isolated artifacts.
        action: Source action that fails in execution.
    Returns:
        None.
    """
    assert_parity(tmp_path, [decision(action), COMPLETE])


def test_device_exception_skips_summary(tmp_path):
    """A real source execution guard omits both summary call and history write.

    Args:
        tmp_path: Isolated artifacts.
    Returns:
        None.
    """
    assert_parity(tmp_path, [CLICK, COMPLETE], fail_click=True)


@pytest.mark.parametrize("summary", [GUIExplorerReply("error", False), GUIExplorerReply("")])
def test_summary_response_presence(tmp_path, summary):
    """Distinguish absent summary responses from successful empty summaries.

    Args:
        tmp_path: Isolated artifacts.
        summary: Original external response fact.
    Returns:
        None.
    """
    assert_parity(tmp_path, [CLICK, summary, COMPLETE])


def test_missing_action_response_is_fatal(tmp_path):
    """Source action transport failure terminates the run instead of becoming feedback.

    Args:
        tmp_path: Isolated artifacts.
    Returns:
        None.
    """
    assert_parity(tmp_path, [GUIExplorerReply("error", False)])


@pytest.mark.parametrize("orientation", [0, 1, 2, 3])
def test_original_geometry_and_crop_coordinates(tmp_path, orientation):
    """Compare raw drawing, crop and summary pixels through all source rotations.

    Args:
        tmp_path: Isolated artifacts.
        orientation: Source rotation fixture.
    Returns:
        None.
    """
    assert_parity(tmp_path, [CLICK, GUIExplorerReply("done"), COMPLETE], orientation=orientation)


@pytest.mark.parametrize("results,comparison", [([], "2"), ([[]], "1"), ([[{"knowledge": "only"}]], "2"),
    ([[{"knowledge": "A"}], [{"knowledge": "B"}]], "I prefer 2"),
    ([[{"knowledge": "A"}], [{"knowledge": "B"}]], "ambiguous")])
def test_rag_and_permissive_pairwise_ranker(tmp_path, results, comparison):
    """Keep short/empty batch zip, original comparisons and all knowledge entries.

    Args:
        tmp_path: Isolated artifacts.
        results: Original batch response.
        comparison: Original model ranking text.
    Returns:
        None.
    """
    assert_parity(tmp_path, [COMPLETE], results=results, comparison=comparison, top_k=3, threshold=0.75)


@pytest.mark.parametrize("rounds", [0, 1, 30])
def test_round_budget_and_final_history_flush(tmp_path, rounds):
    """Exercise zero-round side-effect freedom and complete 30-round shared history.

    Args:
        tmp_path: Isolated artifacts.
        rounds: Source step budget.
    Returns:
        None.
    """
    assert_parity(tmp_path, [GUIExplorerReply("wrong format")] * rounds, max_rounds=rounds)


def test_actual_yaml_runs_the_complete_online_flow(tmp_path):
    """Execute the actual concise YAML rather than a separately tested topology.

    Args:
        tmp_path: Isolated artifacts.
    Returns:
        None.
    """
    loaded = load_graph_yaml(ROOT / "examples/graphs/guiexplorer_online.yaml")
    assert loaded.is_success
    assert loaded.graph.canonical_hash() == build_guiexplorer_graph().canonical_hash()
    assert_parity(tmp_path, [CLICK, GUIExplorerReply("done"), COMPLETE], max_rounds=30, graph=loaded.graph)


@pytest.mark.parametrize("action", [{"action_type": "click", "index": -999}, {"action_type": "answer"}])
def test_source_errors_outside_execution_guard_are_fatal(tmp_path, action):
    """Keep source indexing/answer errors outside the recoverable execution boundary.

    Args:
        tmp_path: Isolated artifacts.
        action: Source input failing before execution.
    Returns:
        None.
    """
    assert_parity(tmp_path, [decision(action)])


def test_one_compiled_graph_keeps_run_histories_isolated(tmp_path):
    """Reuse a compiled definition twice without retaining another episode's Memory.

    Args:
        tmp_path: Isolated artifact root.
    Returns:
        None.
    """
    model = Model([CLICK, GUIExplorerReply("first episode"), COMPLETE,
                   CLICK, GUIExplorerReply("second episode"), COMPLETE])
    agent = compile_agent(build_guiexplorer_graph(max_rounds=3), dependencies={"llm": model, "retrieval": Retrieval()})
    payloads = []
    for _ in range(2):
        device, context = Device(), RuntimeContext(max_steps=4)
        result = agent.run(GOAL, AgentRunConfig(artifact_root=tmp_path, max_steps=4, include_ui_tree=False),
            device=GUIExplorerEnvironment(device, sleep=device.sleep), runtime=context)
        assert result.status is RunStatus.SUCCESS, result.error
        payloads.append(context.state.last_action_result.metadata["guiexplorer"])
    assert model.calls[0][0] == model.calls[3][0]
    assert all(len(payload["history"]) == 2 for payload in payloads)
    assert "first episode" not in json.dumps(payloads[1])
