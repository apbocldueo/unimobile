"""Structured Evaluator Tree runner that preserves leaf-level evidence."""

from __future__ import annotations

import time
from dataclasses import dataclass
import math
from typing import Any, Mapping

from zhixing.benchmark.compatibility import normalize_evaluation_result

from .resolver import BenchmarkComponentResolver
from .models import BenchmarkStageStatus, EvaluationNodeResult


@dataclass(frozen=True)
class PreparedEvaluatorNode:
    """One prepared composite or leaf with a stable logical path."""

    path: str
    name: str
    instance: Any = None
    logic: str = ""
    min_passed: int | None = None
    min_ratio: float | None = None
    pass_threshold: float | None = None
    weights: tuple[float, ...] = ()
    children: tuple["PreparedEvaluatorNode", ...] = ()


def prepare_evaluator_tree(
    config: Mapping[str, Any],
    *,
    resolver: BenchmarkComponentResolver,
    device: Any,
    path: str = "root",
) -> PreparedEvaluatorNode:
    """Resolve every evaluator leaf before any pre-hook side effect.

    Args:
        config (Mapping[str, Any]): Canonical Evaluator Tree definition.
        resolver (BenchmarkComponentResolver): Explicit component resolver.
        device (Any): Shared device session.
        path (str): Stable logical node path.

    Raises:
        ValueError: Tree definition or one leaf is invalid.

    Returns:
        PreparedEvaluatorNode: Fully prepared immutable tree.
    """
    name = str(config.get("name", "")).strip()
    params = config.get("params")
    if not name or not isinstance(params, Mapping):
        raise ValueError("Evaluator node requires name and params")
    if name in {"composite", "eval_composite"}:
        logic = str(params.get("logic", "")).upper()
        if logic not in {"AND", "OR", "SEQUENCE", "THRESHOLD", "WEIGHTED"}:
            raise ValueError(
                "Evaluator composite logic must be AND, OR, SEQUENCE, "
                "THRESHOLD, or WEIGHTED"
            )
        rules = params.get("rules")
        if not isinstance(rules, list) or not rules:
            raise ValueError("Evaluator composite requires non-empty rules")
        raw_weights = params.get("weights")
        weights = (
            tuple(float(value) for value in raw_weights)
            if isinstance(raw_weights, list)
            else ()
        )
        return PreparedEvaluatorNode(
            path=path,
            name=name,
            logic=logic,
            min_passed=(
                int(params["min_passed"])
                if params.get("min_passed") is not None
                else None
            ),
            min_ratio=(
                float(params["min_ratio"])
                if params.get("min_ratio") is not None
                else None
            ),
            pass_threshold=(
                float(params["pass_threshold"])
                if params.get("pass_threshold") is not None
                else None
            ),
            weights=weights,
            children=tuple(
                prepare_evaluator_tree(
                    item,
                    resolver=resolver,
                    device=device,
                    path=f"{path}/{index}",
                )
                for index, item in enumerate(rules)
            ),
        )
    evaluator_class = resolver.resolve_evaluator(config)
    return PreparedEvaluatorNode(
        path=path,
        name=f"{name}:{params.get('method', '')}",
        instance=evaluator_class(dict(params), device),
    )


def run_evaluator_pre_hooks(
    node: PreparedEvaluatorNode,
    context: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    """Run every leaf pre-hook on the same prepared instances used later.

    Args:
        node (PreparedEvaluatorNode): Prepared tree.
        context (Mapping[str, Any]): Legacy-compatible read view.

    Raises:
        Exception: A leaf pre-hook fails.

    Returns:
        tuple[dict[str, Any], ...]: Safe leaf path evidence.
    """
    if node.children:
        evidence: list[dict[str, Any]] = []
        for child in node.children:
            evidence.extend(run_evaluator_pre_hooks(child, context))
        return tuple(evidence)
    started = time.perf_counter()
    node.instance.pre_evaluate(dict(context))
    return (
        {
            "path": node.path,
            "name": node.name,
            "duration_ms": (time.perf_counter() - started) * 1000,
        },
    )


def _skipped_tree(node: PreparedEvaluatorNode, reason: str) -> EvaluationNodeResult:
    """Create an explicit recursively skipped evaluation branch.

    Args:
        node (PreparedEvaluatorNode): Unexecuted node.
        reason (str): Short-circuit reason.

    Raises:
        None.

    Returns:
        EvaluationNodeResult: Skipped branch.
    """
    return EvaluationNodeResult(
        path=node.path,
        name=node.logic or node.name,
        status=BenchmarkStageStatus.SKIPPED,
        is_pass=None,
        reason=reason,
        children=tuple(_skipped_tree(child, reason) for child in node.children),
        short_circuited=True,
    )


def evaluate_tree(
    node: PreparedEvaluatorNode,
    context: Mapping[str, Any],
) -> EvaluationNodeResult:
    """Evaluate a prepared tree with structured short-circuit evidence.

    Args:
        node (PreparedEvaluatorNode): Prepared evaluator tree.
        context (Mapping[str, Any]): Legacy-compatible run view.

    Raises:
        Exception: A leaf evaluator fails unexpectedly.

    Returns:
        EvaluationNodeResult: Complete structured result.
    """
    started = time.perf_counter()
    if not node.children:
        raw_result = node.instance.evaluate(dict(context))
        duration_ms = (time.perf_counter() - started) * 1000
        result = normalize_evaluation_result(
            raw_result,
            evaluator_id=node.name,
            duration_ms=duration_ms,
        )
        stage_status = {
            "completed": BenchmarkStageStatus.SUCCESS,
            "skipped": BenchmarkStageStatus.SKIPPED,
            "error": BenchmarkStageStatus.FAILURE,
            "invalid": BenchmarkStageStatus.FAILURE,
        }[result.status.value]
        legacy_token = result.metadata.get("legacy_token_value")
        return EvaluationNodeResult(
            path=node.path,
            name=node.name,
            status=stage_status,
            is_pass=result.passed,
            reason=result.reason,
            token=(
                float(legacy_token)
                if isinstance(legacy_token, (int, float))
                else None
            ),
            score=result.score,
            duration_ms=duration_ms,
            evidence={
                "items": [item.to_safe_dict() for item in result.evidence],
            },
            evaluator_result=result,
        )
    children: list[EvaluationNodeResult] = []
    decision = node.logic != "OR"
    for index, child in enumerate(node.children):
        child_result = evaluate_tree(child, context)
        children.append(child_result)
        stop = (
            node.logic in {"AND", "SEQUENCE"} and child_result.is_pass is False
        ) or (node.logic == "OR" and child_result.is_pass is True)
        if stop:
            decision = bool(child_result.is_pass)
            for remaining in node.children[index + 1 :]:
                children.append(
                    _skipped_tree(
                        remaining,
                        f"{node.logic} short-circuited at {child.path}",
                    )
                )
            break
    else:
        if node.logic in {"AND", "SEQUENCE"}:
            decision = all(item.is_pass is True for item in children)
        elif node.logic == "OR":
            decision = any(item.is_pass is True for item in children)
    aggregation: dict[str, Any] = {}
    score: float | None = None
    completed_children = [
        item
        for item in children
        if item.status is BenchmarkStageStatus.SUCCESS and item.is_pass is not None
    ]
    if node.logic == "THRESHOLD":
        if len(completed_children) != len(children):
            decision = False
        passed_count = sum(item.is_pass is True for item in completed_children)
        eligible_count = len(completed_children)
        if node.min_passed is not None:
            decision = eligible_count == len(children) and passed_count >= node.min_passed
            threshold: int | float = node.min_passed
            mode = "min_passed"
        else:
            ratio = passed_count / eligible_count if eligible_count else 0.0
            decision = (
                eligible_count == len(children)
                and node.min_ratio is not None
                and ratio >= node.min_ratio
            )
            threshold = node.min_ratio if node.min_ratio is not None else 0.0
            mode = "min_ratio"
        score = passed_count / eligible_count if eligible_count else None
        aggregation = {
            "mode": mode,
            "threshold": threshold,
            "passed_count": passed_count,
            "eligible_count": eligible_count,
        }
    elif node.logic == "WEIGHTED":
        if len(node.weights) != len(children):
            raise ValueError("WEIGHTED node requires one weight per child")
        child_scores = [
            (
                item.score
                if item.score is not None
                else (1.0 if item.is_pass is True else 0.0)
            )
            for item in children
        ]
        if any(not math.isfinite(value) for value in child_scores):
            raise ValueError("WEIGHTED child score must be finite")
        total_weight = sum(node.weights)
        contributions = [
            value * weight / total_weight
            for value, weight in zip(child_scores, node.weights, strict=True)
        ]
        score = sum(contributions)
        decision = (
            len(completed_children) == len(children)
            and node.pass_threshold is not None
            and score >= node.pass_threshold
        )
        aggregation = {
            "mode": "weighted",
            "pass_threshold": node.pass_threshold,
            "weights": list(node.weights),
            "child_scores": child_scores,
            "contributions": contributions,
        }
    elif node.logic in {"AND", "OR", "SEQUENCE"}:
        score = 1.0 if decision else 0.0
    token_values = [item.token for item in children if item.token is not None]
    composite_status = (
        BenchmarkStageStatus.SUCCESS
        if len(completed_children)
        == len(
            [
                item
                for item in children
                if item.status is not BenchmarkStageStatus.SKIPPED
            ]
        )
        else BenchmarkStageStatus.FAILURE
    )
    return EvaluationNodeResult(
        path=node.path,
        name=node.logic,
        status=composite_status,
        is_pass=decision,
        reason=f"{node.logic} evaluated {len(children)} branch(es)",
        token=sum(token_values) if token_values else 0.0,
        score=score,
        duration_ms=(time.perf_counter() - started) * 1000,
        aggregation=aggregation,
        children=tuple(children),
        short_circuited=any(
            item.status is BenchmarkStageStatus.SKIPPED for item in children
        ),
    )
