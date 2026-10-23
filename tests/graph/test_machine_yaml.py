"""Generic routing-table lowering, source errors and executable editability."""

from copy import deepcopy
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from zhixing.graph import (
    ContractPort, InvocationAdapterKind, NodeContract, NodeContractCatalog,
    NodeContractRef, PortCardinality, PortDirection, compile_graph_yaml_data, load_graph_yaml,
)
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/graphs/appagent.yaml"
APPAGENT_HASH = "sha256:d353781fa1e2caea47157a6da8bcfa032ce0ff8d53424e9a055180b58154597d"


def _machine(document):
    """Locate the editable example table. Args: document: Parsed YAML. Returns: dict."""
    return document["nodes"]["workflow"]["loop"]["body"]["graph"]["machine"]


def test_appagent_lowering_preserves_previous_canonical_graph_and_source():
    """Freeze the pre-simplification graph, including every budget and dependency.

    Raises:
        AssertionError: Lowering changes executable semantics or mutates the source.
    Returns:
        None.
    """
    source = yaml.safe_load(EXAMPLE.read_text())
    before = deepcopy(source)
    result = compile_graph_yaml_data(source)
    assert result.is_success, result.diagnostics
    assert source == before
    assert result.graph.canonical_hash() == APPAGENT_HASH
    prefix = ("nodes", "workflow", "loop", "body", "graph", "machine")
    locations = {item.logical_node_path: item.property_path for item in result.source_map}
    assert locations[("workflow", "verify")] == prefix + ("stages", "verify", "node")
    assert locations[("workflow", "verify_correction")] == prefix + ("stages", "verify", "next", "correction")
    assert locations[("workflow", "observe")] == prefix + ("stages", "observe", "nodes", "observe")
    assert locations[("workflow", "write")] == prefix + ("state",)
    # Both wire formats remain independently loadable; lowering is not a runtime preset.
    expanded = result.graph.model_dump(mode="json", exclude_none=True)
    expanded["kind"] = "agent_graph"
    assert compile_graph_yaml_data(expanded).graph.canonical_hash() == APPAGENT_HASH
    changed = deepcopy(source)
    _machine(changed)["stages"]["reason"]["node"]["params"]["component_params"]["preset"] = "default"
    assert compile_graph_yaml_data(changed).graph.canonical_hash() != APPAGENT_HASH


@pytest.mark.parametrize("case,suffix", [
    ("unknown", ("statte",)),
    ("missing", ("selector",)),
    ("target", ("stages", "verify", "next", "continue")),
    ("collision", ("stages", "resume", "node")),
    ("stage_typo", ("stages", "verify", "nexxt")),
    ("mixed", ("stages", "verify")),
    ("empty", ("stages", "verify", "next")),
    ("not_mapping", ("stages", "verify", "next")),
    ("bad_selector", ("outcome",)),
    ("adapter", ("transition", "component")),
    ("destination_param", ("transition", "params", "target")),
    ("endpoint", ("stages", "observe", "inputs", 0)),
    ("edge", ("stages", "observe", "edges", 0)),
    ("stage_bound", ("stages",)),
    ("node_typo", ("stages", "verify", "node", "paramz")),
])
def test_invalid_machine_reports_author_source(case, suffix):
    """Reject typos, unbounded tables and ambiguous plumbing at their source.

    Args:
        case: Controlled invalid declaration.
        suffix: Expected author-visible location within the machine.
    Raises:
        AssertionError: Invalid YAML succeeds, raises or loses its source location.
    Returns:
        None.
    """
    source = yaml.safe_load(EXAMPLE.read_text())
    machine = _machine(source)
    stage = machine["stages"]["verify"]
    if case == "unknown":
        machine["statte"] = {}
    elif case == "missing":
        machine.pop("selector")
    elif case == "target":
        stage["next"]["continue"] = "absent"
    elif case == "collision":
        machine["stages"]["resume"] = machine["stages"].pop("verify")
        machine["stages"]["observe"]["next"]["ok"] = "resume"
        machine["stages"]["perceive_0"]["next"]["retry"] = "resume"
        machine["stages"]["perceive_1"]["next"]["retry"] = "resume"
    elif case == "stage_typo":
        stage["nexxt"] = {}
    elif case == "mixed":
        stage["nodes"] = {}
    elif case == "empty":
        stage["next"] = {}
    elif case == "not_mapping":
        stage["next"] = []
    elif case == "bad_selector":
        machine["outcome"] = []
    elif case == "adapter":
        machine["transition"]["component"] = {}
    elif case == "destination_param":
        machine["transition"]["params"]["target"] = "ignored"
    elif case == "endpoint":
        machine["stages"]["observe"]["inputs"][0] = "reason.value"
    elif case == "edge":
        machine["stages"]["observe"]["edges"][0] = "too -> many -> ports"
    elif case == "stage_bound":
        machine["stages"] = {"stage_" + str(i): deepcopy(stage) for i in range(129)}
    else:
        stage["node"]["paramz"] = {}
    result = compile_graph_yaml_data(source)
    assert not result.is_success
    expected = ("nodes", "workflow", "loop", "body", "graph", "machine") + suffix
    assert any(item.path == expected for item in result.diagnostics), result.diagnostics


def _toy_document(selector, outcome):
    """Build an unrelated no-device state machine using caller-owned adapters.

    Args:
        selector: Custom program-counter field.
        outcome: Custom branch-result field.
    Returns:
        tuple: Source document and extension contracts.
    """
    def node(name, contract="frame"):
        """Declare a test component. Args: name,contract: References. Returns: dict."""
        return {"component": "test.machine:" + name, "contract": {"id": "test.machine." + contract, "version": "1"}}

    contracts = []
    for name, inputs in (("frame", ("value",)), ("resume", ("initial", "previous")), ("merge", ("values",))):
        contracts.append(NodeContract(ref=NodeContractRef(id="test.machine." + name, version="1"),
            adapter=InvocationAdapterKind.TYPED_INVOKE, ports=(
                ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
                *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=("any",), required=True,
                    cardinality=PortCardinality.MULTIPLE if key == "values" else PortCardinality.SINGLE) for key in inputs),
                ContractPort(id="result", direction=PortDirection.OUTPUT, data_types=("any",)),
            )))
    machine = {"state": {"key": "test_counter", "data_type": "any", "scope": "run"},
        "selector": selector, "outcome": outcome, "resume": node("resume", "resume"),
        "transition": node("shift"), "merge": node("merge", "merge"), "stages": {
            "alpha": {"node": node("alpha"), "next": {"go": "beta"}},
            "beta": {"nodes": {"beta": node("beta"), "tail": node("tail")},
                "inputs": ["beta.value"], "entry": "beta.control", "output": "tail.result",
                "edges": ["beta.result -> tail.value"], "next": {"go": "stop"}},
            "stop": {"node": node("stop"), "next": {"go": "stop"}}}}
    return {"kind": "agent_graph", "schema_version": 1, "nodes": {
        "input": {"kind": "input"}, "work": {"loop": {
            "inputs": {"value": "value"}, "outputs": {"result": "result"},
            "until": {"field": "result.done", "operator": "truthy"},
            "max_iterations": 5, "max_activations": 200,
            "body": {"inputs": {"value": "value"}, "outputs": {"result": "result"},
                "max_activations": 40, "graph": {"machine": machine}}}},
        "output": {"kind": "output"}},
        "edges": ["input.value -> work.value", "work.result -> output.result"]}, NodeContractCatalog(tuple(contracts))


class ToyResolver:
    """Resolve only explicit test operations; no production Agent is constructed."""

    def __init__(self, selector):
        """Collect observed calls. Args: selector: Counter field. Returns: None."""
        self.selector, self.calls = selector, []

    def resolve(self, reference, role):
        """Bind a toy operation from its editable reference.

        Args:
            reference: Component name and generated transition parameters.
            role: Unused optional standard role.
        Returns:
            object: Typed-invoke operation.
        """
        resolver = self

        class Operation:
            """Keep the fake adapter's behavior explicit in the test."""

            def invoke(self, value, runtime):
                """Apply one operation. Args: value,runtime: Input/context. Returns: dict: Frame."""
                if reference.name == "resume":
                    return value["previous"] or value["initial"]
                if reference.name == "merge":
                    assert len(value) == 1
                    return value[0]
                if reference.name == "shift":
                    return {**value, resolver.selector: reference.params[resolver.selector]}
                resolver.calls.append(reference.name)
                return {**value, "done": reference.name == "stop"}

        return Operation()


@pytest.mark.parametrize("selector,outcome", [("phase", "code"), ("program_counter", "result_code")])
def test_generic_routes_are_executable_editable_and_run_isolated(selector, outcome):
    """Run two non-Agent workflows, then edit a route to skip a compound stage.

    Args:
        selector: Caller-owned field read by dispatch and written by transition.
        outcome: Caller-owned field read by the branch router.
    Raises:
        AssertionError: Lowering hides the policy, leaks run state or requires AppAgent.
    Returns:
        None.
    """
    source, catalog = _toy_document(selector, outcome)
    compiled = compile_graph_yaml_data(source, contract_catalog=catalog)
    assert compiled.is_success, compiled.diagnostics
    resolver = ToyResolver(selector)
    plan = bind_execution_plan(compiled.graph, resolver, contract_catalog=catalog)
    for _ in range(2):
        result = GraphExecutionKernel().run(plan, {"value": {selector: "alpha", outcome: "go", "done": False}})
        assert result.status is KernelStatus.SUCCESS, result
        assert result.outputs["result"]["done"]
    assert resolver.calls == ["alpha", "beta", "tail", "stop"] * 2
    source["nodes"]["work"]["loop"]["body"]["graph"]["machine"]["stages"]["alpha"]["next"]["go"] = "stop"
    changed = compile_graph_yaml_data(source, contract_catalog=catalog)
    assert changed.graph.canonical_hash(contract_catalog=catalog) != compiled.graph.canonical_hash(contract_catalog=catalog)
    resolver = ToyResolver(selector)
    result = GraphExecutionKernel().run(bind_execution_plan(changed.graph, resolver, contract_catalog=catalog),
        {"value": {selector: "alpha", outcome: "go", "done": False}})
    assert result.status is KernelStatus.SUCCESS, result
    assert resolver.calls == ["alpha", "stop"]


def test_machine_compiles_without_loading_runtime_components():
    """Check the new compiler path in a fresh interpreter with import canaries.

    Raises:
        AssertionError: YAML compilation imports runtime implementations.
    Returns:
        None.
    """
    code = '''
import importlib.abc, sys
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("zhixing.plugins", "zhixing.devices", "zhixing.engine.agent", "torch", "openai")):
            raise AssertionError("runtime import during compile: " + fullname)
sys.meta_path.insert(0, Guard())
from zhixing.graph import load_graph_yaml
result = load_graph_yaml(sys.argv[1])
assert result.is_success, result.diagnostics
'''
    run = subprocess.run([sys.executable, "-c", code, str(EXAMPLE)], cwd=ROOT,
                         capture_output=True, text=True, timeout=30, check=False)
    assert run.returncode == 0, run.stdout + run.stderr


def test_machine_port_error_and_mixed_forms_remain_source_addressable():
    """Keep ordinary IR port validation and reject simultaneous wire formats.

    Raises:
        AssertionError: Generated plumbing masks an invalid port or source typo.
    Returns:
        None.
    """
    source = yaml.safe_load(EXAMPLE.read_text())
    _machine(source)["stages"]["observe"]["inputs"][0] = "observe_request.missing"
    result = compile_graph_yaml_data(source)
    prefix = ("nodes", "workflow", "loop", "body", "graph", "machine", "stages", "observe", "inputs", 0)
    assert any(item.code == "graph.edge.target_port_unknown" and item.path[:len(prefix)] == prefix
               for item in result.diagnostics), result.diagnostics
    source["nodes"]["workflow"]["loop"]["body"]["graph"]["nodes"] = {}
    result = compile_graph_yaml_data(source)
    assert any(item.path == ("nodes", "workflow", "loop", "body", "graph", "machine") for item in result.diagnostics)


@pytest.mark.parametrize("field,value", [
    ("exits", "done"), ("exits", [{}]), ("exits", [""]),
    ("exits", ["done", "done"]), ("exits", ["alpha"]),
    ("exits", [str(i) for i in range(129)]), ("transition_prefix", []),
])
def test_invalid_exit_and_prefix_are_source_addressable(field, value):
    """Reject malformed optional authoring settings without runtime imports.

    Args:
        field: Optional machine setting being checked.
        value: Invalid shape, duplicate, stage collision or excessive size.
    Raises:
        AssertionError: Compilation succeeds or diagnostics lose the source field.
    Returns:
        None.
    """
    source, catalog = _toy_document("phase", "code")
    source["nodes"]["work"]["loop"]["body"]["graph"]["machine"][field] = value
    result = compile_graph_yaml_data(source, contract_catalog=catalog)
    assert not result.is_success
    assert any(item.path == ("nodes", "work", "loop", "body", "graph", "machine", field)
               for item in result.diagnostics), result.diagnostics


def test_declared_exit_uses_parent_predicate_without_running_a_terminal_stage():
    """Return an explicit exit frame and preserve prefixed transition identity.

    Raises:
        AssertionError: An exit adds an operation, bypasses the Loop or loses mapping.
    Returns:
        None.
    """
    source, catalog = _toy_document("phase", "code")
    loop = source["nodes"]["work"]["loop"]
    machine = loop["body"]["graph"]["machine"]
    machine["stages"] = {"alpha": machine["stages"]["alpha"]}
    machine["stages"]["alpha"]["next"]["go"] = "leave"
    machine.update(exits=["leave"], transition_prefix="go_")
    loop["until"] = {"field": "result.phase", "operator": "eq", "value": "leave"}
    compiled = compile_graph_yaml_data(source, contract_catalog=catalog)
    assert compiled.is_success, compiled.diagnostics
    body = next(node for node in compiled.graph.nodes if node.id == "work").loop.body.graph
    assert "go_alpha_go" in {node.id for node in body.nodes}
    assert "leave" not in {node.id for node in body.nodes}
    location = next(item for item in compiled.source_map if item.logical_node_path == ("work", "go_alpha_go"))
    assert location.property_path[-5:] == ("machine", "stages", "alpha", "next", "go")
    resolver = ToyResolver("phase")
    result = GraphExecutionKernel().run(bind_execution_plan(compiled.graph, resolver, contract_catalog=catalog),
        {"value": {"phase": "alpha", "code": "go", "done": False}})
    assert result.status is KernelStatus.SUCCESS, result
    assert result.outputs["result"]["phase"] == "leave"
    assert resolver.calls == ["alpha"]
