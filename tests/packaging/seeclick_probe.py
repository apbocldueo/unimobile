"""Execute installed SeeClick with only base dependencies and scripted I/O."""

import importlib.abc
import json
from pathlib import Path
import sys


class BlockOptional(importlib.abc.MetaPathFinder):
    """Reject accidental model/vision/API imports in the base-wheel execution."""

    def find_spec(self, fullname, path=None, target=None):
        """Permit ordinary imports and reject optional runtimes.

        Args:
            fullname: Module requested by Python.
            path: Standard module search path.
            target: Standard reload target.
        Raises:
            AssertionError: A heavy optional dependency is imported.
        Returns:
            None: Continue normal module lookup.
        """
        if fullname.split(".")[0] in {"torch","transformers","peft","openai","cv2"}:
            raise AssertionError("unexpected optional import: " + fullname)
        return None


sys.meta_path.insert(0, BlockOptional())

from PIL import Image
import zhixing
from zhixing.components import RunStatus
from zhixing.graph import load_graph_yaml
from zhixing.plugins.llm.seeclick_llm import SeeClickLLM
from zhixing.resources import read_prompt
from zhixing.sdk import AgentRunConfig, compile_agent
from zhixing.seeclick import build_seeclick_graph


assert Path(zhixing.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
contract = json.loads(Path("source_contract.json").read_text())
assert read_prompt("reasoning_seeclick_aitw.md").removesuffix("\n") == contract["prompt"].replace("{}","{instruction}",1).replace("{}","{previous_actions}",1)
assert SeeClickLLM("absent-model", "absent-tokenizer")._backend is None
compiled = load_graph_yaml("seeclick_online.yaml")
assert compiled.is_success, compiled.diagnostics
assert compiled.graph.canonical_hash() == build_seeclick_graph().canonical_hash()
responses = ['{"action_type":4,"click_point":(0.25,0.75)}',
             '{"action_type":3,"typed_text":"Ab C"}', '{"action_type":10}']


class Model:
    """Supply only responses; production code builds every prompt and action."""

    def __init__(self):
        """Initialize an empty prompt log.

        Returns:
            None.
        """
        self.prompts = []

    def generate(self, prompt, images=None):
        """Verify exact source prompt/history and return the next decision.

        Args:
            prompt: Real prompt from the installed Reasoning component.
            images: One service-owned screenshot.
        Returns:
            str: Original source-format response.
        """
        index = len(self.prompts)
        history = "".join(f"Step{i}: {raw}. " for i,raw in enumerate(responses[max(0,index-4):index]))
        assert prompt == contract["prompt"].format("Open settings",history)
        assert len(images) == 1 and Path(images[0]).is_file()
        self.prompts.append(prompt)
        return responses[index]


class Device:
    """Small Android-compatible fake behind the installed observation/executor."""

    platform, serial, w, h = "android", "installed-seeclick-fake", 100, 200

    def __init__(self):
        """Initialize confirmed effect recording.

        Returns:
            None.
        """
        self.effects = []

    def screenshot(self,path):
        """Write a real PNG for the installed observation service.

        Args:
            path: Runtime-owned screenshot destination.
        Returns:
            str: Written file path.
        """
        Image.new("RGB",(100,200)).save(path)
        return path

    def get_xml(self,path):
        """Reject XML capture by the visual-only graph.

        Args:
            path: Unexpected XML destination.
        Raises:
            AssertionError: XML is requested.
        Returns:
            None.
        """
        raise AssertionError("unexpected XML capture")

    def tap(self,x,y):
        """Record the real executor's pixel tap.

        Args:
            x: Horizontal coordinate.
            y: Vertical coordinate.
        Returns:
            None.
        """
        self.effects.append(("tap",x,y))

    def input_text(self,text):
        """Record exact text without additional click or Enter.

        Args:
            text: Requested device input.
        Returns:
            None.
        """
        self.effects.append(("text",text))


model,device = Model(),Device()
result = compile_agent(compiled,dependencies={"llm":model}).run("Open settings",
    AgentRunConfig(artifact_root=Path("runs")),device=device)
assert result.status is RunStatus.SUCCESS, result
assert result.interaction_count == 2 and len(model.prompts) == 3
assert device.effects == [("tap",25,150),("text","Ab C")]
assert (Path("runs") / result.run_id / "manifest.json").is_file()
print("seeclick-installed: source prompt, SDK/YAML identity, lazy imports, closed loop and exact effects passed")
