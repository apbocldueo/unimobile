"""Contracts and SQLite persistence tests for Studio Run resources."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.database import STUDIO_SQLITE_SCHEMA_VERSION
from zhixing.studio.run_errors import (
    StudioRunArtifactNotFoundError,
    StudioRunConflictError,
    StudioRunValidationError,
)
from zhixing.studio.run_events import DurableRunEventService
from zhixing.studio.run_models import (
    CreateStudioRunRequestV1,
    RunEvidenceAvailability,
    StudioRunArtifactDescriptorV1,
    StudioRunArtifactRecordV1,
    StudioRunEventDraftV1,
    StudioRunEventEnvelopeV1,
    StudioRunEventPageV1,
    StudioRunLifecycle,
    StudioRunRecordV1,
    StudioRunResultSummaryV1,
    canonical_run_request_fingerprint,
    run_event_fingerprint,
)
from zhixing.studio.run_repository import SQLiteStudioRunRepository
from zhixing.studio.run_service import StudioRunApplicationService
from zhixing.studio.flow_template_loader import get_flow_template_document

class FakeRunBackend:
    """Small in-memory protocol fake without SQLite-specific concepts."""

    def __init__(self) -> None:
        """Create an empty Run and event store.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.record: StudioRunRecordV1 | None = None
        self.events: list[StudioRunEventEnvelopeV1] = []

    def create_run(
        self,
        request,
        snapshot,
        *,
        process_owner_id,
    ):
        """Create one strict in-memory accepted Run.

        Args:
            request (CreateStudioRunRequestV1): Strict request.
            snapshot (RunSnapshotV1): Immutable snapshot.
            process_owner_id (str): Owning process identity.

        Raises:
            None.

        Returns:
            tuple[StudioRunRecordV1, bool]: Record and created flag.
        """
        if self.record is not None:
            return self.record, False
        now = int(time.time() * 1000)
        self.record = StudioRunRecordV1(
            runId="run-" + "f" * 32,
            clientRequestId=request.client_request_id,
            requestFingerprint=canonical_run_request_fingerprint(request),
            request=request,
            snapshot=snapshot,
            lifecycle="accepted",
            processOwnerId=process_owner_id,
            acceptedAt=now,
            updatedAt=now,
        )
        return self.record, True

    def get_run(self, run_id):
        """Return the in-memory record.

        Args:
            run_id (str): Expected Run identity.

        Raises:
            AssertionError: Identity is inconsistent.

        Returns:
            StudioRunRecordV1: Current record.
        """
        assert self.record is not None and self.record.run_id == run_id
        return self.record

    def request_cancel(self, run_id):
        """Apply one idempotent in-memory cancellation request.

        Args:
            run_id (str): Expected Run identity.

        Raises:
            AssertionError: Identity is inconsistent.

        Returns:
            StudioRunRecordV1: Updated record.
        """
        record = self.get_run(run_id)
        self.record = record.model_copy(
            update={
                "lifecycle": StudioRunLifecycle.CANCELLING,
                "cancellation_requested": True,
            }
        )
        return self.record

    def append_event(self, run_id, event):
        """Append one sequential in-memory event.

        Args:
            run_id (str): Expected Run identity.
            event (StudioRunEventDraftV1): Event draft.

        Raises:
            AssertionError: Identity is inconsistent.

        Returns:
            tuple[StudioRunEventEnvelopeV1, bool]: Envelope and created flag.
        """
        self.get_run(run_id)
        envelope = StudioRunEventEnvelopeV1(
            **event.model_dump(mode="python"),
            runId=run_id,
            sequence=len(self.events) + 1,
            fingerprint=run_event_fingerprint(event),
        )
        self.events.append(envelope)
        return envelope, True

    def query_events(self, run_id, *, after=0, limit=100):
        """Return one bounded in-memory event page.

        Args:
            run_id (str): Expected Run identity.
            after (int): Exclusive cursor.
            limit (int): Page size.

        Raises:
            AssertionError: Identity is inconsistent.

        Returns:
            StudioRunEventPageV1: Ordered page.
        """
        record = self.get_run(run_id)
        items = tuple(self.events[after : after + limit])
        cursor = items[-1].sequence if items else after
        return StudioRunEventPageV1(
            runId=run_id,
            items=items,
            nextCursor=cursor,
            highWaterMark=len(self.events),
            terminal=(
                record.lifecycle is StudioRunLifecycle.TERMINAL
                and cursor == len(self.events)
            ),
        )

    def high_water_mark(self, run_id):
        """Return the in-memory event count.

        Args:
            run_id (str): Expected Run identity.

        Raises:
            AssertionError: Identity is inconsistent.

        Returns:
            int: Event count.
        """
        self.get_run(run_id)
        return len(self.events)


def _run_service(
    database: Path,
) -> tuple[
    StudioRunApplicationService,
    SQLiteStudioRunRepository,
    str,
    str,
]:
    """Create a valid Agent revision and Run service over one database.

    Args:
        database (Path): Temporary SQLite path.

    Raises:
        sqlite3.Error: Migration or persistence fails.

    Returns:
        tuple: Run service, repository, Agent identity, and revision identity.
    """
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents)
    agent, revision = authoring.create_agent(
        "Run fixture",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    runs = SQLiteStudioRunRepository(database)
    events = DurableRunEventService(runs)
    return (
        StudioRunApplicationService(
            agents=agents,
            runs=runs,
            events=events,
            process_owner_id="process-test",
            contract_catalog=catalog.node_contract_catalog(),
            component_catalog=catalog,
        ),
        runs,
        agent.agent_id,
        revision.revision_id,
    )


def _request(agent_id: str, revision_id: str, request_id: str = "request-1") -> dict:
    """Build one strict ordinary Run request mapping.

    Args:
        agent_id (str): Fixture Agent identity.
        revision_id (str): Fixture revision identity.
        request_id (str): Idempotency identity.

    Raises:
        None.

    Returns:
        dict: JSON-style create request.
    """
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "agentId": agent_id,
        "revisionId": revision_id,
        "task": {
            "text": "Open Settings",
            "metadata": {"researchTag": "fixture"},
        },
        "deviceProfileId": "local-android",
    }


def test_run_request_round_trip_and_fingerprint_are_deterministic() -> None:
    """Keep the public request strict, camel-cased, and canonically hashable."""
    first = CreateStudioRunRequestV1.model_validate(
        {
            "clientRequestId": "request-1",
            "agentId": "agent-1",
            "revisionId": "revision-1",
            "task": {"text": "hello", "metadata": {"b": 2, "a": 1}},
        }
    )
    second = CreateStudioRunRequestV1.model_validate(
        {
            "revisionId": "revision-1",
            "agentId": "agent-1",
            "clientRequestId": "request-1",
            "task": {"metadata": {"a": 1, "b": 2}, "text": "hello"},
        }
    )
    assert canonical_run_request_fingerprint(first) == canonical_run_request_fingerprint(
        second
    )
    payload = first.model_dump(mode="json", by_alias=True)
    assert payload["schemaVersion"] == 1
    assert "databasePath" not in payload


@pytest.mark.parametrize(
    "task",
    (
        {"text": "   "},
        {"text": "x", "metadata": {"apiKey": "secret-canary"}},
        {"text": "x", "metadata": {"deviceSerial": "emulator-5554"}},
        {"text": "x", "metadata": {"source": "/Users/private/data.json"}},
        {
            "text": "x",
            "metadata": {"taskId": "b-1", "evaluation": {"type": "match"}},
        },
        {"text": "x", "metadata": {"live": object()}},
    ),
)
def test_run_request_rejects_unsafe_or_benchmark_shaped_input(task) -> None:
    """Reject unsafe ordinary-task metadata before any persistence boundary."""
    with pytest.raises(ValueError):
        CreateStudioRunRequestV1.model_validate(
            {
                "clientRequestId": "request-1",
                "agentId": "agent-1",
                "revisionId": "revision-1",
                "task": task,
            }
        )


def test_run_request_rejects_unsupported_runtime_kind() -> None:
    """Reject non-Android Stage 3 execution before persistence."""
    with pytest.raises(ValueError):
        CreateStudioRunRequestV1.model_validate(
            {
                "clientRequestId": "request-harmony",
                "agentId": "agent-1",
                "revisionId": "revision-1",
                "task": {"text": "Open Settings"},
                "runtimeKind": "harmony",
            }
        )


def test_run_creation_binds_immutable_valid_revision(tmp_path) -> None:
    """Persist a self-contained snapshot that does not follow later revisions."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    resource, created = service.create_run(_request(agent_id, revision_id))
    assert created is True
    record = repository.get_run(resource.run_id)
    assert record.snapshot.revision_id == revision_id
    assert record.snapshot.agent_graph
    assert record.snapshot.canonical_hash == resource.canonical_hash
    assert record.lifecycle is StudioRunLifecycle.ACCEPTED
    assert repository.high_water_mark(record.run_id) == 1

    restarted = SQLiteStudioRunRepository(tmp_path / "studio.sqlite3")
    assert restarted.get_run(record.run_id) == record


def test_invalid_revision_is_rejected_without_run_row(tmp_path) -> None:
    """Require a valid compiled saved revision before creating a Run."""
    database = tmp_path / "studio.sqlite3"
    catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(catalog=catalog, repository=agents)
    agent, revision = authoring.create_agent("Invalid draft")
    runs = SQLiteStudioRunRepository(database)
    service = StudioRunApplicationService(
        agents=agents,
        runs=runs,
        events=DurableRunEventService(runs),
        process_owner_id="process-test",
        contract_catalog=catalog.node_contract_catalog(),
        component_catalog=catalog,
    )
    with pytest.raises(StudioRunValidationError) as captured:
        service.create_run(_request(agent.agent_id, revision.revision_id))
    assert captured.value.code == "studio.policy.graph_invalid"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM studio_runs").fetchone()[0] == 0


def test_idempotent_create_and_conflicting_content(tmp_path) -> None:
    """Return one Run for retried content and reject key reuse with new content."""
    service, _repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    first, created = service.create_run(_request(agent_id, revision_id))
    second, repeated = service.create_run(_request(agent_id, revision_id))
    assert created is True
    assert repeated is False
    assert first.run_id == second.run_id

    changed = _request(agent_id, revision_id)
    changed["task"]["text"] = "Different task"
    with pytest.raises(StudioRunConflictError) as captured:
        service.create_run(changed)
    assert captured.value.code == "studio.run.idempotency_conflict"


def test_lifecycle_cancel_terminal_and_recovery_queries(tmp_path) -> None:
    """Apply CAS transitions, idempotent cancellation, and immutable terminal result."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    resource, _created = service.create_run(_request(agent_id, revision_id))
    repository.transition(
        resource.run_id,
        expected=(StudioRunLifecycle.ACCEPTED,),
        target=StudioRunLifecycle.STARTING,
    )
    repository.transition(
        resource.run_id,
        expected=(StudioRunLifecycle.STARTING,),
        target=StudioRunLifecycle.RUNNING,
    )
    cancelled = repository.request_cancel(resource.run_id)
    assert cancelled.lifecycle is StudioRunLifecycle.CANCELLING
    assert repository.request_cancel(resource.run_id) == cancelled

    result = StudioRunResultSummaryV1(
        status="cancelled",
        kernel_status="cancelled",
    )
    terminal, won = repository.finish_run(
        resource.run_id,
        result,
        expected=(StudioRunLifecycle.CANCELLING,),
    )
    repeated, won_again = repository.finish_run(
        resource.run_id,
        StudioRunResultSummaryV1(status="failure"),
        expected=(StudioRunLifecycle.CANCELLING,),
    )
    assert won is True
    assert won_again is False
    assert repeated == terminal
    assert terminal.result == result
    assert repository.list_nonterminal_for_other_owner("another-process") == ()


def test_event_journal_is_idempotent_continuous_and_bounded(tmp_path) -> None:
    """Persist one sequence domain with duplicate and cursor safeguards."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    resource, _created = service.create_run(_request(agent_id, revision_id))
    draft = StudioRunEventDraftV1(
        eventId="service-second",
        timestamp=1.0,
        source="service",
        kind="run.starting",
        payload={"state": "starting"},
    )
    first, created = repository.append_event(resource.run_id, draft)
    repeated, created_again = repository.append_event(resource.run_id, draft)
    assert created is True
    assert created_again is False
    assert repeated == first
    assert first.sequence == 2

    with pytest.raises(StudioRunConflictError):
        repository.append_event(
            resource.run_id,
            draft.model_copy(update={"payload": {"state": "different"}}),
        )
    page = repository.query_events(resource.run_id, after=0, limit=1)
    assert [item.sequence for item in page.items] == [1]
    next_page = repository.query_events(
        resource.run_id,
        after=page.next_cursor,
        limit=10,
    )
    assert [item.sequence for item in next_page.items] == [2]
    with pytest.raises(StudioRunValidationError):
        repository.query_events(resource.run_id, after=99)


def test_artifact_repository_is_run_scoped_and_storage_neutral(tmp_path) -> None:
    """Keep opaque artifact ownership and internal refs out of public descriptors."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    first, _ = service.create_run(_request(agent_id, revision_id, "request-1"))
    second, _ = service.create_run(_request(agent_id, revision_id, "request-2"))
    descriptor = StudioRunArtifactDescriptorV1(
        artifactId="artifact-" + "a" * 32,
        kind="screenshot",
        availability="available",
        contentType="image/png",
        size=3,
        sha256="sha256:" + "b" * 64,
        provenance="fixture",
    )
    repository.put_artifact(
        StudioRunArtifactRecordV1(
            runId=first.run_id,
            descriptor=descriptor,
            storageRef=f"runs/{first.run_id}/artifacts/{descriptor.artifact_id}",
        )
    )
    assert repository.get_artifact(first.run_id, descriptor.artifact_id).descriptor == descriptor
    with pytest.raises(StudioRunArtifactNotFoundError):
        repository.get_artifact(second.run_id, descriptor.artifact_id)
    changed = repository.update_artifact_availability(
        first.run_id,
        descriptor.artifact_id,
        RunEvidenceAvailability.CORRUPT,
    )
    assert changed.descriptor.availability is RunEvidenceAvailability.CORRUPT
    public = descriptor.model_dump(mode="json", by_alias=True)
    assert "storageRef" not in public
    assert "databasePath" not in public


def test_repository_concurrency_gap_detection_and_migration_reentry(
    tmp_path,
) -> None:
    """Cover concurrent idempotency, terminal CAS, gaps, and migration reentry."""
    database = tmp_path / "studio.sqlite3"
    service, repository, agent_id, revision_id = _run_service(database)
    barrier = threading.Barrier(3)
    creations: list[tuple[str, bool]] = []
    failures: list[Exception] = []

    def create() -> None:
        """Race one idempotent create call.

        Args:
            None.

        Raises:
            None: Failures are retained for the parent assertion.

        Returns:
            None.
        """
        barrier.wait(timeout=3)
        try:
            resource, created = service.create_run(
                _request(agent_id, revision_id, "request-race")
            )
            creations.append((resource.run_id, created))
        except Exception as error:
            failures.append(error)

    threads = [threading.Thread(target=create) for _ in range(2)]
    for thread in threads:
        thread.start()
    barrier.wait(timeout=3)
    for thread in threads:
        thread.join(timeout=3)
    assert failures == []
    assert len({identity for identity, _created in creations}) == 1
    assert sorted(created for _identity, created in creations) == [False, True]

    run_id = creations[0][0]
    terminal_barrier = threading.Barrier(3)
    terminal_results: list[tuple[str, bool]] = []

    def finish(status: str) -> None:
        """Race one terminal compare-and-swap.

        Args:
            status (str): Candidate result status.

        Raises:
            None.

        Returns:
            None.
        """
        terminal_barrier.wait(timeout=3)
        record, won = repository.finish_run(
            run_id,
            StudioRunResultSummaryV1(status=status),
            expected=(StudioRunLifecycle.ACCEPTED,),
        )
        assert record.result is not None
        terminal_results.append((record.result.status, won))

    finishers = [
        threading.Thread(target=finish, args=("success",)),
        threading.Thread(target=finish, args=("failure",)),
    ]
    for thread in finishers:
        thread.start()
    terminal_barrier.wait(timeout=3)
    for thread in finishers:
        thread.join(timeout=3)
    assert sum(won for _status, won in terminal_results) == 1
    assert len({status for status, _won in terminal_results}) == 1

    gap_service, gap_repo, gap_agent, gap_revision = _run_service(
        tmp_path / "gap.sqlite3"
    )
    gap_run, _ = gap_service.create_run(
        _request(gap_agent, gap_revision, "gap-run")
    )
    for index in range(2):
        gap_repo.append_event(
            gap_run.run_id,
            StudioRunEventDraftV1(
                eventId=f"gap-{index}",
                timestamp=float(index),
                source="service",
                kind="fixture",
            ),
        )
    with sqlite3.connect(tmp_path / "gap.sqlite3") as connection:
        connection.execute(
            "DELETE FROM studio_run_events WHERE run_id = ? AND sequence = 2",
            (gap_run.run_id,),
        )
    with pytest.raises(StudioRunConflictError) as captured:
        gap_repo.query_events(gap_run.run_id, after=0, limit=10)
    assert captured.value.code == "studio.run.event_sequence_gap"

    SQLiteStudioRunRepository(database)
    SQLiteStudioRunRepository(database)
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))


def test_run_application_uses_protocol_fake_and_public_dtos_are_storage_neutral(
    tmp_path,
) -> None:
    """Prove application behavior without SQLite Run rows or adapter fields."""
    source, _repository, agent_id, revision_id = _run_service(
        tmp_path / "agents.sqlite3"
    )
    fake = FakeRunBackend()
    service = StudioRunApplicationService(
        agents=source.agents,
        runs=fake,
        events=DurableRunEventService(fake),
        process_owner_id="fake-process",
        contract_catalog=source.contract_catalog,
    )
    resource, created = service.create_run(
        _request(agent_id, revision_id, "fake-request")
    )
    assert created is True
    assert service.get_run(resource.run_id) == resource
    cancelled = service.cancel_run(resource.run_id)
    assert cancelled.lifecycle is StudioRunLifecycle.CANCELLING
    serialized = json.dumps(
        {
            "resource": cancelled.model_dump(mode="json", by_alias=True),
            "events": service.query_events(
                resource.run_id,
                after=0,
            ).model_dump(mode="json", by_alias=True),
        }
    ).lower()
    for forbidden in ("sqlite", "databasepath", "storage_ref", "rowid", "sql"):
        assert forbidden not in serialized
