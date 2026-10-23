"""Causal Benchmark and nested AgentGraph trajectory construction."""

from __future__ import annotations

from typing import Any

from ..runtime.models import BenchmarkTaskResult
from .safety import safe_export

TRAJECTORY_SCHEMA_VERSION = "1.0"


def build_task_trajectory(
    result: BenchmarkTaskResult,
) -> tuple[dict[str, Any], ...]:
    """Build phase-ordered records with nested Graph evidence.

    Args:
        result (BenchmarkTaskResult): Immutable task execution facts.

    Raises:
        None.

    Returns:
        tuple[dict[str, Any], ...]: Causally ordered safe records.
    """
    events_by_phase: dict[str, list[dict[str, Any]]] = {}
    for event in result.lifecycle_events:
        events_by_phase.setdefault(event.phase, []).append(event.to_safe_dict())
    records: list[dict[str, Any]] = []
    for index, stage in enumerate(result.stages):
        payload: dict[str, Any] = {
            "schema_version": TRAJECTORY_SCHEMA_VERSION,
            "record_index": index,
            "task_run_id": result.task_run_id,
            "phase": stage.phase,
            "kind": "benchmark_phase",
            "stage": stage.to_safe_dict(),
            "lifecycle_events": sorted(
                events_by_phase.get(stage.phase, []),
                key=lambda item: int(item.get("sequence", 0)),
            ),
        }
        if stage.phase == "agent" and result.agent_result is not None:
            state = result.agent_result.state
            payload["agent_graph"] = {
                "run_id": result.agent_result.run_id,
                "events": [
                    event.to_safe_dict()
                    for event in sorted(
                        result.agent_result.events,
                        key=lambda item: item.sequence,
                    )
                ],
                "observations": [
                    {
                        "sequence": observation.sequence,
                        "interaction_step": observation.interaction_step,
                        "screenshot_artifact": observation.screenshot_artifact,
                        "ui_artifact": observation.ui_artifact,
                    }
                    for observation in sorted(
                        state.observation_history,
                        key=lambda item: (item.sequence, item.interaction_step),
                    )
                ],
                "actions": [
                    action.to_safe_dict()
                    for action in result.agent_result.action_results
                ],
            }
        records.append(safe_export(payload))
    return tuple(records)


__all__ = ["TRAJECTORY_SCHEMA_VERSION", "build_task_trajectory"]
