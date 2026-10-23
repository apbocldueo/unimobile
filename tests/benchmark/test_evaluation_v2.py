"""Evaluation Result V2 and composite-tree contract tests."""

from __future__ import annotations

from typing import Any, Mapping

import pytest
from pydantic import ValidationError

from zhixing.benchmark.compatibility import normalize_evaluation_result
from zhixing.benchmark.runtime import BenchmarkStageStatus
from zhixing.benchmark.runtime.evaluator import evaluate_tree, prepare_evaluator_tree
from zhixing.components import (
    EvalResult,
    EvaluationEvidence,
    EvaluationResultV2,
    EvaluationStatus,
)
from zhixing.config.contracts import BenchmarkTask


class _ConfiguredEvaluator:
    """Small evaluator implementation selected by a logical result value."""

    def __init__(self, params: Mapping[str, Any], device: Any) -> None:
        """Capture evaluator parameters without using the fake device.

        Args:
            params (Mapping[str, Any]): Leaf configuration.
            device (Any): Unused explicit device boundary.

        Raises:
            None.

        Returns:
            None.
        """
        del device
        self.params = dict(params)

    def evaluate(self, context: Mapping[str, Any]) -> EvalResult:
        """Return the configured legacy decision.

        Args:
            context (Mapping[str, Any]): Unused evaluator context.

        Raises:
            None.

        Returns:
            EvalResult: Deterministic legacy output.
        """
        del context
        passed = bool(self.params.get("passed"))
        return EvalResult(is_pass=passed, reason=f"passed={passed}")


class _Resolver:
    """Resolver fixture returning the deterministic evaluator."""

    def resolve_evaluator(self, config: Mapping[str, Any]) -> type[Any]:
        """Resolve every leaf to the deterministic evaluator fixture.

        Args:
            config (Mapping[str, Any]): Leaf declaration.

        Raises:
            None.

        Returns:
            type[Any]: Evaluator fixture class.
        """
        del config
        return _ConfiguredEvaluator


def _leaf(passed: bool) -> dict[str, Any]:
    """Build one canonical leaf declaration.

    Args:
        passed (bool): Deterministic decision.

    Raises:
        None.

    Returns:
        dict[str, Any]: Evaluator leaf mapping.
    """
    return {
        "name": "system",
        "params": {"method": "fixture", "passed": passed},
    }


def _task(evaluator: dict[str, Any]) -> dict[str, Any]:
    """Build the smallest valid BenchmarkTask mapping.

    Args:
        evaluator (dict[str, Any]): Evaluator declaration.

    Raises:
        None.

    Returns:
        dict[str, Any]: Task contract input.
    """
    return {
        "id": "evaluation-v2",
        "instruction": "evaluate",
        "type": "static",
        "task_initializer": {},
        "environment_initializer": [],
        "evaluator": evaluator,
    }


def test_v2_result_and_typed_evidence_serialize_safely() -> None:
    """Preserve supported evidence kinds and explicit unavailable usage."""
    result = EvaluationResultV2(
        evaluator_id="visual:fixture",
        status=EvaluationStatus.COMPLETED,
        passed=True,
        score=0.75,
        evidence=(
            EvaluationEvidence(
                kind="visual.image",
                artifact_ref="runs/example/screenshot.png",
                value={"confidence": 0.75},
            ),
            EvaluationEvidence(kind="custom.vendor.metric", value={"value": 3}),
        ),
    )
    payload = result.to_safe_dict()
    assert payload["score"] == 0.75
    assert payload["usage"]["availability"] == "unavailable"
    assert [item["kind"] for item in payload["evidence"]] == [
        "visual.image",
        "custom.vendor.metric",
    ]


def test_evidence_rejects_unsafe_artifact_reference() -> None:
    """Reject path traversal before evidence reaches a report writer."""
    with pytest.raises(ValueError, match="safe relative"):
        EvaluationEvidence(kind="artifact.file", artifact_ref="../secret.txt")


def test_legacy_normalization_is_explicit_and_rejects_truthy_objects() -> None:
    """Normalize documented shapes without relying on arbitrary truthiness."""
    normalized = normalize_evaluation_result(
        EvalResult(is_pass=False, reason="not found", token=2.0),
        evaluator_id="system:legacy",
        duration_ms=1.5,
    )
    assert normalized.passed is False
    assert normalized.score == 0.0
    assert normalized.evidence == ()
    assert normalized.metadata["legacy_token_value"] == 2.0
    with pytest.raises(TypeError, match="must return"):
        normalize_evaluation_result(
            object(),
            evaluator_id="system:invalid",
            duration_ms=0.0,
        )


def test_threshold_and_weighted_contract_validation() -> None:
    """Validate explicit threshold modes and finite positive weights."""
    threshold = BenchmarkTask.model_validate(
        _task(
            {
                "name": "composite",
                "params": {
                    "logic": "THRESHOLD",
                    "min_passed": 1,
                    "rules": [_leaf(True), _leaf(False)],
                },
            }
        )
    )
    assert threshold.evaluator.params.logic == "THRESHOLD"
    weighted = BenchmarkTask.model_validate(
        _task(
            {
                "name": "composite",
                "params": {
                    "logic": "WEIGHTED",
                    "pass_threshold": 0.6,
                    "weights": [3.0, 1.0],
                    "rules": [_leaf(True), _leaf(False)],
                },
            }
        )
    )
    assert weighted.evaluator.params.weights == [3.0, 1.0]
    with pytest.raises(ValidationError):
        BenchmarkTask.model_validate(
            _task(
                {
                    "name": "composite",
                    "params": {
                        "logic": "WEIGHTED",
                        "pass_threshold": 0.6,
                        "weights": [1.0],
                        "rules": [_leaf(True), _leaf(False)],
                    },
                }
            )
        )


def test_threshold_and_weighted_execution_preserve_all_children() -> None:
    """Compute explicit aggregate evidence without short-circuiting new logic."""
    resolver = _Resolver()
    threshold = prepare_evaluator_tree(
        {
            "name": "composite",
            "params": {
                "logic": "THRESHOLD",
                "min_passed": 1,
                "rules": [_leaf(True), _leaf(False)],
            },
        },
        resolver=resolver,
        device=object(),
    )
    threshold_result = evaluate_tree(threshold, {})
    assert threshold_result.is_pass is True
    assert len(threshold_result.children) == 2
    assert threshold_result.aggregation["passed_count"] == 1

    weighted = prepare_evaluator_tree(
        {
            "name": "composite",
            "params": {
                "logic": "WEIGHTED",
                "pass_threshold": 0.7,
                "weights": [3.0, 1.0],
                "rules": [_leaf(True), _leaf(False)],
            },
        },
        resolver=resolver,
        device=object(),
    )
    weighted_result = evaluate_tree(weighted, {})
    assert weighted_result.status is BenchmarkStageStatus.SUCCESS
    assert weighted_result.is_pass is True
    assert weighted_result.score == pytest.approx(0.75)
    assert weighted_result.aggregation["contributions"] == pytest.approx(
        [0.75, 0.0]
    )


def test_existing_and_logic_keeps_short_circuit_evidence() -> None:
    """Retain explicit SKIPPED branches for legacy composite behavior."""
    node = prepare_evaluator_tree(
        {
            "name": "composite",
            "params": {
                "logic": "AND",
                "rules": [_leaf(False), _leaf(True)],
            },
        },
        resolver=_Resolver(),
        device=object(),
    )
    result = evaluate_tree(node, {})
    assert result.is_pass is False
    assert result.children[1].status is BenchmarkStageStatus.SKIPPED
    assert result.short_circuited is True
