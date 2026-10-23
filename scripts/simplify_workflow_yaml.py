"""Fold one expanded workflow YAML into the existing editable machine shorthand.

This optional offline tool writes only after compilation proves the same graph
identity. It does not load components, run an Agent or choose an Agent strategy.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path

import yaml

from zhixing.graph import compile_graph_yaml_data


def _edges(graph):
    """Normalize the reviewed unconditioned short-edge pattern.

    Args:
        graph: Named-node graph with explicit data/control connections.
    Raises:
        ValueError: A connection uses a different authoring convention.
    Returns:
        list: Data/control edges with string endpoints.
    """
    result = []
    for original in graph["edges"]:
        if isinstance(original, str):
            parts = original.split("->")
            if len(parts) != 2:
                raise ValueError("workflow edge requires source.port -> target.port")
            edge = {"source": parts[0].strip(), "target": parts[1].strip()}
        else:
            edge = dict(original)
        if set(edge) - {"source", "target", "kind"} or edge.get("kind", "data") not in {"data", "control"}:
            raise ValueError("offline folding only accepts unconditioned data/control edges")
        if any(not isinstance(edge[key], str) or "." not in edge[key] for key in ("source", "target")):
            raise ValueError("offline folding requires short string endpoints")
        result.append({"kind": "data", **edge})
    return result


def _fold_body(graph):
    """Recover stages from explicit dispatch and outcome-router connections.

    Args:
        graph: Expanded named-node workflow body.
    Raises:
        KeyError: Required reviewed pattern nodes or fields are absent.
        ValueError: A stage cannot use the existing machine port convention.
    Returns:
        dict: Independent graph scope with editable stage-local nodes and routes.
    """
    nodes, edges = graph["nodes"], _edges(graph)
    cases = nodes["dispatch"]["router"]["cases"]
    names = [case["id"] for case in cases]
    selector = cases[0]["predicate"]["field"]
    # Transition names are author-owned identity, recovered from control edges
    # rather than renamed during folding.
    first = names[0]
    first_outcome = nodes[first + "_route"]["router"]["cases"][0]["id"]
    first_branch, = [edge["target"].rsplit(".", 1)[0] for edge in edges
                     if edge["source"] == first + "_route." + first_outcome]
    suffix = first + "_" + first_outcome
    if not first_branch.endswith(suffix):
        raise ValueError("transition naming does not match the machine convention")
    prefix = first_branch[:-len(suffix)]
    glue = {"input", "output", "read", "resume", "dispatch", "merge", "write"}
    for name in names:
        glue.add(name + "_route")
        glue.update(prefix + name + "_" + case["id"] for case in nodes[name + "_route"]["router"]["cases"])
    core = set(nodes) - glue
    stages, outcome, transition = {}, None, None
    for name in names:
        router = nodes[name + "_route"]["router"]
        output, = [edge["source"] for edge in edges if edge["target"] == name + "_route.value"]
        entry, = [edge["target"] for edge in edges if edge["source"] == "dispatch." + name]
        local, pending = set(), [output.rsplit(".", 1)[0]]
        # Walk only computational ancestors; shared scheduling glue is excluded.
        while pending:
            current = pending.pop()
            if current not in core or current in local:
                continue
            local.add(current)
            pending.extend(edge["source"].rsplit(".", 1)[0] for edge in edges
                           if edge["target"].rsplit(".", 1)[0] == current)
        inputs = [edge["target"] for edge in edges if edge["source"] == "resume.result"
                  and edge["target"].rsplit(".", 1)[0] in local]
        internal = [edge for edge in edges if all(edge[key].rsplit(".", 1)[0] in local for key in ("source", "target"))]
        if not local or entry.rsplit(".", 1)[0] not in local or any(edge["kind"] != "data" for edge in internal):
            raise ValueError("stage does not match the machine data/entry convention")
        destinations = {}
        for case in router["cases"]:
            field = case["predicate"]["field"]
            if outcome is not None and field != outcome:
                raise ValueError("stage outcome selectors differ")
            outcome = field
            branch = nodes[prefix + name + "_" + case["id"]]
            destinations[case["id"]] = branch["params"][selector]
            if transition is None:
                transition = deepcopy(branch)
                transition["params"].pop(selector)
        if local == {name} and inputs == [name + ".value"] and entry == name + ".control" and output == name + ".result" and not internal:
            stage = {"node": deepcopy(nodes[name])}
        else:
            stage = {"nodes": {key: deepcopy(value) for key, value in nodes.items() if key in local},
                "inputs": inputs, "entry": entry, "output": output,
                "edges": [edge["source"] + " -> " + edge["target"] for edge in internal]}
        stages[name] = {**stage, "next": destinations}
    return {**{key: deepcopy(value) for key, value in graph.items() if key not in {"nodes", "edges"}}, "machine": {
        "state": {key: value for key, value in nodes["read"]["state"].items() if key != "operation"},
        "selector": selector, "outcome": outcome, "resume": deepcopy(nodes["resume"]),
        "transition": transition, "merge": deepcopy(nodes["merge"]),
        **({"transition_prefix": prefix} if prefix else {}),
        **({"exits": sorted({target for stage in stages.values() for target in stage["next"].values()} - set(names))}
           if any(target not in names for stage in stages.values() for target in stage["next"].values()) else {}),
        "stages": stages}}


def simplify_document(document):
    """Fold an expanded document only when canonical execution identity is equal.

    Args:
        document: Schema-1 authoring data; the caller retains its original object.
    Raises:
        ValueError: No matching body exists, compilation fails or semantics differ.
        KeyError: The source is outside the supported expanded pattern.
    Returns:
        dict: Independent machine authoring document.
    """
    converted = 0

    def visit(graph):
        """Fold nested scopes. Args: graph: Authoring graph. Returns: dict: Copy."""
        nonlocal converted
        if isinstance(graph.get("nodes"), dict) and "dispatch" in graph["nodes"]:
            converted += 1
            return _fold_body(graph)
        graph = deepcopy(graph)
        for node in graph.get("nodes", {}).values():
            for key in ("loop", "subgraph"):
                if key in node:
                    body = node[key]["body"] if key == "loop" else node[key]
                    if "graph" in body:
                        body["graph"] = visit(body["graph"])
        return graph

    result = visit(document)
    if not converted:
        raise ValueError("no expanded workflow body found")
    before, after = compile_graph_yaml_data(document), compile_graph_yaml_data(result)
    if not before.is_success or not after.is_success:
        raise ValueError("both source and simplified YAML must compile successfully")
    if before.graph.canonical_hash() != after.graph.canonical_hash():
        raise ValueError("simplification changes canonical graph identity; nothing may be written")
    return result


def render_document(document):
    """Keep stages in block form with the same component formatting as AppAgent.

    Args:
        document: Parsed authoring data.
    Returns:
        str: YAML at the established 180-column width, without minifying stages.
    """
    class Component(dict):
        """Mark one component declaration for flow mapping layout."""

    class Dumper(yaml.SafeDumper):
        """Keep formatting local to this offline invocation."""

    def represent(dumper, value):
        """Render a component. Args: dumper,value: YAML writer/data. Returns: MappingNode."""
        return dumper.represent_mapping("tag:yaml.org,2002:map", value.items(), flow_style=True)

    def visit(value):
        """Format nodes only. Args: value: Authoring subtree. Returns: Equivalent data."""
        if isinstance(value, dict):
            return (Component if "component" in value else dict)((key, visit(item)) for key, item in value.items())
        return [visit(item) for item in value] if isinstance(value, list) else value

    Dumper.add_representer(Component, represent)
    return yaml.dump(visit(document), Dumper=Dumper, sort_keys=False, allow_unicode=True, default_flow_style=None, width=180)


def main():
    """Convert one source to one destination after static identity checks.

    Raises:
        OSError: Source or destination cannot be accessed.
        ValueError: The source is unsupported or compilation/identity checks fail.
    Returns:
        None.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    document = simplify_document(yaml.safe_load(args.source.read_text()))
    rendered = render_document(document)
    # Validate the actual serialized bytes as well, before modifying any output.
    parsed = compile_graph_yaml_data(yaml.safe_load(rendered))
    if not parsed.is_success or parsed.graph.canonical_hash() != compile_graph_yaml_data(document).graph.canonical_hash():
        raise ValueError("serialized YAML changed the validated graph")
    args.destination.write_text(rendered)


if __name__ == "__main__":
    main()
