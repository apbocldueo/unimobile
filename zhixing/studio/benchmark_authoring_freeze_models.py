"""Strict contracts for validated Studio Benchmark Package freezes."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from zhixing.benchmark.identity import canonical_hash

from .benchmark_authoring_analysis_models import (
    STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS,
    StudioBenchmarkAuthoringBudgetV1,
    StudioBenchmarkAuthoringDiagnosticV1,
    StudioBenchmarkAuthoringOutputLayoutV1,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS,
    STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS,
    STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES,
    validate_benchmark_authoring_media_type,
    validate_benchmark_authoring_revision_id,
    validate_benchmark_draft_id,
)
from .models import StudioModel


STUDIO_BENCHMARK_FREEZE_VALIDATION_CONTRACT = (
    "studio-benchmark-freeze-validation-v1"
)
STUDIO_BENCHMARK_FREEZE_MAX_SPLITS = 64
STUDIO_BENCHMARK_FREEZE_MAX_WARNINGS = 100
STUDIO_BENCHMARK_FREEZE_MAX_UNVERIFIED_CHECKS = 100
STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES = 10_000

_ATTESTATION_ID = re.compile(r"^benchmark-validation-attestation-[a-f0-9]{32}$")
_PACKAGE_REVISION_ID = re.compile(r"^benchmark-package-revision-[a-f0-9]{32}$")
_CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SPLIT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_CONTENT_ID = re.compile(r"^benchmark-content-[a-f0-9]{64}$")
_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s\"'(])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\s\"']+)"
)


def validate_benchmark_validation_attestation_id(value: str) -> str:
    """Validate one opaque successful validation-attestation identity.

    Args:
        value: Candidate public identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _ATTESTATION_ID.fullmatch(value) is None:
        raise ValueError("invalid Benchmark validation attestation identity")
    return value


def validate_benchmark_package_revision_id(value: str) -> str:
    """Validate one opaque immutable Package-revision identity.

    Args:
        value: Candidate public identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _PACKAGE_REVISION_ID.fullmatch(value) is None:
        raise ValueError("invalid Benchmark Package revision identity")
    return value


def _digest(value: str) -> str:
    """Validate one canonical SHA-256 identity.

    Args:
        value: Candidate prefixed digest.

    Raises:
        ValueError: Digest is malformed.

    Returns:
        Validated digest.
    """
    if _DIGEST.fullmatch(value) is None:
        raise ValueError("canonical identity must be a SHA-256 digest")
    return value


def _member_path(value: str) -> str:
    """Validate one normalized bounded Package-relative member path.

    Args:
        value: Candidate logical path.

    Raises:
        ValueError: Path is unsafe or non-canonical.

    Returns:
        Validated logical path.
    """
    if not value or len(value) > 512 or "\x00" in value or "\\" in value:
        raise ValueError("frozen member path is invalid")
    logical = PurePosixPath(value)
    if (
        logical.is_absolute()
        or "." in logical.parts
        or ".." in logical.parts
        or logical.as_posix() != value
    ):
        raise ValueError("frozen member path must be normalized and relative")
    return value


def _safe_public_text(value: str, *, limit: int) -> str:
    """Reject private capabilities in one bounded public text fact.

    Args:
        value: Candidate reader-facing fact.
        limit: Inclusive character bound.

    Raises:
        ValueError: Text is blank, oversized, multiline, or capability-bearing.

    Returns:
        Validated text.
    """
    if (
        not value
        or len(value) > limit
        or "\r" in value
        or "\n" in value
        or _ABSOLUTE_PATH.search(value) is not None
        or _CONTENT_ID.search(value) is not None
    ):
        raise ValueError("public freeze text is unsafe or outside its bound")
    return value


def benchmark_frozen_closure_identity(
    members: tuple["StudioBenchmarkFrozenMemberV1", ...],
) -> str:
    """Compute the presentation-neutral identity of a frozen member closure.

    Args:
        members: Complete deterministic member sequence.

    Raises:
        TypeError: A member cannot be serialized.

    Returns:
        Canonical SHA-256 identity excluding storage-order ordinals.
    """
    return canonical_hash(
        [
            item.model_dump(mode="json", by_alias=True, exclude={"ordinal"})
            for item in members
        ]
    )


class StudioBenchmarkFreezeModel(StudioModel):
    """Strict immutable base for every validated-freeze wire contract."""


class StudioBenchmarkFreezeRequestV1(StudioBenchmarkFreezeModel):
    """Idempotent command for freezing one exact current authoring revision."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    client_request_id: str
    revision_id: str

    @field_validator("client_request_id")
    @classmethod
    def _request_id(cls, value: str) -> str:
        """Validate one bounded client command identity.

        Args:
            value: Candidate request identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _CLIENT_REQUEST_ID.fullmatch(value) is None:
            raise ValueError("invalid client request identity")
        return value

    @field_validator("revision_id")
    @classmethod
    def _revision_id(cls, value: str) -> str:
        """Validate the exact authoring revision identity.

        Args:
            value: Candidate revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @property
    def fingerprint(self) -> str:
        """Return the command fingerprint including validation semantics.

        Returns:
            Canonical request fingerprint independent of authoring identity.
        """
        return canonical_hash(
            {
                **self.model_dump(mode="json", by_alias=True),
                "validationContractVersion": (
                    STUDIO_BENCHMARK_FREEZE_VALIDATION_CONTRACT
                ),
            }
        )


class StudioBenchmarkFreezeSplitV1(StudioBenchmarkFreezeModel):
    """Complete definition-only validation facts for one declared split."""

    split: str
    benchmark_plan_identity: str
    experiment_protocol_identity: str
    task_count: StrictInt = Field(
        ge=0,
        le=STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS,
    )
    schedule_entry_count: StrictInt = Field(
        ge=0,
        le=STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES,
    )
    budget: StudioBenchmarkAuthoringBudgetV1
    fairness_warnings: tuple[str, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_FREEZE_MAX_WARNINGS,
    )
    output_layout: StudioBenchmarkAuthoringOutputLayoutV1
    unverified_checks: tuple[str, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_FREEZE_MAX_UNVERIFIED_CHECKS,
    )

    @field_validator("split")
    @classmethod
    def _split(cls, value: str) -> str:
        """Validate one manifest-declared split identity.

        Args:
            value: Candidate split name.

        Raises:
            ValueError: Split name is malformed.

        Returns:
            Validated split name.
        """
        if _SPLIT.fullmatch(value) is None:
            raise ValueError("invalid Benchmark split identity")
        return value

    @field_validator("benchmark_plan_identity", "experiment_protocol_identity")
    @classmethod
    def _identities(cls, value: str) -> str:
        """Validate a Plan or Protocol canonical identity.

        Args:
            value: Candidate canonical digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        return _digest(value)

    @field_validator("fairness_warnings", "unverified_checks")
    @classmethod
    def _safe_facts(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require unique sorted safe warning and unverified facts.

        Args:
            value: Candidate ordered public facts.

        Raises:
            ValueError: Facts are duplicated, unsorted, or unsafe.

        Returns:
            Validated facts.
        """
        if value != tuple(sorted(set(value))):
            raise ValueError("freeze facts must be unique and sorted")
        return tuple(_safe_public_text(item, limit=500) for item in value)


class StudioBenchmarkValidationSafetyV1(StudioBenchmarkFreezeModel):
    """Explicit evidence limits for a successful validated freeze."""

    complete_declared_splits: StrictBool = True
    definition_only: StrictBool = True
    execution_evidence: StrictBool = False
    real_device_evidence: StrictBool = False
    model_evidence: StrictBool = False
    package_plugin_evidence: StrictBool = False
    publication_evidence: StrictBool = False
    contract_test_required: StrictBool = False

    @model_validator(mode="after")
    def _fixed_evidence_boundary(self) -> "StudioBenchmarkValidationSafetyV1":
        """Require the exact definition-only, non-execution safety facts.

        Raises:
            ValueError: Any caller tries to broaden successful evidence.

        Returns:
            Validated fixed safety facts.
        """
        if not self.complete_declared_splits or not self.definition_only:
            raise ValueError("successful freeze must cover all declared splits")
        if any(
            (
                self.execution_evidence,
                self.real_device_evidence,
                self.model_evidence,
                self.package_plugin_evidence,
                self.publication_evidence,
                self.contract_test_required,
            )
        ):
            raise ValueError("validated freeze cannot claim runtime evidence")
        return self


class StudioBenchmarkValidationAttestationV1(StudioBenchmarkFreezeModel):
    """Immutable successful validation authority for one authored revision."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    attestation_id: str
    draft_id: str
    authoring_revision_id: str
    document_fingerprint: str
    validation_contract_version: Literal[
        "studio-benchmark-freeze-validation-v1"
    ] = STUDIO_BENCHMARK_FREEZE_VALIDATION_CONTRACT
    package_identity: str = Field(min_length=1, max_length=384)
    package_content_identity: str
    splits: tuple[StudioBenchmarkFreezeSplitV1, ...] = Field(
        min_length=1,
        max_length=STUDIO_BENCHMARK_FREEZE_MAX_SPLITS,
    )
    diagnostics: tuple[StudioBenchmarkAuthoringDiagnosticV1, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS,
    )
    warnings: tuple[str, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_FREEZE_MAX_WARNINGS,
    )
    unverified_checks: tuple[str, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_FREEZE_MAX_UNVERIFIED_CHECKS,
    )
    safety: StudioBenchmarkValidationSafetyV1 = Field(
        default_factory=StudioBenchmarkValidationSafetyV1
    )
    created_at: StrictInt = Field(ge=0)

    @field_validator("attestation_id")
    @classmethod
    def _attestation_id(cls, value: str) -> str:
        """Validate the opaque attestation identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_validation_attestation_id(value)

    @field_validator("draft_id")
    @classmethod
    def _draft_id(cls, value: str) -> str:
        """Validate the owning draft identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("authoring_revision_id")
    @classmethod
    def _authoring_revision_id(cls, value: str) -> str:
        """Validate the attested authoring revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("document_fingerprint", "package_content_identity")
    @classmethod
    def _canonical_identity(cls, value: str) -> str:
        """Validate an authoring or Package canonical digest.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        return _digest(value)

    @field_validator("package_identity")
    @classmethod
    def _package_identity(cls, value: str) -> str:
        """Reject unsafe or unbounded Package identity projection.

        Args:
            value: Candidate Core Package identity.

        Raises:
            ValueError: Identity is unsafe.

        Returns:
            Validated identity.
        """
        return _safe_public_text(value, limit=384)

    @field_validator("warnings", "unverified_checks")
    @classmethod
    def _safe_aggregate_facts(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        """Require deterministic safe aggregate facts.

        Args:
            value: Candidate facts.

        Raises:
            ValueError: Facts are unsafe or non-deterministic.

        Returns:
            Validated facts.
        """
        if value != tuple(sorted(set(value))):
            raise ValueError("aggregate freeze facts must be unique and sorted")
        return tuple(_safe_public_text(item, limit=500) for item in value)

    @model_validator(mode="after")
    def _complete_split_set(self) -> "StudioBenchmarkValidationAttestationV1":
        """Require unique split facts and no error diagnostics.

        Raises:
            ValueError: Successful evidence is incomplete or contradictory.

        Returns:
            Validated attestation.
        """
        names = [item.split for item in self.splits]
        if len(names) != len(set(names)):
            raise ValueError("attestation split identities must be unique")
        if sum(item.schedule_entry_count for item in self.splits) > (
            STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES
        ):
            raise ValueError("attestation schedule exceeds its aggregate limit")
        if any(item.severity == "error" for item in self.diagnostics):
            raise ValueError("successful attestation cannot contain errors")
        return self


class StudioBenchmarkFrozenMemberV1(StudioBenchmarkFreezeModel):
    """One immutable content-addressed member in a frozen Package closure."""

    ordinal: StrictInt = Field(ge=0, lt=STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS)
    kind: Literal["manifest", "task", "protocol", "asset", "ground_truth"]
    path: str
    media_type: str
    size: StrictInt = Field(
        ge=0,
        le=STUDIO_BENCHMARK_AUTHORING_MAX_RESOURCE_BYTES,
    )
    sha256: str
    content_identity: str

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        """Validate the Package-relative member path.

        Args:
            value: Candidate logical path.

        Raises:
            ValueError: Path is unsafe.

        Returns:
            Validated path.
        """
        return _member_path(value)

    @field_validator("media_type")
    @classmethod
    def _media_type(cls, value: str) -> str:
        """Validate the header-safe member media type.

        Args:
            value: Candidate media type.

        Raises:
            ValueError: Media type is malformed.

        Returns:
            Validated media type.
        """
        return validate_benchmark_authoring_media_type(value)

    @field_validator("sha256")
    @classmethod
    def _sha256(cls, value: str) -> str:
        """Validate the member digest.

        Args:
            value: Candidate prefixed digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        return _digest(value)

    @field_validator("content_identity")
    @classmethod
    def _content_identity(cls, value: str) -> str:
        """Validate the immutable managed-content identity.

        Args:
            value: Candidate opaque content identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        if _CONTENT_ID.fullmatch(value) is None:
            raise ValueError("invalid frozen member content identity")
        return value


class StudioBenchmarkPackageRevisionV1(StudioBenchmarkFreezeModel):
    """Immutable closed semantic snapshot prepared for later publication."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    package_revision_id: str
    draft_id: str
    authoring_revision_id: str
    validation_attestation_id: str
    package_identity: str = Field(min_length=1, max_length=384)
    package_content_identity: str
    closure_identity: str
    members: tuple[StudioBenchmarkFrozenMemberV1, ...] = Field(
        min_length=1,
        max_length=STUDIO_BENCHMARK_AUTHORING_MAX_MEMBERS,
    )
    created_at: StrictInt = Field(ge=0)

    @field_validator("package_revision_id")
    @classmethod
    def _package_revision_id(cls, value: str) -> str:
        """Validate the opaque Package revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_package_revision_id(value)

    @field_validator("draft_id")
    @classmethod
    def _draft_id(cls, value: str) -> str:
        """Validate the owning draft identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("authoring_revision_id")
    @classmethod
    def _authoring_revision_id(cls, value: str) -> str:
        """Validate the frozen authoring revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("validation_attestation_id")
    @classmethod
    def _validation_attestation_id(cls, value: str) -> str:
        """Validate the linked validation attestation identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return validate_benchmark_validation_attestation_id(value)

    @field_validator("package_identity")
    @classmethod
    def _package_identity(cls, value: str) -> str:
        """Validate a safe bounded Core Package identity.

        Args:
            value: Candidate Package identity.

        Raises:
            ValueError: Identity is unsafe.

        Returns:
            Validated identity.
        """
        return _safe_public_text(value, limit=384)

    @field_validator("package_content_identity", "closure_identity")
    @classmethod
    def _content_identities(cls, value: str) -> str:
        """Validate semantic and closure canonical identities.

        Args:
            value: Candidate canonical digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        return _digest(value)

    @model_validator(mode="after")
    def _closed_inventory(self) -> "StudioBenchmarkPackageRevisionV1":
        """Require complete deterministic member ordinals and logical paths.

        Raises:
            ValueError: Member order, path, or closure identity is inconsistent.

        Returns:
            Validated Package revision.
        """
        paths = [item.path for item in self.members]
        ordinals = [item.ordinal for item in self.members]
        if paths != sorted(paths) or len(paths) != len(set(paths)):
            raise ValueError("frozen member paths must be unique and sorted")
        if ordinals != list(range(len(self.members))):
            raise ValueError("frozen member ordinals must be complete")
        if sum(item.size for item in self.members) > (
            STUDIO_BENCHMARK_AUTHORING_MAX_TOTAL_IMPORT_BYTES
        ):
            raise ValueError("frozen Package content exceeds its aggregate limit")
        expected = benchmark_frozen_closure_identity(self.members)
        if self.closure_identity != expected:
            raise ValueError("frozen Package closure identity mismatch")
        return self


class StudioBenchmarkPackageRevisionDetailV1(StudioBenchmarkFreezeModel):
    """Exact immutable Package revision with its successful attestation."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    package_revision: StudioBenchmarkPackageRevisionV1
    validation_attestation: StudioBenchmarkValidationAttestationV1

    @model_validator(mode="after")
    def _linked_authority(self) -> "StudioBenchmarkPackageRevisionDetailV1":
        """Require Package revision and attestation ownership to agree.

        Raises:
            ValueError: Immutable identities disagree.

        Returns:
            Validated detail.
        """
        package = self.package_revision
        attestation = self.validation_attestation
        if (
            package.validation_attestation_id != attestation.attestation_id
            or package.draft_id != attestation.draft_id
            or package.authoring_revision_id != attestation.authoring_revision_id
            or package.package_identity != attestation.package_identity
            or package.package_content_identity
            != attestation.package_content_identity
            or package.created_at != attestation.created_at
        ):
            raise ValueError("Package revision attestation does not match")
        return self


class StudioBenchmarkFreezeResultV1(StudioBenchmarkFreezeModel):
    """Strict successful response for a newly committed or retried freeze."""

    schema_version: StrictInt = Field(default=1, ge=1, le=1)
    created: StrictBool
    detail: StudioBenchmarkPackageRevisionDetailV1


__all__ = [
    "STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES",
    "STUDIO_BENCHMARK_FREEZE_MAX_SPLITS",
    "STUDIO_BENCHMARK_FREEZE_MAX_UNVERIFIED_CHECKS",
    "STUDIO_BENCHMARK_FREEZE_MAX_WARNINGS",
    "STUDIO_BENCHMARK_FREEZE_VALIDATION_CONTRACT",
    "StudioBenchmarkFreezeModel",
    "StudioBenchmarkFreezeRequestV1",
    "StudioBenchmarkFreezeResultV1",
    "StudioBenchmarkFreezeSplitV1",
    "StudioBenchmarkFrozenMemberV1",
    "StudioBenchmarkPackageRevisionDetailV1",
    "StudioBenchmarkPackageRevisionV1",
    "StudioBenchmarkValidationAttestationV1",
    "StudioBenchmarkValidationSafetyV1",
    "benchmark_frozen_closure_identity",
    "validate_benchmark_package_revision_id",
    "validate_benchmark_validation_attestation_id",
]
