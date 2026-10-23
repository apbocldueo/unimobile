"""Safe typed failures for Studio Benchmark authoring resources."""

from __future__ import annotations

from .benchmark_errors import (
    StudioBenchmarkCapacityError,
    StudioBenchmarkConflictError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkStorageError,
    StudioBenchmarkValidationError,
)


class StudioBenchmarkAuthoringValidationError(StudioBenchmarkValidationError):
    """An authoring request or document violates the safe resource contract."""


class StudioBenchmarkAuthoringNotFoundError(StudioBenchmarkNotFoundError):
    """A requested draft or owned authoring revision is absent."""


class StudioBenchmarkAuthoringIdempotencyConflictError(
    StudioBenchmarkConflictError
):
    """A scoped client request identity was reused with different content."""


class StudioBenchmarkAuthoringRevisionConflictError(
    StudioBenchmarkConflictError
):
    """A revision save was based on a stale current revision."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        current_revision_id: str,
    ) -> None:
        """Create a safe optimistic-concurrency conflict.

        Args:
            code: Stable public error code.
            message: Bounded reader-facing message.
            current_revision_id: Current safe opaque revision identity.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__(code, message)
        self.current_revision_id = current_revision_id


class StudioBenchmarkAuthoringCapacityError(StudioBenchmarkCapacityError):
    """An authoring definition, member, page, or import exceeds its bound."""


class StudioBenchmarkAuthoringDriftError(StudioBenchmarkConflictError):
    """A selected Catalog source changed while its snapshot was copied."""


class StudioBenchmarkAuthoringReleaseConflictError(
    StudioBenchmarkConflictError
):
    """A readable Package version already has different release content."""


class StudioBenchmarkAuthoringStorageError(StudioBenchmarkStorageError):
    """Managed authoring bytes or durable metadata could not be stored."""


class StudioBenchmarkAuthoringFreezeEligibilityError(
    StudioBenchmarkAuthoringValidationError
):
    """Complete server-owned analysis found no freeze-eligible Package."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostics: tuple[object, ...],
    ) -> None:
        """Create one bounded eligibility failure with safe diagnostics.

        Args:
            code: Stable public error code.
            message: Bounded reader-facing message.
            diagnostics: Strict field-addressable public diagnostics.

        Returns:
            None.
        """
        super().__init__(code, message)
        self.diagnostics = diagnostics


__all__ = [
    "StudioBenchmarkAuthoringCapacityError",
    "StudioBenchmarkAuthoringDriftError",
    "StudioBenchmarkAuthoringFreezeEligibilityError",
    "StudioBenchmarkAuthoringIdempotencyConflictError",
    "StudioBenchmarkAuthoringNotFoundError",
    "StudioBenchmarkAuthoringRevisionConflictError",
    "StudioBenchmarkAuthoringReleaseConflictError",
    "StudioBenchmarkAuthoringStorageError",
    "StudioBenchmarkAuthoringValidationError",
]
