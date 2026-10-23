"""Freeze migrated graph identities while keeping every strategy table editable."""

from copy import deepcopy
from pathlib import Path
import sys

import pytest
import yaml

from scripts.export_legacy_workflow_yaml import build_document
from scripts.simplify_workflow_yaml import main, render_document, simplify_document
from zhixing.graph import compile_graph_yaml_data


ROOT = Path(__file__).resolve().parents[2]
CASES = [
    ("appagent", "agent_appagent.yaml", "d353781fa1e2caea47157a6da8bcfa032ce0ff8d53424e9a055180b58154597d"),
    ("guicourse", "agent_guicourse.yaml", "d38b3f1ee50349a35c5fdadf9bbb00699b6bce420bed965c2ca0a313a5d04f77"),
    ("showui", "agent_showui.yaml", "220c911048caf337024efb582de76e23265f7e0371b0f351803daf958b7766fd"),
    ("os_genesis", "agent_os_genesis.yaml", "9f6c1c3396b5a1ce8d839f77e656eeb2daa11d42550003a1db6a7866c4b40ba4"),
    ("gui_schema_cn", "agent_gui_schema_cn.yaml", "a978b02f16273e0ad81b2dae39ca53cbce4e8fc51e581247a61e3cd5e5abf2f5"),
    ("mobile_agent", "agent_mobileagent.yaml", "212436dcd714fe59a1875708c9e0516c5a0ca169f38f9910548a32735bb09b44"),
    ("mobile_agent_v2_migrated", "agent_mobile_agent_v2.yaml", "212436dcd714fe59a1875708c9e0516c5a0ca169f38f9910548a32735bb09b44"),
    ("mobile_use", "agent_mobile_use_multi.yaml", "49d889df600609fd90c751c3f9f0abf0e6e524e349dc205a60cd227aa76f6c8d"),
    ("uground", "agent_uground.yaml", "f5df6d088706b8786470729996f4b7ab1b97ad157b7e55abf88eda7c15d30eea"),
]


@pytest.mark.parametrize("name,legacy,digest", CASES, ids=[row[0] for row in CASES])
def test_simplified_workflow_identity_and_editability(name, legacy, digest):
    """Keep the exact graph and expose real branch/parameter edits for each Agent.

    Args:
        name: Independently migrated graph filename stem.
        legacy: Retained original configuration filename.
        digest: Canonical graph identity frozen before simplification.
    Raises:
        AssertionError: Semantics drift, a strategy edit is ignored or legacy is lost.
    Returns:
        None.
    """
    path = ROOT / "examples/graphs" / (name + ".yaml")
    source = yaml.safe_load(path.read_text())
    before = deepcopy(source)
    compiled = compile_graph_yaml_data(source)
    assert compiled.is_success, compiled.diagnostics
    assert compiled.graph.canonical_hash() == "sha256:" + digest
    assert source == before
    assert (ROOT / "examples" / legacy).is_file()
    machine = source["nodes"]["workflow"]["loop"]["body"]["graph"]["machine"]
    assert {"observe", "reason", "execute"} <= machine["stages"].keys()
    assert "nodes" in machine["stages"]["observe"] and "nodes" in machine["stages"]["execute"]
    assert len(machine["stages"]) >= 7
    machine["stages"]["reason"]["next"]["ok"] = "execute"
    edited = compile_graph_yaml_data(source)
    assert edited.is_success, edited.diagnostics
    assert edited.graph.canonical_hash() != compiled.graph.canonical_hash()
    body = next(node for node in edited.graph.nodes if node.id == "workflow").loop.body.graph
    branch = next(node for node in body.nodes if node.id == "reason_ok")
    assert branch.component.candidates[0].params["target"] == "execute"
    source = before
    reason = source["nodes"]["workflow"]["loop"]["body"]["graph"]["machine"]["stages"]["reason"]["node"]
    reason["params"]["error_prefix"] = "Author edited error label"
    edited_parameter = compile_graph_yaml_data(source)
    assert edited_parameter.is_success, edited_parameter.diagnostics
    assert edited_parameter.graph.canonical_hash() != compiled.graph.canonical_hash()
    location = next(item for item in compiled.source_map if item.logical_node_path == ("workflow", "reason_ok"))
    assert location.property_path[-5:] == ("machine", "stages", "reason", "next", "ok")


def test_offline_folder_round_trip_keeps_source_and_serialized_graph():
    """Validate the optional tool without introducing a runtime dependency.

    Raises:
        AssertionError: Conversion mutates input, minifies the stage table or drifts.
    Returns:
        None.
    """
    source = build_document(yaml.safe_load((ROOT / "examples/agent_appagent.yaml").read_text()))
    before = deepcopy(source)
    compact = simplify_document(source)
    rendered = render_document(compact)
    assert source == before
    assert "          machine:\n" in rendered and "            stages:\n" in rendered
    assert compile_graph_yaml_data(yaml.safe_load(rendered)).graph.canonical_hash() == compile_graph_yaml_data(source).graph.canonical_hash()


def test_offline_folder_rejects_semantic_loss_without_writing(tmp_path, monkeypatch):
    """Refuse unsupported plumbing before touching an existing destination.

    Args:
        tmp_path: Isolated source and destination.
        monkeypatch: Explicit offline CLI arguments.
    Raises:
        AssertionError: Unsupported graph semantics are dropped or output is modified.
    Returns:
        None.
    """
    document = build_document(yaml.safe_load((ROOT / "examples/agent_appagent.yaml").read_text()))
    document["nodes"]["workflow"]["loop"]["body"]["graph"]["nodes"]["commit_route"]["router"]["default"] = "another_default"
    assert compile_graph_yaml_data(document).is_success
    source, destination = tmp_path / "input.yaml", tmp_path / "existing.yaml"
    source.write_text(render_document(document))
    destination.write_text("keep this file\n")
    monkeypatch.setattr(sys, "argv", ["simplify_workflow_yaml", str(source), str(destination)])
    with pytest.raises(ValueError, match="canonical graph identity"):
        main()
    assert destination.read_text() == "keep this file\n"
