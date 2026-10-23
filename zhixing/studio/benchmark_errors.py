"""Safe application errors for Studio Benchmark Catalog and Composer."""

from __future__ import annotations


class StudioBenchmarkError(RuntimeError):
    """Base error carrying a stable public code and bounded safe message."""

    def __init__(self, code: str, message: str) -> None:
        """Create one safe Studio Benchmark error.

        Args:
            code: Stable machine-readable error code.
            message: Reader-facing message with no sensitive values.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__(str(message).replace("\n", " ")[:500])
        self.code = str(code)[:160]
        self.message = str(message).replace("\n", " ")[:500]


class StudioBenchmarkValidationError(StudioBenchmarkError, ValueError):
    """A Catalog query, validation command, or preview request is invalid."""


class StudioBenchmarkNotFoundError(StudioBenchmarkError, LookupError):
    """A requested opaque Benchmark resource does not exist."""


class StudioBenchmarkConflictError(StudioBenchmarkError):
    """A Catalog source or preview definition is semantically ambiguous."""


class StudioBenchmarkCapacityError(StudioBenchmarkError):
    """A bounded process-local Benchmark transport is at capacity."""


class StudioBenchmarkSnapshotTooLargeError(StudioBenchmarkValidationError):
    """A complete canonical Experiment definition exceeds the inline limit."""


class StudioBenchmarkStorageError(StudioBenchmarkError):
    """Experiment persistence failed without exposing storage internals."""


class StudioBenchmarkIntegrityError(StudioBenchmarkConflictError):
    """Persisted Experiment facts violate an immutable identity invariant."""


class StudioBenchmarkRecoveryOwnershipError(StudioBenchmarkConflictError):
    """Another executable composition owns Benchmark startup recovery."""


class StudioBenchmarkRecoveryUnsupportedError(StudioBenchmarkError):
    """The current platform cannot provide safe local recovery ownership."""


__all__ = [
    "StudioBenchmarkConflictError",
    "StudioBenchmarkCapacityError",
    "StudioBenchmarkError",
    "StudioBenchmarkIntegrityError",
    "StudioBenchmarkNotFoundError",
    "StudioBenchmarkRecoveryOwnershipError",
    "StudioBenchmarkRecoveryUnsupportedError",
    "StudioBenchmarkSnapshotTooLargeError",
    "StudioBenchmarkStorageError",
    "StudioBenchmarkValidationError",
]
