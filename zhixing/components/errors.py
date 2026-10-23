"""Public, sanitized component-protocol errors."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def _safe_class_name(instance: object) -> str:
    cls = type(instance)
    return f"{cls.__module__}.{cls.__qualname__}"


class ComponentError(Exception):
    """Base error for the public component programming model."""


class ComponentInputError(ComponentError, ValueError):
    """A typed component input is incompatible with the selected role."""


class ComponentDefinitionError(ComponentError, ValueError):
    """A formal component definition violates its public authoring contract."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        component_id: str = "",
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create a structured component-definition failure.

        Args:
            code (str): Stable machine-readable diagnostic code.
            message (str): Bounded non-sensitive explanation.
            component_id (str): Optional safe namespace/name/version identity.
            details (Mapping[str, Any] | None): Additional safe diagnostic fields.

        Raises:
            None.

        Returns:
            None: Initializes the exception.
        """
        from .models import redact_mapping

        safe_message = str(message).replace("\n", " ")[:1000]
        super().__init__(safe_message)
        self.code = code
        self.component_id = component_id
        self.details = redact_mapping(details or {})

    def to_safe_dict(self) -> dict[str, Any]:
        """Return a serializable definition diagnostic.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Stable redacted diagnostic fields.
        """
        return {
            "code": self.code,
            "message": str(self),
            "component_id": self.component_id,
            "details": dict(self.details),
        }


class ComponentConfigurationError(ComponentDefinitionError):
    """A component parameter mapping does not satisfy its declared schema."""


class ComponentProtocolError(ComponentError, TypeError):
    """An object does not implement a requested component interface."""

    def __init__(
        self,
        *,
        role: str,
        instance: object,
        expected: str,
        discovered: Iterable[str] = (),
    ) -> None:
        methods = ", ".join(sorted(set(discovered))) or "none"
        super().__init__(
            f"Component role '{role}' requires {expected}; "
            f"class={_safe_class_name(instance)}; compatible_methods={methods}"
        )
        self.role = role
        self.class_name = _safe_class_name(instance)
        self.expected = expected
        self.discovered = tuple(sorted(set(discovered)))


class ComponentExecutionError(ComponentError, RuntimeError):
    """An adapted component failed during domain execution."""


class DeviceExecutionError(ComponentExecutionError):
    """A runtime device service failed before producing a valid value."""

    def __init__(self, operation: str, message: str) -> None:
        """Create a sanitized device-service failure.

        Args:
            operation (str): Stable logical device operation.
            message (str): Bounded diagnostic without credentials.

        Raises:
            None.

        Returns:
            None: Initializes the exception.
        """
        safe_message = str(message).replace("\n", " ")[:500]
        super().__init__(f"{operation}: {safe_message}")
        self.operation = operation
