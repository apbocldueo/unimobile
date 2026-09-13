"""Private disposable Package reconstruction for authoring analysis."""

from __future__ import annotations

import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterator

import yaml

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringStorageError,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES,
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringResourceV1,
)
from .benchmark_authoring_protocols import StudioBenchmarkManagedContent


_COPY_BLOCK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StudioBenchmarkMissingManagedResourceError(Exception):
    """Internal safe fact that one declared logical resource has no bytes."""

    resource_id: str
    member_path: str

    def __str__(self) -> str:
        """Return a bounded message without content or host identity.

        Args:
            None.

        Raises:
            None.

        Returns:
            Safe generic missing-content message.
        """
        return "Declared Benchmark resource content is unavailable"


def _definition_bytes(value: object, *, suffix: str) -> bytes:
    """Serialize one parsed definition member deterministically.

    Args:
        value: Safe parsed JSON-compatible definition value.
        suffix: Destination file suffix controlling JSON or YAML encoding.

    Raises:
        StudioBenchmarkAuthoringCapacityError: Serialized member is too large.
        StudioBenchmarkAuthoringStorageError: Serialization fails.

    Returns:
        Deterministic UTF-8 definition bytes.
    """
    try:
        if suffix == ".json":
            payload = (
                json.dumps(
                    value,
                    ensure_ascii=False,
                    sort_keys=True,
                    allow_nan=False,
                    separators=(",", ":"),
                )
                + "\n"
            ).encode("utf-8")
        else:
            payload = yaml.safe_dump(
                value,
                allow_unicode=True,
                sort_keys=True,
            ).encode("utf-8")
    except (TypeError, ValueError, yaml.YAMLError) as error:
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.analysis_storage_failed",
            "Benchmark analysis definition cannot be serialized",
        ) from error
    if len(payload) > STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES:
        raise StudioBenchmarkAuthoringCapacityError(
            "benchmark.authoring.analysis_definition_too_large",
            "Benchmark analysis definition exceeds its safe limit",
        )
    return payload


def _write_member(root: Path, relative_path: str, payload: bytes) -> None:
    """Write one already validated Package-relative member in private staging.

    Args:
        root: Fresh private Package root.
        relative_path: Strict authoring Package-relative path.
        payload: Deterministic member bytes.

    Raises:
        StudioBenchmarkAuthoringStorageError: Parent or file cannot be written.

    Returns:
        None.
    """
    destination = root.joinpath(*relative_path.split("/"))
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except OSError as error:
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.analysis_storage_failed",
            "Benchmark analysis staging is unavailable",
        ) from error


def _copy_verified_resource(
    content: StudioBenchmarkManagedContent,
    root: Path,
    resource: StudioBenchmarkAuthoringResourceV1,
) -> None:
    """Copy one verified immutable resource into disposable analysis staging.

    Args:
        content: Private immutable managed-content boundary.
        root: Fresh private Package root.
        resource: Exact revision-owned resource descriptor.

    Raises:
        StudioBenchmarkMissingManagedResourceError: Bytes are unavailable.
        StudioBenchmarkAuthoringStorageError: Integrity or copying fails.

    Returns:
        None.
    """
    try:
        source = content.open_verified(
            resource.content_identity,
            expected_sha256=resource.sha256,
            expected_size=resource.size,
        )
    except StudioBenchmarkAuthoringStorageError as error:
        if error.code == "benchmark.authoring.content_unavailable":
            raise StudioBenchmarkMissingManagedResourceError(
                resource_id=resource.id,
                member_path=resource.path,
            ) from error
        raise
    destination = root.joinpath(*resource.path.split("/"))
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        copied = 0
        with source:
            with destination.open("xb") as writer:
                while True:
                    block = source.read(_COPY_BLOCK_BYTES)
                    if not block:
                        break
                    copied += len(block)
                    if (
                        copied > resource.size
                        or copied > STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES
                    ):
                        raise StudioBenchmarkAuthoringStorageError(
                            "benchmark.authoring.content_integrity",
                            "Managed Benchmark content does not match its revision",
                        )
                    writer.write(block)
                writer.flush()
                os.fsync(writer.fileno())
        if copied != resource.size:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.content_integrity",
                "Managed Benchmark content does not match its revision",
            )
    except StudioBenchmarkAuthoringStorageError:
        raise
    except OSError as error:
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.analysis_storage_failed",
            "Benchmark analysis staging is unavailable",
        ) from error


class StudioBenchmarkAuthoringPackageMaterializer:
    """Reconstruct exact authoring revisions as private disposable Packages."""

    def __init__(
        self,
        content: StudioBenchmarkManagedContent,
        *,
        staging_root: str | Path,
    ) -> None:
        """Bind verified content and a server-owned analysis staging root.

        Args:
            content: Private immutable managed-content boundary.
            staging_root: Server-owned directory for disposable analysis roots.

        Raises:
            StudioBenchmarkAuthoringStorageError: Staging cannot be prepared.

        Returns:
            None.
        """
        self._content = content
        self._staging_root = Path(staging_root)
        try:
            self._staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.analysis_storage_failed",
                "Benchmark analysis staging is unavailable",
            ) from error

    @contextmanager
    def materialize(
        self,
        document: StudioBenchmarkAuthoringDocumentV1,
    ) -> Iterator[Path]:
        """Yield one exact disposable Package and remove it on every exit.

        Args:
            document: Exact immutable revision authoring document.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Declared closure is too large.
            StudioBenchmarkMissingManagedResourceError: A resource is unavailable.
            StudioBenchmarkAuthoringStorageError: Reconstruction or cleanup fails.

        Yields:
            Fresh private Package root for Core definition analysis only.
        """
        total_resources = sum(item.size for item in document.resources)
        if total_resources > STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.analysis_content_too_large",
                "Benchmark analysis content exceeds its safe aggregate limit",
            )
        try:
            with tempfile.TemporaryDirectory(
                prefix="analysis-",
                dir=self._staging_root,
            ) as temporary:
                root = Path(temporary) / "package"
                root.mkdir(mode=0o700)
                for directory in document.directories:
                    (root / directory).mkdir(mode=0o700)
                _write_member(
                    root,
                    document.manifest.path,
                    _definition_bytes(
                        document.manifest.document,
                        suffix=".yaml",
                    ),
                )
                for task_file in document.task_files:
                    _write_member(
                        root,
                        task_file.path,
                        _definition_bytes(task_file.tasks, suffix=".json"),
                    )
                for protocol_file in document.protocol_files:
                    _write_member(
                        root,
                        protocol_file.path,
                        _definition_bytes(
                            protocol_file.document,
                            suffix=Path(protocol_file.path).suffix.lower(),
                        ),
                    )
                for resource in document.resources:
                    _copy_verified_resource(self._content, root, resource)
                yield root
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkMissingManagedResourceError,
            StudioBenchmarkAuthoringStorageError,
        ):
            raise
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.analysis_storage_failed",
                "Benchmark analysis staging is unavailable",
            ) from error


__all__ = [
    "StudioBenchmarkAuthoringPackageMaterializer",
    "StudioBenchmarkMissingManagedResourceError",
]
