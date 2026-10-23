"""Revision-bound side-effect-free Benchmark authoring analysis service."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import ValidationError

from zhixing.benchmark import (
    BenchmarkDefinitionError,
    BenchmarkDiagnostic,
    BenchmarkPackage,
    BenchmarkPackageManifest,
    BenchmarkPlan,
    BenchmarkValidationLevel,
    ExperimentProtocol,
    compile_benchmark_package,
    load_manifest,
)
from zhixing.benchmark.authoring import project_benchmark_dry_run
from zhixing.benchmark.loaders import load_package_suites

from .benchmark_authoring_analysis_models import (
    STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES,
    StudioBenchmarkAuthoringAnalysisIdentitiesV1,
    StudioBenchmarkAuthoringBudgetV1,
    StudioBenchmarkAuthoringDiagnosticV1,
    StudioBenchmarkAuthoringDryRunRequestV1,
    StudioBenchmarkAuthoringDryRunResultV1,
    StudioBenchmarkAuthoringOutputLayoutV1,
    StudioBenchmarkAuthoringScheduleEntryV1,
    StudioBenchmarkAuthoringValidationRequestV1,
    StudioBenchmarkAuthoringValidationResultV1,
    StudioBenchmarkVerifiedAgentRevisionV1,
    project_authoring_diagnostics,
)
from .benchmark_authoring_errors import (
    StudioBenchmarkAuthoringCapacityError,
    StudioBenchmarkAuthoringRevisionConflictError,
    StudioBenchmarkAuthoringValidationError,
)
from .benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
    StudioBenchmarkMissingManagedResourceError,
)
from .benchmark_authoring_models import (
    StudioBenchmarkAuthoringRevisionV1,
    validate_benchmark_draft_id,
)
from .benchmark_authoring_protocols import StudioBenchmarkAuthoringRepository
from .repository import AgentDocumentRepository, AgentRevisionNotFoundError
from .revision_verifier import verify_immutable_agent_revision
from .run_errors import StudioRunValidationError


@dataclass(frozen=True)
class StudioBenchmarkCompiledAuthoringAnalysis:
    """Internal staged compilation facts hidden from the HTTP contract."""

    revision: StudioBenchmarkAuthoringRevisionV1
    identities: StudioBenchmarkAuthoringAnalysisIdentitiesV1
    diagnostics: tuple[StudioBenchmarkAuthoringDiagnosticV1, ...]
    diagnostics_truncated: bool
    unverified_checks: tuple[str, ...]
    plan: BenchmarkPlan | None
    protocol: ExperimentProtocol | None

    @property
    def valid(self) -> bool:
        """Return whether complete Plan and Protocol facts are available.

        Returns:
            True only when compilation emitted no error diagnostic.
        """
        return (
            self.plan is not None
            and self.protocol is not None
            and not any(item.severity == "error" for item in self.diagnostics)
        )


def _request_error(error: ValidationError) -> StudioBenchmarkAuthoringValidationError:
    """Convert strict request validation into one safe public failure.

    Args:
        error: Pydantic request validation failure.

    Raises:
        None.

    Returns:
        Safe authoring validation error without input echoing.
    """
    del error
    return StudioBenchmarkAuthoringValidationError(
        "benchmark.authoring.analysis_request_invalid",
        "Benchmark authoring analysis request is invalid",
    )


def _definition_diagnostics(error: Exception) -> tuple[BenchmarkDiagnostic, ...]:
    """Project a known definition failure to safe Core diagnostics.

    Args:
        error: Definition parsing or validation failure.

    Raises:
        None.

    Returns:
        Existing diagnostics or one bounded generic diagnostic.
    """
    if isinstance(error, BenchmarkDefinitionError):
        return error.diagnostics
    return (
        BenchmarkDiagnostic(
            code="benchmark.definition.invalid",
            message="Benchmark definition could not be analyzed.",
            source="benchmark.yaml",
            path=(type(error).__name__,),
        ),
    )


def _missing_resource_diagnostic(
    error: StudioBenchmarkMissingManagedResourceError,
) -> StudioBenchmarkAuthoringDiagnosticV1:
    """Create one field-addressable missing managed-resource diagnostic.

    Args:
        error: Internal missing content fact.

    Raises:
        None.

    Returns:
        Safe resource diagnostic without content capability or host path.
    """
    return StudioBenchmarkAuthoringDiagnosticV1(
        code="benchmark.resource.content_unavailable",
        message="Declared Benchmark resource content is unavailable.",
        member_kind="resource",
        member_path=error.member_path,
        field_path=("content",),
        resource_id=error.resource_id,
    )


def _agent_diagnostic(
    *,
    agent_id: str,
    revision_id: str,
    code: str,
    message: str,
) -> StudioBenchmarkAuthoringDiagnosticV1:
    """Create one safe exact-Agent-revision diagnostic.

    Args:
        agent_id: Requested Agent identity.
        revision_id: Requested immutable revision identity.
        code: Stable safe diagnostic code.
        message: Bounded reader-facing failure message.

    Raises:
        None.

    Returns:
        Strict Agent-addressable diagnostic.
    """
    return StudioBenchmarkAuthoringDiagnosticV1(
        code=code,
        message=message,
        member_kind="agent",
        field_path=("agentRevisions",),
        agent_id=agent_id,
        revision_id=revision_id,
    )


class StudioBenchmarkAuthoringRevisionCompiler:
    """Compile one exact current authoring revision through private staging."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        materializer: StudioBenchmarkAuthoringPackageMaterializer,
        agents: AgentDocumentRepository,
        contract_catalog: Any | None = None,
        known_plugins: set[str] | None = None,
    ) -> None:
        """Bind persistence and the private disposable Package boundary.

        Args:
            repository: Durable authoring draft/revision repository.
            materializer: Private disposable Package reconstruction boundary.
            agents: Retained compatibility dependency; compilation does not
                inspect Agent revisions.
            contract_catalog: Retained compatibility dependency for callers
                that compose both analysis responsibilities.
            known_plugins: Optional metadata-only plugin ID inventory.

        Raises:
            None.

        Returns:
            None.
        """
        self._repository = repository
        self._materializer = materializer
        self._agents = agents
        self._contract_catalog = contract_catalog
        self._known_plugins = (
            set(known_plugins) if known_plugins is not None else None
        )

    @staticmethod
    def parse_validation_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkAuthoringValidationRequestV1:
        """Parse one strict validation request without input coercion.

        Args:
            payload: JSON-compatible request object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is invalid.

        Returns:
            Strict validation request DTO.
        """
        try:
            return StudioBenchmarkAuthoringValidationRequestV1.model_validate(
                payload
            )
        except ValidationError as error:
            raise _request_error(error) from error

    @staticmethod
    def parse_dry_run_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkAuthoringDryRunRequestV1:
        """Parse one strict dry-run request without input coercion.

        Args:
            payload: JSON-compatible request object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is invalid.

        Returns:
            Strict dry-run request DTO.
        """
        try:
            return StudioBenchmarkAuthoringDryRunRequestV1.model_validate(
                payload
            )
        except ValidationError as error:
            raise _request_error(error) from error

    def _load_exact_current(
        self,
        draft_id: str,
        revision_id: str,
    ) -> StudioBenchmarkAuthoringRevisionV1:
        """Load a revision only when it is the draft's current pointer.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact requested immutable revision.

        Raises:
            StudioBenchmarkAuthoringValidationError: Draft identity is invalid.
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringNotFoundError: Draft/revision is absent.
            StudioBenchmarkAuthoringStorageError: Durable state cannot be read.

        Returns:
            Exact current immutable authoring revision.
        """
        try:
            validate_benchmark_draft_id(draft_id)
        except ValueError as error:
            raise StudioBenchmarkAuthoringValidationError(
                "benchmark.authoring.draft_id_invalid",
                "Benchmark authoring draft identity is invalid",
            ) from error
        draft = self._repository.get_draft(draft_id)
        revision = self._repository.get_revision(draft_id, revision_id)
        if draft.current_revision_id != revision_id:
            raise StudioBenchmarkAuthoringRevisionConflictError(
                "benchmark.authoring.analysis_revision_stale",
                "Benchmark analysis requires the current draft revision",
                current_revision_id=draft.current_revision_id,
            )
        return revision

    def _assert_still_current(self, draft_id: str, revision_id: str) -> None:
        """Recheck current-pointer ownership immediately before response.

        Args:
            draft_id: Owning draft identity.
            revision_id: Revision that was analyzed.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Pointer changed.
            StudioBenchmarkAuthoringNotFoundError: Draft disappeared.
            StudioBenchmarkAuthoringStorageError: Durable state cannot be read.

        Returns:
            None.
        """
        current = self._repository.get_draft(draft_id).current_revision_id
        if current != revision_id:
            raise StudioBenchmarkAuthoringRevisionConflictError(
                "benchmark.authoring.analysis_revision_stale",
                "Benchmark analysis requires the current draft revision",
                current_revision_id=current,
            )

    def compile(
        self,
        draft_id: str,
        revision_id: str,
        split: str,
    ) -> StudioBenchmarkCompiledAuthoringAnalysis:
        """Reconstruct and analyze one exact revision without runtime effects.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact current revision identity.
            split: Explicit Package split.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Closure exceeds safe bounds.
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringStorageError: Staging/integrity fails.

        Returns:
            Staged canonical identities, diagnostics, Plan, and Protocol.
        """
        revision = self._load_exact_current(draft_id, revision_id)
        core_diagnostics: tuple[BenchmarkDiagnostic, ...] = ()
        package_identity: str | None = None
        package_content_identity: str | None = None
        plan: BenchmarkPlan | None = None
        protocol: ExperimentProtocol | None = None
        missing_resource: StudioBenchmarkAuthoringDiagnosticV1 | None = None
        try:
            manifest_contract = BenchmarkPackageManifest.model_validate(
                revision.document.manifest.document
            )
            package_identity = manifest_contract.identity.identifier
        except ValidationError:
            pass
        try:
            with self._materializer.materialize(revision.document) as root:
                try:
                    manifest = load_manifest(root)
                    package_identity = manifest.identity.identifier
                except Exception as error:
                    core_diagnostics = _definition_diagnostics(error)
                else:
                    try:
                        suites = load_package_suites(root, manifest)
                        package_content_identity = BenchmarkPackage(
                            manifest=manifest,
                            suites=suites,
                        ).content_identity
                    except Exception as error:
                        core_diagnostics = _definition_diagnostics(error)
                    else:
                        compiled = compile_benchmark_package(
                            root,
                            split=split,
                            validation_level=BenchmarkValidationLevel.FULL,
                            known_plugins=self._known_plugins,
                        )
                        core_diagnostics = compiled.diagnostics
                        plan = compiled.plan
                        protocol = compiled.protocol
                        if manifest.default_protocol is None:
                            core_diagnostics = (
                                *core_diagnostics,
                                BenchmarkDiagnostic(
                                    code="benchmark.protocol.default_required",
                                    message=(
                                        "Authoring analysis requires an explicit "
                                        "default ExperimentProtocol."
                                    ),
                                    source="benchmark.yaml",
                                    path=("default_protocol",),
                                ),
                            )
        except StudioBenchmarkMissingManagedResourceError as error:
            missing_resource = _missing_resource_diagnostic(error)

        projected, truncated = project_authoring_diagnostics(
            core_diagnostics,
            document=revision.document,
            split=split,
        )
        if missing_resource is not None:
            merged = tuple(
                sorted(
                    (*projected, missing_resource),
                    key=lambda item: (
                        item.severity,
                        item.member_kind,
                        item.member_path or "",
                        item.code,
                    ),
                )
            )
            truncated = truncated or len(merged) > 100
            projected = merged[:100]
        unverified: list[str] = []
        if self._known_plugins is None:
            unverified.append("plugin-availability")
        return StudioBenchmarkCompiledAuthoringAnalysis(
            revision=revision,
            identities=StudioBenchmarkAuthoringAnalysisIdentitiesV1(
                package=package_identity,
                package_content=package_content_identity,
                benchmark_plan=(
                    plan.canonical_hash() if plan is not None else None
                ),
                experiment_protocol=(
                    protocol.canonical_hash()
                    if protocol is not None
                    else None
                ),
            ),
            diagnostics=projected,
            diagnostics_truncated=truncated,
            unverified_checks=tuple(unverified),
            plan=plan,
            protocol=protocol,
        )

    def load_exact_current(
        self,
        draft_id: str,
        revision_id: str,
    ) -> StudioBenchmarkAuthoringRevisionV1:
        """Expose the shared exact-current ownership check.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact requested immutable revision.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringValidationError: Draft identity is invalid.

        Returns:
            Exact current immutable revision.
        """
        return self._load_exact_current(draft_id, revision_id)

    def assert_still_current(self, draft_id: str, revision_id: str) -> None:
        """Expose the shared late current-pointer race check.

        Args:
            draft_id: Owning draft identity.
            revision_id: Revision whose result would be returned.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Pointer changed.

        Returns:
            None.
        """
        self._assert_still_current(draft_id, revision_id)


class StudioBenchmarkValidationDryRunApplicationService:
    """Validate and dry-run only an exact current immutable draft revision."""

    def __init__(
        self,
        *,
        repository: StudioBenchmarkAuthoringRepository,
        materializer: StudioBenchmarkAuthoringPackageMaterializer,
        agents: AgentDocumentRepository,
        contract_catalog: Any | None = None,
        known_plugins: set[str] | None = None,
        compiler: StudioBenchmarkAuthoringRevisionCompiler | None = None,
    ) -> None:
        """Bind analysis to the shared exact-revision compiler.

        Args:
            repository: Durable authoring draft/revision repository.
            materializer: Private disposable Package reconstruction boundary.
            agents: Immutable Agent revision repository.
            contract_catalog: Optional AgentGraph extension contract catalog.
            known_plugins: Optional metadata-only plugin ID inventory.
            compiler: Optional shared compiler override for composition tests.

        Raises:
            None.

        Returns:
            None.
        """
        self._repository = repository
        self._materializer = materializer
        self._agents = agents
        self._contract_catalog = contract_catalog
        self._known_plugins = (
            set(known_plugins) if known_plugins is not None else None
        )
        self._compiler = compiler or StudioBenchmarkAuthoringRevisionCompiler(
            repository=repository,
            materializer=materializer,
            agents=agents,
            contract_catalog=contract_catalog,
            known_plugins=known_plugins,
        )

    @staticmethod
    def parse_validation_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkAuthoringValidationRequestV1:
        """Parse one strict validation request without input coercion.

        Args:
            payload: JSON-compatible request object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is invalid.

        Returns:
            Strict validation request DTO.
        """
        try:
            return StudioBenchmarkAuthoringValidationRequestV1.model_validate(
                payload
            )
        except ValidationError as error:
            raise _request_error(error) from error

    @staticmethod
    def parse_dry_run_request(
        payload: Mapping[str, Any],
    ) -> StudioBenchmarkAuthoringDryRunRequestV1:
        """Parse one strict dry-run request without input coercion.

        Args:
            payload: JSON-compatible request object.

        Raises:
            StudioBenchmarkAuthoringValidationError: Payload is invalid.

        Returns:
            Strict dry-run request DTO.
        """
        try:
            return StudioBenchmarkAuthoringDryRunRequestV1.model_validate(
                payload
            )
        except ValidationError as error:
            raise _request_error(error) from error

    def _compile(
        self,
        draft_id: str,
        revision_id: str,
        split: str,
    ) -> StudioBenchmarkCompiledAuthoringAnalysis:
        """Delegate exact-revision compilation to the shared collaborator.

        Args:
            draft_id: Owning draft identity.
            revision_id: Exact current revision identity.
            split: Explicit Package split.

        Raises:
            StudioBenchmarkAuthoringCapacityError: Closure exceeds bounds.
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringStorageError: Staging fails.

        Returns:
            Shared internal compiled analysis facts.
        """
        return self._compiler.compile(draft_id, revision_id, split)

    def _assert_still_current(self, draft_id: str, revision_id: str) -> None:
        """Delegate the late current-pointer check to the collaborator.

        Args:
            draft_id: Owning draft identity.
            revision_id: Revision whose result would be returned.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Pointer changed.

        Returns:
            None.
        """
        self._compiler.assert_still_current(draft_id, revision_id)

    def validate(
        self,
        draft_id: str,
        request: StudioBenchmarkAuthoringValidationRequestV1,
    ) -> StudioBenchmarkAuthoringValidationResultV1:
        """Validate one exact current draft revision side-effect free.

        Args:
            draft_id: Owning authoring draft identity.
            request: Exact revision and explicit split request.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringCapacityError: Analysis exceeds a bound.
            StudioBenchmarkAuthoringStorageError: Staging/integrity fails.

        Returns:
            Field-addressable validation facts and independently gated IDs.
        """
        analysis = self._compile(draft_id, request.revision_id, request.split)
        result = StudioBenchmarkAuthoringValidationResultV1(
            draft_id=draft_id,
            revision_id=analysis.revision.revision_id,
            document_fingerprint=analysis.revision.document_fingerprint,
            split=request.split,
            valid=analysis.valid,
            identities=analysis.identities,
            diagnostics=analysis.diagnostics,
            diagnostics_truncated=analysis.diagnostics_truncated,
            unverified_checks=analysis.unverified_checks,
        )
        self._assert_still_current(draft_id, request.revision_id)
        return result

    def dry_run(
        self,
        draft_id: str,
        request: StudioBenchmarkAuthoringDryRunRequestV1,
    ) -> StudioBenchmarkAuthoringDryRunResultV1:
        """Build a complete bounded definition-only schedule for a revision.

        Args:
            draft_id: Owning authoring draft identity.
            request: Exact split, task selection, and Agent revisions.

        Raises:
            StudioBenchmarkAuthoringRevisionConflictError: Revision is stale.
            StudioBenchmarkAuthoringCapacityError: Schedule exceeds 10,000 rows.
            StudioBenchmarkAuthoringStorageError: Staging/integrity fails.

        Returns:
            Complete schedule or an empty diagnostic-only failed projection.
        """
        analysis = self._compile(draft_id, request.revision_id, request.split)
        diagnostics = list(analysis.diagnostics)
        verified: list[StudioBenchmarkVerifiedAgentRevisionV1] = []
        graph_identities: dict[str, str] = {}
        if analysis.valid:
            for selection in request.agent_revisions:
                try:
                    snapshot = verify_immutable_agent_revision(
                        self._agents,
                        selection.agent_id,
                        selection.revision_id,
                        contract_catalog=self._contract_catalog,
                    )
                except AgentRevisionNotFoundError:
                    diagnostics.append(
                        _agent_diagnostic(
                            agent_id=selection.agent_id,
                            revision_id=selection.revision_id,
                            code="benchmark.authoring.agent_revision_not_found",
                            message="Selected Agent revision was not found.",
                        )
                    )
                except StudioRunValidationError as error:
                    diagnostics.append(
                        _agent_diagnostic(
                            agent_id=selection.agent_id,
                            revision_id=selection.revision_id,
                            code=f"benchmark.authoring.{error.code}",
                            message="Selected Agent revision is not valid.",
                        )
                    )
                else:
                    verified.append(
                        StudioBenchmarkVerifiedAgentRevisionV1(
                            agent_id=selection.agent_id,
                            revision_id=selection.revision_id,
                            agent_graph_identity=snapshot.canonical_hash,
                        )
                    )
                    graph_identities[selection.agent_id] = snapshot.canonical_hash

        ordered_diagnostics = tuple(
            sorted(
                diagnostics,
                key=lambda item: (
                    item.severity,
                    item.member_kind,
                    item.member_path or "",
                    tuple(str(value) for value in item.field_path),
                    item.code,
                    item.agent_id or "",
                ),
            )
        )
        diagnostics_truncated = (
            analysis.diagnostics_truncated or len(ordered_diagnostics) > 100
        )
        ordered_diagnostics = ordered_diagnostics[:100]
        if (
            not analysis.valid
            or len(verified) != len(request.agent_revisions)
            or analysis.plan is None
            or analysis.protocol is None
        ):
            result = StudioBenchmarkAuthoringDryRunResultV1(
                draft_id=draft_id,
                revision_id=analysis.revision.revision_id,
                document_fingerprint=analysis.revision.document_fingerprint,
                split=request.split,
                ok=False,
                identities=analysis.identities,
                agent_revisions=tuple(verified),
                unverified_checks=analysis.unverified_checks,
                diagnostics=ordered_diagnostics,
                diagnostics_truncated=diagnostics_truncated,
            )
            self._assert_still_current(draft_id, request.revision_id)
            return result

        available = {task.id for task in analysis.plan.tasks}
        selected = request.task_ids or tuple(sorted(available))
        missing = sorted(set(selected) - available)
        if missing:
            task_diagnostic = StudioBenchmarkAuthoringDiagnosticV1(
                code="benchmark.dry_run.task_not_found",
                message="Requested Benchmark task does not exist.",
                member_kind="task",
                field_path=("taskIds",),
                task_id=missing[0],
            )
            result = StudioBenchmarkAuthoringDryRunResultV1(
                draft_id=draft_id,
                revision_id=analysis.revision.revision_id,
                document_fingerprint=analysis.revision.document_fingerprint,
                split=request.split,
                ok=False,
                identities=analysis.identities,
                agent_revisions=tuple(verified),
                unverified_checks=analysis.unverified_checks,
                diagnostics=(*ordered_diagnostics, task_diagnostic)[:100],
                diagnostics_truncated=diagnostics_truncated,
            )
            self._assert_still_current(draft_id, request.revision_id)
            return result

        cardinality = (
            len(selected) * len(graph_identities) * analysis.protocol.repeats
        )
        if cardinality > STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES:
            raise StudioBenchmarkAuthoringCapacityError(
                "benchmark.authoring.schedule_too_large",
                "Benchmark dry-run schedule exceeds its safe output limit",
            )
        projected = project_benchmark_dry_run(
            analysis.plan,
            analysis.protocol,
            graph_identities,
            task_ids=tuple(selected),
            max_schedule_entries=(
                STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES
            ),
        )
        unverified = set(analysis.unverified_checks)
        unverified.update(projected.unverified_checks)
        if (
            len(selected) > 1
            or len(graph_identities) > 1
            or analysis.protocol.repeats > 1
        ):
            unverified.add("current-worker-cardinality")
        result = StudioBenchmarkAuthoringDryRunResultV1(
            draft_id=draft_id,
            revision_id=analysis.revision.revision_id,
            document_fingerprint=analysis.revision.document_fingerprint,
            split=request.split,
            ok=projected.ok,
            identities=analysis.identities,
            agent_revisions=tuple(verified),
            schedule=tuple(
                StudioBenchmarkAuthoringScheduleEntryV1.model_validate(item)
                for item in projected.schedule
            ),
            budget=StudioBenchmarkAuthoringBudgetV1.model_validate(
                projected.budget
            ),
            fairness_warnings=tuple(projected.warnings),
            output_layout=StudioBenchmarkAuthoringOutputLayoutV1.model_validate(
                projected.output_layout
            ),
            unverified_checks=tuple(sorted(unverified)),
            diagnostics=ordered_diagnostics,
            diagnostics_truncated=diagnostics_truncated,
        )
        self._assert_still_current(draft_id, request.revision_id)
        return result


StudioBenchmarkAuthoringAnalysisService = (
    StudioBenchmarkValidationDryRunApplicationService
)


__all__ = [
    "StudioBenchmarkAuthoringAnalysisService",
    "StudioBenchmarkAuthoringRevisionCompiler",
    "StudioBenchmarkCompiledAuthoringAnalysis",
    "StudioBenchmarkValidationDryRunApplicationService",
]
