"""Bounded process-local coordination for durable event journal readers."""

from __future__ import annotations

import threading


class BoundedEventWaiterRegistry:
    """Coordinate journal re-queries without caching authoritative events."""

    def __init__(
        self,
        *,
        max_conditions: int = 1000,
        scope_label: str = "Event",
    ) -> None:
        """Create one bounded condition registry.

        Args:
            max_conditions: Largest number of remembered resource keys.
            scope_label: Safe label used in validation errors.

        Raises:
            ValueError: The limit is not positive.

        Returns:
            None.
        """
        if max_conditions < 1:
            raise ValueError(f"max_{scope_label.lower()}_conditions must be positive")
        self._max_conditions = max_conditions
        self._scope_label = scope_label
        self._lock = threading.Lock()
        self._conditions: dict[str, threading.Condition] = {}
        self._waiters: dict[str, int] = {}
        self._closed = False

    def _condition(self, resource_id: str) -> threading.Condition:
        """Return or create one bounded resource condition.

        Args:
            resource_id: Stable resource identity.

        Raises:
            RuntimeError: The registry is at capacity.

        Returns:
            Shared condition for the resource.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError(
                    f"{self._scope_label} event waiter registry is closed"
                )
            condition = self._conditions.get(resource_id)
            if condition is not None:
                return condition
            if len(self._conditions) >= self._max_conditions:
                raise RuntimeError(
                    f"{self._scope_label} event waiter registry is at capacity"
                )
            condition = threading.Condition()
            self._conditions[resource_id] = condition
            return condition

    def notify(self, resource_id: str) -> None:
        """Wake all local waiters after a durable event commit.

        Args:
            resource_id: Stable resource identity.

        Returns:
            None.
        """
        with self._lock:
            if self._closed:
                return
            condition = self._conditions.get(resource_id)
        if condition is None:
            return
        with condition:
            condition.notify_all()

    def wait(self, resource_id: str, *, timeout: float) -> None:
        """Wait for a signal or a bounded heartbeat timeout.

        Args:
            resource_id: Stable resource identity.
            timeout: Maximum seconds to wait.

        Raises:
            ValueError: Timeout is outside the safe range.
            RuntimeError: The registry is at capacity.

        Returns:
            None.
        """
        if timeout <= 0 or timeout > 60:
            raise ValueError(
                f"{self._scope_label} event wait timeout must be within 60 seconds"
            )
        condition = self._condition(resource_id)
        with self._lock:
            self._waiters[resource_id] = self._waiters.get(resource_id, 0) + 1
        try:
            with condition:
                condition.wait(timeout=timeout)
        finally:
            with self._lock:
                remaining = self._waiters.get(resource_id, 1) - 1
                if remaining <= 0:
                    self._waiters.pop(resource_id, None)
                    if self._conditions.get(resource_id) is condition:
                        self._conditions.pop(resource_id, None)
                else:
                    self._waiters[resource_id] = remaining

    def release(self, resource_id: str) -> None:
        """Forget one resource after handlers leave.

        Args:
            resource_id: Stable resource identity.

        Returns:
            None.
        """
        with self._lock:
            self._conditions.pop(resource_id, None)
            self._waiters.pop(resource_id, None)

    def release_all(self) -> None:
        """Wake and forget all process-local waiters during shutdown.

        Returns:
            None.
        """
        with self._lock:
            conditions = tuple(self._conditions.values())
            self._conditions.clear()
            self._waiters.clear()
        for condition in conditions:
            with condition:
                condition.notify_all()

    def close(self) -> None:
        """Reject future waits and wake every current waiter.

        Returns:
            None.
        """
        with self._lock:
            self._closed = True
            conditions = tuple(self._conditions.values())
            self._conditions.clear()
            self._waiters.clear()
        for condition in conditions:
            with condition:
                condition.notify_all()


class BoundedConnectionLimiter:
    """Non-blocking process-local connection capacity guard."""

    def __init__(self, *, max_connections: int) -> None:
        """Create a finite connection limiter.

        Args:
            max_connections: Maximum concurrently acquired connections.

        Raises:
            ValueError: The limit is not positive.

        Returns:
            None.
        """
        if max_connections < 1:
            raise ValueError("max_connections must be positive")
        self.max_connections = max_connections
        self._semaphore = threading.BoundedSemaphore(max_connections)
        self._lock = threading.Lock()
        self._active = 0

    @property
    def active(self) -> int:
        """Return the currently acquired connection count.

        Returns:
            Number of active connection leases.
        """
        with self._lock:
            return self._active

    def acquire(self) -> bool:
        """Try to acquire one connection lease without blocking.

        Returns:
            True when capacity was reserved, otherwise false.
        """
        if not self._semaphore.acquire(blocking=False):
            return False
        with self._lock:
            self._active += 1
        return True

    def release(self) -> None:
        """Release one previously acquired connection lease.

        Raises:
            ValueError: No matching lease is active.

        Returns:
            None.
        """
        with self._lock:
            if self._active < 1:
                raise ValueError("connection limiter release is unbalanced")
            self._active -= 1
        self._semaphore.release()


__all__ = ["BoundedConnectionLimiter", "BoundedEventWaiterRegistry"]
