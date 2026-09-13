"""Private disposable Benchmark authoring Package reconstruction tests."""

from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from pydantic import ValidationError

from zhixing.studio.benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringStorageError,
)
from zhixing.studio.benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
    StudioBenchmarkMissingManagedResourceError,
)
from zhixing.studio.benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    StudioBenchmarkAuthoringDocumentV1,
)

from .test_benchmark_authoring_analysis import _analysis_fixture


def _with_resource(
    document: object,
    *,
    resource_id: str = "fixture",
    path: str = "assets/fixture.txt",
    sha256: str = "sha256:" + "a" * 64,
    size: int = 7,
    content_identity: str = "benchmark-content-" + "a" * 64,
) -> StudioBenchmarkAuthoringDocumentV1:
    """Return an authoring document with one coherent resource descriptor.

    Args:
        document: Existing strict authoring document.
        resource_id: Stable logical resource identity.
        path: Package-relative resource member path.
        sha256: Declared content digest.
        size: Declared byte size.
        content_identity: Private immutable managed-content identity.

    Raises:
        ValidationError: The resulting closed document is invalid.

    Returns:
        Strict augmented authoring document.
    """
    payload = document.model_dump(mode="json", by_alias=True)  # type: ignore[attr-defined]
    manifest_resource = {
        "id": resource_id,
        "kind": "asset",
        "path": path,
        "media_type": "text/plain",
        "sha256": sha256,
        "size": size,
    }
    payload["manifest"]["document"]["resources"] = [manifest_resource]
    payload["resources"] = [
        {
            **manifest_resource,
            "mediaType": manifest_resource["media_type"],
            "contentIdentity": content_identity,
        }
    ]
    payload["resources"][0].pop("media_type")
    return StudioBenchmarkAuthoringDocumentV1.model_validate(payload)


def test_materializer_serializes_exact_deterministic_closed_definition(
    tmp_path: Path,
) -> None:
    """Reconstruct only declared members and produce byte-identical repeats."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    analysis = fixture["analysis"]
    materializer = analysis._materializer  # type: ignore[union-attr]

    def snapshot() -> dict[str, bytes]:
        """Capture declared files while the disposable root is alive.

        Returns:
            Package-relative bytes keyed by safe member path.
        """
        with materializer.materialize(revision.document) as root:  # type: ignore[union-attr]
            return {
                item.relative_to(root).as_posix(): item.read_bytes()
                for item in root.rglob("*")
                if item.is_file()
            }

    first = snapshot()
    second = snapshot()
    assert first == second
    assert set(first) == {
        "benchmark.yaml",
        "tasks/test.json",
        "protocols/default.yaml",
    }
    assert "README.md" not in first


def test_materializer_supports_safe_unicode_definition_member_paths(
    tmp_path: Path,
) -> None:
    """Preserve normalized Unicode paths within the closed task inventory."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    analysis = fixture["analysis"]
    payload = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    payload["manifest"]["document"]["splits"]["test"]["files"] = [
        "tasks/测试.json"
    ]
    payload["taskFiles"][0]["path"] = "tasks/测试.json"
    document = StudioBenchmarkAuthoringDocumentV1.model_validate(payload)
    with analysis._materializer.materialize(document) as root:  # type: ignore[union-attr]
        assert (root / "tasks/测试.json").is_file()


def test_materializer_reports_missing_bytes_without_partial_package(
    tmp_path: Path,
) -> None:
    """Identify a missing logical resource while removing partial staging."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    analysis = fixture["analysis"]
    staging = fixture["staging"]
    document = _with_resource(revision.document)  # type: ignore[union-attr]
    with pytest.raises(StudioBenchmarkMissingManagedResourceError) as caught:
        with analysis._materializer.materialize(document):  # type: ignore[union-attr]
            raise AssertionError("missing content must not yield a Package")
    assert caught.value.resource_id == "fixture"
    assert caught.value.member_path == "assets/fixture.txt"
    assert list(staging.iterdir()) == []  # type: ignore[union-attr]


@pytest.mark.parametrize("drift", ("digest", "size", "symlink"))
def test_materializer_fails_closed_on_content_integrity_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    """Reject digest, size, and non-regular managed-content mismatches."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    analysis = fixture["analysis"]
    staging = fixture["staging"]
    content = analysis._materializer._content  # type: ignore[union-attr]
    raw = b"trusted"
    content_identity, digest, size = content.store_stream(
        BytesIO(raw), max_bytes=100
    )
    declared_digest = digest
    declared_size = size
    if drift == "digest":
        declared_digest = "sha256:" + "0" * 64
    elif drift == "size":
        declared_size += 1
    else:
        object_path = content.content_path(content_identity)
        target = tmp_path / "symlink-target"
        target.write_bytes(raw)
        object_path.unlink()
        object_path.symlink_to(target)
    document = _with_resource(
        revision.document,  # type: ignore[union-attr]
        sha256=declared_digest,
        size=declared_size,
        content_identity=content_identity,
    )
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        with analysis._materializer.materialize(document):  # type: ignore[union-attr]
            raise AssertionError("corrupt content must not yield a Package")
    assert list(staging.iterdir()) == []  # type: ignore[union-attr]


def test_materializer_checks_aggregate_capacity_before_content_reads(
    tmp_path: Path,
) -> None:
    """Reject declared aggregate bytes before opening any content identity."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    analysis = fixture["analysis"]
    payload = revision.document.model_dump(  # type: ignore[union-attr]
        mode="json", by_alias=True
    )
    manifest_resources = []
    resources = []
    for index in range(5):
        raw = {
            "id": f"fixture-{index}",
            "kind": "asset",
            "path": f"assets/fixture-{index}.bin",
            "media_type": "application/octet-stream",
            "sha256": "sha256:" + f"{index + 1:x}" * 64,
            "size": STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
        }
        manifest_resources.append(raw)
        resources.append(
            {
                **raw,
                "mediaType": raw["media_type"],
                "contentIdentity": "benchmark-content-" + f"{index + 1:x}" * 64,
            }
        )
        resources[-1].pop("media_type")
    payload["manifest"]["document"]["resources"] = manifest_resources
    payload["resources"] = resources
    document = StudioBenchmarkAuthoringDocumentV1.model_validate(payload)
    with pytest.raises(StudioBenchmarkAuthoringCapacityError):
        with analysis._materializer.materialize(document):  # type: ignore[union-attr]
            raise AssertionError("overbound closure must not yield")


def test_materializer_cleans_partial_copy_after_interrupted_read(
    tmp_path: Path,
) -> None:
    """Remove a partly written resource when its verified stream later fails."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    staging = fixture["staging"]
    raw = b"partial"
    digest = "sha256:" + hashlib.sha256(raw).hexdigest()
    document = _with_resource(
        revision.document,  # type: ignore[union-attr]
        sha256=digest,
        size=len(raw),
    )

    class InterruptedStream(BytesIO):
        """Yield one block and then simulate an interrupted verified read."""

        def read(self, size: int = -1) -> bytes:
            """Return bytes once, then raise an I/O failure.

            Args:
                size: Requested byte bound.

            Raises:
                OSError: After the first non-empty read.

            Returns:
                First source block.
            """
            if self.tell() == len(raw):
                raise OSError("injected interrupted read")
            return super().read(size)

    class InterruptedContent:
        """Minimal verified-content test double with one failing stream."""

        def open_verified(
            self,
            content_identity: str,
            *,
            expected_sha256: str,
            expected_size: int,
        ) -> BytesIO:
            """Return the injected stream after asserting exact descriptors.

            Args:
                content_identity: Requested private identity.
                expected_sha256: Revision-declared digest.
                expected_size: Revision-declared size.

            Raises:
                AssertionError: Descriptor facts differ from the fixture.

            Returns:
                Interrupting binary stream.
            """
            assert content_identity == "benchmark-content-" + "a" * 64
            assert expected_sha256 == digest
            assert expected_size == len(raw)
            return InterruptedStream(raw)

    materializer = StudioBenchmarkAuthoringPackageMaterializer(
        InterruptedContent(),  # type: ignore[arg-type]
        staging_root=staging,  # type: ignore[arg-type]
    )
    with pytest.raises(StudioBenchmarkAuthoringStorageError):
        with materializer.materialize(document):
            raise AssertionError("interrupted content must not yield")
    assert list(staging.iterdir()) == []  # type: ignore[union-attr]


def test_authoring_contract_rejects_resource_path_escape_before_materialization(
    tmp_path: Path,
) -> None:
    """Keep parent traversal outside the representable closed inventory."""
    fixture = _analysis_fixture(tmp_path)
    revision = fixture["revision"]
    with pytest.raises(ValidationError):
        _with_resource(
            revision.document,  # type: ignore[union-attr]
            path="assets/../../escape.txt",
        )
