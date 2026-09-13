"""Exact-current all-split validation and immutable Benchmark freeze service."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from pydantic import ValidationError

from zhixing.benchmark import BenchmarkPackageManifest
from zhixing.benchmark.authoring import project_benchmark_dry_run

from .benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringRevisionCompiler,
)
from .benchmark_authoring_analysis_models import (
    StudioBenchmarkAuthoringBudgetV1,
    StudioBenchmarkAuthoringDiagnosticV1,
    StudioBenchmarkAuthoringOutputLayoutV1,
)
from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringFreezeEligibilityError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_freeze import StudioBenchmarkFrozenClosureBuilder
from .benchmark_authoring_freeze_models import (
    STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES,
    STUDIO_BENCHMARK_FREEZE_MAX_SPLITS,
    STUDIO_BENCHMARK_FREEZE_VALIDATION_CONTRACT,
    StudioBenchmarkFreezeRequestV1,
    StudioBenchmarkFreezeResultV1,
    StudioBenchmarkFreezeSplitV1,
    StudioBenchmarkPackageRevisionDetailV1,
    StudioBenchmarkPackageRevisionV1,
    StudioBenchmarkValidationAttestationV1,
    validate_benchmark_package_revision_id,
)
from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS,
    StudioBenchmarkAuthoringRevisionV1,
    validate_benchmark_draft_id,
)
from .benchmark_authoring_protocols import StudioBenchmarkAuthoringRepository


@dataclass(frozen=True)
class StudioBenchmarkCompleteFreezeAnalysis:
    """Complete successful all-split facts before durable attestation."""

    revision: StudioBenchmarkAuthoringRevisionV1
    package_identity: str
    package_content_identity: str
    splits: tuple[StudioBenchmarkFreezeSplitV1, ...]
    diagnostics: tuple[StudioBenchmarkAuthoringDiagnosticV1, ...]
    warnings: tuple[str, ...]
    unverified_checks: tuple[str, ...]


def _identity(prefix: str) -> str:
    """Create one opaque UUID-backed freeze identity.

    Args:
        prefix: Stable public resource prefix.

    Returns:
        Opaque identity.
    """
    return f"{prefix}-{uuid.uuid4().hex}"


def _request_error(error: ValidationError) -> StudioBenchmarkAuthoringValidationError:
    """Convert strict request parsing into a safe non-echoing failure.

    Args:
        error: Pydantic request validation failure.

    Returns:
        Safe authoring validation error.
    """
    del error
    return StudioBenchmarkAuthoringValidationError(
        "benchmark.authoring.freeze_request_invalid",
        "Benchmark freeze request is invalid",
    )


def _generic_diagnostic(
    *,
    code: str,
    message: str,
    member_kind: str,
    member_path: str | None,
    field_path: tuple[str | int, ...],
) -> StudioBenchmarkAuthoringDiagnosticV1:
    """Build one bounded field-addressable freeze diagnostic.

    Args:
        code: Stable safe diagnostic code.
        message: Bounded constant reader-facing message.
        member_kind: Manifest, task, Protocol, or resource location kind.
        member_path: Optional safe declared member path.
        field_path: Safe local field breadcrumb.

    Returns:
        Strict diagnostic.
    """
    return StudioBenchmarkAuthoringDiagnosticV1(
        code=code,
        message=message,
        member_kind=member_kind,
        member_path=member_path,
        field_path=field_path,
    )


class StudioBenchmarkValidatedFreezeAnalyzer:
    """Revalidate every manifest-declared split without runtime capabilities."""

    def __init__(self, compiler: StudioBenchmarkAuthoringRevisionCompiler) -> None:
        """Bind the existing exact-revision declaration-only compiler.

        Args:
            compiler: Private disposable Package compiler.

        Returns:
            None.
        """
        self._compiler = compiler

    @staticmethod
    def _manifest(
        revision: StudioBenchmarkAuthoringRevisionV1,
    ) -> BenchmarkPackageManifest:
        """Parse the exact revision manifest or raise bounded eligibility facts.

        Args:
            revision: Exact current immutable authoring revision.

        Raises:
            StudioBenchmarkAuthoringFreezeEligibilityError: Manifest is invalid.

        Returns:
            Strict Core Package manifest.
        """
        try:
            return BenchmarkPackageManifest.model_validate(
                revision.document.manifest.document
            )
        except ValidationError as error:
            diagnostic = _generic_diagnostic(
                code="benchmark.package.manifest_invalid",
                message="Benchmark Package manifest is not valid.",
                member_kind="manifest",
                member_path="benchmark.yaml",
                field_path=("manifest",),
            )
            raise StudioBenchmarkAuthoringFreezeEligibilityError(
                "benchmark.authoring.freeze_ineligible",
                "Benchmark authoring revision is not eligible for freeze",
                diagnostics=(diagnostic,),
            ) from error

    def analyze(
        self,
        draft_id: str,
        revision_id: str,
    ) -> StudioBenchmarkCompleteFreezeAnalysis:
        """Compile and project every split of one exact current revision.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact current authoring revision identity.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Complete analysis exceeds a
                configured bound.
            StudioBenchmarkAuthoringFreezeEligibilityError: Any declared split
                fails validation or dry-run projection.
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringStorageError: Reconstruction fails.

        Returns:
            Complete successful all-split analysis facts.
        """
        revision = self._compiler.load_exact_current(draft_id, revision_id)
        manifest = self._manifest(revision)
        split_names = tuple(manifest.splits)
        if len(split_names) > STUDIO_BENCHMARK_FREEZE_MAX_SPLITS:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.freeze_splits_too_many",
                "Benchmark freeze split count exceeds its safe limit",
            )

        split_facts: list[StudioBenchmarkFreezeSplitV1] = []
        diagnostics: list[StudioBenchmarkAuthoringDiagnosticV1] = []
        warnings: set[str] = set()
        unverified: set[str] = set()
        package_identity: str | None = None
        package_content_identity: str | None = None
        total_schedule_entries = 0

        for split_name in split_names:
            compiled = self._compiler.compile(
                draft_id,
                revision_id,
                split_name,
            )
            if compiled.diagnostics_truncated:
                raise StudioBenchmarkAuthoringCapacityError(
                    "benchmark.authoring.freeze_diagnostics_too_many",
                    "Benchmark freeze diagnostics exceed their safe limit",
                )
            diagnostics.extend(compiled.diagnostics)
            if len(diagnostics) > STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS:
                raise StudioBenchmarkAuthoringCapacityError(
                    "benchmark.authoring.freeze_diagnostics_too_many",
                    "Benchmark freeze diagnostics exceed their safe limit",
                )
            if not compiled.valid:
                continue
            identities = compiled.identities
            if identities.package is None or identities.package_content is None:
                diagnostics.append(
                    _generic_diagnostic(
                        code="benchmark.package.identity_unavailable",
                        message="Benchmark Package identity is unavailable.",
                        member_kind="manifest",
                        member_path="benchmark.yaml",
                        field_path=("identity",),
                    )
                )
                continue
            if package_identity is None:
                package_identity = identities.package
                package_content_identity = identities.package_content
            elif (
                package_identity != identities.package
                or package_content_identity != identities.package_content
            ):
                diagnostics.append(
                    _generic_diagnostic(
                        code="benchmark.package.identity_inconsistent",
                        message="Benchmark Package identity changed across splits.",
                        member_kind="manifest",
                        member_path="benchmark.yaml",
                        field_path=("identity",),
                    )
                )
                continue
            report = project_benchmark_dry_run(
                compiled.plan,
                compiled.protocol,
                {},
                max_schedule_entries=(
                    STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES
                ),
            )
            if not report.ok:
                diagnostics.append(
                    _generic_diagnostic(
                        code="benchmark.dry_run.freeze_incomplete",
                        message="Benchmark split dry-run is not complete.",
                        member_kind="protocol",
                        member_path=manifest.default_protocol,
                        field_path=("splits", split_name),
                    )
                )
                continue
            total_schedule_entries += len(report.schedule)
            if total_schedule_entries > (
                STUDIO_BENCHMARK_FREEZE_MAX_SCHEDULE_ENTRIES
            ):
                raise StudioBenchmarkAuthoringCapacityError(
                    "benchmark.authoring.freeze_schedule_too_large",
                    "Benchmark freeze schedule exceeds its safe aggregate limit",
                )
            split_warnings = tuple(sorted(set(report.warnings)))
            split_unverified = tuple(
                sorted(
                    {
                        *compiled.unverified_checks,
                        *report.unverified_checks,
                    }
                )
            )
            warnings.update(split_warnings)
            unverified.update(split_unverified)
            split_facts.append(
                StudioBenchmarkFreezeSplitV1(
                    split=split_name,
                    benchmark_plan_identity=compiled.plan.canonical_hash(),
                    experiment_protocol_identity=(
                        compiled.protocol.canonical_hash()
                    ),
                    task_count=len(compiled.plan.tasks),
                    schedule_entry_count=len(report.schedule),
                    budget=StudioBenchmarkAuthoringBudgetV1.model_validate(
                        report.budget
                    ),
                    fairness_warnings=split_warnings,
                    output_layout=(
                        StudioBenchmarkAuthoringOutputLayoutV1.model_validate(
                            report.output_layout
                        )
                    ),
                    unverified_checks=split_unverified,
                )
            )

        error_diagnostics = tuple(
            item for item in diagnostics if item.severity == "error"
        )
        if (
            error_diagnostics
            or len(split_facts) != len(split_names)
            or package_identity is None
            or package_content_identity is None
        ):
            bounded = tuple(diagnostics[:STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS])
            if not bounded:
                bounded = (
                    _generic_diagnostic(
                        code="benchmark.package.freeze_ineligible",
                        message="Benchmark Package is not eligible for freeze.",
                        member_kind="manifest",
                        member_path="benchmark.yaml",
                        field_path=("splits",),
                    ),
                )
            raise StudioBenchmarkAuthoringFreezeEligibilityError(
                "benchmark.authoring.freeze_ineligible",
                "Benchmark authoring revision is not eligible for freeze",
                diagnostics=bounded,
            )
        self._compiler.assert_still_current(draft_id, revision_id)
        return StudioBenchmarkCompleteFreezeAnalysis(
            revision=revision,
            package_identity=package_identity,
            package_content_identity=package_content_identity,
            splits=tuple(split_facts),
            diagnostics=tuple(
                item for item in diagnostics if item.severity != "error"
            ),
            warnings=tuple(sorted(warnings)),
            unverified_checks=tuple(sorted(unverified)),
        )


class StudioBenchmarkValidatedFreezeApplicationService:
    """Create immutable Package revisions from complete server-owned evidence."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        analyzer: StudioBenchmarkValidatedFreezeAnalyzer,
        closure_builder: StudioBenchmarkFrozenClosureBuilder,
        clock: Callable[[], int] | None = None,
        identity_factory: Callable[[str], str] | None = None,
    ) -> None:
        """Bind only the durable and definition-only freeze dependencies.

        Args:
            repository: Durable authoring and freeze repository.
            analyzer: Complete exact-current all-split analyzer.
            closure_builder: Canonical managed-content closure builder.
            clock: Optional deterministic millisecond clock.
            identity_factory: Optional deterministic opaque identity factory.

        Returns:
            None.
        """
        self._repository = repository
        self._analyzer = analyzer
        self._closure_builder = closure_builder
        self._clock = clock or (lambda: time.time_ns() // 1_000_000)
        self._identity_factory = identity_factory or _identity

    @staticmethod
    def parse_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkFreezeRequestV1:
        """Parse one strict freeze request without input coercion.

        Args:
            payload: JSON-compatible request object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is invalid.

        Returns:
            Strict freeze command.
        """
        try:
            return StudioBenchmarkFreezeRequestV1.model_validate(payload)
        except ValidationError as error:
            raise _request_error(error) from error

    def freeze(
        self,
        draft_id: str,
        request: StudioBenchmarkFreezeRequestV1,
    ) -> StudioBenchmarkFreezeResultV1:
        """Validate and atomically freeze one exact current authoring revision.

        Args:
            draft_id: Owning draft identity.
            request: Strict idempotent freeze command.

        Raises:
            StudioBenchmarkAuthoringError: Ownership, analysis, content,
                concurrency, idempotency, or durability fails.

        Returns:
            Newly created or original immutable freeze result.
        """
        try:
            validate_benchmark_draft_id(draft_id)
        except ValueError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.draft_id_invalid",
                "Benchmark authoring draft identity is invalid",
            ) from error
        existing = self._repository.find_freeze_result(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
        )
        if existing is not None:
            return StudioBenchmarkFreezeResultV1(
                created=False,
                detail=existing,
            )
        analysis = self._analyzer.analyze(draft_id, request.revision_id)
        closure = self._closure_builder.build(analysis.revision.document)
        created_at = self._clock()
        attestation = StudioBenchmarkValidationAttestationV1(
            attestation_id=self._identity_factory(
                "benchmark-validation-attestation"
            ),
            draft_id=draft_id,
            authoring_revision_id=request.revision_id,
            document_fingerprint=analysis.revision.document_fingerprint,
            validation_contract_version=(
                STUDIO_BENCHMARK_FREEZE_VALIDATION_CONTRACT
            ),
            package_identity=analysis.package_identity,
            package_content_identity=analysis.package_content_identity,
            splits=analysis.splits,
            diagnostics=analysis.diagnostics,
            warnings=analysis.warnings,
            unverified_checks=analysis.unverified_checks,
            created_at=created_at,
        )
        package_revision = StudioBenchmarkPackageRevisionV1(
            package_revision_id=self._identity_factory(
                "benchmark-package-revision"
            ),
            draft_id=draft_id,
            authoring_revision_id=request.revision_id,
            validation_attestation_id=attestation.attestation_id,
            package_identity=analysis.package_identity,
            package_content_identity=analysis.package_content_identity,
            closure_identity=closure.closure_identity,
            members=closure.members,
            created_at=created_at,
        )
        detail, created = self._repository.commit_freeze(
            draft_id,
            client_request_id=request.client_request_id,
            request_fingerprint=request.fingerprint,
            expected_revision_id=request.revision_id,
            attestation=attestation,
            package_revision=package_revision,
        )
        return StudioBenchmarkFreezeResultV1(
            created=created,
            detail=detail,
        )

    def get_package_revision(
        self,
        draft_id: str,
        package_revision_id: str,
    ) -> StudioBenchmarkPackageRevisionDetailV1:
        """Read one exact Package revision only through its owning draft.

        Args:
            draft_id: Owning draft identity.
            package_revision_id: Exact frozen Package revision identity.

        Raises:
            StudioBenchmarkAuthoringValidationError: Identity is malformed.
            StudioBenchmarkAuthoringNotFoundError: Owned resource is absent.
            StudioBenchmarkAuthoringStorageError: Durable rows are invalid.

        Returns:
            Immutable Package revision detail.
        """
        try:
            validate_benchmark_draft_id(draft_id)
            validate_benchmark_package_revision_id(package_revision_id)
        except ValueError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.freeze_identity_invalid",
                "Benchmark freeze resource identity is invalid",
            ) from error
        return self._repository.get_package_revision(
            draft_id,
            package_revision_id,
        )


__all__ = [
    "StudioBenchmarkCompleteFreezeAnalysis",
    "StudioBenchmarkValidatedFreezeAnalyzer",
    "StudioBenchmarkValidatedFreezeApplicationService",
]
