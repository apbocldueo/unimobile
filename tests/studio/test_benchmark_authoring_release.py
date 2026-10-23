"""Immutable publication and deterministic Package export contracts."""

from __future__ import annotations

from pathlib import Path
import json
import sqlite3
import zipfile

import pytest
from pydantic import ValidationError

from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringReleaseConflictError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from zhixing.studio.benchmark_authoring_release_models import (
    StudioBenchmarkExportSafetyV1,
    StudioBenchmarkPublicationSafetyV1,
    StudioBenchmarkReleaseCommandV1,
    benchmark_release_request_fingerprint,
)
from zhixing.studio.benchmark_authoring_release_service import (
    StudioBenchmarkPackageReleaseApplicationService,
)
from zhixing.studio.benchmark_authoring_release_storage import (
    LocalStudioBenchmarkPackageReleaseStore,
    StudioBenchmarkFrozenClosureReader,
)
from zhixing.studio.benchmark_service import (
    StudioBenchmarkCatalogService,
    StudioBenchmarkCatalogSnapshotOwner,
    StudioBenchmarkSource,
)
from zhixing.studio.database import STUDIO_SQLITE_SCHEMA_VERSION

from .test_benchmark_authoring_freeze import (
    _freeze_current,
    _freeze_fixture,
    _freeze_identity_factory,
    _save_document,
)


def _release_fixture(tmp_path: Path) -> dict[str, object]:
    """Build one real frozen Package and runtime-incapable release service.

    Args:
        tmp_path: Pytest persistence root.

    Raises:
        None.

    Returns:
        Freeze fixture extended with release collaborators and frozen detail.
    """
    fixture = _freeze_fixture(tmp_path)
    frozen = _freeze_current(fixture)
    owner = StudioBenchmarkCatalogSnapshotOwner(
        StudioBenchmarkCatalogService(())
    )
    storage = LocalStudioBenchmarkPackageReleaseStore(tmp_path / "release")
    service = StudioBenchmarkPackageReleaseApplicationService(
        repository=fixture["repository"],  # type: ignore[arg-type]
        frozen_reader=StudioBenchmarkFrozenClosureReader(
            fixture["content"]  # type: ignore[arg-type]
        ),
        storage=storage,
        catalog=owner,
        clock=lambda: 3_000,
        identity_factory=_freeze_identity_factory(),  # type: ignore[arg-type]
    )
    return {
        **fixture,
        "frozen": frozen,
        "catalogOwner": owner,
        "releaseStorage": storage,
        "release": service,
    }


def _release_request(request_id: str) -> StudioBenchmarkReleaseCommandV1:
    """Create one strict stable release command.

    Args:
        request_id: Client request identity.

    Raises:
        ValidationError: Test identity violates the command contract.

    Returns:
        Strict release command.
    """
    return StudioBenchmarkReleaseCommandV1(
        schemaVersion=1,
        clientRequestId=request_id,
    )


def test_release_models_are_strict_scoped_and_evidence_negative() -> None:
    """Reject caller authority and lock publication/export safety facts."""
    request = _release_request("release-1")
    draft_id = "benchmark-draft-" + "1" * 32
    package_revision_id = "benchmark-package-revision-" + "2" * 32
    assert benchmark_release_request_fingerprint(
        operation="publish",
        draft_id=draft_id,
        package_revision_id=package_revision_id,
        request=request,
    ) != benchmark_release_request_fingerprint(
        operation="export",
        draft_id=draft_id,
        package_revision_id=package_revision_id,
        request=request,
    )
    for mutation in (
        {"schemaVersion": 1, "clientRequestId": "release-1", "path": "/tmp/x"},
        {"schemaVersion": 1, "clientRequestId": "../escape"},
        {"schemaVersion": 1.0, "clientRequestId": "release-1"},
        {"schemaVersion": 1, "clientRequestId": "release-1", "members": []},
    ):
        with pytest.raises(ValidationError):
            StudioBenchmarkReleaseCommandV1.model_validate(mutation)
    assert StudioBenchmarkPublicationSafetyV1().execution_evidence is False
    assert StudioBenchmarkPublicationSafetyV1().publication_evidence is True
    assert StudioBenchmarkExportSafetyV1().publication_evidence is False
    assert StudioBenchmarkExportSafetyV1().archive_integrity_verified is True
    with pytest.raises(ValidationError):
        StudioBenchmarkPublicationSafetyV1(executionEvidence=True)
    with pytest.raises(ValidationError):
        StudioBenchmarkExportSafetyV1(realDeviceEvidence=True)


def test_schema_10_adds_release_authority_without_rewriting_freeze(
    tmp_path: Path,
) -> None:
    """Preserve schema-9 rows while installing all schema-10 release tables."""
    fixture = _release_fixture(tmp_path)
    database = fixture["repository"].database_path  # type: ignore[union-attr]
    assert STUDIO_SQLITE_SCHEMA_VERSION == 12
    with sqlite3.connect(database) as connection:
        versions = tuple(
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        )
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_package_revisions"
        ).fetchone()[0] == 1
        assert versions == tuple(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))
    assert {
        "studio_benchmark_package_publications",
        "studio_benchmark_publication_commands",
        "studio_benchmark_package_exports",
        "studio_benchmark_export_commands",
    } <= tables


def test_publish_export_retry_page_restart_and_exact_archive(
    tmp_path: Path,
) -> None:
    """Publish visibly, export deterministically, retry, and recover on restart."""
    fixture = _release_fixture(tmp_path)
    frozen = fixture["frozen"]
    package = frozen.detail.package_revision  # type: ignore[union-attr]
    draft_id = package.draft_id
    service = fixture["release"]

    published = service.publish(  # type: ignore[union-attr]
        draft_id,
        package.package_revision_id,
        _release_request("publish-1"),
    )
    assert published.created is True
    assert published.publication.safety.execution_evidence is False
    assert published.publication.catalog_entry_id.startswith("benchmark-entry-")
    page = fixture["catalogOwner"].list_entries(source_kind="catalog")  # type: ignore[union-attr]
    assert [item.catalog_entry_id for item in page.items] == [
        published.publication.catalog_entry_id
    ]
    retry = service.publish(  # type: ignore[union-attr]
        draft_id,
        package.package_revision_id,
        _release_request("publish-1"),
    )
    assert retry.created is False
    assert retry.publication == published.publication
    equivalent = service.publish(  # type: ignore[union-attr]
        draft_id,
        package.package_revision_id,
        _release_request("publish-2"),
    )
    assert equivalent.created is False
    assert equivalent.publication == published.publication
    exported = service.export_package(  # type: ignore[union-attr]
        draft_id,
        package.package_revision_id,
        _release_request("export-1"),
    )
    assert exported.created is True
    descriptor, stream = service.open_export(  # type: ignore[union-attr]
        draft_id,
        package.package_revision_id,
        exported.package_export.export_id,
    )
    archive_bytes = stream.read()
    stream.close()
    assert len(archive_bytes) == descriptor.size
    archive_path = (
        fixture["releaseStorage"].root  # type: ignore[union-attr]
        / "exports"
        / f"{descriptor.export_id}.zip"
    )
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == [member.path for member in package.members]
        assert all(item.compress_type == zipfile.ZIP_STORED for item in archive.infolist())
        assert all(item.date_time == (1980, 1, 1, 0, 0, 0) for item in archive.infolist())
    second = service.export_package(  # type: ignore[union-attr]
        draft_id,
        package.package_revision_id,
        _release_request("export-2"),
    )
    assert second.created is False
    assert second.package_export == descriptor
    release_page = service.list_package_revisions(draft_id, limit=1)  # type: ignore[union-attr]
    assert release_page.items[0].publication == published.publication
    assert release_page.items[0].package_export == descriptor

    restarted_owner = StudioBenchmarkCatalogSnapshotOwner(
        StudioBenchmarkCatalogService(())
    )
    restarted = StudioBenchmarkPackageReleaseApplicationService(
        repository=fixture["repository"],  # type: ignore[arg-type]
        frozen_reader=StudioBenchmarkFrozenClosureReader(
            fixture["content"]  # type: ignore[arg-type]
        ),
        storage=fixture["releaseStorage"],  # type: ignore[arg-type]
        catalog=restarted_owner,
    )
    assert restarted.recover_publications() == 1
    assert restarted_owner.detail(
        published.publication.catalog_entry_id
    ).package_content_identity == package.package_content_identity


def test_release_hides_ownership_and_fails_closed_on_corrupt_bytes(
    tmp_path: Path,
) -> None:
    """Hide cross-draft lookup and reject post-commit archive corruption."""
    fixture = _release_fixture(tmp_path)
    package = fixture["frozen"].detail.package_revision  # type: ignore[union-attr]
    service = fixture["release"]
    exported = service.export_package(  # type: ignore[union-attr]
        package.draft_id,
        package.package_revision_id,
        _release_request("export-corrupt"),
    )
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        service.get_export(  # type: ignore[union-attr]
            "benchmark-draft-" + "f" * 32,
            package.package_revision_id,
            exported.package_export.export_id,
        )
    archive_path = (
        fixture["releaseStorage"].root  # type: ignore[union-attr]
        / "exports"
        / f"{exported.package_export.export_id}.zip"
    )
    archive_path.write_bytes(b"corrupt")
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        service.open_export(  # type: ignore[union-attr]
            package.draft_id,
            package.package_revision_id,
            exported.package_export.export_id,
        )


def test_release_page_cursor_and_command_fingerprint_are_draft_bound(
    tmp_path: Path,
) -> None:
    """Paginate stable freezes and reject command reuse for another target."""
    fixture = _release_fixture(tmp_path)
    first = fixture["frozen"].detail.package_revision  # type: ignore[union-attr]
    revision = fixture["revision"]
    document = revision.document.model_dump(mode="json", by_alias=True)  # type: ignore[union-attr]
    document["manifest"]["document"]["title"] = "Second immutable release"
    _save_document(fixture, document, request_id="release-page-save")
    second = _freeze_current(
        fixture,
        request_id="release-page-freeze",
    ).detail.package_revision
    service = fixture["release"]
    first_page = service.list_package_revisions(  # type: ignore[union-attr]
        first.draft_id,
        limit=1,
    )
    assert [item.package_revision_id for item in first_page.items] == [
        second.package_revision_id
    ]
    assert first_page.next_cursor is not None
    second_page = service.list_package_revisions(  # type: ignore[union-attr]
        first.draft_id,
        limit=1,
        cursor=first_page.next_cursor,
    )
    assert [item.package_revision_id for item in second_page.items] == [
        first.package_revision_id
    ]
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        service.list_package_revisions(  # type: ignore[union-attr]
            "benchmark-draft-" + "f" * 32,
            cursor=first_page.next_cursor,
        )

    service.publish(  # type: ignore[union-attr]
        first.draft_id,
        first.package_revision_id,
        _release_request("same-command"),
    )
    with pytest.raises(StudioBenchmarkAuthoringIdempotencyConflictError):
        service.publish(  # type: ignore[union-attr]
            first.draft_id,
            second.package_revision_id,
            _release_request("same-command"),
        )


def test_configured_equivalence_is_explicit_but_divergent_content_conflicts(
    tmp_path: Path,
) -> None:
    """Preserve equivalent sources and reject one readable divergent version."""
    fixture = _release_fixture(tmp_path)
    detail = fixture["frozen"].detail  # type: ignore[union-attr]
    storage = fixture["releaseStorage"]
    reader = StudioBenchmarkFrozenClosureReader(
        fixture["content"]  # type: ignore[arg-type]
    )
    configured_root = storage.materialize_package(  # type: ignore[union-attr]
        "benchmark-package-publication-" + "a" * 32,
        detail,
        reader,
    )
    equivalent_owner = StudioBenchmarkCatalogSnapshotOwner(
        StudioBenchmarkCatalogService((
            StudioBenchmarkSource(
                source_id="configured-release-fixture",
                kind="package",
                locator=configured_root,
            ),
        ))
    )
    equivalent_service = StudioBenchmarkPackageReleaseApplicationService(
        repository=fixture["repository"],  # type: ignore[arg-type]
        frozen_reader=reader,
        storage=storage,  # type: ignore[arg-type]
        catalog=equivalent_owner,
        identity_factory=_freeze_identity_factory(),  # type: ignore[arg-type]
    )
    package = detail.package_revision
    published = equivalent_service.publish(
        package.draft_id,
        package.package_revision_id,
        _release_request("equivalent-source"),
    )
    assert published.created is True
    equivalent_page = equivalent_owner.list_entries(limit=10)
    assert len(equivalent_page.items) == 2
    assert all(
        any(
            warning.code == "benchmark.catalog.equivalent_source"
            for warning in item.warnings
        )
        for item in equivalent_page.items
    )

    divergent_fixture = _release_fixture(tmp_path / "divergent")
    divergent_detail = divergent_fixture["frozen"].detail  # type: ignore[union-attr]
    divergent_reader = StudioBenchmarkFrozenClosureReader(
        divergent_fixture["content"]  # type: ignore[arg-type]
    )
    divergent_storage = divergent_fixture["releaseStorage"]
    divergent_root = divergent_storage.materialize_package(  # type: ignore[union-attr]
        "benchmark-package-publication-" + "b" * 32,
        divergent_detail,
        divergent_reader,
    )
    manifest_path = divergent_root / "benchmark.yaml"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["title"] = "Divergent configured content"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    divergent_owner = StudioBenchmarkCatalogSnapshotOwner(
        StudioBenchmarkCatalogService((
            StudioBenchmarkSource(
                source_id="divergent-release-fixture",
                kind="package",
                locator=divergent_root,
            ),
        ))
    )
    divergent_service = StudioBenchmarkPackageReleaseApplicationService(
        repository=divergent_fixture["repository"],  # type: ignore[arg-type]
        frozen_reader=divergent_reader,
        storage=divergent_storage,  # type: ignore[arg-type]
        catalog=divergent_owner,
    )
    divergent_package = divergent_detail.package_revision
    with pytest.raises(StudioBenchmarkAuthoringReleaseConflictError):
        divergent_service.publish(
            divergent_package.draft_id,
            divergent_package.package_revision_id,
            _release_request("divergent-source"),
        )
    assert divergent_fixture["repository"].list_publication_records() == ()  # type: ignore[union-attr]


def test_catalog_swap_preserves_old_snapshot_and_failed_commit_has_no_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Expose complete old/new snapshots and hide content after DB failure."""
    fixture = _release_fixture(tmp_path)
    package = fixture["frozen"].detail.package_revision  # type: ignore[union-attr]
    owner = fixture["catalogOwner"]
    old_snapshot = owner.capture()  # type: ignore[union-attr]
    published = fixture["release"].publish(  # type: ignore[union-attr]
        package.draft_id,
        package.package_revision_id,
        _release_request("snapshot-swap"),
    )
    assert old_snapshot.list_entries().items == ()
    assert [item.catalog_entry_id for item in owner.list_entries().items] == [  # type: ignore[union-attr]
        published.publication.catalog_entry_id
    ]

    failed = _release_fixture(tmp_path / "failure")
    failed_package = failed["frozen"].detail.package_revision  # type: ignore[union-attr]

    def reject_commit(*args: object, **kwargs: object) -> object:
        """Inject a durable metadata outage after private materialization.

        Args:
            args: Ignored repository commit arguments.
            kwargs: Ignored repository commit keyword arguments.

        Raises:
            StudioBenchmarkAuthoringStorageError: Always.
        """
        del args, kwargs
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.storage_failed",
            "Injected release database failure",
        )

    monkeypatch.setattr(failed["repository"], "commit_publication", reject_commit)
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        failed["release"].publish(  # type: ignore[union-attr]
            failed_package.draft_id,
            failed_package.package_revision_id,
            _release_request("failed-publication"),
        )
    assert failed["catalogOwner"].list_entries().items == ()  # type: ignore[union-attr]
    assert failed["repository"].list_publication_records() == ()  # type: ignore[union-attr]
    assert any((failed["releaseStorage"].root / "packages").iterdir())  # type: ignore[union-attr]


def test_release_crosses_no_runtime_or_external_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail fast if Package publication or export reaches runtime capabilities.

    Args:
        tmp_path: Pytest persistence root.
        monkeypatch: Pytest patch helper used to install boundary canaries.

    Raises:
        AssertionError: Publication or export invokes a forbidden capability.

    Returns:
        None.
    """
    import socket

    import zhixing.benchmark.reporting.writer as report_writer
    import zhixing.benchmark.runtime.evaluator as runtime_evaluator
    import zhixing.benchmark.runtime.lifecycle as runtime_lifecycle
    import zhixing.benchmark.runtime.materializer as runtime_materializer
    import zhixing.benchmark.runtime.suite as runtime_suite
    import zhixing.studio.benchmark_execution as benchmark_execution
    import zhixing.studio.benchmark_experiment_service as experiment_service
    import zhixing.studio.benchmark_publication as publication
    import zhixing.studio.benchmark_replay as benchmark_replay
    import zhixing.studio.replay_service as replay_service
    import zhixing.studio.run_execution as run_execution

    counts = {
        name: 0
        for name in (
            "initializer/plugin-construction",
            "environment",
            "evaluator",
            "benchmark-runtime",
            "model/secret-resolution",
            "device/android",
            "agent-execution",
            "task-run/result",
            "experiment",
            "report/trajectory/bundle",
            "runtime-publication",
            "replay",
            "runtime-export",
            "network",
        )
    }

    def fail(name: str):
        """Create one variadic fail-fast canary for a forbidden boundary.

        Args:
            name: Stable boundary label whose counter must remain zero.

        Raises:
            None.

        Returns:
            Callable that records and rejects any boundary crossing.
        """

        def canary(*args, **kwargs):
            """Record one forbidden call and fail release immediately.

            Args:
                *args: Ignored target positional arguments.
                **kwargs: Ignored target keyword arguments.

            Raises:
                AssertionError: Always, because release is runtime incapable.

            Returns:
                Never returns.
            """
            del args, kwargs
            counts[name] += 1
            raise AssertionError(f"release crossed forbidden {name} boundary")

        return canary

    targets = (
        (runtime_materializer, "materialize_task", "initializer/plugin-construction"),
        (runtime_lifecycle, "execute_environment_calls", "environment"),
        (runtime_evaluator, "evaluate_tree", "evaluator"),
        (runtime_suite.BenchmarkExperimentRuntime, "run", "benchmark-runtime"),
        (
            run_execution.ProductionComponentResolverFactory,
            "create",
            "model/secret-resolution",
        ),
        (run_execution.AndroidDeviceProfileResolver, "resolve", "device/android"),
        (
            run_execution.AndroidStudioRunExecutionAdapter,
            "execute",
            "agent-execution",
        ),
        (
            benchmark_execution.StudioBenchmarkExecutionAdapter,
            "execute",
            "task-run/result",
        ),
        (
            experiment_service.StudioBenchmarkExperimentApplicationService,
            "create_experiment",
            "experiment",
        ),
        (report_writer, "write_experiment_artifacts", "report/trajectory/bundle"),
        (publication.DurableStudioBenchmarkPublisher, "publish", "runtime-publication"),
        (benchmark_replay.NativeStudioBenchmarkReplayPublisher, "build", "replay"),
        (replay_service.ReplayApplicationService, "export_bundle", "runtime-export"),
    )
    for target, attribute, name in targets:
        monkeypatch.setattr(target, attribute, fail(name))
    monkeypatch.setattr(socket, "create_connection", fail("network"))

    fixture = _release_fixture(tmp_path)
    package = fixture["frozen"].detail.package_revision  # type: ignore[union-attr]
    release = fixture["release"]
    release.publish(  # type: ignore[union-attr]
        package.draft_id,
        package.package_revision_id,
        _release_request("release-canary-publish"),
    )
    release.export_package(  # type: ignore[union-attr]
        package.draft_id,
        package.package_revision_id,
        _release_request("release-canary-export"),
    )
    assert all(count == 0 for count in counts.values())


def test_release_security_projection_hides_private_authority_and_preserves_source(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Scan durable, public, storage, archive, and log release projections.

    Args:
        tmp_path: Pytest persistence root.
        caplog: Captured Python log records for leakage assertions.

    Raises:
        AssertionError: A private canary escapes or source content changes.

    Returns:
        None.
    """
    private_root = tmp_path / "secret-canary_device-serial-canary_private-host"
    private_root.mkdir()
    fixture = _release_fixture(private_root)
    content_root = fixture["content"].root  # type: ignore[union-attr]
    source_before = {
        path.relative_to(content_root).as_posix(): path.read_bytes()
        for path in content_root.rglob("*")
        if path.is_file()
    }
    package = fixture["frozen"].detail.package_revision  # type: ignore[union-attr]
    service = fixture["release"]
    published = service.publish(  # type: ignore[union-attr]
        package.draft_id,
        package.package_revision_id,
        _release_request("security-publish"),
    )
    exported = service.export_package(  # type: ignore[union-attr]
        package.draft_id,
        package.package_revision_id,
        _release_request("security-export"),
    )
    release_page = service.list_package_revisions(  # type: ignore[union-attr]
        package.draft_id,
        limit=10,
    )
    catalog_page = fixture["catalogOwner"].list_entries(limit=10)  # type: ignore[union-attr]
    public_text = json.dumps(
        {
            "publication": published.model_dump(mode="json", by_alias=True),
            "export": exported.model_dump(mode="json", by_alias=True),
            "releasePage": release_page.model_dump(mode="json", by_alias=True),
            "catalogPage": catalog_page.model_dump(mode="json", by_alias=True),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    forbidden = (
        str(private_root),
        "secret-canary",
        "device-serial-canary",
        "managedLocator",
        "archiveLocator",
        "managed_locator",
        "archive_locator",
        "object at 0x",
    )
    assert all(token not in public_text for token in forbidden)

    database = fixture["repository"].database_path  # type: ignore[union-attr]
    with sqlite3.connect(database) as connection:
        publication_locator = connection.execute(
            "SELECT managed_locator FROM studio_benchmark_package_publications"
        ).fetchone()[0]
        export_locator = connection.execute(
            "SELECT archive_locator FROM studio_benchmark_package_exports"
        ).fetchone()[0]
        durable_values = tuple(
            value
            for table in (
                "studio_benchmark_package_publications",
                "studio_benchmark_publication_commands",
                "studio_benchmark_package_exports",
                "studio_benchmark_export_commands",
            )
            for row in connection.execute(f"SELECT * FROM {table}")
            for value in row
        )
    assert publication_locator == published.publication.publication_id
    assert export_locator == exported.package_export.export_id
    durable_text = json.dumps(durable_values, default=str)
    assert str(private_root) not in durable_text
    assert "secret-canary" not in durable_text
    assert "device-serial-canary" not in durable_text

    storage = fixture["releaseStorage"]
    managed_root = storage.package_path(publication_locator)  # type: ignore[union-attr]
    managed_members = {
        path.relative_to(managed_root).as_posix()
        for path in managed_root.rglob("*")
        if path.is_file()
    }
    expected_members = {member.path for member in package.members}
    assert managed_members == expected_members
    archive_path = storage.root / "exports" / f"{export_locator}.zip"  # type: ignore[union-attr]
    archive_bytes = archive_path.read_bytes()
    assert str(private_root).encode() not in archive_bytes
    assert b"secret-canary" not in archive_bytes
    assert b"device-serial-canary" not in archive_bytes
    with zipfile.ZipFile(archive_path) as archive:
        assert archive.namelist() == [member.path for member in package.members]
        assert archive.comment == b""

    source_after = {
        path.relative_to(content_root).as_posix(): path.read_bytes()
        for path in content_root.rglob("*")
        if path.is_file()
    }
    assert source_after == source_before
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert all(token not in log_text for token in forbidden)


def test_export_bytes_are_identical_across_roots_cwd_and_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Prove ZIP v1 identity ignores storage root and process working directory."""
    fixture = _release_fixture(tmp_path)
    detail = fixture["frozen"].detail  # type: ignore[union-attr]
    reader = StudioBenchmarkFrozenClosureReader(
        fixture["content"]  # type: ignore[arg-type]
    )
    first_store = LocalStudioBenchmarkPackageReleaseStore(tmp_path / "first")
    second_store = LocalStudioBenchmarkPackageReleaseStore(tmp_path / "second")
    first_id = "benchmark-package-export-" + "a" * 32
    second_id = "benchmark-package-export-" + "b" * 32
    first_size, first_digest = first_store.create_export(
        first_id,
        detail,
        reader,
    )
    alternate_cwd = tmp_path / "unrelated-cwd"
    alternate_cwd.mkdir()
    monkeypatch.chdir(alternate_cwd)
    second_size, second_digest = second_store.create_export(
        second_id,
        detail,
        reader,
    )
    first_bytes = (first_store.root / "exports" / f"{first_id}.zip").read_bytes()
    second_bytes = (second_store.root / "exports" / f"{second_id}.zip").read_bytes()
    assert first_bytes == second_bytes
    assert (first_size, first_digest) == (second_size, second_digest)
    restarted = LocalStudioBenchmarkPackageReleaseStore(tmp_path / "second")
    assert restarted.create_export(second_id, detail, reader) == (
        second_size,
        second_digest,
    )
