"""Managed local artifact storage for live Studio Runs."""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import uuid
from pathlib import Path, PurePosixPath
from typing import BinaryIO, cast

from zhixing.components import RunEvent

from .run_errors import (
    StudioRunArtifactNotFoundError,
    StudioRunEvidenceError,
)
from .run_models import (
    RunEvidenceAvailability,
    StudioRunArtifactDescriptorV1,
    StudioRunArtifactRecordV1,
    StudioRunEventDraftV1,
    runtime_event_draft,
)
from .run_protocols import StudioRunArtifactRepository
from .run_safety import redact_text


_CONTENT_TYPES = {
    "application/json",
    "application/xml",
    "image/jpeg",
    "image/png",
    "text/plain",
    "text/xml",
}


def default_studio_run_artifact_directory(database_path: str | Path) -> Path:
    """Resolve the managed live-Run artifact root beside Studio data.

    Args:
        database_path (str | Path): Workspace-isolated Studio database.

    Raises:
        OSError: Path resolution fails.

    Returns:
        Path: Managed artifact root.
    """
    database = Path(database_path).expanduser()
    return database.parent / "artifacts" / "live"


def _hash_bytes(content: bytes) -> str:
    """Return one prefixed SHA-256 digest.

    Args:
        content (bytes): Artifact content.

    Raises:
        None.

    Returns:
        str: Prefixed digest.
    """
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _hash_stream(stream: BinaryIO) -> tuple[str, int]:
    """Hash a stream from its start and return digest plus size.

    Args:
        stream (BinaryIO): Readable binary stream.

    Raises:
        OSError: Stream read fails.

    Returns:
        tuple[str, int]: Prefixed digest and byte count.
    """
    stream.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := stream.read(1024 * 1024):
        digest.update(chunk)
        size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


class LocalStudioRunArtifactStore:
    """Run-scoped local content store with opaque registered identities."""

    def __init__(
        self,
        root: str | Path,
        repository: StudioRunArtifactRepository,
        *,
        soft_warning_bytes: int = 20 * 1024**3,
        minimum_free_bytes: int = 256 * 1024**2,
        max_artifact_bytes: int = 32 * 1024**2,
        max_run_bytes: int = 2 * 1024**3,
    ) -> None:
        """Configure managed storage and explicit resource limits.

        Args:
            root (str | Path): Managed artifact root.
            repository (StudioRunArtifactRepository): Descriptor index.
            soft_warning_bytes (int): Existing-content warning threshold.
            minimum_free_bytes (int): Required free-space reserve.
            max_artifact_bytes (int): Maximum stored content size.
            max_run_bytes (int): Maximum registered bytes per Run.

        Raises:
            ValueError: A resource limit is non-positive.
            OSError: Root cannot be created.

        Returns:
            None.
        """
        if min(
            soft_warning_bytes,
            minimum_free_bytes,
            max_artifact_bytes,
            max_run_bytes,
        ) <= 0:
            raise ValueError("Run artifact limits must be positive")
        self.root = Path(root).expanduser().resolve()
        self.repository = repository
        self.soft_warning_bytes = int(soft_warning_bytes)
        self.minimum_free_bytes = int(minimum_free_bytes)
        self.max_artifact_bytes = int(max_artifact_bytes)
        self.max_run_bytes = int(max_run_bytes)
        self.objects_root = self.root / "objects"
        self.runtime_root = self.root / "runtime"
        self.objects_root.mkdir(parents=True, exist_ok=True)
        self.runtime_root.mkdir(parents=True, exist_ok=True)

    def _managed_size(self) -> int:
        """Measure current managed regular-file bytes without following links.

        Args:
            None.

        Raises:
            OSError: Directory traversal fails.

        Returns:
            int: Aggregate regular-file bytes.
        """
        total = 0
        for directory, names, files in os.walk(
            self.root,
            topdown=True,
            followlinks=False,
        ):
            base = Path(directory)
            names[:] = [name for name in names if not (base / name).is_symlink()]
            for name in files:
                path = base / name
                if not path.is_symlink() and path.is_file():
                    total += path.stat().st_size
        return total

    def preflight(self) -> tuple[str, ...]:
        """Verify safe writable storage and return non-blocking warnings.

        Args:
            None.

        Raises:
            StudioRunEvidenceError: Root is unsafe, unwritable, or too full.

        Returns:
            tuple[str, ...]: Stable warning codes.
        """
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            probe_fd, probe_name = tempfile.mkstemp(
                prefix=".write-probe-",
                dir=self.root,
            )
            os.write(probe_fd, b"ok")
            os.close(probe_fd)
            Path(probe_name).unlink()
            free = shutil.disk_usage(self.root).free
            managed = self._managed_size()
        except OSError as error:
            raise StudioRunEvidenceError(
                "studio.run.evidence_preflight_failed",
                "Studio Run evidence storage is unavailable",
            ) from error
        if free < self.minimum_free_bytes:
            raise StudioRunEvidenceError(
                "studio.run.evidence_capacity_insufficient",
                "Studio Run evidence free-space reserve is insufficient",
            )
        return (
            ("studio.run.evidence_soft_limit_warning",)
            if managed >= self.soft_warning_bytes
            else ()
        )

    def _run_size(self, run_id: str) -> int:
        """Return total registered readable bytes for one Run.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunError: Artifact listing fails.

        Returns:
            int: Registered byte count.
        """
        return sum(
            record.descriptor.size
            for record in self.repository.list_artifacts(run_id)
        )

    def write_bytes(
        self,
        run_id: str,
        *,
        kind: str,
        content_type: str,
        content: bytes,
        hidden: bool = False,
        provenance: str = "native_studio_run",
        causal_identity: str = "",
        original_size: int | None = None,
    ) -> StudioRunArtifactDescriptorV1:
        """Persist and register one bounded artifact atomically.

        Args:
            run_id (str): Owning Run identity.
            kind (str): Stable artifact kind.
            content_type (str): Allowlisted media type.
            content (bytes): Already-safe content bytes.
            hidden (bool): Whether ordinary reads are forbidden.
            provenance (str): Capture source label.
            causal_identity (str): Activation/observation/action identity.
            original_size (int | None): Size before an explicit truncation.

        Raises:
            StudioRunEvidenceError: Type, capacity, or atomic write fails.
            StudioRunError: Descriptor registration fails.

        Returns:
            StudioRunArtifactDescriptorV1: Registered public descriptor.
        """
        if content_type not in _CONTENT_TYPES:
            raise StudioRunEvidenceError(
                "studio.run.artifact_content_type",
                "Studio Run artifact content type is not allowed",
            )
        if len(content) > self.max_artifact_bytes:
            raise StudioRunEvidenceError(
                "studio.run.artifact_too_large",
                "Studio Run artifact exceeds its configured size limit",
            )
        if self._run_size(run_id) + len(content) > self.max_run_bytes:
            raise StudioRunEvidenceError(
                "studio.run.evidence_run_limit",
                "Studio Run evidence exceeds its configured total limit",
            )
        artifact_id = f"artifact-{uuid.uuid4().hex}"
        run_root = self.objects_root / run_id / "artifacts"
        target = run_root / artifact_id
        temporary = run_root / f".{artifact_id}.tmp"
        try:
            run_root.mkdir(parents=True, exist_ok=True)
            with temporary.open("xb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        except OSError as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise StudioRunEvidenceError(
                "studio.run.artifact_write_failed",
                "Studio Run artifact could not be persisted",
            ) from error
        descriptor = StudioRunArtifactDescriptorV1(
            artifact_id=artifact_id,
            kind=str(kind)[:256],
            availability=(
                RunEvidenceAvailability.HIDDEN
                if hidden
                else RunEvidenceAvailability.AVAILABLE
            ),
            content_type=content_type,
            size=len(content),
            original_size=original_size,
            sha256=_hash_bytes(content),
            provenance=str(provenance)[:256],
            hidden=hidden,
            causal_identity=str(causal_identity)[:256],
        )
        record = StudioRunArtifactRecordV1(
            run_id=run_id,
            descriptor=descriptor,
            storage_ref=target.relative_to(self.root).as_posix(),
        )
        try:
            self.repository.put_artifact(record)
        except Exception:
            try:
                target.unlink()
            except OSError:
                pass
            raise
        return descriptor

    def _existing_runtime_artifact(
        self,
        run_id: str,
        *,
        kind: str,
        causal_identity: str,
    ) -> StudioRunArtifactDescriptorV1 | None:
        """Find a previously registered exact Runtime reference.

        Args:
            run_id (str): Owning Run identity.
            kind (str): Stable artifact kind.
            causal_identity (str): Runtime relative reference.

        Raises:
            StudioRunError: Artifact listing fails.

        Returns:
            StudioRunArtifactDescriptorV1 | None: Existing descriptor.
        """
        for record in self.repository.list_artifacts(run_id):
            descriptor = record.descriptor
            if (
                descriptor.kind == kind
                and descriptor.causal_identity == causal_identity
            ):
                return descriptor
        return None

    def write_text(
        self,
        run_id: str,
        *,
        kind: str,
        text: str,
        hidden: bool = False,
        provenance: str = "native_studio_run",
        causal_identity: str = "",
    ) -> StudioRunArtifactDescriptorV1:
        """Redact, bound, persist, and register one UTF-8 text artifact.

        Args:
            run_id (str): Owning Run identity.
            kind (str): Stable artifact kind.
            text (str): Candidate sensitive text.
            hidden (bool): Whether ordinary reads are forbidden.
            provenance (str): Capture source label.
            causal_identity (str): Activation or model call identity.

        Raises:
            StudioRunEvidenceError: Content cannot be stored safely.
            StudioRunError: Descriptor registration fails.

        Returns:
            StudioRunArtifactDescriptorV1: Registered descriptor.
        """
        original = str(text)
        original_bytes = original.encode("utf-8")
        safe, redacted, truncated = redact_text(
            original,
            max_length=self.max_artifact_bytes,
        )
        encoded = safe.encode("utf-8")
        if len(encoded) > self.max_artifact_bytes:
            marker = b"\n[truncated]"
            budget = max(0, self.max_artifact_bytes - len(marker))
            encoded = encoded[:budget].decode("utf-8", errors="ignore").encode(
                "utf-8"
            ) + marker
            truncated = True
        descriptor = self.write_bytes(
            run_id,
            kind=kind,
            content_type="text/plain",
            content=encoded,
            hidden=hidden,
            provenance=provenance,
            causal_identity=causal_identity,
            original_size=(len(original_bytes) if truncated else None),
        )
        availability = (
            RunEvidenceAvailability.TRUNCATED
            if truncated
            else (
                RunEvidenceAvailability.REDACTED
                if redacted and not hidden
                else descriptor.availability
            )
        )
        if availability is descriptor.availability:
            return descriptor
        return self.repository.update_artifact_availability(
            run_id,
            descriptor.artifact_id,
            availability,
        ).descriptor

    def register_runtime_reference(
        self,
        run_id: str,
        reference: str,
        *,
        kind: str,
        causal_identity: str = "",
    ) -> StudioRunArtifactDescriptorV1:
        """Copy one exact Runtime artifact reference into opaque managed storage.

        Args:
            run_id (str): Owning Run identity.
            reference (str): Runtime-root-relative artifact reference.
            kind (str): Stable artifact kind.
            causal_identity (str): Observation/action identity.

        Raises:
            StudioRunEvidenceError: Reference escapes, is missing, or too large.

        Returns:
            StudioRunArtifactDescriptorV1: Registered opaque descriptor.
        """
        existing = self._existing_runtime_artifact(
            run_id,
            kind=kind,
            causal_identity=reference,
        )
        if existing is not None:
            return existing
        pure = PurePosixPath(reference)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise StudioRunEvidenceError(
                "studio.run.runtime_artifact_ref_invalid",
                "Runtime artifact reference is unsafe",
            )
        candidate = self.runtime_root.joinpath(*pure.parts)
        resolved = candidate.resolve()
        expected_root = (self.runtime_root / run_id).resolve()
        if (
            candidate.is_symlink()
            or not candidate.is_file()
            or expected_root not in resolved.parents
        ):
            raise StudioRunEvidenceError(
                "studio.run.runtime_artifact_missing",
                "Runtime artifact is unavailable",
            )
        size = resolved.stat().st_size
        if size > self.max_artifact_bytes:
            raise StudioRunEvidenceError(
                "studio.run.artifact_too_large",
                "Runtime artifact exceeds its configured size limit",
            )
        suffix = resolved.suffix.lower()
        content_type = {
            ".json": "application/json",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".txt": "text/plain",
            ".xml": "application/xml",
        }.get(suffix)
        if content_type is None:
            raise StudioRunEvidenceError(
                "studio.run.artifact_content_type",
                "Runtime artifact content type is not allowed",
            )
        return self.write_bytes(
            run_id,
            kind=kind,
            content_type=content_type,
            content=resolved.read_bytes(),
            causal_identity=causal_identity,
        )

    def register_runtime_namespace(
        self,
        run_id: str,
    ) -> tuple[StudioRunArtifactDescriptorV1, ...]:
        """Register every verified regular file in one exact Runtime namespace.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunEvidenceError: Namespace or a member is unsafe.
            StudioRunError: Descriptor persistence fails.

        Returns:
            tuple[StudioRunArtifactDescriptorV1, ...]: Stable descriptors.
        """
        namespace = (self.runtime_root / run_id).resolve()
        if not namespace.is_dir() or namespace.is_symlink():
            raise StudioRunEvidenceError(
                "studio.run.runtime_artifact_missing",
                "Runtime artifact namespace is unavailable",
            )
        descriptors: list[StudioRunArtifactDescriptorV1] = []
        for path in sorted(namespace.rglob("*")):
            if path.is_symlink():
                raise StudioRunEvidenceError(
                    "studio.run.runtime_artifact_ref_invalid",
                    "Runtime artifact namespace contains a symlink",
                )
            if not path.is_file() or path.name.endswith(".tmp"):
                continue
            reference = path.relative_to(self.runtime_root).as_posix()
            lowered = path.name.lower()
            if "observation" in lowered and path.suffix.lower() in {
                ".png",
                ".jpg",
                ".jpeg",
            }:
                kind = "screenshot"
            elif "observation" in lowered and path.suffix.lower() == ".xml":
                kind = "ui_tree"
            elif "action" in lowered:
                kind = "action"
            elif path.name == "manifest.json":
                kind = "run_manifest"
            else:
                kind = "runtime_artifact"
            descriptors.append(
                self.register_runtime_reference(
                    run_id,
                    reference,
                    kind=kind,
                    causal_identity=reference,
                )
            )
        return tuple(descriptors)

    def path_for_record(self, record: StudioRunArtifactRecordV1) -> Path:
        """Resolve an internal storage reference without allowing root escape.

        Args:
            record (StudioRunArtifactRecordV1): Internal artifact record.

        Raises:
            StudioRunEvidenceError: Reference is unsafe or escapes the root.

        Returns:
            Path: Resolved managed content path.
        """
        pure = PurePosixPath(record.storage_ref)
        if pure.is_absolute() or ".." in pure.parts:
            raise StudioRunEvidenceError(
                "studio.run.artifact_ref_invalid",
                "Stored Run artifact reference is unsafe",
            )
        path = self.root.joinpath(*pure.parts)
        resolved = path.resolve()
        if self.root != resolved and self.root not in resolved.parents:
            raise StudioRunEvidenceError(
                "studio.run.artifact_ref_invalid",
                "Stored Run artifact reference escapes managed storage",
            )
        return resolved

    def open_artifact(
        self,
        run_id: str,
        artifact_id: str,
    ) -> tuple[StudioRunArtifactDescriptorV1, BinaryIO]:
        """Open and verify one non-hidden run-scoped artifact.

        Args:
            run_id (str): Owning Run identity.
            artifact_id (str): Opaque artifact identity.

        Raises:
            StudioRunArtifactNotFoundError: Pair is absent or hidden.
            StudioRunEvidenceError: Content is missing or corrupt.
            OSError: Content cannot be opened.

        Returns:
            tuple[StudioRunArtifactDescriptorV1, BinaryIO]: Metadata and stream.
        """
        record = self.repository.get_artifact(run_id, artifact_id)
        if record.descriptor.hidden or record.descriptor.availability is (
            RunEvidenceAvailability.HIDDEN
        ):
            raise StudioRunArtifactNotFoundError(
                "studio.run.artifact_not_found",
                "Studio Run artifact was not found",
            )
        path = self.path_for_record(record)
        if path.is_symlink() or not path.is_file():
            self.repository.update_artifact_availability(
                run_id,
                artifact_id,
                RunEvidenceAvailability.MISSING,
            )
            raise StudioRunEvidenceError(
                "studio.run.artifact_missing",
                "Studio Run artifact content is unavailable",
            )
        stream = path.open("rb")
        digest, size = _hash_stream(stream)
        if (
            digest != record.descriptor.sha256
            or size != record.descriptor.size
        ):
            stream.close()
            self.repository.update_artifact_availability(
                run_id,
                artifact_id,
                RunEvidenceAvailability.CORRUPT,
            )
            raise StudioRunEvidenceError(
                "studio.run.artifact_corrupt",
                "Studio Run artifact failed integrity verification",
            )
        stream.seek(0)
        return record.descriptor, stream


class RuntimeArtifactEventAdapter:
    """Register artifact references before their Runtime event is journaled."""

    _KINDS = {
        "screenshot_artifact": "screenshot",
        "ui_artifact": "ui_tree",
        "artifact": "action",
    }

    def __init__(self, store: LocalStudioRunArtifactStore) -> None:
        """Bind the managed artifact store.

        Args:
            store (LocalStudioRunArtifactStore): Live Run content boundary.

        Raises:
            None.

        Returns:
            None.
        """
        self.store = store

    @classmethod
    def _references(cls, value: object) -> tuple[tuple[str, str], ...]:
        """Collect explicit runtime artifact fields from safe event JSON.

        Args:
            value (object): Safe event payload.

        Raises:
            None.

        Returns:
            tuple[tuple[str, str], ...]: Kind and relative reference pairs.
        """
        found: list[tuple[str, str]] = []

        def visit(candidate: object) -> None:
            """Traverse only JSON mappings and lists.

            Args:
                candidate (object): Nested safe JSON value.

            Raises:
                None.

            Returns:
                None.
            """
            if isinstance(candidate, dict):
                for key, item in candidate.items():
                    kind = cls._KINDS.get(str(key))
                    if kind is not None and isinstance(item, str) and item:
                        found.append((kind, item))
                    else:
                        visit(item)
            elif isinstance(candidate, list):
                for item in candidate:
                    visit(item)

        visit(value)
        return tuple(dict.fromkeys(found))

    @classmethod
    def _opaque_payload(
        cls,
        value: object,
        references: dict[str, str],
    ) -> object:
        """Replace Runtime references with opaque registered identities.

        Args:
            value (object): Sanitized Runtime event value.
            references (dict[str, str]): Relative reference to artifact ID.

        Raises:
            None.

        Returns:
            object: JSON value without Runtime namespace references.
        """
        if isinstance(value, dict):
            return {
                key: (
                    references.get(item, item)
                    if str(key) in cls._KINDS and isinstance(item, str)
                    else cls._opaque_payload(item, references)
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [cls._opaque_payload(item, references) for item in value]
        return value

    def build(self, event: RunEvent) -> StudioRunEventDraftV1:
        """Build one event draft enriched with opaque artifact identities.

        Args:
            event (RunEvent): Canonical Runtime event.

        Raises:
            StudioRunEvidenceError: Referenced content is unsafe or missing.
            StudioRunError: Descriptor registration fails.

        Returns:
            StudioRunEventDraftV1: Enriched deterministic journal draft.
        """
        draft = runtime_event_draft(event)
        references: dict[str, str] = {}
        for kind, reference in self._references(draft.payload):
            descriptor = self.store.register_runtime_reference(
                event.run_id,
                reference,
                kind=kind,
                causal_identity=reference,
            )
            references[reference] = descriptor.artifact_id
        if not references:
            return draft
        return draft.model_copy(
            update={
                "payload": {
                    **cast(
                        dict[str, object],
                        self._opaque_payload(draft.payload, references),
                    ),
                    "artifactIds": tuple(references.values()),
                }
            }
        )


__all__ = [
    "LocalStudioRunArtifactStore",
    "RuntimeArtifactEventAdapter",
    "default_studio_run_artifact_directory",
]
