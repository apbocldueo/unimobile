"""Pure schedule construction and deterministic Benchmark task materialization."""

from __future__ import annotations

import re
from dataclasses import dataclass
from random import Random
from typing import Any, Mapping, Protocol

from zhixing.benchmark.identity import canonical_hash
from zhixing.benchmark.models import (
    BenchmarkPlan,
    ExperimentProtocol,
    GroundTruthBinding,
    TaskInstance,
)
from zhixing.config.contracts import BenchmarkTask
from zhixing.config.contracts.common import PluginReference

from .resources import BenchmarkResourceProvider

_PLACEHOLDER = re.compile(r"\$\{([^{}]+)\}")


class TaskValueResolver(Protocol):
    """Boundary used by the materializer to execute task-value plugins."""

    def generate_task_value(
        self,
        reference: PluginReference,
        params: Mapping[str, Any],
        *,
        rng: Random,
    ) -> tuple[Any, tuple[str, ...]]:
        """Generate one JSON-compatible task parameter."""
        ...


@dataclass(frozen=True)
class BenchmarkScheduleEntry:
    """One deterministic Agent × task × repeat schedule entry."""

    repeat: int
    task_id: str
    agent_id: str
    seed: int
    shared_instance_key: str


def derive_task_seed(
    plan: BenchmarkPlan,
    protocol: ExperimentProtocol,
    *,
    repeat: int,
    task_id: str,
    agent_id: str | None = None,
) -> int:
    """Derive a stable task seed from semantic identities.

    Args:
        plan (BenchmarkPlan): Compiled task semantics.
        protocol (ExperimentProtocol): Fairness policy.
        repeat (int): Zero-based repeat.
        task_id (str): Stable task identifier.
        agent_id (str | None): Agent identity for intentionally unpaired runs.

    Raises:
        ValueError: Repeat or task identity is invalid.

    Returns:
        int: Stable non-negative 63-bit seed.
    """
    if repeat < 0 or not task_id:
        raise ValueError("repeat and task_id must identify a valid task")
    payload = {
        "plan": plan.canonical_hash(),
        "protocol": protocol.canonical_hash(),
        "protocol_seed": protocol.seed,
        "repeat": repeat,
        "task_id": task_id,
    }
    if agent_id is not None:
        payload["agent_id"] = agent_id
    digest = canonical_hash(payload).removeprefix("sha256:")
    return int(digest[:16], 16) & ((1 << 63) - 1)


def build_schedule(
    plan: BenchmarkPlan,
    protocol: ExperimentProtocol,
    agent_ids: tuple[str, ...] | list[str],
    *,
    task_ids: tuple[str, ...] | list[str] = (),
) -> tuple[BenchmarkScheduleEntry, ...]:
    """Build a deterministic execution matrix without runtime side effects.

    Args:
        plan (BenchmarkPlan): Compiled Benchmark definition.
        protocol (ExperimentProtocol): Ordering and repeat semantics.
        agent_ids (tuple[str, ...] | list[str]): Named candidate Agents.
        task_ids (tuple[str, ...] | list[str]): Optional task filter.

    Raises:
        ValueError: Agent names or requested tasks are invalid.

    Returns:
        tuple[BenchmarkScheduleEntry, ...]: Stable schedule.
    """
    normalized_agents = tuple(sorted(set(agent_ids)))
    if not normalized_agents or any(not item.strip() for item in normalized_agents):
        raise ValueError("at least one non-blank Agent ID is required")
    available = {task.id for task in plan.tasks}
    selected = tuple(task_ids) if task_ids else tuple(sorted(available))
    missing = sorted(set(selected) - available)
    if missing:
        raise ValueError(f"unknown Benchmark task IDs: {missing}")
    entries: list[BenchmarkScheduleEntry] = []
    for repeat in range(protocol.repeats):
        ordered = protocol.ordered_task_ids(
            list(selected),
            plan_identity=plan.canonical_hash(),
            repeat=repeat,
        )
        for task_id in ordered:
            shared_seed = derive_task_seed(
                plan,
                protocol,
                repeat=repeat,
                task_id=task_id,
            )
            for agent_id in normalized_agents:
                seed = (
                    shared_seed
                    if protocol.task_materialization.reuse_across_agents
                    else derive_task_seed(
                        plan,
                        protocol,
                        repeat=repeat,
                        task_id=task_id,
                        agent_id=agent_id,
                    )
                )
                key_agent = (
                    ""
                    if protocol.task_materialization.reuse_across_agents
                    else agent_id
                )
                entries.append(
                    BenchmarkScheduleEntry(
                        repeat=repeat,
                        task_id=task_id,
                        agent_id=agent_id,
                        seed=seed,
                        shared_instance_key=(
                            f"{repeat}:{task_id}:{key_agent}:{seed}"
                        ),
                    )
                )
    return tuple(entries)


def render_value(value: Any, values: Mapping[str, Any]) -> Any:
    """Render placeholders recursively while preserving exact-value types.

    Args:
        value (Any): JSON-compatible value containing placeholders.
        values (Mapping[str, Any]): Previously materialized variables.

    Raises:
        ValueError: A placeholder is unresolved.

    Returns:
        Any: Rendered value.
    """
    if isinstance(value, str):
        exact = _PLACEHOLDER.fullmatch(value)
        if exact is not None:
            key = exact.group(1)
            if key not in values:
                raise ValueError(f"unresolved placeholder {key!r}")
            return values[key]

        def replace(match: re.Match[str]) -> str:
            """Replace one embedded placeholder.

            Args:
                match (re.Match[str]): Placeholder match.

            Raises:
                ValueError: Placeholder key is missing.

            Returns:
                str: String representation of the value.
            """
            key = match.group(1)
            if key not in values:
                raise ValueError(f"unresolved placeholder {key!r}")
            return str(values[key])

        rendered = _PLACEHOLDER.sub(replace, value)
        if _PLACEHOLDER.search(rendered):
            raise ValueError("rendered value still contains placeholders")
        return rendered
    if isinstance(value, dict):
        return {key: render_value(item, values) for key, item in value.items()}
    if isinstance(value, list):
        return [render_value(item, values) for item in value]
    if isinstance(value, tuple):
        return tuple(render_value(item, values) for item in value)
    return value


def _ground_truth_value(
    binding: GroundTruthBinding | None,
    provider: BenchmarkResourceProvider,
) -> Any:
    """Select inline ground truth or keep a logical resource identity.

    Args:
        binding (GroundTruthBinding | None): Optional task binding.
        provider (BenchmarkResourceProvider): Runtime resource boundary.

    Raises:
        ValueError: A resource binding is unavailable.

    Returns:
        Any: Materialized ground truth value.
    """
    del provider
    if binding is None:
        return None
    if "inline" in binding.model_fields_set:
        return binding.inline
    return binding.ref


def materialize_task(
    plan: BenchmarkPlan,
    task: BenchmarkTask,
    *,
    repeat: int,
    seed: int,
    resolver: TaskValueResolver,
    resource_provider: BenchmarkResourceProvider,
) -> TaskInstance:
    """Materialize one task deterministically without touching a device.

    Args:
        plan (BenchmarkPlan): Source Plan.
        task (BenchmarkTask): Selected task definition.
        repeat (int): Zero-based repeat.
        seed (int): Derived task seed.
        resolver (TaskValueResolver): Explicit task plugin resolver.
        resource_provider (BenchmarkResourceProvider): Logical resource service.

    Raises:
        ValueError: Generation, rendering, or final validation fails.

    Returns:
        TaskInstance: Immutable concrete task shared across Agents when configured.
    """
    rng = Random(seed)
    generated: dict[str, Any] = {}
    notes: list[str] = []
    for name, reference in task.task_initializer.items():
        params = render_value(reference.params, generated)
        value, generated_notes = resolver.generate_task_value(
            reference,
            params,
            rng=rng,
        )
        generated[name] = value
        notes.extend(generated_notes)
    instruction = render_value(task.instruction, generated)
    environment = tuple(
        render_value(item.model_dump(mode="json", exclude_none=True), generated)
        for item in task.environment_initializer
    )
    evaluator = render_value(
        task.evaluator.model_dump(mode="json", exclude_none=True),
        generated,
    )
    cleanup = tuple(
        render_value(item.model_dump(mode="json", exclude_none=True), generated)
        for item in task.cleanup_initializer
    )
    ground_truth = render_value(
        _ground_truth_value(plan.ground_truth.get(task.id), resource_provider),
        generated,
    )
    return TaskInstance(
        plan_identity=plan.canonical_hash(),
        task_id=task.id,
        repeat=repeat,
        seed=seed,
        generated_params=generated,
        instruction=instruction,
        ground_truth=ground_truth,
        app=task.app,
        environment_initializer=environment,
        evaluator=evaluator,
        cleanup_initializer=cleanup,
        materialization_notes=tuple(sorted(set(notes))),
    )


class TaskInstancePool:
    """Run-local cache implementing paired materialization fairness."""

    def __init__(self) -> None:
        """Create an empty materialization cache.

        Returns:
            None.
        """
        self._items: dict[str, TaskInstance] = {}

    def get_or_materialize(
        self,
        key: str,
        factory: Any,
    ) -> TaskInstance:
        """Return a cached instance or call a side-effect-free factory once.

        Args:
            key (str): Stable schedule materialization key.
            factory (Any): Zero-argument TaskInstance factory.

        Raises:
            TypeError: Factory does not return TaskInstance.

        Returns:
            TaskInstance: Shared or newly materialized instance.
        """
        if key not in self._items:
            value = factory()
            if not isinstance(value, TaskInstance):
                raise TypeError("materialization factory must return TaskInstance")
            self._items[key] = value
        return self._items[key]
