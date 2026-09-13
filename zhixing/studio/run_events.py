"""Durable-first event journal services and bounded waiter coordination."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from zhixing.components import RunEvent
from zhixing.runtime import SimpleCancellationSignal

from .run_errors import StudioRunValidationError
from .event_waiters import BoundedEventWaiterRegistry
from .run_models import (
    StudioRunEventDraftV1,
    StudioRunEventEnvelopeV1,
    StudioRunEventPageV1,
    runtime_event_draft,
)
from .run_protocols import StudioRunEventRepository
from .run_safety import sanitize_runtime_value


class RunEventNotifier(BoundedEventWaiterRegistry):
    """Per-Run condition registry used only to reduce journal polling latency."""

    def __init__(self, *, max_run_conditions: int = 1000) -> None:
        """Create one bounded condition registry.

        Args:
            max_run_conditions (int): Largest number of remembered Run keys.

        Raises:
            ValueError: Limit is not positive.

        Returns:
            None.
        """
        super().__init__(
            max_conditions=max_run_conditions,
            scope_label="Run",
        )


class DurableRunEventService:
    """Persist events before notifying any live transport consumer."""

    def __init__(
        self,
        repository: StudioRunEventRepository,
        *,
        notifier: RunEventNotifier | None = None,
        runtime_draft_builder: Callable[
            [RunEvent],
            StudioRunEventDraftV1,
        ]
        | None = None,
    ) -> None:
        """Bind one journal repository and local notification accelerator.

        Args:
            repository (StudioRunEventRepository): Durable event source.
            notifier (RunEventNotifier | None): Optional shared waiter registry.
            runtime_draft_builder (Callable[[RunEvent], StudioRunEventDraftV1] | None):
                Optional artifact-enriching Runtime event adapter.

        Raises:
            None.

        Returns:
            None.
        """
        self.repository = repository
        self.notifier = notifier or RunEventNotifier()
        self.runtime_draft_builder = runtime_draft_builder or runtime_event_draft

    @staticmethod
    def service_event(
        *,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        source: str = "service",
        event_id: str | None = None,
        timestamp: float | None = None,
    ) -> StudioRunEventDraftV1:
        """Build one bounded service-owned event draft.

        Args:
            kind (str): Stable event kind.
            payload (Mapping[str, Any] | None): Safeable event facts.
            source (str): Event source domain.
            event_id (str | None): Optional explicit idempotency identity.
            timestamp (float | None): Optional deterministic event timestamp.

        Raises:
            StudioRunValidationError: Event fields violate the strict DTO.

        Returns:
            StudioRunEventDraftV1: Strict journal draft.
        """
        safe = sanitize_runtime_value(dict(payload or {})).value
        safe_payload = safe if isinstance(safe, dict) else {"value": safe}
        if event_id is None:
            encoded = json.dumps(
                {"kind": kind, "payload": safe_payload},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            event_id = f"service-{hashlib.sha256(encoded).hexdigest()[:32]}"
        try:
            return StudioRunEventDraftV1(
                event_id=event_id,
                timestamp=time.time() if timestamp is None else timestamp,
                source=source,
                kind=kind,
                payload=safe_payload,
            )
        except ValidationError as error:
            raise StudioRunValidationError(
                "studio.run.event_invalid",
                "Studio Run event is invalid",
            ) from error

    def append(
        self,
        run_id: str,
        draft: StudioRunEventDraftV1,
    ) -> StudioRunEventEnvelopeV1:
        """Commit one event and only then wake live waiters.

        Args:
            run_id (str): Owning Run identity.
            draft (StudioRunEventDraftV1): Strict event draft.

        Raises:
            StudioRunError: Journal commit fails.
            RuntimeError: Waiter registry is at capacity after a successful commit.

        Returns:
            StudioRunEventEnvelopeV1: Persisted envelope.
        """
        envelope, created = self.repository.append_event(run_id, draft)
        if created:
            self.notifier.notify(run_id)
        return envelope

    def append_runtime(
        self,
        run_id: str,
        event: RunEvent,
    ) -> StudioRunEventEnvelopeV1:
        """Commit one canonical Runtime event into the journal.

        Args:
            run_id (str): Owning Run identity.
            event (RunEvent): Runtime event.

        Raises:
            StudioRunValidationError: Event run identity disagrees.
            StudioRunError: Journal commit fails.

        Returns:
            StudioRunEventEnvelopeV1: Persisted envelope.
        """
        if event.run_id != run_id:
            raise StudioRunValidationError(
                "studio.run.event_run_mismatch",
                "Runtime event belongs to a different Run",
            )
        return self.append(run_id, self.runtime_draft_builder(event))

    def runtime_sink(
        self,
        run_id: str,
        cancellation: SimpleCancellationSignal,
    ) -> Callable[[RunEvent], None]:
        """Create a durable-first RuntimeContext event sink.

        Args:
            run_id (str): Owning Run identity.
            cancellation (SimpleCancellationSignal): Signal requested on failure.

        Raises:
            None.

        Returns:
            Callable[[RunEvent], None]: Sink that propagates append failures.
        """

        def sink(event: RunEvent) -> None:
            """Persist one event and cancel execution if persistence fails.

            Args:
                event (RunEvent): Runtime event.

            Raises:
                Exception: Journal failures intentionally propagate to Runtime.

            Returns:
                None.
            """
            try:
                self.append_runtime(run_id, event)
            except Exception:
                cancellation.cancel()
                raise

        return sink

    def query(
        self,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioRunEventPageV1:
        """Read one bounded durable event page.

        Args:
            run_id (str): Owning Run identity.
            after (int): Exclusive journal cursor.
            limit (int): Maximum returned events.

        Raises:
            StudioRunError: Query or cursor validation fails.

        Returns:
            StudioRunEventPageV1: Ordered durable page.
        """
        return self.repository.query_events(run_id, after=after, limit=limit)

    def wait_for_events(
        self,
        run_id: str,
        *,
        after: int,
        limit: int = 100,
        timeout: float = 15.0,
    ) -> StudioRunEventPageV1:
        """Return immediately for backfill or wait once for a new commit.

        Args:
            run_id (str): Owning Run identity.
            after (int): Exclusive journal cursor.
            limit (int): Maximum returned events.
            timeout (float): Heartbeat wait in seconds.

        Raises:
            StudioRunError: Query fails.
            ValueError: Timeout is unsafe.

        Returns:
            StudioRunEventPageV1: Current or newly committed event page.
        """
        page = self.query(run_id, after=after, limit=limit)
        if page.items or page.terminal:
            return page
        self.notifier.wait(run_id, timeout=timeout)
        return self.query(run_id, after=after, limit=limit)


__all__ = ["DurableRunEventService", "RunEventNotifier"]
