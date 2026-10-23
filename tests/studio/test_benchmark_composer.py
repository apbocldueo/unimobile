"""Contract tests for the side-effect-free Studio Benchmark Composer."""

from __future__ import annotations

import json
import shutil
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.benchmark_errors import StudioBenchmarkValidationError
from zhixing.studio.benchmark_models import (
    StudioBenchmarkCatalogPageV1,
    StudioBenchmarkPreviewRequestV1,
    StudioBenchmarkPreviewResponseV1,
    StudioBenchmarkTaskPageV1,
    StudioDeviceProfilePageV1,
)
from zhixing.studio.benchmark_service import (
    StudioBenchmarkApplicationService,
    StudioBenchmarkCatalogService,
    StudioBenchmarkSource,
    default_studio_benchmark_sources,
)
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
)
from zhixing.studio.flow_template_loader import get_flow_template_document

from .benchmark_fixtures import (
    FakeBenchmarkDistribution,
    FakeBenchmarkEntryPoint,
    write_studio_benchmark_package,
)
from .test_documents_catalog_compiler import _planner_document


_CONTRACTS = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "studio"
    / "benchmark"
    / "catalog-composer-contracts.json"
)


class NoResolveProfileResolver(AndroidDeviceProfileResolver):
    """Profile fixture that fails if preview crosses into runtime resolution."""

    def resolve(self, profile_id: str) -> AndroidDeviceProfile:
        """Reject every runtime resolution attempt.

        Args:
            profile_id: Candidate profile identity.

        Raises:
            AssertionError: Always; preview must not resolve devices.

        Returns:
            Never returns.
        """
        del profile_id
        raise AssertionError("preview must not resolve a device profile")


class ReadOnlyPreviewRepository:
    """Repository spy permitting only the immutable revision read."""

    def __init__(self, delegate: SQLiteAgentDocumentRepository) -> None:
        """Wrap the real repository with fail-fast write boundaries.

        Args:
            delegate: Repository containing the fixture revision.

        Raises:
            None.

        Returns:
            None.
        """
        self.delegate = delegate
        self.read_count = 0

    def get_revision(self, agent_id: str, revision_id: str) -> Any:
        """Delegate the one read operation allowed during preview.

        Args:
            agent_id: Selected Agent identity.
            revision_id: Selected immutable revision identity.

        Raises:
            AgentRevisionNotFoundError: The revision is absent.

        Returns:
            Stored immutable revision.
        """
        self.read_count += 1
        return self.delegate.get_revision(agent_id, revision_id)

    def __getattr__(self, name: str) -> Any:
        """Reject every repository operation except immutable revision reads.

        Args:
            name: Requested repository attribute.

        Raises:
            AssertionError: Always; preview must not use another operation.

        Returns:
            Never returns.
        """
        raise AssertionError(f"preview must not access repository operation {name}")


def _saved_revision(database: Path) -> tuple[SQLiteAgentDocumentRepository, str, str]:
    """Create one valid immutable revision for preview tests.

    Args:
        database: Temporary SQLite database.

    Raises:
        ValueError: The fixture Agent document cannot compile.

    Returns:
        Repository, Agent identity, and revision identity.
    """
    catalog = build_studio_component_catalog()
    repository = SQLiteAgentDocumentRepository(database)
    authoring = StudioApplicationService(
        catalog=catalog,
        repository=repository,
    )
    agent, revision = authoring.create_agent(
        "Benchmark preview fixture",
        initial_document=get_flow_template_document("modular_baseline"),
    )
    assert revision.compile_snapshot.status == "valid"
    return repository, agent.agent_id, revision.revision_id


def _preview_service(
    tmp_path: Path,
    *,
    dynamic: bool = False,
) -> tuple[StudioBenchmarkApplicationService, str, str, str, str]:
    """Build one complete preview-only service fixture.

    Args:
        tmp_path: Temporary fixture root.
        dynamic: Whether the Package task is dynamic.

    Raises:
        ValueError: Fixture contracts are invalid.

    Returns:
        Service, entry, task, Agent, and revision identities.
    """
    package = write_studio_benchmark_package(
        tmp_path / "catalog" / "fixture",
        dynamic=dynamic,
    )
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-package",
                kind="package",
                locator=package,
            ),
        )
    )
    agents, agent_id, revision_id = _saved_revision(tmp_path / "studio.sqlite3")
    graph_catalog = build_studio_component_catalog()
    profiles = NoResolveProfileResolver(
        {
            "local-android": AndroidDeviceProfile(
                "local-android",
                serial="/private/serial-must-not-leak",
                label="Local Android",
            )
        }
    )
    service = StudioBenchmarkApplicationService(
        catalog=catalog,
        agents=agents,
        profiles=profiles,
        contract_catalog=graph_catalog.node_contract_catalog(),
    )
    entry_id = catalog.list_entries().items[0].catalog_entry_id
    task_id = catalog.list_tasks(entry_id, split="test").items[0].task_id
    return service, entry_id, task_id, agent_id, revision_id


def _preview_payload(
    entry_id: str,
    task_id: str,
    agent_id: str,
    revision_id: str,
) -> dict:
    """Build one strict browser preview request.

    Args:
        entry_id: Opaque Catalog entry identity.
        task_id: Exact task identity.
        agent_id: Saved Agent identity.
        revision_id: Immutable revision identity.

    Raises:
        None.

    Returns:
        JSON-compatible request mapping.
    """
    payload = json.loads(_CONTRACTS.read_text(encoding="utf-8"))[
        "previewRequest"
    ]
    payload["agentRevisions"][0] = {
        "agentId": agent_id,
        "revisionId": revision_id,
    }
    payload["benchmark"]["catalogEntryId"] = entry_id
    payload["benchmark"]["taskIds"] = [task_id]
    return payload


def test_contract_fixtures_parse_strictly_and_reject_unknown_fields() -> None:
    """Parse all reusable DTO fixtures and reject silent contract expansion."""
    payload = json.loads(_CONTRACTS.read_text(encoding="utf-8"))
    StudioBenchmarkCatalogPageV1.model_validate(payload["catalogList"])
    StudioBenchmarkTaskPageV1.model_validate(payload["taskPage"])
    StudioDeviceProfilePageV1.model_validate(payload["deviceProfiles"])
    request = StudioBenchmarkPreviewRequestV1.model_validate(
        payload["previewRequest"]
    )
    assert request.protocol.repeats == 1

    malformed = dict(payload["previewRequest"])
    malformed["unexpected"] = True
    with pytest.raises(ValidationError):
        StudioBenchmarkPreviewRequestV1.model_validate(malformed)
    nonfinite = json.loads(json.dumps(payload["previewRequest"]))
    nonfinite["protocol"]["budget"]["timeoutSeconds"] = float("inf")
    with pytest.raises(ValidationError):
        StudioBenchmarkPreviewRequestV1.model_validate(nonfinite)


def test_catalog_snapshot_is_deterministic_paginated_and_ignores_data(
    tmp_path: Path,
) -> None:
    """Index only configured roots and keep cursor/filter identity stable."""
    workspace = tmp_path / "workspace"
    write_studio_benchmark_package(workspace / "benchmarks" / "first", name="first")
    write_studio_benchmark_package(workspace / "benchmarks" / "second", name="second")
    write_studio_benchmark_package(workspace / "data" / "hidden", name="hidden")

    sources = default_studio_benchmark_sources(
        workspace,
        include_installed=False,
    )
    first = StudioBenchmarkCatalogService(sources)
    restarted = StudioBenchmarkCatalogService(sources)
    first_page = first.list_entries(limit=1)
    assert len(first_page.items) == 1
    assert first_page.next_cursor is not None
    second_page = first.list_entries(limit=1, cursor=first_page.next_cursor)
    assert len(second_page.items) == 1
    assert {
        first_page.items[0].package_identity,
        second_page.items[0].package_identity,
    } == {"tests/first@1.0.0", "tests/second@1.0.0"}
    assert [
        item.catalog_entry_id for item in first.list_entries().items
    ] == [
        item.catalog_entry_id for item in restarted.list_entries().items
    ]
    assert all(
        "hidden" not in item.package_identity
        for item in first.list_entries().items
    )
    with pytest.raises(StudioBenchmarkValidationError):
        first.list_entries(
            cursor=first_page.next_cursor,
            platform="harmonyos",
        )


def test_invalid_entry_is_isolated_and_duplicate_sources_are_explicit(
    tmp_path: Path,
) -> None:
    """Keep invalid/divergent sources visible without overriding valid entries."""
    root = tmp_path / "catalog"
    valid = write_studio_benchmark_package(root / "valid", name="shared")
    duplicate = root / "duplicate"
    shutil.copytree(valid, duplicate)
    divergent = write_studio_benchmark_package(root / "divergent", name="shared")
    tasks = json.loads((divergent / "tasks" / "test.json").read_text())
    tasks[0]["instruction"] = "Divergent content"
    (divergent / "tasks" / "test.json").write_text(json.dumps(tasks))
    write_studio_benchmark_package(
        root / "invalid",
        name="invalid",
        invalid_tasks=True,
    )
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-root",
                kind="catalog_root",
                locator=root,
            ),
        )
    )
    items = catalog.list_entries().items
    assert len(items) == 4
    invalid = next(item for item in items if "invalid@" in item.package_identity)
    assert invalid.availability == "invalid"
    shared = [item for item in items if "shared@" in item.package_identity]
    assert len(shared) == 3
    assert all(
        any(
            warning.code == "benchmark.catalog.identity_ambiguous"
            for warning in item.warnings
        )
        for item in shared
    )
    serialized = json.dumps(
        catalog.list_entries().model_dump(mode="json", by_alias=True)
    )
    assert str(tmp_path) not in serialized


def test_installed_metadata_does_not_load_provider_code(tmp_path: Path) -> None:
    """Discover an installed Package solely through distribution metadata."""
    package = write_studio_benchmark_package(tmp_path / "installed")
    entry_point = FakeBenchmarkEntryPoint(FakeBenchmarkDistribution(package))
    catalog = StudioBenchmarkCatalogService(
        (StudioBenchmarkSource("installed-fixtures", "installed"),),
        installed_entry_points=(entry_point,),
    )
    item = catalog.list_entries().items[0]
    assert item.source_kind == "installed"
    assert entry_point.loaded is False


def test_catalog_detail_tasks_and_validate_use_formal_compiler(
    tmp_path: Path,
) -> None:
    """Return safe task metadata and full canonical validation identities."""
    package = write_studio_benchmark_package(tmp_path / "fixture")
    catalog = StudioBenchmarkCatalogService(
        (StudioBenchmarkSource("fixture", "package", package),)
    )
    entry_id = catalog.list_entries().items[0].catalog_entry_id
    detail = catalog.detail(entry_id)
    tasks = catalog.list_tasks(entry_id, split="test", limit=1)
    validation = catalog.validate_entry(entry_id, split="test")
    assert detail.package_content_identity is not None
    assert detail.resources[0].sha256.startswith("sha256:")
    assert tasks.items[0].initializer_count == 1
    assert validation.valid is True
    assert validation.identities.benchmark_plan is not None
    payload = json.dumps(
        detail.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    assert str(tmp_path) not in payload
    assert "local_path" not in payload


def test_safe_profiles_never_serialize_serial_or_resolve_device(
    tmp_path: Path,
) -> None:
    """List static profile metadata while keeping runtime identity internal."""
    service, _entry, _task, _agent, _revision = _preview_service(tmp_path)
    payload = service.device_profiles().model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    serialized = json.dumps(payload)
    assert payload["items"][0]["deviceProfileId"] == "local-android"
    assert "serial" not in serialized
    assert "/private/" not in serialized


def test_preview_is_deterministic_normalized_and_non_persistent(
    tmp_path: Path,
) -> None:
    """Reuse formal scheduling and return no Experiment or runtime identity."""
    service, entry_id, task_id, agent_id, revision_id = _preview_service(tmp_path)
    payload = _preview_payload(entry_id, task_id, agent_id, revision_id)
    first = service.preview(payload)
    reordered = json.loads(json.dumps(payload, sort_keys=True))
    second = service.preview(reordered)
    assert first.preview_fingerprint == second.preview_fingerprint
    assert first.schedule == second.schedule
    assert first.preview_only is True
    assert first.execution_limits.max_agents == 1
    assert first.schedule[0].task_instance.availability == "template_only"
    public = first.model_dump(mode="json", by_alias=True, exclude_none=True)
    StudioBenchmarkPreviewResponseV1.model_validate(public)
    serialized = json.dumps(public)
    assert "experimentId" not in serialized
    assert "taskRunId" not in serialized
    assert "serial" not in serialized


def test_preview_has_no_runtime_or_persistence_side_effects(
    tmp_path: Path,
) -> None:
    """Fail fast on repository writes/device resolution and preserve all rows."""
    service, entry_id, task_id, agent_id, revision_id = _preview_service(tmp_path)
    database = tmp_path / "studio.sqlite3"
    repository = service.agents
    assert isinstance(repository, SQLiteAgentDocumentRepository)
    read_only = ReadOnlyPreviewRepository(repository)
    service.agents = read_only
    with sqlite3.connect(database) as connection:
        before = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - fixed table names.
            ).fetchone()[0]
            for table in (
                "studio_agents",
                "studio_agent_revisions",
                "studio_runs",
                "studio_run_events",
                "studio_replays",
            )
        }
    preview = service.preview(
        _preview_payload(entry_id, task_id, agent_id, revision_id)
    )
    with sqlite3.connect(database) as connection:
        after = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"  # noqa: S608 - fixed table names.
            ).fetchone()[0]
            for table in before
        }
    assert preview.preview_only is True
    assert read_only.read_count == 1
    assert after == before
    assert set(vars(service)) == {
        "catalog",
        "agents",
            "profiles",
            "contract_catalog",
            "component_catalog",
        }


def test_preview_rejects_legacy_revision_before_schedule_or_runtime_effect(
    tmp_path: Path,
) -> None:
    """Keep schema-2 history readable while denying new Benchmark execution.

    Args:
        tmp_path: Isolated package and SQLite fixture root.

    Raises:
        StudioBenchmarkValidationError: Expected for the legacy selection.

    Returns:
        None.
    """
    service, entry_id, task_id, _agent_id, _revision_id = _preview_service(tmp_path)
    graph_catalog = build_studio_component_catalog()
    assert isinstance(service.agents, SQLiteAgentDocumentRepository)
    authoring = StudioApplicationService(
        catalog=graph_catalog,
        repository=service.agents,
    )
    legacy_agent, legacy_revision = authoring.create_agent(
        "Legacy Benchmark selection",
        initial_document=_planner_document(),
    )
    legacy_before = legacy_revision.model_dump_json()
    payload = _preview_payload(
        entry_id,
        task_id,
        legacy_agent.agent_id,
        legacy_revision.revision_id,
    )
    with pytest.raises(StudioBenchmarkValidationError) as captured:
        service.preview(payload)
    assert captured.value.code == "benchmark.preview.revision_invalid"
    persisted = service.agents.get_revision(
        legacy_agent.agent_id,
        legacy_revision.revision_id,
    )
    assert persisted.model_dump_json() == legacy_before


def test_preview_rejects_cardinality_profile_task_and_revision(
    tmp_path: Path,
) -> None:
    """Reject the entire unsupported or stale definition before scheduling."""
    service, entry_id, task_id, agent_id, revision_id = _preview_service(tmp_path)
    payload = _preview_payload(entry_id, task_id, agent_id, revision_id)

    repeated = json.loads(json.dumps(payload))
    repeated["protocol"]["repeats"] = 2
    with pytest.raises(StudioBenchmarkValidationError) as cardinality:
        service.preview(repeated)
    assert cardinality.value.code == "benchmark.preview.unsupported_cardinality"

    unknown_profile = json.loads(json.dumps(payload))
    unknown_profile["deviceProfileId"] = "unknown-profile"
    with pytest.raises(StudioBenchmarkValidationError) as profile:
        service.preview(unknown_profile)
    assert profile.value.code == "benchmark.preview.device_profile_unknown"

    unknown_task = json.loads(json.dumps(payload))
    unknown_task["benchmark"]["taskIds"] = ["unknown-task"]
    with pytest.raises(StudioBenchmarkValidationError) as task_error:
        service.preview(unknown_task)
    assert task_error.value.code == "benchmark.preview.task_not_found"

    unknown_revision = json.loads(json.dumps(payload))
    unknown_revision["agentRevisions"][0]["revisionId"] = "revision-missing"
    with pytest.raises(StudioBenchmarkValidationError) as revision_error:
        service.preview(unknown_revision)
    assert revision_error.value.code == "benchmark.preview.revision_invalid"


def test_dynamic_preview_stops_before_materialization(tmp_path: Path) -> None:
    """Expose only derived seed and pending status for dynamic task templates."""
    service, entry_id, task_id, agent_id, revision_id = _preview_service(
        tmp_path,
        dynamic=True,
    )
    preview = service.preview(
        _preview_payload(entry_id, task_id, agent_id, revision_id)
    )
    assert preview.schedule[0].task_instance.availability == (
        "pending_materialization"
    )
    assert preview.schedule[0].task_instance.parameters is None
    assert isinstance(preview.schedule[0].derived_seed, int)


def test_resource_digest_failure_is_normal_validation_result(
    tmp_path: Path,
) -> None:
    """Aggregate full validation errors without exposing the host path."""
    package = write_studio_benchmark_package(tmp_path / "fixture")
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text())
    manifest["resources"][0]["sha256"] = "sha256:" + "0" * 64
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False))
    catalog = StudioBenchmarkCatalogService(
        (StudioBenchmarkSource("fixture", "package", package),)
    )
    entry_id = catalog.list_entries().items[0].catalog_entry_id
    result = catalog.validate_entry(entry_id)
    assert result.valid is False
    serialized = json.dumps(
        result.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    assert str(tmp_path) not in serialized
