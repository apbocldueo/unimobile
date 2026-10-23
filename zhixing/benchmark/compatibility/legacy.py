"""Legacy Benchmark evaluator compatibility boundary."""

from __future__ import annotations

from typing import Any

from zhixing.components import EvaluationResultV2, EvaluationStatus, EvaluationUsage
from zhixing.core.benchmark.protocol import EvalResult


def build_legacy_evaluator_context(
    *,
    task_instance: Any,
    run_result: Any,
    artifact_refs: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build the explicit read-only-shaped context expected by legacy leaves.

    Args:
        task_instance (Any): Materialized TaskInstance.
        run_result (Any): Typed Agent RunResult or None.
        artifact_refs (tuple[str, ...]): Stable artifact references.

    Raises:
        None.

    Returns:
        dict[str, Any]: Compatibility context without AgentRunner state.
    """
    params = {
        **dict(getattr(task_instance, "generated_params", {})),
        "id": getattr(task_instance, "task_id", ""),
        "app": getattr(task_instance, "app", None),
        "instruction": getattr(task_instance, "instruction", ""),
        "ground_truth": getattr(task_instance, "ground_truth", None),
    }
    trajectory: list[dict[str, Any]] = []
    if run_result is not None:
        state = getattr(run_result, "state", None)
        for observation in getattr(state, "observation_history", ()):
            trajectory.append(
                {
                    "kind": "observation",
                    "value": {
                        "sequence": getattr(observation, "sequence", 0),
                        "interaction_step": getattr(
                            observation,
                            "interaction_step",
                            0,
                        ),
                        "screenshot_artifact": getattr(
                            observation,
                            "screenshot_artifact",
                            "",
                        ),
                        "ui_artifact": getattr(
                            observation,
                            "ui_artifact",
                            None,
                        ),
                    },
                }
            )
        for event in getattr(run_result, "events", ()):
            trajectory.append(
                {"kind": "event", "value": event.to_safe_dict()}
            )
        for action in getattr(run_result, "action_results", ()):
            trajectory.append(
                {"kind": "action", "value": action.to_safe_dict()}
            )
    return {
        "task_params": params,
        "trajectory": tuple(trajectory),
        "run_result": run_result,
        "artifacts": tuple(artifact_refs),
    }


def normalize_evaluation_result(
    value: Any,
    *,
    evaluator_id: str,
    duration_ms: float,
) -> EvaluationResultV2:
    """Normalize a supported evaluator output into the canonical V2 result.

    Args:
        value (Any): V2, legacy EvalResult, or exact boolean output.
        evaluator_id (str): Stable logical evaluator identity.
        duration_ms (float): Measured invocation duration.

    Raises:
        TypeError: The evaluator returned an unsupported output shape.

    Returns:
        EvaluationResultV2: Canonical evaluator result without invented evidence.
    """
    if isinstance(value, EvaluationResultV2):
        return value
    if isinstance(value, EvalResult):
        token = float(value.token)
        return EvaluationResultV2(
            evaluator_id=evaluator_id,
            status=EvaluationStatus.COMPLETED,
            passed=bool(value.is_pass),
            score=1.0 if value.is_pass else 0.0,
            reason=str(value.reason),
            duration_ms=duration_ms,
            usage=EvaluationUsage(),
            evidence=(),
            metadata={"legacy_result": True, "legacy_token_value": token},
        )
    if type(value) is bool:
        return EvaluationResultV2(
            evaluator_id=evaluator_id,
            status=EvaluationStatus.COMPLETED,
            passed=value,
            score=1.0 if value else 0.0,
            duration_ms=duration_ms,
            evidence=(),
            metadata={"legacy_boolean": True},
        )
    raise TypeError(
        "evaluator must return EvaluationResultV2, EvalResult, or an exact bool"
    )


__all__ = ["build_legacy_evaluator_context", "normalize_evaluation_result"]
