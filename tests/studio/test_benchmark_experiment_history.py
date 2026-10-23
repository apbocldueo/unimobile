"""Stage 5.4D-1 filtered Benchmark Experiment History contract tests."""

from __future__ import annotations

import base64
import json
import sqlite3
from pathlib import Path
from urllib.parse import urlencode

import pytest
from pydantic import ValidationError

from tests.studio.test_benchmark_experiment_resource import (
    _http_request,
    _resource_service,
    _start_experiment_http_server,
    _stop_experiment_http_server,
)
from tests.studio.test_benchmark_reporting_resource import _create_experiment
from zhixing.benchmark.identity import canonical_hash
from zhixing.studio.benchmark_errors import StudioBenchmarkValidationError
from zhixing.studio.benchmark_experiment_models import (
    JAVASCRIPT_SAFE_INTEGER_MAX,
    StudioBenchmarkExperimentHistoryFilterV1,
    StudioBenchmarkExperimentLifecycle,
)
from zhixing.studio.database import (
    STUDIO_SQLITE_SCHEMA_VERSION,
    migrate_studio_database,
)


def _cursor_v1(accepted_at: int, experiment_id: str) -> str:
    """Encode the historical unfiltered cursor contract for compatibility.

    Args:
        accepted_at: Exclusive acceptance timestamp boundary.
        experiment_id: Exclusive Experiment identity boundary.

    Returns:
        URL-safe legacy cursor.
    """
    body: dict[str, object] = {
        "v": 1,
        "acceptedAt": accepted_at,
        "experimentId": experiment_id,
    }
    body["check"] = canonical_hash(body)
    encoded = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(encoded).decode("ascii").rstrip("=")


def _rewrite_history_facts(
    database: Path,
    experiment_id: str,
    *,
    accepted_at: int | None = None,
    lifecycle: str | None = None,
    catalog_entry_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Rewrite deterministic fixture facts while preserving canonical JSON.

    Args:
        database: Migrated fixture database.
        experiment_id: Owning Experiment identity.
        accepted_at: Optional accepted/updated timestamp replacement.
        lifecycle: Optional non-terminal lifecycle replacement.
        catalog_entry_id: Optional immutable snapshot Catalog identity.
        agent_id: Optional snapshot and scheduled TaskRun Agent identity.

    Raises:
        sqlite3.Error: Fixture storage cannot be updated.

    Returns:
        None.
    """
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT snapshot_json FROM studio_benchmark_experiments "
            "WHERE experiment_id = ?",
            (experiment_id,),
        ).fetchone()
        assert row is not None
        snapshot = json.loads(row[0])
        if catalog_entry_id is not None:
            snapshot["source"]["catalogEntryId"] = catalog_entry_id
        if agent_id is not None:
            snapshot["agentSnapshots"][0]["agentId"] = agent_id
        updates: list[str] = ["snapshot_json = ?"]
        parameters: list[object] = [
            json.dumps(
                snapshot,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        ]
        if accepted_at is not None:
            updates.extend(("accepted_at = ?", "updated_at = ?"))
            parameters.extend((accepted_at, accepted_at))
        if lifecycle is not None:
            updates.append("lifecycle_state = ?")
            parameters.append(lifecycle)
        parameters.append(experiment_id)
        connection.execute(
            "UPDATE studio_benchmark_experiments SET "
            + ", ".join(updates)
            + " WHERE experiment_id = ?",
            parameters,
        )
        if agent_id is not None:
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
                "SET agent_id = ?, task_run_json = ? "
                "WHERE task_run_id = ?",
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


def test_history_filter_is_strict_canonical_and_half_open() -> None:
    """Validate exact identities, safe integers, range, and fingerprinting."""
    filters = StudioBenchmarkExperimentHistoryFilterV1(
        lifecycle=StudioBenchmarkExperimentLifecycle.RUNNING,
        catalog_entry_id="catalog.entry:one",
        agent_id="agent-one",
        accepted_from=10,
        accepted_before=20,
    )
    assert filters.canonical_identity() == {
        "acceptedBefore": 20,
        "acceptedFrom": 10,
        "agentId": "agent-one",
        "catalogEntryId": "catalog.entry:one",
        "lifecycle": "running",
    }
    assert filters.fingerprint() == StudioBenchmarkExperimentHistoryFilterV1(
        accepted_before=20,
        accepted_from=10,
        agent_id="agent-one",
        catalog_entry_id="catalog.entry:one",
        lifecycle="running",
    ).fingerprint()
    assert StudioBenchmarkExperimentHistoryFilterV1().is_empty()
    with pytest.raises(ValidationError):
        StudioBenchmarkExperimentHistoryFilterV1(
            accepted_from=20,
            accepted_before=20,
        )
    with pytest.raises(ValidationError):
        StudioBenchmarkExperimentHistoryFilterV1(
            accepted_from=JAVASCRIPT_SAFE_INTEGER_MAX + 1
        )
    with pytest.raises(ValidationError):
        StudioBenchmarkExperimentHistoryFilterV1(agent_id="../unsafe")


def test_schema_seven_is_index_only_reentrant_and_atomic(
    tmp_path: Path,
) -> None:
    """Upgrade schema 6, preserve rows, and roll back a failed index batch."""
    database = tmp_path / "studio.sqlite3"
    service, _repository, payload = _resource_service(tmp_path)
    experiment_id = _create_experiment(service, payload, 1)
    expected_snapshot = service.get_experiment(experiment_id).definition
    index_names = {
        "studio_benchmark_experiments_history_order",
        "studio_benchmark_experiments_catalog_history",
        "studio_benchmark_task_runs_agent_experiment",
    }
    with sqlite3.connect(database) as connection:
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version >= 7"
        )
        for name in index_names:
            connection.execute(f"DROP INDEX {name}")
    migrate_studio_database(database)
    migrate_studio_database(database)
    assert (
        service.get_experiment(experiment_id).definition == expected_snapshot
    )
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
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))
    assert index_names <= indexes

    failing = tmp_path / "failing.sqlite3"
    migrate_studio_database(failing)
    with sqlite3.connect(failing) as connection:
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version >= 7"
        )
        for name in index_names:
            connection.execute(f"DROP INDEX {name}")
        connection.execute(
            "CREATE TABLE studio_benchmark_experiments_history_order("
            "sentinel INTEGER)"
        )
    with pytest.raises(sqlite3.Error):
        migrate_studio_database(failing)
    with sqlite3.connect(failing) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM studio_schema_migrations"
        ).fetchone()[0]
        partial_indexes = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'"
            )
        }
    assert version == 6
    assert not (index_names - {"studio_benchmark_experiments_history_order"}) & (
        partial_indexes
    )


def test_repository_filters_full_history_and_binds_cursor(
    tmp_path: Path,
) -> None:
    """Apply exact AND filters before stable keyset pagination."""
    service, repository, payload = _resource_service(tmp_path)
    identifiers = [
        _create_experiment(service, payload, index) for index in range(1, 6)
    ]
    database = tmp_path / "studio.sqlite3"
    facts = (
        (100, "accepted", "catalog-a", "agent-a"),
        (200, "running", "catalog-a", "agent-a"),
        (200, "running", "catalog-a", "agent-b"),
        (300, "running", "catalog-b", "agent-a"),
        (400, "accepted", "catalog-b", "agent-b"),
    )
    for experiment_id, fact in zip(identifiers, facts, strict=True):
        _rewrite_history_facts(
            database,
            experiment_id,
            accepted_at=fact[0],
            lifecycle=fact[1],
            catalog_entry_id=fact[2],
            agent_id=fact[3],
        )

    assert {
        item.experiment_id
        for item in repository.list_experiments(
            limit=100,
            filters=StudioBenchmarkExperimentHistoryFilterV1(
                lifecycle="running"
            ),
        ).items
    } == set(identifiers[1:4])
    assert {
        item.experiment_id
        for item in repository.list_experiments(
            limit=100,
            filters=StudioBenchmarkExperimentHistoryFilterV1(
                catalog_entry_id="catalog-a"
            ),
        ).items
    } == set(identifiers[:3])
    assert {
        item.experiment_id
        for item in repository.list_experiments(
            limit=100,
            filters=StudioBenchmarkExperimentHistoryFilterV1(
                agent_id="agent-b"
            ),
        ).items
    } == {identifiers[2], identifiers[4]}
    ranged = repository.list_experiments(
        limit=100,
        filters=StudioBenchmarkExperimentHistoryFilterV1(
            accepted_from=200,
            accepted_before=400,
        ),
    )
    assert {item.experiment_id for item in ranged.items} == set(
        identifiers[1:4]
    )

    combined_filters = StudioBenchmarkExperimentHistoryFilterV1(
        lifecycle="running",
        catalog_entry_id="catalog-a",
        agent_id="agent-a",
        accepted_from=100,
        accepted_before=300,
    )
    first = repository.list_experiments(
        limit=1,
        filters=combined_filters,
    )
    assert [item.experiment_id for item in first.items] == [identifiers[1]]
    assert first.next_cursor is None

    tied = repository.list_experiments(
        limit=1,
        filters=StudioBenchmarkExperimentHistoryFilterV1(
            lifecycle="running"
        ),
    )
    assert tied.next_cursor is not None
    with pytest.raises(
        StudioBenchmarkValidationError,
        match="cursor is invalid",
    ):
        repository.list_experiments(
            limit=10,
            cursor=tied.next_cursor,
            filters=StudioBenchmarkExperimentHistoryFilterV1(
                lifecycle="accepted"
            ),
        )

    legacy = _cursor_v1(300, identifiers[3])
    assert repository.list_experiments(
        limit=100,
        cursor=legacy,
    ).items
    with pytest.raises(StudioBenchmarkValidationError):
        repository.list_experiments(
            limit=100,
            cursor=legacy,
            filters=StudioBenchmarkExperimentHistoryFilterV1(
                agent_id="agent-a"
            ),
        )


def test_filtered_history_uses_current_lifecycle_and_durable_identity(
    tmp_path: Path,
) -> None:
    """Keep mutable lifecycle current while Catalog and schedule stay durable."""
    service, repository, payload = _resource_service(tmp_path)
    experiment_id = _create_experiment(service, payload, 1)
    database = tmp_path / "studio.sqlite3"
    _rewrite_history_facts(
        database,
        experiment_id,
        accepted_at=100,
        lifecycle="accepted",
        catalog_entry_id="deleted-catalog",
        agent_id="deleted-agent",
    )
    exact = StudioBenchmarkExperimentHistoryFilterV1(
        catalog_entry_id="deleted-catalog",
        agent_id="deleted-agent",
    )
    assert repository.list_experiments(
        limit=10,
        filters=exact,
    ).items[0].experiment_id == experiment_id
    service.definitions = object()  # type: ignore[assignment]
    public = service.list_experiments(
        limit=10,
        filters=exact,
    ).model_dump(mode="json", by_alias=True, exclude_none=True)
    serialized = json.dumps(public)
    assert public["items"][0]["source"]["catalogEntryId"] == "deleted-catalog"
    assert public["items"][0]["agents"][0]["agentId"] == "deleted-agent"
    assert "definition" not in serialized
    assert "agentGraph" not in serialized
    assert "storageRef" not in serialized

    _rewrite_history_facts(
        database,
        experiment_id,
        lifecycle="running",
    )
    assert not repository.list_experiments(
        limit=10,
        filters=StudioBenchmarkExperimentHistoryFilterV1(
            lifecycle="accepted"
        ),
    ).items
    assert repository.list_experiments(
        limit=10,
        filters=StudioBenchmarkExperimentHistoryFilterV1(
            lifecycle="running"
        ),
    ).items


def test_http_history_filters_are_strict_safe_and_metadata_only(
    tmp_path: Path,
) -> None:
    """Expose exact filters and reject ambiguous or unsafe query identities."""
    service, _repository, payload = _resource_service(tmp_path)
    experiment_id = _create_experiment(service, payload, 1)
    older_id = _create_experiment(service, payload, 2)
    database = tmp_path / "studio.sqlite3"
    _rewrite_history_facts(
        database,
        experiment_id,
        accepted_at=200,
        lifecycle="running",
        catalog_entry_id="catalog-http",
        agent_id="agent-http",
    )
    _rewrite_history_facts(
        database,
        older_id,
        accepted_at=199,
        lifecycle="running",
        catalog_entry_id="catalog-http",
        agent_id="agent-http",
    )
    server, thread, address = _start_experiment_http_server(service)
    try:
        query = urlencode(
            {
                "limit": "1",
                "lifecycle": "running",
                "catalogEntryId": "catalog-http",
                "agentId": "agent-http",
                "acceptedFrom": "199",
                "acceptedBefore": "201",
            }
        )
        status, page = _http_request(
            address,
            "GET",
            f"/api/studio/benchmark-experiments?{query}",
        )
        assert status == 200
        assert [item["experimentId"] for item in page["items"]] == [
            experiment_id
        ]
        assert "report" not in page["items"][0]["links"]
        assert page["nextCursor"]
        status, second_page = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?"
            + query
            + "&cursor="
            + page["nextCursor"],
        )
        assert status == 200
        assert [item["experimentId"] for item in second_page["items"]] == [
            older_id
        ]
        status, cross_filter = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?"
            + urlencode(
                {
                    "limit": "10",
                    "lifecycle": "accepted",
                    "cursor": page["nextCursor"],
                }
            ),
        )
        assert status == 400
        assert cross_filter["error"]["code"] == (
            "benchmark.experiment.history_cursor_invalid"
        )
        legacy = _cursor_v1(201, f"experiment-{'f' * 32}")
        status, legacy_page = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?"
            + urlencode({"limit": "10", "cursor": legacy}),
        )
        assert status == 200
        assert len(legacy_page["items"]) == 2
        status, filtered_legacy = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?"
            + urlencode(
                {
                    "limit": "10",
                    "cursor": legacy,
                    "lifecycle": "running",
                }
            ),
        )
        assert status == 400
        assert filtered_legacy["error"]["code"] == (
            "benchmark.experiment.history_cursor_invalid"
        )
        serialized = json.dumps(page)
        for forbidden in (
            "agentGraph",
            "protocol",
            "prompt",
            "secret",
            "serial",
            "storageRef",
            "artifactBytes",
            "links.replay",
        ):
            assert forbidden not in serialized

        invalid_queries = (
            ("lifecycle=", "benchmark.experiment.history.query_invalid"),
            (
                "agentId=one&agentId=two",
                "benchmark.experiment.history.query_invalid",
            ),
            ("unknown=value", "benchmark.experiment.history.query_invalid"),
            (
                "acceptedFrom=20&acceptedBefore=10",
                "benchmark.experiment.history_filter_invalid",
            ),
            (
                "acceptedFrom=01",
                "benchmark.experiment.history_filter_invalid",
            ),
            (
                "lifecycle=unknown",
                "benchmark.experiment.history_filter_invalid",
            ),
        )
        for raw_query, expected_code in invalid_queries:
            status, error = _http_request(
                address,
                "GET",
                f"/api/studio/benchmark-experiments?{raw_query}",
            )
            assert status == 400
            assert error["error"]["code"] == expected_code
            assert "sqlite" not in json.dumps(error).lower()
    finally:
        _stop_experiment_http_server(server, thread)
