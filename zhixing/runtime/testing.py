"""Deterministic fake runtime services for examples and contract tests."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
import time
from typing import Any

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionResult,
    DeviceObservation,
    ExecutionStatus,
    RuntimeContext,
)


@dataclass
class FakeObservationProvider:
    """Return scripted observations and record every capture phase."""

    observations: list[DeviceObservation]
    calls: list[tuple[int, str]] = field(default_factory=list)
    _index: int = 0

    def __init__(self, observations: Iterable[DeviceObservation]) -> None:
        """Create a provider from a finite observation sequence.

        Args:
            observations (Iterable[DeviceObservation]): Values returned in order.

        Raises:
            ValueError: The sequence is empty.

        Returns:
            None: Initializes the provider.
        """
        self.observations = list(observations)
        if not self.observations:
            raise ValueError("FakeObservationProvider requires at least one observation")
        self.calls = []
        self._index = 0

    def observe(self, runtime: RuntimeContext, *, phase: str) -> DeviceObservation:
        """Return the next observation, repeating the final value if necessary.

        Args:
            runtime (RuntimeContext): Current run context.
            phase (str): Requested capture phase.

        Raises:
            None.

        Returns:
            DeviceObservation: Scripted observation with stable ordering.
        """
        self.calls.append((runtime.step, phase))
        index = min(self._index, len(self.observations) - 1)
        self._index += 1
        return self.observations[index]


@dataclass
class ScriptedComponent:
    """Return scripted values or raise scripted exceptions from invoke calls."""

    outputs: list[Any]
    calls: list[tuple[Any, RuntimeContext]] = field(default_factory=list)
    delay_seconds: float = 0.0
    _index: int = 0

    def __init__(self, outputs: Iterable[Any], *, delay_seconds: float = 0.0) -> None:
        """Create a component from output values and exception instances.

        Args:
            outputs (Iterable[Any]): Values or Exceptions consumed in order.
            delay_seconds (float): Deterministic delay injected before each result.

        Raises:
            ValueError: No scripted output is provided.

        Returns:
            None: Initializes the component.
        """
        self.outputs = list(outputs)
        if not self.outputs:
            raise ValueError("ScriptedComponent requires at least one output")
        self.calls = []
        self.delay_seconds = max(0.0, float(delay_seconds))
        self._index = 0

    def invoke(self, input: Any, runtime: RuntimeContext) -> Any:
        """Record the typed call and return or raise the next script entry.

        Args:
            input (Any): Role-specific component input.
            runtime (RuntimeContext): Shared run context.

        Raises:
            Exception: Raises a scripted exception entry.

        Returns:
            Any: Scripted output value.
        """
        self.calls.append((input, runtime))
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        index = min(self._index, len(self.outputs) - 1)
        self._index += 1
        value = self.outputs[index]
        if isinstance(value, BaseException):
            raise value
        return value


@dataclass
class FakeActionExecutor:
    """ActionExecutor that records actions without touching a device."""

    statuses: list[ExecutionStatus] = field(default_factory=list)
    calls: list[tuple[ActionExecutionInput, RuntimeContext]] = field(default_factory=list)

    def invoke(self, input: ActionExecutionInput, runtime: RuntimeContext) -> ActionResult:
        """Return a deterministic ActionResult for one action.

        Args:
            input (ActionExecutionInput): Canonical action execution request.
            runtime (RuntimeContext): Shared run context.

        Raises:
            TypeError: The input is not ActionExecutionInput.

        Returns:
            ActionResult: Scripted or action-derived result.
        """
        if not isinstance(input, ActionExecutionInput):
            raise TypeError("FakeActionExecutor expects ActionExecutionInput")
        self.calls.append((input, runtime))
        if self.statuses:
            status = self.statuses[min(len(self.calls) - 1, len(self.statuses) - 1)]
        elif input.action.type.value == "done":
            status = ExecutionStatus.TERMINAL
        elif input.action.type.value == "fail":
            status = ExecutionStatus.FAILURE
        else:
            status = ExecutionStatus.SUCCESS
        return ActionResult(action=input.action, status=status)


def observation(name: str, *, sequence: int = 0) -> DeviceObservation:
    """Create a compact deterministic fake observation.

    Args:
        name (str): Screenshot stem or path.
        sequence (int): Observation sequence number.

    Raises:
        None.

    Returns:
        DeviceObservation: 100x200 fake Android observation.
    """
    path = name if name.endswith(".png") else f"{name}.png"
    return DeviceObservation(path, 100, 200, platform="fake", sequence=sequence)
