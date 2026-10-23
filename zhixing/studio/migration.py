"""Pure migration from legacy Studio FlowDocument schema 1 to schema 2."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from pydantic import ValidationError

from zhixing.graph import (
    GraphDiagnostic,
    GraphRole,
    NodeLifecycle,
    contract_ref_for_role,
)
from zhixing.graph.compilers.common import diagnostics_from_validation_error

from .models import StudioFlowDocument, StudioModel


_ROLE_BY_LEGACY_TYPE = {
    "perception": GraphRole.PERCEPTION,
    "planner": GraphRole.PLANNER,
    "reasoning": GraphRole.REASONING,
    "memory": GraphRole.MEMORY,
    "action": GraphRole.ACTION_EXECUTOR,
    "action_executor": GraphRole.ACTION_EXECUTOR,
    "verifier": GraphRole.VERIFIER,
}
_LIFECYCLE_BY_ROLE = {
    GraphRole.PERCEPTION: NodeLifecycle.PER_STEP,
    GraphRole.PLANNER: NodeLifecycle.ON_RUN_START,
    GraphRole.REASONING: NodeLifecycle.PER_STEP,
    GraphRole.MEMORY: NodeLifecycle.STATEFUL,
    GraphRole.ACTION_EXECUTOR: NodeLifecycle.PER_STEP,
    GraphRole.VERIFIER: NodeLifecycle.POST_ACTION,
}
_LEGACY_PORT_MAP = {
    "out_task": "task",
    "out_observation": "observation",
    "in_task": "task",
    "in_shot": "observation",
    "out_perc": "perception",
    "out_plan": "plan",
    "in_plan": "plan",
    "in_perc": "perception",
    "in_mem": "memory",
    "out_mem": "context",
    "in_ctx": "write",
    "out_action": "action",
    "in_action": "action",
    "out_result": "result",
    "in_result": "result",
    "in_before": "before",
    "in_after": "after",
    "in_action_result": "action_result",
    "out_verified": "result",
    "in_cond": "value",
    "out_true": "true",
    "out_false": "false",
}
_UNSAFE_TYPES = {"verifiedPlan", "__wild__"}


class StudioMigrationResult(StudioModel):
    """Migration output containing either a schema 2 document or diagnostics."""

    document: StudioFlowDocument | None = None
    diagnostics: tuple[GraphDiagnostic, ...] = ()

    @property
    def is_success(self) -> bool:
        """Return whether migration produced a document without errors.

        Args:
            None.

        Raises:
            None.

        Returns:
            bool: True when a schema 2 document is available.
        """
        return self.document is not None

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize migration output without the original mutable input.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Safe API representation.
        """
        return {
            "isSuccess": self.is_success,
            "document": self.document.to_json_dict() if self.document else None,
            "diagnostics": [item.to_safe_dict() for item in self.diagnostics],
        }


def _diagnostic(
    code: str,
    message: str,
    *,
    path: tuple[str | int, ...] = (),
    source_id: str,
) -> GraphDiagnostic:
    """Build one deterministic migration diagnostic.

    Args:
        code (str): Stable diagnostic code.
        message (str): Safe human-readable message.
        path (tuple[str | int, ...]): Source document property path.
        source_id (str): Stable migration source identity.

    Raises:
        None.

    Returns:
        GraphDiagnostic: Safe diagnostic value.
    """
    return GraphDiagnostic(code=code, message=message, path=path, source_id=source_id)


def _legacy_port_map(node: Mapping[str, Any]) -> dict[str, str]:
    """Map legacy random port handles to stable contract port IDs.

    Args:
        node (Mapping[str, Any]): Legacy node declaration.

    Raises:
        None.

    Returns:
        dict[str, str]: Handle-to-contract-port mapping.
    """
    data = node.get("data") if isinstance(node.get("data"), Mapping) else {}
    ports = data.get("ports") if isinstance(data, Mapping) else []
    result: dict[str, str] = {}
    if not isinstance(ports, list):
        return result
    for port in ports:
        if not isinstance(port, Mapping):
            continue
        port_id = str(port.get("portId") or port.get("id") or "")
        role = str(port.get("portRole") or port.get("role") or port_id)
        if port_id:
            result[port_id] = _LEGACY_PORT_MAP.get(role, role)
    return result


def _resource_id(value: Any, fallback: str) -> str:
    """Normalize a legacy resource ID without introducing random identity.

    Args:
        value (Any): Legacy value.
        fallback (str): Stable deterministic fallback.

    Raises:
        None.

    Returns:
        str: Candidate schema 2 resource identity.
    """
    text = str(value or "").strip()
    return text if text else fallback


def migrate_studio_flow_document(
    source: Mapping[str, Any],
    *,
    source_id: str = "studio-migration",
    agent_id: str | None = None,
) -> StudioMigrationResult:
    """Parse schema 2 or purely migrate one unambiguous schema 1 document.

    The function deep-copies source data and never mutates the caller's mapping.

    Args:
        source (Mapping[str, Any]): Parsed Studio JSON mapping.
        source_id (str): Stable diagnostic source identity.
        agent_id (str | None): Optional stable Agent identity for legacy input.

    Raises:
        None: Validation failures are returned as diagnostics.

    Returns:
        StudioMigrationResult: Parsed/migrated document or deterministic
        diagnostics.
    """
    raw = deepcopy(dict(source))
    if raw.get("schemaVersion") == 2 or raw.get("schema_version") == 2:
        try:
            document = StudioFlowDocument.model_validate(raw)
        except ValidationError as error:
            diagnostics = diagnostics_from_validation_error(
                error,
                code="studio.document.structure_invalid",
                source_prefix=source_id,
            )
            return StudioMigrationResult(diagnostics=tuple(diagnostics))
        return StudioMigrationResult(document=document)

    if raw.get("schemaVersion") != 1 and raw.get("schema_version") != 1:
        return StudioMigrationResult(
            diagnostics=(
                _diagnostic(
                    "studio.migration.schema_unsupported",
                    "Studio document must declare schemaVersion 1 or 2",
                    path=("schemaVersion",),
                    source_id=source_id,
                ),
            )
        )

    nodes = raw.get("nodes")
    edges = raw.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return StudioMigrationResult(
            diagnostics=(
                _diagnostic(
                    "studio.migration.structure_invalid",
                    "Legacy FlowDocument requires nodes and edges arrays",
                    source_id=source_id,
                ),
            )
        )

    issues: list[GraphDiagnostic] = []
    migrated_nodes: list[dict[str, Any]] = []
    presentation_nodes: dict[str, dict[str, Any]] = {}
    canvas_to_logical: dict[str, str] = {}
    ports_by_canvas: dict[str, dict[str, str]] = {}

    for index, item in enumerate(nodes):
        if not isinstance(item, Mapping):
            issues.append(
                _diagnostic(
                    "studio.migration.node_invalid",
                    "Legacy node must be an object",
                    path=("nodes", index),
                    source_id=source_id,
                )
            )
            continue
        canvas_id = _resource_id(item.get("nodeId") or item.get("id"), f"node-{index + 1}")
        data = item.get("data") if isinstance(item.get("data"), Mapping) else {}
        node_type = str(item.get("nodeType") or item.get("type") or "")
        role = _ROLE_BY_LEGACY_TYPE.get(node_type)
        logical_id = str(
            item.get("logicalId")
            or item.get("logical_id")
            or data.get("logicalId")
            or data.get("logical_id")
            or ""
        )
        if not logical_id:
            same_type = sum(
                1
                for candidate in nodes
                if isinstance(candidate, Mapping)
                and str(candidate.get("nodeType") or candidate.get("type") or "") == node_type
            )
            if same_type == 1 and role is not None:
                logical_id = role.value
            elif same_type == 1 and node_type in {"input", "output", "ifelse", "condition"}:
                logical_id = "condition" if node_type == "ifelse" else node_type
        if not logical_id:
            issues.append(
                _diagnostic(
                    "studio.migration.logical_id_ambiguous",
                    "Legacy node requires an explicit logicalId",
                    path=("nodes", index),
                    source_id=source_id,
                )
            )
            continue

        migrated: dict[str, Any] = {
            "canvasId": canvas_id,
            "logicalId": logical_id,
        }
        if role is not None:
            plugin_name = data.get("selected_plugin_id") or data.get("selectedPluginId")
            if not plugin_name and role is GraphRole.ACTION_EXECUTOR:
                plugin_name = "legacy_action_executor"
            if not plugin_name:
                issues.append(
                    _diagnostic(
                        "studio.migration.component_missing",
                        f"Legacy component {logical_id!r} has no selected plugin",
                        path=("nodes", index, "data", "selected_plugin_id"),
                        source_id=source_id,
                    )
                )
                continue
            params = data.get("plugin_params") or data.get("pluginParamValues") or {}
            if not isinstance(params, Mapping):
                issues.append(
                    _diagnostic(
                        "studio.migration.params_invalid",
                        "Legacy plugin params must be an object",
                        path=("nodes", index, "data", "plugin_params"),
                        source_id=source_id,
                    )
                )
                continue
            migrated.update(
                {
                    "kind": "component",
                    "lifecycle": _LIFECYCLE_BY_ROLE[role].value,
                    "role": role.value,
                    "contract": contract_ref_for_role(role).model_dump(mode="json"),
                    "primary": role is GraphRole.ACTION_EXECUTOR,
                    "component": {
                        "policy": "single",
                        "candidates": [
                            {
                                "namespace": str(
                                    data.get("selected_plugin_namespace")
                                    or data.get("selectedPluginNamespace")
                                    or f"agent.{role.value}"
                                ),
                                "name": str(plugin_name),
                                "version": str(
                                    data.get("selected_plugin_version")
                                    or data.get("selectedPluginVersion")
                                    or "1"
                                ),
                                "params": deepcopy(dict(params)),
                                "dependencies": {},
                            }
                        ],
                    },
                }
            )
        elif node_type == "input":
            migrated.update({"kind": "input", "lifecycle": "on_run_start"})
        elif node_type == "output":
            migrated.update({"kind": "output", "lifecycle": "terminal"})
        elif node_type in {"ifelse", "condition"}:
            predicate = data.get("predicate")
            if not isinstance(predicate, Mapping):
                issues.append(
                    _diagnostic(
                        "studio.migration.condition_unsafe",
                        "Legacy condition requires a structured predicate",
                        path=("nodes", index, "data", "predicate"),
                        source_id=source_id,
                    )
                )
                continue
            migrated.update(
                {
                    "kind": "condition",
                    "lifecycle": "post_action",
                    "predicate": deepcopy(dict(predicate)),
                }
            )
        else:
            issues.append(
                _diagnostic(
                    "studio.migration.node_type_unsupported",
                    f"Legacy node type {node_type!r} cannot be migrated safely",
                    path=("nodes", index, "nodeType"),
                    source_id=source_id,
                )
            )
            continue

        canvas_to_logical[canvas_id] = logical_id
        ports_by_canvas[canvas_id] = _legacy_port_map(item)
        migrated_nodes.append(migrated)
        position = item.get("position") if isinstance(item.get("position"), Mapping) else {}
        presentation_nodes[canvas_id] = {
            "x": float(position.get("x", 0) or 0),
            "y": float(position.get("y", 0) or 0),
            "label": str(data.get("label") or ""),
            "icon": str(data.get("icon") or ""),
            "description": str(data.get("desc") or ""),
        }

    migrated_edges: list[dict[str, Any]] = []
    for index, item in enumerate(edges):
        if not isinstance(item, Mapping):
            issues.append(
                _diagnostic(
                    "studio.migration.edge_invalid",
                    "Legacy edge must be an object",
                    path=("edges", index),
                    source_id=source_id,
                )
            )
            continue
        declared_type = str(item.get("dataType") or "")
        if declared_type in _UNSAFE_TYPES:
            issues.append(
                _diagnostic(
                    "studio.migration.edge_semantics_unsafe",
                    f"Legacy edge type {declared_type!r} cannot be migrated safely",
                    path=("edges", index, "dataType"),
                    source_id=source_id,
                )
            )
            continue
        source_canvas = str(item.get("sourceNodeId") or item.get("source") or "")
        target_canvas = str(item.get("targetNodeId") or item.get("target") or "")
        if source_canvas not in canvas_to_logical or target_canvas not in canvas_to_logical:
            issues.append(
                _diagnostic(
                    "studio.migration.edge_node_unknown",
                    "Legacy edge references an unknown node",
                    path=("edges", index),
                    source_id=source_id,
                )
            )
            continue
        raw_source_port = str(item.get("sourcePortId") or item.get("sourceHandle") or "")
        raw_target_port = str(item.get("targetPortId") or item.get("targetHandle") or "")
        source_port = ports_by_canvas.get(source_canvas, {}).get(
            raw_source_port,
            _LEGACY_PORT_MAP.get(raw_source_port, raw_source_port),
        )
        target_port = ports_by_canvas.get(target_canvas, {}).get(
            raw_target_port,
            _LEGACY_PORT_MAP.get(raw_target_port, raw_target_port),
        )
        kind = str(item.get("kind") or "")
        if not kind:
            source_node = next(
                candidate
                for candidate in migrated_nodes
                if candidate["canvasId"] == source_canvas
            )
            kind = (
                "control"
                if source_node["kind"] in {"condition", "router"}
                else "data"
            )
        migrated_edge: dict[str, Any] = {
            "canvasId": _resource_id(item.get("edgeId"), f"edge-{index + 1}"),
            "source": {"canvasId": source_canvas, "portId": source_port},
            "target": {"canvasId": target_canvas, "portId": target_port},
            "kind": kind,
        }
        if item.get("condition") is not None:
            migrated_edge["condition"] = deepcopy(item.get("condition"))
        if kind == "feedback":
            migrated_edge["feedback"] = deepcopy(item.get("feedback"))
        migrated_edges.append(migrated_edge)

    if issues:
        return StudioMigrationResult(diagnostics=tuple(issues))

    document_id = _resource_id(raw.get("flowId"), "legacy-document")
    target_agent_id = _resource_id(agent_id or raw.get("agentId"), f"agent-{document_id}")
    candidate = {
        "schemaVersion": 2,
        "contractVersion": "1.1",
        "documentId": document_id,
        "agentId": target_agent_id,
        "name": str(raw.get("flowName") or "Migrated Agent"),
        "semantic": {
            "profile": "mobile_agent",
            "interface": raw.get("interface"),
            "policies": deepcopy(raw.get("policies") or {}),
            "nodes": migrated_nodes,
            "edges": migrated_edges,
        },
        "presentation": {
            "nodes": presentation_nodes,
            "viewport": deepcopy(raw.get("viewport") or {}),
        },
        "authoring": {
            "description": str(raw.get("description") or ""),
            "createdAt": int(raw.get("createTime") or 0),
            "updatedAt": int(raw.get("updateTime") or 0),
        },
    }
    if candidate["semantic"]["interface"] is None:
        candidate["semantic"].pop("interface")
    try:
        document = StudioFlowDocument.model_validate(candidate)
    except (TypeError, ValueError, ValidationError) as error:
        if isinstance(error, ValidationError):
            diagnostics = diagnostics_from_validation_error(
                error,
                code="studio.migration.result_invalid",
                source_prefix=source_id,
            )
        else:
            diagnostics = [
                _diagnostic(
                    "studio.migration.result_invalid",
                    f"Legacy document cannot be migrated safely ({type(error).__name__})",
                    source_id=source_id,
                )
            ]
        return StudioMigrationResult(diagnostics=tuple(diagnostics))
    return StudioMigrationResult(document=document)


__all__ = ["StudioMigrationResult", "migrate_studio_flow_document"]
