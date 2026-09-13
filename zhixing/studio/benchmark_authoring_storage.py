"""Immutable local managed content for Studio Benchmark authoring."""

from __future__ import annotations

import hashlib
from io import BytesIO
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import BinaryIO

from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringNotFoundError,
    StudioBenchmarkAuthoringStorageError,
    StudioBenchmarkAuthoringValidationError,
)


_CONTENT_ID = re.compile(r"^benchmark-content-([a-f0-9]{64})$")
_STREAM_BLOCK_BYTES = 1024 * 1024


def _regular_file_sha256(path: Path) -> str:
    """Hash one existing managed regular file without path projection.

    Args:
        path: Existing managed object.

    Raises:
        OSError: File cannot be read.

    Returns:
        Lowercase SHA-256 hex digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_STREAM_BLOCK_BYTES), b""):
            digest.update(block)
    return digest.hexdigest()


def default_studio_benchmark_authoring_root(database_path: str | Path) -> Path:
    """Derive the database-sibling server-owned authoring root.

    Args:
        database_path: Explicit Studio SQLite path.

    Raises:
        None.

    Returns:
        Local authoring root next to the database file.
    """
    database = Path(database_path).expanduser()
    return database.parent / f"{database.name}.benchmark-authoring"


def _fsync_directory(path: Path) -> None:
    """Best-effort fsync one directory after atomic metadata changes.

    Args:
        path: Directory whose entry metadata should be flushed.

    Raises:
        OSError: Opening or syncing a supported directory fails.

    Returns:
        None.
    """
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class LocalStudioBenchmarkManagedContent:
    """Digest-addressed immutable files beneath one private local root."""

    def __init__(self, root: str | Path) -> None:
        """Create the managed directory structure without reading source data.

        Args:
            root: Explicit server-owned content root.

        Raises:
            StudioBenchmarkAuthoringStorageError: Directories cannot be created.

        Returns:
            None.
        """
        self._root = Path(root).expanduser()
        self._objects = self._root / "objects"
        self._staging = self._root / "staging"
        try:
            self._objects.mkdir(parents=True, exist_ok=True, mode=0o700)
            self._staging.mkdir(parents=True, exist_ok=True, mode=0o700)
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring content storage is unavailable",
            ) from error

    @property
    def root(self) -> Path:
        """Return the private root for internal composition and tests.

        Returns:
            Configured local root.
        """
        return self._root

    @property
    def staging_root(self) -> Path:
        """Return the private staging root for trusted internal adapters.

        Returns:
            Configured staging directory.
        """
        return self._staging

    def store_stream(
        self,
        stream: BinaryIO,
        *,
        max_bytes: int,
    ) -> tuple[str, str, int]:
        """Stream bounded bytes into one atomically finalized object.

        Args:
            stream: Open binary source stream.
            max_bytes: Inclusive maximum accepted byte count.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Source exceeds the limit.
            StudioBenchmarkAuthoringValidationError: Limit is invalid.
            StudioBenchmarkAuthoringStorageError: Storage cannot finalize bytes.

        Returns:
            Opaque content identity, prefixed SHA-256 digest, and byte size.
        """
        if max_bytes < 0:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.limit_invalid",
                "Benchmark authoring content limit is invalid",
            )
        descriptor: int | None = None
        temporary_path: Path | None = None
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=".content-",
                dir=self._staging,
            )
            temporary_path = Path(temporary_name)
            digest = hashlib.sha256()
            size = 0
            with os.fdopen(descriptor, "wb") as target:
                descriptor = None
                while True:
                    block = stream.read(_STREAM_BLOCK_BYTES)
                    if not block:
                        break
                    if not isinstance(block, bytes):
                        raise TypeError("managed content source must be binary")
                    size += len(block)
                    if size > max_bytes:
                        raise StudioBenchmarkAuthoringCapacityError(
                            "benchmark.authoring.content_too_large",
                            "Benchmark authoring content exceeds its safe limit",
                        )
                    digest.update(block)
                    target.write(block)
                target.flush()
                os.fsync(target.fileno())
            hex_digest = digest.hexdigest()
            content_identity = f"benchmark-content-{hex_digest}"
            object_directory = self._objects / hex_digest[:2]
            object_directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            destination = object_directory / hex_digest
            if destination.exists():
                existing = destination.lstat()
                if (
                    stat.S_ISLNK(existing.st_mode)
                    or not stat.S_ISREG(existing.st_mode)
                    or existing.st_size != size
                    or _regular_file_sha256(destination) != hex_digest
                ):
                    raise StudioBenchmarkAuthoringStorageError(
                        "benchmark.authoring.storage_failed",
                        "Managed Benchmark content identity is inconsistent",
                    )
                temporary_path.unlink()
            else:
                os.replace(temporary_path, destination)
                temporary_path = None
                _fsync_directory(object_directory)
            return content_identity, f"sha256:{hex_digest}", size
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkAuthoringStorageError,
        ):
            raise
        except (OSError, TypeError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Benchmark authoring content could not be stored",
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary_path is not None:
                try:
                    temporary_path.unlink(missing_ok=True)
                except OSError:
                    pass

    def store_bytes(
        self,
        payload: bytes,
        *,
        max_bytes: int,
    ) -> tuple[str, str, int]:
        """Store one bounded immutable in-memory definition member.

        Args:
            payload: Canonical binary payload.
            max_bytes: Inclusive maximum accepted byte count.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is not bytes.
            StudioBenchmarkAuthoringCapacityError: Payload exceeds the limit.
            StudioBenchmarkAuthoringStorageError: Storage cannot finalize bytes.

        Returns:
            Opaque content identity, prefixed SHA-256 digest, and byte size.
        """
        if not isinstance(payload, bytes):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.content_invalid",
                "Benchmark authoring definition content must be bytes",
            )
        return self.store_stream(BytesIO(payload), max_bytes=max_bytes)

    def store_file(
        self,
        source: Path,
        *,
        max_bytes: int,
    ) -> tuple[str, str, int]:
        """Store one bounded regular non-symlink source file.

        Args:
            source: Trusted adapter-resolved source candidate.
            max_bytes: Inclusive maximum accepted byte count.

        Raises:
            StudioBenchmarkAuthoringValidationError: Source is unsafe.
            StudioBenchmarkAuthoringCapacityError: Source exceeds the limit.
            StudioBenchmarkAuthoringStorageError: Source or storage cannot be read.

        Returns:
            Opaque content identity, prefixed digest, and byte size.
        """
        try:
            metadata = source.lstat()
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.source_unreadable",
                "Declared Benchmark source member cannot be read",
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.source_unsafe",
                "Declared Benchmark source member must be a regular file",
            )
        if metadata.st_size > max_bytes:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.content_too_large",
                "Benchmark authoring content exceeds its safe limit",
            )
        try:
            with source.open("rb") as stream:
                result = self.store_stream(stream, max_bytes=max_bytes)
            after = source.lstat()
        except (
            StudioBenchmarkAuthoringCapacityError,
            StudioBenchmarkAuthoringStorageError,
            StudioBenchmarkAuthoringValidationError,
        ):
            raise
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.source_unreadable",
                "Declared Benchmark source member cannot be read",
            ) from error
        if (
            stat.S_ISLNK(after.st_mode)
            or not stat.S_ISREG(after.st_mode)
            or (metadata.st_dev, metadata.st_ino, metadata.st_size)
            != (after.st_dev, after.st_ino, after.st_size)
        ):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.source_drift",
                "Declared Benchmark source changed during import",
            )
        return result

    def content_path(self, content_identity: str) -> Path:
        """Resolve one existing opaque content identity for internal use.

        Args:
            content_identity: Digest-derived opaque identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: Identity is malformed.
            StudioBenchmarkAuthoringNotFoundError: Managed object is absent.
            StudioBenchmarkAuthoringStorageError: Stored object is unsafe.

        Returns:
            Existing immutable managed object path.
        """
        match = _CONTENT_ID.fullmatch(content_identity)
        if match is None:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.content_identity_invalid",
                "Managed Benchmark content identity is invalid",
            )
        digest = match.group(1)
        candidate = self._objects / digest[:2] / digest
        try:
            metadata = candidate.lstat()
        except FileNotFoundError as error:
            raise StudioBenchmarkAuthoringNotFoundError(
                "benchmark.authoring.content_not_found",
                "Managed Benchmark content was not found",
            ) from error
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Managed Benchmark content cannot be inspected",
            ) from error
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Managed Benchmark content is not a regular file",
            )
        try:
            if _regular_file_sha256(candidate) != digest:
                raise StudioBenchmarkAuthoringStorageError(
                    "benchmark.authoring.storage_failed",
                    "Managed Benchmark content identity is inconsistent",
                )
        except StudioBenchmarkAuthoringStorageError:
            raise
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Managed Benchmark content cannot be read",
            ) from error
        return candidate

    def open_verified(
        self,
        content_identity: str,
        *,
        expected_sha256: str,
        expected_size: int,
    ) -> BinaryIO:
        """Open one immutable object after closing every integrity boundary.

        Args:
            content_identity: Revision-owned opaque content identity.
            expected_sha256: Revision-declared prefixed SHA-256 digest.
            expected_size: Revision-declared exact byte size.

        Raises:
            StudioBenchmarkAuthoringValidationError: Expected facts are malformed.
            StudioBenchmarkAuthoringStorageError: Object is absent, unsafe, or
                inconsistent with its identity or owning revision.

        Returns:
            Seeked readable binary stream whose descriptor was verified.
        """
        match = _CONTENT_ID.fullmatch(content_identity)
        if (
            match is None
            or not isinstance(expected_size, int)
            or isinstance(expected_size, bool)
            or expected_size < 0
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", expected_sha256)
        ):
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.content_facts_invalid",
                "Managed Benchmark content facts are invalid",
            )
        digest = match.group(1)
        if expected_sha256 != f"sha256:{digest}":
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.content_integrity",
                "Managed Benchmark content does not match its revision",
            )
        candidate = self._objects / digest[:2] / digest
        descriptor: int | None = None
        stream: BinaryIO | None = None
        try:
            descriptor = os.open(
                candidate,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
            )
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_size != expected_size
            ):
                raise StudioBenchmarkAuthoringStorageError(
                    "benchmark.authoring.content_integrity",
                    "Managed Benchmark content does not match its revision",
                )
            stream = os.fdopen(descriptor, "rb")
            descriptor = None
            observed = hashlib.sha256()
            for block in iter(lambda: stream.read(_STREAM_BLOCK_BYTES), b""):
                observed.update(block)
            if observed.hexdigest() != digest:
                raise StudioBenchmarkAuthoringStorageError(
                    "benchmark.authoring.content_integrity",
                    "Managed Benchmark content does not match its revision",
                )
            stream.seek(0)
            result = stream
            stream = None
            return result
        except StudioBenchmarkAuthoringStorageError:
            raise
        except (FileNotFoundError, NotADirectoryError) as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.content_unavailable",
                "Managed Benchmark content is unavailable",
            ) from error
        except OSError as error:
            raise StudioBenchmarkAuthoringStorageError(
                "benchmark.authoring.storage_failed",
                "Managed Benchmark content cannot be read",
            ) from error
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if stream is not None:
                stream.close()


__all__ = [
    "LocalStudioBenchmarkManagedContent",
    "default_studio_benchmark_authoring_root",
]
