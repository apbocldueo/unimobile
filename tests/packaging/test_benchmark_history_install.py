"""Clean-wheel acceptance for filtered Studio Benchmark Experiment History."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tests.studio.test_benchmark_experiment_resource import _resource_service
from tests.studio.test_benchmark_reporting_resource import _create_experiment


@pytest.mark.packaging_acceptance
def test_installed_wheel_upgrades_and_filters_benchmark_history(
    isolated_install: tuple[Path, Path, dict[str, str]],
) -> None:
    """Upgrade a populated schema-6 fixture and query it from site-packages.

    Args:
        isolated_install: Isolated Python, unrelated working directory, and
            clean subprocess environment containing the built wheel.

    Raises:
        AssertionError: Fixture preparation, migration, import isolation, or
            filtered History behavior fails.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    scenario = workdir / "benchmark-history"
    scenario.mkdir()
    service, _repository, payload = _resource_service(scenario)
    experiment_id = _create_experiment(service, payload, 1)
    database = scenario / "studio.sqlite3"
    catalog_entry_id = "installed-history-catalog"
    agent_id = "installed-history-agent"
    history_indexes = (
        "studio_benchmark_experiments_history_order",
        "studio_benchmark_experiments_catalog_history",
        "studio_benchmark_task_runs_agent_experiment",
    )

    with sqlite3.connect(database) as connection:
        experiment_row = connection.execute(
            "SELECT snapshot_json FROM studio_benchmark_experiments "
            "WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        assert experiment_row is not None
        snapshot = json.loads(experiment_row[0])
        snapshot["source"]["catalogEntryId"] = catalog_entry_id
        snapshot["agentSnapshots"][0]["agentId"] = agent_id
        connection.execute(
            "UPDATE studio_benchmark_experiments "
            "SET snapshot_json = ?, lifecycle_state = 'running', "
            "accepted_at = 1234, updated_at = 1234 "
            "WHERE experiment_id = ?",
            (
                json.dumps(
                    snapshot,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                experiment_id,
            ),
        )
        task_row = connection.execute(
            "SELECT task_run_id, task_run_json "
            "FROM studio_benchmark_task_runs WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        assert task_row is not None
        task_run = json.loads(task_row[1])
        task_run["agentId"] = agent_id
        connection.execute(
            "UPDATE studio_benchmark_task_runs "
            "SET agent_id = ?, task_run_json = ? WHERE task_run_id = ?",
            (
                agent_id,
                json.dumps(
                    task_run,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                task_row[0],
            ),
        )
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version >= 7"
        )
        for index_name in history_indexes:
            connection.execute(f"DROP INDEX {index_name}")

    script = """
import pathlib
import sqlite3
import sys

import zhixing
from zhixing.studio.benchmark_experiment_models import (
    StudioBenchmarkExperimentHistoryFilterV1,
)
from zhixing.studio.benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from zhixing.studio.database import migrate_studio_database

database = pathlib.Path(sys.argv[1])
experiment_id = sys.argv[2]
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(
    pathlib.Path(sys.prefix).resolve()
)
migrate_studio_database(database)
repository = SQLiteStudioBenchmarkExperimentRepository(database)
matching = repository.list_experiments(
    limit=10,
    filters=StudioBenchmarkExperimentHistoryFilterV1(
        lifecycle="running",
        catalog_entry_id="installed-history-catalog",
        agent_id="installed-history-agent",
        accepted_from=1234,
        accepted_before=1235,
    ),
)
assert [item.experiment_id for item in matching.items] == [experiment_id]
assert matching.items[0].definition.source.catalog_entry_id == (
    "installed-history-catalog"
)
assert repository.list_experiments(
    limit=10,
    filters=StudioBenchmarkExperimentHistoryFilterV1(
        agent_id="different-agent",
    ),
).items == ()
with sqlite3.connect(database) as connection:
    versions = [
        row[0]
        for row in connection.execute(
            "SELECT version FROM studio_schema_migrations ORDER BY version"
        )
    ]
    indexes = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        )
    }
assert versions == list(range(1, 13))
assert {
    "studio_benchmark_experiments_history_order",
    "studio_benchmark_experiments_catalog_history",
    "studio_benchmark_task_runs_agent_experiment",
} <= indexes
"""
    completed = subprocess.run(
        [str(python), "-c", script, str(database), experiment_id],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
