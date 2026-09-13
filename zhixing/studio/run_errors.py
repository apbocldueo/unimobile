"""Safe application and persistence errors for Studio Run services."""

from __future__ import annotations


class StudioRunError(RuntimeError):
    """Base error carrying a stable public code and bounded safe message."""

    def __init__(self, code: str, message: str) -> None:
        """Create one safe Studio Run error.

        Args:
            code (str): Stable machine-readable error code.
            message (str): Reader-facing message that contains no secrets.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__(str(message)[:1000])
        self.code = str(code)[:160]
        self.message = str(message)[:1000]


class StudioRunValidationError(StudioRunError, ValueError):
    """Run request or stored contract data is invalid."""


class StudioRunNotFoundError(StudioRunError, LookupError):
    """Requested Run identity does not exist."""


class StudioRunConflictError(StudioRunError):
    """Run identity, idempotency key, transition, or event identity conflicts."""


class StudioRunArtifactNotFoundError(StudioRunError, LookupError):
    """Requested run-scoped artifact is absent or hidden."""


class StudioRunEvidenceError(StudioRunError):
    """Run evidence cannot be safely persisted or verified."""


class StudioRunDeviceBusyError(StudioRunError):
    """Selected local device profile already has an active owner."""


__all__ = [
    "StudioRunArtifactNotFoundError",
    "StudioRunConflictError",
    "StudioRunDeviceBusyError",
    "StudioRunError",
    "StudioRunEvidenceError",
    "StudioRunNotFoundError",
    "StudioRunValidationError",
]
