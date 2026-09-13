"""Durable journal ordering, waiter isolation, and local burst boundaries."""

from __future__ import annotations

import threading
import time

import pytest

from zhixing.components import RunEvent
from zhixing.runtime import SimpleCancellationSignal
from zhixing.studio.run_events import (
    DurableRunEventService,
    RunEventNotifier,
)
from zhixing.studio.run_models import StudioRunEventDraftV1

from .test_run_models_repository import _request, _run_service


class CommitInspectingNotifier:
    """Test notifier that verifies persistence before notification."""

    def __init__(self, repository) -> None:
        """Bind the journal repository.

        Args:
            repository (StudioRunEventRepository): Durable source.

        Raises:
            None.

        Returns:
            None.
        """
        self.repository = repository
        self.observed_marks: list[int] = []

    def notify(self, run_id: str) -> None:
        """Record the already-committed high-water mark.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunError: Repository query fails.

        Returns:
            None.
        """
        self.observed_marks.append(self.repository.high_water_mark(run_id))

    def wait(self, run_id: str, *, timeout: float) -> None:
        """Provide the unused waiter part of the notifier contract.

        Args:
            run_id (str): Stable Run identity.
            timeout (float): Bounded timeout.

        Raises:
            None.

        Returns:
            None.
        """
        del run_id, timeout


class FailingAppendRepository:
    """Repository fake that cannot durably append an event."""

    def append_event(self, run_id, draft):
        """Raise a storage failure before any event becomes visible.

        Args:
            run_id (str): Owning Run identity.
            draft (StudioRunEventDraftV1): Candidate event draft.

        Raises:
            OSError: Always, to emulate a failed durable commit.

        Returns:
            None.
        """
        del run_id, draft
        raise OSError("journal unavailable")


def test_journal_commit_precedes_notification(tmp_path) -> None:
    """Expose a committed high-water mark to every notification callback."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    notifier = CommitInspectingNotifier(repository)
    events = DurableRunEventService(repository, notifier=notifier)
    events.append(
        run.run_id,
        StudioRunEventDraftV1(
            eventId="ordering-event",
            timestamp=1.0,
            source="service",
            kind="fixture",
        ),
    )
    assert notifier.observed_marks == [2]


def test_runtime_sink_cancels_when_durable_append_fails() -> None:
    """Stop execution when a Runtime event cannot enter the journal."""
    cancellation = SimpleCancellationSignal()
    sink = DurableRunEventService(
        FailingAppendRepository()
    ).runtime_sink(
        "run-00000000000000000000000000000000",
        cancellation,
    )
    with pytest.raises(OSError):
        sink(
            RunEvent(
                run_id="run-00000000000000000000000000000000",
                sequence=1,
                timestamp=1.0,
                phase="graph_kernel",
                role="fixture",
                component="fixture",
                kind="complete",
            )
        )
    assert cancellation.is_cancelled()


def test_slow_waiter_does_not_block_journal_commit(tmp_path) -> None:
    """Wake a local slow consumer without coupling it to append latency."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    notifier = RunEventNotifier()
    events = DurableRunEventService(repository, notifier=notifier)
    waiting = threading.Event()
    released = threading.Event()

    def wait() -> None:
        """Wait independently of the producer.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        waiting.set()
        notifier.wait(run.run_id, timeout=2)
        time.sleep(0.05)
        released.set()

    thread = threading.Thread(target=wait)
    thread.start()
    assert waiting.wait(timeout=2)
    time.sleep(0.01)
    started = time.perf_counter()
    events.append(
        run.run_id,
        StudioRunEventDraftV1(
            eventId="slow-client-event",
            timestamp=1.0,
            source="service",
            kind="fixture",
        ),
    )
    elapsed = time.perf_counter() - started
    assert elapsed < 0.5
    assert released.wait(timeout=2)
    thread.join(timeout=2)


def test_event_burst_concurrency_and_reconnect_pagination_are_bounded(
    tmp_path,
) -> None:
    """Retain a continuous journal under a representative local event burst."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    failures: list[Exception] = []
    started = time.perf_counter()

    def append_partition(partition: int) -> None:
        """Append one concurrent event partition.

        Args:
            partition (int): Stable producer identity.

        Raises:
            None: Failures are retained for the parent assertion.

        Returns:
            None.
        """
        try:
            for index in range(100):
                repository.append_event(
                    run.run_id,
                    StudioRunEventDraftV1(
                        eventId=f"burst-{partition}-{index}",
                        timestamp=float(index),
                        source="runtime",
                        kind="fixture",
                        runtimeSequence=partition * 100 + index + 1,
                    ),
                )
        except Exception as error:
            failures.append(error)

    producers = [
        threading.Thread(target=append_partition, args=(partition,))
        for partition in range(2)
    ]
    for producer in producers:
        producer.start()
    for producer in producers:
        producer.join(timeout=10)
    elapsed = time.perf_counter() - started
    assert failures == []
    assert elapsed < 10

    cursor = 0
    sequences: list[int] = []
    while cursor < repository.high_water_mark(run.run_id):
        page = repository.query_events(
            run.run_id,
            after=cursor,
            limit=37,
        )
        sequences.extend(item.sequence for item in page.items)
        cursor = page.next_cursor
    assert sequences == list(range(1, 202))
    reconnect = repository.query_events(
        run.run_id,
        after=150,
        limit=500,
    )
    assert reconnect.items[0].sequence == 151
    assert reconnect.next_cursor == 201
