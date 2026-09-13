"""Focused contracts for Studio legacy BenchmarkTask JSON migration."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringDriftError,
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from zhixing.studio.benchmark_authoring_migration import (
    StudioBenchmarkLegacyMigrationAnalyzer,
    StudioBenchmarkLegacyMigrationApplicationService,
)
from zhixing.studio.benchmark_authoring_migration_models import (
    STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY,
    STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS,
    STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES,
    STUDIO_BENCHMARK_MIGRATION_MAX_TASKS,
    StudioBenchmarkLegacyMigrationConfirmRequestV1,
    StudioBenchmarkLegacyMigrationSourceRequestV1,
)
from zhixing.studio.benchmark_authoring_models import (
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkDraftCreateRequestV1,
)
from zhixing.studio.benchmark_authoring_repository import (
    SQLiteStudioBenchmarkAuthoringRepository,
)
from zhixing.studio.database import STUDIO_SQLITE_SCHEMA_VERSION


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
APP_AGENT_SOURCE = REPOSITORY_ROOT / "examples/benchmark_v1/app_agent.json"


def _task(
    task_id: str = "task-1",
    *,
    app: str | None = "clock",
    requires_login: bool | None = False,
) -> dict[str, Any]:
    """Build one standalone BenchmarkTask V1 mapping.

    Args:
        task_id: Stable task identity.
        app: Optional App declaration.
        requires_login: Optional explicit login fact; None omits the field.

    Raises:
        None.

    Returns:
        JSON-compatible canonical V1 task mapping.
    """
    value: dict[str, Any] = {
        "id": task_id,
        "instruction": "Complete the task",
        "type": "static",
        "task_initializer": {},
        "environment_initializer": [],
        "cleanup_initializer": [],
        "evaluator": {
            "name": "system_state",
            "params": {"method": "file_exist", "file_path": "/sdcard/result.txt"},
        },
    }
    if app is not None:
        value["app"] = app
    if requires_login is not None:
        value["requires_login"] = requires_login
    return value


def _payload(
    tasks: list[dict[str, Any]] | None = None,
    *,
    source_text: str | None = None,
) -> dict[str, Any]:
    """Build one complete strict Preview payload.

    Args:
        tasks: Optional source task array.
        source_text: Optional exact source override.

    Raises:
        None.

    Returns:
        JSON-compatible Preview request.
    """
    return {
        "schemaVersion": 1,
        "sourceName": "legacy.json",
        "sourceText": source_text or json.dumps(tasks or [_task()]),
        "target": {
            "draftName": "Imported legacy suite",
            "publisher": "local",
            "packageName": "legacy-suite",
            "version": "0.1.0",
            "title": "Imported legacy suite",
            "platform": "android",
            "split": "test",
            "taskFilePath": "tasks/imported.json",
        },
    }


def _request(payload: dict[str, Any] | None = None):
    """Parse one Preview request fixture.

    Args:
        payload: Optional request mapping override.

    Raises:
        ValidationError: Fixture is malformed.

    Returns:
        Strict source request.
    """
    return StudioBenchmarkLegacyMigrationSourceRequestV1.model_validate(
        payload or _payload()
    )


def _repository(database: Path) -> SQLiteStudioBenchmarkAuthoringRepository:
    """Create one deterministic repository for migration tests.

    Args:
        database: Temporary SQLite path.

    Raises:
        sqlite3.Error: Database migration fails.

    Returns:
        Ready authoring repository.
    """
    counters: dict[str, int] = {}

    def identity(prefix: str) -> str:
        """Produce one valid deterministic opaque identity.

        Args:
            prefix: Repository-selected resource prefix.

        Raises:
            None.

        Returns:
            Prefix plus a UUID-width hexadecimal suffix.
        """
        counters[prefix] = counters.get(prefix, 0) + 1
        return f"{prefix}-{counters[prefix]:032x}"

    return SQLiteStudioBenchmarkAuthoringRepository(
        database,
        clock=lambda: 1_000,
        identity_factory=identity,
    )


def _confirm_payload(
    service: StudioBenchmarkLegacyMigrationApplicationService,
    payload: dict[str, Any] | None = None,
    *,
    request_id: str = "migration-request-1",
) -> dict[str, Any]:
    """Build an exact Confirm payload from an authoritative Preview.

    Args:
        service: Migration service under test.
        payload: Optional source and target payload.
        request_id: Stable command identity.

    Raises:
        StudioBenchmarkError: Preview analysis fails unexpectedly.

    Returns:
        Complete exact Confirm request mapping.
    """
    selected = deepcopy(payload or _payload())
    preview = service.preview(service.parse_preview_request(selected))
    return {
        **selected,
        "clientRequestId": request_id,
        "previewFingerprint": preview.preview_fingerprint,
        "migrationContractIdentity": preview.migration_contract_identity,
    }


def test_migration_limits_and_request_envelope_are_strict() -> None:
    """Lock source/task/diagnostic bounds and reject path-shaped envelopes."""
    assert STUDIO_BENCHMARK_MIGRATION_MAX_SOURCE_BYTES == 1024 * 1024
    assert STUDIO_BENCHMARK_MIGRATION_MAX_TASKS == 100
    assert STUDIO_BENCHMARK_MIGRATION_MAX_DIAGNOSTICS == 100
    assert STUDIO_SQLITE_SCHEMA_VERSION == 12
    invalid = _payload()
    invalid["hostPath"] = "/tmp/legacy.json"
    with pytest.raises(ValidationError):
        StudioBenchmarkLegacyMigrationSourceRequestV1.model_validate(invalid)
    invalid = _payload()
    invalid["sourceName"] = "C:\\secret\\legacy.json"
    with pytest.raises(ValidationError):
        StudioBenchmarkLegacyMigrationSourceRequestV1.model_validate(invalid)


def test_preview_is_stable_and_preserves_raw_task_values_and_order() -> None:
    """Repeat Preview without changing task order, fields, or source identity."""
    tasks = [_task("b"), _task("a")]
    tasks[0]["extension"] = {"kept": [1, 2, 3]}
    source = json.dumps(tasks, indent=2)
    analyzer = StudioBenchmarkLegacyMigrationAnalyzer()
    first = analyzer.analyze(_request(_payload(source_text=source)))
    second = analyzer.analyze(_request(_payload(source_text=source)))
    assert first.preview == second.preview
    assert first.preview.confirmable is False  # strict V1 rejects extension fields

    accepted = [_task("b"), _task("a")]
    accepted_source = json.dumps(accepted, indent=2)
    result = analyzer.analyze(_request(_payload(source_text=accepted_source)))
    assert result.preview.confirmable is True
    assert result.candidate_document is not None
    assert list(result.candidate_document.task_files[0].tasks) == accepted
    assert result.preview.diff.task_changes.model_dump() == {
        "retained": 2,
        "renamed": 0,
        "removed": 0,
        "deduplicated": 0,
        "rewritten": 0,
    }


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("draftName", "Different draft"),
        ("publisher", "other"),
        ("packageName", "other-suite"),
        ("version", "0.2.0"),
        ("title", "Different title"),
        ("platform", "harmonyos"),
        ("split", "validation"),
        ("taskFilePath", "tasks/other.json"),
    ),
)
def test_every_target_field_changes_preview_authority(
    field: str,
    value: str,
) -> None:
    """Bind Preview authority to every semantic target field.

    Args:
        field: Target JSON key to change.
        value: Replacement valid value.

    Raises:
        None.

    Returns:
        None.
    """
    analyzer = StudioBenchmarkLegacyMigrationAnalyzer()
    original = _payload()
    changed = deepcopy(original)
    changed["target"][field] = value
    first = analyzer.analyze(_request(original)).preview
    second = analyzer.analyze(_request(changed)).preview
    assert first.preview_fingerprint != second.preview_fingerprint


def test_shared_reference_projection_covers_cleanup_and_composite_leaves() -> None:
    """Keep migration declaration traversal at compiler-reference parity."""
    task = _task()
    task["task_initializer"] = {
        "value": {"name": "random_choice", "params": {"candidates": ["x"]}}
    }
    task["instruction"] = "Use ${value}"
    task["environment_initializer"] = [
        {"name": "setup_app", "params": {}}
    ]
    task["cleanup_initializer"] = [
        {"name": "cleanup_app", "params": {}}
    ]
    task["evaluator"] = {
        "name": "composite",
        "params": {
            "logic": "AND",
            "rules": [
                {"name": "leaf", "params": {"method": "check_one"}},
                {"name": "leaf", "params": {"method": "check_two"}},
            ],
        },
    }
    preview = StudioBenchmarkLegacyMigrationAnalyzer().analyze(
        _request(_payload([task]))
    ).preview
    assert preview.confirmable is True
    assert preview.diff.plugin_ids == (
        "check_one",
        "check_two",
        "cleanup_app",
        "random_choice",
        "setup_app",
    )


def test_app_projection_is_conservative_and_true_dominates() -> None:
    """Declare only determined App login facts and surface unknown work."""
    tasks = [
        _task("a", app="mail", requires_login=None),
        _task("b", app="mail", requires_login=True),
        _task("c", app="clock", requires_login=False),
        _task("d", app="notes", requires_login=None),
    ]
    analysis = StudioBenchmarkLegacyMigrationAnalyzer().analyze(
        _request(_payload(tasks))
    )
    assert analysis.preview.confirmable is True
    assert analysis.candidate_document is not None
    apps = analysis.candidate_document.manifest.document["apps"]
    assert apps == [
        {"id": "clock", "platform": "android", "requires_login": False},
        {"id": "mail", "platform": "android", "requires_login": True},
    ]
    app_work = next(
        item
        for item in analysis.preview.post_migration_work
        if item.code == "benchmark.migration.work.app_login_unknown"
    )
    assert app_work.source_indexes == (3,)


@pytest.mark.parametrize(
    "source_text",
    (
        "{",
        "{}",
        "NaN",
        json.dumps([{**_task(), "task": "old-field"}]),
        json.dumps([{**_task(), "host_path": "/Users/private/value"}]),
    ),
)
def test_invalid_legacy_sources_have_no_candidate_authority(
    source_text: str,
) -> None:
    """Return safe bounded diagnostics and no confirm authority.

    Args:
        source_text: Malformed, pre-V1, or unsafe source text.

    Raises:
        None.

    Returns:
        None.
    """
    result = StudioBenchmarkLegacyMigrationAnalyzer().analyze(
        _request(_payload(source_text=source_text))
    )
    assert result.preview.confirmable is False
    assert result.preview.preview_fingerprint is None
    assert result.preview.candidate_document_fingerprint is None
    assert result.candidate_document is None
    assert len(result.preview.diagnostics) <= 100
    serialized = json.dumps(result.preview.model_dump(mode="json", by_alias=True))
    assert '"sourceText"' not in serialized


def test_101_tasks_and_duplicate_ids_are_never_silently_changed() -> None:
    """Reject capacity and duplicate cases with explicit zero mutation counts."""
    analyzer = StudioBenchmarkLegacyMigrationAnalyzer()
    over_limit = analyzer.analyze(
        _request(_payload([_task(f"task-{index}") for index in range(101)]))
    ).preview
    assert over_limit.confirmable is False
    assert over_limit.source.entry_count == 101
    assert over_limit.preview_fingerprint is None

    duplicate = analyzer.analyze(
        _request(_payload([_task("same"), _task("same")]))
    ).preview
    assert duplicate.confirmable is False
    assert duplicate.source.entry_count == 2
    assert duplicate.source.unique_task_count == 1
    assert duplicate.diff.task_changes.retained == 2
    assert duplicate.diff.task_changes.deduplicated == 0
    assert duplicate.diagnostics[-1].source_index == 1


def test_appagent_fixture_and_androidworld_duplicate_boundary_are_exact() -> None:
    """Prove the tracked 45-task fixture and 82-entry duplicate boundary."""
    analyzer = StudioBenchmarkLegacyMigrationAnalyzer()
    app_source = APP_AGENT_SOURCE.read_text(encoding="utf-8")
    app_payload = _payload(source_text=app_source)
    app_payload["sourceName"] = APP_AGENT_SOURCE.name
    app = analyzer.analyze(_request(app_payload)).preview
    assert app.confirmable is True
    assert (app.source.entry_count, app.source.unique_task_count) == (45, 45)

    world_tasks = [_task(f"AndroidWorld_{index}") for index in range(82)]
    world_tasks[71] = _task("AndroidWorld_72")
    world_payload = _payload(tasks=world_tasks)
    world_payload["sourceName"] = "android_world_duplicate_boundary.json"
    world = analyzer.analyze(_request(world_payload)).preview
    assert world.confirmable is False
    assert (world.source.entry_count, world.source.unique_task_count) == (82, 81)
    duplicate = next(
        item
        for item in world.diagnostics
        if item.code == "benchmark.migration.task_id_duplicate"
    )
    assert (duplicate.source_index, duplicate.task_id) == (72, "AndroidWorld_72")


def test_preview_has_no_repository_access_and_false_evidence() -> None:
    """Make Preview succeed while every durable repository method fails fast."""

    class NoRepository:
        """Repository canary that fails on every attribute access."""

        def __getattr__(self, name: str) -> Any:
            """Reject every capability lookup.

            Args:
                name: Requested repository attribute.

            Raises:
                AssertionError: Preview attempted durable access.

            Returns:
                Never returns.
            """
            raise AssertionError(f"unexpected repository access: {name}")

    service = StudioBenchmarkLegacyMigrationApplicationService(
        repository=NoRepository()  # type: ignore[arg-type]
    )
    preview = service.preview(service.parse_preview_request(_payload()))
    assert preview.confirmable is True
    assert set(preview.evidence.model_dump().values()) == {False}


def test_confirm_is_atomic_idempotent_stale_aware_and_restart_safe(
    tmp_path: Path,
) -> None:
    """Create once, replay exactly, reject drift, and reconstruct on restart.

    Args:
        tmp_path: Pytest temporary workspace.

    Raises:
        None.

    Returns:
        None.
    """
    database = tmp_path / "studio.sqlite3"
    repository = _repository(database)
    service = StudioBenchmarkLegacyMigrationApplicationService(
        repository=repository
    )
    payload = _confirm_payload(service)
    request = service.parse_confirm_request(payload)
    first = service.confirm(request)
    replay = service.confirm(request)
    assert first.created is True
    assert replay.created is False
    assert replay.draft == first.draft
    assert replay.revision == first.revision
    assert first.revision.ordinal == 1
    assert first.revision.status == "unvalidated"
    assert first.revision.provenance.source_kind == "legacy_migration"

    changed = deepcopy(payload)
    changed["target"]["title"] = "Drifted"
    with pytest.raises(StudioBenchmarkAuthoringIdempotencyConflictError):
        service.confirm(service.parse_confirm_request(changed))

    stale = deepcopy(payload)
    stale["clientRequestId"] = "migration-request-2"
    stale["previewFingerprint"] = "sha256:" + "f" * 64
    with pytest.raises(StudioBenchmarkAuthoringDriftError):
        service.confirm(service.parse_confirm_request(stale))

    restarted = StudioBenchmarkLegacyMigrationApplicationService(
        repository=SQLiteStudioBenchmarkAuthoringRepository(database)
    )
    after_restart = restarted.confirm(
        restarted.parse_confirm_request(payload)
    )
    assert after_restart.created is False
    assert after_restart.revision == first.revision
    assert APP_AGENT_SOURCE.as_posix() not in json.dumps(
        after_restart.model_dump(mode="json", by_alias=True)
    )


def test_contract_change_and_nonconfirmable_source_fail_before_create(
    tmp_path: Path,
) -> None:
    """Reject stale transformation authority and duplicate source before write.

    Args:
        tmp_path: Pytest temporary workspace.

    Raises:
        None.

    Returns:
        None.
    """
    repository = _repository(tmp_path / "studio.sqlite3")
    service = StudioBenchmarkLegacyMigrationApplicationService(
        repository=repository
    )
    payload = _confirm_payload(service)
    payload["migrationContractIdentity"] = "sha256:" + "e" * 64
    with pytest.raises(StudioBenchmarkAuthoringDriftError):
        service.confirm(service.parse_confirm_request(payload))

    duplicate_payload = _payload([_task("same"), _task("same")])
    duplicate_payload.update(
        {
            "clientRequestId": "duplicate-confirm",
            "previewFingerprint": "sha256:" + "a" * 64,
            "migrationContractIdentity": STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY,
        }
    )
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        service.confirm(service.parse_confirm_request(duplicate_payload))
    assert repository.list_drafts().items == ()


def test_repository_failure_exposes_no_partial_migration_authority(
    tmp_path: Path,
) -> None:
    """Roll back command, draft, revision, provenance, and current pointer."""
    database = tmp_path / "studio.sqlite3"
    repository = _repository(database)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TRIGGER fail_migration_revision
            BEFORE INSERT ON studio_benchmark_authoring_revisions
            BEGIN SELECT RAISE(ABORT, 'injected migration failure'); END
            """
        )
    service = StudioBenchmarkLegacyMigrationApplicationService(
        repository=repository
    )
    payload = _confirm_payload(service)
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        service.confirm(service.parse_confirm_request(payload))
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_authoring_drafts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_authoring_revisions"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_authoring_commands"
        ).fetchone()[0] == 0


def test_original_fixture_digest_and_ordinary_create_union_remain_unchanged(
    tmp_path: Path,
) -> None:
    """Prove source-file immutability and keep direct create-source union closed."""
    before = hashlib.sha256(APP_AGENT_SOURCE.read_bytes()).hexdigest()
    repository = _repository(tmp_path / "studio.sqlite3")
    service = StudioBenchmarkLegacyMigrationApplicationService(
        repository=repository
    )
    source = APP_AGENT_SOURCE.read_text(encoding="utf-8")
    payload = _payload(source_text=source)
    payload["sourceName"] = APP_AGENT_SOURCE.name
    confirm = _confirm_payload(service, payload)
    service.confirm(service.parse_confirm_request(confirm))
    assert hashlib.sha256(APP_AGENT_SOURCE.read_bytes()).hexdigest() == before

    with pytest.raises(ValidationError):
        StudioBenchmarkDraftCreateRequestV1.model_validate(
            {
                "schemaVersion": 1,
                "clientRequestId": "bypass",
                "name": "Bypass",
                "source": {
                    "kind": "legacy_migration",
                    "sourceText": source,
                    "previewFingerprint": confirm["previewFingerprint"],
                },
            }
        )


def test_existing_provenance_variants_stay_strict_and_migration_round_trips() -> None:
    """Preserve template/edit parsing while serializing bounded migration facts."""
    assert StudioBenchmarkAuthoringProvenanceV1(
        source_kind="template",
        template_name="minimal",
    ).source_kind == "template"
    assert StudioBenchmarkAuthoringProvenanceV1(
        source_kind="edit"
    ).source_kind == "edit"
    migration = StudioBenchmarkAuthoringProvenanceV1(
        source_kind="legacy_migration",
        source_display_name="legacy.json",
        source_fingerprint="sha256:" + "1" * 64,
        preview_fingerprint="sha256:" + "2" * 64,
        candidate_document_fingerprint="sha256:" + "3" * 64,
        migration_contract_identity=STUDIO_BENCHMARK_MIGRATION_CONTRACT_IDENTITY,
        task_entry_count=1,
        unique_task_count=1,
    )
    restored = StudioBenchmarkAuthoringProvenanceV1.model_validate_json(
        migration.model_dump_json(by_alias=True, exclude_none=True)
    )
    assert restored == migration
