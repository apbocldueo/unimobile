"""Shared compiler utilities and source identity rules."""

from __future__ import annotations

import json
from collections import Counter
from typing import Any, Mapping

from pydantic import ValidationError

from ..diagnostics import (
    CompilationResult,
    GraphDiagnostic,
    SourceMapEntry,
    sorted_diagnostics,
)
from ..enums import DiagnosticSeverity
from ..models import AgentGraph


def normalize_scalar(value: Any) -> Any:
    """Normalize Studio string form values without guessing ordinary text."""

    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if stripped.startswith("${") and stripped.endswith("}"):
        return value
    if stripped in {"true", "false", "null"} or (
        stripped and stripped[0] in "-0123456789[{\""
    ):
        try:
            return json.loads(stripped)
        except (ValueError, TypeError):
            return value
    return value


def normalize_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Mapping):
            out[str(key)] = normalize_mapping(item)
        elif isinstance(item, list):
            out[str(key)] = [normalize_mapping(v) if isinstance(v, Mapping) else normalize_scalar(v) for v in item]
        else:
            out[str(key)] = normalize_scalar(item)
    return out


def normalize_logical_ids(nodes: list[dict[str, Any]], *, source_prefix: str) -> tuple[list[dict[str, Any]], list[GraphDiagnostic]]:
    """Fill IDs only for a role that occurs once; never use declaration order."""

    issues: list[GraphDiagnostic] = []
    role_counts = Counter(str(node.get("role") or "") for node in nodes if node.get("role"))
    normalized: list[dict[str, Any]] = []
    for index, original in enumerate(nodes):
        node = dict(original)
        logical_id = node.get("id") or node.get("logical_id") or node.get("logicalId")
        role = str(node.get("role") or "")
        if not logical_id and role and role_counts[role] == 1:
            logical_id = role
        if not logical_id:
            issues.append(
                GraphDiagnostic(
                    code="graph.compile.logical_id_ambiguous",
                    message="node requires an explicit stable logical id",
                    path=("nodes", index, "id"),
                    source_id=f"{source_prefix}:nodes:{index}",
                )
            )
        else:
            node["id"] = str(logical_id)
        node.pop("logical_id", None)
        node.pop("logicalId", None)
        normalized.append(node)
    return normalized, issues


def diagnostics_from_validation_error(exc: ValidationError, *, code: str, source_prefix: str) -> list[GraphDiagnostic]:
    return [
        GraphDiagnostic(
            code=code,
            message=error["msg"],
            path=tuple(error["loc"]),
            source_id=f"{source_prefix}:{'.'.join(str(part) for part in error['loc'])}",
        )
        for error in exc.errors(include_url=False)
    ]


def finish_compilation(
    graph: AgentGraph | None,
    diagnostics: list[GraphDiagnostic],
    source_map: list[SourceMapEntry],
    *,
    contract_catalog=None,
    graph_catalog=None,
) -> CompilationResult:
    """Finish compilation with deterministic explicit-catalog validation.

    Args:
        graph (AgentGraph | None): Parsed graph, when structural parsing succeeded.
        diagnostics (list[GraphDiagnostic]): Compiler diagnostics collected so far.
        source_map (list[SourceMapEntry]): Stable source-to-graph mappings.
        contract_catalog (Any): Optional explicit NodeContractCatalog.
        graph_catalog (Any): Optional explicit GraphCatalog.

    Raises:
        None.

    Returns:
        CompilationResult: Immutable graph, diagnostics, and source map.
    """
    if graph is not None:
        diagnostics.extend(
            graph.validate_graph(
                contract_catalog=contract_catalog,
                graph_catalog=graph_catalog,
            ).diagnostics
        )
    ordered = sorted_diagnostics(diagnostics)
    return CompilationResult(graph=graph, diagnostics=ordered, source_map=tuple(source_map))


def unsupported(message: str, *, source_id: str) -> CompilationResult:
    return CompilationResult(
        diagnostics=(
            GraphDiagnostic(
                code="graph.compile.unsupported",
                message=message,
                severity=DiagnosticSeverity.ERROR,
                source_id=source_id,
            ),
        )
    )
