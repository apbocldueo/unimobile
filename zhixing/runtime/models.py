"""Runtime-only values kept separate from the side-effect-free AgentGraph IR."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from zhixing.components import DeviceObservation, RuntimeContext
from zhixing.components.authoring import ComponentSpec
from zhixing.graph import AgentGraph, GraphComponentRef, GraphNode


@runtime_checkable
class ObservationProvider(Protocol):
    """Produce typed device observations without exposing scheduler internals."""

    def observe(self, runtime: RuntimeContext, *, phase: str) -> DeviceObservation:
        """Capture one device observation.

        Args:
            runtime (RuntimeContext): Current run context.
            phase (str): Either pre_action or post_action.

        Raises:
            Exception: Propagates device capture failures to the runtime boundary.

        Returns:
            DeviceObservation: Typed snapshot of the current device state.
        """
        ...


@runtime_checkable
class CancellationSignal(Protocol):
    """Expose cooperative cancellation between node invocations."""

    def is_cancelled(self) -> bool:
        """Return whether execution should stop before the next node.

        Args:
            None.

        Raises:
            None.

        Returns:
            bool: True when the run has been cancelled.
        """
        ...


@dataclass
class SimpleCancellationSignal:
    """Mutable cancellation signal useful for local and test execution."""

    cancelled: bool = False

    def cancel(self) -> None:
        """Request cancellation at the next scheduler boundary.

        Args:
            None.

        Raises:
            None.

        Returns:
            None: Updates the signal in place.
        """
        self.cancelled = True

    def is_cancelled(self) -> bool:
        """Return the current cancellation state.

        Args:
            None.

        Raises:
            None.

        Returns:
            bool: Current cancellation flag.
        """
        return self.cancelled


@dataclass(frozen=True)
class BoundCandidate:
    """One resolved component candidate preserving its declarative identity."""

    reference: GraphComponentRef
    instance: Any | None = field(default=None, repr=False)
    error: str = ""


@dataclass(frozen=True)
class ResolvedComponentDefinition:
    """Carry a formal specification and run-scoped resolved dependencies.

    This wrapper belongs to the generic binding boundary. It deliberately has
    no knowledge of whether the specification came from an installed plugin,
    the built-in catalog, or another resolver.

    Args:
        specification (ComponentSpec): Formal declaration to construct.
        dependencies (Mapping[str, Any]): Explicit runtime dependencies already
            resolved by the selected resolver.
    """

    specification: ComponentSpec
    dependencies: Mapping[str, Any] = field(default_factory=dict, repr=False)


@dataclass(frozen=True)
class BoundComponent:
    """Runtime binding for one logical component node."""

    node: GraphNode
    candidates: tuple[BoundCandidate, ...]

    @property
    def node_id(self) -> str:
        """Return the stable graph node identifier.

        Args:
            None.

        Raises:
            None.

        Returns:
            str: Logical node identifier.
        """
        return self.node.id


@dataclass(frozen=True)
class BoundAgentGraph:
    """Validated AgentGraph paired with resolved runtime component candidates."""

    graph: AgentGraph
    components: Mapping[str, BoundComponent]


@dataclass
class StepFrame:
    """Values whose meaning is scoped to one mobile interaction step."""

    step: int
    pre_observation: DeviceObservation | None = None
    post_observation: DeviceObservation | None = None
    action: Any = None
    action_result: Any = None
    feedback_inputs: dict[tuple[str, str], Any] = field(default_factory=dict)


@dataclass
class ValueStore:
    """Typed-by-contract value store addressed by step, node, and port."""

    persistent: dict[tuple[str, str], Any] = field(default_factory=dict)
    step_values: dict[tuple[int, str, str], Any] = field(default_factory=dict)
    controls: set[tuple[int, str, str]] = field(default_factory=set)

    def put(self, step: int, node_id: str, port_id: str, value: Any, *, persistent: bool = False) -> None:
        """Store one produced or delivered port value.

        Args:
            step (int): Current interaction step.
            node_id (str): Logical node identifier.
            port_id (str): Logical port identifier.
            value (Any): Typed value validated by the role boundary.
            persistent (bool): Whether later steps may reuse this value.

        Raises:
            None.

        Returns:
            None: Mutates the store in place.
        """
        key = (node_id, port_id)
        if persistent:
            self.persistent[key] = value
        self.step_values[(step, node_id, port_id)] = value

    def append(self, step: int, node_id: str, port_id: str, value: Any) -> None:
        """Append a value to a multiple-cardinality input port.

        Args:
            step (int): Current interaction step.
            node_id (str): Target logical node identifier.
            port_id (str): Target logical port identifier.
            value (Any): Typed value to append.

        Raises:
            None.

        Returns:
            None: Mutates the target list in place.
        """
        key = (step, node_id, port_id)
        current = self.step_values.setdefault(key, [])
        if not isinstance(current, list):
            current = [current]
            self.step_values[key] = current
        current.append(value)

    def get(self, step: int, node_id: str, port_id: str, default: Any = None) -> Any:
        """Read a step value with fallback to a persistent value.

        Args:
            step (int): Current interaction step.
            node_id (str): Logical node identifier.
            port_id (str): Logical port identifier.
            default (Any): Value returned when the address is absent.

        Raises:
            None.

        Returns:
            Any: Stored value or the supplied default.
        """
        return self.step_values.get(
            (step, node_id, port_id),
            self.persistent.get((node_id, port_id), default),
        )

    def has(self, step: int, node_id: str, port_id: str) -> bool:
        """Check whether a step or persistent address has a value.

        Args:
            step (int): Current interaction step.
            node_id (str): Logical node identifier.
            port_id (str): Logical port identifier.

        Raises:
            None.

        Returns:
            bool: True when a value exists.
        """
        return (step, node_id, port_id) in self.step_values or (node_id, port_id) in self.persistent


ComponentFactory = Callable[..., Any]
