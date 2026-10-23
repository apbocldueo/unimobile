"""Conservative startup recovery and local ownership for Benchmark Studio."""

from __future__ import annotations

import errno
import os
import threading
import time
from pathlib import Path
from typing import BinaryIO, Callable

from .benchmark_errors import (
    StudioBenchmarkIntegrityError,
    StudioBenchmarkRecoveryOwnershipError,
    StudioBenchmarkRecoveryUnsupportedError,
)
from .benchmark_experiment_models import (
    StudioBenchmarkAvailability,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkRecoveryDecision,
    StudioBenchmarkRecoverySummaryV1,
    StudioBenchmarkTaskRunTerminalReason,
)
from .benchmark_experiment_protocols import (
    StudioBenchmarkExperimentRepository,
    StudioBenchmarkRecoveryOwnership,
)
from .benchmark_publication_protocols import StudioBenchmarkPublisher


Clock = Callable[[], int]


def _now_ms() -> int:
    """Return the current Unix epoch in integer milliseconds.

    Returns:
        Current Unix epoch milliseconds.
    """
    return time.time_ns() // 1_000_000


class LocalBenchmarkRecoveryOwnership(StudioBenchmarkRecoveryOwnership):
    """OS-released exclusive ownership for one local SQLite workspace."""

    _guard = threading.Lock()
    _held_database_keys: set[str] = set()

    def __init__(
        self,
        *,
        database_key: str,
        handle: BinaryIO,
        platform: str,
    ) -> None:
        """Store an already acquired private lock handle.

        Args:
            database_key: Canonical private database identity.
            handle: Open file handle holding the OS lock.
            platform: Selected lock implementation.

        Returns:
            None.
        """
        self._database_key = database_key
        self._handle: BinaryIO | None = handle
        self._platform = platform

    @classmethod
    def acquire(
        cls,
        database_path: str | Path,
    ) -> "LocalBenchmarkRecoveryOwnership":
        """Acquire exclusive executable ownership for one SQLite database.

        Args:
            database_path: Explicit local Studio database.

        Raises:
            StudioBenchmarkRecoveryOwnershipError: Another local executable
                composition already owns the database.
            StudioBenchmarkRecoveryUnsupportedError: The platform has no safe
                supported local lock primitive.
            OSError: The private lock storage cannot be opened.

        Returns:
            Ownership held until :meth:`close`.
        """
        database = Path(database_path).expanduser().resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        database_key = os.path.normcase(str(database))
        lock_path = database.parent / (
            f".{database.name}.benchmark-recovery.lock"
        )
        platform = "posix" if os.name == "posix" else "windows"
        if os.name not in {"posix", "nt"}:
            raise StudioBenchmarkRecoveryUnsupportedError(
                "benchmark.recovery.ownership_unsupported",
                "Safe local Benchmark recovery ownership is unsupported",
            )
        with cls._guard:
            if database_key in cls._held_database_keys:
                raise StudioBenchmarkRecoveryOwnershipError(
                    "benchmark.recovery.ownership_contended",
                    "Another executable Benchmark composition owns this workspace",
                )
            handle = lock_path.open("a+b")
            try:
                if os.name == "posix":
                    import fcntl

                    fcntl.flock(
                        handle.fileno(),
                        fcntl.LOCK_EX | fcntl.LOCK_NB,
                    )
                else:
                    import msvcrt

                    handle.seek(0)
                    if handle.read(1) == b"":
                        handle.seek(0)
                        handle.write(b"\0")
                        handle.flush()
                    handle.seek(0)
                    msvcrt.locking(
                        handle.fileno(),
                        msvcrt.LK_NBLCK,
                        1,
                    )
            except OSError as error:
                handle.close()
                if error.errno in {
                    errno.EACCES,
                    errno.EAGAIN,
                    errno.EDEADLK,
                }:
                    raise StudioBenchmarkRecoveryOwnershipError(
                        "benchmark.recovery.ownership_contended",
                        "Another executable Benchmark composition owns this workspace",
                    ) from error
                raise
            cls._held_database_keys.add(database_key)
        return cls(
            database_key=database_key,
            handle=handle,
            platform=platform,
        )

    def close(self) -> None:
        """Release local ownership without deleting its durable lock marker.

        Returns:
            None.
        """
        with self._guard:
            handle = self._handle
            if handle is None:
                return
            try:
                if self._platform == "posix":
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                else:
                    import msvcrt

                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            finally:
                handle.close()
                self._handle = None
                self._held_database_keys.discard(self._database_key)

    def __enter__(self) -> "LocalBenchmarkRecoveryOwnership":
        """Return this already acquired ownership.

        Returns:
            Active ownership.
        """
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: object | None,
    ) -> None:
        """Release ownership on context-manager exit.

        Args:
            exception_type: Optional raised exception type.
            exception: Optional raised exception.
            traceback: Optional traceback object.

        Returns:
            None.
        """
        del exception_type, exception, traceback
        self.close()


class StudioBenchmarkStartupRecovery:
    """Apply conservative durable decisions before worker startup."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkExperimentRepository,
        process_owner_id: str,
        publisher: StudioBenchmarkPublisher | None,
        clock: Clock = _now_ms,
    ) -> None:
        """Configure startup recovery dependencies.

        Args:
            repository: Typed aggregate and recovery transaction boundary.
            process_owner_id: Current opaque executable process identity.
            publisher: Existing idempotent Stage 5.2C-2 publisher.
            clock: Injectable Unix-millisecond clock.

        Raises:
            ValueError: Process owner identity is blank.

        Returns:
            None.
        """
        if not process_owner_id.strip():
            raise ValueError("process_owner_id must not be blank")
        self.repository = repository
        self.process_owner_id = process_owner_id
        self.publisher = publisher
        self.clock = clock

    @staticmethod
    def _terminal_reason(
        task_reasons: tuple[
            StudioBenchmarkTaskRunTerminalReason | None,
            ...,
        ],
    ) -> StudioBenchmarkExperimentTerminalReason:
        """Derive only the service terminal reason from committed TaskRuns.

        Args:
            task_reasons: Stable TaskRun service terminal reasons.

        Returns:
            Conservative Experiment terminal reason.
        """
        if StudioBenchmarkTaskRunTerminalReason.INTERRUPTED in task_reasons:
            return StudioBenchmarkExperimentTerminalReason.INTERRUPTED
        if StudioBenchmarkTaskRunTerminalReason.FAILED in task_reasons:
            return StudioBenchmarkExperimentTerminalReason.FAILED
        if any(
            reason
            in {
                StudioBenchmarkTaskRunTerminalReason.CANCELLED,
                (
                    StudioBenchmarkTaskRunTerminalReason
                    .CANCELLED_BEFORE_START
                ),
            }
            for reason in task_reasons
        ):
            return StudioBenchmarkExperimentTerminalReason.CANCELLED
        return StudioBenchmarkExperimentTerminalReason.COMPLETED

    def recover(
        self,
        *,
        page_size: int = 100,
    ) -> StudioBenchmarkRecoverySummaryV1:
        """Recover all stale nonterminal aggregates to a fixed point.

        Args:
            page_size: Bounded repository page size from 1 through 100.

        Raises:
            StudioBenchmarkIntegrityError: Durable facts cannot be classified
                or publication-only recovery lacks its publisher.
            StudioBenchmarkError: A repository or publisher boundary fails.

        Returns:
            Bounded count-only recovery summary.
        """
        counts = {
            "scanned": 0,
            "requeued": 0,
            "interrupted": 0,
            "publication_only": 0,
            "finalize_only": 0,
        }
        cursor: str | None = None
        while True:
            page = self.repository.list_recovery_candidates(
                process_owner_id=self.process_owner_id,
                limit=page_size,
                cursor=cursor,
            )
            for candidate in page.items:
                counts["scanned"] += 1
                lifecycle = candidate.previous_lifecycle
                if lifecycle in {
                    StudioBenchmarkExperimentLifecycle.ACCEPTED,
                    StudioBenchmarkExperimentLifecycle.STARTING,
                }:
                    self.repository.recover_requeue(
                        candidate,
                        process_owner_id=self.process_owner_id,
                        timestamp=self.clock(),
                    )
                    counts["requeued"] += 1
                    continue
                if lifecycle in {
                    StudioBenchmarkExperimentLifecycle.RUNNING,
                    StudioBenchmarkExperimentLifecycle.CANCELLING,
                }:
                    self.repository.recover_interrupt(
                        candidate,
                        timestamp=self.clock(),
                    )
                    counts["interrupted"] += 1
                    continue
                if (
                    lifecycle
                    is not StudioBenchmarkExperimentLifecycle.FINALIZING
                ):
                    raise StudioBenchmarkIntegrityError(
                        "benchmark.recovery.lifecycle_unknown",
                        "Benchmark recovery lifecycle cannot be classified",
                    )
                has_result = any(
                    task.result_availability
                    is StudioBenchmarkAvailability.AVAILABLE
                    for task in candidate.task_runs
                )
                decision = (
                    StudioBenchmarkRecoveryDecision.PUBLICATION_ONLY
                    if has_result and not candidate.publication_committed
                    else StudioBenchmarkRecoveryDecision.FINALIZE_ONLY
                )
                claimed = self.repository.claim_finalizing_recovery(
                    candidate,
                    process_owner_id=self.process_owner_id,
                    decision=decision,
                    timestamp=self.clock(),
                )
                if (
                    decision
                    is StudioBenchmarkRecoveryDecision.PUBLICATION_ONLY
                ):
                    if self.publisher is None:
                        raise StudioBenchmarkIntegrityError(
                            "benchmark.recovery.publisher_unavailable",
                            "Benchmark publication recovery is unavailable",
                        )
                    task = next(
                        (
                            item
                            for item in claimed.task_runs
                            if item.result_availability
                            is StudioBenchmarkAvailability.AVAILABLE
                        ),
                        None,
                    )
                    if task is None:
                        raise StudioBenchmarkIntegrityError(
                            "benchmark.recovery.result_missing",
                            "Benchmark publication recovery result is missing",
                        )
                    self.publisher.publish(
                        candidate.experiment_id,
                        task.task_run_id,
                        timestamp=self.clock(),
                    )
                    counts["publication_only"] += 1
                else:
                    counts["finalize_only"] += 1
                self.repository.finalize_experiment(
                    candidate.experiment_id,
                    process_owner_id=self.process_owner_id,
                    terminal_reason=self._terminal_reason(
                        tuple(
                            item.terminal_reason
                            for item in claimed.task_runs
                        )
                    ),
                    timestamp=self.clock(),
                )
            if page.next_cursor is None:
                break
            cursor = page.next_cursor
        return StudioBenchmarkRecoverySummaryV1(**counts)


__all__ = [
    "LocalBenchmarkRecoveryOwnership",
    "StudioBenchmarkStartupRecovery",
]
