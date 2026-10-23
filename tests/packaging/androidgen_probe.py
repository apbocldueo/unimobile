"""Exercise installed AndroidGen YAML, original library adapter and six role families."""

import json
import io
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import zhixing
from zhixing.components import RunStatus, RuntimeContext
from zhixing.graph import load_graph_yaml
from zhixing.knowledge.androidgen import AndroidGenExamples
from zhixing.plugins.agent.androidgen.environment import AndroidGenEnvironment
from zhixing.plugins.agent.m3a.source import BoundingBox, UIElement
from zhixing.sdk import AgentRunConfig, compile_agent


class Model:
    """Only the external model is scripted; installed graph roles actually execute."""

    def __init__(self, planner=False):
        """Bind model purpose. Args: planner: Planning dependency. Returns: None."""
        self.planner, self.calls = planner, []

    def generate(self, prompt, system_prompt=None, history=None):
        """Return original protocol text. Args: prompt,system_prompt,history: Source request. Returns: str: Reply."""
        self.calls.append((prompt, system_prompt, history))
        if self.planner:
            if len(self.calls) == 2:
                return 'malformed update'
            return '1. Finish task State: [Todo]'
        assert 'Installed retrieved example' in system_prompt
        if len(self.calls) == 1:
            return "```python\ndo('Input Text', element_id=0, text='')\n```"
        assert '# Last Round Error: The text to input can not be empty.' in prompt
        assert [item['role'] for item in history] == ['user','assistant','user','assistant']
        return "```python\nexit('finished')\n```"


class Env:
    """Explicit original-shaped external environment with no real Android calls."""

    logical_screen_size = (240, 400)

    def __init__(self):
        """Initialize external call log. Returns: None."""
        self.actions, self.observations, self.shell = [], 0, []

    def get_state(self, wait_to_stabilize=False):
        """Supply real pixels/UI dataclasses. Args: wait_to_stabilize: Original flag. Returns: Any: State."""
        assert wait_to_stabilize is True
        self.observations += 1
        return SimpleNamespace(pixels=np.zeros((400,240,3),dtype=np.uint8), ui_elements=[
            UIElement(text='Field', tooltip='help', is_visible=True, is_editable=True,
                bbox_pixels=BoundingBox(10,180,20,90))])

    def execute_action(self, action):
        """Record original JSONAction. Args: action: Original fields. Returns: None."""
        self.actions.append(action.as_dict())

    def close(self):
        """No real resource to release. Returns: None."""
        pass


class Adb:
    """Replace external ADB only."""

    patterns = {}

    def system(self, command):
        """Record setup commands. Args: command: Original string. Returns: int: Status."""
        env.shell.append(command)
        return 0

    def popen(self, command):
        """Read fake focus. Args: command: Original query. Returns: StringIO: Package."""
        return io.StringIO('com.example')


class Ranker:
    """Replace external checkpoint scoring while installed filtering/selection runs."""

    def select_topk(self, query, references, k=1):
        """Verify original retrieval inputs. Args: query,references,k: Source request. Returns: Any: Top-one."""
        assert references == ['Installed task'] and k == 1
        return SimpleNamespace(indices=[0])


Path('library.json').write_text(json.dumps({'one': {'complete':True, 'env':'android',
    'task':'Installed task', 'init_state':'Different App', 'example':'Installed retrieved example'},
    'skip': {'complete':False, 'env':'android', 'task':'bad', 'example':'bad'}}))
examples = AndroidGenExamples('library.json', retriever=Ranker())
env, actor, planner = Env(), Model(), Model(planner=True)
context = RuntimeContext(max_steps=32)
loaded = load_graph_yaml('androidgen_online.yaml')
assert loaded.is_success, loaded.diagnostics
result = compile_agent(loaded, dependencies={'llm':actor, 'planner_llm':planner, 'examples':examples}).run(
    'Installed task', AgentRunConfig(artifact_root=Path('artifacts'), max_steps=32),
    device=AndroidGenEnvironment(env, adb=Adb(), geometry=lambda raw: {
        'orientation':0, 'physical_frame_boundary':(0,0,240,400)}), runtime=context)
assert result.status is RunStatus.SUCCESS, result.error
assert len(actor.calls) == env.observations == 2 and len(planner.calls) == 3
assert env.actions == [{'action_type':'click','index':0}, {'action_type':'answer','text':'finished'}]
assert len(env.shell) == 2
episode = context.state.last_action_result.metadata['androidgen']
assert len(episode['records']) == 2 and len(episode['history']) == 4
assert episode['benchmark_evaluated'] is False
assert Path(zhixing.__file__).resolve().is_relative_to(Path(__import__('sys').prefix).resolve())
print('androidgen-installed:' + json.dumps({'status':result.status.value, 'rounds':2, 'actor':2, 'planner':3}))
