"""Export one reviewed legacy example as an explicit editable operation graph.

This is an offline authoring helper, not an Agent factory or runtime template.
Each exported file is independently parsed and executed by the normal SDK.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml


class FlowMapping(dict):
    """Use ordinary YAML flow mappings for compact leaf declarations."""


def compact_yaml(document):
    """Render readable compact nodes without changing graph semantics.

    Args:
        document: Expanded standalone authoring data.
    Returns:
        str: YAML using real mappings, references and explicit graph edges.
    """
    class Dumper(yaml.SafeDumper):
        """Local dumper; do not change application-wide YAML behavior."""

    def represent(dumper, value):
        """Render one leaf. Args: dumper,value: YAML writer/data. Returns: MappingNode."""
        return dumper.represent_mapping("tag:yaml.org,2002:map", value.items(), flow_style=True)

    def visit(value):
        """Compact leaf maps. Args: value: Authoring subtree. Returns: Equivalent YAML data."""
        if isinstance(value, dict):
            selected = FlowMapping if "component" in value or "predicate" in value or "state" in value else dict
            return selected((key, visit(item)) for key, item in value.items())
        if isinstance(value, list):
            return [visit(item) for item in value]
        return value

    Dumper.add_representer(FlowMapping, represent)
    return yaml.dump(visit(document), Dumper=Dumper, sort_keys=False, allow_unicode=True,
                     default_flow_style=None, width=180)


def build_document(config):
    """Expand the reviewed modular pipeline without loading components.

    Args:
        config: Legacy YAML data containing configured component references.
    Raises:
        ValueError: An unreviewed strategy or component layout is requested.
    Returns:
        dict: Standalone concise AgentGraph authoring document.
    """
    if config["agent_type"] not in {"modular_agent", "reflection_agent", "multi_agent", "uground_agent"}:
        raise ValueError("strategy migration has not passed its sequential gate")
    multi = config["agent_type"] == "multi_agent"
    grounded = config["agent_type"] == "uground_agent"
    reflection = config["agent_type"] in {"reflection_agent", "multi_agent"}
    components = config["agent"]["components"]
    if components.get("memory", {}).get("name") != "sliding_window_memory":
        raise ValueError("only the reviewed sliding-window memory layout is supported")
    if components.get("planner") and not multi:
        raise ValueError("planner migration has not passed its sequential gate")
    perceptions = components["perception"]
    perceptions = perceptions if isinstance(perceptions, list) else [perceptions]
    count = len(perceptions)
    names = [item["name"] for item in perceptions]
    policies = {"max_steps": 15, "max_activations": 65000}
    nodes = {"input": {"kind": "input"}, "output": {"kind": "output"}}
    edges = []
    routes = {}

    def connect(source, target, **extra):
        """Append one declared edge. Args: source,target,extra: Endpoints/options. Returns: None."""
        edges.append({"source": source, "target": target, **extra} if extra else source + " -> " + target)

    def operation(name, op, *, role="memory", contract="frame", params=None, dependencies=None):
        """Declare one operation node. Args: name,op,role,contract,params,dependencies: Schema. Returns: None."""
        identifier = "workflow_setup" if role == "action_executor" else "workflow_state" if role == "memory" else "workflow_" + role
        nodes[name] = {"component": f"agent.{role}:{identifier}",
            "contract": {"id": "zhixing.workflow." + contract, "version": "1.0"},
            "params": {"operation": op, **(params or {})}}
        if dependencies:
            nodes[name]["dependencies"] = dependencies

    def phase(name, node, destinations):
        """Route one role result through YAML edges. Args: name,node,destinations: Stage. Returns: None."""
        routes[name] = name
        router = name + "_route"
        nodes[router] = {"router": {"cases": [{"id": route,
            "predicate": {"field": "route", "operator": "eq", "value": route}} for route in destinations],
            "default": "unrouted"}}
        connect(node + ".result", router + ".value")
        for route, target in destinations.items():
            transition = name + "_" + route
            operation(transition, "transition", params={"target": target})
            connect(node + ".result", transition + ".value")
            connect(router + "." + route, transition + ".control", kind="control")
            connect(transition + ".result", "merge.values")

    state = {"key": "migrated_workflow", "data_type": "workflow_frame", "scope": "run", "operation": "read"}
    nodes["read"] = {"state": state}
    operation("resume", "resume", contract="resume")
    connect("input.value", "read.control", kind="control")
    connect("input.value", "resume.initial")
    connect("read.value", "resume.previous")
    nodes["dispatch"] = {"router": {"cases": [], "default": "unrouted"}}
    connect("resume.result", "dispatch.value")

    operation("observe_request", "observe_request", contract="observe_request")
    nodes["observe"] = {"component": "zhixing.runtime:device_observe",
        "contract": {"id": "zhixing.service.device_observe", "version": "2.0"}}
    operation("observed", "observed", contract="observed")
    connect("resume.result", "observe_request.value")
    connect("dispatch.observe", "observe_request.control", kind="control")
    connect("observe_request.request", "observe.request")
    connect("resume.result", "observed.value")
    connect("observe.observation", "observed.observation")
    summarize = grounded and config["agent"].get("strategy", {}).get("summarize_steps", True)
    phase("observe", "observed", {"ok": "summary" if summarize else "verify" if components.get("verifier") else "select"})

    if components.get("verifier"):
        verifier = components["verifier"]
        verifier_params = {"fallback_count": count, "feedback_style": "reflection" if reflection else "modular",
                           "source": "critic" if multi else "reflection" if reflection else "verifier_correction"}
        if verifier.get("llm"):
            verifier_params.update(component_name=verifier["name"], component_params=verifier.get("params", {}))
            verifier_model = {"namespace": "llm", **verifier["llm"]}
            verifier_model["params"] = {key: {"secret_ref": value[2:-1]} if isinstance(value, str) and value.startswith("${") else value
                                       for key, value in verifier_model.get("params", {}).items()}
            verifier_dependencies = {"llm": verifier_model}
        else:
            verifier_dependencies = {"tool": {"namespace": "agent.verifier", **verifier}}
        operation("verify", "verify", role="verifier", params=verifier_params, dependencies=verifier_dependencies)
        phase("verify", "verify", {"continue": "select", "correction": "execute"})
    operation("select", "select")
    phase("select", "select", {"p" + str(i): "perceive_" + str(i) for i in range(count)})
    for i, perception in enumerate(perceptions):
        name = "perceive_" + str(i)
        operation(name, "perceive", role="perception", params={"perception_index": i, "fallback_count": count},
            dependencies={"tool": {"namespace": "agent.perception", **perception}})
        phase(name, name, {"ok": "plan_step" if multi and config["agent"].get("strategy", {}).get("manager_each_step", True) else "lookup",
            "retry": "verify" if components.get("verifier") and not reflection else "select", "failed": "execute"})
    if multi:
        planner = components["planner"]
        planner_model = {"namespace": "llm", **planner["llm"]}
        planner_model["params"] = {key: {"secret_ref": value[2:-1]} if isinstance(value, str) and value.startswith("${") else value
                                  for key, value in planner_model.get("params", {}).items()}
        for name, destination in (("plan_initial", "observe"), ("plan_step", "lookup")):
            operation(name, name, role="planner", params={"component_name": planner["name"], "component_params": planner.get("params", {})},
                dependencies={"llm": planner_model})
            phase(name, name, {"ok": destination})
    operation("lookup", "lookup", params={"use_experience_cache": config["agent"].get("strategy", {}).get("use_experience_cache", not reflection and not grounded)})
    phase("lookup", "lookup", {"hit": "commit_cache", "miss": "reason"})
    reasoning = components["reasoning"]
    model = reasoning.get("llm") or config.get("global_config", {}).get("default_llm")
    model = {"namespace": "llm", **model}
    model["params"] = {key: {"secret_ref": value[2:-1]} if isinstance(value, str) and value.startswith("${") else value
                       for key, value in model.get("params", {}).items()}
    operation("reason", "reason", role="reasoning", params={"component_name": reasoning["name"],
        "component_params": reasoning.get("params", {}), "error_prefix": "Planner Error" if grounded else "Operator Error" if multi else "Brain Error"}, dependencies={"llm": model})
    phase("reason", "reason", {"ok": "ground" if grounded else "commit", "failed": "execute"})
    if grounded:
        grounder = components["grounder"]
        ground_model = {"namespace": "llm", **grounder["llm"]}
        ground_model["params"] = {key: {"secret_ref": "UGROUND_API_KEY"} if key == "api_key" else value
                                 for key, value in ground_model.get("params", {}).items()}
        operation("ground", "ground", role="grounder", params={"component_name": grounder["name"], "component_params": grounder.get("params", {})},
                  dependencies={"llm": ground_model})
        phase("ground", "ground", {"ok": "commit", "failed": "execute"})
        if summarize:
            operation("summary", "summary", role="reasoning", params={"summary_prompt_file": config["agent"].get("strategy", {}).get(
                "summary_prompt_file", "summary_seeact_uground.md")}, dependencies={"llm": model})
            phase("summary", "summary", {"ok": "select"})
        if config["agent"].get("strategy", {}).get("hide_automation_ui_on_reset", True):
            operation("setup", "setup", role="action_executor", contract="setup")
            phase("setup", "setup", {"ok": "observe"})
    for name, source in (("commit", "operator" if multi else "actor" if reflection else "brain"), ("commit_cache", "memory_cache")):
        operation(name, "commit_grounded" if grounded and name == "commit" else "commit", params={"source": source})
        phase(name, name, {"ok": "execute", "hit": "execute", "miss": "execute"})

    operation("action_request", "action_request", contract="action_request")
    nodes["execute"] = {"component": "zhixing.runtime:action_executor",
        "contract": {"id": "zhixing.service.action_executor", "version": "1.0"}, "primary": True}
    operation("executed", "executed", contract="executed")
    connect("resume.result", "action_request.value")
    connect("dispatch.execute", "action_request.control", kind="control")
    connect("action_request.request", "execute.request")
    connect("resume.result", "executed.value")
    connect("execute.result", "executed.ack")
    phase("execute", "executed", {"ok": "observe"})
    for name in routes:
        if name in {"observe", "execute"}:
            continue
        connect("resume.result", name + ".value")
        connect("dispatch." + name, name + ".control", kind="control")
    nodes["dispatch"]["router"]["cases"] = [{"id": name,
        "predicate": {"field": "target", "operator": "eq", "value": name}} for name in routes]
    operation("merge", "merge", contract="merge")
    nodes["write"] = {"state": {**state, "operation": "write"}}
    connect("merge.result", "write.write")
    connect("write.value", "output.result")
    graph = {"policies": policies, "nodes": nodes, "edges": edges}
    return {"kind": "agent_graph", "schema_version": 1, "policies": policies,
        "nodes": {"input": {"kind": "input"},
            "initialize": {"component": "agent.memory:workflow_state",
                "contract": {"id": "zhixing.workflow.initialize", "version": "1.0"},
                "params": {"operation": "initialize", "memory_params": components.get("memory", {}).get("params", {}),
                    "perception_names": names, "target": "plan_initial" if multi else "setup" if grounded and config["agent"].get(
                        "strategy", {}).get("hide_automation_ui_on_reset", True) else "observe"}},
            "workflow": {"loop": {"inputs": {"value": "value"}, "outputs": {"result": "result"},
                "until": {"field": "result.terminal_status", "operator": "truthy"}, "max_iterations": 500,
                "max_activations": 60000, "body": {"inputs": {"value": "value"}, "outputs": {"result": "result"},
                    "max_activations": 100, "graph": graph}}},
            "finish": {"component": "agent.memory:workflow_state",
                "contract": {"id": "zhixing.workflow.finish", "version": "1.0"}, "params": {"operation": "finish"}},
            "output": {"kind": "output"}},
        "edges": ["input.task -> initialize.task", "initialize.result -> workflow.value",
                  "workflow.result -> finish.value", "finish.result -> output.result"]}


def main():
    """Write one standalone reviewed graph. Raises: ValueError: Unsupported input. Returns: None."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    document = build_document(yaml.safe_load(args.source.read_text()))
    args.destination.write_text(compact_yaml(document))


if __name__ == "__main__":
    main()
