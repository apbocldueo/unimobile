"""Durability and privacy tests for private Benchmark device authority."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from zhixing.studio.benchmark_errors import StudioBenchmarkStorageError
from zhixing.studio.device_profiles import AndroidDeviceProfileResolver
from zhixing.studio.benchmark_experiment_protocols import (
    StudioBenchmarkExperimentAggregate,
)
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)

from .test_benchmark_experiment_resource import _resource_service


def _aggregate(
    repository: SQLiteStudioBenchmarkExperimentRepository,
    experiment_id: str,
) -> StudioBenchmarkExperimentAggregate:
    """Read one internal aggregate for private-authority assertions.

    Args:
        repository: Concrete test repository.
        experiment_id: Owning Experiment identity.

    Raises:
        StudioBenchmarkError: Durable facts are absent or invalid.

    Returns:
        Internal aggregate including private binding authority.
    """
    with repository._connect() as connection:
        return repository._aggregate_in_connection(connection, experiment_id)


def test_binding_commit_is_atomic_with_the_accepted_aggregate(
    tmp_path: Path,
) -> None:
    """Roll back Experiment, TaskRun, event, and binding on the final hook."""
    service, repository, payload = _resource_service(
        tmp_path,
        failure_step="create.after_binding",
    )
    with pytest.raises(StudioBenchmarkStorageError):
        service.create_experiment(payload)
    with sqlite3.connect(repository.database_path) as connection:
        for table in (
            "studio_benchmark_experiments",
            "studio_benchmark_task_runs",
            "studio_benchmark_experiment_events",
            "studio_benchmark_experiment_bindings",
        ):
            count = connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - trusted fixture table
            ).fetchone()[0]
            assert count == 0


def test_retry_returns_original_authority_after_profile_removal(
    tmp_path: Path,
) -> None:
    """Resolve committed idempotency before consulting current profiles."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload)
    aggregate = _aggregate(repository, created.experiment.experiment_id)
    assert aggregate.binding_authority is not None
    original = aggregate.binding_authority
    service.definitions.profiles = AndroidDeviceProfileResolver()
    retried = service.create_experiment(payload)
    restarted = _aggregate(repository, created.experiment.experiment_id)
    assert retried.created is False
    assert restarted.binding_authority == original


def test_binding_table_is_private_minimal_and_public_json_has_no_authority(
    tmp_path: Path,
) -> None:
    """Persist equality authority only in the private schema-11 table."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    with sqlite3.connect(repository.database_path) as connection:
        connection.row_factory = sqlite3.Row
        columns = {
            row["name"]
            for row in connection.execute(
                "PRAGMA table_info(studio_benchmark_experiment_bindings)"
            ).fetchall()
        }
        assert columns == {
            "experiment_id",
            "profile_id",
            "binding_fingerprint",
            "environment_candidate",
            "created_at",
        }
        binding = connection.execute(
            "SELECT * FROM studio_benchmark_experiment_bindings "
            "WHERE experiment_id = ?",
            (created.experiment_id,),
        ).fetchone()
        assert binding is not None
        serial_canary = "/private/serial-must-not-leak"
        assert binding["binding_fingerprint"] != serial_canary
        assert serial_canary not in binding["binding_fingerprint"]
        public_rows = connection.execute(
            "SELECT request_json, snapshot_json FROM "
            "studio_benchmark_experiments WHERE experiment_id = ?",
            (created.experiment_id,),
        ).fetchone()
        assert public_rows is not None
        public_text = "".join(str(value) for value in public_rows)
        assert serial_canary not in public_text
        assert binding["binding_fingerprint"] not in public_text


def test_historical_row_without_binding_remains_publicly_readable(
    tmp_path: Path,
) -> None:
    """Keep historical resource queries readable without synthesizing authority."""
    service, repository, payload = _resource_service(tmp_path)
    created = service.create_experiment(payload).experiment
    with sqlite3.connect(repository.database_path) as connection:
        connection.execute(
            "DELETE FROM studio_benchmark_experiment_bindings "
            "WHERE experiment_id = ?",
            (created.experiment_id,),
        )
    assert service.get_experiment(created.experiment_id).experiment_id == (
        created.experiment_id
    )
    aggregate = _aggregate(repository, created.experiment_id)
    assert aggregate.binding_authority is None
