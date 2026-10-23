"""Independent external fixtures around the original loop and production AgentGraph."""

import ast
import base64
import contextlib
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
from pathlib import Path
import re
import shlex
import subprocess
from types import SimpleNamespace

from PIL import Image
from zhixing.components import RuntimeContext
from zhixing.ecoagent import build_ecoagent_graph
from zhixing.plugins.agent.ecoagent.environment import EcoEnvironment
from zhixing.plugins.agent.ecoagent.types import EcoReply
from zhixing.plugins.llm.ecoagent_llm import image_url
from zhixing.sdk import AgentRunConfig, compile_agent

OFFICIAL = Path(__file__).resolve().parents[1] / 'fixtures/ecoagent/official'


def plan(*steps, fence='JSON'):
    """Build external cloud reply. Args: steps,fence: Instructions/marker. Returns: str: Source plan."""
    return '```' + fence + '\n' + json.dumps({str(i): {'step': step, 'expectation': 'expected ' + str(i)}
        for i, step in enumerate(steps)}) + '\n```'


def pixels(index):
    """Create deterministic fake screen bytes. Args: index: Screen identity. Returns: bytes: PNG."""
    buffer = io.BytesIO()
    Image.new('RGB', (32, 48), (index % 255, 10, 20)).save(buffer, format='PNG')
    return buffer.getvalue()


class Device:
    """Only external device behavior; no Agent decisions or parsing."""

    serial = 'fixture-target'

    def __init__(self, fail=None):
        """Bind scenario. Args: fail: Optional failed primitive. Returns: None."""
        self.events, self.index, self.fail = [], 0, fail

    def shell(self, command, error_raise=True):
        """Record remote argv. Args: command,error_raise: Boundary input. Raises: OSError: Scripted. Returns: object: Status."""
        self.events.append(('device', tuple(shlex.split(command))))
        if self.fail == 'shell':
            raise OSError('device fixture')
        return SimpleNamespace(exit_code=0)

    def screenshot(self, path):
        """Save external screen. Args: path: Owned artifact. Raises: OSError: Scripted. Returns: str: Path."""
        self.events.append(('capture', self.index))
        if self.fail == 'screenshot':
            raise OSError('capture fixture')
        Path(path).write_bytes(pixels(self.index))
        self.index += 1
        return path

    def sleep(self, seconds):
        """Record wait. Args: seconds: Source delay. Returns: None."""
        self.events.append(('sleep', seconds))


class Models:
    """One explicit scripted endpoint per role, reusable by either implementation."""

    def __init__(self, plans, *, actions=('Action: click(10,20)',), summaries=('matches',),
                 descriptions=('screen description',), barrier=None):
        """Bind external scripts. Args: plans,actions,summaries,descriptions,barrier: Replies/overlap guard. Returns: None."""
        self.scripts = {'planning': list(plans[:1]), 'replanning': list(plans[1:]), 'action': list(actions),
            'summary': list(summaries), 'description': list(descriptions)}
        self.calls = {key: [] for key in self.scripts}
        self.barrier = barrier

    def complete_urls(self, operation, prompt, images):
        """Return one endpoint reply. Args: operation,prompt,images: Request. Raises: Exception: Scripted. Returns: EcoReply: Response."""
        self.calls[operation].append((prompt, tuple(images)))
        values = self.scripts[operation]
        if not values:
            raise AssertionError('Unexpected model call: ' + operation)
        value = values.pop(0) if len(values) > 1 or operation in ('planning','replanning') else values[0]
        if self.barrier is not None and operation in ('action','summary','description'):
            self.barrier.wait(timeout=5)
        if isinstance(value, Exception):
            raise value
        return EcoReply(value, total_tokens=10, prompt_tokens=7, completion_tokens=3, has_usage=True)

    def complete(self, operation, prompt, images):
        """Production model boundary. Args: operation,prompt,images: Request. Returns: EcoReply: Scripted response."""
        return self.complete_urls(operation, prompt, [image_url(image) for image in images])


def run_graph(tmp_path, plans, *, graph=None, device=None, **settings):
    """Execute production SDK and real graph with external services substituted.

    Args:
        tmp_path: Artifact root.
        plans: Cloud replies.
        graph,device: Optional selected definition/device.
        settings: Scripted endpoint or graph settings.
    Returns:
        tuple: RunResult, runtime, device, models and closed jobs object.
    """
    options = {name: settings.pop(name) for name in ('max_rounds','fix_protocol','wait_seconds') if name in settings}
    definition = graph or build_ecoagent_graph(**options)
    models = Models(plans, **settings)
    raw = device or Device()
    runtime = RuntimeContext(max_steps=definition.policies.max_steps)
    dependencies = {name + '_llm': models for name in ('planner','executor','description','summary')}
    agent = compile_agent(definition, dependencies=dependencies)
    with EcoEnvironment(raw, sleep=raw.sleep) as boundary:
        jobs = boundary.jobs
        result = agent.run('fixture task', AgentRunConfig(artifact_root=tmp_path,
            max_steps=definition.policies.max_steps), runtime=runtime, device=boundary)
    return result, runtime, raw, models, jobs


def definitions(text, names, namespace):
    """Load pinned original definitions without importing deployment side effects.

    Args:
        text: Complete original file text, optionally separately patched.
        names: Exact requested source definitions.
        namespace: External dependency substitutes.
    Returns:
        dict: Executed original definitions; no Agent loop is invented here.
    """
    nodes = [n for n in ast.parse(text).body if getattr(n, 'name', None) in names or isinstance(n, ast.Assign)
        and any(getattr(t, 'id', None) in names for t in n.targets)]
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *nodes], type_ignores=[])), 'official_ecoagent', 'exec'), namespace)
    return namespace


def reference(plans, *, max_rounds=30, repaired=False, **settings):
    """Run frozen official ECO.step and its original outer for-loop AST.

    Args:
        plans: Same cloud replies used by production.
        max_rounds: Original MAX_STEPS loop bound.
        repaired: Apply the separately checked compatibility.patch to disposable files.
        settings: Same external endpoint scripts.
    Raises:
        AssertionError: Compatibility patch does not apply cleanly.
    Returns:
        tuple: Original source outcome/state, external device and endpoint calls.
    """
    import tempfile
    source = OFFICIAL
    temporary = tempfile.TemporaryDirectory()
    if repaired:
        import shutil
        source = Path(temporary.name) / 'source'
        shutil.copytree(OFFICIAL, source)
        patch = subprocess.run(['git','apply',str(OFFICIAL.parent/'compatibility.patch')], cwd=source,
            capture_output=True, text=True)
        assert patch.returncode == 0, patch.stderr
    raw, models = Device(), Models(plans, **settings)
    constants = {}
    text = (source/'prompt.py').read_text()
    definitions(text, {n.targets[0].id for n in ast.parse(text).body if isinstance(n, ast.Assign)}, constants)

    def execute(command, **kwargs):
        """Substitute external ADB only. Args: command,kwargs: Original command. Returns: object: Status."""
        if isinstance(command, list):
            raw.events.append(('device', tuple(command[2:])))
        else:
            # Source's only command compound comes from newline-submitting type().
            for part in command.split(' && '):
                raw.shell(part.removeprefix('adb shell '), error_raise=False)
        return SimpleNamespace(returncode=0)

    def capture():
        """Substitute screen transport. Returns: str: Same bytes/MIME as production."""
        raw.events.append(('capture', raw.index))
        value = 'data:image/jpeg;base64,' + base64.b64encode(pixels(raw.index)).decode()
        raw.index += 1
        return value

    def post(url, json, **kwargs):
        """Substitute observer HTTP only. Args: url,json,kwargs: Original body/transport settings. Returns: object: Reply."""
        content = json['messages'][0]['content']
        operation = 'summary' if len(content) == 3 else 'description'
        value = models.complete_urls(operation, content[0]['text'], [p['image_url']['url'] for p in content[1:]])
        return SimpleNamespace(json=lambda: {'choices':[{'message':{'content':value.text}}]})

    def cloud(prompt, image):
        """Substitute cloud endpoint. Args: prompt,image: Original request. Returns: tuple: Source four values."""
        operation = 'planning' if not models.calls['planning'] else 'replanning'
        value = models.complete_urls(operation, prompt, [image])
        return value.text, None, None, value.total_tokens

    def action(prompt, image):
        """Substitute action endpoint. Args: prompt,image: Request. Returns: tuple: Source three values."""
        value = models.complete_urls('action', prompt, [image])
        return value.text, None, None

    utils = {'re':re, 'subprocess':SimpleNamespace(run=execute)}
    text = (source/'utils/ui_tars_utils.py').read_text()
    definitions(text, {n.name for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}, utils)
    context = {**constants, 'json':json, 're':re, 'subprocess':SimpleNamespace(run=execute),
        'time':SimpleNamespace(time=lambda:0.0, sleep=raw.sleep), 'ThreadPoolExecutor':ThreadPoolExecutor,
        'capture_and_encode':capture, 'requests':SimpleNamespace(post=post), 'ui_tars_utils':SimpleNamespace(**utils)}
    definitions((source/'agent/eco.py').read_text(), {'ECO'}, context)
    agent = context['ECO'](SimpleNamespace(predict_mm=cloud), SimpleNamespace(predict_mm=action), name='eco_ui-tars',
        config_loader=SimpleNamespace(get_vision_config=lambda:{}))
    # Source CLI Home belongs before the original loop; use its selected-device definition.
    text = (source/'run.py').read_text()
    home = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name=='send_home')
    exec(compile(ast.fix_missing_locations(ast.Module(body=[home],type_ignores=[])), 'official_home','exec'),context)
    # Normalize only the external transport's explicit -s arguments.
    def home_run(command, **kwargs):
        """Record selected Home. Args: command,kwargs: Original invocation. Returns: object: Success."""
        assert command[:4] == ['adb','-s',raw.serial,'shell']
        raw.events.append(('device',tuple(command[4:])))
        return SimpleNamespace(returncode=0)
    with contextlib.redirect_stdout(io.StringIO()):
        original_run = context['subprocess'].run
        context['subprocess'].run = home_run
        context['send_home'](raw.serial)
        context['subprocess'].run = original_run
        body = next(n for n in ast.parse(text).body if isinstance(n,ast.If))
        loop = next(n for n in body.body if isinstance(n,ast.For))
        context.update(agent=agent,goal='fixture task',MAX_STEPS=max_rounds,steps=[],expectations=[],descriptions=[],
            total_tokens=0,llm_calls=0,prev_time=0.0)
        try:
            exec(compile(ast.fix_missing_locations(ast.Module(body=[loop],type_ignores=[])),'official_loop','exec'),context)
            error = ''
        except Exception as failure:
            error = type(failure).__name__
    temporary.cleanup()
    return {'success':context.get('result'), 'steps':context['steps'], 'expectations':context['expectations'],
        'descriptions':context['descriptions'], 'llm_calls':context['llm_calls'], 'total_tokens':context['total_tokens'],
        'error':error}, raw, models
