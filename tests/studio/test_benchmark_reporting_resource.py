"""Stage 5.4A Benchmark history and artifact inventory contract tests."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from tests.studio.test_benchmark_experiment_resource import (
    _http_request,
    _resource_service,
    _start_experiment_http_server,
    _stop_experiment_http_server,
)
from zhixing.studio.benchmark_errors import (
    StudioBenchmarkNotFoundError,
    StudioBenchmarkValidationError,
)
from zhixing.studio.benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from zhixing.studio.benchmark_publication_models import (
    StudioBenchmarkArtifactAvailability,
    StudioBenchmarkArtifactDescriptorV1,
)
from zhixing.studio.benchmark_publication_repository import (
    SQLiteStudioBenchmarkPublicationRepository,
)


def _create_experiment(
    service: StudioBenchmarkExperimentApplicationService,
    payload: dict[str, object],
    request_number: int,
) -> str:
    """Create one Experiment by varying only its idempotency identity.

    Args:
        service: Deterministic Experiment application service.
        payload: Valid base create payload.
        request_number: Unique request suffix.

    Returns:
        Created opaque Experiment identity.
    """
    request = dict(payload)
    request["clientRequestId"] = f"experiment-request-{request_number}"
    return service.create_experiment(request).experiment.experiment_id


def _insert_artifact(
    database: Path,
    descriptor: StudioBenchmarkArtifactDescriptorV1,
) -> None:
    """Insert one valid committed descriptor for metadata query tests.

    Args:
        database: Migrated Studio SQLite path.
        descriptor: Strict managed artifact descriptor.

    Raises:
        sqlite3.Error: Fixture insertion fails.

    Returns:
        None.
    """
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            INSERT INTO studio_benchmark_artifacts(
                experiment_id, artifact_id, task_run_id, kind,
                availability, content_type, size, sha256, provenance,
                causal_identity, hidden, storage_ref, descriptor_json,
                created_at
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
                f"managed/{descriptor.artifact_id}.json",
                json.dumps(
                    descriptor.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                    ),
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                1,
            ),
        )


def _reporting_service(
    tmp_path: Path,
) -> tuple[
    StudioBenchmarkExperimentApplicationService,
    SQLiteStudioBenchmarkPublicationRepository,
    dict[str, object],
]:
    """Build a deterministic service with metadata-only publication access.

    Args:
        tmp_path: Isolated workspace root.

    Returns:
        Reporting-capable service, publication repository, and create payload.
    """
    service, repository, payload = _resource_service(tmp_path)
    publications = SQLiteStudioBenchmarkPublicationRepository(
        tmp_path / "studio.sqlite3"
    )
    service.publication_repository = publications
    service._publication_enabled = True
    return service, publications, payload


def test_history_uses_stable_newest_first_keyset_pagination(
    tmp_path: Path,
) -> None:
    """Keep tied rows stable and ignore inserts above an existing boundary."""
    service, repository, payload = _resource_service(tmp_path)
    identifiers = [
        _create_experiment(service, payload, number)
        for number in range(1, 5)
    ]
    database = tmp_path / "studio.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE studio_benchmark_experiments "
            "SET accepted_at = ?, updated_at = ? "
            "WHERE experiment_id IN (?, ?)",
            (1_700_000_000_100, 1_700_000_000_100, identifiers[1], identifiers[2]),
        )
    tied_page = repository.list_experiments(limit=100)
    tied = [
        item.experiment_id
        for item in tied_page.items
        if item.accepted_at == 1_700_000_000_100
    ]
    assert tied == sorted(tied, reverse=True)

    first = repository.list_experiments(limit=2)
    assert first.next_cursor is not None
    inserted = _create_experiment(service, payload, 5)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE studio_benchmark_experiments "
            "SET accepted_at = ?, updated_at = ? "
            "WHERE experiment_id = ?",
            (1_700_000_000_200, 1_700_000_000_200, inserted),
        )
    second = repository.list_experiments(
        limit=100,
        cursor=first.next_cursor,
    )
    first_ids = {item.experiment_id for item in first.items}
    second_ids = {item.experiment_id for item in second.items}
    assert inserted not in second_ids
    assert first_ids.isdisjoint(second_ids)
    assert first_ids | second_ids == set(identifiers)


def test_history_rejects_invalid_limits_and_tampered_cursors(
    tmp_path: Path,
) -> None:
    """Reject malformed metadata pagination without leaking storage details."""
    _service, repository, _payload = _resource_service(tmp_path)
    with pytest.raises(
        StudioBenchmarkValidationError,
        match="within 1 and 100",
    ):
        repository.list_experiments(limit=0)
    with pytest.raises(
        StudioBenchmarkValidationError,
        match="cursor is invalid",
    ):
        repository.list_experiments(limit=10, cursor="tampered")


def test_history_projection_is_compact_and_immutable(
    tmp_path: Path,
) -> None:
    """Project snapshot identities without a Catalog lookup or full graph."""
    service, _repository, payload = _reporting_service(tmp_path)
    experiment_id = _create_experiment(service, payload, 1)
    service.definitions = object()  # type: ignore[assignment]
    page = service.list_experiments(limit=10)
    item = next(
        entry for entry in page.items if entry.experiment_id == experiment_id
    )
    public = item.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "definition" not in public
    assert "agentGraph" not in json.dumps(public)
    assert item.source.catalog_entry_id
    assert item.source.package_identity
    assert item.planned_task_run_count == 1
    assert item.links.artifacts == (
        f"/studio/benchmark-experiments/{experiment_id}/artifacts"
    )
    assert item.links.report is None


def test_inventory_is_scoped_metadata_only_and_hides_identities(
    tmp_path: Path,
) -> None:
    """Paginate visible descriptors and expose only aggregate hidden count."""
    service, publications, payload = _reporting_service(tmp_path)
    experiment_a = _create_experiment(service, payload, 1)
    experiment_b = _create_experiment(service, payload, 2)
    database = tmp_path / "studio.sqlite3"
    descriptors = (
        StudioBenchmarkArtifactDescriptorV1(
            artifact_id=f"artifact-{'1' * 32}",
            experiment_id=experiment_a,
            kind="benchmark_experiment_report",
            availability=StudioBenchmarkArtifactAvailability.AVAILABLE,
            content_type="application/json",
            size=20,
            sha256=f"sha256:{'1' * 64}",
            causal_identity="reports/experiment-report.json",
        ),
        StudioBenchmarkArtifactDescriptorV1(
            artifact_id=f"artifact-{'2' * 32}",
            experiment_id=experiment_a,
            kind="task_trajectory",
            availability=StudioBenchmarkArtifactAvailability.MISSING,
            size=20,
            causal_identity="runs/task/trajectory.json",
        ),
        StudioBenchmarkArtifactDescriptorV1(
            artifact_id=f"artifact-{'3' * 32}",
            experiment_id=experiment_a,
            kind="private_prompt",
            availability=StudioBenchmarkArtifactAvailability.HIDDEN,
            hidden=True,
            causal_identity="private/prompt.json",
        ),
    )
    for descriptor in descriptors:
        _insert_artifact(database, descriptor)

    first = service.list_artifact_inventory(experiment_a, limit=1)
    assert first.hidden_count == 1
    assert first.next_cursor is not None
    assert first.items[0].links.content == (
        f"/studio/benchmark-experiments/{experiment_a}/artifacts/"
        f"{descriptors[0].artifact_id}"
    )
    second = service.list_artifact_inventory(
        experiment_a,
        limit=1,
        cursor=first.next_cursor,
    )
    assert second.items[0].descriptor.availability is (
        StudioBenchmarkArtifactAvailability.MISSING
    )
    assert second.items[0].links.content is None
    serialized = json.dumps(
        second.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    assert descriptors[2].artifact_id not in serialized
    assert descriptors[2].causal_identity not in serialized

    with pytest.raises(StudioBenchmarkValidationError):
        service.list_artifact_inventory(
            experiment_b,
            limit=10,
            cursor=first.next_cursor,
        )
    with pytest.raises(StudioBenchmarkNotFoundError):
        service.list_artifact_inventory(
            f"experiment-{'f' * 32}",
            limit=10,
        )

    metadata = publications.list_artifact_metadata(experiment_a, limit=100)
    assert all(not item.hidden for item in metadata.items)


def test_inventory_refresh_removes_link_after_integrity_closure(
    tmp_path: Path,
) -> None:
    """Reflect committed missing facts without reading or guessing content."""
    service, publications, payload = _reporting_service(tmp_path)
    experiment_id = _create_experiment(service, payload, 1)
    descriptor = StudioBenchmarkArtifactDescriptorV1(
        artifact_id=f"artifact-{'a' * 32}",
        experiment_id=experiment_id,
        kind="benchmark_experiment_report",
        availability=StudioBenchmarkArtifactAvailability.AVAILABLE,
        content_type="application/json",
        size=2,
        sha256=f"sha256:{'a' * 64}",
        causal_identity="reports/experiment-report.json",
    )
    _insert_artifact(tmp_path / "studio.sqlite3", descriptor)
    before = service.list_artifact_inventory(experiment_id, limit=10)
    assert before.items[0].links.content is not None
    publications.update_artifact_availability(
        experiment_id,
        descriptor.artifact_id,
        StudioBenchmarkArtifactAvailability.MISSING,
    )
    after = service.list_artifact_inventory(experiment_id, limit=10)
    assert after.items[0].descriptor.availability is (
        StudioBenchmarkArtifactAvailability.MISSING
    )
    assert after.items[0].links.content is None


def test_http_history_and_inventory_use_strict_safe_envelopes(
    tmp_path: Path,
) -> None:
    """Expose both metadata resources and preserve stable validation errors."""
    service, _publications, payload = _reporting_service(tmp_path)
    experiment_id = _create_experiment(service, payload, 1)
    descriptor = StudioBenchmarkArtifactDescriptorV1(
        artifact_id=f"artifact-{'b' * 32}",
        experiment_id=experiment_id,
        kind="benchmark_experiment_report",
        availability=StudioBenchmarkArtifactAvailability.AVAILABLE,
        content_type="application/json",
        size=2,
        sha256=f"sha256:{'b' * 64}",
        causal_identity="reports/experiment-report.json",
    )
    _insert_artifact(tmp_path / "studio.sqlite3", descriptor)
    server, thread, address = _start_experiment_http_server(service)
    try:
        status, history = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?limit=10",
        )
        assert status == 200
        assert history["items"][0]["experimentId"] == experiment_id
        status, inventory = _http_request(
            address,
            "GET",
            f"/api/studio/benchmark-experiments/{experiment_id}/artifacts"
            "?limit=10",
        )
        assert status == 200
        assert inventory["items"][0]["descriptor"]["artifactId"] == (
            descriptor.artifact_id
        )
        status, invalid = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?limit=0",
        )
        assert status == 400
        assert invalid["error"]["code"] == (
            "benchmark.experiment.history_limit_invalid"
        )
        status, repeated = _http_request(
            address,
            "GET",
            "/api/studio/benchmark-experiments?limit=10&limit=20",
        )
        assert status == 400
        assert repeated["error"]["code"] == (
            "benchmark.experiment.history.query_invalid"
        )
    finally:
        _stop_experiment_http_server(server, thread)
