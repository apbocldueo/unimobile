"""Process-scoped dependency composition for the local Studio Run service."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .repository import AgentDocumentRepository
from .replay_service import ReplayApplicationService
from .run_artifacts import (
    LocalStudioRunArtifactStore,
    RuntimeArtifactEventAdapter,
    default_studio_run_artifact_directory,
)
from .run_debug import StudioRunDebugCapture
from .run_events import DurableRunEventService
from .run_execution import (
    AndroidDeviceProfileResolver,
    AndroidStudioRunExecutionAdapter,
    DeviceLeaseRegistry,
    LocalThreadRunScheduler,
    ProductionComponentResolverFactory,
    StudioRunOrchestrator,
    new_process_owner_id,
)
from .run_replay import NativeStudioRunReplayFinalizer
from .run_repository import SQLiteStudioRunRepository
from .run_service import StudioRunApplicationService
from .catalog import StudioComponentCatalog
from .readiness import StudioRuntimeReadinessService


@dataclass
class StudioRunComposition:
    """Shared process-scoped Run dependencies owned by the HTTP server."""

    service: StudioRunApplicationService
    artifacts: LocalStudioRunArtifactStore
    events: DurableRunEventService
    orchestrator: StudioRunOrchestrator
    scheduler: LocalThreadRunScheduler
    readiness: StudioRuntimeReadinessService
    recovered_run_ids: tuple[str, ...] = ()

    def shutdown(self, *, wait: bool = True) -> None:
        """Stop accepting Run work and release worker resources.

        Args:
            wait (bool): Whether to wait for the active local worker.

        Raises:
            None.

        Returns:
            None.
        """
        self.scheduler.shutdown(wait=wait)


def build_default_studio_run_composition(
    database_path: str | Path,
    *,
    agents: AgentDocumentRepository,
    replay_service: ReplayApplicationService,
    contract_catalog: Any | None = None,
    profiles: AndroidDeviceProfileResolver | None = None,
    components: ProductionComponentResolverFactory | None = None,
    component_catalog: StudioComponentCatalog | None = None,
    runtime_secrets: Mapping[str, Any] | None = None,
    enforce_readiness: bool | None = None,
    leases: DeviceLeaseRegistry | None = None,
    max_workers: int = 1,
) -> StudioRunComposition:
    """Build one shared SQLite/local-artifact/Android Run composition.

    Args:
        database_path (str | Path): Workspace-isolated Studio database.
        agents (AgentDocumentRepository): Saved Agent revision source.
        replay_service (ReplayApplicationService): Shared Stage 2 Replay service.
        contract_catalog (Any | None): Optional extension NodeContract catalog.
        profiles (AndroidDeviceProfileResolver | None): Explicit device profiles.
        components (ProductionComponentResolverFactory | None): Resolver factory.
        component_catalog: Exact safe Component Catalog used by readiness.
        runtime_secrets: Process-scoped SecretRef values used for presence checks.
        enforce_readiness: Optional new-Run gate override; production resolver
            factories enable it by default while test-specific factories do not.
        leases (DeviceLeaseRegistry | None): Shared exact-target lease registry.
        max_workers (int): Bounded local worker count; defaults to one.

    Raises:
        OSError: Managed storage cannot be created.
        sqlite3.Error: Database migration or recovery fails.
        StudioRunError: Interrupted Run recovery cannot be finalized.

    Returns:
        StudioRunComposition: Ready process-scoped service dependencies.
    """
    repository = SQLiteStudioRunRepository(database_path)
    artifact_store = LocalStudioRunArtifactStore(
        default_studio_run_artifact_directory(database_path),
        repository,
    )
    artifact_events = RuntimeArtifactEventAdapter(artifact_store)
    events = DurableRunEventService(
        repository,
        runtime_draft_builder=artifact_events.build,
    )
    debug = StudioRunDebugCapture(artifacts=artifact_store, events=events)
    selected_components = components or ProductionComponentResolverFactory()
    selected_profiles = profiles or AndroidDeviceProfileResolver()
    if component_catalog is None:
        from .catalog import build_studio_component_catalog

        component_catalog = build_studio_component_catalog()
    readiness = StudioRuntimeReadinessService(
        agents=agents,
        catalog=component_catalog,
        components=selected_components,
        profiles=selected_profiles,
        secrets=runtime_secrets,
        contract_catalog=contract_catalog,
    )
    should_enforce_readiness = (
        isinstance(selected_components, ProductionComponentResolverFactory)
        if enforce_readiness is None
        else enforce_readiness
    )
    execution = AndroidStudioRunExecutionAdapter(
        components=selected_components,
        artifacts=artifact_store,
        profiles=selected_profiles,
        leases=leases,
        contract_catalog=contract_catalog,
        component_catalog=component_catalog,
        warning_sink=repository.set_storage_warnings,
    )
    finalizer = NativeStudioRunReplayFinalizer(
        runs=repository,
        events=repository,
        artifacts=repository,
        live_store=artifact_store,
        replay_store=replay_service.artifact_store,
    )
    owner = new_process_owner_id()
    orchestrator = StudioRunOrchestrator(
        runs=repository,
        events=events,
        execution=execution,
        debug=debug,
        process_owner_id=owner,
        replay=finalizer,
    )
    scheduler = LocalThreadRunScheduler(max_workers=max_workers)
    service = StudioRunApplicationService(
        agents=agents,
        runs=repository,
        events=events,
        process_owner_id=owner,
        contract_catalog=contract_catalog,
        component_catalog=component_catalog,
        scheduler=scheduler,
        execute=orchestrator.execute,
        cancel_active=orchestrator.cancel_active,
        schedule_rejected=orchestrator.reject_scheduling,
        readiness=readiness if should_enforce_readiness else None,
    )
    recovered = orchestrator.recover_interrupted()
    return StudioRunComposition(
        service=service,
        artifacts=artifact_store,
        events=events,
        orchestrator=orchestrator,
        scheduler=scheduler,
        readiness=readiness,
        recovered_run_ids=recovered,
    )


__all__ = [
    "StudioRunComposition",
    "build_default_studio_run_composition",
]
