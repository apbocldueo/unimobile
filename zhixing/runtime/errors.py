"""Structured, redacted errors raised by the AgentGraph runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from zhixing.components import redact_mapping


@dataclass(frozen=True)
class RuntimeErrorInfo:
    """Serializable information about one runtime failure."""

    code: str
    message: str
    node_id: str = ""
    phase: str = ""
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the failure without exposing sensitive details.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Redacted JSON-compatible failure details.
        """
        return {
            "code": self.code,
            "message": self.message[:1000],
            "node_id": self.node_id,
            "phase": self.phase,
            "details": redact_mapping(self.details),
        }


class GraphRuntimeError(RuntimeError):
    """Base exception carrying a stable runtime error code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        node_id: str = "",
        phase: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create a structured runtime exception.

        Args:
            code (str): Stable machine-readable failure code.
            message (str): Human-readable non-sensitive explanation.
            node_id (str): Logical node responsible for the failure.
            phase (str): Runtime phase in which the failure occurred.
            details (Mapping[str, Any] | None): Additional safe diagnostics.

        Raises:
            None.

        Returns:
            None: Initializes the exception instance.
        """
        super().__init__(message)
        self.info = RuntimeErrorInfo(code, message, node_id, phase, details or {})


class GraphBindingError(GraphRuntimeError):
    """A validated graph could not be bound to runtime components."""


class GraphExecutionError(GraphRuntimeError):
    """A bound graph could not complete runtime execution."""


class ObservationError(GraphRuntimeError):
    """The observation provider could not obtain a device state."""

