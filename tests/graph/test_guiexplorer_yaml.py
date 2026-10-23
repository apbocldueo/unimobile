"""GUI-explorer authoring identity, source attribution and import isolation."""

import ast
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from zhixing.graph import GraphRole, load_graph_yaml
from zhixing.guiexplorer import build_guiexplorer_graph
from zhixing.sdk import compile_agent


ROOT = Path(__file__).resolve().parents[2]
YAML = ROOT / "examples/graphs/guiexplorer_online.yaml"


def test_actual_yaml_identity_and_shared_components():
    """Verify exact IR equality, four role families and actual shared component references.

    Returns:
        None.
    """
    actual = compile_agent(load_graph_yaml(YAML))
    expected = compile_agent(build_guiexplorer_graph())
    assert actual.graph == expected.graph and actual.canonical_hash == expected.canonical_hash
    graph = next(node for node in actual.graph.nodes if node.id == "online").loop.body.graph
    assert {node.role for node in graph.nodes if node.role} == {
        GraphRole.MEMORY, GraphRole.PERCEPTION, GraphRole.REASONING, GraphRole.ACTION_EXECUTOR}
    for node_id, component in (("resume", "m3a_resume"), ("commit", "m3a_commit"),
            ("ready", "m3a_pass"), ("memory", "sliding_window_memory")):
        node = next(node for node in graph.nodes if node.id == node_id)
        assert node.component.candidates[0].name == component


def test_compile_and_cli_dry_run_are_inert(tmp_path):
    """Compile in a fresh interpreter without optional imports, effects or key resolution.

    Args:
        tmp_path: Empty external output directory.
    Returns:
        None.
    """
    code = '''
import sys, threading
from zhixing.graph import load_graph_yaml
from zhixing.guiexplorer import build_guiexplorer_graph
from zhixing.sdk import compile_agent
before=set(threading.enumerate())
assert compile_agent(load_graph_yaml(sys.argv[1])).canonical_hash==compile_agent(build_guiexplorer_graph()).canonical_hash
assert set(threading.enumerate())==before
assert not {'numpy','cv2','requests','aiohttp','uiautomator2','imagehash','openai','torch','transformers'} & set(sys.modules)
'''
    env = {key: value for key, value in os.environ.items() if key not in ("OPENAI_API_KEY", "OPENAI_API_MODEL", "RAG_SERVER_ENDPOINT")}
    process = subprocess.run([sys.executable, "-c", code, str(YAML)], cwd=ROOT, env=env,
        capture_output=True, text=True, timeout=20)
    assert process.returncode == 0, process.stdout + process.stderr
    dry = subprocess.run([sys.executable, str(ROOT / "examples/sdk/guiexplorer_online.py"), "--dry-run",
        "--artifact-root", str(tmp_path)], cwd=ROOT, env={**env, "PYTHONPATH": str(ROOT)},
        capture_output=True, text=True, timeout=20)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert json.loads(dry.stdout) == {"graph_hash": build_guiexplorer_graph().canonical_hash(), "execution_evidence": False}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("settings", [{"max_rounds": True}, {"max_rounds": -1}, {"max_rounds": 1000},
    {"top_k": 0}, {"top_k": True}, {"threshold": float("nan")}, {"threshold": True},
    {"model_params": {"unknown": 1}}, {"model_params": {"api_key": "resolved-secret-not-allowed"}}, {"retrieval_endpoint": ""}])
def test_invalid_public_configuration(settings):
    """Reject invalid configurations before any runtime service is constructed.

    Args:
        settings: Invalid public authoring configuration.
    Returns:
        None.
    """
    with pytest.raises(ValueError):
        build_guiexplorer_graph(**settings)


class NormalizeSource(ast.NodeTransformer):
    """Ignore only recorded documentation/import/Pillow compatibility adaptations."""

    def visit_Import(self, node):
        """Remove imports from an algorithm-only comparison.

        Args:
            node: Original or adapted import AST.
        Returns:
            None: No executable algorithm is removed.
        """
        return None

    visit_ImportFrom = visit_Import

    def visit_FunctionDef(self, node):
        """Drop source docstrings while retaining every executable operation.

        Args:
            node: Original or adapted function AST.
        Returns:
            ast.AST: Recursively normalized executable function.
        """
        if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant) and isinstance(node.body[0].value.value, str):
            node.body = node.body[1:]
        return self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Attribute(self, node):
        """Normalize Pillow's renamed LANCZOS constant, without changing interpolation.

        Args:
            node: Possible Image.Resampling.LANCZOS expression.
        Returns:
            ast.AST: Original constant spelling for comparison only.
        """
        if node.attr == "LANCZOS" and isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name) and node.value.value.id == "Image" and node.value.attr == "Resampling":
            node.value = ast.Name(id="Image", ctx=ast.Load())
        return self.generic_visit(node)


def test_pinned_source_integrity_and_executable_algorithm_identity():
    """Verify raw fixture hashes, selected executable definitions and exact prompt values.

    Returns:
        None.
    """
    from zhixing.plugins.agent.guiexplorer import source, prompts

    origin = json.loads((Path(source.__file__).with_name("source-origin.json")).read_text())
    normalizer = NormalizeSource()
    for path, entry in origin["files"].items():
        raw = (ROOT / "tests/fixtures/guiexplorer" / (path.replace("/", "__") + ".txt")).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        if path == "utils/prompt_templates.py":
            values = {}
            exec(raw, values)
            for name in entry["selected"]:
                assert getattr(prompts, name) == values[name]
            continue
        if path == "utils/utils.py":
            lines = raw.decode().splitlines(keepends=True)
            nodes = []
            for name in entry["selected"]:
                start = next(i for i, line in enumerate(lines) if line.startswith("def " + name + "("))
                end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith(("def ", "from ", "import "))), len(lines))
                nodes.extend(ast.parse("".join(lines[start:end])).body)
        else:
            nodes = ast.parse(raw.decode()).body
        selected = entry["selected"]
        for node in nodes:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) or (isinstance(selected, list) and node.name not in selected):
                continue
            adapted = ast.parse(inspect.getsource(getattr(source, node.name))).body[0]
            assert ast.dump(normalizer.visit(node), include_attributes=False) == ast.dump(normalizer.visit(adapted), include_attributes=False), (path, node.name)
    assert not hasattr(source, "GUI_explorer")
    from zhixing.plugins.agent.m3a import source as m3a
    for name in ("_generate_ui_element_description", "validate_ui_element", "_logical_to_physical", "_ui_element_logical_corner", "_generate_ui_elements_description_list"):
        assert getattr(source, name) is getattr(m3a, name)
