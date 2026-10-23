"""Strict DTOs for managed Studio Benchmark publication evidence."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Literal

from pydantic import Field, StrictBool, field_validator, model_validator

from .models import StudioModel


_EXPERIMENT_ID = re.compile(r"^experiment-[a-f0-9]{32}$")
_TASK_RUN_ID = re.compile(r"^task-run-[a-f0-9]{32}$")
_ARTIFACT_ID = re.compile(r"^artifact-[a-f0-9]{32}$")
_REPLAY_ID = re.compile(r"^benchmark-replay-[a-f0-9]{32}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_RELATIVE = re.compile(r"^[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*$")
StudioBenchmarkComponentAvailability = Literal[
    "pending",
    "not_produced",
    "available",
    "failed",
]


class StudioBenchmarkArtifactAvailability(str, Enum):
    """Availability vocabulary for one managed Benchmark artifact."""

    PENDING = "pending"
    NOT_PRODUCED = "not_produced"
    AVAILABLE = "available"
    EXCLUDED = "excluded"
    HIDDEN = "hidden"
    MISSING = "missing"
    CORRUPT = "corrupt"
    FAILED = "failed"
    REDACTED = "redacted"
    TRUNCATED = "truncated"


class StudioBenchmarkPublicationDiagnosticV1(StudioModel):
    """One bounded safe publication failure or integrity fact."""

    code: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=500)
    component: str = Field(default="", max_length=128)
    retryable: StrictBool = False

    @field_validator("code", "message", "component")
    @classmethod
    def _single_line_safe_text(cls, value: str) -> str:
        """Reject host-path-shaped or multiline diagnostic text.

        Args:
            value: Candidate public diagnostic text.

        Raises:
            ValueError: Text contains a host path.

        Returns:
            Normalized one-line text.
        """
        normalized = str(value).strip().replace("\n", " ")
        if normalized.startswith(("/", "\\\\")) or re.match(
            r"^[A-Za-z]:[\\/]", normalized
        ):
            raise ValueError("publication diagnostic must not expose host paths")
        return normalized


class StudioBenchmarkArtifactDescriptorV1(StudioModel):
    """Public Experiment/TaskRun-scoped managed artifact metadata."""

    schema_version: Literal[1] = 1
    artifact_id: str
    experiment_id: str
    task_run_id: str | None = None
    kind: str = Field(min_length=1, max_length=160)
    availability: StudioBenchmarkArtifactAvailability
    content_type: str = Field(default="", max_length=160)
    size: int = Field(default=0, ge=0)
    sha256: str | None = None
    provenance: str = Field(default="native_benchmark", max_length=160)
    causal_identity: str = Field(default="", max_length=256)
    hidden: StrictBool = False

    @field_validator("artifact_id")
    @classmethod
    def _artifact_identity(cls, value: str) -> str:
        """Validate one opaque artifact identity.

        Args:
            value: Candidate artifact identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _ARTIFACT_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark artifact identity")
        return value

    @field_validator("experiment_id")
    @classmethod
    def _experiment_identity(cls, value: str) -> str:
        """Validate the owning Experiment identity.

        Args:
            value: Candidate Experiment identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark Experiment identity")
        return value

    @field_validator("task_run_id")
    @classmethod
    def _task_run_identity(cls, value: str | None) -> str | None:
        """Validate an optional owning TaskRun identity.

        Args:
            value: Candidate TaskRun identity or absence.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity or ``None``.
        """
        if value is not None and _TASK_RUN_ID.fullmatch(value) is None:
            raise ValueError("invalid Benchmark TaskRun identity")
        return value

    @field_validator("sha256")
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        """Validate optional artifact integrity metadata.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest or ``None``.
        """
        if value is not None and _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid Benchmark artifact digest")
        return value

    @model_validator(mode="after")
    def _availability_shape(self) -> "StudioBenchmarkArtifactDescriptorV1":
        """Keep readable and hidden artifact metadata consistent.

        Raises:
            ValueError: Availability contradicts integrity metadata.

        Returns:
            Validated descriptor.
        """
        readable = {
            StudioBenchmarkArtifactAvailability.AVAILABLE,
            StudioBenchmarkArtifactAvailability.REDACTED,
            StudioBenchmarkArtifactAvailability.TRUNCATED,
        }
        if self.availability in readable and (
            not self.content_type or self.sha256 is None
        ):
            raise ValueError(
                "readable Benchmark artifact requires type and digest"
            )
        if self.hidden and self.availability is not (
            StudioBenchmarkArtifactAvailability.HIDDEN
        ):
            raise ValueError("hidden artifact must use hidden availability")
        if (
            self.availability
            is StudioBenchmarkArtifactAvailability.HIDDEN
        ) != self.hidden:
            raise ValueError(
                "hidden availability and hidden metadata must agree"
            )
        if self.hidden and (
            self.content_type or self.size != 0 or self.sha256 is not None
        ):
            raise ValueError("hidden artifact cannot expose readable metadata")
        return self


class StudioBenchmarkManagedArtifactRecordV1(StudioModel):
    """Internal descriptor paired with a safe managed relative reference."""

    descriptor: StudioBenchmarkArtifactDescriptorV1
    storage_ref: str = Field(min_length=1, max_length=1024)

    @field_validator("storage_ref")
    @classmethod
    def _safe_relative_reference(cls, value: str) -> str:
        """Reject absolute, traversing, and platform-specific storage refs.

        Args:
            value: Candidate managed-root-relative POSIX reference.

        Raises:
            ValueError: Reference is unsafe.

        Returns:
            Validated relative reference.
        """
        if (
            _SAFE_RELATIVE.fullmatch(value) is None
            or value.startswith(("/", "\\"))
            or ".." in value.split("/")
        ):
            raise ValueError("managed Benchmark storage reference is unsafe")
        return value


class StudioBenchmarkArtifactMetadataPageV1(StudioModel):
    """Internal metadata-only page without managed storage references."""

    schema_version: Literal[1] = 1
    experiment_id: str
    items: tuple[StudioBenchmarkArtifactDescriptorV1, ...] = Field(
        max_length=100
    )
    hidden_count: int = Field(ge=0)
    next_cursor: str | None = None

    @model_validator(mode="after")
    def _metadata_page_shape(
        self,
    ) -> "StudioBenchmarkArtifactMetadataPageV1":
        """Require scoped visible descriptors in stable identity order.

        Raises:
            ValueError: Scope, visibility, or ordering is invalid.

        Returns:
            Validated metadata-only page.
        """
        artifact_ids = tuple(item.artifact_id for item in self.items)
        if artifact_ids != tuple(sorted(artifact_ids)):
            raise ValueError("artifact metadata page order is unstable")
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("artifact metadata page contains duplicates")
        if any(
            item.experiment_id != self.experiment_id or item.hidden
            for item in self.items
        ):
            raise ValueError(
                "artifact metadata page contains hidden or cross-scope items"
            )
        return self


class StudioBenchmarkArtifactLinksV1(StudioModel):
    """Optional same-service content capability for one visible artifact."""

    content: str | None = Field(
        default=None,
        exclude_if=lambda value: value is None,
    )


class StudioBenchmarkArtifactInventoryItemV1(StudioModel):
    """Public visible managed artifact metadata with an exact content link."""

    schema_version: Literal[1] = 1
    descriptor: StudioBenchmarkArtifactDescriptorV1
    links: StudioBenchmarkArtifactLinksV1

    @model_validator(mode="after")
    def _inventory_item_shape(
        self,
    ) -> "StudioBenchmarkArtifactInventoryItemV1":
        """Keep visibility and readable content capability consistent.

        Raises:
            ValueError: A hidden item is exposed or link disagrees with state.

        Returns:
            Validated inventory item.
        """
        if self.descriptor.hidden:
            raise ValueError("hidden artifact cannot be listed")
        readable = self.descriptor.availability in {
            StudioBenchmarkArtifactAvailability.AVAILABLE,
            StudioBenchmarkArtifactAvailability.REDACTED,
            StudioBenchmarkArtifactAvailability.TRUNCATED,
        }
        if readable != (self.links.content is not None):
            raise ValueError(
                "artifact content link disagrees with availability"
            )
        return self

    @classmethod
    def from_descriptor(
        cls,
        descriptor: StudioBenchmarkArtifactDescriptorV1,
    ) -> "StudioBenchmarkArtifactInventoryItemV1":
        """Project one visible descriptor with an exact scoped content link.

        Args:
            descriptor: Committed visible managed artifact descriptor.

        Raises:
            ValueError: Descriptor is hidden or violates readable invariants.

        Returns:
            Public inventory item.
        """
        if descriptor.hidden:
            raise ValueError("hidden artifact cannot be projected")
        base = (
            f"/studio/benchmark-experiments/{descriptor.experiment_id}"
        )
        if descriptor.task_run_id is None:
            content = f"{base}/artifacts/{descriptor.artifact_id}"
        else:
            content = (
                f"{base}/task-runs/{descriptor.task_run_id}/artifacts/"
                f"{descriptor.artifact_id}"
            )
        readable = descriptor.availability in {
            StudioBenchmarkArtifactAvailability.AVAILABLE,
            StudioBenchmarkArtifactAvailability.REDACTED,
            StudioBenchmarkArtifactAvailability.TRUNCATED,
        }
        return cls(
            descriptor=descriptor,
            links=StudioBenchmarkArtifactLinksV1(
                content=content if readable else None
            ),
        )


class StudioBenchmarkArtifactInventoryPageV1(StudioModel):
    """Public bounded Experiment-scoped visible artifact inventory."""

    schema_version: Literal[1] = 1
    experiment_id: str
    items: tuple[StudioBenchmarkArtifactInventoryItemV1, ...] = Field(
        max_length=100
    )
    hidden_count: int = Field(ge=0)
    next_cursor: str | None = None

    @model_validator(mode="after")
    def _inventory_page_shape(
        self,
    ) -> "StudioBenchmarkArtifactInventoryPageV1":
        """Require stable scoped public inventory items.

        Raises:
            ValueError: Scope or ordering is inconsistent.

        Returns:
            Validated public inventory page.
        """
        descriptors = tuple(item.descriptor for item in self.items)
        if any(
            item.experiment_id != self.experiment_id
            for item in descriptors
        ):
            raise ValueError("artifact inventory contains cross-scope item")
        artifact_ids = tuple(item.artifact_id for item in descriptors)
        if artifact_ids != tuple(sorted(artifact_ids)):
            raise ValueError("artifact inventory order is unstable")
        return self


class StudioBenchmarkPreparedMemberV1(StudioModel):
    """One verified private formal-publication staging member."""

    reference: str = Field(min_length=1, max_length=1024)
    kind: str = Field(min_length=1, max_length=160)
    content_type: str = Field(min_length=1, max_length=160)
    size: int = Field(ge=0)
    sha256: str
    task_run_id: str | None = None
    hidden: StrictBool = False

    @field_validator("reference")
    @classmethod
    def _safe_member_reference(cls, value: str) -> str:
        """Validate one staging-root-relative POSIX member.

        Args:
            value: Candidate member reference.

        Raises:
            ValueError: Reference is unsafe.

        Returns:
            Validated reference.
        """
        if (
            _SAFE_RELATIVE.fullmatch(value) is None
            or value.startswith(("/", "\\"))
            or ".." in value.split("/")
        ):
            raise ValueError("prepared publication member is unsafe")
        return value

    @field_validator("sha256")
    @classmethod
    def _member_digest(cls, value: str) -> str:
        """Validate a prepared member digest.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid prepared publication digest")
        return value


class StudioBenchmarkPreparedPublicationV1(StudioModel):
    """Durable private manifest prepared from the complete Core suite result."""

    schema_version: Literal[1] = 1
    experiment_id: str
    task_run_id: str
    preparation_fingerprint: str
    members: tuple[StudioBenchmarkPreparedMemberV1, ...] = Field(
        min_length=1,
        max_length=2000,
    )
    report_reference: str
    bundle_reference: str
    prepared_at: int = Field(ge=0)

    @field_validator("experiment_id")
    @classmethod
    def _prepared_experiment_identity(cls, value: str) -> str:
        """Validate the prepared Experiment identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid prepared Experiment identity")
        return value

    @field_validator("task_run_id")
    @classmethod
    def _prepared_task_identity(cls, value: str) -> str:
        """Validate the prepared public TaskRun identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is invalid.

        Returns:
            Validated identity.
        """
        if _TASK_RUN_ID.fullmatch(value) is None:
            raise ValueError("invalid prepared TaskRun identity")
        return value

    @field_validator("preparation_fingerprint")
    @classmethod
    def _prepared_fingerprint(cls, value: str) -> str:
        """Validate the preparation fingerprint.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid preparation fingerprint")
        return value

    @model_validator(mode="after")
    def _declared_references(
        self,
    ) -> "StudioBenchmarkPreparedPublicationV1":
        """Require unique members and declared report/bundle references.

        Raises:
            ValueError: Member identities repeat or typed references are absent.

        Returns:
            Validated preparation manifest.
        """
        references = [member.reference for member in self.members]
        if len(references) != len(set(references)):
            raise ValueError("prepared publication members must be unique")
        if (
            self.report_reference not in references
            or self.bundle_reference not in references
        ):
            raise ValueError(
                "prepared report and bundle references must be declared"
            )
        return self


class StudioBenchmarkPublicationRecordV1(StudioModel):
    """Durable query projection for one Experiment publication attempt."""

    schema_version: Literal[1] = 1
    experiment_id: str
    task_run_id: str
    publication_fingerprint: str
    preparation_fingerprint: str
    preparation_availability: StudioBenchmarkComponentAvailability
    report_availability: StudioBenchmarkComponentAvailability
    trajectory_availability: StudioBenchmarkComponentAvailability
    bundle_availability: StudioBenchmarkComponentAvailability
    replay_availability: StudioBenchmarkComponentAvailability
    report_artifact_id: str | None = None
    bundle_artifact_id: str | None = None
    replay_id: str | None = None
    artifact_ids: tuple[str, ...] = Field(default_factory=tuple, max_length=2000)
    diagnostics: tuple[StudioBenchmarkPublicationDiagnosticV1, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    journal_high_water_mark: int = Field(ge=0)
    published_at: int = Field(ge=0)

    @field_validator("experiment_id")
    @classmethod
    def _publication_experiment_identity(cls, value: str) -> str:
        """Validate the publication Experiment identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _EXPERIMENT_ID.fullmatch(value) is None:
            raise ValueError("invalid publication Experiment identity")
        return value

    @field_validator("task_run_id")
    @classmethod
    def _publication_task_identity(cls, value: str) -> str:
        """Validate the publication TaskRun identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity.
        """
        if _TASK_RUN_ID.fullmatch(value) is None:
            raise ValueError("invalid publication TaskRun identity")
        return value

    @field_validator("report_artifact_id", "bundle_artifact_id")
    @classmethod
    def _publication_artifact_identity(
        cls,
        value: str | None,
    ) -> str | None:
        """Validate optional typed artifact identities.

        Args:
            value: Candidate identity or absence.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity or ``None``.
        """
        if value is not None and _ARTIFACT_ID.fullmatch(value) is None:
            raise ValueError("invalid publication artifact identity")
        return value

    @field_validator("artifact_ids")
    @classmethod
    def _publication_artifact_inventory(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Validate a unique stable artifact inventory.

        Args:
            value: Candidate artifact identities.

        Raises:
            ValueError: Identity syntax, ordering, or uniqueness is invalid.

        Returns:
            Validated stable identity tuple.
        """
        if any(_ARTIFACT_ID.fullmatch(item) is None for item in value):
            raise ValueError("invalid publication artifact inventory")
        if tuple(sorted(value)) != value or len(value) != len(set(value)):
            raise ValueError(
                "publication artifact inventory must be sorted and unique"
            )
        return value

    @field_validator(
        "publication_fingerprint",
        "preparation_fingerprint",
    )
    @classmethod
    def _publication_digest(cls, value: str) -> str:
        """Validate immutable publication fingerprints.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("invalid Benchmark publication fingerprint")
        return value

    @field_validator("replay_id")
    @classmethod
    def _replay_identity(cls, value: str | None) -> str | None:
        """Validate an optional native Benchmark Replay identity.

        Args:
            value: Candidate identity or absence.

        Raises:
            ValueError: Identity syntax is invalid.

        Returns:
            Validated identity or ``None``.
        """
        if value is not None and _REPLAY_ID.fullmatch(value) is None:
            raise ValueError("invalid native Benchmark Replay identity")
        return value

    @model_validator(mode="after")
    def _publication_shape(self) -> "StudioBenchmarkPublicationRecordV1":
        """Keep typed identities consistent with component availability.

        Raises:
            ValueError: Availability and identity facts disagree.

        Returns:
            Validated publication record.
        """
        if (self.report_availability == "available") != (
            self.report_artifact_id is not None
        ):
            raise ValueError("available report requires its artifact identity")
        if (self.bundle_availability == "available") != (
            self.bundle_artifact_id is not None
        ):
            raise ValueError("available bundle requires its artifact identity")
        if (self.replay_availability == "available") != (
            self.replay_id is not None
        ):
            raise ValueError("available Replay requires its explicit identity")
        typed = {
            item
            for item in (
                self.report_artifact_id,
                self.bundle_artifact_id,
            )
            if item is not None
        }
        if not typed.issubset(set(self.artifact_ids)):
            raise ValueError(
                "typed publication artifacts must occur in the inventory"
            )
        return self


def canonical_publication_fingerprint(
    *,
    experiment_id: str,
    task_run_id: str,
    result_fingerprint: str,
    preparation_fingerprint: str,
    journal_high_water_mark: int,
    artifact_digests: tuple[str, ...],
) -> str:
    """Hash immutable publication inputs for deterministic retry identity.

    Args:
        experiment_id: Owning Experiment identity.
        task_run_id: Planned public TaskRun identity.
        result_fingerprint: Immutable bounded TaskResult fingerprint.
        preparation_fingerprint: Formal Core output fingerprint.
        journal_high_water_mark: Last committed source journal sequence.
        artifact_digests: Sorted managed member digest facts.

    Raises:
        TypeError: Inputs are not JSON compatible.
        ValueError: Inputs contain non-finite JSON.

    Returns:
        Prefixed SHA-256 publication fingerprint.
    """
    payload = {
        "contract": "studio-benchmark-publication-v1",
        "experimentId": experiment_id,
        "taskRunId": task_run_id,
        "resultFingerprint": result_fingerprint,
        "preparationFingerprint": preparation_fingerprint,
        "journalHighWaterMark": journal_high_water_mark,
        "artifactDigests": list(sorted(artifact_digests)),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def benchmark_replay_id(publication_fingerprint: str) -> str:
    """Derive the stable opaque native Benchmark Replay identity.

    Args:
        publication_fingerprint: Valid immutable publication fingerprint.

    Raises:
        ValueError: Fingerprint syntax is invalid.

    Returns:
        Stable opaque Replay identity.
    """
    if _DIGEST.fullmatch(publication_fingerprint) is None:
        raise ValueError("invalid Benchmark publication fingerprint")
    return (
        "benchmark-replay-"
        + publication_fingerprint.removeprefix("sha256:")[:32]
    )


__all__ = [
    "StudioBenchmarkArtifactAvailability",
    "StudioBenchmarkArtifactDescriptorV1",
    "StudioBenchmarkArtifactInventoryItemV1",
    "StudioBenchmarkArtifactInventoryPageV1",
    "StudioBenchmarkArtifactLinksV1",
    "StudioBenchmarkArtifactMetadataPageV1",
    "StudioBenchmarkComponentAvailability",
    "StudioBenchmarkManagedArtifactRecordV1",
    "StudioBenchmarkPreparedMemberV1",
    "StudioBenchmarkPreparedPublicationV1",
    "StudioBenchmarkPublicationDiagnosticV1",
    "StudioBenchmarkPublicationRecordV1",
    "benchmark_replay_id",
    "canonical_publication_fingerprint",
]
