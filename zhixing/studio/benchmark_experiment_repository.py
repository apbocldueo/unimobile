"""SQLite adapter for atomic Stage 5.2A Benchmark Experiment aggregates."""

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
    ExperimentDefinitionSnapshotV1,
    StudioBenchmarkAvailability,
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventEnvelopeV1,
    StudioBenchmarkEventPageV1,
    StudioBenchmarkEventSource,
    StudioBenchmarkExperimentCancellationV1,
    StudioBenchmarkExperimentCreateRequestV1,
    StudioBenchmarkExperimentHistoryFilterV1,
    StudioBenchmarkExperimentRecordPageV1,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentRecordV1,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkRecoveryAttemptV1,
    StudioBenchmarkRecoveryCandidatePageV1,
    StudioBenchmarkRecoveryCandidateV1,
    StudioBenchmarkRecoveryDecision,
    StudioBenchmarkRecoveryTaskRunV1,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkTaskRunPageV1,
    StudioBenchmarkTaskRunRecordV1,
    StudioBenchmarkTaskResultV1,
    StudioBenchmarkTaskRunTerminalReason,
    benchmark_event_fingerprint,
    canonical_snapshot_json,
)
from .benchmark_experiment_protocols import (
    StudioBenchmarkExperimentAggregate,
    StudioBenchmarkExperimentBindingAuthority,
    StudioBenchmarkExperimentCreateResult,
)
from .benchmark_publication_models import (
    StudioBenchmarkArtifactDescriptorV1,
    StudioBenchmarkPublicationDiagnosticV1,
)
from .database import connect_studio_database, migrate_studio_database


FailureHook = Callable[[str], None]
EventCommitHook = Callable[[str], None]
logger = logging.getLogger(__name__)

_RECOVERY_EVENT_KINDS = {
    StudioBenchmarkRecoveryDecision.REQUEUE: "recovery.requeued",
    StudioBenchmarkRecoveryDecision.INTERRUPT: "recovery.interrupted",
    StudioBenchmarkRecoveryDecision.PUBLICATION_ONLY: (
        "recovery.publication_only"
    ),
    StudioBenchmarkRecoveryDecision.FINALIZE_ONLY: "recovery.finalize_only",
}


def _json_text(value: Any) -> str:
    """Encode deterministic finite JSON for durable SQLite records.

    Args:
        value: JSON-compatible value.

    Raises:
        TypeError: Value is not JSON-compatible.
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


def _stable_event_id(seed: dict[str, Any]) -> str:
    """Derive one stable opaque event identity from aggregate facts.

    Args:
        seed: Safe finite event identity material.

    Raises:
        TypeError: Seed is not JSON-compatible.
        ValueError: Seed is non-finite.

    Returns:
        Opaque Benchmark event identity.
    """
    from zhixing.benchmark.identity import canonical_hash

    suffix = canonical_hash(seed).removeprefix("sha256:")[:32]
    return f"benchmark-event-{suffix}"


def _recovery_token(
    record: StudioBenchmarkExperimentRecordV1,
) -> str:
    """Derive a non-reversible CAS token for one stale aggregate state.

    Args:
        record: Current durable Experiment record.

    Returns:
        Canonical SHA-256 recovery token without the raw process owner.
    """
    return canonical_hash(
        {
            "experimentId": record.experiment_id,
            "previousLifecycle": record.lifecycle.value,
            "previousOwner": record.process_owner_id,
            "eventHighWaterMark": record.event_high_water_mark,
            "updatedAt": record.updated_at,
        }
    )


def _recovery_attempt(
    candidate: StudioBenchmarkRecoveryCandidateV1,
    decision: StudioBenchmarkRecoveryDecision,
) -> StudioBenchmarkRecoveryAttemptV1:
    """Build the stable safe attempt recorded by a recovery transaction.

    Args:
        candidate: Previously queried stale aggregate projection.
        decision: Conservative lifecycle decision.

    Returns:
        Strict bounded recovery attempt.
    """
    affected = tuple(
        item.task_run_id
        for item in candidate.task_runs
        if item.lifecycle is not StudioBenchmarkTaskRunLifecycle.TERMINAL
    )
    attempt_id = canonical_hash(
        {
            "recoveryToken": candidate.recovery_token,
            "decision": decision.value,
            "taskRuns": affected,
        }
    )
    return StudioBenchmarkRecoveryAttemptV1(
        attempt_id=attempt_id,
        experiment_id=candidate.experiment_id,
        previous_lifecycle=candidate.previous_lifecycle,
        decision=decision,
        affected_task_run_ids=affected,
        prior_event_high_water_mark=(
            candidate.prior_event_high_water_mark
        ),
    )


def _recovery_event(
    attempt: StudioBenchmarkRecoveryAttemptV1,
    *,
    timestamp: int,
) -> StudioBenchmarkEventDraftV1:
    """Project one recovery attempt into a bounded sanitized journal fact.

    Args:
        attempt: Strict recovery decision.
        timestamp: Unix epoch milliseconds for the decision.

    Returns:
        Versioned durable event draft.
    """
    kind = _RECOVERY_EVENT_KINDS[attempt.decision]
    return StudioBenchmarkEventDraftV1(
        event_id=_stable_event_id(
            {
                "kind": kind,
                "experiment": attempt.experiment_id,
                "attempt": attempt.attempt_id,
            }
        ),
        timestamp=timestamp,
        source=StudioBenchmarkEventSource.SERVICE,
        kind=kind,
        phase="recovery",
        payload={
            "schemaVersion": 1,
            "attemptId": attempt.attempt_id,
            "previousLifecycle": attempt.previous_lifecycle.value,
            "decision": attempt.decision.value,
            "affectedTaskRunIds": list(
                attempt.affected_task_run_ids
            ),
            "priorEventHighWaterMark": (
                attempt.prior_event_high_water_mark
            ),
        },
    )


class SQLiteStudioBenchmarkExperimentRepository:
    """Atomic SQLite repository for Experiment, TaskRun, and journal facts."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        failure_hook: FailureHook | None = None,
        event_commit_hook: EventCommitHook | None = None,
    ) -> None:
        """Open a migrated Studio database.

        Args:
            database_path: Explicit workspace SQLite path.
            failure_hook: Optional test-only hook called at transaction steps.
            event_commit_hook: Optional payload-free callback invoked only
                after a transaction commits one or more new journal events.

        Raises:
            OSError: Parent storage cannot be created.
            sqlite3.Error: Shared migration fails.

        Returns:
            None.
        """
        self._database_path = Path(database_path).expanduser()
        self._failure_hook = failure_hook
        self._event_commit_hook = event_commit_hook
        migrate_studio_database(self._database_path)

    @property
    def database_path(self) -> Path:
        """Return the private adapter path for operator diagnostics.

        Returns:
            Configured SQLite path, never serialized into public resources.
        """
        return self._database_path

    def _connect(self) -> sqlite3.Connection:
        """Open one configured short-lived connection.

        Raises:
            sqlite3.Error: Connection setup fails.

        Returns:
            Row-enabled SQLite connection.
        """
        return connect_studio_database(self._database_path)

    def _fail(self, step: str) -> None:
        """Invoke the optional deterministic transaction failure hook.

        Args:
            step: Stable transaction checkpoint identity.

        Returns:
            None.
        """
        if self._failure_hook is not None:
            self._failure_hook(step)

    def _commit_event_transaction(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
    ) -> None:
        """Commit event facts, then best-effort notify local readers.

        Args:
            connection: Active SQLite transaction.
            experiment_id: Experiment whose high-water mark advanced.

        Raises:
            sqlite3.Error: The durable commit fails.

        Returns:
            None.
        """
        connection.execute("COMMIT")
        if self._event_commit_hook is None:
            return
        try:
            self._event_commit_hook(experiment_id)
        except Exception:
            logger.warning(
                "benchmark_event_notification_failed experiment_id=%s",
                experiment_id,
            )

    @staticmethod
    def _experiment_from_row(
        row: sqlite3.Row,
    ) -> StudioBenchmarkExperimentRecordV1:
        """Reparse one Experiment row and verify duplicated query columns.

        Args:
            row: Selected `studio_benchmark_experiments` row.

        Raises:
            StudioBenchmarkIntegrityError: Stored JSON or columns disagree.

        Returns:
            Strict storage-neutral Experiment record.
        """
        try:
            request = StudioBenchmarkExperimentCreateRequestV1.model_validate(
                json.loads(row["request_json"])
            )
            snapshot = ExperimentDefinitionSnapshotV1.model_validate(
                json.loads(row["snapshot_json"])
            )
            cancellation = (
                StudioBenchmarkExperimentCancellationV1.model_validate(
                    json.loads(row["cancellation_json"])
                )
                if row["cancellation_json"] is not None
                else None
            )
            row_keys = set(row.keys())
            publication_diagnostics = (
                tuple(
                    StudioBenchmarkPublicationDiagnosticV1.model_validate(item)
                    for item in json.loads(
                        row["publication_diagnostics_json"]
                    )
                )
                if "publication_diagnostics_json" in row_keys
                and row["publication_diagnostics_json"] is not None
                else ()
            )
            record = StudioBenchmarkExperimentRecordV1(
                experiment_id=row["experiment_id"],
                client_request_id=row["client_request_id"],
                request_fingerprint=row["request_fingerprint"],
                request=request,
                definition=snapshot,
                lifecycle=row["lifecycle_state"],
                terminal_reason=row["terminal_reason"],
                cancellation=cancellation,
                process_owner_id=row["process_owner_id"],
                outcome_availability=row["outcome_availability"],
                report_availability=(
                    row["publication_report_availability"]
                    if "publication_report_availability" in row_keys
                    and row["publication_report_availability"] is not None
                    else row["report_availability"]
                ),
                replay_availability=(
                    row["publication_replay_availability"]
                    if "publication_replay_availability" in row_keys
                    and row["publication_replay_availability"] is not None
                    else row["replay_availability"]
                ),
                trajectory_availability=(
                    row["publication_trajectory_availability"]
                    if "publication_trajectory_availability" in row_keys
                    and row["publication_trajectory_availability"] is not None
                    else StudioBenchmarkAvailability.NOT_PRODUCED
                ),
                bundle_availability=(
                    row["publication_bundle_availability"]
                    if "publication_bundle_availability" in row_keys
                    and row["publication_bundle_availability"] is not None
                    else StudioBenchmarkAvailability.NOT_PRODUCED
                ),
                report_artifact_id=(
                    row["publication_report_artifact_id"]
                    if "publication_report_artifact_id" in row_keys
                    else None
                ),
                bundle_artifact_id=(
                    row["publication_bundle_artifact_id"]
                    if "publication_bundle_artifact_id" in row_keys
                    else None
                ),
                publication_diagnostics=publication_diagnostics,
                event_high_water_mark=row["event_high_water_mark"],
                accepted_at=row["accepted_at"],
                updated_at=row["updated_at"],
                terminal_at=row["terminal_at"],
            )
            if request.client_request_id != record.client_request_id:
                raise ValueError("request identity column mismatch")
            if (
                canonical_snapshot_json(snapshot)
                != _json_text(json.loads(row["snapshot_json"]))
            ):
                raise ValueError("snapshot canonical form mismatch")
            return record
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.experiment.storage_corrupt",
                "Stored Benchmark Experiment facts are invalid",
            ) from error

    @staticmethod
    def _task_run_from_row(
        row: sqlite3.Row,
        *,
        artifacts: tuple[StudioBenchmarkArtifactDescriptorV1, ...] = (),
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Reparse one TaskRun row and verify query-critical columns.

        Args:
            row: Selected `studio_benchmark_task_runs` row.

        Raises:
            StudioBenchmarkIntegrityError: Stored JSON or columns disagree.

        Returns:
            Strict storage-neutral TaskRun record.
        """
        try:
            stored = StudioBenchmarkTaskRunRecordV1.model_validate(
                json.loads(row["task_run_json"])
            )
            payload = stored.model_dump()
            payload.update(
                {
                    "process_owner_id": row["process_owner_id"],
                    "core_task_run_id": row["core_task_run_id"],
                    "agent_run_id": row["agent_run_id"],
                    "task_instance_identity": row["task_instance_identity"],
                    "phases": json.loads(row["phase_results_json"]),
                    "agent_status": row["agent_status"],
                    "benchmark_outcome": row["benchmark_outcome"],
                    "evaluation": (
                        json.loads(row["evaluation_json"])
                        if row["evaluation_json"] is not None
                        else None
                    ),
                    "task_instance_availability": row[
                        "task_instance_availability"
                    ],
                    "phase_availability": row["phase_availability"],
                    "agent_status_availability": row[
                        "agent_status_availability"
                    ],
                    "result_availability": row["result_availability"],
                    "evaluation_availability": row[
                        "evaluation_availability"
                    ],
                    "replay_availability": row["replay_availability"],
                    "report_availability": row["report_availability"],
                    "trajectory_availability": row[
                        "trajectory_availability"
                    ],
                    "bundle_availability": row["bundle_availability"],
                    "replay_id": row["replay_id"],
                    "artifacts": artifacts,
                    "publication_diagnostics": json.loads(
                        row["publication_diagnostics_json"]
                    ),
                    "result": (
                        json.loads(row["result_json"])
                        if row["result_json"] is not None
                        else None
                    ),
                    "result_fingerprint": row["result_fingerprint"],
                    "started_at": row["started_at"],
                    "evaluating_at": row["evaluating_at"],
                    "cleaning_up_at": row["cleaning_up_at"],
                }
            )
            record = StudioBenchmarkTaskRunRecordV1.model_validate(payload)
            expected = (
                row["task_run_id"],
                row["experiment_id"],
                row["planned_entry_id"],
                row["schedule_order"],
                row["agent_id"],
                row["revision_id"],
                row["task_id"],
                row["repeat_index"],
                row["derived_seed"],
                row["lifecycle_state"],
                row["terminal_reason"],
                row["outcome_availability"],
                row["created_at"],
                row["updated_at"],
                row["terminal_at"],
            )
            actual = (
                record.task_run_id,
                record.experiment_id,
                record.planned_entry_id,
                record.order,
                record.agent_id,
                record.revision_id,
                record.task_id,
                record.repeat,
                record.derived_seed,
                record.lifecycle.value,
                (
                    record.terminal_reason.value
                    if record.terminal_reason is not None
                    else None
                ),
                record.outcome_availability.value,
                record.created_at,
                record.updated_at,
                record.terminal_at,
            )
            if actual != expected:
                raise ValueError("TaskRun query columns disagree with JSON")
            return record
        except (
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.task_run.storage_corrupt",
                "Stored Benchmark TaskRun facts are invalid",
            ) from error

    @staticmethod
    def _experiment_select(where: str) -> str:
        """Build an Experiment query with its optional publication overlay.

        Args:
            where: Trusted static SQL predicate supplied by this module.

        Returns:
            Query text joining the one-to-one publication projection.
        """
        return (
            "SELECT e.*, "
            "p.report_availability AS publication_report_availability, "
            "p.trajectory_availability "
            "AS publication_trajectory_availability, "
            "p.bundle_availability AS publication_bundle_availability, "
            "p.replay_availability AS publication_replay_availability, "
            "p.report_artifact_id AS publication_report_artifact_id, "
            "p.bundle_artifact_id AS publication_bundle_artifact_id, "
            "p.diagnostics_json AS publication_diagnostics_json "
            "FROM studio_benchmark_experiments e "
            "LEFT JOIN studio_benchmark_publications p "
            "ON p.experiment_id = e.experiment_id "
            f"{where}"
        )

    @staticmethod
    def _artifacts_in_connection(
        connection: sqlite3.Connection,
        experiment_id: str,
        *,
        task_run_id: str | None = None,
    ) -> tuple[StudioBenchmarkArtifactDescriptorV1, ...]:
        """Load artifact descriptors for one validated Experiment scope.

        Args:
            connection: Active SQLite connection or transaction.
            experiment_id: Owning Experiment identity.
            task_run_id: Optional TaskRun scope.

        Raises:
            StudioBenchmarkIntegrityError: Stored descriptors are invalid.

        Returns:
            Stable descriptors ordered by opaque artifact identity.
        """
        if task_run_id is None:
            rows = connection.execute(
                "SELECT descriptor_json FROM studio_benchmark_artifacts "
                "WHERE experiment_id = ? ORDER BY artifact_id ASC",
                (experiment_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT descriptor_json FROM studio_benchmark_artifacts "
                "WHERE experiment_id = ? AND task_run_id = ? "
                "ORDER BY artifact_id ASC",
                (experiment_id, task_run_id),
            ).fetchall()
        try:
            return tuple(
                StudioBenchmarkArtifactDescriptorV1.model_validate(
                    json.loads(row["descriptor_json"])
                )
                for row in rows
            )
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.storage_corrupt",
                "Stored Benchmark artifact metadata is invalid",
            ) from error

    @staticmethod
    def _request_json(
        request: StudioBenchmarkExperimentCreateRequestV1,
    ) -> str:
        """Serialize one strict complete create request.

        Args:
            request: Complete create request DTO.

        Returns:
            Canonical request JSON text.
        """
        return _json_text(
            request.model_dump(mode="json", by_alias=True, exclude_none=True)
        )

    @staticmethod
    def _task_json(task_run: StudioBenchmarkTaskRunRecordV1) -> str:
        """Serialize one strict TaskRun record.

        Args:
            task_run: Stable planned TaskRun.

        Returns:
            Canonical TaskRun JSON text.
        """
        return _json_text(
            task_run.model_dump(mode="json", by_alias=True, exclude_none=True)
        )

    def find_by_client_request_id(
        self,
        client_request_id: str,
    ) -> StudioBenchmarkExperimentRecordV1 | None:
        """Find a durable request before current definition revalidation.

        Args:
            client_request_id: Strict idempotency identity.

        Raises:
            StudioBenchmarkStorageError: SQLite query fails.
            StudioBenchmarkIntegrityError: Stored row is invalid.

        Returns:
            Existing Experiment record or ``None``.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._experiment_select(
                        "WHERE e.client_request_id = ?"
                    ),
                    (client_request_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment storage query failed",
            ) from error
        return self._experiment_from_row(row) if row is not None else None

    def _task_runs_in_connection(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
    ) -> tuple[StudioBenchmarkTaskRunRecordV1, ...]:
        """Load all TaskRuns in stable order inside an active transaction.

        Args:
            connection: Active SQLite transaction.
            experiment_id: Owning Experiment identity.

        Returns:
            Strict TaskRuns ordered by schedule and identity.
        """
        rows = connection.execute(
            "SELECT * FROM studio_benchmark_task_runs "
            "WHERE experiment_id = ? "
            "ORDER BY schedule_order ASC, task_run_id ASC",
            (experiment_id,),
        ).fetchall()
        return tuple(
            self._task_run_from_row(
                row,
                artifacts=self._artifacts_in_connection(
                    connection,
                    experiment_id,
                    task_run_id=row["task_run_id"],
                ),
            )
            for row in rows
        )

    def _aggregate_in_connection(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
    ) -> StudioBenchmarkExperimentAggregate:
        """Load one complete aggregate inside an active transaction.

        Args:
            connection: Active SQLite transaction.
            experiment_id: Opaque aggregate identity.

        Raises:
            StudioBenchmarkNotFoundError: Experiment is absent.

        Returns:
            Strict Experiment and all planned TaskRuns.
        """
        row = connection.execute(
            self._experiment_select("WHERE e.experiment_id = ?"),
            (experiment_id,),
        ).fetchone()
        if row is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.experiment.not_found",
                "Benchmark Experiment was not found",
            )
        return StudioBenchmarkExperimentAggregate(
            experiment=self._experiment_from_row(row),
            task_runs=self._task_runs_in_connection(connection, experiment_id),
            binding_authority=self._binding_in_connection(
                connection,
                experiment_id,
            ),
        )

    @staticmethod
    def _binding_in_connection(
        connection: sqlite3.Connection,
        experiment_id: str,
    ) -> StudioBenchmarkExperimentBindingAuthority | None:
        """Load private binding authority without joining public queries.

        Args:
            connection: Active SQLite connection or transaction.
            experiment_id: Owning Experiment identity.

        Raises:
            StudioBenchmarkIntegrityError: Stored authority is malformed.

        Returns:
            Private authority or ``None`` for historical rows.
        """
        row = connection.execute(
            "SELECT experiment_id, profile_id, binding_fingerprint, "
            "environment_candidate, created_at "
            "FROM studio_benchmark_experiment_bindings "
            "WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            environment = str(row["environment_candidate"])
            if environment not in {"real_android", "fake_device"}:
                raise ValueError("invalid private environment candidate")
            fingerprint = str(row["binding_fingerprint"])
            if not fingerprint.startswith("sha256:") or len(fingerprint) != 71:
                raise ValueError("invalid private binding fingerprint")
            return StudioBenchmarkExperimentBindingAuthority(
                experiment_id=str(row["experiment_id"]),
                profile_id=str(row["profile_id"]),
                binding_fingerprint=fingerprint,
                environment_candidate=environment,  # type: ignore[arg-type]
                created_at=int(row["created_at"]),
            )
        except (TypeError, ValueError) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.experiment.binding_corrupt",
                "Stored Benchmark device authority is invalid",
            ) from error

    def create_accepted_experiment(
        self,
        *,
        experiment: StudioBenchmarkExperimentRecordV1,
        request: StudioBenchmarkExperimentCreateRequestV1,
        snapshot: ExperimentDefinitionSnapshotV1,
        task_runs: tuple[StudioBenchmarkTaskRunRecordV1, ...],
        initial_event: StudioBenchmarkEventDraftV1,
        binding_authority: StudioBenchmarkExperimentBindingAuthority,
    ) -> StudioBenchmarkExperimentCreateResult:
        """Atomically create Experiment, schedule, and sequence-1 event.

        Args:
            experiment: Accepted aggregate root with high-water mark 1.
            request: Complete strict create request.
            snapshot: Complete bounded immutable definition.
            task_runs: Stable planned TaskRuns.
            initial_event: Unique accepted event draft.
            binding_authority: Private exact authority pinned at acceptance.

        Raises:
            StudioBenchmarkConflictError: Idempotency content conflicts.
            StudioBenchmarkIntegrityError: Supplied aggregate is inconsistent.
            StudioBenchmarkStorageError: SQLite transaction fails.

        Returns:
            New or existing aggregate and a created flag.
        """
        if (
            experiment.lifecycle
            is not StudioBenchmarkExperimentLifecycle.ACCEPTED
            or experiment.event_high_water_mark != 1
            or not task_runs
            or any(
                item.experiment_id != experiment.experiment_id
                or item.lifecycle
                is not StudioBenchmarkTaskRunLifecycle.SCHEDULED
                for item in task_runs
            )
            or binding_authority.experiment_id != experiment.experiment_id
            or binding_authority.profile_id != snapshot.device_profile_id
        ):
            raise StudioBenchmarkIntegrityError(
                "benchmark.experiment.aggregate_invalid",
                "Accepted Benchmark Experiment aggregate is inconsistent",
            )
        snapshot_json = canonical_snapshot_json(snapshot)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT * FROM studio_benchmark_experiments "
                        "WHERE client_request_id = ?",
                        (experiment.client_request_id,),
                    ).fetchone()
                    if existing is not None:
                        record = self._experiment_from_row(existing)
                        if (
                            record.request_fingerprint
                            != experiment.request_fingerprint
                        ):
                            raise StudioBenchmarkConflictError(
                                "benchmark.experiment.idempotency_conflict",
                                "Client request identity is already used",
                            )
                        aggregate = self._aggregate_in_connection(
                            connection,
                            record.experiment_id,
                        )
                        connection.execute("COMMIT")
                        return StudioBenchmarkExperimentCreateResult(
                            aggregate=aggregate,
                            created=False,
                        )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_experiments (
                            experiment_id, client_request_id,
                            request_fingerprint, request_json, snapshot_json,
                            lifecycle_state, terminal_reason,
                            cancellation_json, outcome_availability,
                            report_availability, replay_availability,
                            event_high_water_mark, process_owner_id,
                            accepted_at, updated_at, terminal_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            experiment.experiment_id,
                            experiment.client_request_id,
                            experiment.request_fingerprint,
                            self._request_json(request),
                            snapshot_json,
                            experiment.lifecycle.value,
                            None,
                            None,
                            experiment.outcome_availability.value,
                            experiment.report_availability.value,
                            experiment.replay_availability.value,
                            experiment.event_high_water_mark,
                            experiment.process_owner_id,
                            experiment.accepted_at,
                            experiment.updated_at,
                            None,
                        ),
                    )
                    self._fail("create.after_experiment")
                    for task_run in task_runs:
                        connection.execute(
                            """
                            INSERT INTO studio_benchmark_task_runs (
                                task_run_id, experiment_id, planned_entry_id,
                                schedule_order, agent_id, revision_id, task_id,
                                repeat_index, derived_seed, lifecycle_state,
                                terminal_reason, outcome_availability,
                                task_run_json, created_at, updated_at, terminal_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                task_run.task_run_id,
                                task_run.experiment_id,
                                task_run.planned_entry_id,
                                task_run.order,
                                task_run.agent_id,
                                task_run.revision_id,
                                task_run.task_id,
                                task_run.repeat,
                                task_run.derived_seed,
                                task_run.lifecycle.value,
                                None,
                                task_run.outcome_availability.value,
                                self._task_json(task_run),
                                task_run.created_at,
                                task_run.updated_at,
                                None,
                            ),
                        )
                        self._fail("create.after_task_run")
                    envelope = StudioBenchmarkEventEnvelopeV1(
                        **initial_event.model_dump(),
                        experiment_id=experiment.experiment_id,
                        sequence=1,
                        fingerprint=benchmark_event_fingerprint(initial_event),
                    )
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_experiment_events (
                            experiment_id, sequence, event_id, fingerprint,
                            envelope_json, created_at, source,
                            source_sequence, phase
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            envelope.experiment_id,
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
                            initial_event.timestamp,
                            initial_event.source.value,
                            initial_event.source_sequence,
                            initial_event.phase,
                        ),
                    )
                    self._fail("create.after_event")
                    connection.execute(
                        """
                        INSERT INTO studio_benchmark_experiment_bindings (
                            experiment_id, profile_id, binding_fingerprint,
                            environment_candidate, created_at
                        ) VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            binding_authority.experiment_id,
                            binding_authority.profile_id,
                            binding_authority.binding_fingerprint,
                            binding_authority.environment_candidate,
                            binding_authority.created_at,
                        ),
                    )
                    self._fail("create.after_binding")
                    self._commit_event_transaction(
                        connection,
                        experiment.experiment_id,
                    )
                    return StudioBenchmarkExperimentCreateResult(
                        aggregate=StudioBenchmarkExperimentAggregate(
                            experiment=experiment,
                            task_runs=task_runs,
                            binding_authority=binding_authority,
                        ),
                        created=True,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkIntegrityError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment could not be persisted",
            ) from error

    def get_experiment(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkExperimentRecordV1:
        """Load one durable Experiment.

        Args:
            experiment_id: Opaque Experiment identity.

        Raises:
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Strict durable Experiment record.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    self._experiment_select(
                        "WHERE e.experiment_id = ?"
                    ),
                    (experiment_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment storage query failed",
            ) from error
        if row is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.experiment.not_found",
                "Benchmark Experiment was not found",
            )
        return self._experiment_from_row(row)

    @staticmethod
    def _encode_history_cursor(
        accepted_at: int,
        experiment_id: str,
        filters: StudioBenchmarkExperimentHistoryFilterV1,
    ) -> str:
        """Encode a checksummed filter-bound Experiment history boundary.

        Args:
            accepted_at: Acceptance timestamp of the last returned item.
            experiment_id: Experiment identity of the last returned item.
            filters: Exact normalized query identity for the next page.

        Returns:
            URL-safe opaque continuation cursor.
        """
        body = {
            "v": 2,
            "acceptedAt": accepted_at,
            "experimentId": experiment_id,
            "filterFingerprint": filters.fingerprint(),
        }
        body["check"] = canonical_hash(body)
        return base64.urlsafe_b64encode(
            _json_text(body).encode("utf-8")
        ).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_history_cursor(
        cursor: str | None,
        filters: StudioBenchmarkExperimentHistoryFilterV1,
    ) -> tuple[int, str] | None:
        """Decode and validate a checksummed filter-bound history cursor.

        Args:
            cursor: Optional opaque continuation cursor.
            filters: Exact normalized query identity accompanying the cursor.

        Raises:
            StudioBenchmarkValidationError: Cursor is malformed, unsupported,
                or belongs to another filter identity.

        Returns:
            Exclusive `(acceptedAt, experimentId)` boundary or ``None``.
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
            if not isinstance(value, dict):
                raise ValueError("cursor shape")
            version = value.get("v")
            expected_keys = (
                {"v", "acceptedAt", "experimentId", "check"}
                if version == 1
                else {
                    "v",
                    "acceptedAt",
                    "experimentId",
                    "filterFingerprint",
                    "check",
                }
                if version == 2
                else set()
            )
            if not expected_keys or set(value) != expected_keys:
                raise ValueError("cursor shape")
            unsigned = dict(value)
            check = unsigned.pop("check")
            accepted_at = unsigned.get("acceptedAt")
            experiment_id = unsigned.get("experimentId")
            if (
                isinstance(accepted_at, bool)
                or not isinstance(accepted_at, int)
                or accepted_at < 0
                or not isinstance(experiment_id, str)
                or not experiment_id.startswith("experiment-")
                or len(experiment_id) != 43
                or any(
                    character not in "0123456789abcdef"
                    for character in experiment_id.removeprefix(
                        "experiment-"
                    )
                )
                or check != canonical_hash(unsigned)
            ):
                raise ValueError("cursor contract")
            if version == 1 and not filters.is_empty():
                raise ValueError("legacy cursor cannot carry filters")
            if version == 2 and unsigned.get(
                "filterFingerprint"
            ) != filters.fingerprint():
                raise ValueError("cursor filter mismatch")
            return accepted_at, experiment_id
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.history_cursor_invalid",
                "Benchmark Experiment history cursor is invalid",
            ) from error

    @staticmethod
    def _history_predicate(
        filters: StudioBenchmarkExperimentHistoryFilterV1,
        after: tuple[int, str] | None,
    ) -> tuple[str, tuple[object, ...]]:
        """Build fixed SQL predicates and bound values for one History query.

        Args:
            filters: Exact typed filters validated before repository access.
            after: Optional exclusive newest-first continuation boundary.

        Returns:
            Trusted SQL suffix and bound parameter tuple.
        """
        predicates: list[str] = []
        parameters: list[object] = []
        if filters.lifecycle is not None:
            predicates.append("e.lifecycle_state = ?")
            parameters.append(filters.lifecycle.value)
        if filters.catalog_entry_id is not None:
            predicates.append(
                "json_extract("
                "e.snapshot_json, '$.source.catalogEntryId'"
                ") = ?"
            )
            parameters.append(filters.catalog_entry_id)
        if filters.agent_id is not None:
            predicates.append(
                "EXISTS ("
                "SELECT 1 FROM studio_benchmark_task_runs history_task_run "
                "WHERE history_task_run.experiment_id = e.experiment_id "
                "AND history_task_run.agent_id = ?"
                ")"
            )
            parameters.append(filters.agent_id)
        if filters.accepted_from is not None:
            predicates.append("e.accepted_at >= ?")
            parameters.append(filters.accepted_from)
        if filters.accepted_before is not None:
            predicates.append("e.accepted_at < ?")
            parameters.append(filters.accepted_before)
        if after is not None:
            predicates.append(
                "(e.accepted_at < ? OR "
                "(e.accepted_at = ? AND e.experiment_id < ?))"
            )
            parameters.extend((after[0], after[0], after[1]))
        where = (
            f"WHERE {' AND '.join(predicates)} " if predicates else ""
        )
        return (
            where
            + "ORDER BY e.accepted_at DESC, e.experiment_id DESC LIMIT ?",
            tuple(parameters),
        )

    def list_experiments(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        filters: StudioBenchmarkExperimentHistoryFilterV1 | None = None,
    ) -> StudioBenchmarkExperimentRecordPageV1:
        """List matching Experiments using newest-first keyset pagination.

        Args:
            limit: Requested page size within 1..100.
            cursor: Optional opaque exclusive continuation boundary.
            filters: Optional exact immutable History filter identity.

        Raises:
            StudioBenchmarkValidationError: Limit or cursor is invalid.
            StudioBenchmarkStorageError: SQLite query fails.
            StudioBenchmarkIntegrityError: Stored rows are invalid.

        Returns:
            Bounded storage-neutral Experiment record page.
        """
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= 100
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.history_limit_invalid",
                "Benchmark Experiment history limit must be within 1 and 100",
            )
        normalized_filters = (
            filters
            if filters is not None
            else StudioBenchmarkExperimentHistoryFilterV1()
        )
        if not isinstance(
            normalized_filters,
            StudioBenchmarkExperimentHistoryFilterV1,
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.experiment.history_filter_invalid",
                "Benchmark Experiment history filter is invalid",
            )
        after = self._decode_history_cursor(cursor, normalized_filters)
        sql_suffix, parameters = self._history_predicate(
            normalized_filters,
            after,
        )
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    self._experiment_select(sql_suffix),
                    (*parameters, limit + 1),
                ).fetchall()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment history query failed",
            ) from error
        selected = tuple(
            self._experiment_from_row(row) for row in rows[:limit]
        )
        next_cursor = None
        if len(rows) > limit and selected:
            last = selected[-1]
            next_cursor = self._encode_history_cursor(
                last.accepted_at,
                last.experiment_id,
                normalized_filters,
            )
        return StudioBenchmarkExperimentRecordPageV1(
            items=selected,
            next_cursor=next_cursor,
        )

    def get_task_run(
        self,
        experiment_id: str,
        task_run_id: str,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Load one TaskRun only through its owning Experiment.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Opaque TaskRun identity.

        Raises:
            StudioBenchmarkNotFoundError: Scoped TaskRun is absent.
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Strict durable TaskRun record.
        """
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM studio_benchmark_task_runs "
                    "WHERE experiment_id = ? AND task_run_id = ?",
                    (experiment_id, task_run_id),
                ).fetchone()
                artifacts = self._artifacts_in_connection(
                    connection,
                    experiment_id,
                    task_run_id=task_run_id,
                )
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.task_run.storage_failed",
                "Benchmark TaskRun storage query failed",
            ) from error
        if row is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.task_run.not_found",
                "Benchmark TaskRun was not found",
            )
        return self._task_run_from_row(row, artifacts=artifacts)

    @staticmethod
    def _encode_cursor(
        experiment_id: str,
        order: int,
        task_run_id: str,
    ) -> str:
        """Encode one checksummed opaque scoped TaskRun cursor.

        Args:
            experiment_id: Cursor scope.
            order: Last returned schedule order.
            task_run_id: Last returned TaskRun identity.

        Returns:
            URL-safe opaque cursor.
        """
        from zhixing.benchmark.identity import canonical_hash

        body = {
            "v": 1,
            "experiment": experiment_id,
            "order": order,
            "taskRunId": task_run_id,
        }
        body["check"] = canonical_hash(body)
        raw = _json_text(body).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(
        cursor: str | None,
        experiment_id: str,
    ) -> tuple[int, str] | None:
        """Decode and validate one scoped TaskRun cursor.

        Args:
            cursor: Optional opaque cursor.
            experiment_id: Expected scope.

        Raises:
            StudioBenchmarkValidationError: Cursor is malformed or mismatched.

        Returns:
            Last `(order, taskRunId)` tuple or ``None``.
        """
        if cursor is None:
            return None
        try:
            from zhixing.benchmark.identity import canonical_hash

            padding = "=" * (-len(cursor) % 4)
            value = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            )
            if not isinstance(value, dict):
                raise ValueError("cursor root")
            check = value.pop("check", None)
            if (
                value.get("v") != 1
                or value.get("experiment") != experiment_id
                or not isinstance(value.get("order"), int)
                or value["order"] < 0
                or not isinstance(value.get("taskRunId"), str)
                or check != canonical_hash(value)
            ):
                raise ValueError("cursor contract")
            return int(value["order"]), value["taskRunId"]
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.task_run.cursor_invalid",
                "Benchmark TaskRun cursor is invalid",
            ) from error

    def list_task_runs(
        self,
        experiment_id: str,
        *,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkTaskRunPageV1:
        """List stable TaskRuns with a bounded opaque continuation cursor.

        Args:
            experiment_id: Owning Experiment identity.
            limit: Requested page size within 1..100.
            cursor: Optional cursor bound to this Experiment.

        Raises:
            StudioBenchmarkValidationError: Limit or cursor is invalid.
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Stable TaskRun page.
        """
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise StudioBenchmarkValidationError(
                "benchmark.task_run.limit_invalid",
                "Benchmark TaskRun page limit must be within 1 and 100",
            )
        after = self._decode_cursor(cursor, experiment_id)
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
                if after is None:
                    rows = connection.execute(
                        "SELECT * FROM studio_benchmark_task_runs "
                        "WHERE experiment_id = ? "
                        "ORDER BY schedule_order ASC, task_run_id ASC LIMIT ?",
                        (experiment_id, limit + 1),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        "SELECT * FROM studio_benchmark_task_runs "
                        "WHERE experiment_id = ? AND "
                        "(schedule_order > ? OR "
                        "(schedule_order = ? AND task_run_id > ?)) "
                        "ORDER BY schedule_order ASC, task_run_id ASC LIMIT ?",
                        (
                            experiment_id,
                            after[0],
                            after[0],
                            after[1],
                            limit + 1,
                        ),
                    ).fetchall()
                selected = tuple(
                    self._task_run_from_row(
                        row,
                        artifacts=self._artifacts_in_connection(
                            connection,
                            experiment_id,
                            task_run_id=row["task_run_id"],
                        ),
                    )
                    for row in rows[:limit]
                )
        except StudioBenchmarkNotFoundError:
            raise
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.task_run.storage_failed",
                "Benchmark TaskRun storage query failed",
            ) from error
        next_cursor = None
        if len(rows) > limit and selected:
            last = selected[-1]
            next_cursor = self._encode_cursor(
                experiment_id,
                last.order,
                last.task_run_id,
            )
        return StudioBenchmarkTaskRunPageV1(
            experiment_id=experiment_id,
            items=selected,
            next_cursor=next_cursor,
        )

    def enroll_accepted_experiment(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
    ) -> bool:
        """Enroll newly accepted work for one process-local scheduler.

        Args:
            experiment_id: Durable Experiment identity.
            process_owner_id: Current opaque process ownership identity.

        Raises:
            ValueError: Process owner is blank.
            StudioBenchmarkStorageError: Enrollment transaction fails.

        Returns:
            True when the row is accepted and owned by this process.
        """
        if not process_owner_id.strip():
            raise ValueError("process_owner_id must not be blank")
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET process_owner_id = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state = 'accepted'
                            AND process_owner_id IN ('', ?)
                        """,
                        (process_owner_id, experiment_id, process_owner_id),
                    )
                    row = connection.execute(
                        "SELECT lifecycle_state, process_owner_id "
                        "FROM studio_benchmark_experiments "
                        "WHERE experiment_id = ?",
                        (experiment_id,),
                    ).fetchone()
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.enroll_failed",
                "Benchmark Experiment could not be enrolled",
            ) from error
        return bool(
            row is not None
            and row["lifecycle_state"] == "accepted"
            and row["process_owner_id"] == process_owner_id
        )

    def next_enrolled_experiment(
        self,
        *,
        process_owner_id: str,
    ) -> str | None:
        """Select the oldest accepted Experiment enrolled by this process.

        Args:
            process_owner_id: Current opaque process ownership identity.

        Raises:
            ValueError: Process owner is blank.
            StudioBenchmarkStorageError: Selection fails.

        Returns:
            Experiment identity or ``None`` when no local work is pending.
        """
        if not process_owner_id.strip():
            raise ValueError("process_owner_id must not be blank")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT experiment_id
                    FROM studio_benchmark_experiments
                    WHERE lifecycle_state = 'accepted'
                        AND process_owner_id = ?
                    ORDER BY accepted_at ASC, experiment_id ASC
                    LIMIT 1
                    """,
                    (process_owner_id,),
                ).fetchone()
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.dispatch_query_failed",
                "Benchmark Experiment dispatch lookup failed",
            ) from error
        return str(row["experiment_id"]) if row is not None else None

    def claim_experiment(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Claim one accepted Experiment and prepare its sole TaskRun.

        Args:
            experiment_id: Durable Experiment identity.
            process_owner_id: Current opaque process ownership identity.
            timestamp: Unix epoch milliseconds for the transition.

        Raises:
            StudioBenchmarkConflictError: Ownership, cardinality, or CAS fails.
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkStorageError: Transaction fails.

        Returns:
            Claimed aggregate in starting/preparing lifecycle.
        """
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    if len(aggregate.task_runs) != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.cardinality_unsupported",
                            "Stage 5.2B requires exactly one planned TaskRun",
                        )
                    record = aggregate.experiment
                    task = aggregate.task_runs[0]
                    if (
                        record.lifecycle
                        is not StudioBenchmarkExperimentLifecycle.ACCEPTED
                        or record.process_owner_id != process_owner_id
                        or task.lifecycle
                        is not StudioBenchmarkTaskRunLifecycle.SCHEDULED
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.claim_conflict",
                            "Benchmark Experiment cannot be claimed",
                        )
                    starting = record.model_copy(
                        update={
                            "lifecycle": (
                                StudioBenchmarkExperimentLifecycle.STARTING
                            ),
                            "updated_at": timestamp,
                        }
                    )
                    preparing = task.model_copy(
                        update={
                            "lifecycle": (
                                StudioBenchmarkTaskRunLifecycle.PREPARING
                            ),
                            "process_owner_id": process_owner_id,
                            "task_instance_availability": (
                                StudioBenchmarkAvailability.PENDING
                            ),
                            "phase_availability": (
                                StudioBenchmarkAvailability.PENDING
                            ),
                            "agent_status_availability": (
                                StudioBenchmarkAvailability.PENDING
                            ),
                            "outcome_availability": (
                                StudioBenchmarkAvailability.PENDING
                            ),
                            "result_availability": (
                                StudioBenchmarkAvailability.PENDING
                            ),
                            "updated_at": timestamp,
                            "started_at": timestamp,
                        }
                    )
                    preparing = StudioBenchmarkTaskRunRecordV1.model_validate(
                        preparing.model_dump()
                    )
                    sequence = record.event_high_water_mark
                    sequence += 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        StudioBenchmarkEventDraftV1(
                            event_id=_stable_event_id(
                                {
                                    "kind": "experiment.starting",
                                    "experiment": experiment_id,
                                    "priorEventHighWaterMark": (
                                        record.event_high_water_mark
                                    ),
                                }
                            ),
                            timestamp=timestamp,
                            source=StudioBenchmarkEventSource.WORKER,
                            kind="experiment.starting",
                        ),
                    )
                    sequence += 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        StudioBenchmarkEventDraftV1(
                            event_id=_stable_event_id(
                                {
                                    "kind": "task_run.preparing",
                                    "experiment": experiment_id,
                                    "taskRun": task.task_run_id,
                                    "priorEventHighWaterMark": (
                                        record.event_high_water_mark
                                    ),
                                }
                            ),
                            timestamp=timestamp,
                            source=StudioBenchmarkEventSource.WORKER,
                            kind="task_run.preparing",
                            task_run_id=task.task_run_id,
                            phase="preflight",
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'starting',
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state = 'accepted'
                            AND process_owner_id = ?
                        """,
                        (
                            sequence,
                            timestamp,
                            experiment_id,
                            process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.claim_race",
                            "Benchmark Experiment claim lost its CAS race",
                        )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_task_runs
                        SET lifecycle_state = 'preparing',
                            process_owner_id = ?,
                            task_instance_availability = 'pending',
                            phase_availability = 'pending',
                            agent_status_availability = 'pending',
                            outcome_availability = 'pending',
                            result_availability = 'pending',
                            task_run_json = ?, updated_at = ?, started_at = ?
                        WHERE experiment_id = ? AND task_run_id = ?
                            AND lifecycle_state = 'scheduled'
                        """,
                        (
                            process_owner_id,
                            self._task_json(preparing),
                            timestamp,
                            timestamp,
                            experiment_id,
                            task.task_run_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.task_run.claim_race",
                            "Benchmark TaskRun claim lost its CAS race",
                    )
                    self._fail("claim.after_transitions")
                    self._commit_event_transaction(connection, experiment_id)
                    return StudioBenchmarkExperimentAggregate(
                        experiment=starting.model_copy(
                            update={"event_high_water_mark": sequence}
                        ),
                        task_runs=(preparing,),
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkNotFoundError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.claim_failed",
                "Benchmark Experiment could not be claimed",
            ) from error

    def transition_execution(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        process_owner_id: str,
        experiment_lifecycle: StudioBenchmarkExperimentLifecycle,
        task_lifecycle: StudioBenchmarkTaskRunLifecycle,
        timestamp: int,
        event: StudioBenchmarkEventDraftV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Advance owner-scoped execution lifecycle and append its journal fact.

        Args:
            experiment_id: Durable Experiment identity.
            task_run_id: Stable planned TaskRun identity.
            process_owner_id: Current process ownership identity.
            experiment_lifecycle: Requested forward Experiment lifecycle.
            task_lifecycle: Requested forward TaskRun lifecycle.
            timestamp: Unix epoch milliseconds for the transition.
            event: Correlated strict journal event.

        Raises:
            StudioBenchmarkConflictError: Transition is reverse, stale, or late.
            StudioBenchmarkStorageError: Transaction fails.

        Returns:
            Updated complete aggregate.
        """
        experiment_order = {
            StudioBenchmarkExperimentLifecycle.STARTING: 1,
            StudioBenchmarkExperimentLifecycle.RUNNING: 2,
            StudioBenchmarkExperimentLifecycle.CANCELLING: 3,
            StudioBenchmarkExperimentLifecycle.FINALIZING: 4,
        }
        task_order = {
            StudioBenchmarkTaskRunLifecycle.PREPARING: 1,
            StudioBenchmarkTaskRunLifecycle.RUNNING: 2,
            StudioBenchmarkTaskRunLifecycle.EVALUATING: 3,
            StudioBenchmarkTaskRunLifecycle.CLEANING_UP: 4,
        }
        if (
            experiment_lifecycle not in experiment_order
            or task_lifecycle not in task_order
        ):
            raise StudioBenchmarkConflictError(
                "benchmark.experiment.transition_invalid",
                "Requested Benchmark execution transition is unsupported",
            )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    if len(aggregate.task_runs) != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.cardinality_unsupported",
                            "Stage 5.2B requires exactly one TaskRun",
                        )
                    record = aggregate.experiment
                    task = aggregate.task_runs[0]
                    if (
                        task.task_run_id != task_run_id
                        or record.process_owner_id != process_owner_id
                        or task.process_owner_id != process_owner_id
                        or record.lifecycle
                        is StudioBenchmarkExperimentLifecycle.TERMINAL
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.owner_stale",
                            "Benchmark execution owner is stale",
                        )
                    current_experiment = experiment_order.get(record.lifecycle, 0)
                    current_task = task_order.get(task.lifecycle, 0)
                    if (
                        experiment_order[experiment_lifecycle]
                        < current_experiment
                        or task_order[task_lifecycle] < current_task
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.transition_reverse",
                            "Benchmark execution lifecycle cannot move backward",
                        )
                    update: dict[str, Any] = {
                        "lifecycle": task_lifecycle,
                        "updated_at": timestamp,
                    }
                    if task_lifecycle is StudioBenchmarkTaskRunLifecycle.EVALUATING:
                        update["evaluating_at"] = timestamp
                    if (
                        task_lifecycle
                        is StudioBenchmarkTaskRunLifecycle.CLEANING_UP
                    ):
                        update["cleaning_up_at"] = timestamp
                    changed_task = StudioBenchmarkTaskRunRecordV1.model_validate(
                        task.model_copy(update=update).model_dump()
                    )
                    sequence = record.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        event,
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = ?, event_high_water_mark = ?,
                            updated_at = ?
                        WHERE experiment_id = ? AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            experiment_lifecycle.value,
                            sequence,
                            timestamp,
                            experiment_id,
                            process_owner_id,
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_task_runs
                        SET lifecycle_state = ?, task_run_json = ?,
                            updated_at = ?, evaluating_at = ?,
                            cleaning_up_at = ?
                        WHERE experiment_id = ? AND task_run_id = ?
                            AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            task_lifecycle.value,
                            self._task_json(changed_task),
                            timestamp,
                            changed_task.evaluating_at,
                            changed_task.cleaning_up_at,
                            experiment_id,
                            task_run_id,
                            process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.task_run.transition_race",
                            "Benchmark TaskRun transition lost its CAS race",
                    )
                    self._fail("transition.after_event")
                    self._commit_event_transaction(connection, experiment_id)
                    return StudioBenchmarkExperimentAggregate(
                        experiment=record.model_copy(
                            update={
                                "lifecycle": experiment_lifecycle,
                                "event_high_water_mark": sequence,
                                "updated_at": timestamp,
                            }
                        ),
                        task_runs=(changed_task,),
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except StudioBenchmarkConflictError:
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.transition_failed",
                "Benchmark execution transition could not be persisted",
            ) from error

    def _append_event(
        self,
        connection: sqlite3.Connection,
        experiment_id: str,
        sequence: int,
        draft: StudioBenchmarkEventDraftV1,
    ) -> StudioBenchmarkEventEnvelopeV1:
        """Append one event inside an existing aggregate transaction.

        Args:
            connection: Active SQLite transaction.
            experiment_id: Owning Experiment identity.
            sequence: Next strict journal sequence.
            draft: Strict event draft.

        Raises:
            sqlite3.Error: Insert fails.

        Returns:
            Persisted event envelope.
        """
        envelope = StudioBenchmarkEventEnvelopeV1(
            **draft.model_dump(),
            experiment_id=experiment_id,
            sequence=sequence,
            fingerprint=benchmark_event_fingerprint(draft),
        )
        connection.execute(
            """
            INSERT INTO studio_benchmark_experiment_events (
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
        return envelope

    def append_runtime_event(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
        event: StudioBenchmarkEventDraftV1,
    ) -> StudioBenchmarkEventEnvelopeV1:
        """Append one idempotent owner-scoped runtime event synchronously.

        Args:
            experiment_id: Durable Experiment identity.
            process_owner_id: Current process ownership identity.
            event: Stable strict event draft.

        Raises:
            StudioBenchmarkConflictError: Identity conflicts or owner is stale.
            StudioBenchmarkStorageError: Journal transaction fails.

        Returns:
            New or previously committed identical event envelope.
        """
        fingerprint = benchmark_event_fingerprint(event)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    existing = connection.execute(
                        "SELECT fingerprint, envelope_json "
                        "FROM studio_benchmark_experiment_events "
                        "WHERE experiment_id = ? AND event_id = ?",
                        (experiment_id, event.event_id),
                    ).fetchone()
                    if existing is not None:
                        if existing["fingerprint"] != fingerprint:
                            raise StudioBenchmarkConflictError(
                                "benchmark.event.identity_conflict",
                                "Benchmark event identity has different content",
                            )
                        envelope = StudioBenchmarkEventEnvelopeV1.model_validate(
                            json.loads(existing["envelope_json"])
                        )
                        connection.execute("COMMIT")
                        return envelope
                    record = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    ).experiment
                    if (
                        record.lifecycle
                        is StudioBenchmarkExperimentLifecycle.TERMINAL
                        or record.process_owner_id != process_owner_id
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.event.owner_stale",
                            "Benchmark runtime event owner is stale",
                        )
                    sequence = record.event_high_water_mark + 1
                    envelope = self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        event,
                    )
                    self._fail("event.after_append")
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ? AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            sequence,
                            event.timestamp,
                            experiment_id,
                            process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.event.append_race",
                            "Benchmark event append lost its owner CAS",
                        )
                    self._commit_event_transaction(connection, experiment_id)
                    return envelope
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except StudioBenchmarkConflictError:
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.event.append_failed",
                "Benchmark runtime event could not be persisted",
            ) from error

    def request_cancellation(
        self,
        experiment_id: str,
        cancellation: StudioBenchmarkExperimentCancellationV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Persist accepted or active cooperative cancellation idempotently.

        Args:
            experiment_id: Durable Experiment identity.
            cancellation: Safe cancellation command and timestamp.

        Raises:
            StudioBenchmarkConflictError: Stored cancellation content conflicts.
            StudioBenchmarkStorageError: Cancellation transaction fails.

        Returns:
            Current aggregate after the durable cancellation fact.
        """
        current = self.get_experiment(experiment_id)
        if current.lifecycle is StudioBenchmarkExperimentLifecycle.ACCEPTED:
            return self.cancel_accepted_experiment(experiment_id, cancellation)
        if current.lifecycle is StudioBenchmarkExperimentLifecycle.TERMINAL:
            with self._connect() as connection:
                return self._aggregate_in_connection(connection, experiment_id)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    record = aggregate.experiment
                    if (
                        record.lifecycle
                        is StudioBenchmarkExperimentLifecycle.TERMINAL
                    ):
                        connection.execute("COMMIT")
                        return aggregate
                    if record.cancellation is not None:
                        if (
                            record.cancellation.client_request_id
                            != cancellation.client_request_id
                        ):
                            connection.execute("COMMIT")
                            return aggregate
                        connection.execute("COMMIT")
                        return aggregate
                    event = StudioBenchmarkEventDraftV1(
                        event_id=_stable_event_id(
                            {
                                "kind": "experiment.cancellation_requested",
                                "experiment": experiment_id,
                            }
                        ),
                        timestamp=cancellation.requested_at,
                        source=StudioBenchmarkEventSource.SERVICE,
                        kind="experiment.cancellation_requested",
                        payload={
                            "clientRequestId": cancellation.client_request_id,
                            "reasonCode": cancellation.reason_code,
                        },
                    )
                    sequence = record.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        event,
                    )
                    lifecycle = (
                        record.lifecycle
                        if record.lifecycle
                        is StudioBenchmarkExperimentLifecycle.FINALIZING
                        else StudioBenchmarkExperimentLifecycle.CANCELLING
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = ?, cancellation_json = ?,
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state != 'terminal'
                            AND cancellation_json IS NULL
                        """,
                        (
                            lifecycle.value,
                            _json_text(
                                cancellation.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                            sequence,
                            cancellation.requested_at,
                            experiment_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.cancel_race",
                            "Benchmark cancellation lost its persistence race",
                    )
                    self._fail("cancel_active.after_event")
                    self._commit_event_transaction(connection, experiment_id)
                    return StudioBenchmarkExperimentAggregate(
                        experiment=record.model_copy(
                            update={
                                "lifecycle": lifecycle,
                                "cancellation": cancellation,
                                "event_high_water_mark": sequence,
                                "updated_at": cancellation.requested_at,
                            }
                        ),
                        task_runs=aggregate.task_runs,
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except StudioBenchmarkConflictError:
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.cancel_failed",
                "Benchmark cancellation could not be persisted",
            ) from error

    def commit_task_result(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        process_owner_id: str,
        result: StudioBenchmarkTaskResultV1,
        fingerprint: str,
        terminal_reason: StudioBenchmarkTaskRunTerminalReason,
        timestamp: int,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Atomically commit bounded result, provenance, and TaskRun terminal.

        Args:
            experiment_id: Durable Experiment identity.
            task_run_id: Stable planned TaskRun identity.
            process_owner_id: Current process ownership identity.
            result: Safe normalized inline TaskResult.
            fingerprint: Canonical result content fingerprint.
            terminal_reason: TaskRun terminal reason selected by orchestration.
            timestamp: Unix epoch milliseconds for the commit.

        Raises:
            StudioBenchmarkConflictError: Result conflicts or owner is stale.
            StudioBenchmarkStorageError: Result transaction fails.

        Returns:
            Committed terminal TaskRun record.
        """
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    task = next(
                        (
                            item
                            for item in aggregate.task_runs
                            if item.task_run_id == task_run_id
                        ),
                        None,
                    )
                    if task is None:
                        raise StudioBenchmarkNotFoundError(
                            "benchmark.task_run.not_found",
                            "Benchmark TaskRun was not found",
                        )
                    if task.lifecycle is StudioBenchmarkTaskRunLifecycle.TERMINAL:
                        if task.result_fingerprint != fingerprint:
                            raise StudioBenchmarkConflictError(
                                "benchmark.result.commit_conflict",
                                "Benchmark TaskResult is already immutable",
                            )
                        connection.execute("COMMIT")
                        return task
                    if (
                        aggregate.experiment.process_owner_id
                        != process_owner_id
                        or task.process_owner_id != process_owner_id
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.result.owner_stale",
                            "Benchmark TaskResult owner is stale",
                        )
                    if (
                        result.planned_task_run_id != task.task_run_id
                        or result.agent_id != task.agent_id
                        or result.agent_revision_id != task.revision_id
                        or result.task_id != task.task_id
                        or result.repeat != task.repeat
                        or result.schedule_order != task.order
                        or result.service_terminal_reason is not terminal_reason
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.result.coordinates_mismatch",
                            "Benchmark TaskResult does not match the planned TaskRun",
                        )
                    evaluation_availability = (
                        StudioBenchmarkAvailability.AVAILABLE
                        if result.evaluation is not None
                        else StudioBenchmarkAvailability.NOT_PRODUCED
                    )
                    phase_availability = (
                        StudioBenchmarkAvailability.AVAILABLE
                        if result.phases
                        else StudioBenchmarkAvailability.NOT_PRODUCED
                    )
                    agent_status_availability = (
                        StudioBenchmarkAvailability.AVAILABLE
                        if result.agent_status is not None
                        else StudioBenchmarkAvailability.NOT_PRODUCED
                    )
                    terminal = StudioBenchmarkTaskRunRecordV1.model_validate(
                        task.model_copy(
                            update={
                                "lifecycle": (
                                    StudioBenchmarkTaskRunLifecycle.TERMINAL
                                ),
                                "terminal_reason": terminal_reason,
                                "core_task_run_id": result.core_task_run_id,
                                "agent_run_id": result.agent_run_id,
                                "task_instance_identity": (
                                    result.task_instance_identity
                                ),
                                "phases": result.phases,
                                "agent_status": result.agent_status,
                                "benchmark_outcome": (
                                    result.benchmark_outcome
                                ),
                                "evaluation": result.evaluation,
                                "task_instance_availability": (
                                    StudioBenchmarkAvailability.AVAILABLE
                                ),
                                "phase_availability": phase_availability,
                                "agent_status_availability": (
                                    agent_status_availability
                                ),
                                "outcome_availability": (
                                    StudioBenchmarkAvailability.AVAILABLE
                                ),
                                "result_availability": (
                                    StudioBenchmarkAvailability.AVAILABLE
                                ),
                                "evaluation_availability": (
                                    evaluation_availability
                                ),
                                "result": result,
                                "result_fingerprint": fingerprint,
                                "updated_at": timestamp,
                                "terminal_at": timestamp,
                            }
                        ).model_dump()
                    )
                    event = StudioBenchmarkEventDraftV1(
                        event_id=_stable_event_id(
                            {
                                "kind": "task_run.terminal",
                                "experiment": experiment_id,
                                "taskRun": task_run_id,
                            }
                        ),
                        timestamp=timestamp,
                        source=StudioBenchmarkEventSource.WORKER,
                        kind="task_run.terminal",
                        task_run_id=task_run_id,
                        phase="result",
                        payload={
                            "terminalReason": terminal_reason.value,
                            "agentStatus": (
                                result.agent_status.value
                                if result.agent_status is not None
                                else None
                            ),
                            "benchmarkOutcome": (
                                result.benchmark_outcome.value
                            ),
                            "coreTaskRunId": result.core_task_run_id,
                        },
                    )
                    sequence = aggregate.experiment.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        event,
                    )
                    result_json = _json_text(
                        result.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_task_runs
                        SET lifecycle_state = 'terminal', terminal_reason = ?,
                            core_task_run_id = ?, agent_run_id = ?,
                            task_instance_identity = ?, phase_results_json = ?,
                            agent_status = ?, benchmark_outcome = ?,
                            evaluation_json = ?,
                            task_instance_availability = 'available',
                            phase_availability = ?,
                            agent_status_availability = ?,
                            outcome_availability = 'available',
                            result_availability = 'available',
                            evaluation_availability = ?,
                            result_json = ?, result_fingerprint = ?,
                            task_run_json = ?, updated_at = ?, terminal_at = ?
                        WHERE experiment_id = ? AND task_run_id = ?
                            AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            terminal_reason.value,
                            result.core_task_run_id,
                            result.agent_run_id,
                            result.task_instance_identity,
                            _json_text(
                                [
                                    item.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                    for item in result.phases
                                ]
                            ),
                            (
                                result.agent_status.value
                                if result.agent_status is not None
                                else None
                            ),
                            result.benchmark_outcome.value,
                            (
                                _json_text(
                                    result.evaluation.model_dump(
                                        mode="json",
                                        by_alias=True,
                                        exclude_none=True,
                                    )
                                )
                                if result.evaluation is not None
                                else None
                            ),
                            phase_availability.value,
                            agent_status_availability.value,
                            evaluation_availability.value,
                            result_json,
                            fingerprint,
                            self._task_json(terminal),
                            timestamp,
                            timestamp,
                            experiment_id,
                            task_run_id,
                            process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.result.commit_race",
                            "Benchmark TaskResult commit lost its CAS race",
                        )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'finalizing',
                            outcome_availability = 'available',
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ? AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            sequence,
                            timestamp,
                            experiment_id,
                            process_owner_id,
                        ),
                    )
                    self._fail("result.after_commit")
                    self._commit_event_transaction(connection, experiment_id)
                    return terminal
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkNotFoundError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.result.commit_failed",
                "Benchmark TaskResult could not be persisted",
            ) from error

    def finalize_experiment(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
        terminal_reason: StudioBenchmarkExperimentTerminalReason,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Finalize an owner-scoped Experiment with exactly one terminal event.

        Args:
            experiment_id: Durable Experiment identity.
            process_owner_id: Current process ownership identity.
            terminal_reason: Stable service terminal reason.
            timestamp: Unix epoch milliseconds for finalization.

        Raises:
            StudioBenchmarkConflictError: Owner is stale or TaskRun is active.
            StudioBenchmarkStorageError: Terminal transaction fails.

        Returns:
            Immutable terminal aggregate.
        """
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    record = aggregate.experiment
                    if (
                        record.lifecycle
                        is StudioBenchmarkExperimentLifecycle.TERMINAL
                    ):
                        connection.execute("COMMIT")
                        return aggregate
                    if (
                        record.process_owner_id != process_owner_id
                        or any(
                            task.lifecycle
                            is not StudioBenchmarkTaskRunLifecycle.TERMINAL
                            for task in aggregate.task_runs
                        )
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.finalize_conflict",
                            "Benchmark Experiment cannot be finalized",
                        )
                    sequence = record.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        StudioBenchmarkEventDraftV1(
                            event_id=_stable_event_id(
                                {
                                    "kind": "experiment.terminal",
                                    "experiment": experiment_id,
                                }
                            ),
                            timestamp=timestamp,
                            source=StudioBenchmarkEventSource.WORKER,
                            kind="experiment.terminal",
                            payload={
                                "terminalReason": terminal_reason.value,
                            },
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'terminal',
                            terminal_reason = ?, process_owner_id = '',
                            event_high_water_mark = ?, updated_at = ?,
                            terminal_at = ?
                        WHERE experiment_id = ? AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            terminal_reason.value,
                            sequence,
                            timestamp,
                            timestamp,
                            experiment_id,
                            process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.finalize_race",
                            "Benchmark Experiment finalization lost its CAS race",
                    )
                    self._fail("finalize.after_terminal")
                    self._commit_event_transaction(connection, experiment_id)
                    return StudioBenchmarkExperimentAggregate(
                        experiment=record.model_copy(
                            update={
                                "lifecycle": (
                                    StudioBenchmarkExperimentLifecycle.TERMINAL
                                ),
                                "terminal_reason": terminal_reason,
                                "process_owner_id": "",
                                "event_high_water_mark": sequence,
                                "updated_at": timestamp,
                                "terminal_at": timestamp,
                            }
                        ),
                        task_runs=aggregate.task_runs,
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except StudioBenchmarkConflictError:
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.finalize_failed",
                "Benchmark Experiment could not be finalized",
            ) from error

    def finish_task_without_result(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        process_owner_id: str,
        terminal_reason: StudioBenchmarkTaskRunTerminalReason,
        timestamp: int,
        error_code: str,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Close work that stopped before a trustworthy Core result existed.

        Args:
            experiment_id: Durable Experiment identity.
            task_run_id: Stable planned TaskRun identity.
            process_owner_id: Current process ownership identity.
            terminal_reason: Cancelled or failed TaskRun reason.
            timestamp: Unix epoch milliseconds for the commit.
            error_code: Safe bounded orchestration failure code.

        Raises:
            StudioBenchmarkConflictError: Owner is stale or result exists.
            StudioBenchmarkStorageError: Terminal transaction fails.

        Returns:
            Terminal TaskRun with unavailable result and outcome facts.
        """
        availability = (
            StudioBenchmarkAvailability.FAILED
            if terminal_reason is StudioBenchmarkTaskRunTerminalReason.FAILED
            else StudioBenchmarkAvailability.NOT_PRODUCED
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    task = next(
                        (
                            item
                            for item in aggregate.task_runs
                            if item.task_run_id == task_run_id
                        ),
                        None,
                    )
                    if task is None:
                        raise StudioBenchmarkNotFoundError(
                            "benchmark.task_run.not_found",
                            "Benchmark TaskRun was not found",
                        )
                    if task.lifecycle is StudioBenchmarkTaskRunLifecycle.TERMINAL:
                        connection.execute("COMMIT")
                        return task
                    if (
                        aggregate.experiment.process_owner_id
                        != process_owner_id
                        or task.process_owner_id != process_owner_id
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.task_run.owner_stale",
                            "Benchmark TaskRun owner is stale",
                        )
                    terminal = StudioBenchmarkTaskRunRecordV1.model_validate(
                        task.model_copy(
                            update={
                                "lifecycle": (
                                    StudioBenchmarkTaskRunLifecycle.TERMINAL
                                ),
                                "terminal_reason": terminal_reason,
                                "outcome_availability": (
                                    StudioBenchmarkAvailability.NOT_PRODUCED
                                ),
                                "task_instance_availability": (
                                    StudioBenchmarkAvailability.NOT_PRODUCED
                                ),
                                "phase_availability": availability,
                                "agent_status_availability": (
                                    StudioBenchmarkAvailability.NOT_PRODUCED
                                ),
                                "result_availability": availability,
                                "updated_at": timestamp,
                                "terminal_at": timestamp,
                            }
                        ).model_dump()
                    )
                    sequence = aggregate.experiment.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        StudioBenchmarkEventDraftV1(
                            event_id=_stable_event_id(
                                {
                                    "kind": "task_run.terminal",
                                    "experiment": experiment_id,
                                    "taskRun": task_run_id,
                                }
                            ),
                            timestamp=timestamp,
                            source=StudioBenchmarkEventSource.WORKER,
                            kind="task_run.terminal",
                            task_run_id=task_run_id,
                            phase="orchestration",
                            payload={
                                "terminalReason": terminal_reason.value,
                                "resultAvailability": availability.value,
                                "errorCode": error_code[:256],
                            },
                        ),
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_task_runs
                        SET lifecycle_state = 'terminal',
                            terminal_reason = ?,
                            task_instance_availability = 'not_produced',
                            phase_availability = ?,
                            agent_status_availability = 'not_produced',
                            outcome_availability = 'not_produced',
                            result_availability = ?,
                            task_run_json = ?, updated_at = ?, terminal_at = ?
                        WHERE experiment_id = ? AND task_run_id = ?
                            AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            terminal_reason.value,
                            availability.value,
                            availability.value,
                            self._task_json(terminal),
                            timestamp,
                            timestamp,
                            experiment_id,
                            task_run_id,
                            process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.task_run.finish_race",
                            "Benchmark TaskRun finish lost its CAS race",
                        )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'finalizing',
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ? AND process_owner_id = ?
                            AND lifecycle_state != 'terminal'
                        """,
                        (
                            sequence,
                            timestamp,
                            experiment_id,
                            process_owner_id,
                        ),
                    )
                    self._fail("task_without_result.after_commit")
                    self._commit_event_transaction(connection, experiment_id)
                    return terminal
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkNotFoundError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.task_run.finish_failed",
                "Benchmark TaskRun could not be closed safely",
            ) from error

    @staticmethod
    def _encode_recovery_cursor(
        accepted_at: int,
        experiment_id: str,
    ) -> str:
        """Encode one opaque deterministic recovery page cursor.

        Args:
            accepted_at: Accepted timestamp of the last returned record.
            experiment_id: Identity of the last returned record.

        Returns:
            URL-safe opaque cursor.
        """
        payload = _json_text(
            {
                "acceptedAt": accepted_at,
                "experimentId": experiment_id,
            }
        ).encode("utf-8")
        return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_recovery_cursor(cursor: str) -> tuple[int, str]:
        """Decode and validate one recovery page cursor.

        Args:
            cursor: Opaque cursor returned by the repository.

        Raises:
            StudioBenchmarkValidationError: Cursor is malformed.

        Returns:
            Accepted timestamp and Experiment identity.
        """
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            )
            accepted_at = int(payload["acceptedAt"])
            experiment_id = str(payload["experimentId"])
            if accepted_at < 0 or not experiment_id.startswith("experiment-"):
                raise ValueError("invalid recovery cursor coordinates")
            return accepted_at, experiment_id
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StudioBenchmarkValidationError(
                "benchmark.recovery.cursor_invalid",
                "Benchmark recovery cursor is invalid",
            ) from error

    @staticmethod
    def _recovery_candidate(
        aggregate: StudioBenchmarkExperimentAggregate,
        *,
        publication_committed: bool,
    ) -> StudioBenchmarkRecoveryCandidateV1:
        """Project one aggregate into a bounded recovery candidate.

        Args:
            aggregate: Current coherent aggregate.
            publication_committed: Whether coordinated publication exists.

        Returns:
            Safe candidate without the raw process owner.
        """
        record = aggregate.experiment
        return StudioBenchmarkRecoveryCandidateV1(
            experiment_id=record.experiment_id,
            previous_lifecycle=record.lifecycle,
            recovery_token=_recovery_token(record),
            prior_event_high_water_mark=record.event_high_water_mark,
            accepted_at=record.accepted_at,
            cancellation_requested=record.cancellation is not None,
            publication_committed=publication_committed,
            task_runs=tuple(
                StudioBenchmarkRecoveryTaskRunV1(
                    task_run_id=task.task_run_id,
                    lifecycle=task.lifecycle,
                    terminal_reason=task.terminal_reason,
                    result_availability=task.result_availability,
                    replay_availability=task.replay_availability,
                )
                for task in aggregate.task_runs
            ),
        )

    def _validate_recovery_candidate(
        self,
        connection: sqlite3.Connection,
        candidate: StudioBenchmarkRecoveryCandidateV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Validate a candidate against current transactional facts.

        Args:
            connection: Active immediate transaction.
            candidate: Previously queried stale candidate.

        Raises:
            StudioBenchmarkConflictError: Facts changed after the query.

        Returns:
            Current coherent aggregate.
        """
        aggregate = self._aggregate_in_connection(
            connection,
            candidate.experiment_id,
        )
        current = self._recovery_candidate(
            aggregate,
            publication_committed=(
                connection.execute(
                    "SELECT 1 FROM studio_benchmark_publications "
                    "WHERE experiment_id = ?",
                    (candidate.experiment_id,),
                ).fetchone()
                is not None
            ),
        )
        if current != candidate:
            raise StudioBenchmarkConflictError(
                "benchmark.recovery.candidate_stale",
                "Benchmark recovery candidate changed before commit",
            )
        return aggregate

    @staticmethod
    def _recovery_event_exists(
        connection: sqlite3.Connection,
        experiment_id: str,
        event_id: str,
    ) -> bool:
        """Return whether a stable recovery event already committed.

        Args:
            connection: Active SQLite transaction.
            experiment_id: Owning Experiment identity.
            event_id: Stable recovery event identity.

        Returns:
            True when the identical attempt is already durable.
        """
        return (
            connection.execute(
                "SELECT 1 FROM studio_benchmark_experiment_events "
                "WHERE experiment_id = ? AND event_id = ?",
                (experiment_id, event_id),
            ).fetchone()
            is not None
        )

    @staticmethod
    def _closed_recovery_availability(
        availability: StudioBenchmarkAvailability,
    ) -> StudioBenchmarkAvailability:
        """Close a pending availability without changing committed facts.

        Args:
            availability: Current availability fact.

        Returns:
            ``not_produced`` for pending, otherwise the existing fact.
        """
        if availability is StudioBenchmarkAvailability.PENDING:
            return StudioBenchmarkAvailability.NOT_PRODUCED
        return availability

    @staticmethod
    def _reset_starting_task(
        task: StudioBenchmarkTaskRunRecordV1,
        *,
        timestamp: int,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Reset side-effect-free preflight work to its planned state.

        Args:
            task: TaskRun currently in preflight.
            timestamp: Recovery decision timestamp.

        Raises:
            ValueError: Reset facts violate the strict TaskRun DTO.

        Returns:
            Scheduled TaskRun ready for normal preflight.
        """
        return StudioBenchmarkTaskRunRecordV1.model_validate(
            task.model_copy(
                update={
                    "lifecycle": StudioBenchmarkTaskRunLifecycle.SCHEDULED,
                    "terminal_reason": None,
                    "process_owner_id": "",
                    "core_task_run_id": None,
                    "agent_run_id": None,
                    "task_instance_identity": None,
                    "phases": (),
                    "agent_status": None,
                    "benchmark_outcome": None,
                    "evaluation": None,
                    "task_instance_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "phase_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "agent_status_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "outcome_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "result_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "evaluation_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "replay_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "report_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "trajectory_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "bundle_availability": (
                        StudioBenchmarkAvailability.NOT_PRODUCED
                    ),
                    "replay_id": None,
                    "publication_diagnostics": (),
                    "result": None,
                    "result_fingerprint": None,
                    "updated_at": timestamp,
                    "started_at": None,
                    "evaluating_at": None,
                    "cleaning_up_at": None,
                    "terminal_at": None,
                }
            ).model_dump()
        )

    @classmethod
    def _interrupt_recovery_task(
        cls,
        task: StudioBenchmarkTaskRunRecordV1,
        *,
        timestamp: int,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Terminalize uncertain work while retaining committed facts.

        Args:
            task: Current nonterminal TaskRun.
            timestamp: Recovery decision timestamp.

        Raises:
            ValueError: Closed facts violate the strict TaskRun DTO.

        Returns:
            Interrupted TaskRun with no pending availability.
        """
        return StudioBenchmarkTaskRunRecordV1.model_validate(
            task.model_copy(
                update={
                    "lifecycle": StudioBenchmarkTaskRunLifecycle.TERMINAL,
                    "terminal_reason": (
                        StudioBenchmarkTaskRunTerminalReason.INTERRUPTED
                    ),
                    "process_owner_id": "",
                    "task_instance_availability": (
                        cls._closed_recovery_availability(
                            task.task_instance_availability
                        )
                    ),
                    "phase_availability": (
                        cls._closed_recovery_availability(
                            task.phase_availability
                        )
                    ),
                    "agent_status_availability": (
                        cls._closed_recovery_availability(
                            task.agent_status_availability
                        )
                    ),
                    "outcome_availability": (
                        cls._closed_recovery_availability(
                            task.outcome_availability
                        )
                    ),
                    "result_availability": (
                        cls._closed_recovery_availability(
                            task.result_availability
                        )
                    ),
                    "evaluation_availability": (
                        cls._closed_recovery_availability(
                            task.evaluation_availability
                        )
                    ),
                    "replay_availability": (
                        cls._closed_recovery_availability(
                            task.replay_availability
                        )
                    ),
                    "report_availability": (
                        cls._closed_recovery_availability(
                            task.report_availability
                        )
                    ),
                    "trajectory_availability": (
                        cls._closed_recovery_availability(
                            task.trajectory_availability
                        )
                    ),
                    "bundle_availability": (
                        cls._closed_recovery_availability(
                            task.bundle_availability
                        )
                    ),
                    "updated_at": timestamp,
                    "terminal_at": timestamp,
                }
            ).model_dump()
        )

    def _write_recovery_task(
        self,
        connection: sqlite3.Connection,
        previous: StudioBenchmarkTaskRunRecordV1,
        changed: StudioBenchmarkTaskRunRecordV1,
    ) -> None:
        """CAS-write all duplicated mutable TaskRun recovery facts.

        Args:
            connection: Active immediate transaction.
            previous: Expected current TaskRun.
            changed: Strict replacement TaskRun.

        Raises:
            StudioBenchmarkConflictError: The TaskRun changed concurrently.

        Returns:
            None.
        """
        connection.execute(
            """
            UPDATE studio_benchmark_task_runs
            SET lifecycle_state = ?, terminal_reason = ?,
                process_owner_id = ?, core_task_run_id = ?,
                agent_run_id = ?, task_instance_identity = ?,
                phase_results_json = ?, agent_status = ?,
                benchmark_outcome = ?, evaluation_json = ?,
                task_instance_availability = ?, phase_availability = ?,
                agent_status_availability = ?, outcome_availability = ?,
                result_availability = ?, evaluation_availability = ?,
                replay_availability = ?, report_availability = ?,
                trajectory_availability = ?, bundle_availability = ?,
                replay_id = ?, publication_diagnostics_json = ?,
                result_json = ?, result_fingerprint = ?,
                task_run_json = ?, updated_at = ?, started_at = ?,
                evaluating_at = ?, cleaning_up_at = ?, terminal_at = ?
            WHERE experiment_id = ? AND task_run_id = ?
                AND lifecycle_state = ? AND process_owner_id = ?
            """,
            (
                changed.lifecycle.value,
                (
                    changed.terminal_reason.value
                    if changed.terminal_reason is not None
                    else None
                ),
                changed.process_owner_id,
                changed.core_task_run_id,
                changed.agent_run_id,
                changed.task_instance_identity,
                _json_text(
                    [
                        item.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                        for item in changed.phases
                    ]
                ),
                (
                    changed.agent_status.value
                    if changed.agent_status is not None
                    else None
                ),
                (
                    changed.benchmark_outcome.value
                    if changed.benchmark_outcome is not None
                    else None
                ),
                (
                    _json_text(
                        changed.evaluation.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                    )
                    if changed.evaluation is not None
                    else None
                ),
                changed.task_instance_availability.value,
                changed.phase_availability.value,
                changed.agent_status_availability.value,
                changed.outcome_availability.value,
                changed.result_availability.value,
                changed.evaluation_availability.value,
                changed.replay_availability.value,
                changed.report_availability.value,
                changed.trajectory_availability.value,
                changed.bundle_availability.value,
                changed.replay_id,
                _json_text(
                    [
                        item.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                        for item in changed.publication_diagnostics
                    ]
                ),
                (
                    _json_text(
                        changed.result.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                    )
                    if changed.result is not None
                    else None
                ),
                changed.result_fingerprint,
                self._task_json(changed),
                changed.updated_at,
                changed.started_at,
                changed.evaluating_at,
                changed.cleaning_up_at,
                changed.terminal_at,
                previous.experiment_id,
                previous.task_run_id,
                previous.lifecycle.value,
                previous.process_owner_id,
            ),
        )
        if connection.execute(
            "SELECT changes() AS count"
        ).fetchone()["count"] != 1:
            raise StudioBenchmarkConflictError(
                "benchmark.recovery.task_run_race",
                "Benchmark TaskRun changed during startup recovery",
            )

    def list_recovery_candidates(
        self,
        *,
        process_owner_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> StudioBenchmarkRecoveryCandidatePageV1:
        """List stale nonterminal aggregates in deterministic bounded pages.

        Args:
            process_owner_id: Current opaque process identity to exclude.
            limit: Maximum candidates from 1 through 100.
            cursor: Optional opaque exclusive page cursor.

        Raises:
            StudioBenchmarkValidationError: Inputs are invalid.
            StudioBenchmarkStorageError: SQLite query fails.
            StudioBenchmarkIntegrityError: Stored facts are corrupt.

        Returns:
            Stable page ordered by accepted time and Experiment identity.
        """
        if not process_owner_id.strip():
            raise StudioBenchmarkValidationError(
                "benchmark.recovery.owner_invalid",
                "Benchmark recovery owner must not be blank",
            )
        if limit < 1 or limit > 100:
            raise StudioBenchmarkValidationError(
                "benchmark.recovery.limit_invalid",
                "Benchmark recovery limit must be between 1 and 100",
            )
        after = (
            self._decode_recovery_cursor(cursor)
            if cursor is not None
            else None
        )
        try:
            with self._connect() as connection:
                if after is None:
                    rows = connection.execute(
                        """
                        SELECT experiment_id, accepted_at
                        FROM studio_benchmark_experiments
                        WHERE lifecycle_state != 'terminal'
                            AND process_owner_id != ?
                        ORDER BY accepted_at ASC, experiment_id ASC
                        LIMIT ?
                        """,
                        (process_owner_id, limit + 1),
                    ).fetchall()
                else:
                    rows = connection.execute(
                        """
                        SELECT experiment_id, accepted_at
                        FROM studio_benchmark_experiments
                        WHERE lifecycle_state != 'terminal'
                            AND process_owner_id != ?
                            AND (
                                accepted_at > ?
                                OR (
                                    accepted_at = ?
                                    AND experiment_id > ?
                                )
                            )
                        ORDER BY accepted_at ASC, experiment_id ASC
                        LIMIT ?
                        """,
                        (
                            process_owner_id,
                            after[0],
                            after[0],
                            after[1],
                            limit + 1,
                        ),
                    ).fetchall()
                selected = rows[:limit]
                items = tuple(
                    self._recovery_candidate(
                        self._aggregate_in_connection(
                            connection,
                            row["experiment_id"],
                        ),
                        publication_committed=(
                            connection.execute(
                                "SELECT 1 "
                                "FROM studio_benchmark_publications "
                                "WHERE experiment_id = ?",
                                (row["experiment_id"],),
                            ).fetchone()
                            is not None
                        ),
                    )
                    for row in selected
                )
        except (
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
        ):
            raise
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.recovery.query_failed",
                "Benchmark startup recovery query failed",
            ) from error
        next_cursor = None
        if len(rows) > limit and items:
            last = items[-1]
            next_cursor = self._encode_recovery_cursor(
                last.accepted_at,
                last.experiment_id,
            )
        return StudioBenchmarkRecoveryCandidatePageV1(
            items=items,
            next_cursor=next_cursor,
        )

    def recover_requeue(
        self,
        candidate: StudioBenchmarkRecoveryCandidateV1,
        *,
        process_owner_id: str,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Requeue accepted or side-effect-free starting work atomically.

        Args:
            candidate: Previously queried stale aggregate facts.
            process_owner_id: New executable process owner.
            timestamp: Unix epoch milliseconds for the decision.

        Raises:
            StudioBenchmarkConflictError: Candidate or lifecycle is stale.
            StudioBenchmarkStorageError: Recovery transaction fails.

        Returns:
            Accepted aggregate owned by the current process.
        """
        if not process_owner_id.strip():
            raise StudioBenchmarkValidationError(
                "benchmark.recovery.owner_invalid",
                "Benchmark recovery owner must not be blank",
            )
        attempt = _recovery_attempt(
            candidate,
            StudioBenchmarkRecoveryDecision.REQUEUE,
        )
        event = _recovery_event(attempt, timestamp=timestamp)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        candidate.experiment_id,
                    )
                    if (
                        aggregate.experiment.lifecycle
                        is StudioBenchmarkExperimentLifecycle.ACCEPTED
                        and aggregate.experiment.process_owner_id
                        == process_owner_id
                        and self._recovery_event_exists(
                            connection,
                            candidate.experiment_id,
                            event.event_id,
                        )
                    ):
                        connection.execute("COMMIT")
                        return aggregate
                    aggregate = self._validate_recovery_candidate(
                        connection,
                        candidate,
                    )
                    record = aggregate.experiment
                    if record.lifecycle not in {
                        StudioBenchmarkExperimentLifecycle.ACCEPTED,
                        StudioBenchmarkExperimentLifecycle.STARTING,
                    }:
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.requeue_state_invalid",
                            "Benchmark Experiment cannot be safely requeued",
                        )
                    changed_tasks: list[
                        StudioBenchmarkTaskRunRecordV1
                    ] = []
                    for task in aggregate.task_runs:
                        if (
                            record.lifecycle
                            is StudioBenchmarkExperimentLifecycle.ACCEPTED
                        ):
                            if (
                                task.lifecycle
                                is not StudioBenchmarkTaskRunLifecycle.SCHEDULED
                            ):
                                raise StudioBenchmarkConflictError(
                                    "benchmark.recovery.requeue_task_invalid",
                                    "Accepted recovery requires scheduled work",
                                )
                            changed_tasks.append(task)
                            continue
                        if (
                            task.lifecycle
                            is not StudioBenchmarkTaskRunLifecycle.PREPARING
                        ):
                            raise StudioBenchmarkConflictError(
                                "benchmark.recovery.preflight_state_invalid",
                                "Starting recovery requires preflight-only work",
                            )
                        changed = self._reset_starting_task(
                            task,
                            timestamp=timestamp,
                        )
                        self._write_recovery_task(
                            connection,
                            task,
                            changed,
                        )
                        changed_tasks.append(changed)
                    sequence = record.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        candidate.experiment_id,
                        sequence,
                        event,
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'accepted',
                            process_owner_id = ?,
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state = ?
                            AND process_owner_id = ?
                        """,
                        (
                            process_owner_id,
                            sequence,
                            timestamp,
                            candidate.experiment_id,
                            record.lifecycle.value,
                            record.process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.requeue_race",
                            "Benchmark requeue lost its lifecycle CAS race",
                        )
                    self._fail("recovery.requeue.after_transition")
                    self._commit_event_transaction(
                        connection,
                        candidate.experiment_id,
                    )
                    return StudioBenchmarkExperimentAggregate(
                        experiment=record.model_copy(
                            update={
                                "lifecycle": (
                                    StudioBenchmarkExperimentLifecycle.ACCEPTED
                                ),
                                "process_owner_id": process_owner_id,
                                "event_high_water_mark": sequence,
                                "updated_at": timestamp,
                            }
                        ),
                        task_runs=tuple(changed_tasks),
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
            StudioBenchmarkValidationError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.recovery.requeue_failed",
                "Benchmark Experiment could not be requeued safely",
            ) from error

    def recover_interrupt(
        self,
        candidate: StudioBenchmarkRecoveryCandidateV1,
        *,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Interrupt uncertain in-flight work without replaying side effects.

        Args:
            candidate: Previously queried stale aggregate facts.
            timestamp: Unix epoch milliseconds for the decision.

        Raises:
            StudioBenchmarkConflictError: Candidate or lifecycle is stale.
            StudioBenchmarkStorageError: Recovery transaction fails.

        Returns:
            Immutable interrupted aggregate.
        """
        attempt = _recovery_attempt(
            candidate,
            StudioBenchmarkRecoveryDecision.INTERRUPT,
        )
        event = _recovery_event(attempt, timestamp=timestamp)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        candidate.experiment_id,
                    )
                    if (
                        aggregate.experiment.lifecycle
                        is StudioBenchmarkExperimentLifecycle.TERMINAL
                    ):
                        connection.execute("COMMIT")
                        return aggregate
                    aggregate = self._validate_recovery_candidate(
                        connection,
                        candidate,
                    )
                    record = aggregate.experiment
                    if record.lifecycle not in {
                        StudioBenchmarkExperimentLifecycle.RUNNING,
                        StudioBenchmarkExperimentLifecycle.CANCELLING,
                    }:
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.interrupt_state_invalid",
                            "Benchmark Experiment is not uncertain in-flight work",
                        )
                    sequence = record.event_high_water_mark + 1
                    self._append_event(
                        connection,
                        candidate.experiment_id,
                        sequence,
                        event,
                    )
                    terminal_tasks: list[
                        StudioBenchmarkTaskRunRecordV1
                    ] = []
                    for task in aggregate.task_runs:
                        if (
                            task.lifecycle
                            is StudioBenchmarkTaskRunLifecycle.TERMINAL
                        ):
                            terminal_tasks.append(task)
                            continue
                        changed = self._interrupt_recovery_task(
                            task,
                            timestamp=timestamp,
                        )
                        self._write_recovery_task(
                            connection,
                            task,
                            changed,
                        )
                        sequence += 1
                        self._append_event(
                            connection,
                            candidate.experiment_id,
                            sequence,
                            StudioBenchmarkEventDraftV1(
                                event_id=_stable_event_id(
                                    {
                                        "kind": "task_run.terminal",
                                        "experiment": (
                                            candidate.experiment_id
                                        ),
                                        "taskRun": task.task_run_id,
                                    }
                                ),
                                timestamp=timestamp,
                                source=StudioBenchmarkEventSource.SERVICE,
                                kind="task_run.terminal",
                                task_run_id=task.task_run_id,
                                phase="recovery",
                                payload={
                                    "terminalReason": "interrupted",
                                    "resultAvailability": (
                                        changed.result_availability.value
                                    ),
                                },
                            ),
                        )
                        terminal_tasks.append(changed)
                    sequence += 1
                    self._append_event(
                        connection,
                        candidate.experiment_id,
                        sequence,
                        StudioBenchmarkEventDraftV1(
                            event_id=_stable_event_id(
                                {
                                    "kind": "experiment.terminal",
                                    "experiment": candidate.experiment_id,
                                }
                            ),
                            timestamp=timestamp,
                            source=StudioBenchmarkEventSource.SERVICE,
                            kind="experiment.terminal",
                            phase="recovery",
                            payload={"terminalReason": "interrupted"},
                        ),
                    )
                    outcome_availability = (
                        StudioBenchmarkAvailability.AVAILABLE
                        if any(
                            task.outcome_availability
                            is StudioBenchmarkAvailability.AVAILABLE
                            for task in terminal_tasks
                        )
                        else StudioBenchmarkAvailability.NOT_PRODUCED
                    )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'terminal',
                            terminal_reason = 'interrupted',
                            process_owner_id = '',
                            outcome_availability = ?,
                            event_high_water_mark = ?, updated_at = ?,
                            terminal_at = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state = ?
                            AND process_owner_id = ?
                        """,
                        (
                            outcome_availability.value,
                            sequence,
                            timestamp,
                            timestamp,
                            candidate.experiment_id,
                            record.lifecycle.value,
                            record.process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.interrupt_race",
                            "Benchmark interruption lost its lifecycle CAS race",
                        )
                    self._fail("recovery.interrupt.after_terminal")
                    self._commit_event_transaction(
                        connection,
                        candidate.experiment_id,
                    )
                    return StudioBenchmarkExperimentAggregate(
                        experiment=record.model_copy(
                            update={
                                "lifecycle": (
                                    StudioBenchmarkExperimentLifecycle.TERMINAL
                                ),
                                "terminal_reason": (
                                    StudioBenchmarkExperimentTerminalReason
                                    .INTERRUPTED
                                ),
                                "process_owner_id": "",
                                "outcome_availability": outcome_availability,
                                "event_high_water_mark": sequence,
                                "updated_at": timestamp,
                                "terminal_at": timestamp,
                            }
                        ),
                        task_runs=tuple(terminal_tasks),
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.recovery.interrupt_failed",
                "Benchmark in-flight work could not be interrupted safely",
            ) from error

    def claim_finalizing_recovery(
        self,
        candidate: StudioBenchmarkRecoveryCandidateV1,
        *,
        process_owner_id: str,
        decision: StudioBenchmarkRecoveryDecision,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Claim finalizing work and persist its no-execution decision.

        Args:
            candidate: Previously queried stale finalizing aggregate.
            process_owner_id: New executable process owner.
            decision: Publication-only or finalize-only decision.
            timestamp: Unix epoch milliseconds for the decision.

        Raises:
            StudioBenchmarkConflictError: Candidate or classification is stale.
            StudioBenchmarkValidationError: Owner or decision is invalid.
            StudioBenchmarkStorageError: Recovery transaction fails.

        Returns:
            Finalizing aggregate owned by the current process.
        """
        if not process_owner_id.strip():
            raise StudioBenchmarkValidationError(
                "benchmark.recovery.owner_invalid",
                "Benchmark recovery owner must not be blank",
            )
        if decision not in {
            StudioBenchmarkRecoveryDecision.PUBLICATION_ONLY,
            StudioBenchmarkRecoveryDecision.FINALIZE_ONLY,
        }:
            raise StudioBenchmarkValidationError(
                "benchmark.recovery.finalizing_decision_invalid",
                "Benchmark finalizing recovery decision is invalid",
            )
        attempt = _recovery_attempt(candidate, decision)
        event = _recovery_event(attempt, timestamp=timestamp)
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        candidate.experiment_id,
                    )
                    if (
                        aggregate.experiment.lifecycle
                        is StudioBenchmarkExperimentLifecycle.FINALIZING
                        and aggregate.experiment.process_owner_id
                        == process_owner_id
                        and self._recovery_event_exists(
                            connection,
                            candidate.experiment_id,
                            event.event_id,
                        )
                    ):
                        connection.execute("COMMIT")
                        return aggregate
                    aggregate = self._validate_recovery_candidate(
                        connection,
                        candidate,
                    )
                    record = aggregate.experiment
                    if (
                        record.lifecycle
                        is not StudioBenchmarkExperimentLifecycle.FINALIZING
                        or any(
                            task.lifecycle
                            is not StudioBenchmarkTaskRunLifecycle.TERMINAL
                            for task in aggregate.task_runs
                        )
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.finalizing_state_invalid",
                            "Benchmark finalizing recovery facts are invalid",
                        )
                    has_result = any(
                        task.result_availability
                        is StudioBenchmarkAvailability.AVAILABLE
                        and task.result is not None
                        for task in aggregate.task_runs
                    )
                    if (
                        decision
                        is StudioBenchmarkRecoveryDecision.PUBLICATION_ONLY
                        and (
                            not has_result
                            or candidate.publication_committed
                        )
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.publication_state_invalid",
                            "Benchmark publication-only recovery is not needed",
                        )
                    if (
                        decision
                        is StudioBenchmarkRecoveryDecision.FINALIZE_ONLY
                        and has_result
                        and not candidate.publication_committed
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.finalize_state_invalid",
                            "Benchmark result requires publication recovery",
                        )
                    sequence = record.event_high_water_mark
                    latest = connection.execute(
                        "SELECT envelope_json "
                        "FROM studio_benchmark_experiment_events "
                        "WHERE experiment_id = ? AND sequence = ?",
                        (
                            candidate.experiment_id,
                            record.event_high_water_mark,
                        ),
                    ).fetchone()
                    latest_kind = ""
                    if latest is not None:
                        try:
                            latest_kind = str(
                                json.loads(latest["envelope_json"])["kind"]
                            )
                        except (
                            KeyError,
                            TypeError,
                            ValueError,
                            json.JSONDecodeError,
                        ) as error:
                            raise StudioBenchmarkIntegrityError(
                                "benchmark.recovery.event_corrupt",
                                "Stored Benchmark recovery event is invalid",
                            ) from error
                    if latest_kind != event.kind:
                        sequence += 1
                        self._append_event(
                            connection,
                            candidate.experiment_id,
                            sequence,
                            event,
                        )
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET process_owner_id = ?,
                            event_high_water_mark = ?, updated_at = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state = 'finalizing'
                            AND process_owner_id = ?
                        """,
                        (
                            process_owner_id,
                            sequence,
                            timestamp,
                            candidate.experiment_id,
                            record.process_owner_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.recovery.finalizing_race",
                            "Benchmark finalizing recovery lost its CAS race",
                        )
                    self._fail("recovery.finalizing.after_claim")
                    self._commit_event_transaction(
                        connection,
                        candidate.experiment_id,
                    )
                    return StudioBenchmarkExperimentAggregate(
                        experiment=record.model_copy(
                            update={
                                "process_owner_id": process_owner_id,
                                "event_high_water_mark": sequence,
                                "updated_at": timestamp,
                            }
                        ),
                        task_runs=aggregate.task_runs,
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
            StudioBenchmarkValidationError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.recovery.finalizing_failed",
                "Benchmark finalizing work could not be recovered safely",
            ) from error

    def cancel_accepted_experiment(
        self,
        experiment_id: str,
        cancellation: StudioBenchmarkExperimentCancellationV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Atomically terminate one accepted aggregate before execution.

        Args:
            experiment_id: Opaque Experiment identity.
            cancellation: Safe persisted cancellation request.

        Raises:
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkConflictError: Experiment is non-terminal and no
                longer accepted.
            StudioBenchmarkStorageError: Transaction fails.

        Returns:
            Terminal aggregate, or the existing terminal aggregate on retry.
        """
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    aggregate = self._aggregate_in_connection(
                        connection,
                        experiment_id,
                    )
                    record = aggregate.experiment
                    if (
                        record.lifecycle
                        is StudioBenchmarkExperimentLifecycle.TERMINAL
                    ):
                        connection.execute("COMMIT")
                        return aggregate
                    if (
                        record.lifecycle
                        is not StudioBenchmarkExperimentLifecycle.ACCEPTED
                    ):
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.cancel_state_conflict",
                            "Benchmark Experiment can no longer be cancelled "
                            "by the Stage 5.2A service",
                        )
                    sequence = record.event_high_water_mark
                    cancel_event = StudioBenchmarkEventDraftV1(
                        event_id=_stable_event_id(
                            {
                                "kind": "experiment.cancellation_requested",
                                "experiment": experiment_id,
                            }
                        ),
                        timestamp=cancellation.requested_at,
                        kind="experiment.cancellation_requested",
                        payload={
                            "clientRequestId": cancellation.client_request_id,
                            "reasonCode": cancellation.reason_code,
                        },
                    )
                    sequence += 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        cancel_event,
                    )
                    self._fail("cancel.after_request_event")
                    terminal_tasks: list[
                        StudioBenchmarkTaskRunRecordV1
                    ] = []
                    for task in aggregate.task_runs:
                        if (
                            task.lifecycle
                            is not StudioBenchmarkTaskRunLifecycle.SCHEDULED
                        ):
                            raise StudioBenchmarkIntegrityError(
                                "benchmark.task_run.cancel_state_invalid",
                                "Accepted Experiment contains a non-scheduled "
                                "TaskRun",
                            )
                        terminal = task.model_copy(
                            update={
                                "lifecycle": (
                                    StudioBenchmarkTaskRunLifecycle.TERMINAL
                                ),
                                "terminal_reason": (
                                    StudioBenchmarkTaskRunTerminalReason
                                    .CANCELLED_BEFORE_START
                                ),
                                "outcome_availability": (
                                    StudioBenchmarkAvailability.NOT_PRODUCED
                                ),
                                "updated_at": cancellation.requested_at,
                                "terminal_at": cancellation.requested_at,
                            }
                        )
                        terminal = (
                            StudioBenchmarkTaskRunRecordV1.model_validate(
                                terminal.model_dump()
                            )
                        )
                        connection.execute(
                            """
                            UPDATE studio_benchmark_task_runs
                            SET lifecycle_state = ?, terminal_reason = ?,
                                outcome_availability = ?, task_run_json = ?,
                                updated_at = ?, terminal_at = ?
                            WHERE experiment_id = ? AND task_run_id = ?
                                AND lifecycle_state = 'scheduled'
                            """,
                            (
                                terminal.lifecycle.value,
                                terminal.terminal_reason.value,
                                terminal.outcome_availability.value,
                                self._task_json(terminal),
                                terminal.updated_at,
                                terminal.terminal_at,
                                experiment_id,
                                task.task_run_id,
                            ),
                        )
                        if connection.execute(
                            "SELECT changes() AS count"
                        ).fetchone()["count"] != 1:
                            raise StudioBenchmarkConflictError(
                                "benchmark.task_run.cancel_race",
                                "Benchmark TaskRun changed during cancellation",
                            )
                        terminal_tasks.append(terminal)
                        sequence += 1
                        self._append_event(
                            connection,
                            experiment_id,
                            sequence,
                            StudioBenchmarkEventDraftV1(
                                event_id=_stable_event_id(
                                    {
                                        "kind": "task_run.terminal",
                                        "experiment": experiment_id,
                                        "taskRun": task.task_run_id,
                                    }
                                ),
                                timestamp=cancellation.requested_at,
                                kind="task_run.terminal",
                                task_run_id=task.task_run_id,
                                payload={
                                    "terminalReason": (
                                        "cancelled_before_start"
                                    ),
                                    "outcomeAvailability": "not_produced",
                                },
                            ),
                        )
                        self._fail("cancel.after_task_run")
                    sequence += 1
                    self._append_event(
                        connection,
                        experiment_id,
                        sequence,
                        StudioBenchmarkEventDraftV1(
                            event_id=_stable_event_id(
                                {
                                    "kind": "experiment.terminal",
                                    "experiment": experiment_id,
                                }
                            ),
                            timestamp=cancellation.requested_at,
                            kind="experiment.terminal",
                            payload={"terminalReason": "cancelled"},
                        ),
                    )
                    self._fail("cancel.after_terminal_event")
                    connection.execute(
                        """
                        UPDATE studio_benchmark_experiments
                        SET lifecycle_state = 'terminal',
                            terminal_reason = 'cancelled',
                            process_owner_id = '',
                            cancellation_json = ?,
                            event_high_water_mark = ?,
                            updated_at = ?, terminal_at = ?
                        WHERE experiment_id = ?
                            AND lifecycle_state = 'accepted'
                        """,
                        (
                            _json_text(
                                cancellation.model_dump(
                                    mode="json",
                                    by_alias=True,
                                    exclude_none=True,
                                )
                            ),
                            sequence,
                            cancellation.requested_at,
                            cancellation.requested_at,
                            experiment_id,
                        ),
                    )
                    if connection.execute(
                        "SELECT changes() AS count"
                    ).fetchone()["count"] != 1:
                        raise StudioBenchmarkConflictError(
                            "benchmark.experiment.cancel_race",
                            "Benchmark Experiment changed during cancellation",
                    )
                    self._fail("cancel.after_experiment")
                    self._commit_event_transaction(connection, experiment_id)
                    return StudioBenchmarkExperimentAggregate(
                        experiment=StudioBenchmarkExperimentRecordV1(
                            **record.model_dump(
                                exclude={
                                    "lifecycle",
                                    "terminal_reason",
                                    "cancellation",
                                    "process_owner_id",
                                    "event_high_water_mark",
                                    "updated_at",
                                    "terminal_at",
                                }
                            ),
                            lifecycle=StudioBenchmarkExperimentLifecycle.TERMINAL,
                            terminal_reason=(
                                StudioBenchmarkExperimentTerminalReason.CANCELLED
                            ),
                            cancellation=cancellation,
                            process_owner_id="",
                            event_high_water_mark=sequence,
                            updated_at=cancellation.requested_at,
                            terminal_at=cancellation.requested_at,
                        ),
                        task_runs=tuple(terminal_tasks),
                        binding_authority=aggregate.binding_authority,
                    )
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
        except (
            StudioBenchmarkConflictError,
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
        ):
            raise
        except Exception as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment cancellation could not be persisted",
            ) from error

    def list_events(
        self,
        experiment_id: str,
    ) -> tuple[StudioBenchmarkEventEnvelopeV1, ...]:
        """Return all durable aggregate events for contract tests and adapters.

        Stage 5.2A intentionally does not expose this method over HTTP.

        Args:
            experiment_id: Opaque Experiment identity.

        Raises:
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkIntegrityError: Stored event is invalid.
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Continuous strict event envelopes ordered by sequence.
        """
        self.get_experiment(experiment_id)
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT envelope_json FROM "
                    "studio_benchmark_experiment_events "
                    "WHERE experiment_id = ? ORDER BY sequence ASC",
                    (experiment_id,),
                ).fetchall()
            events = tuple(
                StudioBenchmarkEventEnvelopeV1.model_validate(
                    json.loads(row["envelope_json"])
                )
                for row in rows
            )
            if tuple(item.sequence for item in events) != tuple(
                range(1, len(events) + 1)
            ):
                raise ValueError("event sequence gap")
            return events
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.experiment.event_corrupt",
                "Stored Benchmark Experiment journal is invalid",
            ) from error
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment journal query failed",
            ) from error

    def query_events(
        self,
        experiment_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioBenchmarkEventPageV1:
        """Read one bounded continuous page after an exclusive cursor.

        Args:
            experiment_id: Owning Experiment identity.
            after: Exclusive last-confirmed Experiment-local sequence.
            limit: Page size from 1 through 500.

        Raises:
            StudioBenchmarkValidationError: Cursor or limit is invalid.
            StudioBenchmarkNotFoundError: Experiment is absent.
            StudioBenchmarkIntegrityError: Stored journal facts disagree.
            StudioBenchmarkStorageError: SQLite query fails.

        Returns:
            Ordered bounded event page with drain-aware terminal state.
        """
        if (
            type(after) is not int
            or type(limit) is not int
            or after < 0
            or not 1 <= limit <= 500
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.event.cursor_invalid",
                "Benchmark event cursor or limit is invalid",
            )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN")
                row = connection.execute(
                    "SELECT * FROM studio_benchmark_experiments "
                    "WHERE experiment_id = ?",
                    (experiment_id,),
                ).fetchone()
                if row is None:
                    raise StudioBenchmarkNotFoundError(
                        "benchmark.experiment.not_found",
                        "Benchmark Experiment was not found",
                    )
                record = self._experiment_from_row(row)
                stats = connection.execute(
                    """
                    SELECT COUNT(*) AS event_count,
                           COALESCE(MAX(sequence), 0) AS high_water_mark
                    FROM studio_benchmark_experiment_events
                    WHERE experiment_id = ?
                    """,
                    (experiment_id,),
                ).fetchone()
                count = int(stats["event_count"])
                high = int(stats["high_water_mark"])
                if (
                    record.event_high_water_mark != high
                    or count != high
                ):
                    raise StudioBenchmarkIntegrityError(
                        "benchmark.event.journal_corrupt",
                        "Benchmark event journal high-water facts disagree",
                    )
                if after > high:
                    raise StudioBenchmarkValidationError(
                        "benchmark.event.cursor_invalid",
                        "Benchmark event cursor exceeds the high-water mark",
                    )
                rows = connection.execute(
                    """
                    SELECT sequence, event_id, fingerprint, envelope_json
                    FROM studio_benchmark_experiment_events
                    WHERE experiment_id = ? AND sequence > ?
                    ORDER BY sequence ASC
                    LIMIT ?
                    """,
                    (experiment_id, after, limit),
                ).fetchall()
                last_row = connection.execute(
                    """
                    SELECT sequence, event_id, fingerprint, envelope_json
                    FROM studio_benchmark_experiment_events
                    WHERE experiment_id = ?
                    ORDER BY sequence DESC
                    LIMIT 1
                    """,
                    (experiment_id,),
                ).fetchone()
                connection.execute("COMMIT")
            items: list[StudioBenchmarkEventEnvelopeV1] = []
            expected = after + 1
            for event_row in rows:
                envelope = StudioBenchmarkEventEnvelopeV1.model_validate(
                    json.loads(event_row["envelope_json"])
                )
                draft = StudioBenchmarkEventDraftV1.model_validate(
                    envelope.model_dump(
                        exclude={
                            "experiment_id",
                            "sequence",
                            "fingerprint",
                        }
                    )
                )
                if (
                    int(event_row["sequence"]) != expected
                    or envelope.sequence != expected
                    or envelope.experiment_id != experiment_id
                    or event_row["event_id"] != envelope.event_id
                    or event_row["fingerprint"] != envelope.fingerprint
                    or benchmark_event_fingerprint(draft)
                    != envelope.fingerprint
                ):
                    raise StudioBenchmarkIntegrityError(
                        "benchmark.event.journal_corrupt",
                        "Benchmark event journal contains invalid facts",
                    )
                items.append(envelope)
                expected += 1
            cursor = items[-1].sequence if items else after
            last_event = (
                StudioBenchmarkEventEnvelopeV1.model_validate(
                    json.loads(last_row["envelope_json"])
                )
                if last_row is not None
                else None
            )
            if last_event is not None:
                last_draft = StudioBenchmarkEventDraftV1.model_validate(
                    last_event.model_dump(
                        exclude={
                            "experiment_id",
                            "sequence",
                            "fingerprint",
                        }
                    )
                )
                if (
                    int(last_row["sequence"]) != high
                    or last_event.sequence != high
                    or last_event.experiment_id != experiment_id
                    or last_row["event_id"] != last_event.event_id
                    or last_row["fingerprint"] != last_event.fingerprint
                    or benchmark_event_fingerprint(last_draft)
                    != last_event.fingerprint
                ):
                    raise StudioBenchmarkIntegrityError(
                        "benchmark.event.journal_corrupt",
                        "Benchmark event journal high-water facts disagree",
                    )
            terminal_record = (
                record.lifecycle
                is StudioBenchmarkExperimentLifecycle.TERMINAL
            )
            terminal_event = bool(
                last_event is not None
                and last_event.kind == "experiment.terminal"
            )
            if terminal_record != terminal_event:
                raise StudioBenchmarkIntegrityError(
                    "benchmark.event.terminal_corrupt",
                    "Benchmark terminal event facts disagree",
                )
            return StudioBenchmarkEventPageV1(
                experiment_id=experiment_id,
                items=tuple(items),
                next_cursor=cursor,
                high_water_mark=high,
                terminal=(
                    terminal_record
                    and terminal_event
                    and cursor >= high
                ),
            )
        except (
            StudioBenchmarkIntegrityError,
            StudioBenchmarkNotFoundError,
            StudioBenchmarkValidationError,
        ):
            raise
        except (
            TypeError,
            ValueError,
            json.JSONDecodeError,
            ValidationError,
        ) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.event.journal_corrupt",
                "Stored Benchmark Experiment journal is invalid",
            ) from error
        except sqlite3.Error as error:
            raise StudioBenchmarkStorageError(
                "benchmark.experiment.storage_failed",
                "Benchmark Experiment journal query failed",
            ) from error


__all__ = ["SQLiteStudioBenchmarkExperimentRepository"]
