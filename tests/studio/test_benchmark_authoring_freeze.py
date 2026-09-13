"""Validated-freeze contracts for Studio Benchmark authoring revisions."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import json
import sqlite3

import pytest
from pydantic import ValidationError

from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringFreezeEligibilityError,
    StudioBenchmarkAuthoringIdempotencyConflictError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringStorageError,
)
from zhixing.studio.benchmark_authoring_freeze import (
    StudioBenchmarkFrozenClosureBuilder,
)
from zhixing.studio.benchmark_authoring_freeze_models import (
    StudioBenchmarkFreezeRequestV1,
    StudioBenchmarkFrozenMemberV1,
    StudioBenchmarkValidationSafetyV1,
    benchmark_frozen_closure_identity,
)
from zhixing.studio.benchmark_authoring_freeze_service import (
    StudioBenchmarkValidatedFreezeAnalyzer,
    StudioBenchmarkValidatedFreezeApplicationService,
)
from zhixing.studio.benchmark_authoring_repository import (
    SQLiteStudioBenchmarkAuthoringRepository,
)
from zhixing.studio.database import STUDIO_SQLITE_SCHEMA_VERSION

from .test_benchmark_authoring_analysis import _analysis_fixture


def _freeze_identity_factory() -> object:
    """Return deterministic prefix-compatible identities for freeze tests.

    Returns:
        Callable producing a unique UUID-width suffix for each prefix.
    """
    counts: dict[str, int] = {}

    def factory(prefix: str) -> str:
        """Create one deterministic identity for the requested prefix.

        Args:
            prefix: Public resource prefix.

        Returns:
            Stable test identity.
        """
        counts[prefix] = counts.get(prefix, 0) + 1
        return f"{prefix}-{counts[prefix]:032x}"

    return factory


def _freeze_fixture(tmp_path: Path) -> dict[str, object]:
    """Build one real authoring draft and exact-current freeze service.

    Args:
        tmp_path: Pytest persistence root.

    Returns:
        Existing analysis fixture extended with freeze collaborators.
    """
    fixture = _analysis_fixture(tmp_path)
    analyzer = StudioBenchmarkValidatedFreezeAnalyzer(
        fixture["analysis"]._compiler  # type: ignore[union-attr]
    )
    freeze = StudioBenchmarkValidatedFreezeApplicationService(
        repository=fixture["repository"],  # type: ignore[arg-type]
        analyzer=analyzer,
        closure_builder=StudioBenchmarkFrozenClosureBuilder(
            fixture["content"]  # type: ignore[arg-type]
        ),
        clock=lambda: 2_000,
        identity_factory=_freeze_identity_factory(),  # type: ignore[arg-type]
    )
    return {**fixture, "freeze": freeze, "freezeAnalyzer": analyzer}


def _freeze_request(revision_id: str, request_id: str = "freeze-1") -> dict[str, object]:
    """Build one strict freeze command payload.

    Args:
        revision_id: Exact current authoring revision identity.
        request_id: Idempotency identity.

    Returns:
        JSON-compatible request.
    """
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "revisionId": revision_id,
    }


def _save_document(
    fixture: dict[str, object],
    document: dict[str, object],
    *,
    request_id: str,
) -> object:
    """Append one immutable authoring revision through the public service.

    Args:
        fixture: Freeze fixture with authoring, draft, and current revision.
        document: Complete strict authoring document payload.
        request_id: Save command identity.

    Returns:
        Newly created revision record.
    """
    draft = fixture["draft"]
    current = fixture["repository"].get_draft(  # type: ignore[union-attr]
        draft.draft_id  # type: ignore[union-attr]
    )
    result = fixture["authoring"].save_revision(  # type: ignore[union-attr]
        draft.draft_id,  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": request_id,
            "baseRevisionId": current.current_revision_id,
            "document": document,
        },
    )
    return result.revision


def _freeze_current(
    fixture: dict[str, object],
    *,
    request_id: str = "freeze-1",
) -> object:
    """Freeze the fixture's exact durable current revision.

    Args:
        fixture: Freeze fixture.
        request_id: Idempotency identity.

    Returns:
        Strict freeze result.
    """
    draft = fixture["draft"]
    current = fixture["repository"].get_draft(  # type: ignore[union-attr]
        draft.draft_id  # type: ignore[union-attr]
    )
    service = fixture["freeze"]
    request = service.parse_request(  # type: ignore[union-attr]
        _freeze_request(current.current_revision_id, request_id)
    )
    return service.freeze(draft.draft_id, request)  # type: ignore[union-attr]


def _freeze_table_counts(database: Path) -> dict[str, int]:
    """Return row counts for every schema-9 freeze authority table.

    Args:
        database: Studio SQLite database.

    Returns:
        Mapping from table name to durable row count.
    """
    tables = (
        "studio_benchmark_validation_attestations",
        "studio_benchmark_package_revisions",
        "studio_benchmark_package_revision_members",
        "studio_benchmark_freeze_commands",
    )
    with sqlite3.connect(database) as connection:
        return {
            table: int(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            )
            for table in tables
        }


def test_freeze_models_are_strict_bounded_and_explicitly_non_executing() -> None:
    """Reject unsafe inputs and lock the evidence-negative safety contract."""
    revision_id = "benchmark-authoring-revision-" + "1" * 32
    request = StudioBenchmarkFreezeRequestV1.model_validate(
        _freeze_request(revision_id)
    )
    assert request.fingerprint.startswith("sha256:")
    assert StudioBenchmarkValidationSafetyV1().model_dump() == {
        "complete_declared_splits": True,
        "definition_only": True,
        "execution_evidence": False,
        "real_device_evidence": False,
        "model_evidence": False,
        "package_plugin_evidence": False,
        "publication_evidence": False,
        "contract_test_required": False,
    }
    for mutation in (
        {**_freeze_request(revision_id), "hostPath": "/tmp/private"},
        {**_freeze_request(revision_id), "clientRequestId": "../escape"},
        {**_freeze_request(revision_id), "revisionId": "not-a-revision"},
        {**_freeze_request(revision_id), "schemaVersion": 1.0},
        {**_freeze_request(revision_id), "validationResultId": "transient"},
        {**_freeze_request(revision_id), "contractTestResultId": "transient"},
        {**_freeze_request(revision_id), "cancel": True},
    ):
        with pytest.raises(ValidationError):
            StudioBenchmarkFreezeRequestV1.model_validate(mutation)

    base_member = {
        "ordinal": 0,
        "kind": "manifest",
        "path": "benchmark.yaml",
        "mediaType": "application/json",
        "size": 2,
        "sha256": "sha256:" + "2" * 64,
        "contentIdentity": "benchmark-content-" + "2" * 64,
    }
    member = StudioBenchmarkFrozenMemberV1.model_validate(base_member)
    assert benchmark_frozen_closure_identity((member,)).startswith("sha256:")
    for path in ("/tmp/member", "../escape", "a/../b", "a\\b"):
        with pytest.raises(ValidationError):
            StudioBenchmarkFrozenMemberV1.model_validate(
                {**base_member, "path": path}
            )
    with pytest.raises(ValidationError):
        StudioBenchmarkFrozenMemberV1.model_validate(
            {**base_member, "size": float("nan")}
        )
    with pytest.raises(ValidationError):
        StudioBenchmarkFrozenMemberV1.model_validate(
            {**base_member, "size": 64 * 1024 * 1024 + 1}
        )
    for unsafe in (
        {"executionEvidence": True},
        {"publicationEvidence": True},
        {"definitionOnly": False},
        {"executionEvidence": 0},
    ):
        with pytest.raises(ValidationError):
            StudioBenchmarkValidationSafetyV1.model_validate(unsafe)


def test_schema_10_rebuilds_from_populated_schema_8_without_rewriting_authoring(
    tmp_path: Path,
) -> None:
    """Reapply migrations 9 and 10 over populated schema-8-compatible rows."""
    fixture = _freeze_fixture(tmp_path)
    draft = fixture["draft"]
    revision = fixture["revision"]
    database = fixture["repository"].database_path  # type: ignore[union-attr]
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TABLE studio_benchmark_freeze_commands")
        connection.execute(
            "DROP TABLE studio_benchmark_package_revision_members"
        )
        connection.execute("DROP TABLE studio_benchmark_package_revisions")
        connection.execute(
            "DROP TABLE studio_benchmark_validation_attestations"
        )
        connection.execute(
            "DELETE FROM studio_schema_migrations WHERE version = 9"
        )
    restarted = SQLiteStudioBenchmarkAuthoringRepository(database)
    assert STUDIO_SQLITE_SCHEMA_VERSION == 12
    assert restarted.get_draft(draft.draft_id).current_revision_id == (
        revision.revision_id
    )
    assert restarted.get_revision(
        draft.draft_id, revision.revision_id
    ).document_fingerprint == revision.document_fingerprint
    with sqlite3.connect(database) as connection:
        versions = [
            row[0]
            for row in connection.execute(
                "SELECT version FROM studio_schema_migrations ORDER BY version"
            )
        ]
        assert versions == list(range(1, STUDIO_SQLITE_SCHEMA_VERSION + 1))


def test_freeze_success_retry_restart_and_source_immutability(tmp_path: Path) -> None:
    """Persist one closed snapshot without changing its authoring source."""
    fixture = _freeze_fixture(tmp_path)
    repository = fixture["repository"]
    content = fixture["content"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    orphan_identity = content.store_bytes(  # type: ignore[union-attr]
        b"unreferenced", max_bytes=1024
    )[0]
    result = _freeze_current(fixture)
    assert result.created is True
    detail = result.detail
    package = detail.package_revision
    attestation = detail.validation_attestation
    assert package.authoring_revision_id == revision.revision_id
    assert attestation.document_fingerprint == revision.document_fingerprint
    assert [member.path for member in package.members] == [
        "benchmark.yaml",
        "protocols/default.yaml",
        "tasks/test.json",
    ]
    assert attestation.safety.execution_evidence is False
    assert attestation.safety.publication_evidence is False
    assert tuple(item.split for item in attestation.splits) == ("test",)
    assert orphan_identity not in {
        member.content_identity for member in package.members
    }
    compiled = fixture["analysis"]._compiler.compile(  # type: ignore[union-attr]
        draft.draft_id,
        revision.revision_id,
        "test",
    )
    assert attestation.package_identity == compiled.identities.package
    assert (
        attestation.package_content_identity
        == compiled.identities.package_content
    )
    assert attestation.splits[0].benchmark_plan_identity == (
        compiled.plan.canonical_hash()
    )
    assert attestation.splits[0].experiment_protocol_identity == (
        compiled.protocol.canonical_hash()
    )
    assert "plugin-availability" in attestation.unverified_checks
    unsafe_attestation = attestation.model_dump(mode="json", by_alias=True)
    unsafe_attestation["warnings"] = ["failed at /tmp/private"]
    with pytest.raises(ValidationError):
        type(attestation).model_validate(unsafe_attestation)
    overbound_attestation = attestation.model_dump(mode="json", by_alias=True)
    overbound_attestation["warnings"] = [
        f"warning-{index:03d}" for index in range(101)
    ]
    with pytest.raises(ValidationError):
        type(attestation).model_validate(overbound_attestation)
    aggregate_schedule = attestation.model_dump(mode="json", by_alias=True)
    aggregate_schedule["splits"] = [
        {
            **aggregate_schedule["splits"][0],
            "split": split,
            "scheduleEntryCount": 6_000,
        }
        for split in ("test", "dev")
    ]
    with pytest.raises(ValidationError):
        type(attestation).model_validate(aggregate_schedule)
    oversized_members = tuple(
        StudioBenchmarkFrozenMemberV1.model_validate(
            {
                **package.members[0].model_dump(mode="json", by_alias=True),
                "ordinal": ordinal,
                "path": f"assets/member-{ordinal}.bin",
                "size": 60 * 1024 * 1024,
            }
        )
        for ordinal in range(5)
    )
    oversized_package = package.model_dump(mode="json", by_alias=True)
    oversized_package["members"] = [
        item.model_dump(mode="json", by_alias=True)
        for item in oversized_members
    ]
    oversized_package["closureIdentity"] = benchmark_frozen_closure_identity(
        oversized_members
    )
    with pytest.raises(ValidationError):
        type(package).model_validate(oversized_package)
    for member in package.members:
        with content.open_verified(  # type: ignore[union-attr]
            member.content_identity,
            expected_sha256=member.sha256,
            expected_size=member.size,
        ) as stream:
            assert len(stream.read()) == member.size

    retry = _freeze_current(fixture)
    assert retry.created is False
    assert retry.detail == detail
    durable_draft = repository.get_draft(draft.draft_id)  # type: ignore[union-attr]
    durable_revision = repository.get_revision(  # type: ignore[union-attr]
        draft.draft_id, revision.revision_id
    )
    assert durable_draft.current_revision_id == revision.revision_id
    assert durable_revision.status == "unvalidated"
    assert durable_revision.document_fingerprint == revision.document_fingerprint
    assert _freeze_table_counts(repository.database_path) == {  # type: ignore[union-attr]
        "studio_benchmark_validation_attestations": 1,
        "studio_benchmark_package_revisions": 1,
        "studio_benchmark_package_revision_members": 3,
        "studio_benchmark_freeze_commands": 1,
    }

    restarted = SQLiteStudioBenchmarkAuthoringRepository(
        repository.database_path  # type: ignore[union-attr]
    )
    assert restarted.get_package_revision(
        draft.draft_id, package.package_revision_id
    ) == detail


def test_freeze_multi_split_protocol_and_file_content_closure_is_deterministic(
    tmp_path: Path,
) -> None:
    """Freeze every split and only the coherent declared member inventory."""
    fixture = _freeze_fixture(tmp_path)
    revision = fixture["revision"]
    content = fixture["content"]
    document = revision.document.model_dump(mode="json", by_alias=True)
    task = deepcopy(document["taskFiles"][0]["tasks"][0])
    task["id"] = "dev-task"
    document["manifest"]["document"]["splits"] = {
        "test": {"files": ["tasks/test.json"]},
        "dev": {"files": ["tasks/dev.json"]},
    }
    document["taskFiles"] = [
        {"path": "tasks/dev.json", "tasks": [task]},
        document["taskFiles"][0],
    ]
    alternate = deepcopy(document["protocolFiles"][0])
    alternate["path"] = "protocols/alternate.yaml"
    alternate["document"]["seed"] = 7
    document["protocolFiles"] = [alternate, document["protocolFiles"][0]]
    content_identity, sha256, size = content.store_bytes(  # type: ignore[union-attr]
        b'{"answer":true}\n', max_bytes=1024
    )
    manifest_resource = {
        "id": "truth",
        "kind": "ground_truth",
        "path": "ground_truth/truth.json",
        "media_type": "application/json",
        "sha256": sha256,
        "size": size,
    }
    document["manifest"]["document"]["resources"] = [manifest_resource]
    document["manifest"]["document"]["ground_truth"] = {
        "example-task": {"inline": {"expected": True}},
        "dev-task": {"ref": "groundtruth://truth"},
    }
    document["resources"] = [
        {
            "id": "truth",
            "kind": "ground_truth",
            "path": "ground_truth/truth.json",
            "mediaType": "application/json",
            "sha256": sha256,
            "size": size,
            "contentIdentity": content_identity,
        }
    ]
    saved = _save_document(
        fixture,
        document,
        request_id="multi-split-save",
    )
    result = _freeze_current(fixture, request_id="multi-split-freeze")
    package = result.detail.package_revision
    assert tuple(
        item.split for item in result.detail.validation_attestation.splits
    ) == tuple(saved.document.manifest.document["splits"])
    assert [item.path for item in package.members] == sorted(
        (
            "benchmark.yaml",
            "ground_truth/truth.json",
            "protocols/alternate.yaml",
            "protocols/default.yaml",
            "tasks/dev.json",
            "tasks/test.json",
        )
    )
    assert package.authoring_revision_id == saved.revision_id
    assert package.closure_identity == benchmark_frozen_closure_identity(
        package.members
    )
    assert all(item.content_identity.startswith("benchmark-content-") for item in package.members)


def test_invalid_non_selected_split_blocks_freeze_without_authority(
    tmp_path: Path,
) -> None:
    """Reject a revision when any manifest split is invalid."""
    fixture = _freeze_fixture(tmp_path)
    revision = fixture["revision"]
    document = revision.document.model_dump(mode="json", by_alias=True)
    document["manifest"]["document"]["splits"] = {
        "test": {"files": ["tasks/test.json"]},
        "broken": {"files": ["tasks/broken.json"]},
    }
    document["taskFiles"] = [
        {"path": "tasks/broken.json", "tasks": [{"id": "broken"}]},
        document["taskFiles"][0],
    ]
    _save_document(fixture, document, request_id="invalid-split-save")
    with pytest.raises(StudioBenchmarkAuthoringFreezeEligibilityError) as caught:
        _freeze_current(fixture, request_id="invalid-split-freeze")
    assert caught.value.diagnostics
    assert _freeze_table_counts(
        fixture["repository"].database_path  # type: ignore[union-attr]
    ) == {
        "studio_benchmark_validation_attestations": 0,
        "studio_benchmark_package_revisions": 0,
        "studio_benchmark_package_revision_members": 0,
        "studio_benchmark_freeze_commands": 0,
    }


@pytest.mark.parametrize("failure", ("missing", "corrupt"))
def test_freeze_detects_unavailable_managed_content_before_commit(
    tmp_path: Path,
    failure: str,
) -> None:
    """Fail closed on missing or corrupt bytes without durable authority.

    Args:
        tmp_path: Pytest temporary persistence root.
        failure: Missing-object or digest-corruption injection.
    """
    fixture = _freeze_fixture(tmp_path)
    revision = fixture["revision"]
    content = fixture["content"]
    document = revision.document.model_dump(mode="json", by_alias=True)
    content_identity, sha256, size = content.store_bytes(  # type: ignore[union-attr]
        b"trusted", max_bytes=1024
    )
    manifest_resource = {
        "id": "asset",
        "kind": "asset",
        "path": "assets/asset.txt",
        "media_type": "text/plain",
        "sha256": sha256,
        "size": size,
    }
    document["manifest"]["document"]["resources"] = [manifest_resource]
    document["resources"] = [
        {
            "id": "asset",
            "kind": "asset",
            "path": "assets/asset.txt",
            "mediaType": "text/plain",
            "sha256": sha256,
            "size": size,
            "contentIdentity": content_identity,
        }
    ]
    _save_document(fixture, document, request_id="corrupt-save")
    content_path = content.content_path(content_identity)  # type: ignore[union-attr]
    if failure == "missing":
        content_path.unlink()
    else:
        content_path.write_bytes(b"corrupt")
    expected_error = (
        StudioBenchmarkAuthoringFreezeEligibilityError
        if failure == "missing"
        else StudioBenchmarkAuthoringStorageError
    )
    with pytest.raises(expected_error):
        _freeze_current(fixture, request_id="corrupt-freeze")
    assert not any(_freeze_table_counts(
        fixture["repository"].database_path  # type: ignore[union-attr]
    ).values())


def test_freeze_idempotency_conflict_and_foreign_ownership_are_hidden(
    tmp_path: Path,
) -> None:
    """Keep request reuse strict and Package reads draft-scoped."""
    fixture = _freeze_fixture(tmp_path)
    first = _freeze_current(fixture, request_id="fixed-command")
    draft = fixture["draft"]
    revision = fixture["revision"]
    document = revision.document.model_dump(mode="json", by_alias=True)
    document["manifest"]["document"]["title"] = "Later source edit"
    saved = _save_document(fixture, document, request_id="later-edit")
    request = fixture["freeze"].parse_request(  # type: ignore[union-attr]
        _freeze_request(saved.revision_id, "fixed-command")
    )
    with pytest.raises(StudioBenchmarkAuthoringIdempotencyConflictError):
        fixture["freeze"].freeze(draft.draft_id, request)  # type: ignore[union-attr]
    assert fixture["freeze"].get_package_revision(  # type: ignore[union-attr]
        draft.draft_id,
        first.detail.package_revision.package_revision_id,
    ) == first.detail
    later = _freeze_current(fixture, request_id="later-freeze")
    assert later.detail.package_revision.package_content_identity != (
        first.detail.package_revision.package_content_identity
    )
    assert later.detail.package_revision.closure_identity != (
        first.detail.package_revision.closure_identity
    )

    foreign = fixture["authoring"].create_draft(  # type: ignore[union-attr]
        {
            "schemaVersion": 1,
            "clientRequestId": "foreign-draft",
            "name": "Foreign",
            "source": {
                "kind": "template",
                "template": "minimal",
                "publisher": "tests",
                "packageName": "foreign",
                "version": "0.1.0",
            },
        }
    )
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        fixture["freeze"].get_package_revision(  # type: ignore[union-attr]
            foreign.draft.draft_id,
            first.detail.package_revision.package_revision_id,
        )


def test_current_pointer_change_during_commit_rolls_back_freeze(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recheck exact-current ownership inside the final SQLite transaction."""
    fixture = _freeze_fixture(tmp_path)
    repository = fixture["repository"]
    draft = fixture["draft"]
    revision = fixture["revision"]
    original = repository.commit_freeze  # type: ignore[union-attr]
    raced = False

    def race(*args: object, **kwargs: object) -> object:
        """Advance the draft once immediately before the final commit.

        Args:
            args: Original positional commit arguments.
            kwargs: Original keyword commit arguments.

        Returns:
            Delegated commit result when it does not reject the stale revision.
        """
        nonlocal raced
        if not raced:
            raced = True
            document = revision.document.model_dump(mode="json", by_alias=True)
            document["manifest"]["document"]["title"] = "Concurrent edit"
            _save_document(fixture, document, request_id="concurrent-save")
        return original(*args, **kwargs)

    monkeypatch.setattr(repository, "commit_freeze", race)
    with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError):
        _freeze_current(fixture, request_id="racing-freeze")
    assert repository.get_draft(draft.draft_id).current_revision_id != (  # type: ignore[union-attr]
        revision.revision_id
    )
    assert not any(_freeze_table_counts(repository.database_path).values())  # type: ignore[union-attr]


def test_post_promotion_database_failure_leaves_no_queryable_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Allow unreachable content bytes but never partial durable freeze facts."""
    fixture = _freeze_fixture(tmp_path)
    repository = fixture["repository"]
    content = fixture["content"]
    objects = content.root / "objects"  # type: ignore[union-attr]

    def reject(*args: object, **kwargs: object) -> object:
        """Inject one database outage after member promotion.

        Args:
            args: Ignored commit arguments.
            kwargs: Ignored commit keyword arguments.

        Raises:
            StudioBenchmarkAuthoringStorageError: Always.
        """
        del args, kwargs
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.storage_failed",
            "Injected database failure",
        )

    monkeypatch.setattr(repository, "commit_freeze", reject)
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        _freeze_current(fixture, request_id="database-failure")
    assert list(objects.glob("*/*"))
    assert not any(_freeze_table_counts(repository.database_path).values())  # type: ignore[union-attr]


def test_corrupt_member_rows_fail_closed_and_foreign_state_is_unchanged(
    tmp_path: Path,
) -> None:
    """Reject inconsistent stored member indexes after restart reconstruction."""
    fixture = _freeze_fixture(tmp_path)
    result = _freeze_current(fixture)
    repository = fixture["repository"]
    package_id = result.detail.package_revision.package_revision_id
    member = result.detail.package_revision.members[0]
    corrupt = member.model_dump(mode="json", by_alias=True)
    corrupt["ordinal"] = 1
    with sqlite3.connect(repository.database_path) as connection:  # type: ignore[union-attr]
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO studio_benchmark_package_revision_members(
                    package_revision_id, ordinal, member_path, descriptor_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    package_id,
                    99,
                    member.path,
                    json.dumps(member.model_dump(mode="json", by_alias=True)),
                ),
            )
    with sqlite3.connect(repository.database_path) as connection:  # type: ignore[union-attr]
        connection.execute(
            """
            UPDATE studio_benchmark_package_revision_members
            SET descriptor_json = ?
            WHERE package_revision_id = ? AND ordinal = 0
            """,
            (json.dumps(corrupt), package_id),
        )
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        repository.get_package_revision(  # type: ignore[union-attr]
            fixture["draft"].draft_id, package_id  # type: ignore[union-attr]
        )


def test_freeze_dependency_graph_and_cleanup_exclude_runtime_products(
    tmp_path: Path,
) -> None:
    """Prove E-1 has no runtime capability and leaves staging/product rows empty."""
    fixture = _freeze_fixture(tmp_path)
    freeze = fixture["freeze"]
    assert set(vars(freeze)) == {
        "_repository",
        "_analyzer",
        "_closure_builder",
        "_clock",
        "_identity_factory",
    }
    _freeze_current(fixture)
    staging = fixture["staging"]
    assert list(staging.iterdir()) == []  # type: ignore[union-attr]
    database = fixture["repository"].database_path  # type: ignore[union-attr]
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_experiments"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_benchmark_artifacts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM studio_replays"
        ).fetchone()[0] == 0
