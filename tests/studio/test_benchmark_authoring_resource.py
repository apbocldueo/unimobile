"""Studio Benchmark authoring resource contracts and backend journeys."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import BytesIO
import json
import sqlite3
from threading import Barrier

import pytest
from pydantic import ValidationError

from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringDriftError,
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from zhixing.studio.benchmark_authoring_import import (
    StudioBenchmarkAuthoringPackageAdapter,
)
from zhixing.studio.benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS,
    STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS,
    STUDIO_BENCHMARK_AUTHORING_MAX_PAGE_SIZE,
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES,
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringProvenanceV1,
    StudioBenchmarkDraftCreateRequestV1,
    StudioBenchmarkTemplateDraftSourceV1,
)
from zhixing.studio.benchmark_authoring_repository import (
    SQLiteStudioBenchmarkAuthoringRepository,
)
from zhixing.studio.benchmark_authoring_service import (
    StudioBenchmarkAuthoringApplicationService,
)
from zhixing.studio.database import STUDIO_SQLITE_SCHEMA_VERSION
from zhixing.studio.benchmark_authoring_storage import (
    LocalStudioBenchmarkManagedContent,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_service import (
    StudioBenchmarkAuthoringCatalogSource,
    StudioBenchmarkCatalogService,
    StudioBenchmarkSource,
)

from .benchmark_fixtures import write_studio_benchmark_package


def authoring_document_payload() -> dict[str, object]:
    """Return one safe semantically incomplete authoring document.

    Returns:
        JSON-compatible authoring document payload.
    """
    return {
        "schemaVersion": 1,
        "status": "unvalidated",
        "manifest": {
            "path": "benchmark.yaml",
            "document": {
                "schema_version": "1.0",
                "identity": {
                    "publisher": "local",
                    "name": "example",
                    "version": "0.1.0",
                },
                "title": "Example",
                "splits": {"test": {"files": ["tasks/test.json"]}},
                "ground_truth": {},
            },
        },
        "taskFiles": [
            {
                "path": "tasks/test.json",
                "tasks": [
                    {
                        "id": "incomplete-task",
                        "evaluator": {
                            "name": "system_state",
                            "params": {"file_path": "/sdcard/example.txt"},
                        },
                    }
                ],
            }
        ],
        "protocolFiles": [
            {
                "path": "protocols/default.yaml",
                "document": {"schema_version": "1.0", "seed": 0},
            }
        ],
        "resources": [],
        "directories": ["assets", "ground_truth"],
    }


def test_authoring_document_is_safe_versioned_and_deterministic() -> None:
    """Accept safe incomplete content and derive stable presentation-free identity."""
    first = StudioBenchmarkAuthoringDocumentV1.model_validate(
        authoring_document_payload()
    )
    second = StudioBenchmarkAuthoringDocumentV1.model_validate(
        deepcopy(authoring_document_payload())
    )
    assert first.status == "unvalidated"
    assert first.fingerprint == second.fingerprint
    assert first.task_files[0].tasks[0]["evaluator"]["params"]["file_path"] == (
        "/sdcard/example.txt"
    )


@pytest.mark.parametrize(
    ("path", "value"),
    (
        (
            ("taskFiles", 0, "tasks", 0, "host_path"),
            "/Users/example/private.txt",
        ),
        (
            ("taskFiles", 0, "tasks", 0, "password"),
            "resolved-value",
        ),
        (
            ("protocolFiles", 0, "document", "ratio"),
            float("nan"),
        ),
    ),
)
def test_authoring_document_rejects_unsafe_nested_values(
    path: tuple[str | int, ...],
    value: object,
) -> None:
    """Reject host paths, resolved secrets, and non-finite values."""
    payload = authoring_document_payload()
    current: object = payload
    for part in path[:-1]:
        current = current[part]  # type: ignore[index]
    current[path[-1]] = value  # type: ignore[index]
    with pytest.raises(ValidationError):
        StudioBenchmarkAuthoringDocumentV1.model_validate(payload)


def test_authoring_document_rejects_duplicate_or_unsorted_inventory() -> None:
    """Require one deterministic closed logical member inventory."""
    payload = authoring_document_payload()
    payload["taskFiles"] = [
        {"path": "tasks/z.json", "tasks": []},
        {"path": "tasks/a.json", "tasks": []},
    ]
    with pytest.raises(ValidationError, match="deterministic path order"):
        StudioBenchmarkAuthoringDocumentV1.model_validate(payload)


def test_authoring_create_union_rejects_paths_and_unknown_fields() -> None:
    """Accept only a strict template or opaque Catalog source union."""
    with pytest.raises(ValidationError):
        StudioBenchmarkDraftCreateRequestV1.model_validate(
            {
                "schemaVersion": 1,
                "clientRequestId": "request-1",
                "name": "Draft",
                "source": {
                    "kind": "catalog",
                    "catalogEntryId": "benchmark-entry-" + "a" * 32,
                    "path": "/tmp/package",
                },
            }
        )


def test_authoring_limits_are_explicit_and_monotonic() -> None:
    """Lock the first resource slice's bounded capacity constants."""
    assert STUDIO_BENCHMARK_AUTHORING_MAX_PAGE_SIZE == 100
    assert STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS == 100
    assert STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS == 256
    assert STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES == 2 * 1024 * 1024
    assert STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES == 64 * 1024 * 1024
    assert STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES == 256 * 1024 * 1024


def _identity_sequence() -> object:
    """Return a deterministic valid repository identity factory.

    Returns:
        Callable producing prefix-compatible opaque identities.
    """
    counts: dict[str, int] = {}

    def factory(prefix: str) -> str:
        """Produce a deterministic UUID-width identity.

        Args:
            prefix: Requested public resource prefix.

        Returns:
            Stable test identity.
        """
        counts[prefix] = counts.get(prefix, 0) + 1
        return f"{prefix}-{counts[prefix]:032x}"

    return factory


def _repository(database, *, clock=None, identity_factory=None):
    """Build a deterministic SQLite authoring repository.

    Args:
        database: Temporary SQLite path.
        clock: Optional millisecond clock.
        identity_factory: Optional opaque identity factory.

    Returns:
        Configured SQLite repository.
    """
    return SQLiteStudioBenchmarkAuthoringRepository(
        database,
        clock=clock or (lambda: 1000),
        identity_factory=identity_factory or _identity_sequence(),
    )


def _create_repository_draft(repository, request: str = "create-1"):
    """Create one durable template-provenance draft.

    Args:
        repository: Authoring repository under test.
        request: Client request identity.

    Returns:
        Draft and initial revision.
    """
    document = StudioBenchmarkAuthoringDocumentV1.model_validate(
        authoring_document_payload()
    )
    draft, revision, created = repository.create_draft(
        client_request_id=request,
        request_fingerprint="sha256:" + "1" * 64,
        name="Example Draft",
        document=document,
        provenance=StudioBenchmarkAuthoringProvenanceV1(
            source_kind="template",
            template_name="minimal",
            package_identity="local/example@0.1.0",
        ),
    )
    assert created
    return draft, revision


def test_authoring_sqlite_migration_is_additive_and_complete(tmp_path) -> None:
    """Create schema 8 authoring tables without dropping prior Studio tables."""
    database = tmp_path / "studio.sqlite3"
    _repository(database)
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
    assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))
    assert "studio_agents" in tables
    assert "studio_benchmark_experiments" in tables
    assert "studio_benchmark_authoring_drafts" in tables
    assert "studio_benchmark_authoring_revisions" in tables
    assert "studio_benchmark_authoring_commands" in tables


def test_repository_reconstructs_revisions_and_detects_stale_base(tmp_path) -> None:
    """Persist append-only revisions across restart and reject stale writers."""
    database = tmp_path / "studio.sqlite3"
    repository = _repository(database)
    draft, first = _create_repository_draft(repository)
    changed_payload = authoring_document_payload()
    changed_payload["manifest"]["document"]["title"] = "Changed"  # type: ignore[index]
    changed = StudioBenchmarkAuthoringDocumentV1.model_validate(changed_payload)
    updated, second, created = repository.save_revision(
        draft.draft_id,
        client_request_id="save-1",
        request_fingerprint="sha256:" + "2" * 64,
        base_revision_id=first.revision_id,
        document=changed,
        provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
    )
    assert created
    assert updated.current_revision_id == second.revision_id
    assert second.ordinal == 2
    assert second.parent_revision_id == first.revision_id

    with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError) as captured:
        repository.save_revision(
            draft.draft_id,
            client_request_id="save-stale",
            request_fingerprint="sha256:" + "3" * 64,
            base_revision_id=first.revision_id,
            document=changed,
            provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
        )
    assert captured.value.current_revision_id == second.revision_id

    restarted = _repository(database)
    assert restarted.get_draft(draft.draft_id).current_revision_id == (
        second.revision_id
    )
    assert restarted.get_revision(draft.draft_id, first.revision_id).ordinal == 1
    assert restarted.get_revision(draft.draft_id, second.revision_id).document == (
        changed
    )


def test_repository_idempotency_precedes_revision_conflict(tmp_path) -> None:
    """Return successful retries even though their former base is now stale."""
    repository = _repository(tmp_path / "studio.sqlite3")
    draft, first = _create_repository_draft(repository)
    document = StudioBenchmarkAuthoringDocumentV1.model_validate(
        authoring_document_payload()
    )
    _updated, second, created = repository.save_revision(
        draft.draft_id,
        client_request_id="save-1",
        request_fingerprint="sha256:" + "2" * 64,
        base_revision_id=first.revision_id,
        document=document,
        provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
    )
    assert created
    retried_draft, retried, retried_created = repository.save_revision(
        draft.draft_id,
        client_request_id="save-1",
        request_fingerprint="sha256:" + "2" * 64,
        base_revision_id=first.revision_id,
        document=document,
        provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
    )
    assert not retried_created
    assert retried.revision_id == second.revision_id
    assert retried_draft.current_revision_id == second.revision_id
    with pytest.raises(StudioBenchmarkAuthoringIdempotencyConflictError):
        repository.save_revision(
            draft.draft_id,
            client_request_id="save-1",
            request_fingerprint="sha256:" + "9" * 64,
            base_revision_id=second.revision_id,
            document=document,
            provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
        )


def test_repository_create_retry_and_bounded_cursor(tmp_path) -> None:
    """Keep create retries stable and list drafts with an opaque cursor."""
    ticks = iter((1000, 2000))
    repository = _repository(
        tmp_path / "studio.sqlite3",
        clock=lambda: next(ticks),
    )
    first_draft, first_revision = _create_repository_draft(repository, "one")
    second_draft, _ = _create_repository_draft(repository, "two")
    retry = repository.create_draft(
        client_request_id="one",
        request_fingerprint="sha256:" + "1" * 64,
        name="Ignored Retry Name",
        document=StudioBenchmarkAuthoringDocumentV1.model_validate(
            authoring_document_payload()
        ),
        provenance=StudioBenchmarkAuthoringProvenanceV1(
            source_kind="template",
            template_name="minimal",
            package_identity="local/example@0.1.0",
        ),
    )
    assert not retry[2]
    assert retry[0].draft_id == first_draft.draft_id
    assert retry[1].revision_id == first_revision.revision_id
    page = repository.list_drafts(limit=1)
    assert page.items[0].draft_id == second_draft.draft_id
    assert page.next_cursor is not None
    next_page = repository.list_drafts(limit=1, cursor=page.next_cursor)
    assert next_page.items == (first_draft,)


def test_repository_hides_cross_draft_revision_ownership(tmp_path) -> None:
    """Return the same not-found result for absent and foreign revisions."""
    repository = _repository(tmp_path / "studio.sqlite3")
    first_draft, first_revision = _create_repository_draft(repository, "one")
    second_draft, _ = _create_repository_draft(repository, "two")
    assert first_draft.draft_id != second_draft.draft_id
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        repository.get_revision(second_draft.draft_id, first_revision.revision_id)


def test_repository_failed_insert_preserves_current_revision(tmp_path) -> None:
    """Roll back revision and pointer when an immutable insert fails."""
    database = tmp_path / "studio.sqlite3"
    first_factory = _identity_sequence()
    repository = _repository(database, identity_factory=first_factory)
    draft, first = _create_repository_draft(repository)

    def duplicate_revision(prefix: str) -> str:
        """Return the existing revision identity to force a PK conflict.

        Args:
            prefix: Requested identity prefix.

        Returns:
            Existing revision identity.
        """
        assert prefix == "benchmark-authoring-revision"
        return first.revision_id

    failing = _repository(database, identity_factory=duplicate_revision)
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        failing.save_revision(
            draft.draft_id,
            client_request_id="save-fail",
            request_fingerprint="sha256:" + "7" * 64,
            base_revision_id=first.revision_id,
            document=StudioBenchmarkAuthoringDocumentV1.model_validate(
                authoring_document_payload()
            ),
            provenance=StudioBenchmarkAuthoringProvenanceV1(source_kind="edit"),
        )
    assert failing.get_draft(draft.draft_id).current_revision_id == first.revision_id
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_authoring_revisions "
            "WHERE draft_id = ?",
            (draft.draft_id,),
        ).fetchone()[0] == 1


def test_repository_serializes_concurrent_writers_on_one_base(tmp_path) -> None:
    """Allow exactly one of two simultaneous saves from the same base."""
    repository = SQLiteStudioBenchmarkAuthoringRepository(
        tmp_path / "studio.sqlite3"
    )
    draft, first = _create_repository_draft(repository)
    document = StudioBenchmarkAuthoringDocumentV1.model_validate(
        authoring_document_payload()
    )
    barrier = Barrier(2)

    def save(request_id: str) -> str:
        """Race one save after both workers are ready.

        Args:
            request_id: Unique command identity.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Other writer wins.

        Returns:
            Created revision identity.
        """
        barrier.wait()
        return repository.save_revision(
            draft.draft_id,
            client_request_id=request_id,
            request_fingerprint="sha256:" + request_id[-1] * 64,
            base_revision_id=first.revision_id,
            document=document,
            provenance=StudioBenchmarkAuthoringProvenanceV1(
                source_kind="edit"
            ),
        )[1].revision_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(save, "concurrent-1"),
            executor.submit(save, "concurrent-2"),
        ]
    outcomes: list[str] = []
    conflicts = 0
    for future in futures:
        try:
            outcomes.append(future.result())
        except StudioBenchmarkAuthoringRevisionConflictError:
            conflicts += 1
    assert len(outcomes) == 1
    assert conflicts == 1
    assert repository.get_draft(draft.draft_id).current_revision_id == (
        outcomes[0]
    )


def _package_adapter(tmp_path):
    """Build one private managed content and Package adapter pair.

    Args:
        tmp_path: Temporary test root.

    Returns:
        Content store and Package adapter.
    """
    root = default_studio_benchmark_authoring_root(
        tmp_path / "studio.sqlite3"
    )
    content = LocalStudioBenchmarkManagedContent(root)
    return content, StudioBenchmarkAuthoringPackageAdapter(
        content,
        staging_root=content.staging_root,
    )


def test_managed_content_is_bounded_atomic_and_deduplicated(tmp_path) -> None:
    """Deduplicate equal bytes and remove temporary files on bounded failure."""
    content, _adapter = _package_adapter(tmp_path)
    first = content.store_stream(BytesIO(b"fixture"), max_bytes=7)
    second = content.store_stream(BytesIO(b"fixture"), max_bytes=7)
    assert first == second
    assert content.content_path(first[0]).read_bytes() == b"fixture"
    with pytest.raises(StudioBenchmarkAuthoringCapacityError):
        content.store_stream(BytesIO(b"too-large"), max_bytes=3)
    assert not tuple(content.staging_root.glob(".content-*"))
    assert all(
        str(content.root) not in value
        for value in first
        if isinstance(value, str)
    )


@pytest.mark.parametrize(
    "template",
    ("minimal", "dynamic-task", "composite-evaluation"),
)
def test_template_adapter_reuses_scaffold_in_private_staging(
    tmp_path,
    template: str,
) -> None:
    """Ingest every existing scaffold without accepting a caller destination."""
    content, adapter = _package_adapter(tmp_path)
    prepared = adapter.from_template(
        StudioBenchmarkTemplateDraftSourceV1(
            template=template,
            publisher="tests",
            package_name=f"{template}-draft",
            version="0.1.0",
        )
    )
    assert prepared.package_identity == f"tests/{template}-draft@0.1.0"
    assert prepared.document.task_files[0].path == "tasks/test.json"
    assert prepared.document.protocol_files[0].path == (
        "protocols/default.yaml"
    )
    assert prepared.document.resources == ()
    assert list(content.staging_root.iterdir()) == []


def test_catalog_import_copies_only_declared_closure_and_preserves_source(
    tmp_path,
) -> None:
    """Ignore undeclared files, manage resource bytes, and never mutate source."""
    package = write_studio_benchmark_package(tmp_path / "package")
    undeclared = package / ".private-tooling"
    undeclared.write_text("must-not-be-imported", encoding="utf-8")
    before = {
        path.relative_to(package).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in package.rglob("*")
        if path.is_file()
    }
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-source",
                kind="package",
                locator=package,
            ),
        )
    )
    source = catalog.resolve_authoring_source(
        catalog.list_entries().items[0].catalog_entry_id
    )
    content, adapter = _package_adapter(tmp_path)
    prepared = adapter.from_catalog(source)
    resource = prepared.document.resources[0]
    assert resource.path == "assets/fixture.txt"
    assert content.content_path(resource.content_identity).read_text(
        encoding="utf-8"
    ) == "fixture\n"
    assert "must-not-be-imported" not in json.dumps(
        prepared.document.model_dump(mode="json"),
        sort_keys=True,
    )
    after = {
        path.relative_to(package).as_posix(): (
            path.read_bytes(),
            path.stat().st_mtime_ns,
        )
        for path in package.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_catalog_import_rejects_symlink_and_hides_host_path(tmp_path) -> None:
    """Fail closed when a declared member is a source-tree symlink."""
    package = write_studio_benchmark_package(tmp_path / "package")
    original = package / "tasks" / "test.json"
    linked = package / "tasks" / "linked.json"
    linked.symlink_to(original.name)
    manifest_path = package / "benchmark.yaml"
    manifest_text = manifest_path.read_text(encoding="utf-8").replace(
        "tasks/test.json",
        "tasks/linked.json",
    )
    manifest_path.write_text(manifest_text, encoding="utf-8")
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-source",
                kind="package",
                locator=package,
            ),
        )
    )
    source = catalog.resolve_authoring_source(
        catalog.list_entries().items[0].catalog_entry_id
    )
    _content, adapter = _package_adapter(tmp_path)
    with pytest.raises(
        StudioBenchmarkAuthoringValidationError
    ) as captured:
        adapter.from_catalog(source)
    assert str(package) not in str(captured.value)


def test_catalog_import_detects_post_snapshot_definition_drift(tmp_path) -> None:
    """Reject a Catalog entry whose task semantics changed after discovery."""
    package = write_studio_benchmark_package(tmp_path / "package")
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-source",
                kind="package",
                locator=package,
            ),
        )
    )
    source = catalog.resolve_authoring_source(
        catalog.list_entries().items[0].catalog_entry_id
    )
    task_path = package / "tasks" / "test.json"
    tasks = json.loads(task_path.read_text(encoding="utf-8"))
    tasks[0]["instruction"] = "Changed after Catalog snapshot"
    task_path.write_text(json.dumps(tasks), encoding="utf-8")
    _content, adapter = _package_adapter(tmp_path)
    with pytest.raises(StudioBenchmarkAuthoringDriftError):
        adapter.from_catalog(source)


@pytest.mark.parametrize(
    "unsafe_path",
    ("/tmp/escape.json", "../escape.json", "tasks/../escape.json"),
)
def test_catalog_import_rejects_absolute_and_traversing_members(
    tmp_path,
    unsafe_path: str,
) -> None:
    """Reject unsafe declared paths before opening caller-selected locations."""
    package = write_studio_benchmark_package(tmp_path / "package")
    manifest_path = package / "benchmark.yaml"
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "tasks/test.json",
            unsafe_path,
        ),
        encoding="utf-8",
    )
    source = StudioBenchmarkAuthoringCatalogSource(
        catalog_entry_id="benchmark-entry-" + "a" * 32,
        catalog_snapshot_identity="sha256:" + "b" * 64,
        package_identity="tests/fixture@1.0.0",
        package_content_identity="sha256:" + "c" * 64,
        protocol_identity=None,
        root=package,
    )
    _content, adapter = _package_adapter(tmp_path)
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        adapter.from_catalog(source)


def test_managed_content_atomic_finalize_failure_leaves_no_object(
    tmp_path,
    monkeypatch,
) -> None:
    """Clean staged bytes when atomic finalization fails."""
    content, _adapter = _package_adapter(tmp_path)

    def fail_replace(source, destination) -> None:
        """Inject one atomic-finalization storage failure.

        Args:
            source: Temporary object path.
            destination: Digest-addressed destination.

        Raises:
            OSError: Always.

        Returns:
            None.
        """
        del source, destination
        raise OSError("injected atomic failure")

    monkeypatch.setattr(
        "zhixing.studio.benchmark_authoring_storage.os.replace",
        fail_replace,
    )
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        content.store_stream(BytesIO(b"fixture"), max_bytes=100)
    assert not tuple(content.staging_root.glob(".content-*"))
    assert not tuple(
        path
        for path in (content.root / "objects").rglob("*")
        if path.is_file()
    )


@pytest.mark.parametrize(
    ("constant", "limit"),
    (
        ("STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS", 2),
        ("STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES", 100),
        ("STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES", 3),
        ("STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES", 10),
    ),
)
def test_catalog_import_enforces_every_closure_capacity(
    tmp_path,
    monkeypatch,
    constant: str,
    limit: int,
) -> None:
    """Fail before draft persistence for every centralized import bound."""
    package = write_studio_benchmark_package(tmp_path / "package")
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-source",
                kind="package",
                locator=package,
            ),
        )
    )
    source = catalog.resolve_authoring_source(
        catalog.list_entries().items[0].catalog_entry_id
    )
    monkeypatch.setattr(
        f"zhixing.studio.benchmark_authoring_import.{constant}",
        limit,
    )
    _content, adapter = _package_adapter(tmp_path)
    with pytest.raises(StudioBenchmarkAuthoringCapacityError):
        adapter.from_catalog(source)


def test_catalog_import_rejects_missing_declared_bytes(tmp_path) -> None:
    """Fail safely when a formerly available declared resource disappears."""
    package = write_studio_benchmark_package(tmp_path / "package")
    catalog = StudioBenchmarkCatalogService(
        (
            StudioBenchmarkSource(
                source_id="fixture-source",
                kind="package",
                locator=package,
            ),
        )
    )
    source = catalog.resolve_authoring_source(
        catalog.list_entries().items[0].catalog_entry_id
    )
    (package / "assets" / "fixture.txt").unlink()
    _content, adapter = _package_adapter(tmp_path)
    with pytest.raises(StudioBenchmarkAuthoringStorageError) as captured:
        adapter.from_catalog(source)
    assert str(package) not in str(captured.value)


def _authoring_service(tmp_path, *, package=None):
    """Build a real no-device authoring service with optional Catalog source.

    Args:
        tmp_path: Temporary persistence root.
        package: Optional explicit Benchmark Package.

    Returns:
        Service, repository, content store, and Catalog.
    """
    sources = (
        (
            StudioBenchmarkSource(
                source_id="fixture-source",
                kind="package",
                locator=package,
            ),
        )
        if package is not None
        else ()
    )
    catalog = StudioBenchmarkCatalogService(sources)
    repository = _repository(tmp_path / "studio.sqlite3")
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(repository.database_path)
    )
    packages = StudioBenchmarkAuthoringPackageAdapter(
        content,
        staging_root=content.staging_root,
    )
    return (
        StudioBenchmarkAuthoringApplicationService(
            repository=repository,
            packages=packages,
            catalog=catalog,
        ),
        repository,
        content,
        catalog,
    )


def _template_create_payload(request_id: str = "create-template"):
    """Return one strict template create payload.

    Args:
        request_id: Client command identity.

    Returns:
        JSON-compatible request mapping.
    """
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "name": "Template Draft",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "studio-draft",
            "version": "0.1.0",
        },
    }


def test_authoring_service_template_create_save_reopen_and_restart(
    tmp_path,
) -> None:
    """Exercise the complete template resource journey across service restart."""
    service, repository, _content, catalog = _authoring_service(tmp_path)
    created = service.create_draft(_template_create_payload())
    assert created.created
    detail = service.get_draft(created.draft.draft_id)
    assert detail.current_revision == created.revision
    assert service.get_revision(
        created.draft.draft_id,
        created.revision.revision_id,
    ) == created.revision
    payload = created.revision.document.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    payload["manifest"]["document"]["title"] = "Edited title"
    saved = service.save_revision(
        created.draft.draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "save-template",
            "baseRevisionId": created.revision.revision_id,
            "document": payload,
        },
    )
    assert saved.created
    assert saved.revision.ordinal == 2
    assert service.list_drafts().items == (saved.draft,)

    restarted_content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(repository.database_path)
    )
    restarted = StudioBenchmarkAuthoringApplicationService(
        repository=_repository(repository.database_path),
        packages=StudioBenchmarkAuthoringPackageAdapter(
            restarted_content,
            staging_root=restarted_content.staging_root,
        ),
        catalog=catalog,
    )
    assert restarted.get_draft(created.draft.draft_id).current_revision == (
        saved.revision
    )
    retried = restarted.save_revision(
        created.draft.draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "save-template",
            "baseRevisionId": created.revision.revision_id,
            "document": payload,
        },
    )
    assert not retried.created
    assert retried.revision == saved.revision


def test_authoring_service_catalog_retry_does_not_reread_drifted_source(
    tmp_path,
) -> None:
    """Return durable create retry after its former Catalog source changes."""
    package = write_studio_benchmark_package(tmp_path / "package")
    service, _repository_value, _content, catalog = _authoring_service(
        tmp_path,
        package=package,
    )
    entry_id = catalog.list_entries().items[0].catalog_entry_id
    payload = {
        "schemaVersion": 1,
        "clientRequestId": "catalog-create",
        "name": "Imported Draft",
        "source": {
            "kind": "catalog",
            "catalogEntryId": entry_id,
        },
    }
    created = service.create_draft(payload)
    assert created.created
    assert created.revision.provenance.catalog_entry_id == entry_id
    (package / "tasks" / "test.json").write_text(
        "not valid JSON any more",
        encoding="utf-8",
    )
    retried = service.create_draft(payload)
    assert not retried.created
    assert retried.draft == created.draft
    assert retried.revision == created.revision


def test_authoring_service_accepts_safe_semantically_incomplete_save(
    tmp_path,
) -> None:
    """Commit parsed intermediate content without claiming Core validity."""
    service, _repository_value, _content, _catalog = _authoring_service(
        tmp_path
    )
    created = service.create_draft(_template_create_payload())
    saved = service.save_revision(
        created.draft.draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "save-incomplete",
            "baseRevisionId": created.revision.revision_id,
            "document": authoring_document_payload(),
        },
    )
    assert saved.created
    assert saved.revision.status == "unvalidated"
    assert saved.revision.document.task_files[0].tasks[0]["id"] == (
        "incomplete-task"
    )


def test_authoring_service_rejects_unknown_source_and_conflicting_retry(
    tmp_path,
) -> None:
    """Reject browser paths and unequal reuse without another revision."""
    service, _repository_value, _content, _catalog = _authoring_service(
        tmp_path
    )
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        service.create_draft(
            {
                **_template_create_payload(),
                "source": {
                    "kind": "template",
                    "template": "minimal",
                    "publisher": "tests",
                    "packageName": "studio-draft",
                    "destination": "/tmp/browser-selected",
                },
            }
        )
    created = service.create_draft(_template_create_payload())
    conflicting = _template_create_payload()
    conflicting["name"] = "Different"
    with pytest.raises(StudioBenchmarkAuthoringIdempotencyConflictError):
        service.create_draft(conflicting)
    assert service.list_drafts().items == (created.draft,)


def test_complete_authoring_journey_never_crosses_runtime_boundaries(
    tmp_path,
    monkeypatch,
) -> None:
    """Instrument every adjacent execution boundary and require zero calls."""
    calls: list[str] = []

    def forbidden(name: str):
        """Build a fail-fast runtime boundary replacement.

        Args:
            name: Stable boundary label.

        Returns:
            Callable that records and fails on any invocation.
        """

        def invoke(*args, **kwargs):
            """Reject one unexpected runtime-side call.

            Args:
                *args: Ignored positional inputs.
                **kwargs: Ignored keyword inputs.

            Raises:
                AssertionError: Always.

            Returns:
                Never returns.
            """
            del args, kwargs
            calls.append(name)
            raise AssertionError(f"authoring crossed {name}")

        return invoke

    boundaries = (
        (
            "zhixing.benchmark.runtime.resolver."
            "RegistryBenchmarkComponentResolver.generate_task_value",
            "task-initializer",
        ),
        (
            "zhixing.benchmark.runtime.resolver."
            "RegistryBenchmarkComponentResolver.resolve_environment",
            "environment-plugin",
        ),
        (
            "zhixing.benchmark.runtime.resolver."
            "RegistryBenchmarkComponentResolver.resolve_evaluator",
            "evaluator-plugin",
        ),
        (
            "zhixing.studio.run_execution.AndroidDeviceProfileResolver.resolve",
            "device",
        ),
        (
            "zhixing.studio.run_execution."
            "ProductionComponentResolverFactory.create",
            "model-secret-component",
        ),
        (
            "zhixing.studio.benchmark_execution."
            "StudioBenchmarkExecutionAdapter.execute",
            "benchmark-runtime",
        ),
        (
            "zhixing.studio.benchmark_execution."
            "LocalBenchmarkExperimentScheduler.wake",
            "scheduler",
        ),
        (
            "zhixing.studio.benchmark_experiment_service."
            "StudioBenchmarkExperimentApplicationService.create_experiment",
            "experiment",
        ),
        (
            "zhixing.studio.benchmark_publication."
            "DurableStudioBenchmarkPublisher.publish",
            "report-publication",
        ),
        (
            "zhixing.studio.benchmark_replay."
            "NativeStudioBenchmarkReplayPublisher.build",
            "replay",
        ),
    )
    for target, name in boundaries:
        monkeypatch.setattr(target, forbidden(name))

    service, _repository_value, _content, _catalog = _authoring_service(
        tmp_path
    )
    created = service.create_draft(_template_create_payload("no-runtime"))
    service.get_draft(created.draft.draft_id)
    service.list_drafts()
    service.save_revision(
        created.draft.draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "no-runtime-save",
            "baseRevisionId": created.revision.revision_id,
            "document": created.revision.document.model_dump(
                mode="json",
                by_alias=True,
                exclude_none=True,
            ),
        },
    )
    assert calls == []
