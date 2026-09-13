"""Strict DTOs for revision-bound Studio Benchmark Contract Tests."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from zhixing.benchmark import canonical_hash

from .benchmark_authoring_analysis_models import (
    StudioBenchmarkAuthoringAnalysisIdentitiesV1,
    StudioBenchmarkAuthoringDiagnosticV1,
)
from .benchmark_authoring_models import (
    validate_benchmark_authoring_revision_id,
    validate_benchmark_draft_id,
)
from .models import StudioModel


STUDIO_BENCHMARK_CONTRACT_MAX_CASES = 1_000
STUDIO_BENCHMARK_CONTRACT_MAX_DIAGNOSTICS = 100
STUDIO_BENCHMARK_CONTRACT_MAX_PROFILES = 32

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_SPLIT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_PACKAGE_PATH = re.compile(
    r"^(?!/)(?!.*(?:^|/)\.\.(?:/|$))(?!.*\\)(?!.*//)[^\x00]+$"
)

ContractKind = Literal["initializer", "environment", "evaluator"]
ContractStatus = Literal["passed", "failed", "skipped"]


def _stable_id(value: str) -> str:
    """Validate one bounded public fixture identity.

    Args:
        value: Candidate public identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _STABLE_ID.fullmatch(value) is None:
        raise ValueError("identity must be stable and bounded")
    return value


def _member_path(value: str | None) -> str | None:
    """Validate one optional safe Package-relative member path.

    Args:
        value: Candidate member path or ``None``.

    Raises:
        ValueError: The path is absolute, traversing, ambiguous, or unsafe.

    Returns:
        Validated path or ``None``.
    """
    if value is not None and _PACKAGE_PATH.fullmatch(value) is None:
        raise ValueError("member path must be safe and Package-relative")
    return value


def _field_path(
    value: tuple[str | int, ...],
) -> tuple[str | int, ...]:
    """Validate one bounded member-local breadcrumb.

    Args:
        value: Candidate field path.

    Raises:
        ValueError: A segment is boolean, negative, or unbounded.

    Returns:
        Validated field path.
    """
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int)):
            raise ValueError("diagnostic path is invalid")
        if isinstance(item, str) and (not item or len(item) > 160):
            raise ValueError("diagnostic path segment is invalid")
        if isinstance(item, int) and item < 0:
            raise ValueError("diagnostic path index is invalid")
    return value


class StudioBenchmarkContractTestProfileV1(StudioModel):
    """Safe metadata projection for one server-owned fixture profile."""

    profile_id: str
    version: str
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(max_length=500)
    evidence_level: str
    supported_kinds: tuple[ContractKind, ...] = Field(max_length=3)
    capabilities: tuple[str, ...] = Field(default=(), max_length=16)

    @field_validator("profile_id", "evidence_level")
    @classmethod
    def _identity(cls, value: str) -> str:
        """Validate profile and evidence identities.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _stable_id(value)

    @field_validator("version")
    @classmethod
    def _version(cls, value: str) -> str:
        """Require a simple semantic profile version.

        Args:
            value: Candidate version.

        Raises:
            ValueError: Version is malformed.

        Returns:
            Validated semantic version.
        """
        if _SEMVER.fullmatch(value) is None:
            raise ValueError("profile version must be semantic")
        return value

    @model_validator(mode="after")
    def _stable_inventory(self) -> "StudioBenchmarkContractTestProfileV1":
        """Require unique sorted metadata without implementation details.

        Raises:
            ValueError: Kinds or capabilities are duplicated or unsorted.

        Returns:
            Validated profile metadata.
        """
        if not self.supported_kinds:
            raise ValueError("profile must declare at least one contract kind")
        if list(self.supported_kinds) != sorted(set(self.supported_kinds)):
            raise ValueError("supported kinds must be unique and sorted")
        if list(self.capabilities) != sorted(set(self.capabilities)):
            raise ValueError("capabilities must be unique and sorted")
        return self


class StudioBenchmarkContractTestProfilePageV1(StudioModel):
    """Bounded metadata-only fixture-profile resource."""

    schema_version: Literal[1] = 1
    profiles: tuple[StudioBenchmarkContractTestProfileV1, ...] = Field(
        max_length=STUDIO_BENCHMARK_CONTRACT_MAX_PROFILES
    )

    @model_validator(mode="after")
    def _ordered_unique(self) -> "StudioBenchmarkContractTestProfilePageV1":
        """Require unique stable profile ordering.

        Raises:
            ValueError: Profile identities repeat or ordering is unstable.

        Returns:
            Validated profile page.
        """
        keys = [(item.profile_id, item.version) for item in self.profiles]
        if keys != sorted(set(keys)):
            raise ValueError("profiles must be unique and sorted")
        return self


class StudioBenchmarkContractTestRequestV1(StudioModel):
    """Strict command for one exact current authoring revision."""

    schema_version: Literal[1] = 1
    revision_id: str
    split: str
    seed: StrictInt = Field(ge=-(1 << 63), le=(1 << 63) - 1)
    fixture_profile_id: str

    @field_validator("revision_id")
    @classmethod
    def _revision(cls, value: str) -> str:
        """Validate the exact immutable revision identity.

        Args:
            value: Candidate revision identity.

        Raises:
            ValueError: Revision identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("split")
    @classmethod
    def _split(cls, value: str) -> str:
        """Validate an explicit bounded split.

        Args:
            value: Candidate split name.

        Raises:
            ValueError: Split name is malformed.

        Returns:
            Validated split name.
        """
        if _SPLIT.fullmatch(value) is None:
            raise ValueError("split must be explicit, stable, and bounded")
        return value

    @field_validator("fixture_profile_id")
    @classmethod
    def _profile(cls, value: str) -> str:
        """Validate the selected server-owned profile identity.

        Args:
            value: Candidate profile identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated profile identity.
        """
        return _stable_id(value)

    @property
    def fingerprint(self) -> str:
        """Return a canonical request-owner fingerprint.

        Returns:
            Canonical SHA-256 command fingerprint.
        """
        return canonical_hash(self.model_dump(mode="json", by_alias=True))


class StudioBenchmarkContractTestDiagnosticV1(StudioModel):
    """One safe case-local Contract Test diagnostic."""

    code: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=500)
    member_kind: Literal["manifest", "task", "protocol"]
    member_path: str | None = Field(default=None, max_length=512)
    field_path: tuple[str | int, ...] = Field(default=(), max_length=16)
    task_id: str | None = Field(default=None, max_length=256)

    @field_validator("member_path")
    @classmethod
    def _member(cls, value: str | None) -> str | None:
        """Require a safe optional Package-relative member path.

        Args:
            value: Candidate member path.

        Raises:
            ValueError: The path is unsafe.

        Returns:
            Validated member path.
        """
        return _member_path(value)

    @field_validator("field_path")
    @classmethod
    def _safe_path(
        cls,
        value: tuple[str | int, ...],
    ) -> tuple[str | int, ...]:
        """Reject booleans and unbounded path segments.

        Args:
            value: Candidate safe field breadcrumb.

        Raises:
            ValueError: A segment is unsafe.

        Returns:
            Validated field path.
        """
        return _field_path(value)


class StudioBenchmarkContractTestCaseV1(StudioModel):
    """One stable initializer, environment, or evaluator occurrence result."""

    case_id: str
    task_id: str = Field(min_length=1, max_length=256)
    kind: ContractKind
    logical_name: str = Field(min_length=1, max_length=160)
    member_path: str | None = Field(default=None, max_length=512)
    field_path: tuple[str | int, ...] = Field(default=(), max_length=16)
    phase: Literal["reset", "setup", "cleanup", "evaluation"] | None = None
    seed: StrictInt = Field(ge=0, le=(1 << 63) - 1)
    status: ContractStatus
    fixture_id: str | None = None
    fixture_version: str | None = None
    checks: tuple[str, ...] = Field(default=(), max_length=32)
    skipped: tuple[str, ...] = Field(default=(), max_length=32)
    diagnostics: tuple[StudioBenchmarkContractTestDiagnosticV1, ...] = Field(
        default=(), max_length=STUDIO_BENCHMARK_CONTRACT_MAX_DIAGNOSTICS
    )

    @field_validator("case_id")
    @classmethod
    def _case_digest(cls, value: str) -> str:
        """Validate the canonical case identity.

        Args:
            value: Candidate SHA-256 identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated case identity.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("case identity must be canonical")
        return value

    @field_validator("fixture_id")
    @classmethod
    def _fixture_identity(cls, value: str | None) -> str | None:
        """Validate an optional matched fixture identity.

        Args:
            value: Candidate fixture identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity or ``None``.
        """
        return _stable_id(value) if value is not None else None

    @field_validator("fixture_version")
    @classmethod
    def _fixture_version(cls, value: str | None) -> str | None:
        """Validate an optional matched fixture version.

        Args:
            value: Candidate semantic version.

        Raises:
            ValueError: Version is malformed.

        Returns:
            Validated version or ``None``.
        """
        if value is not None and _SEMVER.fullmatch(value) is None:
            raise ValueError("fixture version must be semantic")
        return value

    @field_validator("member_path")
    @classmethod
    def _member(cls, value: str | None) -> str | None:
        """Require a safe optional Package-relative member path.

        Args:
            value: Candidate member path.

        Raises:
            ValueError: The path is unsafe.

        Returns:
            Validated member path.
        """
        return _member_path(value)

    @field_validator("field_path")
    @classmethod
    def _case_path(
        cls,
        value: tuple[str | int, ...],
    ) -> tuple[str | int, ...]:
        """Require a bounded member-local case breadcrumb.

        Args:
            value: Candidate field path.

        Raises:
            ValueError: A segment is unsafe.

        Returns:
            Validated field path.
        """
        return _field_path(value)

    @model_validator(mode="after")
    def _status_ownership(self) -> "StudioBenchmarkContractTestCaseV1":
        """Keep pass/fail/skip evidence mutually consistent.

        Raises:
            ValueError: Case status contradicts its evidence.

        Returns:
            Validated case result.
        """
        matched = self.fixture_id is not None and self.fixture_version is not None
        if (self.fixture_id is None) != (self.fixture_version is None):
            raise ValueError("fixture identity and version must be paired")
        if self.status == "passed" and (not matched or self.skipped or self.diagnostics):
            raise ValueError("passed cases require matched clean execution")
        if self.status == "failed" and (not matched or not self.diagnostics or self.skipped):
            raise ValueError("failed cases require matched diagnostics")
        if self.status == "skipped" and (matched or not self.skipped):
            raise ValueError("skipped cases require an explicit missing coverage reason")
        return self


class StudioBenchmarkContractTestCoverageV1(StudioModel):
    """Independent case counts, completeness, and executed-check success."""

    total: StrictInt = Field(ge=0, le=STUDIO_BENCHMARK_CONTRACT_MAX_CASES)
    passed: StrictInt = Field(ge=0, le=STUDIO_BENCHMARK_CONTRACT_MAX_CASES)
    failed: StrictInt = Field(ge=0, le=STUDIO_BENCHMARK_CONTRACT_MAX_CASES)
    skipped: StrictInt = Field(ge=0, le=STUDIO_BENCHMARK_CONTRACT_MAX_CASES)
    complete: StrictBool
    executed_checks_passed: StrictBool

    @model_validator(mode="after")
    def _consistent_counts(self) -> "StudioBenchmarkContractTestCoverageV1":
        """Reject contradictory aggregate facts.

        Raises:
            ValueError: Counts or booleans contradict one another.

        Returns:
            Validated aggregate facts.
        """
        if self.total != self.passed + self.failed + self.skipped:
            raise ValueError("Contract Test counts do not sum to total")
        if self.complete != (self.skipped == 0):
            raise ValueError("completeness contradicts skipped count")
        if self.executed_checks_passed != (self.failed == 0):
            raise ValueError("executed-check fact contradicts failed count")
        return self


class StudioBenchmarkContractTestSafetyV1(StudioModel):
    """Fixed truthful safety/evidence boundary for the Studio command."""

    fixture_execution: Literal[True] = True
    package_code_executed: Literal[False] = False
    real_device_evidence: Literal[False] = False
    process_sandbox: Literal[False] = False
    device_capability: Literal[False] = False
    model_capability: Literal[False] = False
    network_capability: Literal[False] = False
    secret_capability: Literal[False] = False
    runtime_capability: Literal[False] = False
    experiment_capability: Literal[False] = False
    output_path_capability: Literal[False] = False
    benchmark_execution: Literal[False] = False
    agent_execution: Literal[False] = False
    publication_eligibility: Literal[False] = False
    result_persisted: Literal[False] = False


class StudioBenchmarkContractTestResultV1(StudioModel):
    """Strict bounded disposable Contract Test result for one request owner."""

    schema_version: Literal[1] = 1
    mode: Literal["fake-fixture"] = "fake-fixture"
    draft_id: str
    revision_id: str
    document_fingerprint: str
    request_fingerprint: str
    split: str
    seed: StrictInt = Field(ge=-(1 << 63), le=(1 << 63) - 1)
    profile: StudioBenchmarkContractTestProfileV1
    identities: StudioBenchmarkAuthoringAnalysisIdentitiesV1
    valid_definition: StrictBool
    coverage: StudioBenchmarkContractTestCoverageV1
    cases: tuple[StudioBenchmarkContractTestCaseV1, ...] = Field(
        default=(), max_length=STUDIO_BENCHMARK_CONTRACT_MAX_CASES
    )
    precondition_diagnostics: tuple[
        StudioBenchmarkAuthoringDiagnosticV1, ...
    ] = Field(default=(), max_length=STUDIO_BENCHMARK_CONTRACT_MAX_DIAGNOSTICS)
    diagnostics_truncated: StrictBool = False
    safety: StudioBenchmarkContractTestSafetyV1 = (
        StudioBenchmarkContractTestSafetyV1()
    )

    @field_validator("draft_id")
    @classmethod
    def _draft(cls, value: str) -> str:
        """Validate the owning draft identity.

        Args:
            value: Candidate draft identity.

        Raises:
            ValueError: Draft identity is malformed.

        Returns:
            Validated draft identity.
        """
        return validate_benchmark_draft_id(value)

    @field_validator("revision_id")
    @classmethod
    def _result_revision(cls, value: str) -> str:
        """Validate the bound revision identity.

        Args:
            value: Candidate revision identity.

        Raises:
            ValueError: Revision identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("document_fingerprint", "request_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        """Validate a canonical result-owner fingerprint.

        Args:
            value: Candidate SHA-256 identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated fingerprint.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("fingerprint must be canonical")
        return value

    @model_validator(mode="after")
    def _closed_result(self) -> "StudioBenchmarkContractTestResultV1":
        """Reject partial, contradictory, or unowned public results.

        Raises:
            ValueError: Result contradicts definition or aggregate facts.

        Returns:
            Validated closed result.
        """
        if len(self.cases) != self.coverage.total:
            raise ValueError("case collection does not match aggregate total")
        status_counts = {
            status: sum(item.status == status for item in self.cases)
            for status in ("passed", "failed", "skipped")
        }
        if (
            status_counts["passed"] != self.coverage.passed
            or status_counts["failed"] != self.coverage.failed
            or status_counts["skipped"] != self.coverage.skipped
        ):
            raise ValueError("case statuses contradict aggregate counts")
        diagnostic_count = len(self.precondition_diagnostics) + sum(
            len(item.diagnostics) for item in self.cases
        )
        if diagnostic_count > STUDIO_BENCHMARK_CONTRACT_MAX_DIAGNOSTICS:
            raise ValueError("public diagnostics exceed the safe limit")
        if not self.valid_definition:
            if self.cases or self.coverage.total != 0:
                raise ValueError("invalid definitions cannot expose fixture cases")
            if not self.precondition_diagnostics:
                raise ValueError("invalid definitions require diagnostics")
        elif self.precondition_diagnostics:
            raise ValueError("valid definitions cannot carry precondition errors")
        return self


__all__ = [
    "STUDIO_BENCHMARK_CONTRACT_MAX_CASES",
    "STUDIO_BENCHMARK_CONTRACT_MAX_DIAGNOSTICS",
    "STUDIO_BENCHMARK_CONTRACT_MAX_PROFILES",
    "StudioBenchmarkContractTestCaseV1",
    "StudioBenchmarkContractTestCoverageV1",
    "StudioBenchmarkContractTestDiagnosticV1",
    "StudioBenchmarkContractTestProfilePageV1",
    "StudioBenchmarkContractTestProfileV1",
    "StudioBenchmarkContractTestRequestV1",
    "StudioBenchmarkContractTestResultV1",
    "StudioBenchmarkContractTestSafetyV1",
]
