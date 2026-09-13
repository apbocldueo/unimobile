"""Pure cross-field validation for Agent and Benchmark contracts."""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, Sequence

from pydantic import ValidationError

from .agent import (
    AgentConfig,
    ModularStrategy,
    MultiAgentStrategy,
    ReflectionStrategy,
    UGroundStrategy,
)
from .benchmark import BenchmarkSuite, BenchmarkTask, CompositeEvaluator, LeafEvaluator
from .diagnostics import ValidationIssue


_PLACEHOLDER = re.compile(r"\$\{([^{}]+)\}")

# Built-in components whose current constructors require LLM injection. Registry
# validation extends this convention to third-party components by signature.
_LLM_REQUIRED_COMPONENTS = {
    "universal_reasoning",
    "universal_planner",
    "summary_memory",
    "llm_reflect_verifier",
    "uground_grounder",
}


def _pydantic_issues(exc: ValidationError, prefix: tuple[Any, ...]) -> list[ValidationIssue]:
    return [
        ValidationIssue(
            code="agent.strategy.invalid",
            path=prefix + tuple(error["loc"]),
            message=error["msg"],
        )
        for error in exc.errors(include_url=False)
    ]


def validate_agent_semantics(config: AgentConfig) -> tuple[ValidationIssue, ...]:
    issues: list[ValidationIssue] = []
    strategy_model = {
        "modular_agent": ModularStrategy,
        "reflection_agent": ReflectionStrategy,
        "multi_agent": MultiAgentStrategy,
        "uground_agent": UGroundStrategy,
    }.get(config.agent_type)

    parsed_strategy = None
    if strategy_model is not None:
        try:
            parsed_strategy = strategy_model.model_validate(config.agent.strategy)
        except ValidationError as exc:
            issues.extend(_pydantic_issues(exc, ("agent", "strategy")))

    components = config.agent.components
    if config.agent_type == "multi_agent":
        manager_each_step = getattr(parsed_strategy, "manager_each_step", True)
        if manager_each_step and components.planner is None:
            issues.append(
                ValidationIssue(
                    code="agent.strategy.planner_required",
                    path=("agent", "components", "planner"),
                    message="multi_agent with manager_each_step requires planner",
                )
            )
    if config.agent_type == "uground_agent" and components.grounder is None:
        issues.append(
            ValidationIssue(
                code="agent.strategy.grounder_required",
                path=("agent", "components", "grounder"),
                message="uground_agent requires grounder",
            )
        )

    default_llm = config.global_config.default_llm
    for role, index, component in components.iter_slots():
        if component.name not in _LLM_REQUIRED_COMPONENTS:
            continue
        if component.llm is None and default_llm is None:
            path: tuple[Any, ...] = ("agent", "components", role)
            if index is not None:
                path += (index,)
            issues.append(
                ValidationIssue(
                    code="agent.llm.required",
                    path=path + ("llm",),
                    message=f"component {component.name!r} requires local llm or global_config.default_llm",
                )
            )
    return tuple(issues)


def _walk_placeholders(value: Any, path: tuple[Any, ...]) -> Iterable[tuple[str, tuple[Any, ...]]]:
    if isinstance(value, str):
        for match in _PLACEHOLDER.finditer(value):
            yield match.group(1), path
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _walk_placeholders(item, path + (str(key),))
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for index, item in enumerate(value):
            yield from _walk_placeholders(item, path + (index,))


def _task_semantic_issues(
    task: BenchmarkTask,
    task_index: int,
    runtime_variables: frozenset[str],
) -> list[ValidationIssue]:
    """Validate initializer dependency and placeholder closure for one task.

    Args:
        task (BenchmarkTask): Parsed task contract.
        task_index (int): Source index used in diagnostics.
        runtime_variables (frozenset[str]): Explicit externally supplied names.

    Raises:
        None.

    Returns:
        list[ValidationIssue]: Deterministic semantic diagnostics.
    """
    issues: list[ValidationIssue] = []
    available = set(runtime_variables)
    used: set[str] = set()

    for name, call in task.task_initializer.items():
        for ref, ref_path in _walk_placeholders(call.params, ("task_initializer", name, "params")):
            used.add(ref)
            if ref not in available:
                issues.append(
                    ValidationIssue(
                        code="benchmark.placeholder.forward_or_missing",
                        path=(task_index,) + ref_path,
                        message=f"placeholder ${{{ref}}} is not produced by an earlier initializer",
                        task_id=task.id,
                    )
                )
        available.add(name)

    external_values = {
        "instruction": task.instruction,
        "environment_initializer": [item.model_dump(mode="python") for item in task.environment_initializer],
        "evaluator": task.evaluator.model_dump(mode="python"),
        "cleanup_initializer": [item.model_dump(mode="python") for item in task.cleanup_initializer],
    }
    for ref, ref_path in _walk_placeholders(external_values, ()):
        used.add(ref)
        if ref not in available:
            issues.append(
                ValidationIssue(
                    code="benchmark.placeholder.unresolved",
                    path=(task_index,) + ref_path,
                    message=f"placeholder ${{{ref}}} has no task initializer or runtime variable",
                    task_id=task.id,
                )
            )

    for name in task.task_initializer:
        if name not in used:
            issues.append(
                ValidationIssue(
                    code="benchmark.initializer.unused",
                    path=(task_index, "task_initializer", name),
                    message=f"initializer {name!r} is not referenced by the task",
                    severity="warning",
                    task_id=task.id,
                )
            )
    return issues


def validate_benchmark_semantics(
    suite: BenchmarkSuite,
    runtime_variables: Iterable[str] = (),
) -> tuple[ValidationIssue, ...]:
    allowed = frozenset(runtime_variables)
    issues: list[ValidationIssue] = []
    for index, task in enumerate(suite.root):
        issues.extend(_task_semantic_issues(task, index, allowed))
    return tuple(issues)
