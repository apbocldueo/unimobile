"""Graph-native YAML loading and deterministic routing from YAML envelopes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from ..diagnostics import CompilationResult, GraphDiagnostic, SourceMapEntry
from ..models import AgentGraph
from .common import diagnostics_from_validation_error, finish_compilation, normalize_logical_ids


GRAPH_YAML_KIND = "agent_graph"
GRAPH_YAML_SCHEMA_VERSION = 1


def compile_graph_yaml_data(
    data: Mapping[str, Any],
    *,
    source_id: str = "graph-yaml",
    contract_catalog=None,
    graph_catalog=None,
) -> CompilationResult:
    """Compile graph-native YAML data using only explicit catalogs.

    Args:
        data (Mapping[str, Any]): Parsed YAML mapping.
        source_id (str): Stable diagnostic source identifier.
        contract_catalog (Any): Optional explicit NodeContractCatalog.
        graph_catalog (Any): Optional explicit GraphCatalog.

    Raises:
        None.

    Returns:
        CompilationResult: Parsed graph or deterministic diagnostics.
    """
    issues: list[GraphDiagnostic] = []
    if data.get("kind") != GRAPH_YAML_KIND:
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.kind_invalid",
                    message=f"graph YAML requires kind: {GRAPH_YAML_KIND}",
                    path=("kind",),
                    source_id=source_id,
                ),
            )
        )
    raw = dict(data)
    raw.pop("kind", None)
    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list):
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.nodes_invalid",
                    message="graph YAML nodes must be an array",
                    path=("nodes",),
                    source_id=source_id,
                ),
            )
        )
    normalized, id_issues = normalize_logical_ids(
        [dict(item) if isinstance(item, Mapping) else {"_invalid": item} for item in raw_nodes],
        source_prefix=source_id,
    )
    issues.extend(id_issues)
    raw["nodes"] = normalized
    if issues:
        return finish_compilation(None, issues, [])
    try:
        graph = AgentGraph.model_validate(raw)
    except ValidationError as exc:
        issues.extend(
            diagnostics_from_validation_error(
                exc, code="graph.yaml.structure_invalid", source_prefix=source_id
            )
        )
        return finish_compilation(None, issues, [])
    source_map = [
        SourceMapEntry(source_id=f"{source_id}:nodes:{index}", graph_kind="node", graph_id=node.id)
        for index, node in enumerate(graph.nodes)
    ] + [
        SourceMapEntry(source_id=f"{source_id}:edges:{index}", graph_kind="edge", graph_id=str(index))
        for index, _edge in enumerate(graph.edges)
    ]
    return finish_compilation(
        graph,
        issues,
        source_map,
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )


def load_graph_yaml(
    path: str | Path,
    *,
    contract_catalog=None,
    graph_catalog=None,
) -> CompilationResult:
    """Load and compile one graph-native YAML file.

    Args:
        path (str | Path): YAML path.
        contract_catalog (Any): Optional explicit NodeContractCatalog.
        graph_catalog (Any): Optional explicit GraphCatalog.

    Raises:
        None.

    Returns:
        CompilationResult: Parsed graph or deterministic diagnostics.
    """
    source = Path(path)
    if source.suffix.lower() not in {".yaml", ".yml"}:
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.format_invalid",
                    message="AgentGraph configuration must be YAML",
                    source_id=str(source),
                ),
            )
        )
    try:
        with source.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.read_failed",
                    message=f"cannot read graph YAML: {type(exc).__name__}",
                    source_id=str(source),
                ),
            )
        )
    if not isinstance(data, Mapping):
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.root_invalid",
                    message="AgentGraph YAML root must be an object",
                    source_id=str(source),
                ),
            )
        )
    return compile_graph_yaml_data(
        data,
        source_id=str(source),
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )


def compile_agent_yaml(
    path: str | Path,
    *,
    contract_catalog=None,
    graph_catalog=None,
) -> CompilationResult:
    """Route graph-native YAML or AgentConfig V1 without envelope guessing.

    Args:
        path (str | Path): YAML path.
        contract_catalog (Any): Optional explicit NodeContractCatalog for graph-native YAML.
        graph_catalog (Any): Optional explicit GraphCatalog for graph-native YAML.

    Raises:
        None.

    Returns:
        CompilationResult: Compiled graph or deterministic diagnostics.
    """

    source = Path(path)
    try:
        with source.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError) as exc:
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.read_failed",
                    message=f"cannot read Agent YAML: {type(exc).__name__}",
                    source_id=str(source),
                ),
            )
        )
    if isinstance(data, Mapping) and data.get("kind") == GRAPH_YAML_KIND:
        return compile_graph_yaml_data(
            data,
            source_id=str(source),
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        )
    if isinstance(data, Mapping) and data.get("schema_version") == 1 and "agent_type" in data:
        from zhixing.config.contracts import parse_agent_config

        from .agent_config import compile_agent_config

        try:
            config = parse_agent_config(data)
        except Exception as exc:
            return CompilationResult(
                diagnostics=(
                    GraphDiagnostic(
                        code="graph.agent_config.invalid",
                        message=f"AgentConfig V1 validation failed: {type(exc).__name__}",
                        source_id=str(source),
                    ),
                )
            )
        return compile_agent_config(config, source_id=str(source))
    return CompilationResult(
        diagnostics=(
            GraphDiagnostic(
                code="graph.yaml.envelope_unknown",
                message="YAML is neither graph-native agent_graph nor AgentConfig V1",
                source_id=str(source),
            ),
        )
    )
