"""Managed-content contracts for Studio Benchmark authoring."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

import zhixing.studio.benchmark_authoring_storage as authoring_storage_module
from zhixing.studio.benchmark_authoring_content import (
    StudioBenchmarkAuthoringContentApplicationService,
    parse_authoring_content_remove_query,
    parse_authoring_content_replace_query,
    parse_authoring_content_upload_query,
)
from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
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
    StudioBenchmarkAuthoringContentRemoveRequestV1,
    StudioBenchmarkAuthoringContentReplaceRequestV1,
    StudioBenchmarkAuthoringContentUploadRequestV1,
    StudioBenchmarkAuthoringResourceV1,
)
from zhixing.studio.benchmark_authoring_repository import (
    SQLiteStudioBenchmarkAuthoringRepository,
)
from zhixing.studio.benchmark_authoring_service import (
    StudioBenchmarkAuthoringApplicationService,
)
from zhixing.studio.benchmark_authoring_storage import (
    LocalStudioBenchmarkManagedContent,
    default_studio_benchmark_authoring_root,
)
from zhixing.studio.benchmark_service import StudioBenchmarkCatalogService


def _template_create_payload(request_id: str) -> dict[str, object]:
    """Return one strict built-in template create request.

    Args:
        request_id: Stable client command identity.

    Raises:
        None.

    Returns:
        JSON-compatible authoring create payload.
    """
    return {
        "schemaVersion": 1,
        "clientRequestId": request_id,
        "name": "Managed Content Draft",
        "source": {
            "kind": "template",
            "template": "minimal",
            "publisher": "tests",
            "packageName": "managed-content",
            "version": "0.1.0",
        },
    }


def _services(tmp_path):
    """Build real definition and content services over one local aggregate.

    Args:
        tmp_path: Pytest temporary persistence root.

    Raises:
        OSError: Local persistence cannot be prepared.

    Returns:
        Definition service, content service, repository, and content store.
    """
    repository = SQLiteStudioBenchmarkAuthoringRepository(
        tmp_path / "studio.sqlite3"
    )
    content = LocalStudioBenchmarkManagedContent(
        default_studio_benchmark_authoring_root(repository.database_path)
    )
    definition = StudioBenchmarkAuthoringApplicationService(
        repository=repository,
        packages=StudioBenchmarkAuthoringPackageAdapter(
            content,
            staging_root=content.staging_root,
        ),
        catalog=StudioBenchmarkCatalogService(),
    )
    managed = StudioBenchmarkAuthoringContentApplicationService(
        repository=repository,
        content=content,
    )
    return definition, managed, repository, content


def _upload_request(
    base_revision_id: str,
    *,
    request_id: str = "upload-resource",
    resource_id: str = "fixture-asset",
    path: str = "assets/fixture.txt",
    media_type: str = "text/plain",
) -> StudioBenchmarkAuthoringContentUploadRequestV1:
    """Build one strict asset upload request.

    Args:
        base_revision_id: Exact client-observed base revision.
        request_id: Stable client command identity.
        resource_id: New logical resource identity.
        path: New Package-relative asset path.
        media_type: Declared safe media type.

    Raises:
        ValidationError: Test inputs violate the request contract.

    Returns:
        Strict upload request.
    """
    return StudioBenchmarkAuthoringContentUploadRequestV1(
        client_request_id=request_id,
        base_revision_id=base_revision_id,
        resource_id=resource_id,
        kind="asset",
        path=path,
        media_type=media_type,
    )


def test_content_query_parsers_are_exact_single_valued_and_path_safe() -> None:
    """Parse only the operation-specific versioned metadata envelope."""
    revision_id = "benchmark-authoring-revision-" + "a" * 32
    uploaded = parse_authoring_content_upload_query(
        resource_id="fixture-asset",
        media_type="text/plain; charset=utf-8",
        query={
            "schemaVersion": ["1"],
            "clientRequestId": ["upload-1"],
            "baseRevisionId": [revision_id],
            "kind": ["asset"],
            "path": ["assets/测试.txt"],
        },
    )
    assert uploaded.path == "assets/测试.txt"
    assert uploaded.kind == "asset"

    replaced = parse_authoring_content_replace_query(
        resource_id="fixture-asset",
        media_type="application/octet-stream",
        query={
            "schemaVersion": ["1"],
            "clientRequestId": ["replace-1"],
            "baseRevisionId": [revision_id],
        },
    )
    assert replaced.resource_id == "fixture-asset"
    removed = parse_authoring_content_remove_query(
        resource_id="fixture-asset",
        query={
            "schemaVersion": ["1"],
            "clientRequestId": ["remove-1"],
            "baseRevisionId": [revision_id],
        },
    )
    assert removed.base_revision_id == revision_id

    for query in (
        {
            "schemaVersion": ["1"],
            "clientRequestId": ["upload-1", "upload-2"],
            "baseRevisionId": [revision_id],
            "kind": ["asset"],
            "path": ["assets/fixture.txt"],
        },
        {
            "schemaVersion": ["1"],
            "clientRequestId": ["upload-1"],
            "baseRevisionId": [revision_id],
            "kind": ["asset"],
            "path": ["assets/fixture.txt"],
            "contentIdentity": ["benchmark-content-" + "b" * 64],
        },
        {
            "schemaVersion": ["1"],
            "clientRequestId": ["upload-1"],
            "baseRevisionId": [revision_id],
            "kind": ["asset"],
            "path": ["/tmp/fixture.txt"],
        },
    ):
        with pytest.raises(StudioBenchmarkAuthoringValidationError):
            parse_authoring_content_upload_query(
                resource_id="fixture-asset",
                media_type="text/plain",
                query=query,
            )


@pytest.mark.parametrize(
    "payload",
    (
        {
            "clientRequestId": "upload",
            "baseRevisionId": "benchmark-authoring-revision-" + "a" * 32,
            "resourceId": "fixture",
            "kind": "ground_truth",
            "path": "assets/wrong.json",
            "mediaType": "application/json",
        },
        {
            "clientRequestId": "upload",
            "baseRevisionId": "benchmark-authoring-revision-" + "a" * 32,
            "resourceId": "fixture",
            "kind": "asset",
            "path": "assets/right.txt",
            "mediaType": "text/plain\r\nX-Unsafe: yes",
        },
    ),
)
def test_content_command_models_reject_kind_path_and_header_injection(
    payload: dict[str, object],
) -> None:
    """Reject unsafe logical placement and response-header metadata."""
    with pytest.raises(ValidationError):
        StudioBenchmarkAuthoringContentUploadRequestV1.model_validate(payload)


def test_upload_replace_remove_retry_restart_and_historical_read(
    tmp_path,
) -> None:
    """Preserve immutable bytes and revision facts across the full journey."""
    definition, managed, repository, content = _services(tmp_path)
    created = definition.create_draft(_template_create_payload("create-main"))
    draft_id = created.draft.draft_id

    upload = _upload_request(created.revision.revision_id)
    uploaded = managed.upload(draft_id, upload, BytesIO(b"first bytes"))
    assert uploaded.created
    assert uploaded.operation == "upload"
    assert uploaded.revision.status == "unvalidated"
    assert uploaded.resource is not None
    assert uploaded.resource.size == len(b"first bytes")
    assert uploaded.resource.sha256.startswith("sha256:")
    manifest_resource = uploaded.revision.document.manifest.document["resources"][0]
    assert manifest_resource["id"] == "fixture-asset"
    assert "contentIdentity" not in manifest_resource

    old_open = managed.open_content(
        draft_id,
        uploaded.revision.revision_id,
        "fixture-asset",
    )
    try:
        assert old_open.stream.read() == b"first bytes"
    finally:
        old_open.stream.close()

    extended_document = uploaded.revision.document.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    extended_document["manifest"]["document"]["resources"][0][
        "x_preserved"
    ] = {"label": "keep"}
    extended_document["manifest"]["document"]["x_manifest_preserved"] = {
        "mode": "opaque"
    }
    extended = definition.save_revision(
        draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "preserve-extension",
            "baseRevisionId": uploaded.revision.revision_id,
            "document": extended_document,
        },
    )

    replacement = StudioBenchmarkAuthoringContentReplaceRequestV1(
        client_request_id="replace-resource",
        base_revision_id=extended.revision.revision_id,
        resource_id="fixture-asset",
        media_type="text/markdown",
    )
    replaced = managed.replace(
        draft_id,
        replacement,
        BytesIO(b"replacement bytes"),
    )
    assert replaced.resource is not None
    assert replaced.resource.id == uploaded.resource.id
    assert replaced.resource.kind == uploaded.resource.kind
    assert replaced.resource.path == uploaded.resource.path
    assert replaced.resource.content_identity != uploaded.resource.content_identity
    assert (
        replaced.revision.document.manifest.document["resources"][0][
            "x_preserved"
        ]
        == {"label": "keep"}
    )
    assert replaced.revision.document.manifest.document[
        "x_manifest_preserved"
    ] == {"mode": "opaque"}
    replacement_retry = managed.replace(
        draft_id,
        replacement,
        BytesIO(b"replacement bytes"),
    )
    assert not replacement_retry.created
    assert replacement_retry.revision == replaced.revision

    with pytest.raises(StudioBenchmarkAuthoringIdempotencyConflictError):
        managed.replace(
            draft_id,
            replacement,
            BytesIO(b"different retry bytes"),
        )

    removed = managed.remove(
        draft_id,
        StudioBenchmarkAuthoringContentRemoveRequestV1(
            client_request_id="remove-resource",
            base_revision_id=replaced.revision.revision_id,
            resource_id="fixture-asset",
        ),
    )
    assert removed.created
    assert removed.removed_resource_id == "fixture-asset"
    assert removed.revision.document.resources == ()
    assert removed.revision.document.manifest.document["resources"] == []
    remove_retry = managed.remove(
        draft_id,
        StudioBenchmarkAuthoringContentRemoveRequestV1(
            client_request_id="remove-resource",
            base_revision_id=replaced.revision.revision_id,
            resource_id="fixture-asset",
        ),
    )
    assert not remove_retry.created
    assert remove_retry.revision == removed.revision
    late_upload_retry = managed.upload(
        draft_id,
        upload,
        BytesIO(b"first bytes"),
    )
    assert not late_upload_retry.created
    assert late_upload_retry.revision == uploaded.revision
    assert (
        late_upload_retry.draft.current_revision_id
        == removed.revision.revision_id
    )
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        managed.open_content(
            draft_id,
            removed.revision.revision_id,
            "fixture-asset",
        )

    restarted_content = LocalStudioBenchmarkManagedContent(content.root)
    restarted = StudioBenchmarkAuthoringContentApplicationService(
        repository=SQLiteStudioBenchmarkAuthoringRepository(
            repository.database_path
        ),
        content=restarted_content,
    )
    historical = restarted.open_content(
        draft_id,
        uploaded.revision.revision_id,
        "fixture-asset",
    )
    try:
        assert historical.stream.read() == b"first bytes"
    finally:
        historical.stream.close()


def test_asset_and_ground_truth_projection_is_complete_and_deterministic(
    tmp_path,
) -> None:
    """Sort both inventories while preserving unrelated definition members."""
    definition, managed, _repository, _content = _services(tmp_path)
    created = definition.create_draft(_template_create_payload("create-order"))
    original_tasks = created.revision.document.task_files
    original_protocols = created.revision.document.protocol_files
    asset = managed.upload(
        created.draft.draft_id,
        _upload_request(
            created.revision.revision_id,
            request_id="upload-z-asset",
            resource_id="z-asset",
            path="assets/z.txt",
        ),
        BytesIO(b"asset"),
    )
    ground_truth = managed.upload(
        created.draft.draft_id,
        StudioBenchmarkAuthoringContentUploadRequestV1(
            client_request_id="upload-a-ground-truth",
            base_revision_id=asset.revision.revision_id,
            resource_id="a-ground-truth",
            kind="ground_truth",
            path="ground_truth/a.json",
            media_type="application/json",
        ),
        BytesIO(b'{"answer": true}'),
    )
    assert [item.path for item in ground_truth.revision.document.resources] == [
        "assets/z.txt",
        "ground_truth/a.json",
    ]
    assert [
        item["path"]
        for item in ground_truth.revision.document.manifest.document["resources"]
    ] == ["assets/z.txt", "ground_truth/a.json"]
    assert ground_truth.revision.document.task_files == original_tasks
    assert ground_truth.revision.document.protocol_files == original_protocols


def test_stale_new_command_and_incoherent_base_fail_before_streaming(
    tmp_path,
) -> None:
    """Reject impossible content commands before reading caller bytes."""
    definition, managed, _repository, _content = _services(tmp_path)
    created = definition.create_draft(_template_create_payload("create-stale"))
    draft_id = created.draft.draft_id
    uploaded = managed.upload(
        draft_id,
        _upload_request(created.revision.revision_id),
        BytesIO(b"content"),
    )

    class RecordingStream(BytesIO):
        """Binary stream that records whether service code reads it."""

        read_called = False

        def read(self, size: int = -1) -> bytes:
            """Record and forward one binary read.

            Args:
                size: Requested byte count.

            Raises:
                None.

            Returns:
                Next bytes.
            """
            self.read_called = True
            return super().read(size)

    stale_stream = RecordingStream(b"must not be read")
    with pytest.raises(StudioBenchmarkAuthoringRevisionConflictError):
        managed.upload(
            draft_id,
            _upload_request(
                created.revision.revision_id,
                request_id="new-stale-command",
                resource_id="second-asset",
                path="assets/second.txt",
            ),
            stale_stream,
        )
    assert not stale_stream.read_called

    incoherent_document = uploaded.revision.document.model_dump(
        mode="json",
        by_alias=True,
        exclude_none=True,
    )
    incoherent_document["manifest"]["document"]["resources"][0]["sha256"] = (
        "sha256:" + "0" * 64
    )
    incoherent = definition.save_revision(
        draft_id,
        {
            "schemaVersion": 1,
            "clientRequestId": "save-incoherent-base",
            "baseRevisionId": uploaded.revision.revision_id,
            "document": incoherent_document,
        },
    )
    incoherent_stream = RecordingStream(b"must not be read either")
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        managed.replace(
            draft_id,
            StudioBenchmarkAuthoringContentReplaceRequestV1(
                client_request_id="replace-incoherent",
                base_revision_id=incoherent.revision.revision_id,
                resource_id="fixture-asset",
                media_type="text/plain",
            ),
            incoherent_stream,
        )
    assert not incoherent_stream.read_called


def test_two_content_clients_race_on_one_current_revision(tmp_path) -> None:
    """Allow exactly one concurrent content command to advance the draft."""
    definition, managed, _repository, content = _services(tmp_path)
    created = definition.create_draft(_template_create_payload("create-race"))
    barrier = Barrier(2)
    original_store = content.store_stream

    def synchronized_store(stream, *, max_bytes):
        """Finalize bytes, then release both callers toward the same CAS.

        Args:
            stream: Caller-owned binary source.
            max_bytes: Inclusive resource byte limit.

        Raises:
            StudioBenchmarkAuthoringStorageError: Content storage fails.

        Returns:
            Opaque content identity, digest, and byte size.
        """
        result = original_store(stream, max_bytes=max_bytes)
        barrier.wait(timeout=5)
        return result

    content.store_stream = synchronized_store

    def upload(resource_id: str):
        """Attempt one concurrent upload against the shared base.

        Args:
            resource_id: Unique logical resource identity.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: The peer wins CAS.

        Returns:
            Successful content command result.
        """
        return managed.upload(
            created.draft.draft_id,
            _upload_request(
                created.revision.revision_id,
                request_id=f"race-{resource_id}",
                resource_id=resource_id,
                path=f"assets/{resource_id}.txt",
            ),
            BytesIO(b"same deduplicated race bytes"),
        )

    results = []
    failures = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(upload, "race-first"),
            executor.submit(upload, "race-second"),
        ]
        for future in futures:
            try:
                results.append(future.result(timeout=10))
            except StudioBenchmarkAuthoringRevisionConflictError as error:
                failures.append(error)
    assert len(results) == 1
    assert len(failures) == 1
    current = definition.get_draft(created.draft.draft_id).current_revision
    assert current == results[0].revision
    assert failures[0].current_revision_id == current.revision_id


def test_upload_duplicate_noop_replace_and_cross_draft_scope_fail_closed(
    tmp_path,
) -> None:
    """Reject ambiguous mutation and foreign exact-content capabilities."""
    definition, managed, _repository, _content = _services(tmp_path)
    first = definition.create_draft(_template_create_payload("create-first"))
    uploaded = managed.upload(
        first.draft.draft_id,
        _upload_request(first.revision.revision_id),
        BytesIO(b"same"),
    )
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        managed.upload(
            first.draft.draft_id,
            _upload_request(
                uploaded.revision.revision_id,
                request_id="duplicate-path",
                resource_id="different-id",
            ),
            BytesIO(b"duplicate"),
        )
    with pytest.raises(StudioBenchmarkAuthoringValidationError):
        managed.replace(
            first.draft.draft_id,
            StudioBenchmarkAuthoringContentReplaceRequestV1(
                client_request_id="no-op-replace",
                base_revision_id=uploaded.revision.revision_id,
                resource_id="fixture-asset",
                media_type="text/plain",
            ),
            BytesIO(b"same"),
        )
    assert (
        definition.get_draft(first.draft.draft_id).draft.current_revision_id
        == uploaded.revision.revision_id
    )

    second = definition.create_draft(_template_create_payload("create-second"))
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        managed.open_content(
            second.draft.draft_id,
            uploaded.revision.revision_id,
            "fixture-asset",
        )


@pytest.mark.parametrize(
    "fault",
    ("missing", "size", "digest", "symlink", "directory"),
)
def test_exact_read_detects_missing_size_digest_and_non_regular_objects(
    tmp_path,
    fault: str,
) -> None:
    """Fail before returning a stream for every managed-object integrity fault."""
    definition, managed, _repository, content = _services(tmp_path / fault)
    created = definition.create_draft(
        _template_create_payload(f"create-integrity-{fault}")
    )
    uploaded = managed.upload(
        created.draft.draft_id,
        _upload_request(created.revision.revision_id),
        BytesIO(b"integrity"),
    )
    assert uploaded.resource is not None
    object_path = content.content_path(uploaded.resource.content_identity)
    if fault == "missing":
        object_path.unlink()
    elif fault == "size":
        object_path.write_bytes(b"short")
    elif fault == "digest":
        object_path.write_bytes(b"integritx")
    elif fault == "symlink":
        external = tmp_path / "outside-content"
        external.write_bytes(b"integrity")
        object_path.unlink()
        object_path.symlink_to(external)
    else:
        object_path.unlink()
        object_path.mkdir()
    with pytest.raises(StudioBenchmarkAuthoringStorageError) as failure:
        managed.open_content(
            created.draft.draft_id,
            uploaded.revision.revision_id,
            "fixture-asset",
        )
    assert failure.value.code in {
        "benchmark.authoring.content_integrity",
        "benchmark.authoring.content_unavailable",
        "benchmark.authoring.storage_failed",
    }
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        managed.open_content(
            created.draft.draft_id,
            created.revision.revision_id,
            "fixture-asset",
        )


def test_content_storage_failures_leave_previous_revision_authoritative(
    tmp_path,
    monkeypatch,
) -> None:
    """Clean staging and expose no revision after bounded streaming failures."""
    definition, managed, _repository, content = _services(tmp_path)
    created = definition.create_draft(_template_create_payload("create-failures"))
    draft_id = created.draft.draft_id

    class InterruptedStream(BytesIO):
        """Source that fails after one successful block read."""

        reads = 0

        def read(self, size: int = -1) -> bytes:
            """Return one block and then inject a source read failure.

            Args:
                size: Requested byte count.

            Raises:
                OSError: On every read after the first.

            Returns:
                First source block.
            """
            self.reads += 1
            if self.reads > 1:
                raise OSError("injected source interruption")
            return super().read(1 if size < 0 else min(size, 1))

    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        managed.upload(
            draft_id,
            _upload_request(
                created.revision.revision_id,
                request_id="interrupted-upload",
            ),
            InterruptedStream(b"more than one byte"),
        )
    assert not tuple(content.staging_root.glob(".content-*"))
    assert (
        definition.get_draft(draft_id).draft.current_revision_id
        == created.revision.revision_id
    )

    monkeypatch.setattr(
        "zhixing.studio.benchmark_authoring_content."
        "STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES",
        3,
    )
    with pytest.raises(StudioBenchmarkAuthoringCapacityError) as capacity:
        managed.upload(
            draft_id,
            _upload_request(
                created.revision.revision_id,
                request_id="capacity-upload",
            ),
            BytesIO(b"four"),
        )
    assert capacity.value.code == "benchmark.authoring.content_too_large"
    assert not tuple(content.staging_root.glob(".content-*"))
    assert (
        definition.get_draft(draft_id).draft.current_revision_id
        == created.revision.revision_id
    )


@pytest.mark.parametrize("failure", ("hash", "write", "fsync", "replace"))
def test_content_finalize_failure_injections_do_not_commit_revision(
    tmp_path,
    monkeypatch,
    failure: str,
) -> None:
    """Fail hash, flush, or atomic promotion without a visible child revision."""
    definition, managed, _repository, content = _services(tmp_path / failure)
    created = definition.create_draft(
        _template_create_payload(f"create-{failure}")
    )
    if failure == "hash":
        class FailingHash:
            """SHA-256 test double that rejects the first byte update."""

            def update(self, block: bytes) -> None:
                """Inject one hashing failure.

                Args:
                    block: Ignored source bytes.

                Raises:
                    OSError: Always.

                Returns:
                    None.
                """
                del block
                raise OSError("injected hash failure")

            def hexdigest(self) -> str:
                """Return an unreachable placeholder digest.

                Raises:
                    None.

                Returns:
                    Placeholder lowercase digest.
                """
                return "0" * 64

        monkeypatch.setattr(
            "zhixing.studio.benchmark_authoring_storage.hashlib",
            SimpleNamespace(sha256=FailingHash),
        )
    elif failure == "write":
        real_fdopen = authoring_storage_module.os.fdopen

        class FailingTarget:
            """Context-managed file wrapper that rejects target writes."""

            def __init__(self, target) -> None:
                """Bind the real target so cleanup still closes its descriptor.

                Args:
                    target: Real binary file object.

                Raises:
                    None.

                Returns:
                    None.
                """
                self._target = target

            def __enter__(self):
                """Return this failing wrapper.

                Returns:
                    Active wrapper.
                """
                return self

            def __exit__(self, exc_type, exc_value, traceback) -> None:
                """Close the real target after the injected failure.

                Args:
                    exc_type: Active exception type.
                    exc_value: Active exception value.
                    traceback: Active exception traceback.

                Raises:
                    OSError: Closing the real target fails.

                Returns:
                    None.
                """
                del exc_type, exc_value, traceback
                self._target.close()

            def write(self, block: bytes) -> int:
                """Inject one target write failure.

                Args:
                    block: Ignored source bytes.

                Raises:
                    OSError: Always.

                Returns:
                    Never returns.
                """
                del block
                raise OSError("injected target write failure")

            def flush(self) -> None:
                """Delegate an otherwise unreachable flush.

                Raises:
                    OSError: The real flush fails.

                Returns:
                    None.
                """
                self._target.flush()

            def fileno(self) -> int:
                """Return the real target descriptor.

                Raises:
                    OSError: The target has already closed.

                Returns:
                    Open file descriptor.
                """
                return self._target.fileno()

        def fail_fdopen(descriptor: int, mode: str):
            """Wrap one storage descriptor with the failing target.

            Args:
                descriptor: Open staging descriptor.
                mode: Requested binary file mode.

            Raises:
                OSError: The real descriptor cannot be opened.

            Returns:
                Context-managed failing target.
            """
            return FailingTarget(real_fdopen(descriptor, mode))

        monkeypatch.setattr(
            "zhixing.studio.benchmark_authoring_storage.os.fdopen",
            fail_fdopen,
        )
    elif failure == "fsync":
        def fail_fsync(descriptor: int) -> None:
            """Inject one file flush failure.

            Args:
                descriptor: Ignored file descriptor.

            Raises:
                OSError: Always.

            Returns:
                None.
            """
            del descriptor
            raise OSError("injected fsync failure")

        monkeypatch.setattr(
            "zhixing.studio.benchmark_authoring_storage.os.fsync",
            fail_fsync,
        )
    else:
        def fail_replace(source: Path, destination: Path) -> None:
            """Inject one atomic promotion failure.

            Args:
                source: Ignored staging path.
                destination: Ignored immutable object path.

            Raises:
                OSError: Always.

            Returns:
                None.
            """
            del source, destination
            raise OSError("injected replace failure")

        monkeypatch.setattr(
            "zhixing.studio.benchmark_authoring_storage.os.replace",
            fail_replace,
        )

    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        managed.upload(
            created.draft.draft_id,
            _upload_request(
                created.revision.revision_id,
                request_id=f"{failure}-upload",
            ),
            BytesIO(b"failure fixture"),
        )
    assert not tuple(content.staging_root.glob(".content-*"))
    assert (
        definition.get_draft(
            created.draft.draft_id
        ).draft.current_revision_id
        == created.revision.revision_id
    )


def test_repository_failure_after_promotion_leaves_only_unreachable_object(
    tmp_path,
    monkeypatch,
) -> None:
    """Document the content-first orphan trade-off without visible revision."""
    definition, managed, repository, content = _services(tmp_path)
    created = definition.create_draft(_template_create_payload("create-orphan"))

    def fail_save(*args, **kwargs):
        """Inject one post-promotion durable transaction failure.

        Args:
            *args: Ignored repository inputs.
            **kwargs: Ignored repository inputs.

        Raises:
            StudioBenchmarkAuthoringStorageError: Always.

        Returns:
            Never returns.
        """
        del args, kwargs
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.storage_failed",
            "Injected repository failure",
        )

    monkeypatch.setattr(repository, "save_revision", fail_save)
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        managed.upload(
            created.draft.draft_id,
            _upload_request(created.revision.revision_id),
            BytesIO(b"orphaned but immutable"),
        )
    assert (
        definition.get_draft(
            created.draft.draft_id
        ).draft.current_revision_id
        == created.revision.revision_id
    )
    objects = tuple(
        path
        for path in (content.root / "objects").rglob("*")
        if path.is_file()
    )
    assert len(objects) == 1
    with pytest.raises(StudioBenchmarkAuthoringNotFoundError):
        managed.open_content(
            created.draft.draft_id,
            created.revision.revision_id,
            "fixture-asset",
        )


def test_complete_content_journey_never_crosses_runtime_boundaries(
    tmp_path,
    monkeypatch,
) -> None:
    """Require zero adjacent runtime or product calls through content editing."""
    calls: list[str] = []

    def forbidden(name: str):
        """Build one fail-fast adjacent-boundary replacement.

        Args:
            name: Stable boundary label.

        Raises:
            None.

        Returns:
            Callable that records and rejects every invocation.
        """

        def invoke(*args, **kwargs):
            """Reject one unexpected adjacent-boundary call.

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
            raise AssertionError(f"content authoring crossed {name}")

        return invoke

    boundaries = (
        (
            "zhixing.benchmark.runtime.resolver."
            "RegistryBenchmarkComponentResolver.generate_task_value",
            "initializer",
        ),
        (
            "zhixing.benchmark.runtime.resolver."
            "RegistryBenchmarkComponentResolver.resolve_environment",
            "environment",
        ),
        (
            "zhixing.benchmark.runtime.resolver."
            "RegistryBenchmarkComponentResolver.resolve_evaluator",
            "evaluator",
        ),
        (
            "zhixing.studio.run_execution.AndroidDeviceProfileResolver.resolve",
            "device",
        ),
        (
            "zhixing.engine.agent.agent_factory.AgentFactory.build",
            "agent-plugin-construction",
        ),
        (
            "zhixing.studio.run_execution."
            "ProductionComponentResolverFactory.create",
            "model-secret-component",
        ),
        (
            "zhixing.runtime.facade.run_agent_graph",
            "agent-runtime",
        ),
        (
            "socket.create_connection",
            "network",
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
        (
            "zhixing.studio.migration.migrate_studio_flow_document",
            "migration",
        ),
        (
            "zhixing.studio.service.StudioApplicationService."
            "export_replay_bundle",
            "export",
        ),
    )
    for target, name in boundaries:
        monkeypatch.setattr(target, forbidden(name))

    definition, managed, _repository, _content = _services(tmp_path)
    created = definition.create_draft(
        _template_create_payload("content-no-runtime")
    )
    uploaded = managed.upload(
        created.draft.draft_id,
        _upload_request(created.revision.revision_id),
        BytesIO(b"runtime-free upload"),
    )
    opened = managed.open_content(
        created.draft.draft_id,
        uploaded.revision.revision_id,
        "fixture-asset",
    )
    try:
        assert opened.stream.read() == b"runtime-free upload"
    finally:
        opened.stream.close()
    replaced = managed.replace(
        created.draft.draft_id,
        StudioBenchmarkAuthoringContentReplaceRequestV1(
            client_request_id="content-no-runtime-replace",
            base_revision_id=uploaded.revision.revision_id,
            resource_id="fixture-asset",
            media_type="application/octet-stream",
        ),
        BytesIO(b"runtime-free replacement"),
    )
    managed.remove(
        created.draft.draft_id,
        StudioBenchmarkAuthoringContentRemoveRequestV1(
            client_request_id="content-no-runtime-remove",
            base_revision_id=replaced.revision.revision_id,
            resource_id="fixture-asset",
        ),
    )
    assert calls == []


def test_resource_model_rejects_header_unsafe_media_type() -> None:
    """Keep persisted resource metadata safe for exact HTTP projection."""
    with pytest.raises(ValidationError):
        StudioBenchmarkAuthoringResourceV1(
            id="fixture",
            kind="asset",
            path="assets/fixture.txt",
            media_type="text/plain\nX-Bad: yes",
            sha256="sha256:" + "a" * 64,
            size=1,
            content_identity="benchmark-content-" + "a" * 64,
        )
