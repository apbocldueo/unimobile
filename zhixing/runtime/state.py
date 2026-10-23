"""Typed, explicitly scoped state for generalized AgentGraph execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from zhixing.graph import StateMergePolicy, StateScope

from .errors import GraphExecutionError


def _matches_type(value: Any, data_type: str) -> bool:
    """Check lightweight built-in state types without importing plugins.

    Args:
        value (Any): Runtime value.
        data_type (str): Logical contract type identifier.

    Raises:
        None.

    Returns:
        bool: True when the value is compatible with the declared type.
    """
    if value is None or data_type == "any":
        return True
    expected = {
        "text": str,
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "list": (list, tuple),
        "mapping": dict,
    }.get(data_type)
    return True if expected is None else isinstance(value, expected)


@dataclass
class StateStore:
    """State values partitioned by declared scope and logical owner path."""

    _values: dict[tuple[StateScope, str, str], Any] = field(default_factory=dict)
    _types: dict[tuple[StateScope, str, str], str] = field(default_factory=dict)

    def read(
        self,
        scope: StateScope,
        owner: str,
        key: str,
        data_type: str,
        initial: Any,
    ) -> Any:
        """Read typed state, lazily installing its declared initial value.

        Args:
            scope (StateScope): State lifetime.
            owner (str): Stable scope owner path.
            key (str): Logical state key.
            data_type (str): Declared logical type.
            initial (Any): Initial value when absent.

        Raises:
            GraphExecutionError: A prior declaration used a different type.

        Returns:
            Any: Current or initial state value.
        """
        address = (scope, owner, key)
        declared = self._types.get(address)
        if declared is not None and declared != data_type:
            raise GraphExecutionError(
                "runtime.state_type_conflict",
                f"State {key!r} was declared as {declared!r}, not {data_type!r}",
                phase="state",
                details={"scope": scope.value, "key": key},
            )
        self._types[address] = data_type
        if address not in self._values:
            self._values[address] = initial
        return self._values[address]

    def write(
        self,
        scope: StateScope,
        owner: str,
        key: str,
        data_type: str,
        value: Any,
        merge: StateMergePolicy,
    ) -> Any:
        """Write typed state using an explicit merge policy.

        Args:
            scope (StateScope): State lifetime.
            owner (str): Stable scope owner path.
            key (str): Logical state key.
            data_type (str): Declared logical type.
            value (Any): New value.
            merge (StateMergePolicy): Replace or append behavior.

        Raises:
            GraphExecutionError: Type checking or append compatibility fails.

        Returns:
            Any: Updated state value.
        """
        address = (scope, owner, key)
        declared = self._types.get(address)
        if declared is not None and declared != data_type:
            raise GraphExecutionError(
                "runtime.state_type_conflict",
                f"State {key!r} has incompatible declarations",
                phase="state",
                details={"scope": scope.value, "key": key},
            )
        if not _matches_type(value, data_type):
            raise GraphExecutionError(
                "runtime.state_value_type",
                f"State {key!r} received an incompatible value",
                phase="state",
                details={"scope": scope.value, "key": key, "actual": type(value).__name__},
            )
        self._types[address] = data_type
        if merge is StateMergePolicy.REPLACE:
            updated = value
        else:
            current = self._values.get(address, [])
            if not isinstance(current, list):
                raise GraphExecutionError(
                    "runtime.state_append_target",
                    f"State {key!r} is not appendable",
                    phase="state",
                    details={"scope": scope.value, "key": key},
                )
            updated = [*current, value]
        self._values[address] = updated
        return updated

    def clear(self, scope: StateScope, owner: str) -> None:
        """Clear one scope owner at its lifecycle boundary.

        Args:
            scope (StateScope): Scope to clear.
            owner (str): Stable owner path.

        Raises:
            None.

        Returns:
            None: Matching values and declarations are removed.
        """
        addresses = [
            address
            for address in self._values
            if address[0] is scope and address[1] == owner
        ]
        for address in addresses:
            self._values.pop(address, None)
            self._types.pop(address, None)

    def snapshot(self) -> dict[str, Any]:
        """Return a safe structural snapshot for tests and reports.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Address strings mapped to current values.
        """
        return {
            f"{scope.value}:{owner}:{key}": value
            for (scope, owner, key), value in sorted(
                self._values.items(),
                key=lambda item: (item[0][0].value, item[0][1], item[0][2]),
            )
        }
