"""Managed local artifact storage for formal Studio Benchmark evidence."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import BinaryIO

from zhixing.benchmark.identity import canonical_hash
from zhixing.benchmark.reporting import verify_trajectory_bundle

from .benchmark_errors import (
    StudioBenchmarkIntegrityError,
    StudioBenchmarkNotFoundError,
    StudioBenchmarkStorageError,
)
from .benchmark_publication_models import (
    StudioBenchmarkArtifactAvailability,
    StudioBenchmarkArtifactDescriptorV1,
    StudioBenchmarkManagedArtifactRecordV1,
)
from .benchmark_publication_protocols import (
    StudioBenchmarkPublicationRepository,
)


_READABLE = {
    StudioBenchmarkArtifactAvailability.AVAILABLE,
    StudioBenchmarkArtifactAvailability.REDACTED,
    StudioBenchmarkArtifactAvailability.TRUNCATED,
}
_CONTENT_TYPES = {
    "application/json",
    "application/x-ndjson",
    "application/zip",
    "image/png",
    "application/xml",
    "text/plain",
}


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    """Hash a binary stream from its current position.

    Args:
        stream: Open readable binary stream.

    Raises:
        OSError: Stream reading fails.

    Returns:
        Prefixed digest and byte count.
    """
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


class LocalStudioBenchmarkManagedArtifactStore:
    """Immutable Experiment-scoped managed content with verified resolution."""

    def __init__(
        self,
        root: str | Path,
        repository: StudioBenchmarkPublicationRepository,
        *,
        maximum_file_bytes: int = 128 * 1024 * 1024,
        maximum_experiment_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        """Configure a server-owned managed artifact root.

        Args:
            root: Explicit managed storage root shared with Replay resolution.
            repository: Metadata and integrity-state persistence port.
            maximum_file_bytes: Maximum bytes in one managed artifact.
            maximum_experiment_bytes: Maximum bytes per Experiment.

        Raises:
            ValueError: Limits are not positive.
            OSError: Root cannot be created.

        Returns:
            None.
        """
        if maximum_file_bytes < 1 or maximum_experiment_bytes < 1:
            raise ValueError("managed artifact limits must be positive")
        self.root = Path(root).expanduser().resolve()
        self.repository = repository
        self.maximum_file_bytes = maximum_file_bytes
        self.maximum_experiment_bytes = maximum_experiment_bytes
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / ".staging").mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _artifact_id(
        *,
        experiment_id: str,
        task_run_id: str | None,
        reference: str,
        kind: str,
        sha256: str,
    ) -> str:
        """Derive a stable opaque identity from immutable member facts.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Optional TaskRun scope.
            reference: Private causal member reference.
            kind: Stable artifact kind.
            sha256: Verified content digest.

        Returns:
            Stable opaque artifact identity.
        """
        suffix = canonical_hash(
            {
                "contract": "studio-benchmark-managed-artifact-v1",
                "experimentId": experiment_id,
                "taskRunId": task_run_id,
                "reference": reference,
                "kind": kind,
                "sha256": sha256,
            }
        ).removeprefix("sha256:")[:32]
        return f"artifact-{suffix}"

    def import_file(
        self,
        *,
        experiment_id: str,
        task_run_id: str | None,
        reference: str,
        kind: str,
        content_type: str,
        source: Path,
        trusted_root: Path,
        expected_sha256: str,
        hidden: bool = False,
        causal_identity: str = "",
    ) -> StudioBenchmarkManagedArtifactRecordV1:
        """Verify and atomically retain one declared private source member.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Optional owning TaskRun.
            reference: Declared private causal reference.
            kind: Stable artifact kind.
            content_type: Allowlisted media type.
            source: Exact declared regular source file.
            trusted_root: Expected private source root.
            expected_sha256: Preparation-manifest digest.
            hidden: Whether content must never become readable.
            causal_identity: Optional safe cross-surface identity.

        Raises:
            StudioBenchmarkIntegrityError: Scope, type, size, or hash fails.
            StudioBenchmarkStorageError: Immutable copy fails.

        Returns:
            Managed descriptor paired with a root-relative storage reference.
        """
        if content_type not in _CONTENT_TYPES:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.type_unsupported",
                "Benchmark artifact content type is unsupported",
            )
        source = Path(source)
        root = Path(trusted_root).resolve()
        try:
            if source.is_symlink() or not source.is_file():
                raise OSError("source is not a regular file")
            resolved_source = source.resolve(strict=True)
            if resolved_source != root and root not in resolved_source.parents:
                raise OSError("source escapes trusted root")
            source_flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                source_flags |= os.O_NOFOLLOW
            descriptor = os.open(resolved_source, source_flags)
            with os.fdopen(descriptor, "rb") as stream:
                source_stat = os.fstat(stream.fileno())
                if not stat.S_ISREG(source_stat.st_mode):
                    raise OSError("source is not regular")
                actual_sha256, size = _hash_stream(stream)
            if size > self.maximum_file_bytes:
                raise ValueError("artifact exceeds file limit")
            existing_size = sum(
                record.descriptor.size
                for record in self.repository.list_artifacts(experiment_id)
            )
            if existing_size + size > self.maximum_experiment_bytes:
                raise ValueError("artifact exceeds Experiment limit")
            if actual_sha256 != expected_sha256:
                raise ValueError("artifact digest changed after preparation")
        except (OSError, ValueError) as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.source_invalid",
                "Benchmark artifact source failed verification",
            ) from error
        artifact_id = self._artifact_id(
            experiment_id=experiment_id,
            task_run_id=task_run_id,
            reference=reference,
            kind=kind,
            sha256=actual_sha256,
        )
        storage_ref = (
            f"benchmark/{experiment_id}/artifacts/{artifact_id}"
        )
        availability = (
            StudioBenchmarkArtifactAvailability.HIDDEN
            if hidden
            else StudioBenchmarkArtifactAvailability.AVAILABLE
        )
        public_descriptor = StudioBenchmarkArtifactDescriptorV1(
            artifact_id=artifact_id,
            experiment_id=experiment_id,
            task_run_id=task_run_id,
            kind=kind,
            availability=availability,
            content_type="" if hidden else content_type,
            size=0 if hidden else size,
            sha256=None if hidden else actual_sha256,
            causal_identity=causal_identity,
            hidden=hidden,
        )
        record = StudioBenchmarkManagedArtifactRecordV1(
            descriptor=public_descriptor,
            storage_ref=storage_ref,
        )
        if hidden:
            return record
        final = self.storage_path(record)
        final.parent.mkdir(parents=True, exist_ok=True)
        if final.exists():
            try:
                with final.open("rb") as stream:
                    digest, existing_bytes = _hash_stream(stream)
                if digest != actual_sha256 or existing_bytes != size:
                    raise OSError("existing immutable member differs")
                return record
            except OSError as error:
                raise StudioBenchmarkIntegrityError(
                    "benchmark.artifact.immutable_conflict",
                    "Benchmark managed artifact identity has different content",
                ) from error
        staging_parent = self.root / ".staging"
        temporary_name = ""
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{artifact_id}.",
                dir=staging_parent,
            )
            source_flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                source_flags |= os.O_NOFOLLOW
            source_descriptor = os.open(resolved_source, source_flags)
            with os.fdopen(descriptor, "wb") as target, os.fdopen(
                source_descriptor,
                "rb",
            ) as source_stream:
                shutil.copyfileobj(source_stream, target, length=1024 * 1024)
                target.flush()
                os.fsync(target.fileno())
            temporary = Path(temporary_name)
            with temporary.open("rb") as stream:
                copied_hash, copied_size = _hash_stream(stream)
            if copied_hash != actual_sha256 or copied_size != size:
                raise OSError("managed copy failed integrity verification")
            os.replace(temporary, final)
            temporary_name = ""
        except OSError as error:
            raise StudioBenchmarkStorageError(
                "benchmark.artifact.storage_failed",
                "Benchmark managed artifact could not be retained",
            ) from error
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
        return record

    def storage_path(
        self,
        record: StudioBenchmarkManagedArtifactRecordV1,
    ) -> Path:
        """Resolve an internal safe record beneath the managed root.

        Args:
            record: Validated managed record.

        Raises:
            StudioBenchmarkIntegrityError: Reference escapes its root.

        Returns:
            Internal managed path.
        """
        candidate = self.root.joinpath(*record.storage_ref.split("/"))
        resolved = candidate.resolve(strict=False)
        if resolved != self.root and self.root not in resolved.parents:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.storage_ref_invalid",
                "Benchmark managed artifact reference is invalid",
            )
        return candidate

    def open_artifact(
        self,
        experiment_id: str,
        artifact_id: str,
    ) -> tuple[StudioBenchmarkArtifactDescriptorV1, BinaryIO]:
        """Open one scoped artifact only after size and hash verification.

        Args:
            experiment_id: Owning Experiment identity.
            artifact_id: Opaque artifact identity.

        Raises:
            StudioBenchmarkNotFoundError: Content is absent or not readable.
            StudioBenchmarkIntegrityError: Managed content is corrupt.

        Returns:
            Public descriptor and verified seekable binary stream.
        """
        record = self.repository.get_artifact(experiment_id, artifact_id)
        descriptor = record.descriptor
        if descriptor.hidden or descriptor.availability not in _READABLE:
            raise StudioBenchmarkNotFoundError(
                "benchmark.artifact.not_readable",
                "Benchmark artifact is not readable",
            )
        path = self.storage_path(record)
        try:
            resolved = path.resolve(strict=True)
            if resolved != self.root and self.root not in resolved.parents:
                raise OSError("managed member escapes root")
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            file_descriptor = os.open(path, flags)
            stream = os.fdopen(file_descriptor, "rb")
            opened_stat = os.fstat(stream.fileno())
            if not stat.S_ISREG(opened_stat.st_mode):
                raise OSError("managed member is not regular")
            actual_sha256, size = _hash_stream(stream)
            if (
                actual_sha256 != descriptor.sha256
                or size != descriptor.size
                or size > self.maximum_file_bytes
            ):
                stream.close()
                self.repository.update_artifact_availability(
                    experiment_id,
                    artifact_id,
                    StudioBenchmarkArtifactAvailability.CORRUPT,
                )
                raise StudioBenchmarkIntegrityError(
                    "benchmark.artifact.corrupt",
                    "Benchmark artifact failed integrity verification",
                )
            stream.seek(0)
            return descriptor, stream
        except FileNotFoundError as error:
            self.repository.update_artifact_availability(
                experiment_id,
                artifact_id,
                StudioBenchmarkArtifactAvailability.MISSING,
            )
            raise StudioBenchmarkNotFoundError(
                "benchmark.artifact.missing",
                "Benchmark artifact content is missing",
            ) from error
        except StudioBenchmarkIntegrityError:
            raise
        except OSError as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.artifact.open_failed",
                "Benchmark artifact could not be verified",
            ) from error


class CoreStudioBenchmarkBundleVerifier:
    """Verify an exported formal Benchmark trajectory bundle."""

    def verify(self, source: str | Path) -> bool:
        """Verify safe members and declared hashes in a bundle.

        Args:
            source: Explicit bundle file.

        Raises:
            ValueError: Bundle paths or manifest are unsafe.
            OSError: Bundle cannot be read.

        Returns:
            True only when every formal member matches its digest.
        """
        return verify_trajectory_bundle(Path(source))


__all__ = [
    "CoreStudioBenchmarkBundleVerifier",
    "LocalStudioBenchmarkManagedArtifactStore",
]
