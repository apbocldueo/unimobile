"""Execute the installed M3A YAML without repository imports or real services."""

import json
from pathlib import Path

import numpy as np

import zhixing
from zhixing.components import RunStatus, RuntimeContext
from zhixing.graph import load_graph_yaml
from zhixing.m3a import build_m3a_graph
from zhixing.plugins.agent.m3a.environment import M3AEnvironment
from zhixing.plugins.agent.m3a.source import BoundingBox, UIElement
from zhixing.plugins.agent.m3a.types import M3AReply
from zhixing.sdk import AgentRunConfig, compile_agent


class Model:
    """Script only the external model while installed graph/components execute."""

    def __init__(self):
        """Initialize external call count. Returns: None."""
        self.calls = 0

    def generate_m3a(self, prompt, images):
        """Return one scripted source response. Args: prompt,images: Original request. Returns: M3AReply: Reply."""
        self.calls += 1
        assert len(images) == 2 and all(Path(path).is_file() for path in images)
        if self.calls == 1:
            assert "You just started, no action has been performed yet." in prompt
            return M3AReply('Reason: tap\nAction: {"action_type":"click","index":0}')
        if self.calls == 2:
            return M3AReply("Opened the target.")
        assert self.calls == 3
        assert 'Step 1- Action selected:' in prompt and "Opened the target." in prompt
        return M3AReply('Reason: done\nAction: {"action_type":"status","goal_status":"complete"}')


class Env:
    """Explicit external AsyncEnv double, without a generic Android fallback."""

    logical_screen_size = (240, 400)
    orientation = 0
    physical_frame_boundary = (0, 0, 240, 400)

    def __init__(self):
        """Initialize execution log. Returns: None."""
        self.actions, self.waits = [], []

    def reset(self, go_home=False):
        """Accept source reset. Args: go_home: Source setting. Returns: None."""
        assert go_home is False

    def hide_automation_ui(self):
        """Accept source overlay setup. Returns: None."""
        pass

    def get_state(self, wait_to_stabilize=False):
        """Provide original-shaped UI/pixels. Args: wait_to_stabilize: Source policy. Returns: State: External value."""
        from types import SimpleNamespace

        assert wait_to_stabilize is False
        return SimpleNamespace(pixels=np.zeros((400, 240, 3), dtype=np.uint8),
            ui_elements=[UIElement(text="Button", is_visible=True, is_clickable=True,
                bbox_pixels=BoundingBox(10, 100, 40, 100))])

    def execute_action(self, action):
        """Record one external action. Args: action: Original JSON fields. Returns: None."""
        self.actions.append(action.as_dict())


graph = load_graph_yaml("m3a_online.yaml")
assert graph.is_success
assert graph.graph.canonical_hash() == build_m3a_graph().canonical_hash()
model, env, context = Model(), Env(), RuntimeContext(max_steps=31)
result = compile_agent(graph, dependencies={"llm": model}).run("Open the target",
    AgentRunConfig(artifact_root=Path("artifacts"), max_steps=31),
    device=M3AEnvironment(env, sleep=env.waits.append), runtime=context)
assert result.status is RunStatus.SUCCESS, result.error
assert model.calls == 3 and env.waits == [1.0, 2.0, 1.0]
assert env.actions == [{"action_type": "click", "index": 0}]
payload = context.state.last_action_result.metadata["m3a"]
assert payload["decision_rounds"] == 2 and len(payload["history"]) == 2
assert Path(zhixing.__file__).resolve().is_relative_to(Path(__import__('sys').prefix).resolve())
print("m3a-installed:" + json.dumps({"status": result.status.value, "calls": model.calls}))
