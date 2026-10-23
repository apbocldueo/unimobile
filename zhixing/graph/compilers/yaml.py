"""Graph-native YAML loading and deterministic routing from YAML envelopes."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from ..authoring import MobileAgentAuthoring
from ..diagnostics import CompilationResult, GraphDiagnostic, SourceMapEntry
from ..enums import DiagnosticSeverity
from ..models import AgentGraph
from .common import diagnostics_from_validation_error, finish_compilation, normalize_logical_ids


GRAPH_YAML_KIND = "agent_graph"
GRAPH_YAML_SCHEMA_VERSION = 1
AUTHORING_YAML_SCHEMA_VERSION = 2


def compile_mobile_agent_yaml_data(
    data: Mapping[str, Any],
    *,
    source_id: str = "mobile-agent-yaml",
    contract_catalog=None,
    graph_catalog=None,
) -> CompilationResult:
    """Compile schema-2 high-level YAML into the standard AgentGraph.

    Args:
        data (Mapping[str, Any]): Parsed schema-2 authoring document.
        source_id (str): Stable diagnostic source identifier.
        contract_catalog (Any): Optional explicit node-contract catalog.
        graph_catalog (Any): Optional explicit graph catalog.

    Raises:
        None.

    Returns:
        CompilationResult: Canonical graph or user-addressable diagnostics.
    """
    try:
        authoring = MobileAgentAuthoring.model_validate(data)
    except ValidationError as exc:
        return finish_compilation(
            None,
            diagnostics_from_validation_error(
                exc, code="graph.yaml.authoring_invalid", source_prefix=source_id
            ),
            [],
        )

    if not authoring.capabilities.memory.enabled:
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.authoring_capability_unsupported",
                    message="mobile_vlm requires memory.enabled: true for bounded feedback",
                    path=("capabilities", "memory", "enabled"),
                    source_id=source_id,
                ),
            )
        )

    from zhixing.agents import build_builtin_mobile_agent_graph

    max_feedback = authoring.policies.max_feedback_iterations
    if max_feedback is None:
        max_feedback = min(authoring.policies.max_steps, 10)
    graph = build_builtin_mobile_agent_graph(
        model=authoring.model.name,
        base_url=authoring.model.base_url,
        api_key_secret=authoring.model.secret_ref,
        base_url_secret=authoring.model.base_url_secret,
        max_steps=authoring.policies.max_steps,
        max_feedback_iterations=max_feedback,
        reasoning_params={
            "preset": authoring.capabilities.reasoning.preset,
            "parse_max_retries": authoring.capabilities.reasoning.parse_max_retries,
        },
        memory_params={"window_size": authoring.capabilities.memory.window_size},
    )
    source_map = tuple(
        SourceMapEntry(
            source_id=f"{source_id}:generated:{node.id}",
            graph_kind="node",
            graph_id=node.id,
            document_id=authoring.name,
            logical_node_path=(node.id,),
        )
        for node in graph.nodes
    )
    return finish_compilation(
        graph,
        [],
        list(source_map),
        contract_catalog=contract_catalog,
        graph_catalog=graph_catalog,
    )


def compile_graph_yaml_data(
    data: Mapping[str, Any],
    *,
    source_id: str = "graph-yaml",
    contract_catalog=None,
    graph_catalog=None,
) -> CompilationResult:
    """Compile graph-native YAML data using only explicit catalogs.

    Args:
        data (Mapping[str, Any]): Parsed YAML with arrays, named nodes or a machine.
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
    if isinstance(raw_nodes, Mapping) or "machine" in raw:
        from .compact_yaml import compile_compact_graph_yaml_data

        return compile_compact_graph_yaml_data(
            data, source_id=source_id,
            contract_catalog=contract_catalog, graph_catalog=graph_catalog,
        )
    if not isinstance(raw_nodes, list):
        return CompilationResult(
            diagnostics=(
                GraphDiagnostic(
                    code="graph.yaml.nodes_invalid",
                    message="graph YAML nodes must be an array or named node mapping",
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
    if (
        data.get("kind") == GRAPH_YAML_KIND
        and data.get("schema_version") == AUTHORING_YAML_SCHEMA_VERSION
    ):
        return compile_mobile_agent_yaml_data(
            data,
            source_id=str(source),
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
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
    if (
        isinstance(data, Mapping)
        and data.get("kind") == GRAPH_YAML_KIND
        and data.get("schema_version") == AUTHORING_YAML_SCHEMA_VERSION
    ):
        return compile_mobile_agent_yaml_data(
            data,
            source_id=str(source),
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
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
        result = compile_agent_config(config, source_id=str(source))
        deprecation = GraphDiagnostic(
            code="graph.agent_config.deprecated",
            message=(
                "AgentConfig V1 is a compatibility-only format; use "
                "kind: agent_graph with schema_version: 2 for new Agents"
            ),
            severity=DiagnosticSeverity.WARNING,
            source_id=str(source),
        )
        return result.model_copy(update={"diagnostics": (*result.diagnostics, deprecation)})
    return CompilationResult(
        diagnostics=(
            GraphDiagnostic(
                code="graph.yaml.envelope_unknown",
                message="YAML is neither graph-native agent_graph nor AgentConfig V1",
                source_id=str(source),
            ),
        )
    )
