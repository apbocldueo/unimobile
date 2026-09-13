"""SQLite coordination boundary for durable Benchmark publication."""

from __future__ import annotations

import base64
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Callable

from pydantic import ValidationError
from zhixing.benchmark.identity import canonical_hash

from .benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkIntegrityError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkStorageError,
    StudioBenchmarkValidationError,
)
from .benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventEnvelopeV1,
    StudioBenchmarkAvailability,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunLinksV1,
    benchmark_event_fingerprint,
)
from .benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from .benchmark_publication_models import (
    StudioBenchmarkArtifactAvailability,
    StudioBenchmarkArtifactDescriptorV1,
    StudioBenchmarkArtifactMetadataPageV1,
    StudioBenchmarkManagedArtifactRecordV1,
    StudioBenchmarkPublicationDiagnosticV1,
    StudioBenchmarkPublicationRecordV1,
)
from .database import connect_studio_database, migrate_studio_database
from .replay_contracts import ReplayArtifactRecord, replay_list_item
from .replay_models import (
    ReplayEvidenceEnvelope,
    ReplayIntegrityDiagnostic,
)


FailureHook = Callable[[str], None]
EventCommitHook = Callable[[str], None]
logger = logging.getLogger(__name__)


def _json_text(value: Any) -> str:
    """Encode one deterministic finite JSON document.

    Args:
        value: JSON-compatible value.

    Raises:
        TypeError: Value is not JSON compatible.
        ValueError: Value contains a non-finite number.

    Returns:
        Compact canonical JSON text.
    """
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


class SQLiteStudioBenchmarkPublicationRepository:
    """Atomically expose publication metadata, artifacts, Replay, and events."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        failure_hook: FailureHook | None = None,
        event_commit_hook: EventCommitHook | None = None,
    ) -> None:
        """Open a migrated shared Studio database.

        Args:
            database_path: Explicit workspace SQLite path.
            failure_hook: Optional deterministic rollback-test hook.
            event_commit_hook: Optional callback invoked after event commit.

        Raises:
            OSError: Database storage cannot be created.
            sqlite3.Error: Migration fails.

        Returns:
            None.
        """
        self._database_path = Path(database_path).expanduser()
        self._failure_hook = failure_hook
        self._event_commit_hook = event_commit_hook
        migrate_studio_database(self._database_path)

    def _connect(self) -> sqlite3.Connection:
        """Open one row-enabled short-lived SQLite connection.

        Returns:
            Configured SQLite connection.
        """
        return connect_studio_database(self._database_path)

    def _fail(self, step: str) -> None:
        """Invoke a configured deterministic transaction failure hook.

        Args:
            step: Stable transaction checkpoint.

        Returns:
            None.
        """
        if self._failure_hook is not None:
            self._failure_hook(step)

    @staticmethod
    def _publication_from_row(
        row: sqlite3.Row,
    ) -> StudioBenchmarkPublicationRecordV1:
        """Parse and cross-check one stored publication row.

        Args:
            row: Selected publication row.

        Raises:
            StudioBenchmarkIntegrityError: JSON or indexed fields disagree.

        Returns:
            Strict publication record.
        """
        try:
            record = StudioBenchmarkPublicationRecordV1.model_validate(
                json.loads(row["publication_json"])
            )
            expected = (
                row["experiment_id"],
                row["task_run_id"],
                row["publication_fingerprint"],
                row["preparation_fingerprint"],
                row["preparation_availability"],
                row["report_availability"],
                row["trajectory_availability"],
                row["bundle_availability"],
                row["replay_availability"],
                row["report_artifact_id"],
                row["bundle_artifact_id"],
                row["replay_id"],
                tuple(json.loads(row["artifact_ids_json"])),
                tuple(json.loads(row["diagnostics_json"])),
                row["journal_high_water_mark"],
                row["published_at"],
            )
            actual = (
                record.experiment_id,
                record.task_run_id,
                record.publication_fingerprint,
                record.preparation_fingerprint,
                record.preparation_availability,
                record.report_availability,
                record.trajectory_availability,
                record.bundle_availability,
                record.replay_availability,
                record.report_artifact_id,
                record.bundle_artifact_id,
                record.replay_id,
                record.artifact_ids,
                tuple(
                    item.model_dump(mode="json", by_alias=True)
                    for item in record.diagnostics
                ),
                record.journal_high_water_mark,
                record.published_at,
            )
            if actual != expected:
                raise ValueError("publication query columns disagree with JSON")
            return record
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.publication.storage_corrupt",
                "Stored Benchmark publication metadata is invalid",
            ) from error

    @staticmethod
    def _artifact_from_row(
        row: sqlite3.Row,
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Parse and cross-check one managed artifact row.

        Args:
            row: Selected managed artifact row.

        Raises:
            StudioBenchmarkIntegrityError: Stored metadata is inconsistent.

        Returns:
            Strict managed artifact record.
        """
        try:
            record = StudioBenchmarkManagedArtifactRecordV1(
                descriptor=json.loads(row["descriptor_json"]),
                storage_ref=row["storage_ref"],
            )
            descriptor = record.descriptor
            expected = (
                row["experiment_id"],
                row["artifact_id"],
                row["task_run_id"],
                row["kind"],
                row["availability"],
                row["content_type"],
                row["size"],
                row["sha256"],
                row["provenance"],
                row["causal_identity"],
                bool(row["hidden"]),
            )
            actual = (
                descriptor.experiment_id,
                descriptor.artifact_id,
                descriptor.task_run_id,
                descriptor.kind,
                descriptor.availability.value,
                descriptor.content_type,
                descriptor.size,
                descriptor.sha256,
                descriptor.provenance,
                descriptor.causal_identity,
                descriptor.hidden,
            )
            if actual != expected:
                raise ValueError("artifact query columns disagree with JSON")
            return record
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.storage_corrupt",
                "Stored Benchmark artifact metadata is invalid",
            ) from error

    def get_publication(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkPublicationRecordV1 | None:
        """Return a committed publication when one exists.

        Args:
            experiment_id: Owning Experiment identity.

        Raises:
            StudioBenchmarkStorageError: SQLite query fails.
            StudioBenchmarkIntegrityError: Stored facts are invalid.

        Returns:
            Publication record or ``None``.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM studio_benchmark_publications "
                    "WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.publication.storage_failed",
                "Benchmark publication lookup failed",
            ) from error
        return self._publication_from_row(row) if row is not None else None

    def get_artifact(
        self,
        experiment_id: str,
        artifact_id: str,
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Resolve one artifact only through its owning Experiment.

        Args:
            experiment_id: Owning Experiment identity.
            artifact_id: Opaque artifact identity.

        Raises:
            StudioBenchmarkNotFoundError: Scoped artifact is absent.
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Strict managed artifact record.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM studio_benchmark_artifacts "
                    "WHERE experiment_id = ? AND artifact_id = ?",
                    (experiment_id, artifact_id),
                ).fetchone()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.artifact.storage_failed",
                "Benchmark artifact lookup failed",
            ) from error
        if row is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.artifact.not_found",
                "Benchmark artifact was not found",
            )
        return self._artifact_from_row(row)

    def list_artifacts(
        self,
        experiment_id: str,
        *,
        task_run_id: str | None = None,
    ) -> tuple[StudioBenchmarkManagedArtifactRecordV1, ...]:
        """List stable artifact records for one validated scope.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Optional TaskRun scope.

        Raises:
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Stable managed artifact records.
        """
        try:
            with self._connect() as connection:
                if task_run_id is None:
                    rows = connection.execute(
                        "SELECT * FROM studio_benchmark_artifacts "
                        "WHERE experiment_id = ? ORDER BY artifact_id ASC",
                        (experiment_id,),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT * FROM studio_benchmark_artifacts "
                        "WHERE experiment_id = ? AND task_run_id = ? "
                        "ORDER BY artifact_id ASC",
                        (experiment_id, task_run_id),
                    ).fetchall()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.artifact.storage_failed",
                "Benchmark artifact listing failed",
            ) from error
        return tuple(self._artifact_from_row(row) for row in rows)

    @staticmethod
    def _encode_artifact_cursor(
        experiment_id: str,
        artifact_id: str,
    ) -> str:
        """Encode one checksummed Experiment-bound artifact cursor.

        Args:
            experiment_id: Owning Experiment identity.
            artifact_id: Last returned visible artifact identity.

        Returns:
            URL-safe opaque continuation cursor.
        """
        body = {
            "v": 1,
            "experimentId": experiment_id,
            "artifactId": artifact_id,
        }
        body["check"] = canonical_hash(body)
        return base64.urlsafe_b64encode(
            _json_text(body).encode("utf-8")
        ).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_artifact_cursor(
        cursor: str | None,
        experiment_id: str,
    ) -> str | None:
        """Decode one checksummed cursor bound to its Experiment.

        Args:
            cursor: Optional opaque continuation cursor.
            experiment_id: Expected owning Experiment identity.

        Raises:
            StudioBenchmarkValidationError: Cursor is malformed or mismatched.

        Returns:
            Last visible artifact identity or ``None``.
        """
        if cursor is None:
            return None
        try:
            if not cursor or len(cursor) > 2048:
                raise ValueError("cursor length")
            padding = "=" * (-len(cursor) % 4)
            value = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            )
            if not isinstance(value, dict) or set(value) != {
                "v",
                "experimentId",
                "artifactId",
                "check",
            }:
                raise ValueError("cursor shape")
            check = value.pop("check")
            artifact_id = value.get("artifactId")
            if (
                value.get("v") != 1
                or value.get("experimentId") != experiment_id
                or not isinstance(artifact_id, str)
                or not artifact_id.startswith("artifact-")
                or len(artifact_id) != 41
                or any(
                    character not in "0123456789abcdef"
                    for character in artifact_id.removeprefix("artifact-")
                )
                or check != canonical_hash(value)
            ):
                raise ValueError("cursor contract")
            return artifact_id
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.artifact.cursor_invalid",
                "Benchmark artifact cursor is invalid",
            ) from error

    @staticmethod
    def _descriptor_from_metadata_row(
        row: sqlite3.Row,
    ) -> StudioBenchmarkArtifactDescriptorV1:
        """Parse descriptor-only query output without a storage reference.

        Args:
            row: Row containing only artifact identity and descriptor JSON.

        Raises:
            StudioBenchmarkIntegrityError: Stored descriptor is invalid.

        Returns:
            Strict public managed artifact descriptor.
        """
        try:
            descriptor = StudioBenchmarkArtifactDescriptorV1.model_validate(
                json.loads(row["descriptor_json"])
            )
            if descriptor.artifact_id != row["artifact_id"]:
                raise ValueError("artifact identity column mismatch")
            return descriptor
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.storage_corrupt",
                "Stored Benchmark artifact metadata is invalid",
            ) from error

    def list_artifact_metadata(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkArtifactMetadataPageV1:
        """List visible committed artifact descriptors without reading bodies.

        Args:
            experiment_id: Owning Experiment identity.
            limit: Requested visible page size within 1..100.
            cursor: Optional opaque cursor bound to the Experiment.

        Raises:
            StudioBenchmarkValidationError: Limit or cursor is invalid.
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkStorageError: Metadata query fails.
            StudioBenchmarkIntegrityError: Stored descriptors are invalid.

        Returns:
            Stable descriptor-only page and aggregate hidden count.
        """
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.artifact.limit_invalid",
                "Benchmark artifact page limit must be within 1 and 100",
            )
        after = self._decode_artifact_cursor(cursor, experiment_id)
        try:
            with self._connect() as connection:
                exists = connection.execute(
                    "SELECT 1 FROM studio_benchmark_experiments "
                    "WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
                if exists is None:
                    raise StudioBenchmarkNotFoundError(
                        "benchmark.experiment.not_found",
                        "Benchmark Experiment was not found",
                    )
                hidden_count = int(
                    connection.execute(
                        "SELECT COUNT(*) AS count "
                        "FROM studio_benchmark_artifacts "
                        "WHERE experiment_id = ? AND hidden = 1",
                        (experiment_id,),
                    ).fetchone()["count"]
                )
                if after is None:
                    rows = connection.execute(
                        "SELECT artifact_id, descriptor_json "
                        "FROM studio_benchmark_artifacts "
                        "WHERE experiment_id = ? AND hidden = 0 "
                        "ORDER BY artifact_id ASC LIMIT ?",
                        (experiment_id, limit + 1),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT artifact_id, descriptor_json "
                        "FROM studio_benchmark_artifacts "
                        "WHERE experiment_id = ? AND hidden = 0 "
                        "AND artifact_id > ? "
                        "ORDER BY artifact_id ASC LIMIT ?",
                        (experiment_id, after, limit + 1),
                    ).fetchall()
        except StudioBenchmarkNotFoundError:
            raise
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.artifact.storage_failed",
                "Benchmark artifact metadata query failed",
            ) from error
        selected = tuple(
            self._descriptor_from_metadata_row(row) for row in rows[:limit]
        )
        next_cursor = None
        if len(rows) > limit and selected:
            next_cursor = self._encode_artifact_cursor(
                experiment_id,
                selected[-1].artifact_id,
            )
        return StudioBenchmarkArtifactMetadataPageV1(
            experiment_id=experiment_id,
            items=selected,
            hidden_count=hidden_count,
            next_cursor=next_cursor,
        )

    def update_artifact_availability(
        self,
        experiment_id: str,
        artifact_id: str,
        availability: StudioBenchmarkArtifactAvailability,
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Close one readable artifact as missing or corrupt.

        Args:
            experiment_id: Owning Experiment identity.
            artifact_id: Opaque artifact identity.
            availability: Closed integrity availability.

        Raises:
            ValueError: Availability is not a safe integrity closure.
            StudioBenchmarkNotFoundError: Scoped artifact is absent.
            StudioBenchmarkStorageError: Update fails.

        Returns:
            Updated managed record.
        """
        if availability not in {
            StudioBenchmarkArtifactAvailability.MISSING,
            StudioBenchmarkArtifactAvailability.CORRUPT,
        }:
            raise ValueError("artifact integrity closure must be missing or corrupt")
        record = self.get_artifact(experiment_id, artifact_id)
        changed_descriptor = record.descriptor.model_copy(
            update={
                "availability": availability,
                "content_type": "",
                "sha256": None,
            }
        )
        changed = StudioBenchmarkManagedArtifactRecordV1(
            descriptor=changed_descriptor,
            storage_ref=record.storage_ref,
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE studio_benchmark_artifacts "
                    "SET availability = ?, content_type = '', sha256 = NULL, "
                    "descriptor_json = ? "
                    "WHERE experiment_id = ? AND artifact_id = ?",
                    (
                        availability.value,
                        _json_text(
                            changed_descriptor.model_dump(
                                mode="json",
                                by_alias=True,
                                exclude_none=True,
                            )
                        ),
                        experiment_id,
                        artifact_id,
                    ),
                )
                if connection.execute(
                    "SELECT changes() AS count"
                ).fetchone()["count"] != 1:
                    connection.execute("ROLLBACK")
                    raise StudioBenchmarkNotFoundError(
                        "benchmark.artifact.not_found",
                        "Benchmark artifact was not found",
                    )
                publication_row = connection.execute(
                    "SELECT * FROM studio_benchmark_publications "
                    "WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
                if publication_row is not None:
                    publication = self._publication_from_row(publication_row)
                    component_updates: dict[str, object] = {}
                    if publication.report_artifact_id == artifact_id:
                        component_updates.update(
                            report_availability="failed",
                            report_artifact_id=None,
                        )
                    if publication.bundle_artifact_id == artifact_id:
                        component_updates.update(
                            bundle_availability="failed",
                            bundle_artifact_id=None,
                        )
                    if record.descriptor.kind == "task_trajectory":
                        component_updates["trajectory_availability"] = "failed"
                    diagnostic = StudioBenchmarkPublicationDiagnosticV1(
                        code=f"benchmark.artifact.{availability.value}",
                        message=(
                            "A managed Benchmark artifact failed "
                            "read-time integrity verification"
                        ),
                        component=record.descriptor.kind,
                        retryable=False,
                    )
                    if diagnostic not in publication.diagnostics:
                        component_updates["diagnostics"] = (
                            publication.diagnostics + (diagnostic,)
                        )
                    changed_publication = publication.model_copy(
                        update=component_updates,
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_publications
                        SET report_availability = ?,
                            trajectory_availability = ?,
                            bundle_availability = ?,
                            report_artifact_id = ?,
                            bundle_artifact_id = ?,
                            diagnostics_json = ?,
                            publication_json = ?
                        WHERE experiment_id = ?
                        """,
                        (
                            changed_publication.report_availability,
                            changed_publication.trajectory_availability,
                            changed_publication.bundle_availability,
                            changed_publication.report_artifact_id,
                            changed_publication.bundle_artifact_id,
                            _json_text(
                                [
                                    item.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                    for item in changed_publication.diagnostics
                                ]
                            ),
                            _json_text(
                                changed_publication.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                            experiment_id,
                        ),
                    )
                    task_row = connection.execute(
                        "SELECT * FROM studio_benchmark_task_runs "
                        "WHERE experiment_id = ? AND task_run_id = ?",
                        (experiment_id, publication.task_run_id),
                    ).fetchone()
                    artifact_rows = connection.execute(
                        "SELECT * FROM studio_benchmark_artifacts "
                        "WHERE experiment_id = ? ORDER BY artifact_id ASC",
                        (experiment_id,),
                    ).fetchall()
                    if task_row is not None:
                        task_artifacts = tuple(
                            self._artifact_from_row(row).descriptor
                            for row in artifact_rows
                            if row["task_run_id"] == publication.task_run_id
                        )
                        task = (
                            SQLiteStudioBenchmarkExperimentRepository
                            ._task_run_from_row(
                                task_row,
                                artifacts=task_artifacts,
                            )
                        )
                        changed_task = task.model_copy(
                            update={
                                "report_availability": (
                                    StudioBenchmarkAvailability(
                                        changed_publication.report_availability
                                    )
                                ),
                                "trajectory_availability": (
                                    StudioBenchmarkAvailability(
                                        changed_publication
                                        .trajectory_availability
                                    )
                                ),
                                "bundle_availability": (
                                    StudioBenchmarkAvailability(
                                        changed_publication.bundle_availability
                                    )
                                ),
                                "publication_diagnostics": (
                                    changed_publication.diagnostics
                                ),
                            }
                        )
                        connection.execute(
                            """
                            UPDATE studio_benchmark_task_runs
                            SET report_availability = ?,
                                trajectory_availability = ?,
                                bundle_availability = ?,
                                publication_diagnostics_json = ?,
                                task_run_json = ?
                            WHERE experiment_id = ? AND task_run_id = ?
                            """,
                            (
                                changed_publication.report_availability,
                                changed_publication.trajectory_availability,
                                changed_publication.bundle_availability,
                                _json_text(
                                    [
                                        item.model_dump(
                                            mode="json",
                                            by_alias=True,
                                            exclude_none=True,
                                        )
                                        for item in (
                                            changed_publication.diagnostics
                                        )
                                    ]
                                ),
                                _json_text(
                                    changed_task.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                ),
                                experiment_id,
                                publication.task_run_id,
                            ),
                        )
                    connection.execute(
                        "UPDATE studio_benchmark_experiments "
                        "SET report_availability = ? WHERE experiment_id = ?",
                        (
                            (
                                "available"
                                if changed_publication.report_availability
                                == "available"
                                else "not_produced"
                            ),
                            experiment_id,
                        ),
                    )
                    if publication.replay_id is not None:
                        replay_row = connection.execute(
                            "SELECT envelope_json FROM studio_replays "
                            "WHERE run_id = ?",
                            (publication.replay_id,),
                        ).fetchone()
                        if replay_row is not None:
                            replay = ReplayEvidenceEnvelope.model_validate(
                                json.loads(replay_row["envelope_json"])
                            )
                            replay_artifacts = tuple(
                                item.model_copy(
                                    update={
                                        "availability": availability.value,
                                        "content_type": "",
                                        "sha256": None,
                                    }
                                )
                                if item.artifact_id == artifact_id
                                else item
                                for item in replay.artifacts
                            )
                            integrity = ReplayIntegrityDiagnostic(
                                code=f"benchmark.artifact.{availability.value}",
                                message=(
                                    "A managed Benchmark artifact failed "
                                    "read-time integrity verification"
                                ),
                                severity="error",
                                source="benchmark_publication",
                            )
                            changed_replay = replay.model_copy(
                                update={
                                    "artifacts": replay_artifacts,
                                    "integrity_state": "partial",
                                    "integrity": replay.integrity + (integrity,),
                                }
                            )
                            replay_item = replay_list_item(changed_replay)
                            connection.execute(
                                """
                                UPDATE studio_replays
                                SET integrity_state = ?,
                                    evidence_completeness = ?,
                                    envelope_json = ?
                                WHERE run_id = ?
                                """,
                                (
                                    replay_item.integrity_state,
                                    replay_item.evidence_completeness,
                                    _json_text(
                                        changed_replay.model_dump(
                                            mode="json",
                                            by_alias=True,
                                            exclude_none=True,
                                        )
                                    ),
                                    publication.replay_id,
                                ),
                            )
                            connection.execute(
                                """
                                UPDATE studio_replay_artifacts
                                SET availability = ?, content_type = '',
                                    sha256 = NULL, descriptor_json = ?
                                WHERE run_id = ? AND artifact_id = ?
                                """,
                                (
                                    availability.value,
                                    _json_text(
                                        next(
                                            item
                                            for item in replay_artifacts
                                            if item.artifact_id == artifact_id
                                        ).model_dump(
                                            mode="json",
                                            by_alias=True,
                                            exclude_none=True,
                                        )
                                    ),
                                    publication.replay_id,
                                    artifact_id,
                                ),
                            )
                connection.execute("COMMIT")
        except StudioBenchmarkNotFoundError:
            raise
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.artifact.storage_failed",
                "Benchmark artifact integrity state could not be closed",
            ) from error
        return changed

    @staticmethod
    def _validate_commit_inputs(
        publication: StudioBenchmarkPublicationRecordV1,
        artifacts: tuple[StudioBenchmarkManagedArtifactRecordV1, ...],
        replay: ReplayEvidenceEnvelope | None,
        replay_artifacts: tuple[ReplayArtifactRecord, ...],
    ) -> None:
        """Validate cross-resource publication identities before storage.

        Args:
            publication: Immutable publication record.
            artifacts: Managed artifact metadata to expose.
            replay: Optional native Benchmark Replay envelope.
            replay_artifacts: Readable Replay artifact records.

        Raises:
            ValueError: Identities, terminal states, or inventories disagree.

        Returns:
            None.
        """
        component_states = {
            publication.preparation_availability,
            publication.report_availability,
            publication.trajectory_availability,
            publication.bundle_availability,
            publication.replay_availability,
        }
        if "pending" in component_states:
            raise ValueError("committed publication cannot remain pending")
        artifact_ids = tuple(
            sorted(record.descriptor.artifact_id for record in artifacts)
        )
        if tuple(sorted(publication.artifact_ids)) != artifact_ids:
            raise ValueError("publication artifact inventory is inconsistent")
        for record in artifacts:
            descriptor = record.descriptor
            if descriptor.experiment_id != publication.experiment_id:
                raise ValueError("artifact Experiment scope is inconsistent")
            if descriptor.task_run_id not in {
                None,
                publication.task_run_id,
            }:
                raise ValueError("artifact TaskRun scope is inconsistent")
        if publication.replay_availability == "available":
            if replay is None or replay.run_id != publication.replay_id:
                raise ValueError("available Replay requires its explicit envelope")
            if replay.provenance != "native_benchmark_task_run":
                raise ValueError("native Benchmark Replay provenance is required")
        elif replay is not None or replay_artifacts:
            raise ValueError("unavailable Replay cannot expose Replay records")
        if replay is not None:
            expected = {
                item.artifact_id: item
                for item in replay.artifacts
                if item.availability
                in {"available", "redacted", "truncated"}
            }
            actual = {
                item.descriptor.artifact_id: item.descriptor
                for item in replay_artifacts
            }
            if expected != actual:
                raise ValueError(
                    "Replay artifact records do not match its envelope"
                )

    @staticmethod
    def _insert_replay(
        connection: sqlite3.Connection,
        replay: ReplayEvidenceEnvelope,
        artifacts: tuple[ReplayArtifactRecord, ...],
    ) -> None:
        """Insert native Replay rows inside the publication transaction.

        Args:
            connection: Active coordinated transaction.
            replay: Validated native Benchmark Replay.
            artifacts: Matching readable managed content records.

        Raises:
            sqlite3.Error: Any Replay row insert fails.

        Returns:
            None.
        """
        item = replay_list_item(replay)
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
                    replay.model_dump(
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
                    replay.run_id,
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
                for moment in replay.moments
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
                    replay.run_id,
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

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        experiment_id: str,
        sequence: int,
        draft: StudioBenchmarkEventDraftV1,
    ) -> None:
        """Append one event inside the coordinated transaction.

        Args:
            connection: Active coordinated transaction.
            experiment_id: Owning Experiment identity.
            sequence: Strict next sequence.
            draft: Validated event draft.

        Raises:
            sqlite3.Error: Journal insert fails.

        Returns:
            None.
        """
        envelope = StudioBenchmarkEventEnvelopeV1(
            **draft.model_dump(),
            experiment_id=experiment_id,
            sequence=sequence,
            fingerprint=benchmark_event_fingerprint(draft),
        )
        connection.execute(
            """
            INSERT INTO studio_benchmark_experiment_events(
                experiment_id, sequence, event_id, fingerprint,
                envelope_json, created_at, source, source_sequence, phase
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                experiment_id,
                sequence,
                draft.event_id,
                envelope.fingerprint,
                _json_text(
                    envelope.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                    )
                ),
                draft.timestamp,
                draft.source.value,
                draft.source_sequence,
                draft.phase,
            ),
        )

    def commit_publication(
        self,
        *,
        publication: StudioBenchmarkPublicationRecordV1,
        artifacts: tuple[StudioBenchmarkManagedArtifactRecordV1, ...],
        replay: ReplayEvidenceEnvelope | None,
        replay_artifacts: tuple[ReplayArtifactRecord, ...],
        events: tuple[StudioBenchmarkEventDraftV1, ...],
    ) -> StudioBenchmarkPublicationRecordV1:
        """Atomically expose artifacts, Replay, mappings, and journal facts.

        Args:
            publication: Final non-pending publication projection.
            artifacts: Managed artifact records prepared before metadata commit.
            replay: Optional native Benchmark Replay envelope.
            replay_artifacts: Replay-readable views over the same managed bytes.
            events: Bounded publication journal facts.

        Raises:
            ValueError: Cross-resource inputs are inconsistent.
            StudioBenchmarkConflictError: Identity or immutable input conflicts.
            StudioBenchmarkNotFoundError: Experiment or TaskRun is absent.
            StudioBenchmarkStorageError: Coordinated transaction fails.

        Returns:
            Newly committed or identical previously committed publication.
        """
        self._validate_commit_inputs(
            publication,
            artifacts,
            replay,
            replay_artifacts,
        )
        committed_events = False
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT * FROM studio_benchmark_publications "
                        "WHERE experiment_id = ?",
                        (publication.experiment_id,),
                    ).fetchone()
                    if existing is not None:
                        restored = self._publication_from_row(existing)
                        if (
                            restored.publication_fingerprint
                            != publication.publication_fingerprint
                        ):
                            raise StudioBenchmarkConflictError(
                                "benchmark.publication.identity_conflict",
                                "Benchmark publication identity has different inputs",
                            )
                        connection.execute("COMMIT")
                        return restored
                    experiment_row = connection.execute(
                        "SELECT lifecycle_state, event_high_water_mark "
                        "FROM studio_benchmark_experiments "
                        "WHERE experiment_id = ?",
                        (publication.experiment_id,),
                    ).fetchone()
                    task_row = connection.execute(
                        "SELECT * FROM studio_benchmark_task_runs "
                        "WHERE experiment_id = ? AND task_run_id = ?",
                        (
                            publication.experiment_id,
                            publication.task_run_id,
                        ),
                    ).fetchone()
                    if experiment_row is None or task_row is None:
                        raise StudioBenchmarkNotFoundError(
                            "benchmark.publication.scope_not_found",
                            "Benchmark publication scope was not found",
                        )
                    if experiment_row["lifecycle_state"] not in {
                        StudioBenchmarkExperimentLifecycle.FINALIZING.value,
                        StudioBenchmarkExperimentLifecycle.TERMINAL.value,
                    }:
                        raise StudioBenchmarkConflictError(
                            "benchmark.publication.lifecycle_conflict",
                            "Benchmark publication requires finalizing work",
                        )
                    if (
                        task_row["lifecycle_state"]
                        != StudioBenchmarkTaskRunLifecycle.TERMINAL.value
                        or task_row["result_availability"] != "available"
                        or task_row["result_fingerprint"] is None
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.publication.result_unavailable",
                            "Benchmark publication requires a terminal TaskResult",
                        )
                    if (
                        experiment_row["event_high_water_mark"]
                        != publication.journal_high_water_mark
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.publication.journal_conflict",
                            "Benchmark publication journal prefix changed",
                        )
                    for record in artifacts:
                        descriptor = record.descriptor
                        connection.execute(
                            """
                            INSERT INTO studio_benchmark_artifacts(
                                experiment_id, artifact_id, task_run_id, kind,
                                availability, content_type, size, sha256,
                                provenance, causal_identity, hidden, storage_ref,
                                descriptor_json, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                descriptor.experiment_id,
                                descriptor.artifact_id,
                                descriptor.task_run_id,
                                descriptor.kind,
                                descriptor.availability.value,
                                descriptor.content_type,
                                descriptor.size,
                                descriptor.sha256,
                                descriptor.provenance,
                                descriptor.causal_identity,
                                int(descriptor.hidden),
                                record.storage_ref,
                                _json_text(
                                    descriptor.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                ),
                                publication.published_at,
                            ),
                        )
                    self._fail("publication.after_artifacts")
                    if replay is not None:
                        conflicting_replay = connection.execute(
                            "SELECT provenance FROM studio_replays "
                            "WHERE run_id = ?",
                            (replay.run_id,),
                        ).fetchone()
                        if conflicting_replay is not None:
                            raise StudioBenchmarkConflictError(
                                "benchmark.publication.replay_identity_conflict",
                                (
                                    "Native Benchmark Replay identity "
                                    "conflicts with durable Replay facts"
                                ),
                            )
                        self._insert_replay(
                            connection,
                            replay,
                            replay_artifacts,
                        )
                    self._fail("publication.after_replay")
                    sequence = publication.journal_high_water_mark
                    for draft in events:
                        sequence += 1
                        self._append_event(
                            connection,
                            publication.experiment_id,
                            sequence,
                            draft,
                        )
                    task = (
                        SQLiteStudioBenchmarkExperimentRepository
                        ._task_run_from_row(
                            task_row,
                            artifacts=tuple(
                                record.descriptor
                                for record in artifacts
                                if record.descriptor.task_run_id
                                == publication.task_run_id
                            ),
                        )
                    )
                    base = (
                        f"/studio/benchmark-experiments/"
                        f"{publication.experiment_id}/task-runs/"
                        f"{publication.task_run_id}"
                    )
                    changed_task = task.model_copy(
                        update={
                            "report_availability": (
                                StudioBenchmarkAvailability(
                                    publication.report_availability
                                )
                            ),
                            "trajectory_availability": (
                                StudioBenchmarkAvailability(
                                    publication.trajectory_availability
                                )
                            ),
                            "bundle_availability": (
                                StudioBenchmarkAvailability(
                                    publication.bundle_availability
                                )
                            ),
                            "replay_availability": (
                                StudioBenchmarkAvailability(
                                    publication.replay_availability
                                )
                            ),
                            "replay_id": publication.replay_id,
                            "publication_diagnostics": (
                                publication.diagnostics
                            ),
                            "links": StudioBenchmarkTaskRunLinksV1(
                                self_link=base,
                                artifacts=(
                                    f"{base}/artifacts"
                                    if artifacts
                                    else None
                                ),
                                replay=(
                                    f"/studio/replays/{publication.replay_id}"
                                    if publication.replay_id is not None
                                    else None
                                ),
                            ),
                        }
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_task_runs
                        SET report_availability = ?,
                            trajectory_availability = ?,
                            bundle_availability = ?,
                            replay_availability = ?, replay_id = ?,
                            publication_diagnostics_json = ?,
                            task_run_json = ?
                        WHERE experiment_id = ? AND task_run_id = ?
                        """,
                        (
                            publication.report_availability,
                            publication.trajectory_availability,
                            publication.bundle_availability,
                            publication.replay_availability,
                            publication.replay_id,
                            _json_text(
                                [
                                    item.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                    for item in publication.diagnostics
                                ]
                            ),
                            _json_text(
                                changed_task.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                            publication.experiment_id,
                            publication.task_run_id,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET report_availability = ?,
                            replay_availability = ?,
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ?
                        """,
                        (
                            (
                                "available"
                                if publication.report_availability
                                == "available"
                                else "not_produced"
                            ),
                            (
                                "available"
                                if publication.replay_availability
                                == "available"
                                else "not_produced"
                            ),
                            sequence,
                            publication.published_at,
                            publication.experiment_id,
                        ),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_publications(
                            experiment_id, task_run_id,
                            publication_fingerprint,
                            preparation_fingerprint,
                            preparation_availability, report_availability,
                            trajectory_availability, bundle_availability,
                            replay_availability, report_artifact_id,
                            bundle_artifact_id, replay_id, artifact_ids_json,
                            diagnostics_json, journal_high_water_mark,
                            published_at, publication_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            publication.experiment_id,
                            publication.task_run_id,
                            publication.publication_fingerprint,
                            publication.preparation_fingerprint,
                            publication.preparation_availability,
                            publication.report_availability,
                            publication.trajectory_availability,
                            publication.bundle_availability,
                            publication.replay_availability,
                            publication.report_artifact_id,
                            publication.bundle_artifact_id,
                            publication.replay_id,
                            _json_text(list(publication.artifact_ids)),
                            _json_text(
                                [
                                    item.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                    for item in publication.diagnostics
                                ]
                            ),
                            publication.journal_high_water_mark,
                            publication.published_at,
                            _json_text(
                                publication.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                        ),
                    )
                    self._fail("publication.after_metadata")
                    connection.execute("COMMIT")
                    committed_events = bool(events)
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
            ValueError,
        ):
            raise
        except sqlite3.IntegrityError as error:
            raise StudioBenchmarkConflictError(
                "benchmark.publication.identity_conflict",
                "Benchmark publication identity conflicts with durable facts",
            ) from error
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.publication.storage_failed",
                "Benchmark publication transaction failed",
            ) from error
        if committed_events and self._event_commit_hook is not None:
            try:
                self._event_commit_hook(publication.experiment_id)
            except Exception:
                logger.warning(
                    "benchmark_publication_notification_failed "
                    "experiment_id=%s",
                    publication.experiment_id,
                )
        return publication


__all__ = ["SQLiteStudioBenchmarkPublicationRepository"]
