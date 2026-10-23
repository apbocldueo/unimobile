"""Private frozen-closure reader and managed Package release storage."""

from __future__ import annotations

from contextlib import contextmanager
import hashlib
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import tempfile
from typing import BinaryIO, Iterator
import zipfile

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_freeze_models import (
    StudioBenchmarkFrozenMemberV1,
    StudioBenchmarkPackageRevisionDetailV1,
)
from .benchmark_authoring_protocols import StudioBenchmarkManagedContent
from .benchmark_authoring_release_models import (
    STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES,
    StudioBenchmarkPackageExportV1,
    validate_benchmark_package_export_id,
    validate_benchmark_package_publication_id,
)


_STREAM_BLOCK_BYTES = 1024 * 1024
_DIGEST = re.compile(r"^sha256:([a-f0-9]{64})$")


def default_studio_benchmark_release_root(database_path: str | Path) -> Path:
    """Derive the database-sibling managed Package release root.

    Args:
        database_path: Explicit Studio SQLite path.

    Raises:
        None.

    Returns:
        Private release root adjacent to the database file.
    """
    database = Path(database_path).expanduser()
    return database.parent / f"{database.name}.benchmark-release"


def _fsync_directory(path: Path) -> None:
    """Flush one directory entry boundary after atomic promotion.

    Args:
        path: Existing directory.

    Raises:
        OSError: Directory cannot be opened or synchronized.

    Returns:
        None.
    """
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _hash_regular_file(path: Path) -> tuple[int, str]:
    """Measure and hash one non-symlink regular file.

    Args:
        path: Candidate managed file.

    Raises:
        OSError: Candidate cannot be inspected or read.
        ValueError: Candidate is not a regular non-symlink file.

    Returns:
        Exact byte size and prefixed SHA-256 digest.
    """
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise ValueError("managed release member is not a regular file")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_STREAM_BLOCK_BYTES), b""):
            digest.update(block)
    return metadata.st_size, f"sha256:{digest.hexdigest()}"


class StudioBenchmarkFrozenClosureReader:
    """Stream only an owned immutable Package revision's verified members."""

    def __init__(self, content: StudioBenchmarkManagedContent) -> None:
        """Bind the reader to server-owned immutable authoring content.

        Args:
            content: Opaque managed-content boundary from authoring.

        Raises:
            None.

        Returns:
            None.
        """
        self._content = content

    @contextmanager
    def open_member(
        self,
        member: StudioBenchmarkFrozenMemberV1,
    ) -> Iterator[BinaryIO]:
        """Open one frozen member after identity, size, and digest checks.

        Args:
            member: Immutable revision-owned member descriptor.

        Raises:
            StudioBenchmarkAuthoringStorageError: Content is missing or corrupt.

        Returns:
            Context-managed readable binary stream positioned at zero.
        """
        stream = self._content.open_verified(
            member.content_identity,
            expected_sha256=member.sha256,
            expected_size=member.size,
        )
        try:
            yield stream
        finally:
            stream.close()

    def verify(self, detail: StudioBenchmarkPackageRevisionDetailV1) -> None:
        """Reverify every member in one complete deterministic frozen closure.

        Args:
            detail: Exact owned Package revision and attestation.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Aggregate bytes exceed bounds.
            StudioBenchmarkAuthoringStorageError: Any member is missing or corrupt.

        Returns:
            None.
        """
        observed = 0
        for member in detail.package_revision.members:
            with self.open_member(member) as stream:
                size = 0
                digest = hashlib.sha256()
                for block in iter(lambda: stream.read(_STREAM_BLOCK_BYTES), b""):
                    if not isinstance(block, bytes):
                        raise StudioBenchmarkAuthoringStorageError(
                            "benchmark.authoring.release_integrity",
                            "Frozen Benchmark content is not binary",
                        )
                    size += len(block)
                    observed += len(block)
                    if observed > STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES:
                        raise StudioBenchmarkAuthoringCapacityError(
                            "benchmark.authoring.release_too_large",
                            "Frozen Benchmark closure exceeds its release limit",
                        )
                    digest.update(block)
                if size != member.size or f"sha256:{digest.hexdigest()}" != member.sha256:
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.release_integrity",
                        "Frozen Benchmark content does not match its Package revision",
                    )


class LocalStudioBenchmarkPackageReleaseStore:
    """Atomic private managed Package trees and deterministic export archives."""

    def __init__(self, root: str | Path) -> None:
        """Create private managed release directories.

        Args:
            root: Explicit database-sibling server-owned root.

        Raises:
            StudioBenchmarkAuthoringStorageError: Directories cannot be created.

        Returns:
            None.
        """
        self._root = Path(root).expanduser()
        self._packages = self._root / "packages"
        self._exports = self._root / "exports"
        self._package_staging = self._root / "package-staging"
        self._export_staging = self._root / "export-staging"
        try:
            for path in (
                self._packages,
                self._exports,
                self._package_staging,
                self._export_staging,
            ):
                path.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.release_storage_unavailable",
                "Benchmark Package release storage is unavailable",
            ) from error

    @property
    def root(self) -> Path:
        """Return the private root for trusted composition and tests.

        Returns:
            Configured release root.
        """
        return self._root

    def package_path(self, locator: str) -> Path:
        """Resolve an opaque publication locator to its private Package root.

        Args:
            locator: Publication-ID-shaped private locator.

        Raises:
            StudioBenchmarkAuthoringValidationError: Locator is malformed.

        Returns:
            Private candidate root without asserting existence.
        """
        try:
            validate_benchmark_package_publication_id(locator)
        except ValueError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.publication_locator_invalid",
                "Benchmark publication storage identity is invalid",
            ) from error
        return self._packages / locator

    def _verify_package_tree(
        self,
        root: Path,
        detail: StudioBenchmarkPackageRevisionDetailV1,
    ) -> None:
        """Verify exact regular-file membership and frozen digests in a tree.

        Args:
            root: Private managed Package root.
            detail: Exact frozen Package authority.

        Raises:
            StudioBenchmarkAuthoringStorageError: Tree is absent, extra, or corrupt.

        Returns:
            None.
        """
        try:
            root_metadata = root.lstat()
            if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(
                root_metadata.st_mode
            ):
                raise ValueError("managed Package root is unsafe")
            observed: set[str] = set()
            for candidate in root.rglob("*"):
                relative = candidate.relative_to(root).as_posix()
                metadata = candidate.lstat()
                if stat.S_ISLNK(metadata.st_mode):
                    raise ValueError("managed Package tree contains a symlink")
                if stat.S_ISREG(metadata.st_mode):
                    observed.add(relative)
                elif not stat.S_ISDIR(metadata.st_mode):
                    raise ValueError("managed Package tree contains an unsafe entry")
            expected = {item.path for item in detail.package_revision.members}
            if observed != expected:
                raise ValueError("managed Package membership is not closed")
            for member in detail.package_revision.members:
                size, digest = _hash_regular_file(root / PurePosixPath(member.path))
                if size != member.size or digest != member.sha256:
                    raise ValueError("managed Package member integrity mismatch")
        except (OSError, ValueError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.publication_integrity",
                "Managed Benchmark Package is missing or corrupt",
            ) from error

    def materialize_package(
        self,
        locator: str,
        detail: StudioBenchmarkPackageRevisionDetailV1,
        reader: StudioBenchmarkFrozenClosureReader,
    ) -> Path:
        """Atomically materialize exactly one verified frozen member closure.

        Args:
            locator: Publication-ID-shaped private locator.
            detail: Exact immutable Package revision authority.
            reader: Server-owned frozen-content reader.

        Raises:
            StudioBenchmarkAuthoringStorageError: Content or storage fails closed.
            StudioBenchmarkAuthoringCapacityError: Closure exceeds bounds.

        Returns:
            Verified immutable managed Package root.
        """
        destination = self.package_path(locator)
        if destination.exists():
            self._verify_package_tree(destination, detail)
            return destination
        staging: Path | None = None
        try:
            staging = Path(
                tempfile.mkdtemp(prefix=".package-", dir=self._package_staging)
            )
            total = 0
            for member in detail.package_revision.members:
                relative = PurePosixPath(member.path)
                target = staging.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                digest = hashlib.sha256()
                size = 0
                descriptor = os.open(
                    target,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0),
                    0o600,
                )
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        descriptor = -1
                        with reader.open_member(member) as source:
                            for block in iter(
                                lambda: source.read(_STREAM_BLOCK_BYTES), b""
                            ):
                                size += len(block)
                                total += len(block)
                                if total > STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES:
                                    raise StudioBenchmarkAuthoringCapacityError(
                                        "benchmark.authoring.release_too_large",
                                        "Frozen Benchmark closure exceeds its release limit",
                                    )
                                digest.update(block)
                                output.write(block)
                        output.flush()
                        os.fsync(output.fileno())
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                if size != member.size or f"sha256:{digest.hexdigest()}" != member.sha256:
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.release_integrity",
                        "Frozen Benchmark content changed during materialization",
                    )
            self._verify_package_tree(staging, detail)
            os.replace(staging, destination)
            staging = None
            _fsync_directory(self._packages)
            self._verify_package_tree(destination, detail)
            return destination
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkAuthoringStorageError,
        ):
            raise
        except (OSError, TypeError, ValueError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.publication_storage_failed",
                "Managed Benchmark Package could not be finalized",
            ) from error
        finally:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)

    def verify_package(
        self,
        locator: str,
        detail: StudioBenchmarkPackageRevisionDetailV1,
    ) -> Path:
        """Verify and return one already finalized managed Package tree.

        Args:
            locator: Publication-ID-shaped private locator.
            detail: Exact frozen Package authority.

        Raises:
            StudioBenchmarkAuthoringValidationError: Locator is malformed.
            StudioBenchmarkAuthoringStorageError: Tree is absent or corrupt.

        Returns:
            Verified private managed Package root.
        """
        root = self.package_path(locator)
        self._verify_package_tree(root, detail)
        return root

    @staticmethod
    def export_filename(package_revision_id: str) -> str:
        """Derive one deterministic safe attachment basename.

        Args:
            package_revision_id: Exact immutable Package revision identity.

        Raises:
            ValueError: Package revision identity is malformed.

        Returns:
            Stable ASCII ZIP filename.
        """
        from .benchmark_authoring_freeze_models import (
            validate_benchmark_package_revision_id,
        )

        validate_benchmark_package_revision_id(package_revision_id)
        suffix = package_revision_id.rsplit("-", 1)[-1]
        return f"benchmark-package-{suffix}.zip"

    @staticmethod
    def _zip_info(member: StudioBenchmarkFrozenMemberV1) -> zipfile.ZipInfo:
        """Build fixed cross-process metadata for one stored ZIP entry.

        Args:
            member: Frozen logical member descriptor.

        Raises:
            None.

        Returns:
            Normalized ZIP entry metadata.
        """
        info = zipfile.ZipInfo(member.path, date_time=(1980, 1, 1, 0, 0, 0))
        info.compress_type = zipfile.ZIP_STORED
        info.create_system = 3
        info.external_attr = (stat.S_IFREG | 0o644) << 16
        info.internal_attr = 0
        info.extra = b""
        info.comment = b""
        return info

    @classmethod
    def _verify_archive(
        cls,
        path: Path,
        detail: StudioBenchmarkPackageRevisionDetailV1,
    ) -> tuple[int, str]:
        """Verify deterministic archive metadata, closure, bytes, size, and hash.

        Args:
            path: Candidate private ZIP file.
            detail: Exact frozen member authority.

        Raises:
            StudioBenchmarkAuthoringStorageError: Archive is unsafe or corrupt.
            StudioBenchmarkAuthoringCapacityError: Archive exceeds its bound.

        Returns:
            Exact archive byte size and prefixed SHA-256 digest.
        """
        try:
            metadata = path.lstat()
            if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
                raise ValueError("Package archive is not a regular file")
            if metadata.st_size > STUDIO_BENCHMARK_PACKAGE_EXPORT_MAX_BYTES:
                raise StudioBenchmarkAuthoringCapacityError(
                    "benchmark.authoring.export_too_large",
                    "Benchmark Package export exceeds its safe limit",
                )
            with zipfile.ZipFile(path, "r") as archive:
                if archive.comment != b"":
                    raise ValueError("archive comment is not normalized")
                infos = archive.infolist()
                expected = detail.package_revision.members
                if [item.filename for item in infos] != [item.path for item in expected]:
                    raise ValueError("archive membership or order differs")
                if len({item.filename for item in infos}) != len(infos):
                    raise ValueError("archive contains duplicate members")
                for info, member in zip(infos, expected, strict=True):
                    if (
                        info.is_dir()
                        or info.compress_type != zipfile.ZIP_STORED
                        or info.date_time != (1980, 1, 1, 0, 0, 0)
                        or info.create_system != 3
                        or (info.external_attr >> 16) != (stat.S_IFREG | 0o644)
                        or info.extra != b""
                        or info.comment != b""
                        or info.file_size != member.size
                    ):
                        raise ValueError("archive member metadata is not normalized")
                    digest = hashlib.sha256()
                    size = 0
                    with archive.open(info, "r") as stream:
                        for block in iter(
                            lambda: stream.read(_STREAM_BLOCK_BYTES), b""
                        ):
                            size += len(block)
                            digest.update(block)
                    if size != member.size or f"sha256:{digest.hexdigest()}" != member.sha256:
                        raise ValueError("archive member content differs")
            size, digest = _hash_regular_file(path)
            return size, digest
        except StudioBenchmarkAuthoringCapacityError:
            raise
        except (OSError, ValueError, zipfile.BadZipFile, RuntimeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.export_integrity",
                "Benchmark Package export is missing or corrupt",
            ) from error

    def create_export(
        self,
        locator: str,
        detail: StudioBenchmarkPackageRevisionDetailV1,
        reader: StudioBenchmarkFrozenClosureReader,
    ) -> tuple[int, str]:
        """Create and atomically promote one byte-deterministic ZIP archive.

        Args:
            locator: Export-ID-shaped private archive locator.
            detail: Exact immutable Package revision authority.
            reader: Server-owned frozen-content reader.

        Raises:
            StudioBenchmarkAuthoringStorageError: Content or archive fails closed.
            StudioBenchmarkAuthoringCapacityError: Archive exceeds its bound.

        Returns:
            Verified archive size and prefixed SHA-256 digest.
        """
        try:
            validate_benchmark_package_export_id(locator)
        except ValueError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.export_locator_invalid",
                "Benchmark Package export storage identity is invalid",
            ) from error
        destination = self._exports / f"{locator}.zip"
        if destination.exists():
            return self._verify_archive(destination, detail)
        descriptor: int | None = None
        staging: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".export-", suffix=".zip", dir=self._export_staging
            )
            os.close(descriptor)
            descriptor = None
            staging = Path(temporary_name)
            with zipfile.ZipFile(
                staging,
                "w",
                compression=zipfile.ZIP_STORED,
                allowZip64=False,
                strict_timestamps=True,
            ) as archive:
                archive.comment = b""
                for member in detail.package_revision.members:
                    info = self._zip_info(member)
                    with reader.open_member(member) as source:
                        with archive.open(info, "w", force_zip64=False) as target:
                            for block in iter(
                                lambda: source.read(_STREAM_BLOCK_BYTES), b""
                            ):
                                target.write(block)
            with staging.open("rb") as stream:
                os.fsync(stream.fileno())
            size, digest = self._verify_archive(staging, detail)
            os.replace(staging, destination)
            staging = None
            _fsync_directory(self._exports)
            final_size, final_digest = self._verify_archive(destination, detail)
            if (final_size, final_digest) != (size, digest):
                raise StudioBenchmarkAuthoringStorageError(
                    "benchmark.authoring.export_integrity",
                    "Benchmark Package export changed during promotion",
                )
            return final_size, final_digest
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkAuthoringStorageError,
        ):
            raise
        except (OSError, TypeError, ValueError, zipfile.BadZipFile) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.export_storage_failed",
                "Benchmark Package export could not be finalized",
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if staging is not None:
                try:
                    staging.unlink(missing_ok=True)
                except OSError:
                    pass

    def open_export(
        self,
        record: StudioBenchmarkPackageExportV1,
        detail: StudioBenchmarkPackageRevisionDetailV1,
    ) -> BinaryIO:
        """Open an exact private archive after full descriptor verification.

        Args:
            record: Durable public export descriptor.
            detail: Exact frozen Package authority.

        Raises:
            StudioBenchmarkAuthoringStorageError: Archive is absent or corrupt.

        Returns:
            Verified readable binary stream positioned at zero.
        """
        candidate = self._exports / f"{record.export_id}.zip"
        size, digest = self._verify_archive(candidate, detail)
        if size != record.size or digest != record.sha256:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.export_integrity",
                "Benchmark Package export does not match its durable descriptor",
            )
        descriptor: int | None = None
        try:
            descriptor = os.open(
                candidate, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            )
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != record.size:
                raise StudioBenchmarkAuthoringStorageError(
                    "benchmark.authoring.export_integrity",
                    "Benchmark Package export changed before download",
                )
            stream = os.fdopen(descriptor, "rb")
            descriptor = None
            return stream
        except StudioBenchmarkAuthoringStorageError:
            raise
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.export_integrity",
                "Benchmark Package export is unavailable",
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)


__all__ = [
    "LocalStudioBenchmarkPackageReleaseStore",
    "StudioBenchmarkFrozenClosureReader",
    "default_studio_benchmark_release_root",
]
