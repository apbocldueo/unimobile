"""Bounded safe projection from Benchmark Core results to Studio TaskResults."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from zhixing.benchmark import BenchmarkTaskResult

from .benchmark_experiment_models import (
    StudioBenchmarkEvaluationV1,
    StudioBenchmarkTaskPhaseV1,
    StudioBenchmarkTaskResultV1,
    StudioBenchmarkTaskRunTerminalReason,
)
from .run_safety import (
    SanitizationPolicy,
    redact_text,
    sanitize_runtime_value,
)
from .evidence_origin import StudioExecutionEvidenceOriginV1


STUDIO_BENCHMARK_RESULT_MAX_BYTES = 256 * 1024
_RESULT_POLICY = SanitizationPolicy(
    max_depth=8,
    max_members=50,
    max_text=4000,
    max_total_text=96 * 1024,
)


def _safe_mapping(value: Any) -> tuple[dict[str, Any], tuple[str, ...]]:
    """Sanitize one result mapping and expose only transformation diagnostics.

    Args:
        value: Candidate Core result evidence.

    Raises:
        None.

    Returns:
        Safe mapping and non-sensitive diagnostic codes.
    """
    sanitized = sanitize_runtime_value(value, policy=_RESULT_POLICY)
    mapping = sanitized.value if isinstance(sanitized.value, dict) else {}
    diagnostics: list[str] = []
    if sanitized.redacted:
        diagnostics.append("benchmark.result.redacted")
    if sanitized.truncated:
        diagnostics.append("benchmark.result.truncated")
    if sanitized.excluded:
        diagnostics.append("benchmark.result.excluded")
    return mapping, tuple(diagnostics)


def _safe_text(
    value: Any,
    *,
    max_length: int,
) -> tuple[str, tuple[str, ...]]:
    """Redact and bound one Core-provided human-readable text field.

    Args:
        value: Candidate text-like runtime value.
        max_length: Largest safe returned character count.

    Raises:
        None.

    Returns:
        Safe text plus non-sensitive transformation diagnostics.
    """
    safe, redacted, truncated = redact_text(
        str(value),
        max_length=max_length,
    )
    diagnostics: list[str] = []
    if redacted:
        diagnostics.append("benchmark.result.redacted")
    if truncated:
        diagnostics.append("benchmark.result.truncated")
    return safe, tuple(diagnostics)


def _project_evaluation(
    value: Any,
    *,
    depth: int = 0,
) -> tuple[StudioBenchmarkEvaluationV1 | None, tuple[str, ...]]:
    """Project one bounded Evaluation Tree node recursively.

    Args:
        value: Optional Core Evaluation node.
        depth: Current bounded tree depth.

    Raises:
        ValueError: Required Evaluation fields violate the strict DTO.

    Returns:
        Optional projected node and transformation diagnostic codes.
    """
    if value is None:
        return None, ()
    if depth >= 8:
        return None, ("benchmark.result.evaluation_depth_truncated",)
    evidence, diagnostics = _safe_mapping(value.evidence)
    reason, reason_diagnostics = _safe_text(value.reason, max_length=1000)
    children: list[StudioBenchmarkEvaluationV1] = []
    collected = [*diagnostics, *reason_diagnostics]
    for child in tuple(value.children)[:50]:
        projected, child_diagnostics = _project_evaluation(
            child,
            depth=depth + 1,
        )
        if projected is not None:
            children.append(projected)
        collected.extend(child_diagnostics)
    if len(value.children) > 50:
        collected.append("benchmark.result.evaluation_children_truncated")
    return (
        StudioBenchmarkEvaluationV1(
            path=value.path,
            name=value.name,
            status=value.status,
            is_pass=value.is_pass,
            reason=reason,
            score=value.score,
            token=value.token,
            evidence=evidence,
            children=tuple(children),
        ),
        tuple(collected),
    )


def _encoded_size(value: StudioBenchmarkTaskResultV1) -> int:
    """Return deterministic UTF-8 JSON size for one normalized result.

    Args:
        value: Strict normalized result.

    Raises:
        TypeError: Result is unexpectedly not JSON compatible.
        ValueError: Result contains a non-finite number.

    Returns:
        Encoded JSON byte length.
    """
    payload = value.model_dump(mode="json", by_alias=True, exclude_none=True)
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    )


def project_benchmark_task_result(
    result: BenchmarkTaskResult,
    *,
    planned_task_run_id: str,
    agent_revision_id: str,
    schedule_order: int,
    service_terminal_reason: StudioBenchmarkTaskRunTerminalReason,
    evidence_origin: StudioExecutionEvidenceOriginV1 | None = None,
    max_bytes: int = STUDIO_BENCHMARK_RESULT_MAX_BYTES,
) -> tuple[StudioBenchmarkTaskResultV1, str]:
    """Create a safe bounded TaskResult without duplicating runtime events.

    Args:
        result: Complete in-memory Benchmark Core result.
        planned_task_run_id: Stable public TaskRun identity planned at create.
        agent_revision_id: Immutable Agent revision identity from the snapshot.
        schedule_order: Stable zero-based planned schedule position.
        service_terminal_reason: Service-level TaskRun termination fact.
        evidence_origin: Safe typed source evidence provenance.
        max_bytes: Maximum encoded inline result size.

    Raises:
        ValueError: Limit is invalid or required facts cannot fit.
        TypeError: Required result facts are not JSON compatible.

    Returns:
        Normalized TaskResult and canonical content fingerprint.
    """
    if max_bytes < 4096:
        raise ValueError("Benchmark TaskResult limit must be at least 4096 bytes")
    diagnostics: list[str] = []
    phases: list[StudioBenchmarkTaskPhaseV1] = []
    logical_refs: list[str] = []
    for stage in result.stages[:32]:
        evidence, stage_diagnostics = _safe_mapping(stage.evidence)
        diagnostics.extend(stage_diagnostics)
        message, message_diagnostics = _safe_text(
            stage.message,
            max_length=1000,
        )
        diagnostics.extend(message_diagnostics)
        safe_ref_values: list[str] = []
        for reference in stage.artifact_refs[:50]:
            if not reference or str(reference).startswith(("/", "\\\\")):
                diagnostics.append("benchmark.result.redacted")
                continue
            safe_reference, reference_diagnostics = _safe_text(
                reference,
                max_length=512,
            )
            diagnostics.extend(reference_diagnostics)
            safe_ref_values.append(safe_reference)
        safe_refs = tuple(safe_ref_values)
        logical_refs.extend(safe_refs)
        phases.append(
            StudioBenchmarkTaskPhaseV1(
                phase=stage.phase,
                status=stage.status,
                duration_ms=max(0.0, stage.duration_ms),
                error_code=stage.error_code[:256],
                message=message,
                evidence=evidence,
                artifact_refs=safe_refs,
            )
        )
    if len(result.stages) > 32:
        diagnostics.append("benchmark.result.phases_truncated")
    evaluation, evaluation_diagnostics = _project_evaluation(result.evaluation)
    diagnostics.extend(evaluation_diagnostics)
    usage, usage_diagnostics = _safe_mapping(result.usage)
    diagnostics.extend(usage_diagnostics)
    agent_status = result.agent_result.status if result.agent_result else None
    agent_run_id = result.agent_result.run_id if result.agent_result else None
    if result.artifact_namespace and not result.artifact_namespace.startswith(
        ("/", "\\\\")
    ):
        safe_namespace, namespace_diagnostics = _safe_text(
            result.artifact_namespace,
            max_length=512,
        )
        logical_refs.append(safe_namespace)
        diagnostics.extend(namespace_diagnostics)
    elif result.artifact_namespace:
        diagnostics.append("benchmark.result.redacted")
    fairness_warnings: list[str] = []
    for warning in result.fairness_warnings[:50]:
        safe_warning, warning_diagnostics = _safe_text(
            warning,
            max_length=512,
        )
        fairness_warnings.append(safe_warning)
        diagnostics.extend(warning_diagnostics)
    projected = StudioBenchmarkTaskResultV1(
        planned_task_run_id=planned_task_run_id,
        core_task_run_id=result.task_run_id,
        agent_run_id=agent_run_id,
        agent_id=result.agent_id,
        agent_revision_id=agent_revision_id,
        task_id=result.task_id,
        repeat=result.repeat,
        schedule_order=schedule_order,
        service_terminal_reason=service_terminal_reason,
        agent_graph_identity=result.agent_graph_identity,
        benchmark_plan_identity=result.benchmark_plan_identity,
        experiment_protocol_identity=result.experiment_protocol_identity,
        task_instance_identity=result.task_instance_identity,
        agent_status=agent_status,
        benchmark_outcome=result.outcome,
        phases=tuple(phases),
        evaluation=evaluation,
        usage=usage,
        fairness_warnings=tuple(fairness_warnings),
        logical_artifact_refs=tuple(dict.fromkeys(logical_refs))[:100],
        diagnostics=tuple(sorted(set(diagnostics)))[:100],
        evidence_origin=evidence_origin or StudioExecutionEvidenceOriginV1(),
    )
    if _encoded_size(projected) > max_bytes:
        projected = projected.model_copy(
            update={
                "phases": tuple(
                    phase.model_copy(
                        update={
                            "evidence": {},
                            "message": phase.message[:256],
                        }
                    )
                    for phase in projected.phases
                ),
                "evaluation": (
                    projected.evaluation.model_copy(
                        update={"evidence": {}, "children": ()}
                    )
                    if projected.evaluation is not None
                    else None
                ),
                "usage": {},
                "diagnostics": tuple(
                    sorted(
                        {
                            *projected.diagnostics,
                            "benchmark.result.optional_evidence_not_captured",
                        }
                    )
                ),
            }
        )
        projected = StudioBenchmarkTaskResultV1.model_validate(
            projected.model_dump()
        )
    if _encoded_size(projected) > max_bytes:
        raise ValueError("required Benchmark TaskResult facts exceed inline limit")
    encoded = json.dumps(
        projected.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    fingerprint = "sha256:" + hashlib.sha256(encoded).hexdigest()
    return projected, fingerprint


__all__ = [
    "STUDIO_BENCHMARK_RESULT_MAX_BYTES",
    "project_benchmark_task_result",
]
