"""SQLite persistence for durable Studio Benchmark authoring revisions."""

from __future__ import annotations

import base64
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringReleaseConflictError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_PAGE_SIZE,
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkAuthoringRevisionV1,
    StudioBenchmarkDraftPageV1,
    StudioBenchmarkDraftRecordV1,
)
from .benchmark_authoring_freeze_models import (
    StudioBenchmarkFrozenMemberV1,
    StudioBenchmarkPackageRevisionDetailV1,
    StudioBenchmarkPackageRevisionV1,
    StudioBenchmarkValidationAttestationV1,
    validate_benchmark_package_revision_id,
)
from .benchmark_authoring_release_models import (
    STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT,
    STUDIO_BENCHMARK_PACKAGE_REVISION_PAGE_MAX,
    StudioBenchmarkPackageExportV1,
    StudioBenchmarkPackagePublicationV1,
    StudioBenchmarkPackageRevisionPageV1,
    StudioBenchmarkPackageRevisionReleaseSummaryV1,
    StudioBenchmarkStoredExportV1,
    StudioBenchmarkStoredPublicationV1,
)
from .database import connect_studio_database, migrate_studio_database


def _json_text(value: Any) -> str:
    """Encode deterministic finite JSON for durable authoring facts.

    Args:
        value: JSON-compatible value.

    Raises:
        TypeError: Value is not serializable.
        ValueError: Value contains a non-finite number.

    Returns:
        Compact deterministic JSON.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _new_id(prefix: str) -> str:
    """Create one opaque UUID-derived authoring identity.

    Args:
        prefix: Stable public resource prefix.

    Raises:
        None.

    Returns:
        Opaque resource identity.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


def _encode_cursor(updated_at: int, draft_id: str) -> str:
    """Encode one opaque draft-list cursor.

    Args:
        updated_at: Last selected update timestamp.
        draft_id: Last selected stable draft identity.

    Raises:
        None.

    Returns:
        URL-safe opaque cursor.
    """
    raw = _json_text(
        {"updatedAt": updated_at, "draftId": draft_id}
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[int, str]:
    """Decode and validate one opaque draft-list cursor.

    Args:
        cursor: Browser-provided cursor.

    Raises:
        StudioBenchmarkAuthoringValidationError: Cursor is malformed.

    Returns:
        Update timestamp and draft identity.
    """
    try:
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(
            base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode(
                "utf-8"
            )
        )
        updated_at = int(value["updatedAt"])
        draft_id = str(value["draftId"])
        StudioBenchmarkDraftRecordV1.model_validate(
            {
                "draftId": draft_id,
                "name": "cursor",
                "currentRevisionId": "benchmark-authoring-revision-" + "0" * 32,
                "createdAt": 0,
                "updatedAt": updated_at,
            }
        )
    except Exception as error:
        raise StudioBenchmarkAuthoringValidationError(
            "benchmark.authoring.cursor_invalid",
            "Benchmark authoring cursor is invalid",
        ) from error
    return updated_at, draft_id


def _encode_package_revision_cursor(
    *,
    draft_id: str,
    created_at: int,
    package_revision_id: str,
) -> str:
    """Encode one draft-bound Package-revision continuation cursor.

    Args:
        draft_id: Owning draft identity.
        created_at: Last selected creation timestamp.
        package_revision_id: Last selected immutable revision identity.

    Raises:
        TypeError: Cursor facts cannot be encoded as JSON.

    Returns:
        URL-safe opaque continuation cursor.
    """
    raw = _json_text(
        {
            "v": 1,
            "draftId": draft_id,
            "createdAt": created_at,
            "packageRevisionId": package_revision_id,
        }
    ).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_package_revision_cursor(
    cursor: str,
    *,
    draft_id: str,
) -> tuple[int, str]:
    """Decode one exact draft-bound Package-revision cursor.

    Args:
        cursor: Browser-provided opaque cursor.
        draft_id: Expected owning draft identity.

    Raises:
        StudioBenchmarkAuthoringValidationError: Cursor is malformed or stale.

    Returns:
        Creation timestamp and Package revision identity.
    """
    try:
        if not isinstance(cursor, str) or not 1 <= len(cursor) <= 2048:
            raise ValueError("cursor length is invalid")
        padding = "=" * (-len(cursor) % 4)
        value = json.loads(
            base64.urlsafe_b64decode((cursor + padding).encode("ascii")).decode(
                "utf-8"
            )
        )
        if not isinstance(value, dict):
            raise ValueError("cursor must decode to an object")
        created_at = value["createdAt"]
        package_revision_id = value["packageRevisionId"]
        if (
            set(value) != {"v", "draftId", "createdAt", "packageRevisionId"}
            or value.get("v") != 1
            or value.get("draftId") != draft_id
            or not isinstance(created_at, int)
            or isinstance(created_at, bool)
            or not 0 <= created_at <= 2**63 - 1
            or not isinstance(package_revision_id, str)
        ):
            raise ValueError("cursor contract mismatch")
        validate_benchmark_package_revision_id(package_revision_id)
    except Exception as error:
        raise StudioBenchmarkAuthoringValidationError(
            "benchmark.authoring.package_revision_cursor_invalid",
            "Benchmark Package revision cursor is invalid or stale",
        ) from error
    return created_at, package_revision_id


class SQLiteStudioBenchmarkAuthoringRepository:
    """SQLite adapter for append-only Benchmark authoring revisions."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], int] | None = None,
        identity_factory: Callable[[str], str] | None = None,
    ) -> None:
        """Open or migrate one explicit Studio database.

        Args:
            database_path: Explicit Studio SQLite path.
            clock: Optional deterministic millisecond clock.
            identity_factory: Optional deterministic test identity factory.

        Raises:
            OSError: Database parent cannot be created.
            sqlite3.Error: Migration fails.

        Returns:
            None.
        """
        self._database_path = Path(database_path).expanduser()
        self._clock = clock or (lambda: time.time_ns() // 1_000_000)
        self._identity_factory = identity_factory or _new_id
        migrate_studio_database(self._database_path)

    @property
    def database_path(self) -> Path:
        """Return the configured adapter path for internal composition.

        Returns:
            Configured SQLite path.
        """
        return self._database_path

    def _connect(self) -> sqlite3.Connection:
        """Open one configured short-lived SQLite connection.

        Returns:
            Row-enabled SQLite connection.
        """
        return connect_studio_database(self._database_path)

    @staticmethod
    def _draft_from_row(row: sqlite3.Row) -> StudioBenchmarkDraftRecordV1:
        """Project one draft row into a strict storage-neutral DTO.

        Args:
            row: SQLite row containing draft columns.

        Raises:
            ValueError: Stored data violates current contracts.

        Returns:
            Strict draft record.
        """
        return StudioBenchmarkDraftRecordV1(
            draft_id=row["draft_id"],
            name=row["name"],
            current_revision_id=row["current_revision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_from_row(
        row: sqlite3.Row,
    ) -> StudioBenchmarkAuthoringRevisionV1:
        """Project one revision row into a strict immutable DTO.

        Args:
            row: SQLite row containing revision columns.

        Raises:
            ValueError: Stored JSON or identity facts are invalid.

        Returns:
            Strict authoring revision.
        """
        return StudioBenchmarkAuthoringRevisionV1(
            revision_id=row["revision_id"],
            draft_id=row["draft_id"],
            ordinal=row["ordinal"],
            parent_revision_id=row["parent_revision_id"],
            document=StudioBenchmarkAuthoringDocumentV1.model_validate(
                json.loads(row["document_json"])
            ),
            document_fingerprint=row["document_fingerprint"],
            provenance=StudioBenchmarkAuthoringProvenanceV1.model_validate(
                json.loads(row["provenance_json"])
            ),
            status=row["status"],
            created_at=row["created_at"],
        )

    @staticmethod
    def _normalize_name(name: str) -> str:
        """Normalize one bounded reader-facing draft name.

        Args:
            name: Candidate name.

        Raises:
            StudioBenchmarkAuthoringValidationError: Name is blank or oversized.

        Returns:
            Trimmed name.
        """
        value = str(name).strip()
        if not value or len(value) > 256:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.name_invalid",
                "Benchmark draft name must contain 1 to 256 characters",
            )
        return value

    @staticmethod
    def _command_result(
        connection: sqlite3.Connection,
        *,
        scope: str,
        client_request_id: str,
        request_fingerprint: str,
    ) -> tuple[str, str] | None:
        """Resolve one durable idempotency fact inside a transaction.

        Args:
            connection: Active SQLite connection.
            scope: Stable create or draft-local save scope.
            client_request_id: Client command identity.
            request_fingerprint: Canonical submitted request fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.

        Returns:
            Draft/revision identities when a matching command already exists.
        """
        row = connection.execute(
            """
            SELECT request_fingerprint, draft_id, revision_id
            FROM studio_benchmark_authoring_commands
            WHERE command_scope = ? AND client_request_id = ?
            """,
            (scope, client_request_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_fingerprint"] != request_fingerprint:
            raise StudioBenchmarkAuthoringIdempotencyConflictError(
                "benchmark.authoring.idempotency_conflict",
                "Client request identity is already used for different content",
            )
        return str(row["draft_id"]), str(row["revision_id"])

    @classmethod
    def _load_pair(
        cls,
        connection: sqlite3.Connection,
        draft_id: str,
        revision_id: str,
    ) -> tuple[StudioBenchmarkDraftRecordV1, StudioBenchmarkAuthoringRevisionV1]:
        """Load a draft and one exact owned revision inside a connection.

        Args:
            connection: Active SQLite connection.
            draft_id: Owning draft identity.
            revision_id: Exact revision identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Either resource is absent.
            ValueError: Stored facts violate current contracts.

        Returns:
            Draft and revision DTO pair.
        """
        draft_row = connection.execute(
            """
            SELECT draft_id, name, current_revision_id, created_at, updated_at
            FROM studio_benchmark_authoring_drafts
            WHERE draft_id = ?
            """,
            (draft_id,),
        ).fetchone()
        revision_row = connection.execute(
            """
            SELECT revision_id, draft_id, ordinal, parent_revision_id,
                   document_json, document_fingerprint, provenance_json,
                   status, created_at
            FROM studio_benchmark_authoring_revisions
            WHERE draft_id = ? AND revision_id = ?
            """,
            (draft_id, revision_id),
        ).fetchone()
        if draft_row is None or revision_row is None:
            raise StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.not_found",
                "Benchmark authoring resource was not found",
            )
        return (
            cls._draft_from_row(draft_row),
            cls._revision_from_row(revision_row),
        )

    def find_create_result(
        self,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> tuple[StudioBenchmarkDraftRecordV1, StudioBenchmarkAuthoringRevisionV1] | None:
        """Find a durable create retry before reading a mutable source.

        Args:
            client_request_id: Create command identity.
            request_fingerprint: Canonical create request fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.
            StudioBenchmarkAuthoringStorageError: Storage cannot be read safely.

        Returns:
            Existing draft/revision pair or None.
        """
        try:
            with self._connect() as connection:
                result = self._command_result(
                    connection,
                    scope="create",
                    client_request_id=client_request_id,
                    request_fingerprint=request_fingerprint,
                )
                return (
                    self._load_pair(connection, *result)
                    if result is not None
                    else None
                )
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring storage could not be read safely",
            ) from error

    def create_draft(
        self,
        *,
        client_request_id: str,
        request_fingerprint: str,
        name: str,
        document: StudioBenchmarkAuthoringDocumentV1,
        provenance: StudioBenchmarkAuthoringProvenanceV1,
    ) -> tuple[
        StudioBenchmarkDraftRecordV1,
        StudioBenchmarkAuthoringRevisionV1,
        bool,
    ]:
        """Create an initial draft and revision atomically.

        Args:
            client_request_id: Durable create command identity.
            request_fingerprint: Canonical request fingerprint.
            name: Reader-facing draft name.
            document: Strict initial authoring document.
            provenance: Safe template or Catalog provenance.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.
            StudioBenchmarkAuthoringStorageError: Transaction fails.
            StudioBenchmarkAuthoringValidationError: Name is invalid.

        Returns:
            Draft, initial revision, and whether they were newly created.
        """
        normalized_name = self._normalize_name(name)
        document_json = _json_text(
            document.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        provenance_json = _json_text(
            provenance.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = self._command_result(
                        connection,
                        scope="create",
                        client_request_id=client_request_id,
                        request_fingerprint=request_fingerprint,
                    )
                    if existing is not None:
                        pair = self._load_pair(connection, *existing)
                        connection.execute("COMMIT")
                        return pair[0], pair[1], False
                    draft_id = self._identity_factory("benchmark-draft")
                    revision_id = self._identity_factory(
                        "benchmark-authoring-revision"
                    )
                    now = self._clock()
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_authoring_drafts(
                            draft_id, name, current_revision_id,
                            created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (draft_id, normalized_name, revision_id, now, now),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_authoring_revisions(
                            revision_id, draft_id, ordinal, parent_revision_id,
                            document_json, document_fingerprint,
                            provenance_json, status, created_at
                        ) VALUES (?, ?, 1, NULL, ?, ?, ?, 'unvalidated', ?)
                        """,
                        (
                            revision_id,
                            draft_id,
                            document_json,
                            document.fingerprint,
                            provenance_json,
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_authoring_commands(
                            command_scope, client_request_id,
                            request_fingerprint, draft_id, revision_id,
                            created_at
                        ) VALUES ('create', ?, ?, ?, ?, ?)
                        """,
                        (
                            client_request_id,
                            request_fingerprint,
                            draft_id,
                            revision_id,
                            now,
                        ),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                pair = self._load_pair(connection, draft_id, revision_id)
                return pair[0], pair[1], True
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
            StudioBenchmarkAuthoringValidationError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring draft could not be stored",
            ) from error

    def list_drafts(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkDraftPageV1:
        """List drafts in deterministic newest-first order.

        Args:
            limit: Page size from 1 through the shared maximum.
            cursor: Optional opaque exclusive continuation cursor.

        Raises:
            StudioBenchmarkAuthoringValidationError: Page input is invalid.
            StudioBenchmarkAuthoringStorageError: Query or stored rows fail.

        Returns:
            Bounded draft page.
        """
        if not 1 <= limit <= STUDIO_BENCHMARK_AUTHORING_MAX_PAGE_SIZE:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.limit_invalid",
                "Benchmark authoring page limit is invalid",
            )
        where = ""
        parameters: list[Any] = []
        if cursor is not None:
            updated_at, draft_id = _decode_cursor(cursor)
            where = (
                "WHERE updated_at < ? OR "
                "(updated_at = ? AND draft_id > ?)"
            )
            parameters.extend((updated_at, updated_at, draft_id))
        parameters.append(limit + 1)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT draft_id, name, current_revision_id,
                           created_at, updated_at
                    FROM studio_benchmark_authoring_drafts
                    {where}
                    ORDER BY updated_at DESC, draft_id ASC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
            selected = rows[:limit]
            items = tuple(self._draft_from_row(row) for row in selected)
            next_cursor = (
                _encode_cursor(items[-1].updated_at, items[-1].draft_id)
                if len(rows) > limit and items
                else None
            )
            return StudioBenchmarkDraftPageV1(
                items=items,
                next_cursor=next_cursor,
            )
        except StudioBenchmarkAuthoringValidationError:
            raise
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring drafts could not be listed safely",
            ) from error

    def get_draft(self, draft_id: str) -> StudioBenchmarkDraftRecordV1:
        """Read one draft by stable opaque identity.

        Args:
            draft_id: Draft identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Draft is absent.
            StudioBenchmarkAuthoringStorageError: Stored row is invalid.

        Returns:
            Draft record.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT draft_id, name, current_revision_id,
                           created_at, updated_at
                    FROM studio_benchmark_authoring_drafts
                    WHERE draft_id = ?
                    """,
                    (draft_id,),
                ).fetchone()
            if row is None:
                raise StudioBenchmarkAuthoringNotFoundError(
                    "benchmark.authoring.not_found",
                    "Benchmark authoring resource was not found",
                )
            return self._draft_from_row(row)
        except StudioBenchmarkAuthoringNotFoundError:
            raise
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring draft could not be read safely",
            ) from error

    def get_revision(
        self,
        draft_id: str,
        revision_id: str,
    ) -> StudioBenchmarkAuthoringRevisionV1:
        """Read one exact revision only through its owning draft.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact authoring revision identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Owned revision is absent.
            StudioBenchmarkAuthoringStorageError: Stored row is invalid.

        Returns:
            Immutable authoring revision.
        """
        try:
            with self._connect() as connection:
                return self._load_pair(
                    connection,
                    draft_id,
                    revision_id,
                )[1]
        except StudioBenchmarkAuthoringNotFoundError:
            raise
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring revision could not be read safely",
            ) from error

    def has_save_command(
        self,
        draft_id: str,
        *,
        client_request_id: str,
    ) -> bool:
        """Return whether one draft-local save identity already committed.

        This presence check allows a response-loss retry to re-read and hash its
        bytes even when its original base revision is no longer current. The
        transaction-time fingerprint comparison remains the idempotency
        authority.

        Args:
            draft_id: Owning draft identity.
            client_request_id: Draft-local command identity.

        Raises:
            StudioBenchmarkAuthoringStorageError: Durable facts cannot be read.

        Returns:
            True when the scoped command identity is already durable.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT 1
                    FROM studio_benchmark_authoring_commands
                    WHERE command_scope = ? AND client_request_id = ?
                    """,
                    (f"save:{draft_id}", client_request_id),
                ).fetchone()
            return row is not None
        except sqlite3.Error as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring command facts could not be read safely",
            ) from error

    def save_revision(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
        base_revision_id: str,
        document: StudioBenchmarkAuthoringDocumentV1,
        provenance: StudioBenchmarkAuthoringProvenanceV1,
    ) -> tuple[
        StudioBenchmarkDraftRecordV1,
        StudioBenchmarkAuthoringRevisionV1,
        bool,
    ]:
        """Append an idempotent optimistic authoring revision.

        Args:
            draft_id: Owning draft identity.
            client_request_id: Draft-local command identity.
            request_fingerprint: Canonical save request fingerprint.
            base_revision_id: Client-observed current revision.
            document: Complete next safe authoring document.
            provenance: Edit provenance for the new revision.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.
            StudioBenchmarkAuthoringRevisionConflictError: Base is stale.
            StudioBenchmarkAuthoringNotFoundError: Draft is absent.
            StudioBenchmarkAuthoringStorageError: Transaction fails.

        Returns:
            Draft, resulting revision, and whether it was newly created.
        """
        document_json = _json_text(
            document.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        provenance_json = _json_text(
            provenance.model_dump(mode="json", by_alias=True, exclude_none=True)
        )
        scope = f"save:{draft_id}"
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = self._command_result(
                        connection,
                        scope=scope,
                        client_request_id=client_request_id,
                        request_fingerprint=request_fingerprint,
                    )
                    if existing is not None:
                        pair = self._load_pair(connection, *existing)
                        connection.execute("COMMIT")
                        return pair[0], pair[1], False
                    draft_row = connection.execute(
                        """
                        SELECT current_revision_id
                        FROM studio_benchmark_authoring_drafts
                        WHERE draft_id = ?
                        """,
                        (draft_id,),
                    ).fetchone()
                    if draft_row is None:
                        raise StudioBenchmarkAuthoringNotFoundError(
                            "benchmark.authoring.not_found",
                            "Benchmark authoring resource was not found",
                        )
                    current_revision_id = str(
                        draft_row["current_revision_id"]
                    )
                    if current_revision_id != base_revision_id:
                        raise StudioBenchmarkAuthoringRevisionConflictError(
                            "benchmark.authoring.revision_conflict",
                            "Benchmark draft current revision has changed",
                            current_revision_id=current_revision_id,
                        )
                    ordinal_row = connection.execute(
                        """
                        SELECT COALESCE(MAX(ordinal), 0) AS ordinal
                        FROM studio_benchmark_authoring_revisions
                        WHERE draft_id = ?
                        """,
                        (draft_id,),
                    ).fetchone()
                    ordinal = int(ordinal_row["ordinal"]) + 1
                    revision_id = self._identity_factory(
                        "benchmark-authoring-revision"
                    )
                    now = self._clock()
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_authoring_revisions(
                            revision_id, draft_id, ordinal, parent_revision_id,
                            document_json, document_fingerprint,
                            provenance_json, status, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, 'unvalidated', ?)
                        """,
                        (
                            revision_id,
                            draft_id,
                            ordinal,
                            current_revision_id,
                            document_json,
                            document.fingerprint,
                            provenance_json,
                            now,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_authoring_drafts
                        SET current_revision_id = ?, updated_at = ?
                        WHERE draft_id = ?
                        """,
                        (revision_id, now, draft_id),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_authoring_commands(
                            command_scope, client_request_id,
                            request_fingerprint, draft_id, revision_id,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            scope,
                            client_request_id,
                            request_fingerprint,
                            draft_id,
                            revision_id,
                            now,
                        ),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                pair = self._load_pair(connection, draft_id, revision_id)
                return pair[0], pair[1], True
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
            StudioBenchmarkAuthoringRevisionConflictError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring revision could not be stored",
            ) from error

    @staticmethod
    def _load_freeze_detail(
        connection: sqlite3.Connection,
        draft_id: str,
        package_revision_id: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1:
        """Reconstruct one strict immutable freeze detail inside a connection.

        Args:
            connection: Active SQLite connection.
            draft_id: Owning draft identity.
            package_revision_id: Exact Package revision identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Owned resource is absent.
            ValueError: Durable rows violate the strict freeze contract.

        Returns:
            Exact Package revision and successful attestation.
        """
        row = connection.execute(
            """
            SELECT
                p.package_revision_id,
                p.draft_id,
                p.authoring_revision_id,
                p.attestation_id,
                p.package_identity,
                p.package_content_identity,
                p.closure_identity,
                p.created_at,
                a.document_fingerprint,
                a.validation_contract_version,
                a.package_identity AS attestation_package_identity,
                a.package_content_identity AS attestation_content_identity,
                a.attestation_json,
                a.created_at AS attestation_created_at
            FROM studio_benchmark_package_revisions AS p
            JOIN studio_benchmark_validation_attestations AS a
              ON a.attestation_id = p.attestation_id
            WHERE p.draft_id = ? AND p.package_revision_id = ?
            """,
            (draft_id, package_revision_id),
        ).fetchone()
        if row is None:
            raise StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.package_revision_not_found",
                "Benchmark Package revision was not found",
            )
        member_rows = connection.execute(
            """
            SELECT ordinal, member_path, descriptor_json
            FROM studio_benchmark_package_revision_members
            WHERE package_revision_id = ?
            ORDER BY ordinal ASC
            """,
            (package_revision_id,),
        ).fetchall()
        members = tuple(
            StudioBenchmarkFrozenMemberV1.model_validate(
                json.loads(member_row["descriptor_json"])
            )
            for member_row in member_rows
        )
        if any(
            member.ordinal != int(member_row["ordinal"])
            or member.path != str(member_row["member_path"])
            for member, member_row in zip(members, member_rows, strict=True)
        ):
            raise ValueError("stored frozen member index is inconsistent")
        attestation = StudioBenchmarkValidationAttestationV1.model_validate(
            json.loads(row["attestation_json"])
        )
        if (
            attestation.attestation_id != row["attestation_id"]
            or attestation.draft_id != row["draft_id"]
            or attestation.authoring_revision_id
            != row["authoring_revision_id"]
            or attestation.document_fingerprint
            != row["document_fingerprint"]
            or attestation.validation_contract_version
            != row["validation_contract_version"]
            or attestation.package_identity
            != row["attestation_package_identity"]
            or attestation.package_content_identity
            != row["attestation_content_identity"]
            or attestation.created_at != row["attestation_created_at"]
        ):
            raise ValueError("stored validation attestation is inconsistent")
        package_revision = StudioBenchmarkPackageRevisionV1(
            package_revision_id=row["package_revision_id"],
            draft_id=row["draft_id"],
            authoring_revision_id=row["authoring_revision_id"],
            validation_attestation_id=row["attestation_id"],
            package_identity=row["package_identity"],
            package_content_identity=row["package_content_identity"],
            closure_identity=row["closure_identity"],
            members=members,
            created_at=row["created_at"],
        )
        return StudioBenchmarkPackageRevisionDetailV1(
            package_revision=package_revision,
            validation_attestation=attestation,
        )

    @classmethod
    def _freeze_command_result(
        cls,
        connection: sqlite3.Connection,
        *,
        draft_id: str,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1 | None:
        """Resolve one scoped freeze retry inside an active connection.

        Args:
            connection: Active SQLite connection.
            draft_id: Owning draft scope.
            client_request_id: Stable client command identity.
            request_fingerprint: Canonical freeze request fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.
            StudioBenchmarkAuthoringNotFoundError: Stored result is missing.

        Returns:
            Original immutable result or ``None``.
        """
        row = connection.execute(
            """
            SELECT request_fingerprint, package_revision_id
            FROM studio_benchmark_freeze_commands
            WHERE draft_id = ? AND client_request_id = ?
            """,
            (draft_id, client_request_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_fingerprint"] != request_fingerprint:
            raise StudioBenchmarkAuthoringIdempotencyConflictError(
                "benchmark.authoring.freeze_idempotency_conflict",
                "Benchmark freeze request identity was reused",
            )
        return cls._load_freeze_detail(
            connection,
            draft_id,
            str(row["package_revision_id"]),
        )

    def find_freeze_result(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1 | None:
        """Read a durable freeze retry before private reconstruction.

        Args:
            draft_id: Owning draft scope.
            client_request_id: Stable client command identity.
            request_fingerprint: Canonical freeze request fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.
            StudioBenchmarkAuthoringNotFoundError: Stored result is inconsistent.
            StudioBenchmarkAuthoringStorageError: Rows cannot be read safely.

        Returns:
            Original immutable freeze result or ``None``.
        """
        try:
            with self._connect() as connection:
                return self._freeze_command_result(
                    connection,
                    draft_id=draft_id,
                    client_request_id=client_request_id,
                    request_fingerprint=request_fingerprint,
                )
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark freeze command facts could not be read safely",
            ) from error

    def commit_freeze(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
        expected_revision_id: str,
        attestation: StudioBenchmarkValidationAttestationV1,
        package_revision: StudioBenchmarkPackageRevisionV1,
    ) -> tuple[StudioBenchmarkPackageRevisionDetailV1, bool]:
        """Atomically commit one successful exact-current validated freeze.

        Args:
            draft_id: Owning draft identity.
            client_request_id: Stable client command identity.
            request_fingerprint: Canonical request fingerprint.
            expected_revision_id: Revision that must still be current.
            attestation: Successful immutable validation evidence.
            package_revision: Complete frozen Package member closure.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: ID was reused.
            StudioBenchmarkAuthoringRevisionConflictError: Current advanced.
            StudioBenchmarkAuthoringNotFoundError: Draft is absent.
            StudioBenchmarkAuthoringStorageError: Transaction or rows fail.
            ValueError: Supplied immutable identities disagree.

        Returns:
            Durable detail and whether this transaction created it.
        """
        detail = StudioBenchmarkPackageRevisionDetailV1(
            package_revision=package_revision,
            validation_attestation=attestation,
        )
        if (
            detail.package_revision.draft_id != draft_id
            or detail.package_revision.authoring_revision_id
            != expected_revision_id
        ):
            raise ValueError("freeze commit ownership does not match")
        attestation_json = _json_text(
            attestation.model_dump(mode="json", by_alias=True)
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = self._freeze_command_result(
                        connection,
                        draft_id=draft_id,
                        client_request_id=client_request_id,
                        request_fingerprint=request_fingerprint,
                    )
                    if existing is not None:
                        connection.execute("COMMIT")
                        return existing, False
                    draft_row = connection.execute(
                        """
                        SELECT current_revision_id
                        FROM studio_benchmark_authoring_drafts
                        WHERE draft_id = ?
                        """,
                        (draft_id,),
                    ).fetchone()
                    if draft_row is None:
                        raise StudioBenchmarkAuthoringNotFoundError(
                            "benchmark.authoring.not_found",
                            "Benchmark authoring resource was not found",
                        )
                    current_revision_id = str(draft_row["current_revision_id"])
                    if current_revision_id != expected_revision_id:
                        raise StudioBenchmarkAuthoringRevisionConflictError(
                            "benchmark.authoring.freeze_revision_stale",
                            "Benchmark freeze requires the current draft revision",
                            current_revision_id=current_revision_id,
                        )
                    revision_row = connection.execute(
                        """
                        SELECT document_fingerprint
                        FROM studio_benchmark_authoring_revisions
                        WHERE draft_id = ? AND revision_id = ?
                        """,
                        (draft_id, expected_revision_id),
                    ).fetchone()
                    if revision_row is None:
                        raise StudioBenchmarkAuthoringNotFoundError(
                            "benchmark.authoring.not_found",
                            "Benchmark authoring resource was not found",
                        )
                    if (
                        revision_row["document_fingerprint"]
                        != attestation.document_fingerprint
                    ):
                        raise ValueError("freeze document fingerprint changed")
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_validation_attestations(
                            attestation_id, draft_id, authoring_revision_id,
                            document_fingerprint, validation_contract_version,
                            package_identity, package_content_identity,
                            attestation_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            attestation.attestation_id,
                            draft_id,
                            expected_revision_id,
                            attestation.document_fingerprint,
                            attestation.validation_contract_version,
                            attestation.package_identity,
                            attestation.package_content_identity,
                            attestation_json,
                            attestation.created_at,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_package_revisions(
                            package_revision_id, draft_id,
                            authoring_revision_id, attestation_id,
                            package_identity, package_content_identity,
                            closure_identity, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            package_revision.package_revision_id,
                            draft_id,
                            expected_revision_id,
                            attestation.attestation_id,
                            package_revision.package_identity,
                            package_revision.package_content_identity,
                            package_revision.closure_identity,
                            package_revision.created_at,
                        ),
                    )
                    connection.executemany(
                        """
                        INSERT INTO studio_benchmark_package_revision_members(
                            package_revision_id, ordinal, member_path,
                            descriptor_json
                        ) VALUES (?, ?, ?, ?)
                        """,
                        tuple(
                            (
                                package_revision.package_revision_id,
                                member.ordinal,
                                member.path,
                                _json_text(
                                    member.model_dump(
                                        mode="json",
                                        by_alias=True,
                                    )
                                ),
                            )
                            for member in package_revision.members
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_freeze_commands(
                            draft_id, client_request_id, request_fingerprint,
                            package_revision_id, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            draft_id,
                            client_request_id,
                            request_fingerprint,
                            package_revision.package_revision_id,
                            package_revision.created_at,
                        ),
                    )
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                return (
                    self._load_freeze_detail(
                        connection,
                        draft_id,
                        package_revision.package_revision_id,
                    ),
                    True,
                )
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
            StudioBenchmarkAuthoringRevisionConflictError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark freeze could not be committed atomically",
            ) from error

    def get_package_revision(
        self,
        draft_id: str,
        package_revision_id: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1:
        """Read one exact immutable Package revision through its owning draft.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Exact immutable Package revision identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Owned resource is absent.
            StudioBenchmarkAuthoringStorageError: Durable rows are invalid.

        Returns:
            Strict frozen Package revision and validation attestation.
        """
        try:
            with self._connect() as connection:
                return self._load_freeze_detail(
                    connection,
                    draft_id,
                    package_revision_id,
                )
        except StudioBenchmarkAuthoringNotFoundError:
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package revision could not be read safely",
            ) from error

    @staticmethod
    def _stored_publication_from_row(
        row: sqlite3.Row,
    ) -> StudioBenchmarkStoredPublicationV1:
        """Reconstruct and cross-check one durable publication row.

        Args:
            row: SQLite row containing publication JSON and indexed facts.

        Raises:
            ValueError: JSON, locator, or indexed facts disagree.

        Returns:
            Strict storage-neutral publication record.
        """
        publication = StudioBenchmarkPackagePublicationV1.model_validate(
            json.loads(row["publication_json"])
        )
        indexed = {
            "publication_id": row["publication_id"],
            "draft_id": row["draft_id"],
            "package_revision_id": row["package_revision_id"],
            "package_identity": row["package_identity"],
            "package_content_identity": row["package_content_identity"],
            "closure_identity": row["closure_identity"],
            "catalog_entry_id": row["catalog_entry_id"],
            "created_at": row["created_at"],
        }
        if any(getattr(publication, key) != value for key, value in indexed.items()):
            raise ValueError("stored publication indexes disagree with JSON")
        return StudioBenchmarkStoredPublicationV1(
            publication=publication,
            managedLocator=str(row["managed_locator"]),
        )

    @staticmethod
    def _stored_export_from_row(row: sqlite3.Row) -> StudioBenchmarkStoredExportV1:
        """Reconstruct and cross-check one durable Package export row.

        Args:
            row: SQLite row containing export JSON and indexed facts.

        Raises:
            ValueError: JSON, locator, or indexed facts disagree.

        Returns:
            Strict storage-neutral export record.
        """
        package_export = StudioBenchmarkPackageExportV1.model_validate(
            json.loads(row["export_json"])
        )
        indexed = {
            "export_id": row["export_id"],
            "draft_id": row["draft_id"],
            "package_revision_id": row["package_revision_id"],
            "export_contract_version": row["export_contract_version"],
            "size": row["archive_size"],
            "sha256": row["archive_sha256"],
            "created_at": row["created_at"],
        }
        if any(getattr(package_export, key) != value for key, value in indexed.items()):
            raise ValueError("stored export indexes disagree with JSON")
        return StudioBenchmarkStoredExportV1(
            packageExport=package_export,
            archiveLocator=str(row["archive_locator"]),
        )

    @classmethod
    def _publication_command_result(
        cls,
        connection: sqlite3.Connection,
        *,
        draft_id: str,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackagePublicationV1 | None:
        """Resolve an early publication retry inside one connection.

        Args:
            connection: Active row-enabled SQLite connection.
            draft_id: Owning draft identity.
            client_request_id: Stable client command identity.
            request_fingerprint: Expected canonical command fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: Identity was
                reused with different command semantics.
            ValueError: Durable command relationships are inconsistent.

        Returns:
            Prior immutable publication, or ``None`` for a new command.
        """
        row = connection.execute(
            """
            SELECT c.request_fingerprint, c.requested_package_revision_id,
                   p.*
            FROM studio_benchmark_publication_commands AS c
            JOIN studio_benchmark_package_publications AS p
              ON p.publication_id = c.publication_id
            WHERE c.draft_id = ? AND c.client_request_id = ?
            """,
            (draft_id, client_request_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_fingerprint"] != request_fingerprint:
            raise StudioBenchmarkAuthoringIdempotencyConflictError(
                "benchmark.authoring.publication_request_conflict",
                "Benchmark publication request identity was already used",
            )
        record = cls._stored_publication_from_row(row)
        requested = connection.execute(
            """
            SELECT draft_id FROM studio_benchmark_package_revisions
            WHERE package_revision_id = ?
            """,
            (row["requested_package_revision_id"],),
        ).fetchone()
        if requested is None or requested["draft_id"] != draft_id:
            raise ValueError("publication command ownership is inconsistent")
        return record.publication

    @classmethod
    def _export_command_result(
        cls,
        connection: sqlite3.Connection,
        *,
        draft_id: str,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackageExportV1 | None:
        """Resolve an early export retry inside one connection.

        Args:
            connection: Active row-enabled SQLite connection.
            draft_id: Owning draft identity.
            client_request_id: Stable client command identity.
            request_fingerprint: Expected canonical command fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: Identity was
                reused with different command semantics.
            ValueError: Durable command relationships are inconsistent.

        Returns:
            Prior immutable export, or ``None`` for a new command.
        """
        row = connection.execute(
            """
            SELECT c.request_fingerprint, c.requested_package_revision_id,
                   e.*
            FROM studio_benchmark_export_commands AS c
            JOIN studio_benchmark_package_exports AS e
              ON e.export_id = c.export_id
            WHERE c.draft_id = ? AND c.client_request_id = ?
            """,
            (draft_id, client_request_id),
        ).fetchone()
        if row is None:
            return None
        if row["request_fingerprint"] != request_fingerprint:
            raise StudioBenchmarkAuthoringIdempotencyConflictError(
                "benchmark.authoring.export_request_conflict",
                "Benchmark Package export request identity was already used",
            )
        record = cls._stored_export_from_row(row)
        requested = connection.execute(
            """
            SELECT draft_id FROM studio_benchmark_package_revisions
            WHERE package_revision_id = ?
            """,
            (row["requested_package_revision_id"],),
        ).fetchone()
        if requested is None or requested["draft_id"] != draft_id:
            raise ValueError("export command ownership is inconsistent")
        return record.package_export

    def list_package_revisions(
        self,
        draft_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkPackageRevisionPageV1:
        """List a stable bounded page of frozen revisions for one draft.

        Args:
            draft_id: Owning draft identity.
            limit: Inclusive page size within 1..100.
            cursor: Optional draft-bound continuation cursor.

        Raises:
            StudioBenchmarkAuthoringValidationError: Limit or cursor is invalid.
            StudioBenchmarkAuthoringNotFoundError: Draft is absent.
            StudioBenchmarkAuthoringStorageError: Durable rows are corrupt.

        Returns:
            Strict immutable Package-revision release page.
        """
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= STUDIO_BENCHMARK_PACKAGE_REVISION_PAGE_MAX
        ):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.package_revision_limit_invalid",
                "Benchmark Package revision page limit must be within 1 and 100",
            )
        cursor_facts = (
            _decode_package_revision_cursor(cursor, draft_id=draft_id)
            if cursor is not None
            else None
        )
        try:
            with self._connect() as connection:
                if connection.execute(
                    "SELECT 1 FROM studio_benchmark_authoring_drafts WHERE draft_id = ?",
                    (draft_id,),
                ).fetchone() is None:
                    raise StudioBenchmarkAuthoringNotFoundError(
                        "benchmark.authoring.not_found",
                        "Benchmark authoring resource was not found",
                    )
                where = "p.draft_id = ?"
                parameters: list[object] = [draft_id]
                if cursor_facts is not None:
                    where += (
                        " AND (p.created_at < ? OR "
                        "(p.created_at = ? AND p.package_revision_id < ?))"
                    )
                    parameters.extend(
                        [cursor_facts[0], cursor_facts[0], cursor_facts[1]]
                    )
                rows = connection.execute(
                    f"""
                    SELECT p.package_revision_id
                    FROM studio_benchmark_package_revisions AS p
                    WHERE {where}
                    ORDER BY p.created_at DESC, p.package_revision_id DESC
                    LIMIT ?
                    """,
                    (*parameters, limit + 1),
                ).fetchall()
                selected = rows[:limit]
                items: list[StudioBenchmarkPackageRevisionReleaseSummaryV1] = []
                for row in selected:
                    detail = self._load_freeze_detail(
                        connection,
                        draft_id,
                        str(row["package_revision_id"]),
                    )
                    publication_row = connection.execute(
                        """
                        SELECT * FROM studio_benchmark_package_publications
                        WHERE draft_id = ? AND package_revision_id = ?
                        """,
                        (draft_id, row["package_revision_id"]),
                    ).fetchone()
                    export_row = connection.execute(
                        """
                        SELECT * FROM studio_benchmark_package_exports
                        WHERE draft_id = ? AND package_revision_id = ?
                          AND export_contract_version = ?
                        """,
                        (
                            draft_id,
                            row["package_revision_id"],
                            STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT,
                        ),
                    ).fetchone()
                    items.append(
                        StudioBenchmarkPackageRevisionReleaseSummaryV1.from_package_revision(
                            detail.package_revision,
                            publication=(
                                self._stored_publication_from_row(publication_row).publication
                                if publication_row is not None
                                else None
                            ),
                            package_export=(
                                self._stored_export_from_row(export_row).package_export
                                if export_row is not None
                                else None
                            ),
                        )
                    )
                next_cursor = None
                if len(rows) > limit and items:
                    last = items[-1]
                    next_cursor = _encode_package_revision_cursor(
                        draft_id=draft_id,
                        created_at=last.created_at,
                        package_revision_id=last.package_revision_id,
                    )
                return StudioBenchmarkPackageRevisionPageV1(
                    items=tuple(items),
                    nextCursor=next_cursor,
                )
        except (
            StudioBenchmarkAuthoringNotFoundError,
            StudioBenchmarkAuthoringValidationError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package revisions could not be listed safely",
            ) from error

    def find_publication_result(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackagePublicationV1 | None:
        """Return a matching committed publication retry result.

        Args:
            draft_id: Command-scope draft identity.
            client_request_id: Stable client request identity.
            request_fingerprint: Expected canonical request fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: Fingerprint differs.
            StudioBenchmarkAuthoringStorageError: Durable rows are corrupt.

        Returns:
            Prior publication or ``None``.
        """
        try:
            with self._connect() as connection:
                return self._publication_command_result(
                    connection,
                    draft_id=draft_id,
                    client_request_id=client_request_id,
                    request_fingerprint=request_fingerprint,
                )
        except StudioBenchmarkAuthoringIdempotencyConflictError:
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark publication retry could not be reconstructed",
            ) from error

    def find_export_result(
        self,
        draft_id: str,
        *,
        client_request_id: str,
        request_fingerprint: str,
    ) -> StudioBenchmarkPackageExportV1 | None:
        """Return a matching committed export retry result.

        Args:
            draft_id: Command-scope draft identity.
            client_request_id: Stable client request identity.
            request_fingerprint: Expected canonical request fingerprint.

        Raises:
            StudioBenchmarkAuthoringIdempotencyConflictError: Fingerprint differs.
            StudioBenchmarkAuthoringStorageError: Durable rows are corrupt.

        Returns:
            Prior export or ``None``.
        """
        try:
            with self._connect() as connection:
                return self._export_command_result(
                    connection,
                    draft_id=draft_id,
                    client_request_id=client_request_id,
                    request_fingerprint=request_fingerprint,
                )
        except StudioBenchmarkAuthoringIdempotencyConflictError:
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package export retry could not be reconstructed",
            ) from error

    def find_semantic_publication(
        self,
        package_identity: str,
    ) -> StudioBenchmarkStoredPublicationV1 | None:
        """Resolve the single durable managed authority for a readable version.

        Args:
            package_identity: Safe readable ``publisher/name@version`` identity.

        Raises:
            StudioBenchmarkAuthoringStorageError: Durable rows are corrupt.

        Returns:
            Existing storage-neutral publication or ``None``.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM studio_benchmark_package_publications
                    WHERE package_identity = ?
                    """,
                    (package_identity,),
                ).fetchone()
                return (
                    self._stored_publication_from_row(row)
                    if row is not None
                    else None
                )
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark publication could not be reconstructed",
            ) from error

    def find_package_export(
        self,
        draft_id: str,
        package_revision_id: str,
    ) -> StudioBenchmarkStoredExportV1 | None:
        """Resolve the deterministic export for one exact owned Package.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Exact immutable Package revision.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Package ownership is absent.
            StudioBenchmarkAuthoringStorageError: Durable rows are corrupt.

        Returns:
            Existing storage-neutral export or ``None``.
        """
        try:
            with self._connect() as connection:
                if connection.execute(
                    """
                    SELECT 1 FROM studio_benchmark_package_revisions
                    WHERE draft_id = ? AND package_revision_id = ?
                    """,
                    (draft_id, package_revision_id),
                ).fetchone() is None:
                    raise StudioBenchmarkAuthoringNotFoundError(
                        "benchmark.authoring.package_revision_not_found",
                        "Benchmark Package revision was not found",
                    )
                row = connection.execute(
                    """
                    SELECT * FROM studio_benchmark_package_exports
                    WHERE draft_id = ? AND package_revision_id = ?
                      AND export_contract_version = ?
                    """,
                    (
                        draft_id,
                        package_revision_id,
                        STUDIO_BENCHMARK_PACKAGE_EXPORT_CONTRACT,
                    ),
                ).fetchone()
                return self._stored_export_from_row(row) if row is not None else None
        except StudioBenchmarkAuthoringNotFoundError:
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package export could not be reconstructed",
            ) from error

    def list_publication_records(self) -> tuple[StudioBenchmarkStoredPublicationV1, ...]:
        """Reconstruct all durable managed publications for process startup.

        Raises:
            StudioBenchmarkAuthoringStorageError: Any row is malformed.

        Returns:
            Stable creation-order storage-neutral publication records.
        """
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    """
                    SELECT * FROM studio_benchmark_package_publications
                    ORDER BY created_at ASC, publication_id ASC
                    """
                ).fetchall()
                records = tuple(self._stored_publication_from_row(row) for row in rows)
                identities = [item.publication.package_identity for item in records]
                if len(identities) != len(set(identities)):
                    raise ValueError("durable publication semantics are duplicated")
                return records
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark publications could not be reconstructed",
            ) from error

    def commit_publication(
        self,
        draft_id: str,
        *,
        requested_package_revision_id: str,
        client_request_id: str,
        request_fingerprint: str,
        record: StudioBenchmarkStoredPublicationV1,
    ) -> tuple[StudioBenchmarkPackagePublicationV1, bool]:
        """Atomically commit one publication and its command result.

        Args:
            draft_id: Owning command-scope draft identity.
            requested_package_revision_id: Immutable release candidate.
            client_request_id: Stable client command identity.
            request_fingerprint: Canonical operation fingerprint.
            record: Prepared strict publication plus opaque locator.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Package ownership is hidden.
            StudioBenchmarkAuthoringIdempotencyConflictError: Request ID differs.
            StudioBenchmarkAuthoringReleaseConflictError: Readable version differs.
            StudioBenchmarkAuthoringStorageError: Transaction or rows fail.

        Returns:
            Durable publication and whether this transaction created it.
        """
        publication = record.publication
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    retry = self._publication_command_result(
                        connection,
                        draft_id=draft_id,
                        client_request_id=client_request_id,
                        request_fingerprint=request_fingerprint,
                    )
                    if retry is not None:
                        connection.execute("COMMIT")
                        return retry, False
                    detail = self._load_freeze_detail(
                        connection, draft_id, requested_package_revision_id
                    )
                    package = detail.package_revision
                    existing_row = connection.execute(
                        """
                        SELECT * FROM studio_benchmark_package_publications
                        WHERE package_identity = ?
                        """,
                        (publication.package_identity,),
                    ).fetchone()
                    if existing_row is not None:
                        existing = self._stored_publication_from_row(existing_row)
                        if (
                            existing.publication.package_identity
                            != package.package_identity
                            or existing.publication.package_content_identity
                            != package.package_content_identity
                            or existing.publication.closure_identity
                            != package.closure_identity
                        ):
                            raise StudioBenchmarkAuthoringReleaseConflictError(
                                "benchmark.authoring.publication_version_conflict",
                                "Benchmark Package version has different published content",
                            )
                        connection.execute(
                            """
                            INSERT INTO studio_benchmark_publication_commands(
                                draft_id, client_request_id, request_fingerprint,
                                requested_package_revision_id, publication_id,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                draft_id,
                                client_request_id,
                                request_fingerprint,
                                requested_package_revision_id,
                                existing.publication.publication_id,
                                publication.created_at,
                            ),
                        )
                        connection.execute("COMMIT")
                        return existing.publication, False
                    if any(
                        (
                            publication.draft_id != draft_id,
                            publication.package_revision_id
                            != requested_package_revision_id,
                            publication.validation_attestation_id
                            != package.validation_attestation_id,
                            publication.package_identity != package.package_identity,
                            publication.package_content_identity
                            != package.package_content_identity,
                            publication.closure_identity != package.closure_identity,
                        )
                    ):
                        raise ValueError("publication does not match immutable Package")
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_package_publications(
                            publication_id, draft_id, package_revision_id,
                            package_identity, package_content_identity,
                            closure_identity, catalog_entry_id, managed_locator,
                            publication_json, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            publication.publication_id,
                            draft_id,
                            requested_package_revision_id,
                            publication.package_identity,
                            publication.package_content_identity,
                            publication.closure_identity,
                            publication.catalog_entry_id,
                            record.managed_locator,
                            _json_text(publication.model_dump(mode="json", by_alias=True)),
                            publication.created_at,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_publication_commands(
                            draft_id, client_request_id, request_fingerprint,
                            requested_package_revision_id, publication_id,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            draft_id,
                            client_request_id,
                            request_fingerprint,
                            requested_package_revision_id,
                            publication.publication_id,
                            publication.created_at,
                        ),
                    )
                    connection.execute("COMMIT")
                    return publication, True
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
            StudioBenchmarkAuthoringReleaseConflictError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark publication could not be committed atomically",
            ) from error

    def commit_export(
        self,
        draft_id: str,
        *,
        requested_package_revision_id: str,
        client_request_id: str,
        request_fingerprint: str,
        record: StudioBenchmarkStoredExportV1,
    ) -> tuple[StudioBenchmarkPackageExportV1, bool]:
        """Atomically commit one deterministic export and command result.

        Args:
            draft_id: Owning command-scope draft identity.
            requested_package_revision_id: Immutable release candidate.
            client_request_id: Stable client command identity.
            request_fingerprint: Canonical operation fingerprint.
            record: Prepared strict export plus opaque archive locator.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Package ownership is hidden.
            StudioBenchmarkAuthoringIdempotencyConflictError: Request ID differs.
            StudioBenchmarkAuthoringStorageError: Transaction or rows fail.

        Returns:
            Durable export and whether this transaction created it.
        """
        package_export = record.package_export
        if (
            package_export.draft_id != draft_id
            or package_export.package_revision_id != requested_package_revision_id
        ):
            raise ValueError("export ownership does not match command")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    retry = self._export_command_result(
                        connection,
                        draft_id=draft_id,
                        client_request_id=client_request_id,
                        request_fingerprint=request_fingerprint,
                    )
                    if retry is not None:
                        connection.execute("COMMIT")
                        return retry, False
                    detail = self._load_freeze_detail(
                        connection, draft_id, requested_package_revision_id
                    )
                    package = detail.package_revision
                    if any(
                        (
                            package_export.validation_attestation_id
                            != package.validation_attestation_id,
                            package_export.package_identity != package.package_identity,
                            package_export.package_content_identity
                            != package.package_content_identity,
                            package_export.closure_identity != package.closure_identity,
                            package_export.member_count != len(package.members),
                        )
                    ):
                        raise ValueError("export does not match immutable Package")
                    existing_row = connection.execute(
                        """
                        SELECT * FROM studio_benchmark_package_exports
                        WHERE package_revision_id = ?
                          AND export_contract_version = ?
                        """,
                        (
                            requested_package_revision_id,
                            package_export.export_contract_version,
                        ),
                    ).fetchone()
                    if existing_row is not None:
                        existing = self._stored_export_from_row(existing_row)
                        connection.execute(
                            """
                            INSERT INTO studio_benchmark_export_commands(
                                draft_id, client_request_id, request_fingerprint,
                                requested_package_revision_id, export_id,
                                created_at
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                draft_id,
                                client_request_id,
                                request_fingerprint,
                                requested_package_revision_id,
                                existing.package_export.export_id,
                                package_export.created_at,
                            ),
                        )
                        connection.execute("COMMIT")
                        return existing.package_export, False
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_package_exports(
                            export_id, draft_id, package_revision_id,
                            export_contract_version, archive_size,
                            archive_sha256, archive_locator, export_json,
                            created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            package_export.export_id,
                            draft_id,
                            requested_package_revision_id,
                            package_export.export_contract_version,
                            package_export.size,
                            package_export.sha256,
                            record.archive_locator,
                            _json_text(package_export.model_dump(mode="json", by_alias=True)),
                            package_export.created_at,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_export_commands(
                            draft_id, client_request_id, request_fingerprint,
                            requested_package_revision_id, export_id, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            draft_id,
                            client_request_id,
                            request_fingerprint,
                            requested_package_revision_id,
                            package_export.export_id,
                            package_export.created_at,
                        ),
                    )
                    connection.execute("COMMIT")
                    return package_export, True
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkAuthoringIdempotencyConflictError,
            StudioBenchmarkAuthoringNotFoundError,
        ):
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package export could not be committed atomically",
            ) from error

    def get_publication(
        self,
        draft_id: str,
        package_revision_id: str,
        publication_id: str,
    ) -> StudioBenchmarkPackagePublicationV1:
        """Read one exact publication through full immutable ownership.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Owning Package revision identity.
            publication_id: Exact publication identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Exact ownership is absent.
            StudioBenchmarkAuthoringStorageError: Durable metadata is corrupt.

        Returns:
            Strict immutable publication.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM studio_benchmark_package_publications
                    WHERE draft_id = ? AND package_revision_id = ?
                      AND publication_id = ?
                    """,
                    (draft_id, package_revision_id, publication_id),
                ).fetchone()
                if row is None:
                    raise StudioBenchmarkAuthoringNotFoundError(
                        "benchmark.authoring.publication_not_found",
                        "Benchmark Package publication was not found",
                    )
                return self._stored_publication_from_row(row).publication
        except StudioBenchmarkAuthoringNotFoundError:
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package publication could not be read safely",
            ) from error

    def get_export_record(
        self,
        draft_id: str,
        package_revision_id: str,
        export_id: str,
    ) -> StudioBenchmarkStoredExportV1:
        """Read one exact export and private opaque locator by full ownership.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Owning Package revision identity.
            export_id: Exact export identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Exact ownership is absent.
            StudioBenchmarkAuthoringStorageError: Durable metadata is corrupt.

        Returns:
            Strict storage-neutral export row.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT * FROM studio_benchmark_package_exports
                    WHERE draft_id = ? AND package_revision_id = ?
                      AND export_id = ?
                    """,
                    (draft_id, package_revision_id, export_id),
                ).fetchone()
                if row is None:
                    raise StudioBenchmarkAuthoringNotFoundError(
                        "benchmark.authoring.export_not_found",
                        "Benchmark Package export was not found",
                    )
                return self._stored_export_from_row(row)
        except StudioBenchmarkAuthoringNotFoundError:
            raise
        except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark Package export could not be read safely",
            ) from error

    def get_export(
        self,
        draft_id: str,
        package_revision_id: str,
        export_id: str,
    ) -> StudioBenchmarkPackageExportV1:
        """Read one exact public export descriptor by full ownership.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Owning Package revision identity.
            export_id: Exact export identity.

        Raises:
            StudioBenchmarkAuthoringNotFoundError: Exact ownership is absent.
            StudioBenchmarkAuthoringStorageError: Durable metadata is corrupt.

        Returns:
            Strict immutable Package export.
        """
        return self.get_export_record(
            draft_id, package_revision_id, export_id
        ).package_export


__all__ = ["SQLiteStudioBenchmarkAuthoringRepository"]
