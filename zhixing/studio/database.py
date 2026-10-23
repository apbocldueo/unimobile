"""Shared SQLite connection and monotonic schema migrations for Studio."""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path


STUDIO_SQLITE_SCHEMA_VERSION = 12


def connect_studio_database(database_path: str | Path) -> sqlite3.Connection:
    """Open one configured short-lived Studio SQLite connection.

    Args:
        database_path: Explicit workspace database path.

    Raises:
        sqlite3.Error: Connection or pragma setup fails.

    Returns:
        Row-enabled SQLite connection with foreign keys and a bounded wait.
    """
    connection = sqlite3.connect(
        Path(database_path),
        timeout=5.0,
        isolation_level=None,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def _applied_at_ms() -> int:
    """Return the migration timestamp in Unix epoch milliseconds.

    Returns:
        Integer Unix epoch milliseconds.
    """
    return time.time_ns() // 1_000_000


def migrate_studio_database(database_path: str | Path) -> None:
    """Apply the shared Studio SQLite schema history atomically.

    Migrations 1 through 3 preserve the pre-existing Agent, Replay, and Run
    schema. Migration 4 adds the independent Benchmark Experiment aggregate;
    migration 5 adds its execution and bounded result journal facts. Migration
    6 adds managed Benchmark publication, artifact, and explicit Replay facts.
    Migration 7 adds metadata-only Experiment History query indexes. Migration
    8 adds independent Benchmark authoring draft, immutable revision, and
    idempotent command facts without rewriting earlier resources. Migration 9
    adds immutable successful validation attestations, closed Package revisions,
    ordered frozen members, and idempotent freeze-command facts. Migration 10
    adds managed authoring publication/export authority. Migration 11 adds the
    private one-to-one Experiment device-binding authority without rewriting
    historical Experiments. Migration 12 adds nullable capability-authoring
    policy, lowering, semantic identity, and projection evidence to immutable
    Agent revisions without rewriting schema-2 history.

    Args:
        database_path: Explicit workspace database path.

    Raises:
        OSError: The database parent cannot be created.
        sqlite3.Error: Migration or connection setup fails.
        RuntimeError: The database schema is newer than this build.

    Returns:
        None.
    """
    path = Path(database_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect_studio_database(path) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS studio_schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at INTEGER NOT NULL
                )
                """
            )
            recorded_versions = [
                int(row["version"])
                for row in connection.execute(
                    "SELECT version FROM studio_schema_migrations "
                    "ORDER BY version ASC"
                ).fetchall()
            ]
            if recorded_versions and max(
                recorded_versions
            ) > STUDIO_SQLITE_SCHEMA_VERSION:
                raise RuntimeError(
                    "Studio database schema is newer than this build"
                )
            version = 0
            for candidate in recorded_versions:
                if candidate != version + 1:
                    break
                version = candidate
            if any(candidate > version for candidate in recorded_versions):
                # A transactionally migrated production database cannot have a
                # gap. Treat higher rows/tables as stale historical-fixture or
                # interrupted-development residue and rebuild from the last
                # contiguous contract boundary.
                connection.execute(
                    "DELETE FROM studio_schema_migrations WHERE version > ?",
                    (version,),
                )
            if version < 6:
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_artifacts"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_publications"
                )
            if version < 10:
                # Release metadata is append-only authority. Remove only
                # unregistered development residue in reverse FK order before
                # installing the transactional schema-10 boundary.
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_export_commands"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_package_exports"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_publication_commands"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_package_publications"
                )
            if version < 11:
                # Clean only unregistered development residue. A committed
                # migration always records its version in the same transaction.
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_experiment_bindings"
                )
            if version < 9:
                # Schema-9 tables are append-only authority. Production
                # transactions cannot leave them without the matching migration
                # row; clean only interrupted development residue in reverse
                # foreign-key order.
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_freeze_commands"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS "
                    "studio_benchmark_package_revision_members"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS studio_benchmark_package_revisions"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS "
                    "studio_benchmark_validation_attestations"
                )
            if version < 8:
                # Transactional production migrations cannot leave these tables
                # without version 8. Clean only unregistered development or
                # historical-fixture residue, in foreign-key reverse order.
                connection.execute(
                    "DROP TABLE IF EXISTS "
                    "studio_benchmark_authoring_commands"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS "
                    "studio_benchmark_authoring_revisions"
                )
                connection.execute(
                    "DROP TABLE IF EXISTS "
                    "studio_benchmark_authoring_drafts"
                )
            if version < 1:
                connection.execute(
                    """
                    CREATE TABLE studio_agents (
                        agent_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        current_revision_id TEXT,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_agent_revisions (
                        revision_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        ordinal INTEGER NOT NULL,
                        parent_revision_id TEXT,
                        document_json TEXT NOT NULL,
                        compile_status TEXT NOT NULL
                            CHECK (compile_status IN ('valid', 'invalid')),
                        diagnostics_json TEXT NOT NULL,
                        source_map_json TEXT NOT NULL,
                        agent_graph_json TEXT,
                        canonical_hash TEXT,
                        created_at INTEGER NOT NULL,
                        UNIQUE (agent_id, ordinal),
                        FOREIGN KEY (agent_id)
                            REFERENCES studio_agents(agent_id)
                            ON DELETE CASCADE,
                        FOREIGN KEY (parent_revision_id)
                            REFERENCES studio_agent_revisions(revision_id),
                        CHECK (
                            (compile_status = 'valid'
                                AND agent_graph_json IS NOT NULL
                                AND canonical_hash IS NOT NULL)
                            OR
                            (compile_status = 'invalid'
                                AND agent_graph_json IS NULL
                                AND canonical_hash IS NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_agent_revisions_agent_created
                    ON studio_agent_revisions(agent_id, ordinal DESC)
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (1, _applied_at_ms()),
                )
            if version < 2:
                connection.execute(
                    """
                    CREATE TABLE studio_replays (
                        run_id TEXT PRIMARY KEY,
                        agent_id TEXT NOT NULL,
                        agent_status TEXT NOT NULL,
                        benchmark_outcome TEXT,
                        provenance TEXT NOT NULL,
                        integrity_state TEXT NOT NULL
                            CHECK (integrity_state IN (
                                'complete', 'partial', 'corrupt'
                            )),
                        evidence_completeness INTEGER NOT NULL
                            CHECK (
                                evidence_completeness >= 0
                                AND evidence_completeness <= 100
                            ),
                        imported_at INTEGER NOT NULL,
                        envelope_json TEXT NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_replays_imported
                    ON studio_replays(imported_at DESC, run_id ASC)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_replay_moments (
                        run_id TEXT NOT NULL,
                        causal_index INTEGER NOT NULL,
                        moment_id TEXT NOT NULL,
                        source_kind TEXT NOT NULL,
                        source_sequence INTEGER,
                        phase TEXT NOT NULL,
                        kind TEXT NOT NULL,
                        node_path TEXT NOT NULL,
                        activation_id TEXT NOT NULL,
                        interaction_step INTEGER NOT NULL,
                        moment_json TEXT NOT NULL,
                        PRIMARY KEY (run_id, causal_index),
                        UNIQUE (run_id, moment_id),
                        FOREIGN KEY (run_id)
                            REFERENCES studio_replays(run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_replay_moments_activation
                    ON studio_replay_moments(
                        run_id, node_path, activation_id, causal_index
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_replay_artifacts (
                        run_id TEXT NOT NULL,
                        artifact_id TEXT NOT NULL,
                        availability TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        sha256 TEXT,
                        storage_ref TEXT NOT NULL,
                        descriptor_json TEXT NOT NULL,
                        PRIMARY KEY (run_id, artifact_id),
                        FOREIGN KEY (run_id)
                            REFERENCES studio_replays(run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (2, _applied_at_ms()),
                )
            if version < 3:
                connection.execute(
                    """
                    CREATE TABLE studio_runs (
                        run_id TEXT PRIMARY KEY,
                        client_request_id TEXT NOT NULL UNIQUE,
                        request_fingerprint TEXT NOT NULL,
                        agent_id TEXT NOT NULL,
                        revision_id TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        lifecycle_state TEXT NOT NULL
                            CHECK (lifecycle_state IN (
                                'accepted', 'starting', 'running',
                                'cancelling', 'terminal'
                            )),
                        cancellation_requested INTEGER NOT NULL DEFAULT 0
                            CHECK (cancellation_requested IN (0, 1)),
                        process_owner_id TEXT NOT NULL,
                        accepted_at INTEGER NOT NULL,
                        started_at INTEGER,
                        updated_at INTEGER NOT NULL,
                        terminal_at INTEGER,
                        result_json TEXT,
                        replay_availability TEXT NOT NULL
                            CHECK (replay_availability IN (
                                'available', 'not_captured', 'excluded',
                                'hidden', 'missing', 'corrupt', 'redacted',
                                'truncated'
                            )),
                        replay_error_code TEXT NOT NULL DEFAULT '',
                        storage_warnings_json TEXT NOT NULL DEFAULT '[]',
                        FOREIGN KEY (agent_id)
                            REFERENCES studio_agents(agent_id),
                        FOREIGN KEY (revision_id)
                            REFERENCES studio_agent_revisions(revision_id),
                        CHECK (
                            (lifecycle_state = 'terminal'
                                AND terminal_at IS NOT NULL
                                AND result_json IS NOT NULL)
                            OR
                            (lifecycle_state != 'terminal'
                                AND terminal_at IS NULL
                                AND result_json IS NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_runs_lifecycle_owner
                    ON studio_runs(
                        lifecycle_state, process_owner_id, accepted_at
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_run_events (
                        run_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL CHECK (sequence >= 1),
                        event_id TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        envelope_json TEXT NOT NULL,
                        PRIMARY KEY (run_id, sequence),
                        UNIQUE (run_id, event_id),
                        FOREIGN KEY (run_id)
                            REFERENCES studio_runs(run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_run_events_identity
                    ON studio_run_events(run_id, event_id)
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_run_artifacts (
                        run_id TEXT NOT NULL,
                        artifact_id TEXT NOT NULL,
                        availability TEXT NOT NULL,
                        content_type TEXT NOT NULL,
                        size INTEGER NOT NULL CHECK (size >= 0),
                        sha256 TEXT,
                        hidden INTEGER NOT NULL CHECK (hidden IN (0, 1)),
                        storage_ref TEXT NOT NULL,
                        descriptor_json TEXT NOT NULL,
                        PRIMARY KEY (run_id, artifact_id),
                        UNIQUE (storage_ref),
                        FOREIGN KEY (run_id)
                            REFERENCES studio_runs(run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (3, _applied_at_ms()),
                )
            if version < 4:
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_experiments (
                        experiment_id TEXT PRIMARY KEY,
                        client_request_id TEXT NOT NULL UNIQUE,
                        request_fingerprint TEXT NOT NULL,
                        request_json TEXT NOT NULL,
                        snapshot_json TEXT NOT NULL,
                        lifecycle_state TEXT NOT NULL
                            CHECK (lifecycle_state IN (
                                'accepted', 'starting', 'running',
                                'cancelling', 'finalizing', 'terminal'
                            )),
                        terminal_reason TEXT
                            CHECK (
                                terminal_reason IS NULL
                                OR terminal_reason IN (
                                    'completed', 'cancelled',
                                    'failed', 'interrupted'
                                )
                            ),
                        cancellation_json TEXT,
                        outcome_availability TEXT NOT NULL
                            CHECK (outcome_availability IN (
                                'not_produced', 'available'
                            )),
                        report_availability TEXT NOT NULL
                            CHECK (report_availability IN (
                                'not_produced', 'available'
                            )),
                        replay_availability TEXT NOT NULL
                            CHECK (replay_availability IN (
                                'not_produced', 'available'
                            )),
                        event_high_water_mark INTEGER NOT NULL
                            CHECK (event_high_water_mark >= 0),
                        process_owner_id TEXT NOT NULL DEFAULT '',
                        accepted_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        terminal_at INTEGER,
                        CHECK (
                            (lifecycle_state = 'terminal'
                                AND terminal_reason IS NOT NULL
                                AND terminal_at IS NOT NULL)
                            OR
                            (lifecycle_state != 'terminal'
                                AND terminal_reason IS NULL
                                AND terminal_at IS NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_experiments_lifecycle
                    ON studio_benchmark_experiments(
                        lifecycle_state, accepted_at, experiment_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_task_runs (
                        task_run_id TEXT PRIMARY KEY,
                        experiment_id TEXT NOT NULL,
                        planned_entry_id TEXT NOT NULL,
                        schedule_order INTEGER NOT NULL
                            CHECK (schedule_order >= 0),
                        agent_id TEXT NOT NULL,
                        revision_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        repeat_index INTEGER NOT NULL
                            CHECK (repeat_index >= 0),
                        derived_seed INTEGER NOT NULL,
                        lifecycle_state TEXT NOT NULL
                            CHECK (lifecycle_state IN (
                                'scheduled', 'starting', 'running',
                                'cancelling', 'terminal'
                            )),
                        terminal_reason TEXT
                            CHECK (
                                terminal_reason IS NULL
                                OR terminal_reason IN (
                                    'completed', 'cancelled_before_start',
                                    'cancelled', 'failed', 'interrupted'
                                )
                            ),
                        outcome_availability TEXT NOT NULL
                            CHECK (outcome_availability IN (
                                'not_produced', 'available'
                            )),
                        task_run_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        terminal_at INTEGER,
                        UNIQUE (experiment_id, planned_entry_id),
                        UNIQUE (experiment_id, schedule_order, task_run_id),
                        FOREIGN KEY (experiment_id)
                            REFERENCES studio_benchmark_experiments(experiment_id)
                            ON DELETE CASCADE,
                        CHECK (
                            (lifecycle_state = 'terminal'
                                AND terminal_reason IS NOT NULL
                                AND terminal_at IS NOT NULL)
                            OR
                            (lifecycle_state != 'terminal'
                                AND terminal_reason IS NULL
                                AND terminal_at IS NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_task_runs_order
                    ON studio_benchmark_task_runs(
                        experiment_id, schedule_order, task_run_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_experiment_events (
                        experiment_id TEXT NOT NULL,
                        sequence INTEGER NOT NULL CHECK (sequence >= 1),
                        event_id TEXT NOT NULL,
                        fingerprint TEXT NOT NULL,
                        envelope_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (experiment_id, sequence),
                        UNIQUE (experiment_id, event_id),
                        FOREIGN KEY (experiment_id)
                            REFERENCES studio_benchmark_experiments(experiment_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_experiment_events_identity
                    ON studio_benchmark_experiment_events(
                        experiment_id, event_id
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (4, _applied_at_ms()),
                )
            if version < 5:
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_experiment_events
                    ADD COLUMN source TEXT NOT NULL DEFAULT 'service'
                    """
                )
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_experiment_events
                    ADD COLUMN source_sequence INTEGER
                    """
                )
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_experiment_events
                    ADD COLUMN phase TEXT NOT NULL DEFAULT ''
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_task_runs_v5 (
                        task_run_id TEXT PRIMARY KEY,
                        experiment_id TEXT NOT NULL,
                        planned_entry_id TEXT NOT NULL,
                        schedule_order INTEGER NOT NULL
                            CHECK (schedule_order >= 0),
                        agent_id TEXT NOT NULL,
                        revision_id TEXT NOT NULL,
                        task_id TEXT NOT NULL,
                        repeat_index INTEGER NOT NULL
                            CHECK (repeat_index >= 0),
                        derived_seed INTEGER NOT NULL,
                        lifecycle_state TEXT NOT NULL
                            CHECK (lifecycle_state IN (
                                'scheduled', 'preparing', 'running',
                                'evaluating', 'cleaning_up', 'terminal',
                                'starting', 'cancelling'
                            )),
                        terminal_reason TEXT
                            CHECK (
                                terminal_reason IS NULL
                                OR terminal_reason IN (
                                    'completed', 'cancelled_before_start',
                                    'cancelled', 'failed', 'interrupted'
                                )
                            ),
                        process_owner_id TEXT NOT NULL DEFAULT '',
                        core_task_run_id TEXT,
                        agent_run_id TEXT,
                        task_instance_identity TEXT,
                        phase_results_json TEXT NOT NULL DEFAULT '[]',
                        agent_status TEXT,
                        benchmark_outcome TEXT,
                        evaluation_json TEXT,
                        task_instance_availability TEXT NOT NULL
                            DEFAULT 'not_produced'
                            CHECK (task_instance_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        phase_availability TEXT NOT NULL
                            DEFAULT 'not_produced'
                            CHECK (phase_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        agent_status_availability TEXT NOT NULL
                            DEFAULT 'not_produced'
                            CHECK (agent_status_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        outcome_availability TEXT NOT NULL
                            CHECK (outcome_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        result_availability TEXT NOT NULL DEFAULT 'not_produced'
                            CHECK (result_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        evaluation_availability TEXT NOT NULL
                            DEFAULT 'not_produced'
                            CHECK (evaluation_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        replay_availability TEXT NOT NULL DEFAULT 'not_produced'
                            CHECK (replay_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        result_json TEXT,
                        result_fingerprint TEXT,
                        task_run_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL,
                        started_at INTEGER,
                        evaluating_at INTEGER,
                        cleaning_up_at INTEGER,
                        terminal_at INTEGER,
                        UNIQUE (experiment_id, planned_entry_id),
                        UNIQUE (experiment_id, schedule_order, task_run_id),
                        FOREIGN KEY (experiment_id)
                            REFERENCES studio_benchmark_experiments(experiment_id)
                            ON DELETE CASCADE,
                        CHECK (
                            (lifecycle_state = 'terminal'
                                AND terminal_reason IS NOT NULL
                                AND terminal_at IS NOT NULL)
                            OR
                            (lifecycle_state != 'terminal'
                                AND terminal_reason IS NULL
                                AND terminal_at IS NULL)
                        ),
                        CHECK (
                            (result_json IS NULL
                                AND result_fingerprint IS NULL)
                            OR
                            (result_json IS NOT NULL
                                AND result_fingerprint IS NOT NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT INTO studio_benchmark_task_runs_v5 (
                        task_run_id, experiment_id, planned_entry_id,
                        schedule_order, agent_id, revision_id, task_id,
                        repeat_index, derived_seed, lifecycle_state,
                        terminal_reason, outcome_availability, task_run_json,
                        created_at, updated_at, terminal_at
                    )
                    SELECT
                        task_run_id, experiment_id, planned_entry_id,
                        schedule_order, agent_id, revision_id, task_id,
                        repeat_index, derived_seed, lifecycle_state,
                        terminal_reason, outcome_availability, task_run_json,
                        created_at, updated_at, terminal_at
                    FROM studio_benchmark_task_runs
                    """
                )
                connection.execute("DROP TABLE studio_benchmark_task_runs")
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_task_runs_v5
                    RENAME TO studio_benchmark_task_runs
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_task_runs_order
                    ON studio_benchmark_task_runs(
                        experiment_id, schedule_order, task_run_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_task_runs_owner_state
                    ON studio_benchmark_task_runs(
                        process_owner_id, lifecycle_state,
                        experiment_id, schedule_order
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE UNIQUE INDEX
                    studio_benchmark_experiment_terminal_event
                    ON studio_benchmark_experiment_events(experiment_id)
                    WHERE json_extract(
                        envelope_json, '$.kind'
                    ) = 'experiment.terminal'
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (5, _applied_at_ms()),
                )
            if version < 6:
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_task_runs
                    ADD COLUMN report_availability TEXT NOT NULL
                        DEFAULT 'not_produced'
                        CHECK (report_availability IN (
                            'pending', 'not_produced', 'available', 'failed'
                        ))
                    """
                )
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_task_runs
                    ADD COLUMN trajectory_availability TEXT NOT NULL
                        DEFAULT 'not_produced'
                        CHECK (trajectory_availability IN (
                            'pending', 'not_produced', 'available', 'failed'
                        ))
                    """
                )
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_task_runs
                    ADD COLUMN bundle_availability TEXT NOT NULL
                        DEFAULT 'not_produced'
                        CHECK (bundle_availability IN (
                            'pending', 'not_produced', 'available', 'failed'
                        ))
                    """
                )
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_task_runs
                    ADD COLUMN replay_id TEXT
                    """
                )
                connection.execute(
                    """
                    ALTER TABLE studio_benchmark_task_runs
                    ADD COLUMN publication_diagnostics_json TEXT NOT NULL
                        DEFAULT '[]'
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_publications (
                        experiment_id TEXT PRIMARY KEY,
                        task_run_id TEXT NOT NULL,
                        publication_fingerprint TEXT NOT NULL UNIQUE,
                        preparation_fingerprint TEXT NOT NULL,
                        preparation_availability TEXT NOT NULL
                            CHECK (preparation_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        report_availability TEXT NOT NULL
                            CHECK (report_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        trajectory_availability TEXT NOT NULL
                            CHECK (trajectory_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        bundle_availability TEXT NOT NULL
                            CHECK (bundle_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        replay_availability TEXT NOT NULL
                            CHECK (replay_availability IN (
                                'pending', 'not_produced',
                                'available', 'failed'
                            )),
                        report_artifact_id TEXT,
                        bundle_artifact_id TEXT,
                        replay_id TEXT,
                        artifact_ids_json TEXT NOT NULL,
                        diagnostics_json TEXT NOT NULL,
                        journal_high_water_mark INTEGER NOT NULL
                            CHECK (journal_high_water_mark >= 0),
                        published_at INTEGER NOT NULL,
                        publication_json TEXT NOT NULL,
                        FOREIGN KEY (experiment_id)
                            REFERENCES studio_benchmark_experiments(experiment_id)
                            ON DELETE CASCADE,
                        FOREIGN KEY (task_run_id)
                            REFERENCES studio_benchmark_task_runs(task_run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE UNIQUE INDEX
                    studio_benchmark_publications_replay
                    ON studio_benchmark_publications(replay_id)
                    WHERE replay_id IS NOT NULL
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_artifacts (
                        experiment_id TEXT NOT NULL,
                        artifact_id TEXT NOT NULL,
                        task_run_id TEXT,
                        kind TEXT NOT NULL,
                        availability TEXT NOT NULL
                            CHECK (availability IN (
                                'pending', 'not_produced', 'available',
                                'excluded', 'hidden', 'missing', 'corrupt',
                                'failed', 'redacted', 'truncated'
                            )),
                        content_type TEXT NOT NULL,
                        size INTEGER NOT NULL CHECK (size >= 0),
                        sha256 TEXT,
                        provenance TEXT NOT NULL,
                        causal_identity TEXT NOT NULL,
                        hidden INTEGER NOT NULL CHECK (hidden IN (0, 1)),
                        storage_ref TEXT NOT NULL,
                        descriptor_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (experiment_id, artifact_id),
                        FOREIGN KEY (experiment_id)
                            REFERENCES studio_benchmark_experiments(experiment_id)
                            ON DELETE CASCADE,
                        FOREIGN KEY (task_run_id)
                            REFERENCES studio_benchmark_task_runs(task_run_id)
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_artifacts_task
                    ON studio_benchmark_artifacts(
                        experiment_id, task_run_id, artifact_id
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (6, _applied_at_ms()),
                )
            if version < 7:
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    studio_benchmark_experiments_history_order
                    ON studio_benchmark_experiments(
                        accepted_at DESC, experiment_id DESC
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    studio_benchmark_experiments_catalog_history
                    ON studio_benchmark_experiments(
                        json_extract(
                            snapshot_json, '$.source.catalogEntryId'
                        ),
                        accepted_at DESC,
                        experiment_id DESC
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX IF NOT EXISTS
                    studio_benchmark_task_runs_agent_experiment
                    ON studio_benchmark_task_runs(
                        agent_id, experiment_id
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (7, _applied_at_ms()),
                )
            if version < 8:
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_authoring_drafts (
                        draft_id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        current_revision_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        updated_at INTEGER NOT NULL
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_authoring_revisions (
                        revision_id TEXT PRIMARY KEY,
                        draft_id TEXT NOT NULL,
                        ordinal INTEGER NOT NULL CHECK (ordinal >= 1),
                        parent_revision_id TEXT,
                        document_json TEXT NOT NULL,
                        document_fingerprint TEXT NOT NULL,
                        provenance_json TEXT NOT NULL,
                        status TEXT NOT NULL
                            CHECK (status = 'unvalidated'),
                        created_at INTEGER NOT NULL,
                        UNIQUE (draft_id, ordinal),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (parent_revision_id)
                            REFERENCES studio_benchmark_authoring_revisions(
                                revision_id
                            ),
                        CHECK (
                            (ordinal = 1 AND parent_revision_id IS NULL)
                            OR
                            (ordinal > 1 AND parent_revision_id IS NOT NULL)
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX
                    studio_benchmark_authoring_drafts_updated
                    ON studio_benchmark_authoring_drafts(
                        updated_at DESC, draft_id ASC
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX
                    studio_benchmark_authoring_revisions_draft_ordinal
                    ON studio_benchmark_authoring_revisions(
                        draft_id, ordinal DESC
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_authoring_commands (
                        command_scope TEXT NOT NULL,
                        client_request_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        draft_id TEXT NOT NULL,
                        revision_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (command_scope, client_request_id),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (revision_id)
                            REFERENCES studio_benchmark_authoring_revisions(
                                revision_id
                            )
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (8, _applied_at_ms()),
                )
            if version < 9:
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_validation_attestations (
                        attestation_id TEXT PRIMARY KEY,
                        draft_id TEXT NOT NULL,
                        authoring_revision_id TEXT NOT NULL,
                        document_fingerprint TEXT NOT NULL,
                        validation_contract_version TEXT NOT NULL,
                        package_identity TEXT NOT NULL,
                        package_content_identity TEXT NOT NULL,
                        attestation_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (authoring_revision_id)
                            REFERENCES studio_benchmark_authoring_revisions(
                                revision_id
                            )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX
                    studio_benchmark_validation_attestations_revision
                    ON studio_benchmark_validation_attestations(
                        draft_id, authoring_revision_id, created_at,
                        attestation_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_package_revisions (
                        package_revision_id TEXT PRIMARY KEY,
                        draft_id TEXT NOT NULL,
                        authoring_revision_id TEXT NOT NULL,
                        attestation_id TEXT NOT NULL UNIQUE,
                        package_identity TEXT NOT NULL,
                        package_content_identity TEXT NOT NULL,
                        closure_identity TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (authoring_revision_id)
                            REFERENCES studio_benchmark_authoring_revisions(
                                revision_id
                            ),
                        FOREIGN KEY (attestation_id)
                            REFERENCES studio_benchmark_validation_attestations(
                                attestation_id
                            )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_package_revisions_revision
                    ON studio_benchmark_package_revisions(
                        draft_id, authoring_revision_id, created_at,
                        package_revision_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_package_revision_members (
                        package_revision_id TEXT NOT NULL,
                        ordinal INTEGER NOT NULL CHECK (ordinal >= 0),
                        member_path TEXT NOT NULL,
                        descriptor_json TEXT NOT NULL,
                        PRIMARY KEY (package_revision_id, ordinal),
                        UNIQUE (package_revision_id, member_path),
                        FOREIGN KEY (package_revision_id)
                            REFERENCES studio_benchmark_package_revisions(
                                package_revision_id
                            )
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_freeze_commands (
                        draft_id TEXT NOT NULL,
                        client_request_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        package_revision_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (draft_id, client_request_id),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (package_revision_id)
                            REFERENCES studio_benchmark_package_revisions(
                                package_revision_id
                            )
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (9, _applied_at_ms()),
                )
            if version < 10:
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_package_publications (
                        publication_id TEXT PRIMARY KEY,
                        draft_id TEXT NOT NULL,
                        package_revision_id TEXT NOT NULL,
                        package_identity TEXT NOT NULL UNIQUE,
                        package_content_identity TEXT NOT NULL,
                        closure_identity TEXT NOT NULL,
                        catalog_entry_id TEXT NOT NULL UNIQUE,
                        managed_locator TEXT NOT NULL UNIQUE,
                        publication_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        UNIQUE (
                            package_identity,
                            package_content_identity,
                            closure_identity
                        ),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (package_revision_id)
                            REFERENCES studio_benchmark_package_revisions(
                                package_revision_id
                            )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_package_publications_owner
                    ON studio_benchmark_package_publications(
                        draft_id, package_revision_id, created_at,
                        publication_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_publication_commands (
                        draft_id TEXT NOT NULL,
                        client_request_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        requested_package_revision_id TEXT NOT NULL,
                        publication_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (draft_id, client_request_id),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (requested_package_revision_id)
                            REFERENCES studio_benchmark_package_revisions(
                                package_revision_id
                            ),
                        FOREIGN KEY (publication_id)
                            REFERENCES studio_benchmark_package_publications(
                                publication_id
                            )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_package_exports (
                        export_id TEXT PRIMARY KEY,
                        draft_id TEXT NOT NULL,
                        package_revision_id TEXT NOT NULL,
                        export_contract_version TEXT NOT NULL,
                        archive_size INTEGER NOT NULL CHECK (archive_size > 0),
                        archive_sha256 TEXT NOT NULL,
                        archive_locator TEXT NOT NULL UNIQUE,
                        export_json TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        UNIQUE (package_revision_id, export_contract_version),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (package_revision_id)
                            REFERENCES studio_benchmark_package_revisions(
                                package_revision_id
                            )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE INDEX studio_benchmark_package_exports_owner
                    ON studio_benchmark_package_exports(
                        draft_id, package_revision_id, created_at, export_id
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_export_commands (
                        draft_id TEXT NOT NULL,
                        client_request_id TEXT NOT NULL,
                        request_fingerprint TEXT NOT NULL,
                        requested_package_revision_id TEXT NOT NULL,
                        export_id TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        PRIMARY KEY (draft_id, client_request_id),
                        FOREIGN KEY (draft_id)
                            REFERENCES studio_benchmark_authoring_drafts(
                                draft_id
                            )
                            ON DELETE CASCADE,
                        FOREIGN KEY (requested_package_revision_id)
                            REFERENCES studio_benchmark_package_revisions(
                                package_revision_id
                            ),
                        FOREIGN KEY (export_id)
                            REFERENCES studio_benchmark_package_exports(
                                export_id
                            )
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (10, _applied_at_ms()),
                )
            if version < 11:
                connection.execute(
                    """
                    CREATE TABLE studio_benchmark_experiment_bindings (
                        experiment_id TEXT PRIMARY KEY,
                        profile_id TEXT NOT NULL,
                        binding_fingerprint TEXT NOT NULL,
                        environment_candidate TEXT NOT NULL
                            CHECK (environment_candidate IN (
                                'real_android', 'fake_device'
                            )),
                        created_at INTEGER NOT NULL,
                        FOREIGN KEY (experiment_id)
                            REFERENCES studio_benchmark_experiments(
                                experiment_id
                            )
                            ON DELETE CASCADE
                    )
                    """
                )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (11, _applied_at_ms()),
                )
            if version < 12:
                existing_columns = {
                    str(row["name"])
                    for row in connection.execute(
                        "PRAGMA table_info(studio_agent_revisions)"
                    ).fetchall()
                }
                additions = (
                    ("authoring_policy", "TEXT"),
                    ("lowering_profile", "TEXT"),
                    ("capability_hash", "TEXT"),
                    ("projection_map_json", "TEXT"),
                )
                for column, column_type in additions:
                    if column not in existing_columns:
                        connection.execute(
                            f"ALTER TABLE studio_agent_revisions "
                            f"ADD COLUMN {column} {column_type}"
                        )
                connection.execute(
                    "INSERT INTO studio_schema_migrations(version, applied_at) "
                    "VALUES (?, ?)",
                    (12, _applied_at_ms()),
                )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise


__all__ = [
    "STUDIO_SQLITE_SCHEMA_VERSION",
    "connect_studio_database",
    "migrate_studio_database",
]
