"""Managed scaffold and closed-closure Catalog import for Benchmark drafts."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from pydantic import ValidationError

from zhixing.benchmark import (
    BenchmarkDefinitionError,
    BenchmarkPackage,
    canonical_hash,
    load_manifest,
    load_mapping,
    load_protocol,
    scaffold_benchmark_package,
)
from zhixing.benchmark.loaders import load_package_suites

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringDriftError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS,
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES,
    StudioBenchmarkAuthoringDocumentV1,
    StudioBenchmarkAuthoringManifestV1,
    StudioBenchmarkAuthoringProtocolFileV1,
    StudioBenchmarkAuthoringResourceV1,
    StudioBenchmarkAuthoringTaskFileV1,
    StudioBenchmarkTemplateDraftSourceV1,
)
from .benchmark_authoring_protocols import StudioBenchmarkManagedContent
from .benchmark_service import StudioBenchmarkAuthoringCatalogSource


_COPY_BLOCK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class PreparedStudioBenchmarkAuthoringDocument:
    """One coherent managed document and safe source identity facts."""

    document: StudioBenchmarkAuthoringDocumentV1
    package_identity: str
    package_content_identity: str
    source_fingerprint: str


@dataclass(frozen=True)
class _CopiedMember:
    """Internal immutable fingerprint fact for one declared source member."""

    path: str
    sha256: str
    size: int


def _logical_path(value: str) -> PurePosixPath:
    """Validate one normalized Package-relative path.

    Args:
        value: Candidate declared path.

    Raises:
        StudioBenchmarkAuthoringValidationError: Path is unsafe.

    Returns:
        Validated logical POSIX path.
    """
    logical = PurePosixPath(value)
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or logical.is_absolute()
        or ".." in logical.parts
        or "." in logical.parts
        or logical.as_posix() != value
    ):
        raise StudioBenchmarkAuthoringValidationError(
            "benchmark.authoring.source_path_invalid",
            "Declared Benchmark source path is invalid",
        )
    return logical


def _regular_source(root: Path, logical_path: str) -> Path:
    """Resolve a declared source member without following symlink components.

    Args:
        root: Trusted Catalog Package root.
        logical_path: Validated Package-relative path.

    Raises:
        StudioBenchmarkAuthoringValidationError: A component is unsafe.
        StudioBenchmarkAuthoringStorageError: Metadata cannot be inspected.

    Returns:
        Existing regular source member below the resolved Package root.
    """
    logical = _logical_path(logical_path)
    resolved_root = root.expanduser().resolve()
    candidate = resolved_root
    try:
        for index, part in enumerate(logical.parts):
            candidate = candidate / part
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise StudioBenchmarkAuthoringValidationError(
                    "benchmark.authoring.source_unsafe",
                    "Declared Benchmark source member must not use symlinks",
                )
            if index < len(logical.parts) - 1:
                if not stat.S_ISDIR(metadata.st_mode):
                    raise StudioBenchmarkAuthoringValidationError(
                        "benchmark.authoring.source_unsafe",
                        "Declared Benchmark source parent must be a directory",
                    )
            elif not stat.S_ISREG(metadata.st_mode):
                raise StudioBenchmarkAuthoringValidationError(
                    "benchmark.authoring.source_unsafe",
                    "Declared Benchmark source member must be a regular file",
                )
        candidate.relative_to(resolved_root)
    except StudioBenchmarkAuthoringValidationError:
        raise
    except (FileNotFoundError, OSError, ValueError) as error:
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.source_unreadable",
            "Declared Benchmark source member cannot be read",
        ) from error
    return candidate


def _copy_member(
    source_root: Path,
    destination_root: Path,
    logical_path: str,
    *,
    max_bytes: int,
) -> _CopiedMember:
    """Copy and hash one bounded source member into managed staging.

    Args:
        source_root: Trusted Package root.
        destination_root: Fresh private snapshot root.
        logical_path: Declared Package-relative member path.
        max_bytes: Inclusive byte limit.

    Raises:
        StudioBenchmarkAuthoringCapacityError: Member exceeds its bound.
        StudioBenchmarkAuthoringValidationError: Member changes or is unsafe.
        StudioBenchmarkAuthoringStorageError: Copying fails.

    Returns:
        Copied member fingerprint facts.
    """
    source = _regular_source(source_root, logical_path)
    before = source.lstat()
    if before.st_size > max_bytes:
        raise StudioBenchmarkAuthoringCapacityError(
            "benchmark.authoring.content_too_large",
            "Benchmark authoring content exceeds its safe limit",
        )
    destination = destination_root / Path(*_logical_path(logical_path).parts)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(source, flags)
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino)
            != (before.st_dev, before.st_ino)
        ):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.source_drift",
                "Declared Benchmark source changed during import",
            )
        digest = hashlib.sha256()
        size = 0
        with os.fdopen(descriptor, "rb") as reader:
            descriptor = None
            with destination.open("xb") as writer:
                while True:
                    block = reader.read(_COPY_BLOCK_BYTES)
                    if not block:
                        break
                    size += len(block)
                    if size > max_bytes:
                        raise StudioBenchmarkAuthoringCapacityError(
                            "benchmark.authoring.content_too_large",
                            "Benchmark authoring content exceeds its safe limit",
                        )
                    digest.update(block)
                    writer.write(block)
                writer.flush()
                os.fsync(writer.fileno())
        after = source.lstat()
        if (
            stat.S_ISLNK(after.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or (
                before.st_dev,
                before.st_ino,
                before.st_size,
                before.st_mtime_ns,
            )
            != (
                after.st_dev,
                after.st_ino,
                after.st_size,
                after.st_mtime_ns,
            )
        ):
            raise StudioBenchmarkAuthoringDriftError(
                "benchmark.authoring.source_drift",
                "Benchmark Catalog source changed during import",
            )
        return _CopiedMember(
            path=logical_path,
            sha256=f"sha256:{digest.hexdigest()}",
            size=size,
        )
    except (
        StudioBenchmarkAuthoringCapacityError,
        StudioBenchmarkAuthoringDriftError,
        StudioBenchmarkAuthoringValidationError,
    ):
        raise
    except OSError as error:
        raise StudioBenchmarkAuthoringStorageError(
            "benchmark.authoring.source_unreadable",
            "Declared Benchmark source member cannot be copied",
        ) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _load_task_array(path: Path) -> tuple[Any, ...]:
    """Load one parsed task array without applying semantic task validation.

    Args:
        path: Managed task JSON file.

    Raises:
        StudioBenchmarkAuthoringValidationError: JSON is invalid or not an array.

    Returns:
        Parsed task tuple.
    """
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise StudioBenchmarkAuthoringValidationError(
            "benchmark.authoring.definition_invalid",
            "Declared Benchmark task file cannot be parsed",
        ) from error
    if not isinstance(value, list):
        raise StudioBenchmarkAuthoringValidationError(
            "benchmark.authoring.definition_invalid",
            "Declared Benchmark task file root must be an array",
        )
    return tuple(value)


class StudioBenchmarkAuthoringPackageAdapter:
    """Prepare strict authoring documents from managed template/Catalog copies."""

    def __init__(
        self,
        content_store: StudioBenchmarkManagedContent,
        *,
        staging_root: Path,
    ) -> None:
        """Bind the adapter to server-owned staging and immutable content.

        Args:
            content_store: Immutable managed resource byte store.
            staging_root: Private staging directory.

        Raises:
            StudioBenchmarkAuthoringStorageError: Staging cannot be prepared.

        Returns:
            None.
        """
        self._content_store = content_store
        self._staging_root = Path(staging_root)
        try:
            self._staging_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring staging is unavailable",
            ) from error

    def from_template(
        self,
        source: StudioBenchmarkTemplateDraftSourceV1,
    ) -> PreparedStudioBenchmarkAuthoringDocument:
        """Create and ingest a built-in scaffold in fresh private staging.

        Args:
            source: Strict template and Package identity parameters.

        Raises:
            StudioBenchmarkAuthoringValidationError: Scaffold cannot be parsed.
            StudioBenchmarkAuthoringStorageError: Staging or scaffold fails.

        Returns:
            Managed strict authoring document.
        """
        try:
            with tempfile.TemporaryDirectory(
                prefix="template-",
                dir=self._staging_root,
            ) as temporary:
                root = Path(temporary) / "package"
                scaffold_benchmark_package(
                    root,
                    name=source.package_name,
                    publisher=source.publisher,
                    version=source.version,
                    template=source.template,
                    force=False,
                )
                return self._snapshot_document(root)
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkAuthoringDriftError,
            StudioBenchmarkAuthoringStorageError,
            StudioBenchmarkAuthoringValidationError,
        ):
            raise
        except (OSError, ValueError, FileExistsError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.scaffold_failed",
                "Benchmark scaffold could not be prepared safely",
            ) from error

    def from_catalog(
        self,
        source: StudioBenchmarkAuthoringCatalogSource,
    ) -> PreparedStudioBenchmarkAuthoringDocument:
        """Copy and verify one opaque available Catalog source.

        Args:
            source: Internal path-bearing Catalog source facts.

        Raises:
            StudioBenchmarkAuthoringDriftError: Current content changed.
            StudioBenchmarkAuthoringValidationError: Declared closure is unsafe.
            StudioBenchmarkAuthoringStorageError: Source cannot be copied.

        Returns:
            Independent managed authoring document.
        """
        return self._snapshot_document(
            source.root,
            expected_package_identity=source.package_identity,
            expected_package_content_identity=(
                source.package_content_identity
            ),
            expected_protocol_identity=source.protocol_identity,
        )

    def _snapshot_document(
        self,
        source_root: Path,
        *,
        expected_package_identity: str | None = None,
        expected_package_content_identity: str | None = None,
        expected_protocol_identity: str | None = None,
    ) -> PreparedStudioBenchmarkAuthoringDocument:
        """Copy a declared closure, reparse it, and finalize resource bytes.

        Args:
            source_root: Trusted template or Catalog Package root.
            expected_package_identity: Optional selected Catalog identity.
            expected_package_content_identity: Optional frozen semantic content.
            expected_protocol_identity: Optional frozen default Protocol identity.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Closure exceeds a bound.
            StudioBenchmarkAuthoringDriftError: Frozen Catalog facts disagree.
            StudioBenchmarkAuthoringValidationError: Managed definitions are unsafe.
            StudioBenchmarkAuthoringStorageError: Source or staging cannot be read.

        Returns:
            Coherent strict authoring document and source identities.
        """
        try:
            with tempfile.TemporaryDirectory(
                prefix="snapshot-",
                dir=self._staging_root,
            ) as temporary:
                snapshot_root = Path(temporary)
                copied: dict[str, _CopiedMember] = {}
                manifest_member = _copy_member(
                    source_root,
                    snapshot_root,
                    "benchmark.yaml",
                    max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
                )
                copied[manifest_member.path] = manifest_member
                manifest = load_manifest(snapshot_root)
                task_paths = sorted(
                    {
                        path
                        for split in manifest.splits.values()
                        for path in split.files
                    }
                )
                protocol_paths = (
                    [manifest.default_protocol]
                    if manifest.default_protocol is not None
                    else []
                )
                resource_paths = sorted(item.path for item in manifest.resources)
                declared_paths = [
                    "benchmark.yaml",
                    *task_paths,
                    *protocol_paths,
                    *resource_paths,
                ]
                if len(declared_paths) != len(set(declared_paths)):
                    raise StudioBenchmarkAuthoringValidationError(
                        "benchmark.authoring.inventory_duplicate",
                        "Benchmark declared member paths must be unique",
                    )
                if len(declared_paths) > STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS:
                    raise StudioBenchmarkAuthoringCapacityError(
                        "benchmark.authoring.member_limit",
                        "Benchmark declared closure exceeds its member limit",
                    )
                definition_size = manifest_member.size
                total_size = manifest_member.size
                for path in [*task_paths, *protocol_paths]:
                    member = _copy_member(
                        source_root,
                        snapshot_root,
                        path,
                        max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES,
                    )
                    copied[path] = member
                    definition_size += member.size
                    total_size += member.size
                    if (
                        definition_size
                        > STUDIO_BENCHMARK_AUTHORING_MAX_DEFINITION_BYTES
                    ):
                        raise StudioBenchmarkAuthoringCapacityError(
                            "benchmark.authoring.definition_too_large",
                            "Benchmark definition exceeds its safe byte limit",
                        )
                for path in resource_paths:
                    member = _copy_member(
                        source_root,
                        snapshot_root,
                        path,
                        max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
                    )
                    copied[path] = member
                    total_size += member.size
                    if total_size > STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES:
                        raise StudioBenchmarkAuthoringCapacityError(
                            "benchmark.authoring.import_too_large",
                            "Benchmark declared closure exceeds its total limit",
                        )
                return self._document_from_snapshot(
                    snapshot_root,
                    copied,
                    expected_package_identity=expected_package_identity,
                    expected_package_content_identity=(
                        expected_package_content_identity
                    ),
                    expected_protocol_identity=expected_protocol_identity,
                )
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkAuthoringDriftError,
            StudioBenchmarkAuthoringStorageError,
            StudioBenchmarkAuthoringValidationError,
        ):
            raise
        except (BenchmarkDefinitionError, ValidationError) as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.definition_invalid",
                "Benchmark declared closure cannot be parsed safely",
            ) from error
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark declared closure could not be staged",
            ) from error

    def _document_from_snapshot(
        self,
        snapshot_root: Path,
        copied: dict[str, _CopiedMember],
        *,
        expected_package_identity: str | None,
        expected_package_content_identity: str | None,
        expected_protocol_identity: str | None,
    ) -> PreparedStudioBenchmarkAuthoringDocument:
        """Reparse a managed snapshot and bind immutable resource content.

        Args:
            snapshot_root: Fresh private declared-closure snapshot.
            copied: Fingerprints for every copied member.
            expected_package_identity: Optional selected Catalog identity.
            expected_package_content_identity: Optional selected Catalog content.
            expected_protocol_identity: Optional selected Protocol identity.

        Raises:
            StudioBenchmarkAuthoringDriftError: Frozen Catalog facts disagree.
            StudioBenchmarkAuthoringValidationError: Parsed envelope is unsafe.
            StudioBenchmarkAuthoringStorageError: Resource finalization fails.

        Returns:
            Strict authoring document and coherent identity facts.
        """
        manifest = load_manifest(snapshot_root)
        raw_manifest = load_mapping(snapshot_root / "benchmark.yaml")
        suites = load_package_suites(snapshot_root, manifest)
        package = BenchmarkPackage(manifest=manifest, suites=suites)
        package_identity = manifest.identity.identifier
        if (
            expected_package_identity is not None
            and package_identity != expected_package_identity
        ) or (
            expected_package_content_identity is not None
            and package.content_identity != expected_package_content_identity
        ):
            raise StudioBenchmarkAuthoringDriftError(
                "benchmark.authoring.source_drift",
                "Benchmark Catalog source no longer matches the selected entry",
            )
        task_paths = sorted(
            {
                path
                for split in manifest.splits.values()
                for path in split.files
            }
        )
        task_files = tuple(
            StudioBenchmarkAuthoringTaskFileV1(
                path=path,
                tasks=_load_task_array(
                    snapshot_root / Path(*PurePosixPath(path).parts)
                ),
            )
            for path in task_paths
        )
        protocol_files: tuple[StudioBenchmarkAuthoringProtocolFileV1, ...] = ()
        protocol_identity: str | None = None
        if manifest.default_protocol is not None:
            protocol_path = snapshot_root / Path(
                *PurePosixPath(manifest.default_protocol).parts
            )
            protocol = load_protocol(protocol_path)
            protocol_identity = protocol.canonical_hash()
            protocol_files = (
                StudioBenchmarkAuthoringProtocolFileV1(
                    path=manifest.default_protocol,
                    document=load_mapping(protocol_path),
                ),
            )
        if protocol_identity != expected_protocol_identity and (
            expected_package_identity is not None
        ):
            raise StudioBenchmarkAuthoringDriftError(
                "benchmark.authoring.source_drift",
                "Benchmark Catalog Protocol no longer matches the selected entry",
            )
        resources: list[StudioBenchmarkAuthoringResourceV1] = []
        for resource in sorted(manifest.resources, key=lambda item: item.path):
            snapshot_path = snapshot_root / Path(
                *PurePosixPath(resource.path).parts
            )
            content_identity, digest, size = self._content_store.store_file(
                snapshot_path,
                max_bytes=STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
            )
            if digest != resource.sha256 or size != resource.size:
                raise StudioBenchmarkAuthoringDriftError(
                    "benchmark.authoring.resource_drift",
                    "Declared Benchmark resource metadata does not match its bytes",
                )
            resources.append(
                StudioBenchmarkAuthoringResourceV1(
                    id=resource.id,
                    kind=resource.kind.value,
                    path=resource.path,
                    media_type=resource.media_type,
                    sha256=digest,
                    size=size,
                    content_identity=content_identity,
                )
            )
        document = StudioBenchmarkAuthoringDocumentV1(
            manifest=StudioBenchmarkAuthoringManifestV1(document=raw_manifest),
            task_files=task_files,
            protocol_files=protocol_files,
            resources=tuple(resources),
        )
        source_fingerprint = canonical_hash(
            {
                "contract": "studio-benchmark-authoring-source-v1",
                "members": [
                    {
                        "path": item.path,
                        "sha256": item.sha256,
                        "size": item.size,
                    }
                    for item in sorted(
                        copied.values(),
                        key=lambda item: item.path,
                    )
                ],
            }
        )
        return PreparedStudioBenchmarkAuthoringDocument(
            document=document,
            package_identity=package_identity,
            package_content_identity=package.content_identity,
            source_fingerprint=source_fingerprint,
        )


__all__ = [
    "PreparedStudioBenchmarkAuthoringDocument",
    "StudioBenchmarkAuthoringPackageAdapter",
]
