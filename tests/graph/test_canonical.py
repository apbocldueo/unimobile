from __future__ import annotations

import subprocess
import sys

from zhixing.graph import BindingPolicy, ComponentBinding, GraphComponentRef, GraphPresentation, NodePresentation

from .helpers import make_golden_graph


def test_canonical_hash_is_stable_and_prefixed():
    graph = make_golden_graph()
    assert graph.canonical_hash() == graph.canonical_hash()
    assert graph.canonical_hash().startswith("sha256:")
    assert len(graph.canonical_hash()) == len("sha256:") + 64


def test_canonical_hash_is_stable_across_processes():
    local = make_golden_graph().canonical_hash()
    script = "from tests.graph.helpers import make_golden_graph; print(make_golden_graph().canonical_hash())"
    completed = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == local


def test_declaration_order_and_presentation_do_not_change_identity():
    graph = make_golden_graph()
    reordered = graph.model_copy(update={"nodes": tuple(reversed(graph.nodes)), "edges": tuple(reversed(graph.edges))})
    presented = graph.model_copy(
        update={
            "presentation": GraphPresentation(
                flow_id="random-flow",
                flow_name="新标题",
                created_at=1,
                updated_at=999,
                nodes={"reasoning": NodePresentation(x=900, y=10, label="不同名称", icon="⚡")},
            ),
            "metadata": {"studio": {"zoom": 1.5}},
        }
    )
    assert reordered.canonical_json() == graph.canonical_json()
    assert presented.canonical_hash() == graph.canonical_hash()


def test_semantic_mutations_change_hash():
    graph = make_golden_graph()
    assert graph.model_copy(update={"contract_version": "1.1"}).canonical_hash() != graph.canonical_hash()
    assert graph.model_copy(
        update={"policies": graph.policies.model_copy(update={"max_steps": 16})}
    ).canonical_hash() != graph.canonical_hash()

    reasoning_index = next(i for i, item in enumerate(graph.nodes) if item.id == "reasoning")
    reasoning = graph.nodes[reasoning_index]
    candidate = reasoning.component.candidates[0].model_copy(update={"params": {"temperature": 0.2}})
    changed = reasoning.model_copy(
        update={"component": ComponentBinding(candidates=(candidate,))}
    )
    nodes = list(graph.nodes)
    nodes[reasoning_index] = changed
    assert graph.model_copy(update={"nodes": tuple(nodes)}).canonical_hash() != graph.canonical_hash()


def test_fallback_order_is_semantic():
    graph = make_golden_graph()
    perception_index = next(i for i, item in enumerate(graph.nodes) if item.id == "perception")
    perception = graph.nodes[perception_index]
    first = perception.component.candidates[0]
    second = first.model_copy(update={"name": "backup_perception"})
    binding = ComponentBinding(policy=BindingPolicy.FALLBACK, candidates=(first, second))
    swapped = ComponentBinding(policy=BindingPolicy.FALLBACK, candidates=(second, first))
    nodes_a = list(graph.nodes)
    nodes_b = list(graph.nodes)
    nodes_a[perception_index] = perception.model_copy(update={"component": binding})
    nodes_b[perception_index] = perception.model_copy(update={"component": swapped})
    assert graph.model_copy(update={"nodes": tuple(nodes_a)}).canonical_hash() != graph.model_copy(
        update={"nodes": tuple(nodes_b)}
    ).canonical_hash()


def test_secret_placeholder_is_normalized_without_resolution():
    graph = make_golden_graph()
    index = next(i for i, item in enumerate(graph.nodes) if item.id == "reasoning")
    reasoning = graph.nodes[index]
    candidate = GraphComponentRef(
        namespace="agent.reasoning",
        name="test_reasoning",
        params={"api_key": "${shared_api_key}", "temperature": 0.1},
    )
    nodes = list(graph.nodes)
    nodes[index] = reasoning.model_copy(update={"component": ComponentBinding(candidates=(candidate,))})
    canonical = graph.model_copy(update={"nodes": tuple(nodes)}).canonical_json()
    assert '"secret_ref":"shared_api_key"' in canonical
    assert "sk-live" not in canonical
