"""Durable-first query and waiting service for Benchmark Experiment events."""

from __future__ import annotations

from .benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkValidationError,
)
from .benchmark_experiment_models import StudioBenchmarkEventPageV1
from .benchmark_experiment_protocols import StudioBenchmarkExperimentRepository
from .event_waiters import BoundedEventWaiterRegistry


class BenchmarkEventNotifier(BoundedEventWaiterRegistry):
    """Bounded Experiment waiter registry carrying no event payloads."""

    def __init__(self, *, max_experiment_conditions: int = 1000) -> None:
        """Create one bounded Benchmark Experiment registry.

        Args:
            max_experiment_conditions: Maximum simultaneous Experiment keys.

        Raises:
            ValueError: The limit is not positive.

        Returns:
            None.
        """
        super().__init__(
            max_conditions=max_experiment_conditions,
            scope_label="Benchmark Experiment",
        )


class DurableBenchmarkEventService:
    """Read committed Benchmark events and coordinate bounded live waits."""

    def __init__(
        self,
        repository: StudioBenchmarkExperimentRepository,
        *,
        notifier: BenchmarkEventNotifier | None = None,
    ) -> None:
        """Bind one durable journal repository and notification accelerator.

        Args:
            repository: Durable Experiment repository.
            notifier: Optional process-local bounded waiter registry.

        Returns:
            None.
        """
        self.repository = repository
        self.notifier = notifier or BenchmarkEventNotifier()

    def query(
        self,
        experiment_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioBenchmarkEventPageV1:
        """Read one bounded page from the durable journal.

        Args:
            experiment_id: Owning Experiment identity.
            after: Exclusive Experiment-local sequence.
            limit: Maximum events in the page.

        Raises:
            StudioBenchmarkError: Repository validation or query fails.

        Returns:
            Current durable event page.
        """
        return self.repository.query_events(
            experiment_id,
            after=after,
            limit=limit,
        )

    def wait_for_events(
        self,
        experiment_id: str,
        *,
        after: int,
        limit: int = 100,
        timeout: float = 15.0,
    ) -> StudioBenchmarkEventPageV1:
        """Return backfill immediately or wait once before re-querying.

        Args:
            experiment_id: Owning Experiment identity.
            after: Exclusive Experiment-local sequence.
            limit: Maximum events in the page.
            timeout: Maximum heartbeat wait in seconds.

        Raises:
            StudioBenchmarkValidationError: Timeout is unsafe.
            StudioBenchmarkConflictError: Waiter registry is at capacity.
            StudioBenchmarkError: Durable query fails.

        Returns:
            Current or newly committed durable page.
        """
        if timeout <= 0 or timeout > 60:
            raise StudioBenchmarkValidationError(
                "benchmark.event.wait_timeout_invalid",
                "Benchmark event wait timeout must be within 60 seconds",
            )
        page = self.query(experiment_id, after=after, limit=limit)
        if page.items or page.terminal:
            return page
        try:
            self.notifier.wait(experiment_id, timeout=timeout)
        except RuntimeError as error:
            raise StudioBenchmarkConflictError(
                "benchmark.event.waiter_capacity",
                "Benchmark event waiter capacity is exhausted",
            ) from error
        return self.query(experiment_id, after=after, limit=limit)

    def shutdown(self) -> None:
        """Release all process-local waiter state without deleting facts.

        Returns:
            None.
        """
        self.notifier.close()


__all__ = ["BenchmarkEventNotifier", "DurableBenchmarkEventService"]
