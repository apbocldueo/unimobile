"""Run installed AutoDroid outside the source tree with all heavy imports blocked."""

import importlib.abc
import json
from pathlib import Path
import sys

import yaml


class BlockHeavy(importlib.abc.MetaPathFinder):
    """Fail if the base install eagerly requests an optional runtime."""

    def find_spec(self, fullname, path=None, target=None):
        """Reject heavy packages while allowing ordinary import resolution.

        Args:
            fullname: Requested module name.
            path: Standard finder search path.
            target: Standard reload target.
        Raises:
            AssertionError: An optional dependency is requested.
        Returns:
            None: Delegate all permitted imports.
        """
        if fullname.split(".")[0] in {"torch", "InstructorEmbedding", "sentence_transformers", "transformers", "openai", "cv2"}:
            raise AssertionError("unexpected optional import: " + fullname)
        return None


sys.meta_path.insert(0, BlockHeavy())

from PIL import Image
import zhixing
from zhixing.autodroid import build_autodroid_graph
from zhixing.components import RunStatus
from zhixing.graph import compile_graph_yaml_data, load_graph_yaml
from zhixing.knowledge.autodroid import InstructorEncoder
from zhixing.resources import read_prompt
from zhixing.sdk import AgentRunConfig, compile_agent

assert Path(zhixing.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert read_prompt("reasoning_autodroid.md")
assert load_graph_yaml("autodroid_online.yaml").graph.canonical_hash() == build_autodroid_graph().canonical_hash()


class Model:
    """Select tap, input, BACK and completion through the actual prompt protocol."""

    def __init__(self):
        """Initialize a deterministic four-decision script."""
        self.decisions = iter([{"id": 0}, {"id": 1, "action": "input", "input_text": "hello"}, {"id": 2}, {"id": -1}])

    def generate(self, prompt, images=None):
        """Return the next choice with no external model.

        Args:
            prompt: Production prompt, required to contain UI data.
            images: Expected None.
        Returns:
            str: Decision JSON.
        """
        assert "Current UI state" in prompt and images is None
        return json.dumps(next(self.decisions))


class Device:
    """Minimal Android-compatible device for installed executor verification."""

    platform, serial, w, h = "android", "installed-fake", 100, 200

    def __init__(self):
        """Initialize confirmed effect recording."""
        self.effects = []

    def screenshot(self, path):
        """Write a valid PNG at the requested artifact path.

        Args:
            path: Service-owned destination.
        Returns:
            str: Written PNG path.
        """
        Image.new("RGB", (100, 200)).save(path)
        return path

    def get_xml(self, path):
        """Write one button and editable field for current-frame grounding.

        Args:
            path: XML artifact destination.
        Returns:
            str: Written hierarchy content.
        """
        value = '<hierarchy><node package="org.example.notes" text="New note" clickable="true" bounds="[0,0][80,40]"/><node package="org.example.notes" class="EditText" bounds="[0,40][80,80]"/></hierarchy>'
        Path(path).write_text(value, encoding="utf-8")
        return value

    def tap(self, x, y):
        """Record a production executor tap.

        Args:
            x: Horizontal coordinate.
            y: Vertical coordinate.
        Returns:
            None.
        """
        self.effects.append(("tap", x, y))

    def input_text(self, text):
        """Record a production executor input operation.

        Args:
            text: Requested input text.
        Returns:
            None.
        """
        self.effects.append(("text", text))

    def go_back(self):
        """Record a production executor BACK operation."""
        self.effects.append(("back",))


def encode(self, texts, instruction):
    """Supply deterministic vectors through the normal lazy encoder seam.

    Args:
        self: Lazy encoder configuration.
        texts: Sentences to encode.
        instruction: Memory's declared embedding convention.
    Returns:
        list: Test vectors without optional model imports.
    """
    return [(1, 0) for _ in texts]


InstructorEncoder.encode = encode
Path("memory.json").write_text(json.dumps({"schema_version": 1, "app_id": "org.example.notes", "entries": [
    {"id": "a", "task": "Create note", "embedding": [1, 0]}
]}), encoding="utf-8")
source = yaml.safe_load(Path("autodroid_online.yaml").read_text(encoding="utf-8"))
body_nodes = source["nodes"]["online"]["loop"]["body"]["graph"]["nodes"]
body_nodes["memory"]["params"]["memory_path"] = "memory.json"
body_nodes["reasoning"]["params"] = {"scan_enabled": False, "shortcut_enabled": False}
compiled = compile_graph_yaml_data(source)
assert compiled.is_success, compiled.diagnostics
graph = compiled.graph
agent = compile_agent(graph, dependencies={"llm": Model()})
device = Device()
result = agent.run("Create note", AgentRunConfig(artifact_root=Path("runs"), max_steps=8, include_ui_tree=True), device=device)
assert result.status is RunStatus.SUCCESS, result
assert result.interaction_count == 3
assert device.effects == [("tap", 40, 20), ("tap", 40, 60), ("text", "hello"), ("back",)]
print("autodroid-installed: SDK/YAML hash, concise YAML execution, lazy imports, 3 interactions, terminal DONE passed")
