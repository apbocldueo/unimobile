"""Application service for immutable revision-bound Studio Run resources."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pydantic import ValidationError

from .repository import (
    AgentDocumentRepository,
    AgentRevisionNotFoundError,
)
from .catalog import StudioComponentCatalog
from .revision_verifier import verify_immutable_agent_revision
from .run_errors import StudioRunConflictError, StudioRunValidationError
from .run_events import DurableRunEventService
from .run_models import (
    CreateStudioRunRequestV1,
    RunSnapshotV1,
    StudioRunEventPageV1,
    StudioRunLifecycle,
    StudioRunRecordV1,
    StudioRunResourceV1,
    canonical_run_request_fingerprint,
)
from .run_protocols import RunScheduler, StudioRunRepository
from .readiness import StudioRuntimeReadinessService


class StudioRunApplicationService:
    """Orchestrate Run creation, query, cancellation, and durable events."""

    def __init__(
        self,
        *,
        agents: AgentDocumentRepository,
        runs: StudioRunRepository,
        events: DurableRunEventService,
        process_owner_id: str,
        contract_catalog: Any | None = None,
        component_catalog: StudioComponentCatalog | None = None,
        scheduler: RunScheduler | None = None,
        execute: Callable[[str], None] | None = None,
        cancel_active: Callable[[str], None] | None = None,
        schedule_rejected: Callable[[str, Exception], None] | None = None,
        readiness: StudioRuntimeReadinessService | None = None,
    ) -> None:
        """Configure explicit authoring, persistence, and execution boundaries.

        Args:
            agents (AgentDocumentRepository): Immutable revision source.
            runs (StudioRunRepository): Run persistence boundary.
            events (DurableRunEventService): Durable event service.
            process_owner_id (str): Current service process identity.
            contract_catalog (Any | None): Optional extension NodeContract catalog.
            component_catalog: Exact safe Component Catalog for policy checks.
            scheduler (RunScheduler | None): Optional bounded scheduler.
            execute (Callable[[str], None] | None): Persisted Run worker callback.
            cancel_active (Callable[[str], None] | None): In-memory signal callback.
            schedule_rejected (Callable[[str, Exception], None] | None):
                Terminal finalizer for bounded scheduler rejection.
            readiness: Optional static readiness gate for new commands.

        Raises:
            ValueError: Scheduler and execute callback are configured separately.

        Returns:
            None.
        """
        if (scheduler is None) != (execute is None):
            raise ValueError("scheduler and execute must be configured together")
        self.agents = agents
        self.runs = runs
        self.events = events
        self.process_owner_id = str(process_owner_id)
        self.contract_catalog = contract_catalog
        self.component_catalog = component_catalog
        self.scheduler = scheduler
        self.execute = execute
        self.cancel_active = cancel_active
        self.schedule_rejected = schedule_rejected
        self.readiness = readiness

    @staticmethod
    def parse_create_request(raw: Mapping[str, Any]) -> CreateStudioRunRequestV1:
        """Parse an untrusted HTTP mapping into the strict create DTO.

        Args:
            raw (Mapping[str, Any]): Untrusted request mapping.

        Raises:
            StudioRunValidationError: Request violates the public contract.

        Returns:
            CreateStudioRunRequestV1: Strict immutable request.
        """
        try:
            return CreateStudioRunRequestV1.model_validate(dict(raw))
        except ValidationError as error:
            first = error.errors(include_url=False)[0]
            location = ".".join(str(item) for item in first["loc"])
            raise StudioRunValidationError(
                "studio.run.request_invalid",
                f"Invalid Studio Run request at {location}: {first['msg']}",
            ) from error

    def snapshot_for_request(
        self,
        request: CreateStudioRunRequestV1,
    ) -> RunSnapshotV1:
        """Load and re-verify one valid immutable revision.

        Args:
            request (CreateStudioRunRequestV1): Strict Run create request.

        Raises:
            StudioRunValidationError: Revision is invalid or graph identity differs.
            AgentRevisionNotFoundError: Revision is absent.

        Returns:
            RunSnapshotV1: Self-contained immutable Run snapshot.
        """
        return verify_immutable_agent_revision(
            self.agents,
            request.agent_id,
            request.revision_id,
            contract_catalog=self.contract_catalog,
            component_catalog=self.component_catalog,
        )

    def create_run(
        self,
        raw: Mapping[str, Any] | CreateStudioRunRequestV1,
    ) -> tuple[StudioRunResourceV1, bool]:
        """Persist and optionally schedule one idempotent Studio Run.

        Args:
            raw (Mapping[str, Any] | CreateStudioRunRequestV1): Request DTO or
                untrusted mapping.

        Raises:
            StudioRunValidationError: Request or revision is invalid.
            StudioRunConflictError: Idempotency content conflicts.
            AgentRevisionNotFoundError: Revision is absent.

        Returns:
            tuple[StudioRunResourceV1, bool]: Public resource and created flag.
        """
        request = (
            raw
            if isinstance(raw, CreateStudioRunRequestV1)
            else self.parse_create_request(raw)
        )
        existing = self._existing_request(request.client_request_id)
        if existing is not None:
            if existing.request_fingerprint != canonical_run_request_fingerprint(request):
                raise StudioRunConflictError(
                    "studio.run.idempotency_conflict",
                    "Client request identity was used for different content",
                )
            return self._resource(existing), False
        snapshot = self.snapshot_for_request(request)
        if self.readiness is not None:
            readiness = self.readiness.snapshot_readiness(
                snapshot,
                request.device_profile_id,
            )
            if not readiness.ready:
                # A same-command accept may have won between the first lookup
                # and static validation; preserve idempotency before rejecting.
                raced = self._existing_request(request.client_request_id)
                if raced is not None:
                    if raced.request_fingerprint != canonical_run_request_fingerprint(
                        request
                    ):
                        raise StudioRunConflictError(
                            "studio.run.idempotency_conflict",
                            "Client request identity was used for different content",
                        )
                    return self._resource(raced), False
                issue = readiness.diagnostics[0]
                raise StudioRunValidationError(issue.code, issue.message)
        record, created = self.runs.create_run(
            request,
            snapshot,
            process_owner_id=self.process_owner_id,
        )
        if created:
            self.events.append(
                record.run_id,
                self.events.service_event(
                    kind="run.accepted",
                    event_id="service-run-accepted",
                    payload={
                        "agentId": snapshot.agent_id,
                        "revisionId": snapshot.revision_id,
                        "canonicalHash": snapshot.canonical_hash,
                    },
                ),
            )
            if self.scheduler is not None and self.execute is not None:
                try:
                    self.scheduler.submit(record.run_id, self.execute)
                except Exception as error:
                    if self.schedule_rejected is None:
                        raise
                    self.schedule_rejected(record.run_id, error)
                    record = self.runs.get_run(record.run_id)
        return self._resource(record), created

    def _existing_request(self, client_request_id: str) -> StudioRunRecordV1 | None:
        """Look up an accepted idempotency identity when the repository supports it.

        Args:
            client_request_id: Stable client command identity.

        Raises:
            StudioRunError: Repository lookup fails.

        Returns:
            StudioRunRecordV1 | None: Existing record or no prior acceptance.
        """
        lookup = getattr(self.runs, "get_by_client_request_id", None)
        return lookup(client_request_id) if callable(lookup) else None

    def _resource(self, record: StudioRunRecordV1) -> StudioRunResourceV1:
        """Project one record with its committed event high-water mark.

        Args:
            record (StudioRunRecordV1): Internal Run record.

        Raises:
            StudioRunError: Event query fails.

        Returns:
            StudioRunResourceV1: Public resource.
        """
        return StudioRunResourceV1.from_record(
            record,
            event_high_water_mark=self.events.repository.high_water_mark(
                record.run_id
            ),
        )

    def get_run(self, run_id: str) -> StudioRunResourceV1:
        """Read one safe public Run resource.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.

        Returns:
            StudioRunResourceV1: Current public resource.
        """
        return self._resource(self.runs.get_run(run_id))

    def cancel_run(self, run_id: str) -> StudioRunResourceV1:
        """Persist and signal an idempotent cooperative cancellation request.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.

        Returns:
            StudioRunResourceV1: Updated or existing terminal resource.
        """
        before = self.runs.get_run(run_id)
        record = self.runs.request_cancel(run_id)
        if (
            before.lifecycle is not StudioRunLifecycle.TERMINAL
            and before.lifecycle is not StudioRunLifecycle.CANCELLING
        ):
            self.events.append(
                run_id,
                self.events.service_event(
                    kind="run.cancellation_requested",
                    event_id="service-run-cancellation-requested",
                    payload={"cooperative": True},
                ),
            )
        if self.cancel_active is not None:
            self.cancel_active(run_id)
        return self._resource(record)

    def query_events(
        self,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioRunEventPageV1:
        """Read a bounded durable event page for one Run.

        Args:
            run_id (str): Stable Run identity.
            after (int): Exclusive journal cursor.
            limit (int): Maximum returned events.

        Raises:
            StudioRunError: Run, cursor, or journal is invalid.

        Returns:
            StudioRunEventPageV1: Ordered event page.
        """
        return self.events.query(run_id, after=after, limit=limit)


__all__ = ["StudioRunApplicationService"]
