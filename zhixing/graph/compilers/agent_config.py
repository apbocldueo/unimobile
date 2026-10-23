"""Compatibility compiler from canonical AgentConfig V1 to AgentGraph V1."""

from __future__ import annotations

from typing import Any

from zhixing.config.contracts import AgentConfig

from ..diagnostics import CompilationResult, SourceMapEntry
from ..models import AgentGraph, normalize_secret_placeholders
from ..templates import LEGACY_PARADIGM_COMPATIBILITY
from .common import finish_compilation, unsupported


LEGACY_ACTION_NAMESPACE = "agent.action_executor"
LEGACY_ACTION_NAME = "legacy_action_executor"


def _component_candidate(role: str, ref, *, default_llm=None, extra_dependencies=None) -> dict[str, Any]:
    dependencies: dict[str, Any] = {}
    llm = getattr(ref, "llm", None) or default_llm
    if llm is not None:
        dependencies["llm"] = normalize_secret_placeholders(llm.model_dump(mode="python"))
    dependencies.update(extra_dependencies or {})
    return {
        "namespace": f"agent.{role}",
        "name": ref.name,
        "params": normalize_secret_placeholders(ref.params),
        "dependencies": dependencies,
    }


def _binding(role: str, value, *, default_llm=None, extra_dependencies=None) -> dict[str, Any]:
    values = value if isinstance(value, list) else [value]
    return {
        "policy": "fallback" if len(values) > 1 else "single",
        "candidates": [
            _component_candidate(
                role,
                item,
                default_llm=default_llm,
                extra_dependencies=extra_dependencies,
            )
            for item in values
        ],
    }


def compile_agent_config(config: AgentConfig, *, source_id: str = "agent-config-v1") -> CompilationResult:
    """Compile only legacy strategies with verified graph parity.

    Args:
        config (AgentConfig): Validated AgentConfig V1.
        source_id (str): Stable diagnostic source identifier.

    Raises:
        None.

    Returns:
        CompilationResult: Compatible graph or stable unsupported diagnostic.
    """
    compatibility = LEGACY_PARADIGM_COMPATIBILITY.get(config.agent_type)
    if compatibility is None or not compatibility.compilation_enabled:
        reason = (
            compatibility.reason
            if compatibility is not None
            else "no versioned paradigm template is registered"
        )
        return unsupported(
            f"AgentConfig V1 type {config.agent_type!r} has no validated AgentGraph template ({reason}); use the legacy AgentFactory/Runner path",
            source_id=source_id,
        )
    components = config.agent.components
    default_llm = config.global_config.default_llm
    nodes: list[dict[str, Any]] = [
        {"id": "input", "kind": "input", "lifecycle": "on_run_start"},
    ]
    source_map: list[SourceMapEntry] = [
        SourceMapEntry(source_id=f"{source_id}:input", graph_kind="node", graph_id="input")
    ]

    def add_component(role: str, value, lifecycle: str, *, primary=False, dependencies=None):
        if value is None:
            return
        nodes.append(
            {
                "id": role,
                "kind": "component",
                "role": role,
                "lifecycle": lifecycle,
                "primary": primary,
                "component": _binding(
                    role,
                    value,
                    default_llm=default_llm,
                    extra_dependencies=dependencies,
                ),
            }
        )
        source_map.append(
            SourceMapEntry(
                source_id=f"{source_id}:agent.components.{role}",
                graph_kind="node",
                graph_id=role,
            )
        )

    grounder_dependency = None
    if components.grounder is not None:
        grounder_dependency = {
            "grounder": _component_candidate(
                "grounder", components.grounder, default_llm=default_llm
            )
        }
    add_component("planner", components.planner, "on_run_start")
    add_component("perception", components.perception, "per_step")
    add_component("memory", components.memory, "stateful")
    add_component("reasoning", components.reasoning, "per_step", dependencies=grounder_dependency)
    add_component("verifier", components.verifier, "post_action")
    nodes.append(
        {
            "id": "action_executor",
            "kind": "component",
            "role": "action_executor",
            "lifecycle": "per_step",
            "primary": True,
            "component": {
                "policy": "single",
                "candidates": [
                    {
                        "namespace": LEGACY_ACTION_NAMESPACE,
                        "name": LEGACY_ACTION_NAME,
                        "params": {},
                        "dependencies": {},
                    }
                ],
            },
        }
    )
    nodes.append({"id": "output", "kind": "output", "lifecycle": "terminal"})
    source_map.extend(
        [
            SourceMapEntry(source_id=f"{source_id}:implicit-action", graph_kind="node", graph_id="action_executor"),
            SourceMapEntry(source_id=f"{source_id}:output", graph_kind="node", graph_id="output"),
        ]
    )

    def e(sn, sp, tn, tp, kind="data", **extra):
        return {
            "source": {"node": sn, "port": sp},
            "target": {"node": tn, "port": tp},
            "kind": kind,
            **extra,
        }

    edges: list[dict[str, Any]] = [
        e("input", "task", "reasoning", "task"),
        e("input", "observation", "perception", "observation"),
        e("perception", "perception", "reasoning", "perception"),
        e("reasoning", "action", "action_executor", "action"),
        e("input", "observation", "action_executor", "observation"),
        e("action_executor", "result", "output", "result"),
    ]
    if components.planner is not None:
        edges.extend(
            [
                e("input", "task", "planner", "task"),
                e("planner", "plan", "reasoning", "plan"),
                e("planner", "plan", "memory", "write"),
            ]
        )
    if components.memory is not None:
        edges.extend(
            [
                e("input", "task", "memory", "write"),
                e("memory", "context", "reasoning", "memory"),
            ]
        )
    if components.verifier is not None:
        edges.extend(
            [
                e("input", "task", "verifier", "task"),
                e("input", "observation", "verifier", "before"),
                e("input", "observation", "verifier", "after"),
                e("reasoning", "action", "verifier", "action"),
                e("action_executor", "result", "verifier", "action_result"),
                e(
                    "verifier",
                    "result",
                    "reasoning",
                    "verification",
                    "feedback",
                    feedback={
                        "predicate": {"field": "is_success", "operator": "eq", "value": False},
                        "max_iterations": 2,
                        "on_exhausted": "continue",
                    },
                ),
            ]
        )
    graph = AgentGraph.model_validate(
        {
            "schema_version": 1,
            "contract_version": "1.0",
            "profile": "mobile_agent",
            "nodes": nodes,
            "edges": edges,
            "policies": {"max_steps": 15, "max_feedback_iterations": 3},
            "metadata": {
                "source": "agent_config_v1",
                "device_requirement": config.device.model_dump(mode="python"),
            },
        }
    )
    source_map.extend(
        SourceMapEntry(source_id=f"{source_id}:edges:{index}", graph_kind="edge", graph_id=str(index))
        for index, _edge in enumerate(edges)
    )
    return finish_compilation(graph, [], source_map)
