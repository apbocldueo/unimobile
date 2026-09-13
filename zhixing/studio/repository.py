"""Database-neutral Agent revision contracts and the default SQLite adapter."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field, model_validator

from zhixing.graph import GraphDiagnostic, SourceMapEntry

from .database import connect_studio_database, migrate_studio_database
from .models import (
    StudioAuthoringDocument,
    StudioCapabilityDocument,
    StudioModel,
    StudioProjectionEntry,
    parse_studio_authoring_document,
)


class AgentDocumentRepositoryError(RuntimeError):
    """Base error for safe Agent document repository failures."""


class AgentNotFoundError(AgentDocumentRepositoryError, LookupError):
    """Requested Agent identity does not exist."""


class AgentRevisionNotFoundError(AgentDocumentRepositoryError, LookupError):
    """Requested revision does not exist for the selected Agent."""


class AgentRevisionConflictError(AgentDocumentRepositoryError):
    """Save base differs from the Agent current revision."""

    def __init__(self, current_revision_id: str | None) -> None:
        """Create an optimistic concurrency conflict.

        Args:
            current_revision_id (str | None): Current server revision.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__("Agent revision base is stale")
        self.current_revision_id = current_revision_id


class CompileSnapshot(StudioModel):
    """Immutable compile evidence stored with one authoring revision."""

    status: Literal["valid", "invalid"]
    diagnostics: tuple[GraphDiagnostic, ...] = ()
    source_map: tuple[SourceMapEntry, ...] = ()
    agent_graph: dict[str, Any] | None = None
    canonical_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    authoring_policy: str | None = None
    lowering_profile: str | None = None
    capability_hash: str | None = Field(
        default=None,
        pattern=r"^sha256:[0-9a-f]{64}$",
    )
    projection_map: tuple[StudioProjectionEntry, ...] = ()

    @model_validator(mode="after")
    def _status_shape(self) -> "CompileSnapshot":
        """Keep runnable graph identity exclusive to valid snapshots.

        Args:
            None.

        Raises:
            ValueError: Status and graph/hash fields disagree.

        Returns:
            CompileSnapshot: Validated snapshot.
        """
        if self.status == "valid":
            if self.agent_graph is None or self.canonical_hash is None:
                raise ValueError("valid snapshot requires AgentGraph and canonical hash")
        elif self.agent_graph is not None or self.canonical_hash is not None:
            raise ValueError("invalid snapshot cannot contain AgentGraph or hash")
        closure = (
            self.authoring_policy,
            self.lowering_profile,
            self.capability_hash,
        )
        if any(item is not None for item in closure) and not all(
            item is not None for item in closure
        ):
            raise ValueError("capability compile identity closure must be complete")
        if self.projection_map and not all(item is not None for item in closure):
            raise ValueError("projection map requires capability compile identity closure")
        return self


class AgentRecord(StudioModel):
    """Mutable Agent metadata with a stable identity."""

    agent_id: str
    name: str
    current_revision_id: str | None = None
    created_at: int
    updated_at: int


class AgentRevisionRecord(StudioModel):
    """Immutable Studio authoring revision and compile snapshot."""

    revision_id: str
    agent_id: str
    ordinal: int = Field(ge=1)
    parent_revision_id: str | None = None
    document: StudioAuthoringDocument
    compile_snapshot: CompileSnapshot
    created_at: int


class AgentPage(StudioModel):
    """Stable bounded Agent list page."""

    items: tuple[AgentRecord, ...]
    next_cursor: str | None = None


class AgentDocumentRepository(Protocol):
    """Persistence contract that does not expose SQLite implementation details."""

    def create_agent(
        self,
        name: str,
        document: StudioAuthoringDocument,
        snapshot: CompileSnapshot,
    ) -> tuple[AgentRecord, AgentRevisionRecord]:
        """Create one Agent and its initial immutable revision atomically."""

    def list_agents(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AgentPage:
        """List Agents using a stable bounded cursor."""

    def get_agent(self, agent_id: str) -> AgentRecord:
        """Read Agent metadata by stable identity."""

    def rename_agent(self, agent_id: str, name: str) -> AgentRecord:
        """Rename Agent metadata without mutating revisions."""

    def get_revision(
        self,
        agent_id: str,
        revision_id: str,
    ) -> AgentRevisionRecord:
        """Read one immutable revision belonging to an Agent."""

    def save_revision(
        self,
        agent_id: str,
        *,
        base_revision_id: str | None,
        document: StudioAuthoringDocument,
        snapshot: CompileSnapshot,
    ) -> tuple[AgentRecord, AgentRevisionRecord]:
        """Append a revision if the optimistic base is current."""


def workspace_identity(workspace: str | Path) -> str:
    """Derive a stable opaque identity without persisting the absolute path.

    Args:
        workspace (str | Path): Workspace root.

    Raises:
        OSError: Path resolution fails.

    Returns:
        str: SHA-256-prefixed workspace identity.
    """
    resolved = str(Path(workspace).expanduser().resolve())
    digest = hashlib.sha256(resolved.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def studio_user_data_directory() -> Path:
    """Resolve the operating-system user data directory for ZhiXing Studio.

    Args:
        None.

    Raises:
        RuntimeError: A Windows data directory cannot be resolved.

    Returns:
        Path: User-scoped Studio data directory.
    """
    if sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        configured = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if not configured:
            raise RuntimeError("Windows user data directory is unavailable")
        root = Path(configured)
    else:
        configured = os.environ.get("XDG_DATA_HOME")
        root = Path(configured) if configured else Path.home() / ".local" / "share"
    return root / "ZhiXing" / "studio"


def default_studio_database_path(
    workspace: str | Path,
    *,
    data_directory: str | Path | None = None,
) -> Path:
    """Resolve a workspace-isolated SQLite path outside the Git workspace.

    Args:
        workspace (str | Path): Workspace root used only to derive an opaque
            identity.
        data_directory (str | Path | None): Explicit test/config override.

    Raises:
        OSError: Workspace or user path resolution fails.

    Returns:
        Path: SQLite database path.
    """
    root = (
        Path(data_directory).expanduser()
        if data_directory is not None
        else studio_user_data_directory()
    )
    digest = workspace_identity(workspace).split(":", 1)[1][:24]
    return root / "workspaces" / digest / "studio.sqlite3"


def _json_text(value: Any) -> str:
    """Encode deterministic finite JSON for SQLite.

    Args:
        value (Any): JSON-compatible value.

    Raises:
        TypeError: Value is not JSON-compatible.
        ValueError: Value contains non-finite floats.

    Returns:
        str: Compact deterministic JSON.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _new_id(prefix: str) -> str:
    """Create one opaque stable resource identity.

    Args:
        prefix (str): Human-readable resource prefix.

    Raises:
        None.

    Returns:
        str: Prefix plus UUID hex.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


def _encode_cursor(updated_at: int, agent_id: str) -> str:
    """Encode a storage-neutral pagination cursor.

    Args:
        updated_at (int): Last item update timestamp.
        agent_id (str): Last item stable identity.

    Raises:
        None.

    Returns:
        str: URL-safe opaque cursor.
    """
    payload = _json_text({"updatedAt": updated_at, "agentId": agent_id}).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[int, str]:
    """Decode and validate a storage-neutral pagination cursor.

    Args:
        cursor (str): Opaque URL-safe cursor.

    Raises:
        ValueError: Cursor is malformed.

    Returns:
        tuple[int, str]: Update timestamp and Agent identity.
    """
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
        updated_at = int(parsed["updatedAt"])
        agent_id = str(parsed["agentId"])
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise ValueError("invalid Agent list cursor") from error
    if not agent_id:
        raise ValueError("invalid Agent list cursor")
    return updated_at, agent_id


class SQLiteAgentDocumentRepository:
    """SQLite implementation of the AgentDocumentRepository contract."""

    def __init__(self, database_path: str | Path) -> None:
        """Open or create a versioned Studio database.

        Args:
            database_path (str | Path): Explicit SQLite database path.

        Raises:
            OSError: Parent directory cannot be created.
            sqlite3.Error: Database migration fails.

        Returns:
            None.
        """
        self._database_path = Path(database_path).expanduser()
        migrate_studio_database(self._database_path)

    @property
    def database_path(self) -> Path:
        """Return the adapter-local database path for operational tooling.

        The path is never included in repository DTOs or HTTP responses.

        Args:
            None.

        Raises:
            None.

        Returns:
            Path: Configured SQLite database path.
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
    def _agent_from_row(row: sqlite3.Row) -> AgentRecord:
        """Map one SQLite row to an implementation-neutral Agent DTO.

        Args:
            row (sqlite3.Row): Agent row.

        Raises:
            ValueError: Stored data is invalid.

        Returns:
            AgentRecord: Stable Agent metadata.
        """
        return AgentRecord(
            agent_id=row["agent_id"],
            name=row["name"],
            current_revision_id=row["current_revision_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _revision_from_row(row: sqlite3.Row) -> AgentRevisionRecord:
        """Map one SQLite row to an immutable revision DTO.

        Args:
            row (sqlite3.Row): Revision row.

        Raises:
            ValueError: Stored JSON violates current contracts.

        Returns:
            AgentRevisionRecord: Parsed immutable revision.
        """
        diagnostics = tuple(
            GraphDiagnostic.model_validate(item)
            for item in json.loads(row["diagnostics_json"])
        )
        source_map = tuple(
            SourceMapEntry.model_validate(item)
            for item in json.loads(row["source_map_json"])
        )
        graph = (
            json.loads(row["agent_graph_json"])
            if row["agent_graph_json"] is not None
            else None
        )
        return AgentRevisionRecord(
            revision_id=row["revision_id"],
            agent_id=row["agent_id"],
            ordinal=row["ordinal"],
            parent_revision_id=row["parent_revision_id"],
            document=parse_studio_authoring_document(json.loads(row["document_json"])),
            compile_snapshot=CompileSnapshot(
                status=row["compile_status"],
                diagnostics=diagnostics,
                source_map=source_map,
                agent_graph=graph,
                canonical_hash=row["canonical_hash"],
                authoring_policy=row["authoring_policy"],
                lowering_profile=row["lowering_profile"],
                capability_hash=row["capability_hash"],
                projection_map=tuple(
                    StudioProjectionEntry.model_validate(item)
                    for item in json.loads(row["projection_map_json"] or "[]")
                ),
            ),
            created_at=row["created_at"],
        )

    @staticmethod
    def _validate_name(name: str) -> str:
        """Normalize and validate an Agent display name.

        Args:
            name (str): Candidate display name.

        Raises:
            ValueError: Name is blank or too long.

        Returns:
            str: Trimmed display name.
        """
        normalized = str(name).strip()
        if not normalized or len(normalized) > 256:
            raise ValueError("Agent name must contain 1 to 256 characters")
        return normalized

    @staticmethod
    def _serialized_revision(
        document: StudioAuthoringDocument,
        snapshot: CompileSnapshot,
    ) -> tuple[str, str, str, str | None, str]:
        """Serialize validated revision values before entering a transaction.

        Args:
            document (StudioAuthoringDocument): Strict authoring document.
            snapshot (CompileSnapshot): Strict compile snapshot.

        Raises:
            TypeError: A value is not JSON serializable.
            ValueError: A value contains non-finite JSON.

        Returns:
            tuple[str, str, str, str | None, str]: Document, diagnostics,
            source map, optional graph JSON, and projection map JSON.
        """
        if (
            isinstance(document, StudioCapabilityDocument)
            and snapshot.status == "valid"
            and (
                snapshot.authoring_policy is None
                or snapshot.lowering_profile is None
                or snapshot.capability_hash is None
                or not snapshot.projection_map
            )
        ):
            raise ValueError(
                "valid schema-3 revision requires complete policy and projection evidence"
            )
        return (
            _json_text(document.to_json_dict()),
            _json_text([item.to_safe_dict() for item in snapshot.diagnostics]),
            _json_text(
                [
                    item.model_dump(mode="json", exclude_none=True)
                    for item in snapshot.source_map
                ]
            ),
            _json_text(snapshot.agent_graph)
            if snapshot.agent_graph is not None
            else None,
            _json_text(
                [
                    item.model_dump(mode="json", by_alias=True, exclude_none=True)
                    for item in snapshot.projection_map
                ]
            ),
        )

    @staticmethod
    def _insert_revision(
        connection: sqlite3.Connection,
        *,
        revision_id: str,
        agent_id: str,
        ordinal: int,
        parent_revision_id: str | None,
        document_json: str,
        snapshot: CompileSnapshot,
        diagnostics_json: str,
        source_map_json: str,
        graph_json: str | None,
        projection_map_json: str,
        created_at: int,
    ) -> None:
        """Insert one immutable revision row inside a caller transaction.

        Args:
            connection (sqlite3.Connection): Active transaction.
            revision_id (str): New revision identity.
            agent_id (str): Parent Agent identity.
            ordinal (int): Monotonic Agent-local ordinal.
            parent_revision_id (str | None): Previous current revision.
            document_json (str): Strict Studio document JSON.
            snapshot (CompileSnapshot): Compile status and identity.
            diagnostics_json (str): Safe diagnostics JSON.
            source_map_json (str): Safe source map JSON.
            graph_json (str | None): Valid AgentGraph JSON.
            projection_map_json (str): Generated-to-capability mapping JSON.
            created_at (int): Millisecond timestamp.

        Raises:
            sqlite3.Error: Insert fails.

        Returns:
            None.
        """
        connection.execute(
            """
            INSERT INTO studio_agent_revisions(
                revision_id, agent_id, ordinal, parent_revision_id,
                document_json, compile_status, diagnostics_json,
                source_map_json, agent_graph_json, canonical_hash,
                authoring_policy, lowering_profile, capability_hash,
                projection_map_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                revision_id,
                agent_id,
                ordinal,
                parent_revision_id,
                document_json,
                snapshot.status,
                diagnostics_json,
                source_map_json,
                graph_json,
                snapshot.canonical_hash,
                snapshot.authoring_policy,
                snapshot.lowering_profile,
                snapshot.capability_hash,
                projection_map_json,
                created_at,
            ),
        )

    def create_agent(
        self,
        name: str,
        document: StudioAuthoringDocument,
        snapshot: CompileSnapshot,
    ) -> tuple[AgentRecord, AgentRevisionRecord]:
        """Create one Agent and initial revision in one transaction.

        Args:
            name (str): Agent display name.
            document (StudioAuthoringDocument): Initial strict document.
            snapshot (CompileSnapshot): Initial compile snapshot.

        Raises:
            ValueError: Name or document identity is invalid.
            sqlite3.Error: Transaction fails.

        Returns:
            tuple[AgentRecord, AgentRevisionRecord]: Created metadata and
            immutable revision.
        """
        normalized_name = self._validate_name(name)
        document_json, diagnostics_json, source_map_json, graph_json, projection_json = (
            self._serialized_revision(document, snapshot)
        )
        agent_id = document.agent_id
        revision_id = _new_id("revision")
        now = time.time_ns() // 1_000_000
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO studio_agents(
                        agent_id, name, current_revision_id, created_at, updated_at
                    ) VALUES (?, ?, NULL, ?, ?)
                    """,
                    (agent_id, normalized_name, now, now),
                )
                self._insert_revision(
                    connection,
                    revision_id=revision_id,
                    agent_id=agent_id,
                    ordinal=1,
                    parent_revision_id=None,
                    document_json=document_json,
                    snapshot=snapshot,
                    diagnostics_json=diagnostics_json,
                    source_map_json=source_map_json,
                    graph_json=graph_json,
                    projection_map_json=projection_json,
                    created_at=now,
                )
                connection.execute(
                    """
                    UPDATE studio_agents
                    SET current_revision_id = ?, updated_at = ?
                    WHERE agent_id = ?
                    """,
                    (revision_id, now, agent_id),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_agent(agent_id), self.get_revision(agent_id, revision_id)

    def list_agents(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AgentPage:
        """List Agents in updated-descending stable order.

        Args:
            limit (int): Page size from 1 through 100.
            cursor (str | None): Opaque cursor from a previous page.

        Raises:
            ValueError: Limit or cursor is invalid.
            sqlite3.Error: Query fails.

        Returns:
            AgentPage: Bounded Agent page.
        """
        if not 1 <= limit <= 100:
            raise ValueError("Agent page limit must be between 1 and 100")
        parameters: list[Any] = []
        where = ""
        if cursor is not None:
            updated_at, agent_id = _decode_cursor(cursor)
            where = (
                "WHERE updated_at < ? OR "
                "(updated_at = ? AND agent_id > ?)"
            )
            parameters.extend((updated_at, updated_at, agent_id))
        parameters.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT agent_id, name, current_revision_id, created_at, updated_at
                FROM studio_agents
                {where}
                ORDER BY updated_at DESC, agent_id ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        has_more = len(rows) > limit
        selected = rows[:limit]
        items = tuple(self._agent_from_row(row) for row in selected)
        next_cursor = (
            _encode_cursor(items[-1].updated_at, items[-1].agent_id)
            if has_more and items
            else None
        )
        return AgentPage(items=items, next_cursor=next_cursor)

    def get_agent(self, agent_id: str) -> AgentRecord:
        """Read Agent metadata by stable identity.

        Args:
            agent_id (str): Stable Agent identity.

        Raises:
            AgentNotFoundError: Agent does not exist.
            sqlite3.Error: Query fails.

        Returns:
            AgentRecord: Agent metadata.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT agent_id, name, current_revision_id, created_at, updated_at
                FROM studio_agents WHERE agent_id = ?
                """,
                (agent_id,),
            ).fetchone()
        if row is None:
            raise AgentNotFoundError("Agent not found")
        return self._agent_from_row(row)

    def rename_agent(self, agent_id: str, name: str) -> AgentRecord:
        """Rename Agent metadata without changing revision data.

        Args:
            agent_id (str): Stable Agent identity.
            name (str): New display name.

        Raises:
            ValueError: Name is invalid.
            AgentNotFoundError: Agent does not exist.
            sqlite3.Error: Update fails.

        Returns:
            AgentRecord: Updated metadata.
        """
        normalized_name = self._validate_name(name)
        now = time.time_ns() // 1_000_000
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE studio_agents SET name = ?, updated_at = ?
                WHERE agent_id = ?
                """,
                (normalized_name, now, agent_id),
            )
        if cursor.rowcount == 0:
            raise AgentNotFoundError("Agent not found")
        return self.get_agent(agent_id)

    def get_revision(
        self,
        agent_id: str,
        revision_id: str,
    ) -> AgentRevisionRecord:
        """Read one immutable revision by Agent and revision identity.

        Args:
            agent_id (str): Stable Agent identity.
            revision_id (str): Stable revision identity.

        Raises:
            AgentRevisionNotFoundError: Revision is absent or belongs to
                another Agent.
            sqlite3.Error: Query fails.
            ValueError: Stored data violates current contracts.

        Returns:
            AgentRevisionRecord: Immutable revision.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT revision_id, agent_id, ordinal, parent_revision_id,
                       document_json, compile_status, diagnostics_json,
                       source_map_json, agent_graph_json, canonical_hash,
                       authoring_policy, lowering_profile, capability_hash,
                       projection_map_json,
                       created_at
                FROM studio_agent_revisions
                WHERE agent_id = ? AND revision_id = ?
                """,
                (agent_id, revision_id),
            ).fetchone()
        if row is None:
            raise AgentRevisionNotFoundError("Agent revision not found")
        return self._revision_from_row(row)

    def save_revision(
        self,
        agent_id: str,
        *,
        base_revision_id: str | None,
        document: StudioAuthoringDocument,
        snapshot: CompileSnapshot,
    ) -> tuple[AgentRecord, AgentRevisionRecord]:
        """Append an immutable revision with optimistic conflict detection.

        Args:
            agent_id (str): Stable Agent identity.
            base_revision_id (str | None): Client-observed current revision.
            document (StudioAuthoringDocument): Strict authoring document.
            snapshot (CompileSnapshot): Compile evidence.

        Raises:
            ValueError: Document Agent identity differs.
            AgentNotFoundError: Agent does not exist.
            AgentRevisionConflictError: Base revision is stale.
            sqlite3.Error: Transaction fails.

        Returns:
            tuple[AgentRecord, AgentRevisionRecord]: Updated Agent and new
            immutable revision.
        """
        if document.agent_id != agent_id:
            raise ValueError("document agentId does not match request Agent")
        document_json, diagnostics_json, source_map_json, graph_json, projection_json = (
            self._serialized_revision(document, snapshot)
        )
        revision_id = _new_id("revision")
        now = time.time_ns() // 1_000_000
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                agent = connection.execute(
                    """
                    SELECT current_revision_id FROM studio_agents
                    WHERE agent_id = ?
                    """,
                    (agent_id,),
                ).fetchone()
                if agent is None:
                    raise AgentNotFoundError("Agent not found")
                current_revision_id = agent["current_revision_id"]
                if current_revision_id != base_revision_id:
                    raise AgentRevisionConflictError(current_revision_id)
                row = connection.execute(
                    """
                    SELECT COALESCE(MAX(ordinal), 0) AS ordinal
                    FROM studio_agent_revisions WHERE agent_id = ?
                    """,
                    (agent_id,),
                ).fetchone()
                ordinal = int(row["ordinal"]) + 1
                self._insert_revision(
                    connection,
                    revision_id=revision_id,
                    agent_id=agent_id,
                    ordinal=ordinal,
                    parent_revision_id=current_revision_id,
                    document_json=document_json,
                    snapshot=snapshot,
                    diagnostics_json=diagnostics_json,
                    source_map_json=source_map_json,
                    graph_json=graph_json,
                    projection_map_json=projection_json,
                    created_at=now,
                )
                connection.execute(
                    """
                    UPDATE studio_agents
                    SET current_revision_id = ?, updated_at = ?
                    WHERE agent_id = ?
                    """,
                    (revision_id, now, agent_id),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return self.get_agent(agent_id), self.get_revision(agent_id, revision_id)


__all__ = [
    "AgentDocumentRepository",
    "AgentDocumentRepositoryError",
    "AgentNotFoundError",
    "AgentPage",
    "AgentRecord",
    "AgentRevisionConflictError",
    "AgentRevisionNotFoundError",
    "AgentRevisionRecord",
    "CompileSnapshot",
    "SQLiteAgentDocumentRepository",
    "default_studio_database_path",
    "studio_user_data_directory",
    "workspace_identity",
]
