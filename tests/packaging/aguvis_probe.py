"""Exercise the installed base wheel without optional models or repo imports."""

import importlib.abc
import json
from pathlib import Path
import sys


class BlockOptional(importlib.abc.MetaPathFinder):
    """Detect accidental optional stack imports during compilation/execution."""

    def find_spec(self, fullname, path=None, target=None):
        """Block heavy modules. Args: fullname,path,target: Import arguments. Raises: AssertionError: Optional runtime imported. Returns: None."""
        if fullname.split(".")[0] in {"torch","transformers","qwen_vl_utils","openai","cv2","networkx"}:
            raise AssertionError("unexpected optional import: "+fullname)
        return None


sys.meta_path.insert(0,BlockOptional())
from PIL import Image
import zhixing
from zhixing.aguvis import build_aguvis_graph
from zhixing.components import RunStatus
from zhixing.graph import load_graph_yaml
from zhixing.plugins.llm.aguvis_llm import AguvisLLM, source_protocol
from zhixing.sdk import AgentRunConfig, compile_agent

assert Path(zhixing.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
assert source_protocol()==json.loads(Path("source_protocol.json").read_text())
assert AguvisLLM("missing-local-model")._model is None
compiled=load_graph_yaml("aguvis_online.yaml")
assert compiled.is_success and compiled.graph.canonical_hash()==build_aguvis_graph().canonical_hash()


class Model:
    """Provide only external responses; leave all Agent logic installed."""

    def __init__(self):
        """Initialize log. Returns: None."""
        self.calls=[]

    def generate_aguvis(self, request):
        """Verify exact history. Args: request: Production typed input. Returns: str: Scripted response."""
        self.calls.append(request)
        assert Path(request.screenshot_path).is_file()
        if len(self.calls)==1:
            assert request.previous_actions==()
            return "all\nAction: Type query\nassistantos\npyautogui.click(0.25,0.75); pyautogui.write('Ab C')"
        assert request.previous_actions==("Step 1: Type query",)
        return "answer('done'); mobile.terminate(status='success')"


class Device:
    """Small Android fake behind installed observation and executor services."""

    platform,serial,w,h="android","installed-aguvis-fake",100,200

    def __init__(self):
        """Initialize effects. Returns: None."""
        self.effects=[]

    def screenshot(self,path):
        """Write real PNG. Args: path: Artifact destination. Returns: str: Path."""
        Image.new("RGB",(100,200)).save(path)
        return path

    def tap(self,x,y):
        """Record executor tap. Args: x,y: Pixels. Returns: None."""
        self.effects.append(("tap",x,y))

    def input_text(self,text):
        """Record exact text. Args: text: Requested input. Returns: None."""
        self.effects.append(("text",text))


model,device=Model(),Device()
result=compile_agent(compiled,dependencies={"llm":model}).run("Open settings",
    AgentRunConfig(artifact_root=Path("runs")),device=device)
assert result.status is RunStatus.SUCCESS,result
assert result.interaction_count==2 and len(model.calls)==2
assert device.effects==[("tap",25,150),("text","Ab C")]
assert any(event.kind=="answer" for event in result.events)
assert (Path("runs")/result.run_id/"manifest.json").is_file()
print("aguvis-installed: exact resources, SDK/YAML, lazy imports and multi-command online loop passed")
