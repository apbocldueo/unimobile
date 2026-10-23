"""Lower editable state-machine plumbing to ordinary AgentGraph declarations.

Adapters are explicit component nodes using the documented frame-port convention;
this module knows no Agent names, strategies, devices or component implementations.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


class MachineAuthoringError(ValueError):
    """Carry a safe, source-addressable shorthand error."""

    def __init__(self, message: str, path: tuple[str | int, ...]) -> None:
        """Store an error without echoing configuration values.

        Args:
            message: Fixed structural explanation.
            path: Location in the authoring document.
        Returns:
            None.
        """
        super().__init__(message)
        self.path = path


def _object(value: Any, path: tuple, *, allowed=None, required=()) -> dict:
    """Check one strict shorthand mapping.

    Args:
        value: Source value.
        path: Diagnostic location.
        allowed: Optional complete set of accepted keys.
        required: Keys that must be present.
    Raises:
        MachineAuthoringError: Object shape, keys or required fields are invalid.
    Returns:
        dict: Independent shallow mapping.
    """
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise MachineAuthoringError("machine declaration requires a string-keyed object", path)
    for key in value:
        if allowed is not None and key not in allowed:
            raise MachineAuthoringError("unknown machine field", path + (key,))
    for key in sorted(required):
        if key not in value:
            raise MachineAuthoringError("required machine field is missing", path + (key,))
    return dict(value)


def expand_machine(data: Mapping[str, Any], path: tuple) -> tuple[dict, dict, list]:
    """Expand a bounded routing table with optional exits and stable name prefix.

    Args:
        data: Graph scope with a machine instead of nodes and edges.
        path: Source path of this graph scope.
    Raises:
        MachineAuthoringError: Shorthand is malformed, targets are absent or names
            collide; node/port/model validity is checked by the ordinary compiler.
    Returns:
        tuple: Named-node graph, per-node source paths and per-edge source paths.
    """
    location = path + ("machine",)
    if "nodes" in data or "edges" in data:
        raise MachineAuthoringError("machine cannot coexist with nodes or edges", location)
    keys = {"state", "selector", "outcome", "resume", "transition", "merge", "stages"}
    spec = _object(data["machine"], location, allowed=keys | {"exits", "transition_prefix"}, required=keys)
    state = _object(spec["state"], location + ("state",),
                    allowed={"key", "data_type", "scope"}, required={"key", "data_type", "scope"})
    for key in ("selector", "outcome"):
        if not isinstance(spec[key], str) or not spec[key]:
            raise MachineAuthoringError("machine field selector must be a nonempty string", location + (key,))
    stages = _object(spec["stages"], location + ("stages",))
    if not 1 <= len(stages) <= 128:
        raise MachineAuthoringError("machine requires 1 to 128 stages", location + ("stages",))
    # Exit values are returned to the enclosing graph, whose explicit Loop
    # predicate owns termination. They never create a hidden terminal operation.
    exits = spec.get("exits", [])
    if (not isinstance(exits, list) or len(exits) > 128
            or any(not isinstance(value, str) or not value or value in stages for value in exits)):
        raise MachineAuthoringError("exits require distinct non-stage strings", location + ("exits",))
    if len(set(exits)) != len(exits):
        raise MachineAuthoringError("exits require distinct non-stage strings", location + ("exits",))
    prefix = spec.get("transition_prefix", "")
    if not isinstance(prefix, str):
        raise MachineAuthoringError("transition prefix requires a string", location + ("transition_prefix",))
    adapters = {}
    for name in ("resume", "transition", "merge"):
        adapter = _object(spec[name], location + (name,), required={"component"})
        if not isinstance(adapter["component"], str):
            raise MachineAuthoringError("machine adapter requires a namespace:name component", location + (name, "component"))
        if "kind" in adapter and adapter["kind"] != "component":
            raise MachineAuthoringError("machine adapter must be a component", location + (name, "kind"))
        adapters[name] = adapter
    transition_params = _object(adapters["transition"].get("params", {}), location + ("transition", "params"))
    if spec["selector"] in transition_params:
        raise MachineAuthoringError("transition destination is supplied by next", location + ("transition", "params", spec["selector"]))
    nodes, origins, edges, edge_origins = {}, {}, [], []

    def add(name, declaration, origin):
        """Reserve one generated or source name. Args: name,declaration,origin: Node. Raises: MachineAuthoringError: Collision. Returns: None."""
        if name in nodes:
            raise MachineAuthoringError("machine node names collide", origin)
        nodes[name], origins[name] = deepcopy(declaration), origin

    def connect(source, target, origin, *, control=False):
        """Record a plain IR edge. Args: source,target,origin,control: Connection. Returns: None."""
        edges.append({"source": source, "target": target, **({"kind": "control"} if control else {})})
        edge_origins.append(origin)

    def endpoint(value, names, origin):
        """Resolve a stage-local endpoint. Args: value,names,origin: Address. Raises: MachineAuthoringError: Invalid address. Returns: str."""
        if not isinstance(value, str):
            raise MachineAuthoringError("stage endpoint requires node.port", origin)
        matches = [name for name in names if value.startswith(name + ".") and value[len(name) + 1:]]
        if len(matches) != 1:
            raise MachineAuthoringError("stage endpoint must address one local node", origin)
        return value

    add("input", {"kind": "input"}, location)
    add("output", {"kind": "output"}, location)
    add("read", {"state": {**state, "operation": "read"}}, location + ("state",))
    add("resume", adapters["resume"], location + ("resume",))
    add("dispatch", {"router": {"cases": [
        {"id": name, "predicate": {"field": spec["selector"], "operator": "eq", "value": name}}
        for name in stages], "default": "unrouted"}}, location + ("selector",))
    connect("input.value", "read.control", location + ("state",), control=True)
    connect("input.value", "resume.initial", location + ("resume",))
    connect("read.value", "resume.previous", location + ("resume",))
    connect("resume.result", "dispatch.value", location + ("selector",))
    # Reserve framework names before stage expansion so collisions never overwrite.
    add("merge", adapters["merge"], location + ("merge",))
    add("write", {"state": {**state, "operation": "write"}}, location + ("state",))
    for name, source in stages.items():
        stage_path = location + ("stages", name)
        stage = _object(source, stage_path,
                        allowed={"node", "nodes", "inputs", "entry", "output", "edges", "next"}, required={"next"})
        if "node" in stage:
            if set(stage) != {"node", "next"}:
                raise MachineAuthoringError("single-node stage only accepts node and next", stage_path)
            add(name, _object(stage["node"], stage_path + ("node",)), stage_path + ("node",))
            inputs, entry, output = [name + ".value"], name + ".control", name + ".result"
        else:
            compound = _object(stage, stage_path, required={"nodes", "inputs", "entry", "output", "edges"})
            local = _object(compound["nodes"], stage_path + ("nodes",))
            if not local or len(local) > 128:
                raise MachineAuthoringError("compound stage requires 1 to 128 nodes", stage_path + ("nodes",))
            for node_id, node in local.items():
                add(node_id, _object(node, stage_path + ("nodes", node_id)), stage_path + ("nodes", node_id))
            inputs = compound["inputs"]
            if not isinstance(inputs, list) or not inputs:
                raise MachineAuthoringError("stage inputs must be a nonempty array", stage_path + ("inputs",))
            inputs = [endpoint(value, local, stage_path + ("inputs", i)) for i, value in enumerate(inputs)]
            entry = endpoint(compound["entry"], local, stage_path + ("entry",))
            output = endpoint(compound["output"], local, stage_path + ("output",))
            if not isinstance(compound["edges"], list) or len(compound["edges"]) > 1024:
                raise MachineAuthoringError("stage edges must be an array of at most 1024 connections", stage_path + ("edges",))
            for i, edge in enumerate(compound["edges"]):
                edge_path = stage_path + ("edges", i)
                if not isinstance(edge, str) or len(parts := edge.split("->")) != 2:
                    raise MachineAuthoringError("stage edge requires source.port -> target.port", edge_path)
                connect(endpoint(parts[0].strip(), local, edge_path), endpoint(parts[1].strip(), local, edge_path), edge_path)
        for i, target in enumerate(inputs):
            connect("resume.result", target, stage_path + (("node",) if "node" in stage else ("inputs", i)))
        connect("dispatch." + name, entry, stage_path + (("node",) if "node" in stage else ("entry",)), control=True)
        destinations = _object(stage["next"], stage_path + ("next",))
        if not destinations or len(destinations) > 128:
            raise MachineAuthoringError("stage next requires 1 to 128 outcomes", stage_path + ("next",))
        route = name + "_route"
        add(route, {"router": {"cases": [{"id": outcome,
            "predicate": {"field": spec["outcome"], "operator": "eq", "value": outcome}} for outcome in destinations],
            "default": "unrouted"}}, stage_path + ("next",))
        connect(output, route + ".value", stage_path + ("next",))
        for outcome, destination in destinations.items():
            branch_path = stage_path + ("next", outcome)
            if not isinstance(destination, str) or destination not in stages and destination not in exits:
                raise MachineAuthoringError("next destination must name a declared stage or exit", branch_path)
            transition = prefix + name + "_" + outcome
            node = deepcopy(adapters["transition"])
            node["params"] = {**transition_params, spec["selector"]: destination}
            add(transition, node, branch_path)
            connect(output, transition + ".value", branch_path)
            connect(route + "." + outcome, transition + ".control", branch_path, control=True)
            connect(transition + ".result", "merge.values", branch_path)
    connect("merge.result", "write.write", location + ("merge",))
    connect("write.value", "output.result", location + ("state",))
    return {**{key: value for key, value in data.items() if key != "machine"}, "nodes": nodes, "edges": edges}, origins, edge_origins
