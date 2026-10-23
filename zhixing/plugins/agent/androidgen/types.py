"""Serializable AndroidGen state; clients and environment handles stay in services."""

from dataclasses import dataclass
from typing import Any, Mapping

from zhixing.components import ActionResult, DeviceObservation, TaskInput


@dataclass(frozen=True)
class AndroidGenSeed:
    """Task and source initial App, without the environment handle."""

    task: TaskInput
    init_state: str


@dataclass(frozen=True)
class AndroidGenView:
    """Source text/image inputs and immutable observation record."""

    observation: DeviceObservation
    state: Mapping[str, Any]
    record: Mapping[str, Any]


@dataclass(frozen=True)
class AndroidGenFrame:
    """Run-owned data cursor, including exact source history and pending writes."""

    task: TaskInput
    system_prompt: str
    example: str | None = None
    round_number: int = 0
    plan: tuple[tuple[str, bool], ...] = ()
    messages: tuple[Mapping[str, Any], ...] = ()
    previous_result: Mapping[str, Any] | None = None
    pending: tuple[Mapping[str, Any], ...] = ()
    view: AndroidGenView | None = None
    output: Mapping[str, Any] | None = None
    code: str = ""
    planning_done: bool = False
    planning_attempts: int = 0
    route: str = "continue"
    done: bool = False
    finished: bool = False
    records: tuple[Mapping[str, Any], ...] = ()
    actions: tuple[ActionResult, ...] = ()


def format_plan(plan: tuple[tuple[str, bool], ...]) -> str | None:
    """Preserve the original Done/Todo serialization.

    Args:
        plan: Ordered source statements and completion flags.
    Returns:
        str | None: Original formatted plan or None for an empty plan.
    """
    return '\n'.join(f'{stmt} State: [{"Done" if state else "Todo"}]' for stmt, state in plan) if plan else None
