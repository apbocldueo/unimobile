"""Exact-revision Studio Benchmark Contract Test application service."""

from __future__ import annotations

from typing import Any, Mapping

from pydantic import ValidationError

from zhixing.benchmark.authoring import (
    BenchmarkContractTestCapacityError,
    BenchmarkFixtureProfile,
    BenchmarkFixtureProfileMetadata,
    BenchmarkFixtureProfileRegistry,
    run_benchmark_contract_tests,
)

from .benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringRevisionCompiler,
)
from .benchmark_authoring_contract_models import (
    StudioBenchmarkContractTestCaseV1,
    StudioBenchmarkContractTestCoverageV1,
    StudioBenchmarkContractTestDiagnosticV1,
    StudioBenchmarkContractTestProfilePageV1,
    StudioBenchmarkContractTestProfileV1,
    StudioBenchmarkContractTestRequestV1,
    StudioBenchmarkContractTestResultV1,
)
from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_models import StudioBenchmarkAuthoringDocumentV1


def _profile_dto(
    value: BenchmarkFixtureProfileMetadata,
) -> StudioBenchmarkContractTestProfileV1:
    """Project safe Core profile metadata into the strict Studio DTO.

    Args:
        value: Bounded Core metadata without fixture implementations.

    Raises:
        ValueError: Core metadata violates the Studio public contract.

    Returns:
        Strict metadata-only Studio profile.
    """
    return StudioBenchmarkContractTestProfileV1(
        profile_id=value.profile_id,
        version=value.version,
        title=value.title,
        description=value.description,
        evidence_level=value.evidence_level,
        supported_kinds=tuple(item.value for item in value.supported_kinds),
        capabilities=value.capabilities,
    )


def _task_origins(
    document: StudioBenchmarkAuthoringDocumentV1,
    split: str,
) -> dict[str, tuple[str, int]]:
    """Resolve valid Plan task identities to immutable definition members.

    Args:
        document: Exact immutable authoring document.
        split: Explicit selected split.

    Raises:
        None: Invalid fragments produce a partial mapping and are diagnosed by
            the shared compiler before fixture discovery.

    Returns:
        Task identity to safe member path and local task-array index.
    """
    splits = document.manifest.document.get("splits")
    if not isinstance(splits, Mapping):
        return {}
    selected = splits.get(split)
    if not isinstance(selected, Mapping):
        return {}
    files = selected.get("files")
    if not isinstance(files, (list, tuple)):
        return {}
    by_path = {item.path: item for item in document.task_files}
    origins: dict[str, tuple[str, int]] = {}
    for raw_path in files:
        if not isinstance(raw_path, str) or raw_path not in by_path:
            continue
        for index, task in enumerate(by_path[raw_path].tasks):
            if isinstance(task, Mapping) and isinstance(task.get("id"), str):
                origins[str(task["id"])] = (raw_path, index)
    return origins


def _case_dto(
    case: Any,
    *,
    task_origins: Mapping[str, tuple[str, int]],
) -> StudioBenchmarkContractTestCaseV1:
    """Project one bounded Core case into member-addressable Studio facts.

    Args:
        case: Typed Core Contract Test case.
        task_origins: Exact task member provenance for the selected split.

    Raises:
        ValueError: A Core case violates the strict Studio contract.

    Returns:
        Strict revision-addressable Studio case.
    """
    origin = task_origins.get(case.task_id)
    member_path = origin[0] if origin is not None else None
    field_path = tuple(case.path)
    if origin is not None and field_path and isinstance(field_path[0], int):
        field_path = (origin[1], *field_path[1:])
    diagnostics = tuple(
        StudioBenchmarkContractTestDiagnosticV1(
            code=item.code,
            message=item.message,
            member_kind="task",
            member_path=member_path,
            field_path=field_path,
            task_id=case.task_id,
        )
        for item in case.diagnostics
    )
    return StudioBenchmarkContractTestCaseV1(
        case_id=case.case_id,
        task_id=case.task_id,
        kind=case.kind.value,
        logical_name=case.logical_name,
        member_path=member_path,
        field_path=field_path,
        phase=case.phase,
        seed=case.seed,
        status=case.status.value,
        fixture_id=case.fixture_id,
        fixture_version=case.fixture_version,
        checks=case.checks,
        skipped=case.skipped,
        diagnostics=diagnostics,
    )


class StudioBenchmarkContractTestApplicationService:
    """Run reviewed fake fixtures for one exact current draft revision."""

    def __init__(
        self,
        *,
        compiler: StudioBenchmarkAuthoringRevisionCompiler,
        profiles: BenchmarkFixtureProfileRegistry,
    ) -> None:
        """Bind shared exact-revision compilation and trusted fixtures.

        Args:
            compiler: Shared private disposable Package compiler.
            profiles: Injected server-owned fake-fixture registry.

        Raises:
            None.

        Returns:
            None.
        """
        self._compiler = compiler
        self._profiles = profiles

    @staticmethod
    def parse_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkContractTestRequestV1:
        """Parse one strict command without coercion or executable fields.

        Args:
            payload: JSON-compatible request object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is malformed.

        Returns:
            Strict Contract Test command.
        """
        try:
            return StudioBenchmarkContractTestRequestV1.model_validate(payload)
        except ValidationError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.contract_test_request_invalid",
                "Benchmark Contract Test request is invalid",
            ) from error

    def list_profiles(self) -> StudioBenchmarkContractTestProfilePageV1:
        """Return bounded metadata only, never factories or import locations.

        Raises:
            ValueError: Injected metadata violates public bounds.

        Returns:
            Stable enabled fixture-profile metadata page.
        """
        return StudioBenchmarkContractTestProfilePageV1(
            profiles=tuple(
                _profile_dto(item) for item in self._profiles.list_metadata()
            )
        )

    def _profile(self, profile_id: str) -> BenchmarkFixtureProfile:
        """Resolve one exact enabled profile before private materialization.

        Args:
            profile_id: Requested server-owned profile identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: Profile is unavailable.

        Returns:
            Exact enabled trusted profile.
        """
        try:
            return self._profiles.get(profile_id)
        except LookupError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.fixture_profile_unavailable",
                "Requested Benchmark fixture profile is unavailable",
            ) from error

    def run(
        self,
        draft_id: str,
        request: StudioBenchmarkContractTestRequestV1,
    ) -> StudioBenchmarkContractTestResultV1:
        """Compile and test only the exact current immutable revision.

        Args:
            draft_id: Owning authoring draft identity.
            request: Exact revision, split, seed, and profile command.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringCapacityError: Case count exceeds 1,000.
            StudioBenchmarkAuthoringStorageError: Private staging fails.
            StudioBenchmarkAuthoringValidationError: Profile is unavailable.

        Returns:
            Strict disposable result with no durable authoring mutation.
        """
        profile = self._profile(request.fixture_profile_id)
        analysis = self._compiler.compile(
            draft_id,
            request.revision_id,
            request.split,
        )
        public_profile = _profile_dto(profile.metadata)
        if not analysis.valid or analysis.plan is None:
            result = StudioBenchmarkContractTestResultV1(
                draft_id=draft_id,
                revision_id=analysis.revision.revision_id,
                document_fingerprint=(
                    analysis.revision.document_fingerprint
                ),
                request_fingerprint=request.fingerprint,
                split=request.split,
                seed=request.seed,
                profile=public_profile,
                identities=analysis.identities,
                valid_definition=False,
                coverage=StudioBenchmarkContractTestCoverageV1(
                    total=0,
                    passed=0,
                    failed=0,
                    skipped=0,
                    complete=True,
                    executed_checks_passed=True,
                ),
                precondition_diagnostics=analysis.diagnostics,
                diagnostics_truncated=analysis.diagnostics_truncated,
            )
            self._compiler.assert_still_current(
                draft_id,
                request.revision_id,
            )
            return result
        try:
            core = run_benchmark_contract_tests(
                analysis.plan,
                profile,
                seed=request.seed,
            )
        except BenchmarkContractTestCapacityError as error:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.contract_test_too_large",
                "Benchmark Contract Test case count exceeds its safe limit",
            ) from error
        origins = _task_origins(analysis.revision.document, request.split)
        result = StudioBenchmarkContractTestResultV1(
            draft_id=draft_id,
            revision_id=analysis.revision.revision_id,
            document_fingerprint=analysis.revision.document_fingerprint,
            request_fingerprint=request.fingerprint,
            split=request.split,
            seed=request.seed,
            profile=public_profile,
            identities=analysis.identities,
            valid_definition=True,
            coverage=StudioBenchmarkContractTestCoverageV1(
                total=core.coverage.total,
                passed=core.coverage.passed,
                failed=core.coverage.failed,
                skipped=core.coverage.skipped,
                complete=core.coverage.complete,
                executed_checks_passed=(
                    core.coverage.executed_checks_passed
                ),
            ),
            cases=tuple(
                _case_dto(item, task_origins=origins) for item in core.cases
            ),
            diagnostics_truncated=core.diagnostics_truncated,
        )
        self._compiler.assert_still_current(draft_id, request.revision_id)
        return result


__all__ = ["StudioBenchmarkContractTestApplicationService"]
