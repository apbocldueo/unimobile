"""SQLite metadata and local artifact storage for Studio Replay."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, BinaryIO

from .replay_adapters import REPLAY_PACKAGE_SCHEMA_VERSION
from .replay_contracts import (
    ReplayArtifactNotFoundError,
    ReplayArtifactRecord,
    ReplayConflictError,
    ReplayImportArtifact,
    ReplayImportCandidate,
    ReplayImportError,
    ReplayNotFoundError,
    replay_list_item,
)
from .replay_models import (
    ReplayArtifactDescriptor,
    ReplayEvidenceAvailability,
    ReplayEvidenceEnvelope,
    ReplayListItem,
    ReplayPage,
)
from .database import connect_studio_database, migrate_studio_database


_STABLE_AGENT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")


def default_studio_artifact_directory(database_path: str | Path) -> Path:
    """Resolve the Local Artifact Store next to the workspace-isolated DB.

    Args:
        database_path (str | Path): Configured Studio SQLite database.

    Raises:
        None.

    Returns:
        Path: Sibling Replay artifact root.
    """
    return Path(database_path).expanduser().parent / "artifacts"


def _json_text(value: Any) -> str:
    """Encode deterministic finite JSON for persistence and bundles.

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


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    """Hash a binary stream from its current position.

    Args:
        stream (BinaryIO): Readable binary stream.

    Raises:
        OSError: Stream cannot be read.

    Returns:
        tuple[str, int]: Prefixed SHA-256 and byte count.
    """
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        digest.update(chunk)
        size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


def _encode_cursor(imported_at: int, run_id: str) -> str:
    """Encode a storage-neutral Replay pagination cursor.

    Args:
        imported_at (int): Last row import timestamp.
        run_id (str): Last row stable run identity.

    Raises:
        None.

    Returns:
        str: URL-safe opaque cursor.
    """
    payload = _json_text({"importedAt": imported_at, "runId": run_id}).encode(
        "utf-8"
    )
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[int, str]:
    """Decode and validate a Replay cursor.

    Args:
        cursor (str): Opaque URL-safe cursor.

    Raises:
        ValueError: Cursor is malformed.

    Returns:
        tuple[int, str]: Import timestamp and run identity.
    """
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        parsed = json.loads(raw.decode("utf-8"))
        imported_at = int(parsed["importedAt"])
        run_id = str(parsed["runId"])
    except (KeyError, TypeError, ValueError, UnicodeError) as error:
        raise ValueError("invalid Replay list cursor") from error
    if not run_id:
        raise ValueError("invalid Replay list cursor")
    return imported_at, run_id


class SQLiteReplayRepository:
    """SQLite implementation of the structured Replay repository contract."""

    def __init__(self, database_path: str | Path) -> None:
        """Open a migrated Studio database.

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

    def _connect(self) -> sqlite3.Connection:
        """Create one configured short-lived connection.

        Args:
            None.

        Raises:
            sqlite3.Error: Connection setup fails.

        Returns:
            sqlite3.Connection: Row-enabled connection.
        """
        return connect_studio_database(self._database_path)

    def create_replay(
        self,
        envelope: ReplayEvidenceEnvelope,
        artifacts: tuple[ReplayArtifactRecord, ...],
    ) -> ReplayEvidenceEnvelope:
        """Persist one immutable Replay and artifact index atomically.

        Args:
            envelope (ReplayEvidenceEnvelope): Verified public evidence.
            artifacts (tuple[ReplayArtifactRecord, ...]): Internal storage refs.

        Raises:
            ReplayConflictError: Run identity already exists.
            ValueError: Artifact records do not match the envelope.
            sqlite3.Error: Transaction fails.

        Returns:
            ReplayEvidenceEnvelope: Persisted immutable envelope.
        """
        expected = {
            item.artifact_id: item
            for item in envelope.artifacts
            if item.availability in {"available", "redacted", "truncated"}
        }
        actual = {item.descriptor.artifact_id: item.descriptor for item in artifacts}
        if expected != actual:
            raise ValueError("Replay artifact records do not match envelope")
        item = replay_list_item(envelope)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    INSERT INTO studio_replays(
                        run_id, agent_id, agent_status, benchmark_outcome,
                        provenance, integrity_state, evidence_completeness,
                        imported_at, envelope_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item.run_id,
                        item.agent_id,
                        item.agent_status,
                        item.benchmark_outcome,
                        item.provenance,
                        item.integrity_state,
                        item.evidence_completeness,
                        item.imported_at,
                        _json_text(
                            envelope.model_dump(
                                mode="json",
                                by_alias=True,
                                exclude_none=True,
                            )
                        ),
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO studio_replay_moments(
                        run_id, causal_index, moment_id, source_kind,
                        source_sequence, phase, kind, node_path,
                        activation_id, interaction_step, moment_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            envelope.run_id,
                            moment.causal_index,
                            moment.moment_id,
                            moment.source_kind,
                            moment.source_sequence,
                            moment.phase,
                            moment.kind,
                            moment.node_path,
                            moment.activation_id,
                            moment.interaction_step,
                            _json_text(
                                moment.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                        )
                        for moment in envelope.moments
                    ],
                )
                connection.executemany(
                    """
                    INSERT INTO studio_replay_artifacts(
                        run_id, artifact_id, availability, content_type,
                        size, sha256, storage_ref, descriptor_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            envelope.run_id,
                            record.descriptor.artifact_id,
                            record.descriptor.availability,
                            record.descriptor.content_type,
                            record.descriptor.size,
                            record.descriptor.sha256,
                            record.storage_ref,
                            _json_text(
                                record.descriptor.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                        )
                        for record in artifacts
                    ],
                )
                connection.execute("COMMIT")
            except sqlite3.IntegrityError as error:
                connection.execute("ROLLBACK")
                raise ReplayConflictError(
                    "Replay run identity already exists"
                ) from error
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return envelope

    def list_replays(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        agent_id: str | None = None,
    ) -> ReplayPage:
        """List Replay summaries with a stable newest-first cursor.

        Args:
            limit (int): Page size from 1 through 100.
            cursor (str | None): Opaque cursor from a previous page.
            agent_id (str | None): Optional exact safe Agent identity filter.

        Raises:
            ValueError: Limit or cursor is invalid.
            sqlite3.Error: Query fails.

        Returns:
            ReplayPage: Bounded page.
        """
        if not 1 <= limit <= 100:
            raise ValueError("Replay page limit must be between 1 and 100")
        if agent_id is not None and _STABLE_AGENT_ID.fullmatch(agent_id) is None:
            raise ValueError("Replay Agent filter is invalid")
        parameters: list[Any] = []
        conditions: list[str] = []
        if agent_id is not None:
            conditions.append("agent_id = ?")
            parameters.append(agent_id)
        if cursor is not None:
            imported_at, run_id = _decode_cursor(cursor)
            conditions.append(
                "(imported_at < ? OR "
                "(imported_at = ? AND run_id > ?))"
            )
            parameters.extend((imported_at, imported_at, run_id))
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        parameters.append(limit + 1)
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT run_id, agent_id, agent_status, benchmark_outcome,
                       provenance, integrity_state, evidence_completeness,
                       imported_at, envelope_json
                FROM studio_replays
                {where}
                ORDER BY imported_at DESC, run_id ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
        has_more = len(rows) > limit
        visible = rows[:limit]
        items = tuple(
            ReplayListItem(
                run_id=row["run_id"],
                agent_id=row["agent_id"],
                agent_status=row["agent_status"],
                benchmark_outcome=row["benchmark_outcome"],
                provenance=row["provenance"],
                evidence_origin=ReplayEvidenceEnvelope.model_validate(
                    json.loads(row["envelope_json"])
                ).evidence_origin,
                integrity_state=row["integrity_state"],
                evidence_completeness=row["evidence_completeness"],
                imported_at=row["imported_at"],
            )
            for row in visible
        )
        next_cursor = (
            _encode_cursor(visible[-1]["imported_at"], visible[-1]["run_id"])
            if has_more and visible
            else None
        )
        return ReplayPage(items=items, next_cursor=next_cursor)

    def get_replay(self, run_id: str) -> ReplayEvidenceEnvelope:
        """Load one immutable Replay envelope.

        Args:
            run_id (str): Stable run identity.

        Raises:
            ReplayNotFoundError: Run identity is absent.
            ValueError: Stored envelope violates the current schema.
            sqlite3.Error: Query fails.

        Returns:
            ReplayEvidenceEnvelope: Strict persisted evidence.
        """
        with self._connect() as connection:
            row = connection.execute(
                "SELECT envelope_json FROM studio_replays WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise ReplayNotFoundError("Replay was not found")
        return ReplayEvidenceEnvelope.model_validate(
            json.loads(row["envelope_json"])
        )

    def get_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> ReplayArtifactRecord:
        """Resolve one artifact only within its owning Replay.

        Args:
            run_id (str): Owning run identity.
            artifact_id (str): Opaque artifact identity.

        Raises:
            ReplayArtifactNotFoundError: Pair is absent.
            ValueError: Stored descriptor violates current schema.
            sqlite3.Error: Query fails.

        Returns:
            ReplayArtifactRecord: Public descriptor and internal store ref.
        """
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT descriptor_json, storage_ref
                FROM studio_replay_artifacts
                WHERE run_id = ? AND artifact_id = ?
                """,
                (run_id, artifact_id),
            ).fetchone()
        if row is None:
            raise ReplayArtifactNotFoundError("Replay artifact was not found")
        return ReplayArtifactRecord(
            descriptor=ReplayArtifactDescriptor.model_validate(
                json.loads(row["descriptor_json"])
            ),
            storage_ref=row["storage_ref"],
        )


class ReplayArtifactStore:
    """Run-scoped local store with atomic staging and opaque resolution."""

    def __init__(
        self,
        root: str | Path,
        repository: SQLiteReplayRepository,
    ) -> None:
        """Create a local artifact store.

        Args:
            root (str | Path): Explicit managed storage root.
            repository (SQLiteReplayRepository): Structured artifact index.

        Raises:
            OSError: Root cannot be created.

        Returns:
            None.
        """
        self.root = Path(root).expanduser().resolve()
        self.repository = repository
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".staging").mkdir(parents=True, exist_ok=True)

    def import_candidate(
        self,
        candidate: ReplayImportCandidate,
    ) -> ReplayEvidenceEnvelope:
        """Copy and verify candidate artifacts before committing metadata.

        Args:
            candidate (ReplayImportCandidate): Parsed explicit source.

        Raises:
            ReplayImportError: Source path, size, or hash is invalid.
            ReplayConflictError: Run identity already exists.
            OSError: File operations fail.

        Returns:
            ReplayEvidenceEnvelope: Persisted evidence.
        """
        run_id = candidate.envelope.run_id
        stage = self.root / ".staging" / f"{run_id}-{uuid.uuid4().hex}"
        final = self.root / "runs" / run_id
        if final.exists():
            try:
                self.repository.get_replay(run_id)
            except ReplayNotFoundError:
                shutil.rmtree(final)
            else:
                raise ReplayConflictError(
                    "Replay artifact namespace already exists"
                )
        stage_artifacts = stage / "artifacts"
        stage_artifacts.mkdir(parents=True, exist_ok=False)
        records: list[ReplayArtifactRecord] = []
        try:
            for artifact_id in sorted(candidate.artifacts):
                imported = candidate.artifacts[artifact_id]
                if imported.descriptor.artifact_id != artifact_id:
                    raise ReplayImportError(
                        "studio.replay.artifact_identity_invalid",
                        "Replay artifact input identity is inconsistent",
                    )
                target = stage_artifacts / artifact_id
                self._copy_import(imported, target)
                with target.open("rb") as stream:
                    actual_hash, actual_size = _hash_stream(stream)
                if (
                    actual_hash != imported.descriptor.sha256
                    or actual_size != imported.descriptor.size
                ):
                    raise ReplayImportError(
                        "studio.replay.artifact_integrity",
                        "Replay artifact failed size or hash verification",
                    )
                records.append(
                    ReplayArtifactRecord(
                        descriptor=imported.descriptor,
                        storage_ref=f"runs/{run_id}/artifacts/{artifact_id}",
                    )
                )
            final.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage, final)
            try:
                return self.repository.create_replay(
                    candidate.envelope,
                    tuple(records),
                )
            except Exception:
                shutil.rmtree(final, ignore_errors=True)
                raise
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            raise

    @staticmethod
    def _copy_import(imported: ReplayImportArtifact, target: Path) -> None:
        """Copy one direct file or ZIP member to staging.

        Args:
            imported (ReplayImportArtifact): Verified import source.
            target (Path): Staging destination.

        Raises:
            ReplayImportError: Source is unsafe.
            OSError: Source cannot be read or target cannot be written.

        Returns:
            None.
        """
        source = imported.source_path
        if imported.bundle_member is not None:
            pure = PurePosixPath(imported.bundle_member)
            if pure.is_absolute() or ".." in pure.parts:
                raise ReplayImportError(
                    "studio.replay.bundle_member_unsafe",
                    "Replay bundle member is unsafe",
                )
            with zipfile.ZipFile(source, "r") as archive:
                info = archive.getinfo(imported.bundle_member)
                if info.is_dir() or (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ReplayImportError(
                        "studio.replay.bundle_member_unsafe",
                        "Replay bundle member is not a regular file",
                    )
                with archive.open(info, "r") as input_stream, target.open(
                    "wb"
                ) as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)
            return
        if source.is_symlink() or not source.is_file():
            raise ReplayImportError(
                "studio.replay.artifact_source_unsafe",
                "Replay artifact source must be a regular non-symlink file",
            )
        if imported.trusted_root is not None:
            trusted = imported.trusted_root.resolve()
            resolved = source.resolve()
            if trusted != resolved and trusted not in resolved.parents:
                raise ReplayImportError(
                    "studio.replay.artifact_source_escape",
                    "Replay artifact source escapes its trusted root",
                )
        shutil.copyfile(source, target, follow_symlinks=False)

    def open_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> tuple[ReplayArtifactDescriptor, BinaryIO]:
        """Open one verified replay-scoped regular artifact.

        Args:
            run_id (str): Owning run identity.
            artifact_id (str): Opaque artifact identity.

        Raises:
            ReplayArtifactNotFoundError: Pair is absent.
            ReplayImportError: Stored path or content is unsafe/corrupt.
            OSError: Content cannot be opened.

        Returns:
            tuple[ReplayArtifactDescriptor, BinaryIO]: Descriptor and stream.
        """
        record = self.repository.get_artifact(run_id, artifact_id)
        if record.descriptor.hidden:
            raise ReplayArtifactNotFoundError("Replay artifact was not found")
        pure = PurePosixPath(record.storage_ref)
        if pure.is_absolute() or ".." in pure.parts:
            raise ReplayImportError(
                "studio.replay.storage_ref_unsafe",
                "Stored Replay artifact reference is unsafe",
            )
        path = self.root.joinpath(*pure.parts)
        resolved = path.resolve()
        if (
            path.is_symlink()
            or not path.is_file()
            or (self.root != resolved and self.root not in resolved.parents)
        ):
            raise ReplayImportError(
                "studio.replay.artifact_missing",
                "Replay artifact content is unavailable",
            )
        stream = resolved.open("rb")
        actual_hash, actual_size = _hash_stream(stream)
        if (
            actual_hash != record.descriptor.sha256
            or actual_size != record.descriptor.size
        ):
            stream.close()
            raise ReplayImportError(
                "studio.replay.artifact_corrupt",
                "Replay artifact failed integrity verification",
            )
        stream.seek(0)
        return record.descriptor, stream


class ReplayBundleStore:
    """Export and verify native Replay packages from managed storage."""

    def __init__(
        self,
        repository: SQLiteReplayRepository,
        artifacts: ReplayArtifactStore,
    ) -> None:
        """Bind structured and binary Replay stores.

        Args:
            repository (SQLiteReplayRepository): Replay metadata source.
            artifacts (ReplayArtifactStore): Verified content source.

        Raises:
            None.

        Returns:
            None.
        """
        self.repository = repository
        self.artifacts = artifacts

    def write_bundle(self, run_id: str, target: Path) -> Path:
        """Write one versioned, integrity-checked Replay ZIP.

        Args:
            run_id (str): Persisted Replay identity.
            target (Path): Explicit output ZIP path.

        Raises:
            ReplayNotFoundError: Run does not exist.
            ReplayImportError: An included artifact is corrupt.
            OSError: Bundle cannot be written.

        Returns:
            Path: Completed bundle path.
        """
        envelope = self.repository.get_replay(run_id)
        target = Path(target).expanduser()
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{target.name}.",
            suffix=".tmp",
            dir=target.parent,
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        members: dict[str, dict[str, str | int]] = {}
        exported_envelope = envelope.model_copy(
            update={
                "availability": {
                    **envelope.availability,
                    "prompt": ReplayEvidenceAvailability(
                        state="excluded",
                        reason_code="studio.replay.prompt_default_excluded",
                    ),
                },
                "artifacts": tuple(
                    item.model_copy(update={"availability": "excluded"})
                    if item.hidden
                    else item
                    for item in envelope.artifacts
                ),
            }
        )
        try:
            with zipfile.ZipFile(
                temporary,
                "w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                envelope_bytes = (
                    json.dumps(
                        exported_envelope.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        ),
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
                archive.writestr("envelope.json", envelope_bytes)
                members["envelope.json"] = {
                    "sha256": "sha256:"
                    + hashlib.sha256(envelope_bytes).hexdigest(),
                    "size": len(envelope_bytes),
                }
                for item in envelope.artifacts:
                    if item.hidden or item.availability not in {
                        "available",
                        "redacted",
                        "truncated",
                    }:
                        continue
                    _metadata, stream = self.artifacts.open_artifact(
                        run_id,
                        item.artifact_id,
                    )
                    member = f"artifacts/{item.artifact_id}"
                    try:
                        with archive.open(member, "w") as output_stream:
                            shutil.copyfileobj(stream, output_stream)
                    finally:
                        stream.close()
                    members[member] = {
                        "sha256": item.sha256 or "",
                        "size": item.size,
                    }
                manifest = {
                    "schemaVersion": REPLAY_PACKAGE_SCHEMA_VERSION,
                    "kind": "studio_replay_package",
                    "runId": run_id,
                    "promptIncluded": False,
                    "members": dict(sorted(members.items())),
                }
                archive.writestr(
                    "replay-manifest.json",
                    (
                        json.dumps(
                            manifest,
                            ensure_ascii=False,
                            indent=2,
                            sort_keys=True,
                        )
                        + "\n"
                    ).encode("utf-8"),
                )
            os.replace(temporary, target)
        finally:
            if temporary.exists():
                temporary.unlink()
        return target

    @staticmethod
    def verify_bundle(path: Path) -> bool:
        """Verify native Replay member declarations and hashes.

        Args:
            path (Path): Replay ZIP package.

        Raises:
            ReplayImportError: Manifest or member path is unsafe.
            OSError: Package cannot be read.

        Returns:
            bool: True only when all declared members match.
        """
        try:
            with zipfile.ZipFile(path, "r") as archive:
                names = archive.namelist()
                for name in names:
                    pure = PurePosixPath(name)
                    if pure.is_absolute() or ".." in pure.parts:
                        raise ReplayImportError(
                            "studio.replay.bundle_member_unsafe",
                            "Replay bundle contains an unsafe member",
                        )
                manifest = json.loads(archive.read("replay-manifest.json"))
                members = manifest.get("members")
                if not isinstance(members, dict):
                    return False
                if set(names) != set(members) | {"replay-manifest.json"}:
                    return False
                for name, expected in members.items():
                    if not isinstance(expected, dict):
                        return False
                    content = archive.read(name)
                    if (
                        "sha256:" + hashlib.sha256(content).hexdigest()
                        != expected.get("sha256")
                        or len(content) != expected.get("size")
                    ):
                        return False
                return True
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            return False


__all__ = [
    "ReplayArtifactStore",
    "ReplayBundleStore",
    "SQLiteReplayRepository",
    "default_studio_artifact_directory",
]
