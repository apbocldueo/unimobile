"""Side-effect-free Benchmark experiment planning."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

from zhixing.graph import compile_agent_yaml

from ..compiler import BenchmarkValidationLevel, compile_benchmark_package
from ..models import BenchmarkPlan, ExperimentProtocol
from ..runtime.materializer import build_schedule


@dataclass(frozen=True)
class BenchmarkDryRunReport:
    """Definition-only experiment schedule and validation report."""

    ok: bool
    plan_identity: str = ""
    protocol_identity: str = ""
    agent_graph_identities: Mapping[str, str] = field(default_factory=dict)
    schedule: tuple[Mapping[str, Any], ...] = ()
    budget: Mapping[str, Any] = field(default_factory=dict)
    output_layout: Mapping[str, str] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    unverified_checks: tuple[str, ...] = ()
    diagnostics: tuple[Mapping[str, Any], ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the definition-only report.

        Returns:
            dict[str, Any]: Safe dry-run output.
        """
        return {
            "ok": self.ok,
            "mode": "side-effect-free-dry-run",
            "plan_identity": self.plan_identity,
            "protocol_identity": self.protocol_identity,
            "agent_graph_identities": dict(self.agent_graph_identities),
            "schedule": [dict(item) for item in self.schedule],
            "budget": dict(self.budget),
            "output_layout": dict(self.output_layout),
            "warnings": list(self.warnings),
            "unverified_checks": list(self.unverified_checks),
            "diagnostics": [dict(item) for item in self.diagnostics],
        }


def dry_run_benchmark(
    package_root: Path,
    *,
    agent_paths: Mapping[str, Path] | None = None,
    split: str | None = None,
    task_ids: tuple[str, ...] = (),
) -> BenchmarkDryRunReport:
    """Compile Benchmark and Agent definitions and derive a schedule only.

    Args:
        package_root (Path): Local Benchmark Package directory.
        agent_paths (Mapping[str, Path] | None): Named Agent YAML definitions.
        split (str | None): Optional Package split.
        task_ids (tuple[str, ...]): Optional task selection.

    Raises:
        None: Definition failures are returned as diagnostics.

    Returns:
        BenchmarkDryRunReport: Side-effect-free plan and schedule evidence.
    """
    compiled = compile_benchmark_package(
        package_root,
        split=split,
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    if compiled.plan is None or compiled.protocol is None:
        return BenchmarkDryRunReport(
            ok=False,
            diagnostics=tuple(
                item.to_safe_dict() for item in compiled.diagnostics
            ),
        )
    graph_identities: dict[str, str] = {}
    graph_diagnostics: list[dict[str, Any]] = []
    for name, path in sorted((agent_paths or {}).items()):
        result = compile_agent_yaml(Path(path))
        if result.graph is None or not result.is_success:
            graph_diagnostics.extend(
                {
                    "source": name,
                    "code": item.code,
                    "path": list(item.path),
                    "message": item.message,
                }
                for item in result.diagnostics
            )
            continue
        graph_identities[name] = result.graph.canonical_hash()
    if graph_diagnostics:
        return BenchmarkDryRunReport(
            ok=False,
            plan_identity=compiled.plan.canonical_hash(),
            protocol_identity=compiled.protocol.canonical_hash(),
            agent_graph_identities=graph_identities,
            diagnostics=tuple(graph_diagnostics),
        )
    return project_benchmark_dry_run(
        compiled.plan,
        compiled.protocol,
        graph_identities,
        task_ids=task_ids,
        diagnostics=tuple(
            item.to_safe_dict() for item in compiled.diagnostics
        ),
    )


def project_benchmark_dry_run(
    plan: BenchmarkPlan,
    protocol: ExperimentProtocol,
    agent_graph_identities: Mapping[str, str],
    *,
    task_ids: tuple[str, ...] = (),
    diagnostics: tuple[Mapping[str, Any], ...] = (),
    max_schedule_entries: int | None = None,
) -> BenchmarkDryRunReport:
    """Project a complete deterministic schedule from verified definitions.

    This helper is deliberately pure: it never materializes tasks, constructs
    plugins, resolves secrets, connects devices, calls models, or writes output.

    Args:
        plan: Compiled immutable Benchmark semantics.
        protocol: Parsed fairness and execution-budget definition.
        agent_graph_identities: Verified Agent names to canonical graph hashes.
        task_ids: Optional explicit task selection.
        diagnostics: Existing non-error compilation diagnostics to preserve.
        max_schedule_entries: Optional inclusive output-cardinality bound.

    Raises:
        ValueError: Schedule bound is not positive when supplied.

    Returns:
        Complete dry-run projection, or an empty failed result for selection or
        cardinality errors.
    """
    if max_schedule_entries is not None and max_schedule_entries <= 0:
        raise ValueError("max_schedule_entries must be positive")
    available = {task.id for task in plan.tasks}
    selected = task_ids or tuple(sorted(available))
    missing = sorted(set(selected) - available)
    if missing:
        return BenchmarkDryRunReport(
            ok=False,
            plan_identity=plan.canonical_hash(),
            protocol_identity=protocol.canonical_hash(),
            agent_graph_identities=dict(agent_graph_identities),
            diagnostics=(
                {
                    "code": "benchmark.dry_run.task_not_found",
                    "message": "Requested Benchmark task does not exist.",
                    "source": "task-selection",
                    "path": ["task_ids"],
                    "task_id": missing[0],
                },
            ),
        )
    agent_ids = tuple(agent_graph_identities) or ("unbound-agent",)
    cardinality = len(selected) * len(set(agent_ids)) * protocol.repeats
    if max_schedule_entries is not None and cardinality > max_schedule_entries:
        return BenchmarkDryRunReport(
            ok=False,
            plan_identity=plan.canonical_hash(),
            protocol_identity=protocol.canonical_hash(),
            agent_graph_identities=dict(agent_graph_identities),
            diagnostics=(
                {
                    "code": "benchmark.dry_run.schedule_too_large",
                    "message": "Dry-run schedule exceeds its safe output limit.",
                    "source": "schedule",
                    "path": ["schedule"],
                },
            ),
        )
    schedule = build_schedule(
        plan,
        protocol,
        agent_ids,
        task_ids=tuple(selected),
    )
    dynamic = any(
        task.type == "dynamic"
        for task in plan.tasks
        if task.id in set(selected)
    )
    return BenchmarkDryRunReport(
        ok=True,
        plan_identity=plan.canonical_hash(),
        protocol_identity=protocol.canonical_hash(),
        agent_graph_identities=dict(agent_graph_identities),
        schedule=tuple(
            {
                "repeat": item.repeat,
                "task_id": item.task_id,
                "agent_id": item.agent_id,
                "seed": item.seed,
                "shared_instance_key": item.shared_instance_key,
            }
            for item in schedule
        ),
        budget=protocol.budget.model_dump(mode="json"),
        output_layout={
            "experiment_report": "<artifact-root>/<experiment-id>/experiment-report.json",
            "run_report": "<artifact-root>/<experiment-id>/runs/<task-run-id>/run-report.json",
            "trajectory": "<artifact-root>/<experiment-id>/runs/<task-run-id>/trajectory.jsonl",
            "bundle": "<artifact-root>/<experiment-id>/trajectory-bundle.zip",
        },
        warnings=tuple(protocol.fairness_warnings),
        unverified_checks=(
            ("dynamic-task-materialization",) if dynamic else ()
        ),
        diagnostics=diagnostics,
    )


__all__ = [
    "BenchmarkDryRunReport",
    "dry_run_benchmark",
    "project_benchmark_dry_run",
]
