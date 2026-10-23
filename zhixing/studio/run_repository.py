"""SQLite adapters for Studio Run resources, event journals, and artifacts."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from .database import connect_studio_database, migrate_studio_database
from .run_errors import (
    StudioRunArtifactNotFoundError,
    StudioRunConflictError,
    StudioRunNotFoundError,
    StudioRunValidationError,
)
from .run_models import (
    CreateStudioRunRequestV1,
    RunEvidenceAvailability,
    RunSnapshotV1,
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


def _now_ms() -> int:
    """Return the current wall-clock time in integer milliseconds.

    Args:
        None.

    Raises:
        None.

    Returns:
        int: Unix epoch milliseconds.
    """
    return time.time_ns() // 1_000_000


def _json_text(value: Any) -> str:
    """Encode compact deterministic finite JSON for SQLite.

    Args:
        value (Any): JSON-compatible value.

    Raises:
        TypeError: Value is not JSON-compatible.
        ValueError: Value contains non-finite numbers.

    Returns:
        str: Deterministic JSON text.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class SQLiteStudioRunRepository:
    """Combined SQLite implementation of the three Studio Run repositories."""

    def __init__(self, database_path: str | Path) -> None:
        """Open a migrated Studio database.

        Args:
            database_path (str | Path): Explicit workspace database path.

        Raises:
            OSError: Parent storage cannot be created.
            sqlite3.Error: Schema migration fails.

        Returns:
            None.
        """
        self._database_path = Path(database_path).expanduser()
        migrate_studio_database(self._database_path)

    @property
    def database_path(self) -> Path:
        """Return the adapter-local path for operator diagnostics.

        Args:
            None.

        Raises:
            None.

        Returns:
            Path: Configured database path, never included in public DTOs.
        """
        return self._database_path

    def _connect(self) -> sqlite3.Connection:
        """Create one short-lived configured SQLite connection.

        Args:
            None.

        Raises:
            sqlite3.Error: Connection setup fails.

        Returns:
            sqlite3.Connection: Row-enabled connection.
        """
        return connect_studio_database(self._database_path)

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> StudioRunRecordV1:
        """Convert one storage row to a strict implementation-neutral record.

        Args:
            row (sqlite3.Row): Selected `studio_runs` row.

        Raises:
            ValueError: Stored JSON violates current Run contracts.

        Returns:
            StudioRunRecordV1: Parsed Run record.
        """
        result = (
            StudioRunResultSummaryV1.model_validate(
                json.loads(row["result_json"])
            )
            if row["result_json"] is not None
            else None
        )
        return StudioRunRecordV1(
            run_id=row["run_id"],
            client_request_id=row["client_request_id"],
            request_fingerprint=row["request_fingerprint"],
            request=CreateStudioRunRequestV1.model_validate(
                json.loads(row["request_json"])
            ),
            snapshot=RunSnapshotV1.model_validate(
                json.loads(row["snapshot_json"])
            ),
            lifecycle=row["lifecycle_state"],
            cancellation_requested=bool(row["cancellation_requested"]),
            process_owner_id=row["process_owner_id"],
            accepted_at=row["accepted_at"],
            started_at=row["started_at"],
            updated_at=row["updated_at"],
            terminal_at=row["terminal_at"],
            result=result,
            replay_availability=row["replay_availability"],
            replay_error_code=row["replay_error_code"],
            storage_warnings=tuple(
                str(item)
                for item in json.loads(row["storage_warnings_json"])
            ),
        )

    @staticmethod
    def _select_run(
        connection: sqlite3.Connection,
        run_id: str,
    ) -> sqlite3.Row:
        """Select one Run row or raise the safe not-found error.

        Args:
            connection (sqlite3.Connection): Active transaction connection.
            run_id (str): Stable Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.

        Returns:
            sqlite3.Row: Selected storage row.
        """
        row = connection.execute(
            "SELECT * FROM studio_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if row is None:
            raise StudioRunNotFoundError(
                "studio.run.not_found",
                "Studio Run was not found",
            )
        return row

    def create_run(
        self,
        request: CreateStudioRunRequestV1,
        snapshot: RunSnapshotV1,
        *,
        process_owner_id: str,
    ) -> tuple[StudioRunRecordV1, bool]:
        """Create or return one idempotent persisted Run.

        Args:
            request (CreateStudioRunRequestV1): Strict create request.
            snapshot (RunSnapshotV1): Immutable verified revision snapshot.
            process_owner_id (str): Current local service process identity.

        Raises:
            StudioRunConflictError: Idempotency identity has different content.
            sqlite3.Error: Transaction fails.

        Returns:
            tuple[StudioRunRecordV1, bool]: Record and newly-created flag.
        """
        fingerprint = canonical_run_request_fingerprint(request)
        timestamp = _now_ms()
        run_id = f"run-{uuid.uuid4().hex}"
        request_json = _json_text(
            request.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        snapshot_json = _json_text(
            snapshot.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    """
                    SELECT * FROM studio_runs
                    WHERE client_request_id = ?
                    """,
                    (request.client_request_id,),
                ).fetchone()
                if existing is not None:
                    if existing["request_fingerprint"] != fingerprint:
                        raise StudioRunConflictError(
                            "studio.run.idempotency_conflict",
                            "Client request identity was used for different content",
                        )
                    connection.execute("COMMIT")
                    return self._record_from_row(existing), False
                connection.execute(
                    """
                    INSERT INTO studio_runs(
                        run_id, client_request_id, request_fingerprint,
                        agent_id, revision_id, request_json, snapshot_json,
                        lifecycle_state, cancellation_requested,
                        process_owner_id, accepted_at, updated_at,
                        replay_availability, storage_warnings_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'accepted', 0, ?, ?, ?,
                              'not_captured', '[]')
                    """,
                    (
                        run_id,
                        request.client_request_id,
                        fingerprint,
                        snapshot.agent_id,
                        snapshot.revision_id,
                        request_json,
                        snapshot_json,
                        process_owner_id,
                        timestamp,
                        timestamp,
                    ),
                )
                row = self._select_run(connection, run_id)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._record_from_row(row), True

    def get_by_client_request_id(
        self,
        client_request_id: str,
    ) -> StudioRunRecordV1 | None:
        """Read an existing idempotency identity without creating storage.

        Args:
            client_request_id: Stable client command identity.

        Raises:
            sqlite3.Error: Query execution fails.

        Returns:
            StudioRunRecordV1 | None: Existing record, if already accepted.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM studio_runs WHERE client_request_id = ?",
                (client_request_id,),
            ).fetchone()
        return self._record_from_row(row) if row is not None else None

    def get_run(self, run_id: str) -> StudioRunRecordV1:
        """Read one Run by stable identity.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Query fails.

        Returns:
            StudioRunRecordV1: Strict Run record.
        """
        with self._connect() as connection:
            return self._record_from_row(self._select_run(connection, run_id))

    def transition(
        self,
        run_id: str,
        *,
        expected: tuple[StudioRunLifecycle, ...],
        target: StudioRunLifecycle,
        process_owner_id: str | None = None,
    ) -> StudioRunRecordV1:
        """Apply one compare-and-swap nonterminal lifecycle transition.

        Args:
            run_id (str): Stable Run identity.
            expected (tuple[StudioRunLifecycle, ...]): Allowed current states.
            target (StudioRunLifecycle): Requested nonterminal target.
            process_owner_id (str | None): Optional current owner update.

        Raises:
            StudioRunConflictError: Current state is not expected or target is terminal.
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Transaction fails.

        Returns:
            StudioRunRecordV1: Updated record.
        """
        if target is StudioRunLifecycle.TERMINAL:
            raise StudioRunValidationError(
                "studio.run.transition_invalid",
                "Use finish_run for a terminal transition",
            )
        expected_values = tuple(item.value for item in expected)
        if not expected_values:
            raise StudioRunValidationError(
                "studio.run.transition_invalid",
                "At least one expected lifecycle is required",
            )
        timestamp = _now_ms()
        placeholders = ",".join("?" for _ in expected_values)
        owner_sql = ", process_owner_id = ?" if process_owner_id is not None else ""
        parameters: list[Any] = [
            target.value,
            timestamp,
            timestamp if target is StudioRunLifecycle.STARTING else None,
        ]
        if process_owner_id is not None:
            parameters.append(process_owner_id)
        parameters.extend((run_id, *expected_values))
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                cursor = connection.execute(
                    f"""
                    UPDATE studio_runs
                    SET lifecycle_state = ?, updated_at = ?,
                        started_at = COALESCE(started_at, ?)
                        {owner_sql}
                    WHERE run_id = ?
                      AND lifecycle_state IN ({placeholders})
                    """,
                    parameters,
                )
                if cursor.rowcount != 1:
                    current = self._select_run(connection, run_id)
                    raise StudioRunConflictError(
                        "studio.run.lifecycle_conflict",
                        "Studio Run lifecycle changed concurrently "
                        f"(current={current['lifecycle_state']})",
                    )
                row = self._select_run(connection, run_id)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._record_from_row(row)

    def request_cancel(self, run_id: str) -> StudioRunRecordV1:
        """Persist an idempotent cooperative cancellation request.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Transaction fails.

        Returns:
            StudioRunRecordV1: Updated or already-terminal record.
        """
        timestamp = _now_ms()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._select_run(connection, run_id)
                if current["lifecycle_state"] not in {
                    StudioRunLifecycle.TERMINAL.value,
                    StudioRunLifecycle.CANCELLING.value,
                }:
                    connection.execute(
                        """
                        UPDATE studio_runs
                        SET cancellation_requested = 1,
                            lifecycle_state = 'cancelling',
                            updated_at = ?
                        WHERE run_id = ?
                          AND lifecycle_state != 'terminal'
                        """,
                        (timestamp, run_id),
                    )
                row = self._select_run(connection, run_id)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._record_from_row(row)

    def finish_run(
        self,
        run_id: str,
        result: StudioRunResultSummaryV1,
        *,
        expected: tuple[StudioRunLifecycle, ...],
    ) -> tuple[StudioRunRecordV1, bool]:
        """Commit one immutable terminal result through compare-and-swap.

        Args:
            run_id (str): Stable Run identity.
            result (StudioRunResultSummaryV1): Safe terminal result.
            expected (tuple[StudioRunLifecycle, ...]): Allowed current states.

        Raises:
            StudioRunConflictError: Current nonterminal state is unexpected.
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Transaction fails.

        Returns:
            tuple[StudioRunRecordV1, bool]: Record and whether this call won.
        """
        expected_values = tuple(item.value for item in expected)
        timestamp = _now_ms()
        result_json = _json_text(
            result.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                current = self._select_run(connection, run_id)
                if current["lifecycle_state"] == StudioRunLifecycle.TERMINAL.value:
                    connection.execute("COMMIT")
                    return self._record_from_row(current), False
                if current["lifecycle_state"] not in expected_values:
                    raise StudioRunConflictError(
                        "studio.run.lifecycle_conflict",
                        "Studio Run cannot terminate from its current lifecycle",
                    )
                connection.execute(
                    """
                    UPDATE studio_runs
                    SET lifecycle_state = 'terminal',
                        result_json = ?,
                        terminal_at = ?,
                        updated_at = ?
                    WHERE run_id = ?
                    """,
                    (result_json, timestamp, timestamp, run_id),
                )
                row = self._select_run(connection, run_id)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self._record_from_row(row), True

    def set_replay_availability(
        self,
        run_id: str,
        availability: RunEvidenceAvailability,
        *,
        error_code: str = "",
    ) -> StudioRunRecordV1:
        """Update native Replay finalization availability.

        Args:
            run_id (str): Stable Run identity.
            availability (RunEvidenceAvailability): New evidence state.
            error_code (str): Optional stable failure code.

        Raises:
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Update fails.

        Returns:
            StudioRunRecordV1: Updated record.
        """
        timestamp = _now_ms()
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE studio_runs
                SET replay_availability = ?, replay_error_code = ?,
                    updated_at = ?
                WHERE run_id = ?
                """,
                (availability.value, str(error_code)[:160], timestamp, run_id),
            )
            return self._record_from_row(self._select_run(connection, run_id))

    def set_storage_warnings(
        self,
        run_id: str,
        warnings: tuple[str, ...],
    ) -> StudioRunRecordV1:
        """Persist bounded storage warning codes for one Run.

        Args:
            run_id (str): Stable Run identity.
            warnings (tuple[str, ...]): Non-sensitive warning codes.

        Raises:
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Update fails.

        Returns:
            StudioRunRecordV1: Updated record.
        """
        bounded = tuple(str(item)[:160] for item in warnings[:20])
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE studio_runs
                SET storage_warnings_json = ?, updated_at = ?
                WHERE run_id = ?
                """,
                (_json_text(bounded), _now_ms(), run_id),
            )
            return self._record_from_row(self._select_run(connection, run_id))

    def list_nonterminal_for_other_owner(
        self,
        process_owner_id: str,
    ) -> tuple[StudioRunRecordV1, ...]:
        """List nonterminal Runs that do not belong to the active process.

        Args:
            process_owner_id (str): Current process owner identity.

        Raises:
            sqlite3.Error: Query fails.

        Returns:
            tuple[StudioRunRecordV1, ...]: Stable oldest-first records.
        """
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM studio_runs
                WHERE lifecycle_state != 'terminal'
                  AND process_owner_id != ?
                ORDER BY accepted_at ASC, run_id ASC
                """,
                (process_owner_id,),
            ).fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    def append_event(
        self,
        run_id: str,
        event: StudioRunEventDraftV1,
    ) -> tuple[StudioRunEventEnvelopeV1, bool]:
        """Append or idempotently return one durable journal event.

        Args:
            run_id (str): Owning Run identity.
            event (StudioRunEventDraftV1): Strict unsequenced event.

        Raises:
            StudioRunConflictError: Event identity has different content.
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Transaction fails.

        Returns:
            tuple[StudioRunEventEnvelopeV1, bool]: Envelope and new flag.
        """
        fingerprint = run_event_fingerprint(event)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                self._select_run(connection, run_id)
                existing = connection.execute(
                    """
                    SELECT fingerprint, envelope_json
                    FROM studio_run_events
                    WHERE run_id = ? AND event_id = ?
                    """,
                    (run_id, event.event_id),
                ).fetchone()
                if existing is not None:
                    if existing["fingerprint"] != fingerprint:
                        raise StudioRunConflictError(
                            "studio.run.event_identity_conflict",
                            "Run event identity has conflicting content",
                        )
                    connection.execute("COMMIT")
                    return (
                        StudioRunEventEnvelopeV1.model_validate(
                            json.loads(existing["envelope_json"])
                        ),
                        False,
                    )
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                    FROM studio_run_events
                    WHERE run_id = ?
                    """,
                    (run_id,),
                ).fetchone()
                envelope = StudioRunEventEnvelopeV1(
                    **event.model_dump(mode="python"),
                    run_id=run_id,
                    sequence=int(row["next_sequence"]),
                    fingerprint=fingerprint,
                )
                connection.execute(
                    """
                    INSERT INTO studio_run_events(
                        run_id, sequence, event_id, fingerprint, envelope_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        envelope.sequence,
                        envelope.event_id,
                        envelope.fingerprint,
                        _json_text(
                            envelope.model_dump(
                                mode="json",
                                by_alias=True,
                                exclude_none=True,
                            )
                        ),
                    ),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return envelope, True

    def query_events(
        self,
        run_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioRunEventPageV1:
        """Read one bounded continuous page after an exclusive cursor.

        Args:
            run_id (str): Owning Run identity.
            after (int): Exclusive last-confirmed journal sequence.
            limit (int): Page size from 1 through 500.

        Raises:
            StudioRunValidationError: Cursor or limit is invalid.
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Query fails.

        Returns:
            StudioRunEventPageV1: Ordered bounded journal page.
        """
        if after < 0 or not 1 <= limit <= 500:
            raise StudioRunValidationError(
                "studio.run.event_cursor_invalid",
                "Run event cursor or limit is invalid",
            )
        with self._connect() as connection:
            run = self._select_run(connection, run_id)
            high_row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS high_water_mark
                FROM studio_run_events WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
            high = int(high_row["high_water_mark"])
            if after > high:
                raise StudioRunValidationError(
                    "studio.run.event_cursor_invalid",
                    "Run event cursor exceeds the high-water mark",
                )
            rows = connection.execute(
                """
                SELECT envelope_json
                FROM studio_run_events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                LIMIT ?
                """,
                (run_id, after, limit),
            ).fetchall()
            last_row = connection.execute(
                """
                SELECT envelope_json
                FROM studio_run_events
                WHERE run_id = ?
                ORDER BY sequence DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
        items = tuple(
            StudioRunEventEnvelopeV1.model_validate(
                json.loads(row["envelope_json"])
            )
            for row in rows
        )
        expected = after + 1
        for item in items:
            if item.sequence != expected:
                raise StudioRunConflictError(
                    "studio.run.event_sequence_gap",
                    "Run event journal contains a sequence gap",
                )
            expected += 1
        cursor = items[-1].sequence if items else after
        last_kind = (
            StudioRunEventEnvelopeV1.model_validate(
                json.loads(last_row["envelope_json"])
            ).kind
            if last_row is not None
            else ""
        )
        return StudioRunEventPageV1(
            run_id=run_id,
            items=items,
            next_cursor=cursor,
            high_water_mark=high,
            terminal=(
                run["lifecycle_state"] == StudioRunLifecycle.TERMINAL.value
                and last_kind == "run.terminal"
                and cursor >= high
            ),
        )

    def high_water_mark(self, run_id: str) -> int:
        """Return the latest committed journal sequence.

        Args:
            run_id (str): Owning Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Query fails.

        Returns:
            int: Latest sequence, or zero before the first event.
        """
        with self._connect() as connection:
            self._select_run(connection, run_id)
            row = connection.execute(
                """
                SELECT COALESCE(MAX(sequence), 0) AS high_water_mark
                FROM studio_run_events WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        return int(row["high_water_mark"])

    def put_artifact(self, record: StudioRunArtifactRecordV1) -> None:
        """Create one immutable artifact record.

        Args:
            record (StudioRunArtifactRecordV1): Descriptor and managed reference.

        Raises:
            StudioRunValidationError: Storage reference is unsafe.
            StudioRunConflictError: Artifact identity already exists.
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Transaction fails.

        Returns:
            None.
        """
        pure = PurePosixPath(record.storage_ref)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise StudioRunValidationError(
                "studio.run.artifact_ref_invalid",
                "Run artifact storage reference is unsafe",
            )
        descriptor = record.descriptor
        with self._connect() as connection:
            self._select_run(connection, record.run_id)
            try:
                connection.execute(
                    """
                    INSERT INTO studio_run_artifacts(
                        run_id, artifact_id, availability, content_type,
                        size, sha256, hidden, storage_ref, descriptor_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.run_id,
                        descriptor.artifact_id,
                        descriptor.availability.value,
                        descriptor.content_type,
                        descriptor.size,
                        descriptor.sha256,
                        int(descriptor.hidden),
                        record.storage_ref,
                        _json_text(
                            descriptor.model_dump(
                                mode="json",
                                by_alias=True,
                                exclude_none=True,
                            )
                        ),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StudioRunConflictError(
                    "studio.run.artifact_conflict",
                    "Run artifact identity already exists",
                ) from error

    def get_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> StudioRunArtifactRecordV1:
        """Resolve one artifact only within its owning Run.

        Args:
            run_id (str): Owning Run identity.
            artifact_id (str): Opaque artifact identity.

        Raises:
            StudioRunArtifactNotFoundError: Pair is absent.
            sqlite3.Error: Query fails.

        Returns:
            StudioRunArtifactRecordV1: Descriptor and internal storage reference.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT descriptor_json, storage_ref
                FROM studio_run_artifacts
                WHERE run_id = ? AND artifact_id = ?
                """,
                (run_id, artifact_id),
            ).fetchone()
        if row is None:
            raise StudioRunArtifactNotFoundError(
                "studio.run.artifact_not_found",
                "Studio Run artifact was not found",
            )
        return StudioRunArtifactRecordV1(
            run_id=run_id,
            descriptor=StudioRunArtifactDescriptorV1.model_validate(
                json.loads(row["descriptor_json"])
            ),
            storage_ref=row["storage_ref"],
        )

    def list_artifacts(
        self,
        run_id: str,
    ) -> tuple[StudioRunArtifactRecordV1, ...]:
        """List artifact records for one Run in stable order.

        Args:
            run_id (str): Owning Run identity.

        Raises:
            StudioRunNotFoundError: Run is absent.
            sqlite3.Error: Query fails.

        Returns:
            tuple[StudioRunArtifactRecordV1, ...]: Stable artifact records.
        """
        with self._connect() as connection:
            self._select_run(connection, run_id)
            rows = connection.execute(
                """
                SELECT artifact_id, descriptor_json, storage_ref
                FROM studio_run_artifacts
                WHERE run_id = ?
                ORDER BY artifact_id ASC
                """,
                (run_id,),
            ).fetchall()
        return tuple(
            StudioRunArtifactRecordV1(
                run_id=run_id,
                descriptor=StudioRunArtifactDescriptorV1.model_validate(
                    json.loads(row["descriptor_json"])
                ),
                storage_ref=row["storage_ref"],
            )
            for row in rows
        )

    def update_artifact_availability(
        self,
        run_id: str,
        artifact_id: str,
        availability: RunEvidenceAvailability,
    ) -> StudioRunArtifactRecordV1:
        """Update integrity availability after a verified read failure.

        Args:
            run_id (str): Owning Run identity.
            artifact_id (str): Opaque artifact identity.
            availability (RunEvidenceAvailability): New integrity state.

        Raises:
            StudioRunArtifactNotFoundError: Pair is absent.
            sqlite3.Error: Update fails.

        Returns:
            StudioRunArtifactRecordV1: Updated record.
        """
        current = self.get_artifact(run_id, artifact_id)
        descriptor = current.descriptor.model_copy(
            update={"availability": availability}
        )
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE studio_run_artifacts
                SET availability = ?, descriptor_json = ?
                WHERE run_id = ? AND artifact_id = ?
                """,
                (
                    availability.value,
                    _json_text(
                        descriptor.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                    ),
                    run_id,
                    artifact_id,
                ),
            )
        if cursor.rowcount != 1:
            raise StudioRunArtifactNotFoundError(
                "studio.run.artifact_not_found",
                "Studio Run artifact was not found",
            )
        return StudioRunArtifactRecordV1(
            run_id=run_id,
            descriptor=descriptor,
            storage_ref=current.storage_ref,
        )


__all__ = ["SQLiteStudioRunRepository"]
