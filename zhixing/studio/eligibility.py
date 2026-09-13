"""Pure current-policy eligibility checks for immutable Studio Agent revisions."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from zhixing.graph import AgentGraph, compile_studio_flow_document

from .catalog import StudioComponentCatalog
from .models import (
    STUDIO_CAPABILITY_AUTHORING_POLICY,
    STUDIO_CAPABILITY_LOWERING_PROFILE,
    StudioCapabilityDocument,
    StudioModel,
    StudioProjectionEntry,
    parse_studio_authoring_document,
)
from .repository import AgentRevisionRecord
from .run_models import RunSnapshotV1


class StudioEligibilityDiagnostic(StudioModel):
    """Bounded stable current-policy eligibility diagnostic."""

    code: str
    message: str = Field(max_length=500)
    path: tuple[str | int, ...] = ()
    remediation_key: str


class StudioRevisionEligibility(StudioModel):
    """Separate historical, graph, policy, and environment eligibility facts."""

    graph_valid: bool
    history_readable: bool = True
    current_policy_eligible: bool
    environment_ready: bool | None = None
    diagnostics: tuple[StudioEligibilityDiagnostic, ...] = ()


def _issue(
    code: str,
    message: str,
    remediation_key: str,
    *path: str | int,
) -> StudioEligibilityDiagnostic:
    """Build one bounded deterministic eligibility diagnostic.

    Args:
        code: Stable machine-readable code.
        message: Safe human-readable explanation.
        remediation_key: Stable remediation action identity.
        path: Optional exact document/snapshot property path.

    Raises:
        ValueError: Diagnostic fields violate their strict bounds.

    Returns:
        Strict eligibility diagnostic.
    """
    return StudioEligibilityDiagnostic(
        code=code,
        message=message,
        path=tuple(path),
        remediation_key=remediation_key,
    )


def _projection_diagnostics(
    graph: AgentGraph,
    projection_map: tuple[StudioProjectionEntry, ...],
) -> tuple[StudioEligibilityDiagnostic, ...]:
    """Validate complete one-to-one generated graph projection coverage.

    Args:
        graph: Revalidated exact AgentGraph.
        projection_map: Persisted generated-to-capability mapping.

    Raises:
        None.

    Returns:
        Stable projection-integrity diagnostics.
    """
    issues: list[StudioEligibilityDiagnostic] = []
    keys = [(item.graph_kind, item.graph_id) for item in projection_map]
    if len(keys) != len(set(keys)):
        issues.append(
            _issue(
                "studio.policy.projection_duplicate",
                "Capability projection contains duplicate graph identities",
                "rebuild-from-current-capability-template",
                "projectionMap",
            )
        )
    expected_nodes = {node.id for node in graph.nodes}
    mapped_nodes = {
        item.graph_id for item in projection_map if item.graph_kind == "node"
    }
    if mapped_nodes != expected_nodes:
        issues.append(
            _issue(
                "studio.policy.projection_node_mismatch",
                "Capability projection does not cover the exact AgentGraph nodes",
                "rebuild-from-current-capability-template",
                "projectionMap",
            )
        )
    expected_edges = {f"edge.{index:04d}" for index, _ in enumerate(graph.edges)}
    mapped_edges = {
        item.graph_id for item in projection_map if item.graph_kind == "edge"
    }
    if mapped_edges != expected_edges:
        issues.append(
            _issue(
                "studio.policy.projection_edge_mismatch",
                "Capability projection does not cover the exact AgentGraph edges",
                "rebuild-from-current-capability-template",
                "projectionMap",
            )
        )
    return tuple(issues)


def _catalog_diagnostics(
    document: StudioCapabilityDocument,
    catalog: StudioComponentCatalog,
) -> tuple[StudioEligibilityDiagnostic, ...]:
    """Revalidate exact capability placement and family closure in the Catalog.

    Args:
        document: Immutable schema-3 capability document.
        catalog: Current exact safe Component Catalog.

    Raises:
        None.

    Returns:
        Stable placement and availability diagnostics.
    """
    descriptors = {
        (item.namespace, item.name, item.version): item
        for item in catalog.components
    }
    issues: list[StudioEligibilityDiagnostic] = []
    for node_index, node in enumerate(document.capabilities):
        for candidate_index, candidate in enumerate(node.implementation.candidates):
            descriptor = descriptors.get(
                (candidate.namespace, candidate.name, candidate.version)
            )
            path = (
                "capabilities",
                node_index,
                "implementation",
                "candidates",
                candidate_index,
            )
            if descriptor is None:
                issues.append(
                    _issue(
                        "studio.policy.catalog_component_missing",
                        "Selected capability implementation is absent from the current Catalog",
                        "choose-eligible-capability-implementation",
                        *path,
                    )
                )
            elif (
                descriptor.placement != "agent_capability"
                or descriptor.capability_family != node.family
                or not descriptor.availability.available
            ):
                issues.append(
                    _issue(
                        "studio.policy.catalog_placement_ineligible",
                        "Selected Catalog entry is not currently eligible for this capability",
                        "choose-eligible-capability-implementation",
                        *path,
                    )
                )
    return tuple(issues)


def _lowering_closure_diagnostics(
    document: StudioCapabilityDocument,
    *,
    catalog: StudioComponentCatalog,
    canonical_hash: str | None,
    projection_map: tuple[StudioProjectionEntry, ...],
    contract_catalog: Any | None,
) -> tuple[StudioEligibilityDiagnostic, ...]:
    """Re-lower one immutable capability document and compare its identity closure.

    Args:
        document: Exact immutable schema-3 capability document.
        catalog: Current safe Component Catalog used for deterministic lowering.
        canonical_hash: Persisted lowered AgentGraph canonical identity.
        projection_map: Persisted runtime-to-authoring projection.
        contract_catalog: Optional explicit extension NodeContract catalog.

    Raises:
        None: Lowering failures and mismatches become diagnostics.

    Returns:
        Stable closure mismatch diagnostics.
    """
    selected_contracts = contract_catalog or catalog.node_contract_catalog()
    result = compile_studio_flow_document(
        document.to_json_dict(),
        component_catalog=catalog,
        contract_catalog=selected_contracts,
        expected_catalog_version=catalog.catalog_version,
    )
    if not result.is_success or result.graph is None:
        return (
            _issue(
                "studio.policy.lowering_no_longer_valid",
                "Capability document no longer lowers under the current Catalog",
                "rebuild-from-current-capability-template",
                "capabilityDocument",
            ),
        )
    lowered_hash = result.graph.canonical_hash(contract_catalog=selected_contracts)
    issues: list[StudioEligibilityDiagnostic] = []
    if lowered_hash != canonical_hash:
        issues.append(
            _issue(
                "studio.policy.lowered_graph_mismatch",
                "Persisted AgentGraph is not the deterministic lowering of this capability document",
                "rebuild-from-current-capability-template",
                "canonicalHash",
            )
        )
    expected_projection = tuple(getattr(result, "projection_map", ()))
    if expected_projection != projection_map:
        issues.append(
            _issue(
                "studio.policy.lowered_projection_mismatch",
                "Persisted projection is not the deterministic lowering projection",
                "rebuild-from-current-capability-template",
                "projectionMap",
            )
        )
    return tuple(issues)


def evaluate_revision_eligibility(
    revision: AgentRevisionRecord,
    *,
    catalog: StudioComponentCatalog,
    contract_catalog: Any | None = None,
) -> StudioRevisionEligibility:
    """Evaluate one exact immutable revision without crossing runtime boundaries.

    Args:
        revision: Exact immutable authoring revision and compile evidence.
        catalog: Current exact safe Component Catalog.
        contract_catalog: Optional explicit extension NodeContract catalog.

    Raises:
        None: Every incompatibility is returned as bounded diagnostics.

    Returns:
        Separate graph-valid, history-readable, policy, and environment facts.
    """
    snapshot = revision.compile_snapshot
    issues: list[StudioEligibilityDiagnostic] = []
    graph: AgentGraph | None = None
    graph_valid = False
    if snapshot.status != "valid" or snapshot.agent_graph is None or snapshot.canonical_hash is None:
        issues.append(
            _issue(
                "studio.policy.graph_invalid",
                "Revision does not contain valid immutable AgentGraph evidence",
                "save-valid-capability-revision",
                "compileSnapshot",
            )
        )
    else:
        try:
            graph = AgentGraph.model_validate(snapshot.agent_graph)
            graph_valid = (
                graph.canonical_hash(contract_catalog=contract_catalog)
                == snapshot.canonical_hash
            )
        except Exception:
            graph_valid = False
        if not graph_valid:
            issues.append(
                _issue(
                    "studio.policy.graph_identity_mismatch",
                    "Saved AgentGraph identity does not match the immutable revision",
                    "rebuild-from-current-capability-template",
                    "compileSnapshot",
                    "canonicalHash",
                )
            )
    if not isinstance(revision.document, StudioCapabilityDocument):
        issues.append(
            _issue(
                "studio.policy.legacy_revision_ineligible",
                "Legacy Studio revisions remain readable but cannot start new execution",
                "rebuild-from-current-capability-template",
                "document",
                "schemaVersion",
            )
        )
    else:
        document = revision.document
        if snapshot.authoring_policy != STUDIO_CAPABILITY_AUTHORING_POLICY:
            issues.append(
                _issue(
                    "studio.policy.authoring_policy_unsupported",
                    "Revision authoring policy is missing or unsupported",
                    "rebuild-from-current-capability-template",
                    "compileSnapshot",
                    "authoringPolicy",
                )
            )
        if snapshot.lowering_profile != STUDIO_CAPABILITY_LOWERING_PROFILE:
            issues.append(
                _issue(
                    "studio.policy.lowering_profile_unsupported",
                    "Revision lowering profile is missing or unsupported",
                    "rebuild-from-current-capability-template",
                    "compileSnapshot",
                    "loweringProfile",
                )
            )
        if snapshot.capability_hash != document.semantic_hash():
            issues.append(
                _issue(
                    "studio.policy.capability_identity_mismatch",
                    "Capability semantic identity does not match the immutable document",
                    "rebuild-from-current-capability-template",
                    "compileSnapshot",
                    "capabilityHash",
                )
            )
        issues.extend(_catalog_diagnostics(document, catalog))
        if graph is not None:
            issues.extend(_projection_diagnostics(graph, snapshot.projection_map))
        issues.extend(
            _lowering_closure_diagnostics(
                document,
                catalog=catalog,
                canonical_hash=snapshot.canonical_hash,
                projection_map=snapshot.projection_map,
                contract_catalog=contract_catalog,
            )
        )
    ordered = tuple(
        sorted(issues, key=lambda item: (item.code, tuple(map(str, item.path))))[:64]
    )
    return StudioRevisionEligibility(
        graph_valid=graph_valid,
        history_readable=True,
        current_policy_eligible=not ordered,
        environment_ready=None,
        diagnostics=ordered,
    )


def evaluate_run_snapshot_eligibility(
    snapshot: RunSnapshotV1,
    *,
    catalog: StudioComponentCatalog,
    contract_catalog: Any | None = None,
) -> StudioRevisionEligibility:
    """Re-evaluate an immutable Run/Experiment Agent snapshot before effects.

    Args:
        snapshot: Persisted self-contained Agent snapshot.
        catalog: Current exact safe Component Catalog.
        contract_catalog: Optional explicit extension NodeContract catalog.

    Raises:
        None: Tampering and policy drift become diagnostics.

    Returns:
        Current snapshot eligibility facts.
    """
    issues: list[StudioEligibilityDiagnostic] = []
    graph: AgentGraph | None = None
    graph_valid = False
    try:
        graph = AgentGraph.model_validate(snapshot.agent_graph)
        graph_valid = (
            graph.canonical_hash(contract_catalog=contract_catalog)
            == snapshot.canonical_hash
        )
    except Exception:
        graph_valid = False
    if not graph_valid:
        issues.append(
            _issue(
                "studio.policy.graph_identity_mismatch",
                "Agent snapshot graph identity is invalid",
                "do-not-retry-incompatible-snapshot",
                "canonicalHash",
            )
        )
    try:
        document = parse_studio_authoring_document(snapshot.capability_document)
    except Exception:
        document = None
        issues.append(
            _issue(
                "studio.policy.capability_document_missing",
                "Agent snapshot lacks a valid schema-3 capability document",
                "do-not-retry-incompatible-snapshot",
                "capabilityDocument",
            )
        )
    if not isinstance(document, StudioCapabilityDocument):
        issues.append(
            _issue(
                "studio.policy.legacy_snapshot_ineligible",
                "Legacy Agent snapshots cannot start new execution",
                "do-not-retry-incompatible-snapshot",
                "capabilityDocument",
            )
        )
    else:
        if snapshot.authoring_policy != STUDIO_CAPABILITY_AUTHORING_POLICY:
            issues.append(
                _issue(
                    "studio.policy.authoring_policy_unsupported",
                    "Agent snapshot authoring policy is unsupported",
                    "do-not-retry-incompatible-snapshot",
                    "authoringPolicy",
                )
            )
        if snapshot.lowering_profile != STUDIO_CAPABILITY_LOWERING_PROFILE:
            issues.append(
                _issue(
                    "studio.policy.lowering_profile_unsupported",
                    "Agent snapshot lowering profile is unsupported",
                    "do-not-retry-incompatible-snapshot",
                    "loweringProfile",
                )
            )
        if snapshot.capability_hash != document.semantic_hash():
            issues.append(
                _issue(
                    "studio.policy.capability_identity_mismatch",
                    "Agent snapshot capability identity is invalid",
                    "do-not-retry-incompatible-snapshot",
                    "capabilityHash",
                )
            )
        issues.extend(_catalog_diagnostics(document, catalog))
        if graph is not None:
            issues.extend(_projection_diagnostics(graph, snapshot.projection_map))
        issues.extend(
            _lowering_closure_diagnostics(
                document,
                catalog=catalog,
                canonical_hash=snapshot.canonical_hash,
                projection_map=snapshot.projection_map,
                contract_catalog=contract_catalog,
            )
        )
    ordered = tuple(
        sorted(issues, key=lambda item: (item.code, tuple(map(str, item.path))))[:64]
    )
    return StudioRevisionEligibility(
        graph_valid=graph_valid,
        history_readable=True,
        current_policy_eligible=not ordered,
        environment_ready=None,
        diagnostics=ordered,
    )


__all__ = [
    "StudioEligibilityDiagnostic",
    "StudioRevisionEligibility",
    "evaluate_revision_eligibility",
    "evaluate_run_snapshot_eligibility",
]
