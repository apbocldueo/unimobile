"""Process-scoped dependency composition for Studio Benchmark definition tools."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

from zhixing.benchmark.authoring import studio_fixture_profile_registry

from .catalog import StudioComponentCatalog

from .benchmark_authoring_import import (
    StudioBenchmarkAuthoringPackageAdapter,
)
from .benchmark_authoring_content import (
    StudioBenchmarkAuthoringContentApplicationService,
)
from .benchmark_authoring_analysis import (
    StudioBenchmarkAuthoringAnalysisService,
    StudioBenchmarkAuthoringRevisionCompiler,
)
from .benchmark_authoring_contracts import (
    StudioBenchmarkContractTestApplicationService,
)
from .benchmark_authoring_freeze import StudioBenchmarkFrozenClosureBuilder
from .benchmark_authoring_freeze_service import (
    StudioBenchmarkValidatedFreezeAnalyzer,
    StudioBenchmarkValidatedFreezeApplicationService,
)
from .benchmark_authoring_materializer import (
    StudioBenchmarkAuthoringPackageMaterializer,
)
from .benchmark_authoring_migration import (
    StudioBenchmarkLegacyMigrationApplicationService,
)
from .benchmark_authoring_repository import (
    SQLiteStudioBenchmarkAuthoringRepository,
)
from .benchmark_authoring_service import (
    StudioBenchmarkAuthoringApplicationService,
)
from .benchmark_authoring_storage import (
    LocalStudioBenchmarkManagedContent,
    default_studio_benchmark_authoring_root,
)
from .benchmark_authoring_release_service import (
    StudioBenchmarkPackageReleaseApplicationService,
)
from .benchmark_authoring_release_storage import (
    LocalStudioBenchmarkPackageReleaseStore,
    StudioBenchmarkFrozenClosureReader,
    default_studio_benchmark_release_root,
)
from .benchmark_service import (
    StudioBenchmarkApplicationService,
    StudioBenchmarkCatalogService,
    StudioBenchmarkCatalogSnapshotOwner,
    StudioBenchmarkSource,
    default_studio_benchmark_sources,
)
from .benchmark_events import (
    BenchmarkEventNotifier,
    DurableBenchmarkEventService,
)
from .benchmark_experiment_repository import (
    SQLiteStudioBenchmarkExperimentRepository,
)
from .benchmark_experiment_service import (
    StudioBenchmarkExperimentApplicationService,
)
from .benchmark_evidence import LocalStudioBenchmarkEvidenceStore
from .benchmark_artifacts import (
    CoreStudioBenchmarkBundleVerifier,
    LocalStudioBenchmarkManagedArtifactStore,
)
from .benchmark_execution import (
    ActiveBenchmarkExperimentRegistry,
    LocalBenchmarkExperimentScheduler,
    StudioBenchmarkExecutionAdapter,
    StudioBenchmarkExperimentOrchestrator,
    new_benchmark_process_owner_id,
)
from .benchmark_publication import (
    CoreStudioBenchmarkPublicationPreparer,
    DurableStudioBenchmarkPublisher,
)
from .benchmark_publication_repository import (
    SQLiteStudioBenchmarkPublicationRepository,
)
from .benchmark_recovery import (
    LocalBenchmarkRecoveryOwnership,
    StudioBenchmarkStartupRecovery,
)
from .benchmark_experiment_models import StudioBenchmarkRecoverySummaryV1
from .benchmark_experiment_protocols import StudioBenchmarkRecoveryOwnership
from .benchmark_replay import NativeStudioBenchmarkReplayPublisher
from .replay_storage import default_studio_artifact_directory
from .repository import AgentDocumentRepository
from .run_execution import (
    AndroidDeviceProfileResolver,
    DeviceLeaseRegistry,
    ProductionComponentResolverFactory,
)


@dataclass(frozen=True)
class StudioBenchmarkComposition:
    """Shared Benchmark definition, resource, execution, and worker ownership."""

    service: StudioBenchmarkApplicationService
    catalog: StudioBenchmarkCatalogSnapshotOwner
    profiles: AndroidDeviceProfileResolver
    authoring: StudioBenchmarkAuthoringApplicationService | None = None
    authoring_content_service: (
        StudioBenchmarkAuthoringContentApplicationService | None
    ) = None
    authoring_analysis: StudioBenchmarkAuthoringAnalysisService | None = None
    authoring_contract_tests: (
        StudioBenchmarkContractTestApplicationService | None
    ) = None
    authoring_freeze: (
        StudioBenchmarkValidatedFreezeApplicationService | None
    ) = None
    authoring_release: (
        StudioBenchmarkPackageReleaseApplicationService | None
    ) = None
    authoring_release_storage: (
        LocalStudioBenchmarkPackageReleaseStore | None
    ) = None
    authoring_migration: (
        StudioBenchmarkLegacyMigrationApplicationService | None
    ) = None
    authoring_repository: (
        SQLiteStudioBenchmarkAuthoringRepository | None
    ) = None
    authoring_content: LocalStudioBenchmarkManagedContent | None = None
    experiments: StudioBenchmarkExperimentApplicationService | None = None
    events: DurableBenchmarkEventService | None = None
    repository: SQLiteStudioBenchmarkExperimentRepository | None = None
    evidence: LocalStudioBenchmarkEvidenceStore | None = None
    publications: SQLiteStudioBenchmarkPublicationRepository | None = None
    artifacts: LocalStudioBenchmarkManagedArtifactStore | None = None
    publisher: DurableStudioBenchmarkPublisher | None = None
    execution: StudioBenchmarkExecutionAdapter | None = None
    orchestrator: StudioBenchmarkExperimentOrchestrator | None = None
    scheduler: LocalBenchmarkExperimentScheduler | None = None
    recovery: StudioBenchmarkStartupRecovery | None = None
    recovery_summary: StudioBenchmarkRecoverySummaryV1 | None = None
    recovery_ownership: StudioBenchmarkRecoveryOwnership | None = None

    def shutdown(self, *, wait: bool = True) -> None:
        """Release the process-local worker without deleting durable facts.

        Args:
            wait: Whether to wait for an active cooperative execution.

        Raises:
            None.

        Returns:
            None.
        """
        try:
            if self.scheduler is not None:
                self.scheduler.shutdown(wait=wait)
        finally:
            try:
                if self.events is not None:
                    self.events.shutdown()
            finally:
                if self.recovery_ownership is not None:
                    self.recovery_ownership.close()


def build_default_studio_benchmark_composition(
    workspace: str | Path,
    *,
    agents: AgentDocumentRepository,
    profiles: AndroidDeviceProfileResolver,
    contract_catalog: Any | None = None,
    component_catalog: StudioComponentCatalog | None = None,
    sources: Iterable[StudioBenchmarkSource] | None = None,
    package_dirs: Sequence[str | Path] = (),
    catalog_roots: Sequence[str | Path] = (),
    include_installed: bool = True,
    database_path: str | Path | None = None,
    leases: DeviceLeaseRegistry | None = None,
    component_resolvers: ProductionComponentResolverFactory | None = None,
) -> StudioBenchmarkComposition:
    """Build one process-level Catalog snapshot and pure preview service.

    Args:
        workspace: Explicit Studio workspace root.
        agents: Immutable Agent revision repository.
        profiles: Shared safe profile directory/runtime resolver.
        contract_catalog: Optional extension NodeContract catalog.
        component_catalog: Exact safe Agent Component Catalog.
        sources: Optional complete typed source override.
        package_dirs: Additional explicit Package directories.
        catalog_roots: Additional explicit Catalog roots.
        include_installed: Whether installed Package metadata is discoverable.
        database_path: Optional Studio database enabling Stage 5.2A resources.
        leases: Optional process-scoped exact-target lease shared with Run.
        component_resolvers: Optional explicit production resolver factory for
            deterministic composition tests; omitted uses the standard
            framework-owned built-in resolver without secret dependencies.

    Raises:
        BenchmarkDefinitionError: An explicit source is invalid.
        OSError: Workspace/source paths cannot be resolved.
        ValueError: Source identities collide.

    Returns:
        Ready immutable Benchmark definition composition.
    """
    if sources is None:
        selected = list(
            default_studio_benchmark_sources(
                workspace,
                include_installed=include_installed,
            )
        )
        selected.extend(
            StudioBenchmarkSource(
                source_id=f"configured-package-{index + 1}",
                kind="package",
                locator=Path(value),
            )
            for index, value in enumerate(package_dirs)
        )
        selected.extend(
            StudioBenchmarkSource(
                source_id=f"configured-catalog-{index + 1}",
                kind="catalog_root",
                locator=Path(value),
            )
            for index, value in enumerate(catalog_roots)
        )
        selected_sources = tuple(selected)
    else:
        selected_sources = tuple(sources)
    catalog = StudioBenchmarkCatalogSnapshotOwner(
        StudioBenchmarkCatalogService(selected_sources)
    )
    service = StudioBenchmarkApplicationService(
        catalog=catalog,
        agents=agents,
        profiles=profiles,
        contract_catalog=contract_catalog,
        component_catalog=component_catalog,
    )
    repository = None
    evidence = None
    execution = None
    orchestrator = None
    scheduler = None
    experiments = None
    events = None
    publications = None
    managed_artifacts = None
    publisher = None
    recovery = None
    recovery_summary = None
    recovery_ownership = None
    authoring = None
    authoring_content_service = None
    authoring_repository = None
    authoring_content = None
    authoring_analysis = None
    authoring_contract_tests = None
    authoring_freeze = None
    authoring_release = None
    authoring_release_storage = None
    authoring_migration = None
    if database_path is not None:
        database = Path(database_path).expanduser().resolve()
        authoring_repository = SQLiteStudioBenchmarkAuthoringRepository(
            database
        )
        authoring_content = LocalStudioBenchmarkManagedContent(
            default_studio_benchmark_authoring_root(database)
        )
        authoring = StudioBenchmarkAuthoringApplicationService(
            repository=authoring_repository,
            packages=StudioBenchmarkAuthoringPackageAdapter(
                authoring_content,
                staging_root=authoring_content.staging_root,
            ),
            catalog=catalog,
        )
        authoring_migration = StudioBenchmarkLegacyMigrationApplicationService(
            repository=authoring_repository
        )
        authoring_content_service = (
            StudioBenchmarkAuthoringContentApplicationService(
                repository=authoring_repository,
                content=authoring_content,
            )
        )
        authoring_materializer = StudioBenchmarkAuthoringPackageMaterializer(
            authoring_content,
            staging_root=authoring_content.staging_root / "analysis",
        )
        authoring_compiler = StudioBenchmarkAuthoringRevisionCompiler(
            repository=authoring_repository,
            materializer=authoring_materializer,
            agents=agents,
            contract_catalog=contract_catalog,
        )
        authoring_analysis = StudioBenchmarkAuthoringAnalysisService(
            repository=authoring_repository,
            materializer=authoring_materializer,
            agents=agents,
            contract_catalog=contract_catalog,
            compiler=authoring_compiler,
        )
        authoring_contract_tests = StudioBenchmarkContractTestApplicationService(
            compiler=authoring_compiler,
            profiles=studio_fixture_profile_registry(),
        )
        authoring_freeze = StudioBenchmarkValidatedFreezeApplicationService(
            repository=authoring_repository,
            analyzer=StudioBenchmarkValidatedFreezeAnalyzer(
                authoring_compiler
            ),
            closure_builder=StudioBenchmarkFrozenClosureBuilder(
                authoring_content
            ),
        )
        authoring_release_storage = LocalStudioBenchmarkPackageReleaseStore(
            default_studio_benchmark_release_root(database)
        )
        authoring_release = StudioBenchmarkPackageReleaseApplicationService(
            repository=authoring_repository,
            frozen_reader=StudioBenchmarkFrozenClosureReader(
                authoring_content
            ),
            storage=authoring_release_storage,
            catalog=catalog,
        )
        # Durable publications must be verified and visible before this
        # composition can be returned to any HTTP request handler.
        authoring_release.recover_publications()
        notifier = BenchmarkEventNotifier()
        repository = SQLiteStudioBenchmarkExperimentRepository(
            database,
            event_commit_hook=notifier.notify,
        )
        events = DurableBenchmarkEventService(
            repository,
            notifier=notifier,
        )
        evidence = LocalStudioBenchmarkEvidenceStore(
            database.parent / f".{database.stem}-benchmark-evidence"
        )
        publications = SQLiteStudioBenchmarkPublicationRepository(
            database,
            event_commit_hook=notifier.notify,
        )
        preparer = CoreStudioBenchmarkPublicationPreparer(evidence)
        managed_artifacts = LocalStudioBenchmarkManagedArtifactStore(
            default_studio_artifact_directory(database),
            publications,
        )
        replay_publisher = NativeStudioBenchmarkReplayPublisher(
            repository,
            managed_artifacts,
        )
        publisher = DurableStudioBenchmarkPublisher(
            experiments=repository,
            publications=publications,
            preparer=preparer,
            artifacts=managed_artifacts,
            bundles=CoreStudioBenchmarkBundleVerifier(),
            replay=replay_publisher,
        )
        process_owner_id = new_benchmark_process_owner_id()
        try:
            recovery_ownership = LocalBenchmarkRecoveryOwnership.acquire(
                database
            )
            recovery = StudioBenchmarkStartupRecovery(
                repository=repository,
                process_owner_id=process_owner_id,
                publisher=publisher,
            )
            recovery_summary = recovery.recover()
            active = ActiveBenchmarkExperimentRegistry()
            execution = StudioBenchmarkExecutionAdapter(
                definitions=service,
                components=(
                    component_resolvers
                    or ProductionComponentResolverFactory()
                ),
                evidence=evidence,
                profiles=profiles,
                leases=leases,
                publication_preparer=preparer,
            )
            orchestrator = StudioBenchmarkExperimentOrchestrator(
                repository=repository,
                execution=execution,
                process_owner_id=process_owner_id,
                active=active,
                publisher=publisher,
            )
            scheduler = LocalBenchmarkExperimentScheduler(
                repository=repository,
                orchestrator=orchestrator,
                process_owner_id=process_owner_id,
            )
            if recovery_summary.requeued:
                scheduler.wake()

            def dispatch(experiment_id: str, created: bool) -> None:
                """Enroll new work or re-wake an accepted local retry.

                Args:
                    experiment_id: Durable Experiment identity.
                    created: Whether create inserted this aggregate.

                Raises:
                    RuntimeError: Scheduler is already closed.

                Returns:
                    None.
                """
                eligible = False
                if created:
                    eligible = repository.enroll_accepted_experiment(
                        experiment_id,
                        process_owner_id=process_owner_id,
                    )
                else:
                    current = repository.get_experiment(experiment_id)
                    eligible = bool(
                        current.lifecycle.value == "accepted"
                        and current.process_owner_id == process_owner_id
                    )
                if eligible:
                    scheduler.wake()

            experiments = StudioBenchmarkExperimentApplicationService(
                definitions=service,
                repository=repository,
                publication_repository=publications,
                dispatch=dispatch,
                cancel_active=orchestrator.cancel_active,
                execution_enabled=True,
                event_transport_enabled=True,
                publication_enabled=True,
            )
        except Exception:
            try:
                if scheduler is not None:
                    scheduler.shutdown(wait=True)
            finally:
                try:
                    if events is not None:
                        events.shutdown()
                finally:
                    if recovery_ownership is not None:
                        recovery_ownership.close()
            raise
    return StudioBenchmarkComposition(
        service=service,
        experiments=experiments,
        events=events,
        catalog=catalog,
        profiles=profiles,
        authoring=authoring,
        authoring_content_service=authoring_content_service,
        authoring_repository=authoring_repository,
        authoring_content=authoring_content,
        authoring_analysis=authoring_analysis,
        authoring_contract_tests=authoring_contract_tests,
        authoring_freeze=authoring_freeze,
        authoring_release=authoring_release,
        authoring_release_storage=authoring_release_storage,
        authoring_migration=authoring_migration,
        repository=repository,
        evidence=evidence,
        publications=publications,
        artifacts=managed_artifacts,
        publisher=publisher,
        execution=execution,
        orchestrator=orchestrator,
        scheduler=scheduler,
        recovery=recovery,
        recovery_summary=recovery_summary,
        recovery_ownership=recovery_ownership,
    )


__all__ = [
    "StudioBenchmarkComposition",
    "build_default_studio_benchmark_composition",
]
