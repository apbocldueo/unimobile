"""Execute installed standalone migration graphs with deterministic I/O only."""

import hashlib
import importlib.abc
from pathlib import Path
import socket
import subprocess
import sys

from PIL import Image

import zhixing
from zhixing.graph import load_graph_yaml
from zhixing.sdk import AgentRunConfig, compile_agent


class NoBindingImports(importlib.abc.MetaPathFinder):
    """Reject component/model/device imports during YAML validation."""

    def find_spec(self, fullname, path=None, target=None):
        """Check import boundary. Args: fullname,path,target: Import request. Raises: AssertionError: Binding during compile. Returns: None."""
        if fullname.startswith(("zhixing.plugins", "zhixing.devices", "openai", "torch")):
            raise AssertionError("compilation imported a runtime dependency: " + fullname)
        return None


def forbidden(*args, **kwargs):
    """Reject external effects. Args: args,kwargs: Attempt. Raises: AssertionError: Always. Returns: None."""
    raise AssertionError("network/process execution is forbidden in installed acceptance")


class Model:
    """Finite deterministic replacement for the external model only."""

    def __init__(self, responses):
        """Store script. Args: responses: Model texts. Returns: None."""
        self.responses = list(responses)

    def generate(self, prompt, images=None):
        """Return external text. Args: prompt,images: Real production inputs. Returns: str."""
        assert prompt and all(Path(path).is_file() for path in (images or []))
        return self.responses.pop(0)


class Android:
    """Produce actual PNG/XML files and record only fake device effects."""

    platform, serial, w, h = "android", "installed-migration", 120, 240

    def __init__(self):
        """Create independent device state. Returns: None."""
        self.images, self.effects = [], []

    def screenshot(self, path):
        """Create PNG. Args: path: Managed destination. Returns: str."""
        n = len(self.images) * 80
        Image.new("RGB", (self.w, self.h), (n, n, n)).save(path)
        self.images.append(path)
        return path

    def get_xml(self, path):
        """Create UI XML. Args: path: Managed destination. Returns: str."""
        Path(path).write_text('<hierarchy><node clickable="true" enabled="true" text="Button" '
            'class="android.widget.Button" bounds="[10,20][50,60]" /></hierarchy>')
        return path

    def tap(self, x, y):
        """Record TAP. Args: x,y: Pixels. Returns: None."""
        self.effects.append(("tap", x, y))

    def shell(self, command):
        """Record optional reset. Args: command: Fixed device command. Returns: str."""
        self.effects.append(("shell", command))
        return ""


assert "site-packages" in zhixing.__file__, zhixing.__file__
socket.create_connection = forbidden
socket.socket.connect = forbidden
subprocess.Popen = forbidden
mobile = ["### Action ###\nTap (30,40)", "### Answer ###\nA", "### Action ###\nStop"]
plan = "### Plan ###\npress button"
scripts = {
    "appagent": ["Action: tap(1)\nSummary: button", "Action: FINISH\nSummary: done"],
    "guicourse": ["tap, <point> 250 500</point>", "answer, complete"],
    "showui": ['{"action":"TAP","position":[0.25,0.5]}', '{"action":"ANSWER","value":"done"}'],
    "os_genesis": ['{"action_type":"click","x":30,"y":40}', '{"action_type":"status","goal_status":"successful"}'],
    "gui_schema_cn": ['{"POINT":[250,500]}', '{"STATUS":"finish"}'],
    "mobile_agent": mobile,
    "mobile_agent_v2_migrated": mobile,
    "mobile_use": [plan, plan, '<tool_call>{"name":"mobile_use","arguments":{"action":"click","coordinate":[30,40]}}</tool_call>',
        "### Answer ###\nA", plan, '<tool_call>{"name":"mobile_use","arguments":{"action":"answer","text":"done"}}</tool_call>'],
    "uground": ['Reason: choose\nAction: {"action_type":"click","element":"Button"}', '(250,500)', 'pressed',
        'Reason: done\nAction: {"action_type":"status","goal_status":"complete"}'],
}
finder = NoBindingImports()
sys.meta_path.insert(0, finder)
try:
    sources = {name: load_graph_yaml(name + ".yaml") for name in scripts}
    assert all(source.is_success for source in sources.values())
finally:
    sys.meta_path.remove(finder)
for name, responses in scripts.items():
    model, device = Model(responses), Android()
    result = compile_agent(sources[name], dependencies={"llm": model}).run("Press the button",
        AgentRunConfig(artifact_root=Path("artifacts") / name, include_ui_tree=True), device=device)
    assert result.status.value == "success", (name, result.error, result.error_details)
    assert len(result.action_results) == 2, name
    assert len(device.images) == 2 and not model.responses, name
    assert sum(item[0] == "tap" for item in device.effects) == 1, name
    print(name, "passed", sources[name].graph.canonical_hash())
assert "torch" not in sys.modules
print("legacy-yaml-installed: nine standalone graphs passed without repository imports, model/network/device execution")
