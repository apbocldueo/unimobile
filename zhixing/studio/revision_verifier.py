"""Shared immutable Agent revision verification for Studio execution surfaces."""

from __future__ import annotations

from typing import Any

from zhixing.graph import AgentGraph

from .catalog import StudioComponentCatalog, build_studio_component_catalog
from .eligibility import evaluate_revision_eligibility
from .repository import AgentDocumentRepository, AgentRevisionNotFoundError
from .run_errors import StudioRunValidationError
from .run_models import RunSnapshotV1


def verify_immutable_agent_revision(
    agents: AgentDocumentRepository,
    agent_id: str,
    revision_id: str,
    *,
    contract_catalog: Any | None = None,
    component_catalog: StudioComponentCatalog | None = None,
) -> RunSnapshotV1:
    """Load and re-verify one valid immutable Agent revision.

    Args:
        agents: Immutable Agent revision repository.
        agent_id: Selected stable Agent identity.
        revision_id: Selected immutable revision identity.
        contract_catalog: Optional extension NodeContract catalog.
        component_catalog: Exact safe Component Catalog; omitted uses the
            deterministic built-in Catalog.

    Raises:
        AgentRevisionNotFoundError: Revision is absent.
        StudioRunValidationError: Compile evidence or graph identity is invalid.

    Returns:
        Self-contained immutable verified revision snapshot.
    """
    revision = agents.get_revision(agent_id, revision_id)
    compile_snapshot = revision.compile_snapshot
    if revision.agent_id != agent_id:
        raise StudioRunValidationError(
            "studio.run.revision_agent_mismatch",
            "Revision belongs to a different Agent",
        )
    selected_catalog = component_catalog or build_studio_component_catalog()
    eligibility = evaluate_revision_eligibility(
        revision,
        catalog=selected_catalog,
        contract_catalog=contract_catalog,
    )
    if not eligibility.current_policy_eligible:
        issue = eligibility.diagnostics[0]
        raise StudioRunValidationError(issue.code, issue.message)
    assert compile_snapshot.agent_graph is not None
    assert compile_snapshot.canonical_hash is not None
    graph = AgentGraph.model_validate(compile_snapshot.agent_graph)
    actual_hash = graph.canonical_hash(contract_catalog=contract_catalog)
    return RunSnapshotV1(
        agent_id=revision.agent_id,
        revision_id=revision.revision_id,
        contract_version=graph.contract_version,
        canonical_hash=actual_hash,
        agent_graph=graph.model_dump(mode="json", exclude_none=True),
        presentation=revision.document.presentation.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
        source_map=tuple(
            item.model_dump(mode="json", exclude_none=True)
            for item in compile_snapshot.source_map
        ),
        authoring_policy=compile_snapshot.authoring_policy,
        lowering_profile=compile_snapshot.lowering_profile,
        capability_hash=compile_snapshot.capability_hash,
        capability_document=revision.document.to_json_dict(),
        projection_map=compile_snapshot.projection_map,
    )


__all__ = ["verify_immutable_agent_revision"]
