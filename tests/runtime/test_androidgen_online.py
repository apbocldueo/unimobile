"""Differential AndroidGen online execution against the pinned official source."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import io
import json
import re
from functools import partial
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from zhixing.androidgen import build_androidgen_graph
from zhixing.components import RunStatus, RuntimeContext
from zhixing.graph import load_graph_yaml
from zhixing.knowledge.androidgen import AndroidGenExamples
from zhixing.plugins.agent.androidgen import prompts, source
from zhixing.plugins.agent.androidgen.environment import AndroidGenAdb, AndroidGenEnvironment
from zhixing.plugins.agent.m3a import source as m3a
from zhixing.sdk import AgentRunConfig, compile_agent


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / 'tests/fixtures/androidgen'
GOAL = 'Open Settings and enter a note'


def official(path, namespace, names=None):
    """Load unchanged definitions with explicitly injected external imports.

    Args:
        path: Official repository-relative path.
        namespace: External dependency substitutes, without model/device I/O.
        names: Optional selected top-level definition names.
    Raises:
        Exception: Original source cannot be compiled in the supplied context.
    Returns:
        SimpleNamespace: Executable original definitions, not production adapters.
    """
    tree = ast.parse((FIXTURES / (path.replace('/', '__') + '.txt')).read_text())
    body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
        and (names is None or getattr(node, 'name', None) in names)]
    future = ast.ImportFrom(module='__future__', names=[ast.alias(name='annotations')], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *body], type_ignores=[])), path, 'exec'), namespace)
    return SimpleNamespace(**namespace)


class Model:
    """Script external model replies while retaining every full original request."""

    def __init__(self, replies, *, repeat=False):
        """Bind replies. Args: replies: Original texts; repeat: Repeat final reply. Returns: None."""
        self.replies, self.calls, self.repeat = list(replies), [], repeat

    def generate(self, prompt, system_prompt=None, history=None):
        """Record one source call. Args: prompt,system_prompt,history: Original request. Raises: AssertionError: Unexpected call. Returns: str: Reply."""
        self.calls.append(copy.deepcopy({'prompt': prompt, 'system_prompt': system_prompt, 'history': history}))
        index = min(len(self.calls) - 1, len(self.replies) - 1) if self.repeat else len(self.calls) - 1
        assert index < len(self.replies), 'unexpected model call'
        return self.replies[index]


class Adb:
    """Only the external ADB protocol is substituted, preserving command strings."""

    patterns = {'Settings|settings': ['com.android.settings']}

    def __init__(self, events, app='com.android.settings'):
        """Bind the log. Args: events: Shared I/O log; app: Focus package. Returns: None."""
        self.events, self.app = events, app

    def system(self, command):
        """Record a source shell effect. Args: command: Original string. Returns: int: Success status."""
        self.events.append(('shell', command))
        return 0

    def popen(self, command):
        """Record a focus query. Args: command: Original pipeline. Returns: StringIO: Focus output."""
        self.events.append(('focus', command))
        return io.StringIO(self.app)

    def get_adb_activity(self, app_name):
        """Resolve a source name. Args: app_name: Original alias. Returns: str | None: Activity."""
        self.events.append(('resolve', app_name))
        return None if app_name == 'Missing' else 'com.android.settings/.Settings'


class RawEnv:
    """Original-shaped external AsyncEnv with ordered UI, geometry and pixels."""

    logical_screen_size = (240, 400)
    orientation = 0
    physical_frame_boundary = (0, 0, 240, 400)

    def __init__(self, *, tooltip='', fail_actions=()):
        """Initialize I/O evidence. Args: tooltip: Source tooltip; fail_actions: Failed JSON action kinds. Returns: None."""
        self.events, self.actions, self.states = [], [], []
        self.tooltip, self.fail_actions = tooltip, set(fail_actions)
        self.base_env = self

    def reset(self, go_home=False):
        """Record original reset. Args: go_home: Source setting. Returns: None."""
        self.events.append(('reset', go_home))

    def get_state(self, wait_to_stabilize=True):
        """Return fresh deterministic source UI/pixels. Args: wait_to_stabilize: Source flag. Returns: Any: State."""
        self.events.append(('observe', wait_to_stabilize))
        index = len(self.states)
        elements = [m3a.UIElement(text='hidden', is_visible=False),
            m3a.UIElement(text=f'Button {index}', class_name='android.widget.EditText', tooltip=self.tooltip,
                resource_name='com.android.settings:id/entry', is_visible=True, is_clickable=True,
                is_editable=True, is_checkable=True, is_checked=False,
                bbox_pixels=m3a.BoundingBox(10, 180, 30, 110)),
            m3a.UIElement(text='keyboard', resource_name='com.google.inputmethod:id/key', is_visible=True,
                bbox_pixels=m3a.BoundingBox(30, 50, 120, 160)),
            m3a.UIElement(text='outside', is_visible=True, bbox_pixels=m3a.BoundingBox(300, 350, 20, 40)),
            m3a.UIElement(text=None, content_description='No box', is_visible=True),
            m3a.UIElement(text='', content_description='Do not use this', is_visible=True)]
        pixels = np.zeros((400, 240, 3), dtype=np.uint8)
        pixels[:, :, 0] = index % 255
        pixels[:, :, 1] = np.arange(240, dtype=np.uint8)[None, :]
        state = SimpleNamespace(pixels=pixels, ui_elements=elements)
        self.states.append(state)
        return state

    def execute_action(self, action):
        """Execute the external primitive. Args: action: Original JSONAction. Raises: RuntimeError: Scripted failure. Returns: None."""
        data = action.as_dict()
        self.events.append(('action', data))
        self.actions.append(data)
        if action.action_type in self.fail_actions:
            raise RuntimeError('external execution failed')

    def close(self):
        """Record explicit cleanup. Returns: None."""
        self.events.append(('close',))


class Examples:
    """Substitute one external original-compatible retrieval result."""

    def __init__(self, value='Selected source example'):
        """Bind result. Args: value: Original example or None. Returns: None."""
        self.value, self.calls = value, []

    def retrieve_example(self, *args):
        """Record original lookup. Args: args: Task/env/init_state. Returns: str | None: Example."""
        self.calls.append(args)
        return self.value


def run_graph(tmp_path, actions, plans=('1. Finish State: [Todo]',), *, raw=None, examples=None, graph=None, **options):
    """Execute production components, substituting external model and device services only.

    Args:
        tmp_path: Artifact directory.
        actions: Scripted actor responses.
        plans: Scripted planner responses, repeated after exhaustion.
        raw: Optional external environment.
        examples: Optional external retrieval service.
        graph: Optional YAML/SDK graph instead of a newly built one.
        options: SDK graph configuration.
    Returns:
        tuple: Result, context, external env/ADB, actor, planner and retriever.
    """
    raw = raw or RawEnv()
    adb, actor, planner = Adb(raw.events), Model(actions, repeat=True), Model(plans, repeat=True)
    examples = examples or Examples()
    graph = graph or build_androidgen_graph(**options)
    context = RuntimeContext(max_steps=graph.policies.max_steps)
    result = compile_agent(graph, dependencies={'llm': actor, 'planner_llm': planner, 'examples': examples}).run(
        GOAL, AgentRunConfig(artifact_root=tmp_path, max_steps=graph.policies.max_steps),
        device=AndroidGenEnvironment(raw, adb=adb, geometry=lambda env: {
            'orientation': env.orientation, 'physical_frame_boundary': env.physical_frame_boundary}), runtime=context)
    return result, context, raw, adb, actor, planner, examples


def payload(context):
    """Read final source evidence. Args: context: Completed runtime. Returns: dict: Episode."""
    return context.state.last_action_result.metadata['androidgen']


def code(text):
    """Wrap a source response. Args: text: Original Python. Returns: str: Fenced response."""
    return 'Thought: next\n```python\n' + text + '\n```'


def source_env(raw, adb, tmp_path):
    """Instantiate the original Env with unchanged definitions and external imports.

    Args:
        raw: Original-shaped external AsyncEnv.
        adb: Scoped external ADB substitute.
        tmp_path: Original cache location.
    Returns:
        Any: Unmodified official Env, including its original tooltip error.
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    module = official('environment/android/env.py', {'__file__': str(tmp_path/'env.py'),
        'os': SimpleNamespace(system=adb.system, popen=adb.popen, path=__import__('os').path,
            makedirs=__import__('os').makedirs), 'inspect': inspect, 'partial': partial, 'Image': Image,
        'json_action': m3a, '_PATTERN_TO_ACTIVITY': adb.patterns, 'get_adb_activity': adb.get_adb_activity,
        'adb_utils': SimpleNamespace(get_orientation=lambda env: env.orientation,
            get_physical_frame_boundary=lambda env: env.physical_frame_boundary), 'm3a_utils': m3a}, {'Env'})
    return module.Env(env=raw)


def normalize(value):
    """Compare image inputs by pixels instead of framework-owned artifact paths.

    Args:
        value: Nested source prompt/history/record data.
    Returns:
        Any: Path-independent comparable value.
    """
    if isinstance(value, dict):
        return {key: (np.array(Image.open(item)).tolist() if key in ('image_url', 'image', 'raw') and item else normalize(item))
            for key, item in value.items() if key not in ('trace_id',)}
    if isinstance(value, (tuple, list)):
        return [normalize(item) for item in value]
    return value


@pytest.mark.parametrize('actor_type,planner_type', [('text','text'), ('image','text'), ('text','image'), ('image','image')])
def test_full_online_matches_original_agent_plan_and_environment(tmp_path, actor_type, planner_type):
    """Compare complete original requests, observations, results, history and external effects.

    Args:
        tmp_path: Evidence directory.
        actor_type: Original actor input selection.
        planner_type: Independent original planner input selection.
    Raises:
        AssertionError: Production graph changes any compared online semantics.
    Returns:
        None.
    """
    actions = [code("do('Input Text', element_id=1, text='')"), code("quote('remember')"),
        code("do('Swipe', direction='up')"), code("exit('done')")]
    plans = ['invalid\n1. Enter note State: [Todo]', 'invalid update',
        '1. Enter note State: [Done]', '1. Finish State: [Done]', '1. Finish State: [Done]']
    result, context, raw, adb, actor, planner, examples = run_graph(tmp_path/'graph', actions, plans,
        model_type=actor_type, planner_model_type=planner_type)
    assert result.status is RunStatus.SUCCESS, result.error
    records = payload(context)['records']
    original_raw = RawEnv()
    original_adb = Adb(original_raw.events)
    env = source_env(original_raw, original_adb, tmp_path/'original')
    source_actor, source_planner = Model(actions), Model(plans)
    plan_module = official('model/planning/__init__.py', {'re': re, 'llm_provider': lambda **kwargs: source_planner,
        'plan_system_prompt': prompts.plan_system_prompt, 'update_plan_system_prompt': prompts.update_plan_system_prompt}, {'Plan'})
    agent_module = official('model/agent.py', {'llm_provider': lambda name: source_actor, 'Plan': plan_module.Plan,
        'ExampleRetriever': lambda **kwargs: examples,
        'prompt_provider': lambda env, example: prompts.system_prompt % example}, {'Agent'})
    agent = agent_module.Agent({'model_name':'actor', 'model_type':actor_type},
        {'reflectplan':{'model_name':'planner', 'model_type':planner_type}, 'autocheck':True,
         'expsearch':{'database_path':'external', 'retriever_ckpt_path':'external'}}, GOAL, 'android', env.init_state)
    recorder_module = official('recorder.py', {'json':json, 'os':__import__('os'), 'time':__import__('time'),
        'copyfile':__import__('shutil').copyfile}, {'Recorder'})
    recorder = recorder_module.Recorder(GOAL, str(tmp_path/'source-records'), task_id='source')
    original_records = []
    while recorder.turn_number <= 30:
        state, record = env.get_current_state()
        # Capture original images before its mutable cache is overwritten.
        expected_view = normalize(record)
        output = agent(state, recorder.format_history())
        exe_res = env.interact(source.get_code_snippet(output['response']))
        agent.update(exe_res)
        expected = {**expected_view, 'instruction': GOAL, 'index':recorder.turn_number,
                    **output, 'parsed_action': exe_res}
        original_records.append(expected)
        recorder.update(record, output, exe_res)
        if exe_res['operation'] == 'exit':
            break
    # Source model calls reference overwritten cache filenames. Compare each
    # request's text plus the matching immutable graph image for its real round.
    for actual_calls, expected_calls in ((actor.calls, source_actor.calls), (planner.calls, source_planner.calls)):
        assert len(actual_calls) == len(expected_calls)
        for actual, expected in zip(actual_calls, expected_calls):
            actual, expected = copy.deepcopy(actual), copy.deepcopy(expected)
            if isinstance(expected['prompt'], dict):
                assert Path(actual['prompt'].pop('image_url')).is_file()
                expected['prompt'].pop('image_url')
            assert actual == expected
    assert [normalize(record) for record in records] == original_records
    assert payload(context)['history'] == recorder.format_history()
    assert raw.events == original_raw.events
    assert len(raw.states) == 4 and len(planner.calls) == 5
    assert len(examples.calls) == 2  # once by each independent implementation
    assert payload(context)['agent_declared_exit'] and payload(context)['benchmark_evaluated'] is False


@pytest.mark.parametrize('statement', [
    "open_app('Settings')", "open_app('Missing')", "do('Click', element_id=1)",
    "do('Click', element_id='1')", "do('Click', element_id='bad')", "do('Long Press', element_id=1)",
    "do('Input Text', element_id=1, text='A b\\n\\\'\\\"#?')", "do('Input Text', element_id=1, text='')",
    "do('Press Enter')", "do('Navigate Home')", "do('Navigate Back')", "do('Scroll', direction='left')",
    "do('Scroll', direction='invalid')", "do('Swipe', direction='down', element_id=1)",
    "do('Swipe', direction='bad')", "do('Wait')", "quote('x')", "quote('')", "exit()", "exit('answer')",
    "do('Unknown')", "raise ValueError('bad')", "quote('one'); quote('two')", "value = 1",
])
def test_complete_action_protocol_matches_original(tmp_path, statement):
    """Differentially exercise every source action, validation and Python-code result.

    Args:
        tmp_path: Cache directory.
        statement: Exact source code, including multiple calls and malformed inputs.
    Raises:
        AssertionError: Result, exception recovery or primitive order differs.
    Returns:
        None.
    """
    expected_raw, actual_raw = RawEnv(), RawEnv()
    expected_adb, actual_adb = Adb(expected_raw.events), Adb(actual_raw.events)
    original = source_env(expected_raw, expected_adb, tmp_path)
    bridge = AndroidGenEnvironment(actual_raw, adb=actual_adb)
    bridge.setup()
    expected = original.interact(statement)
    actual = bridge.interact(statement, RuntimeContext())
    assert actual == expected
    assert actual_raw.events == expected_raw.events


@pytest.mark.parametrize('kind,statement', [('click', "do('Click', element_id=3)"),
    ('long_press', "do('Long Press', element_id=3)"), ('click', "do('Input Text', element_id=3, text='x')"),
    ('scroll', "do('Scroll', direction='up')"), ('open_app', "open_app('Settings')")])
def test_original_device_exception_guards(tmp_path, kind, statement):
    """Preserve source-specific missing-ID and generic interact errors.

    Args:
        tmp_path: Source cache directory.
        kind: Failed original action kind.
        statement: Original code block.
    Returns:
        None.
    """
    left, right = RawEnv(fail_actions=(kind,)), RawEnv(fail_actions=(kind,))
    original = source_env(left, Adb(left.events), tmp_path)
    bridge = AndroidGenEnvironment(right, adb=Adb(right.events))
    bridge.setup()
    assert bridge.interact(statement, RuntimeContext()) == original.interact(statement)
    assert left.events == right.events


def test_tooltip_compatibility_fix_and_original_error(tmp_path):
    """Retain evidence of the original unbound local and verify the one-field fix.

    Args:
        tmp_path: Source cache and graph artifacts.
    Raises:
        AssertionError: The documented baseline defect disappears or fix changes indexes.
    Returns:
        None.
    """
    raw = RawEnv(tooltip='Help')
    original = source_env(raw, Adb(raw.events), tmp_path/'source')
    with pytest.raises(UnboundLocalError):
        original.get_current_state()
    result, context, *_ = run_graph(tmp_path/'graph', [code('exit()')], raw=RawEnv(tooltip='Help'))
    assert result.status is RunStatus.SUCCESS, result.error
    state = payload(context)['records'][0]['state']
    assert 'id="1"' in state and 'tooltip="Help"' in state
    assert 'id="2"' not in state and 'id="3"' not in state
    assert 'No box' in state and 'Do not use this' not in state


@pytest.mark.parametrize('autocheck', [True, False])
def test_feedback_switch_preserves_click_before_empty_text_check(tmp_path, autocheck):
    """Only feedback injection changes when AutoCheck is disabled.

    Args:
        tmp_path: Artifacts.
        autocheck: Source feedback flag.
    Returns:
        None.
    """
    result, context, raw, _, actor, *_ = run_graph(tmp_path,
        [code("do('Input Text', text='', element_id=1)"), code('exit()')], autocheck=autocheck)
    assert result.status is RunStatus.SUCCESS, result.error
    assert raw.actions == [{'action_type':'click', 'index':1}]
    records = payload(context)['records']
    assert records[0]['parsed_action']['operation'] == 'fail'
    assert ('error_feedback' in records[1]) is autocheck
    assert ('# Last Round Error:' in actor.calls[1]['prompt']) is autocheck
    assert context.step == 1


def test_initial_empty_plan_proceeds_and_all_done_does_not_stop(tmp_path):
    """Empty generation is not an update retry and Done does not substitute exit.

    Args:
        tmp_path: Graph artifacts.
    Returns:
        None.
    """
    result, context, raw, _, actor, planner, _ = run_graph(tmp_path,
        [code("quote('same')"), code("quote('same')"), code('exit()')],
        ['not a plan', '1. Finish State: [Done]', '1. Finish State: [Done]'])
    assert result.status is RunStatus.SUCCESS, result.error
    assert len(raw.states) == len(actor.calls) == len(planner.calls) == 3
    assert payload(context)['records'][0]['plan'] is None
    assert len(payload(context)['history']) == 6
    assert [item['role'] for item in payload(context)['history']] == ['user','assistant'] * 3


def test_update_retry_budget_stops_without_new_observation_or_actor(tmp_path):
    """Explicit Graph budget replaces original unbounded malformed-update loop.

    Args:
        tmp_path: Artifacts.
    Returns:
        None.
    """
    result, _, raw, _, actor, planner, _ = run_graph(tmp_path,
        [code("quote('x')")], ['1. Continue State: [Todo]', 'bad'], max_plan_attempts=2)
    assert result.status is not RunStatus.SUCCESS
    assert len(raw.states) == 2 and len(actor.calls) == 1 and len(planner.calls) == 3
    assert planner.calls[1] == planner.calls[2]
    assert 'loop' in result.error.lower()


def test_31_logical_rounds_full_planner_history_actor_window_and_terminal_flush(tmp_path):
    """Repeated nonphysical quotes still consume 31 rounds and retain 62 messages.

    Args:
        tmp_path: Graph artifacts.
    Returns:
        None.
    """
    result, context, raw, _, actor, planner, retriever = run_graph(tmp_path, [code("quote('same')")])
    assert result.status is RunStatus.STEP_LIMIT, result.error
    episode = payload(context)
    assert episode['decision_rounds'] == 31 and len(episode['history']) == 62
    assert len(raw.states) == len(actor.calls) == len(planner.calls) == 31
    assert context.step == 0 and len(retriever.calls) == 1
    assert len(actor.calls[-1]['history']) == 22
    assert planner.calls[-1]['prompt'].count(code("quote('same')")) == 30
    assert episode['history'][-1]['content']['text'] == code("quote('same')")


def test_last_physical_round_commits_before_budget(tmp_path):
    """Physical step allowance leaves room for all source records and final flush.

    Args:
        tmp_path: Graph artifacts.
    Returns:
        None.
    """
    result, context, *_ = run_graph(tmp_path, [code("do('Click', element_id=1)")], max_rounds=3)
    assert result.status is RunStatus.STEP_LIMIT, result.error
    assert payload(context)['decision_rounds'] == context.step == 3
    assert len(payload(context)['history']) == 6


@pytest.mark.parametrize('response', ['no code', code('value = 1')])
def test_source_fatal_boundaries_are_not_resampled(tmp_path, response):
    """Missing fence and None execution result abort outside source interact recovery.

    Args:
        tmp_path: Graph artifacts.
        response: Fatal source response.
    Returns:
        None.
    """
    result, _, raw, _, actor, planner, _ = run_graph(tmp_path, [response])
    assert result.status is not RunStatus.SUCCESS
    assert len(actor.calls) == len(planner.calls) == len(raw.states) == 1
    records = list(tmp_path.rglob('androidgen-records.json'))
    assert bool(records) is (response != 'no code')
    if records:
        assert json.loads(records[0].read_text())['records'][0]['parsed_action'] is None


def test_exec_exception_is_feedback_on_next_real_round(tmp_path):
    """A caught execution error differs from fatal missing-code extraction.

    Args:
        tmp_path: Graph artifacts.
    Returns:
        None.
    """
    result, context, *_ = run_graph(tmp_path, [code("raise ValueError('bad')"), code('exit()')])
    assert result.status is RunStatus.SUCCESS, result.error
    records = payload(context)['records']
    assert records[1]['error_feedback'] == 'Some error happened in previous action.'


def test_yaml_same_graph_and_isolated_repeated_runs(tmp_path):
    """Execute the shipped explicit YAML twice with fresh run-owned plan and Memory.

    Args:
        tmp_path: Separate run artifacts.
    Returns:
        None.
    """
    loaded = load_graph_yaml(ROOT/'examples/graphs/androidgen_online.yaml')
    assert loaded.is_success, loaded.diagnostics
    assert loaded.graph.canonical_hash() == build_androidgen_graph().canonical_hash()
    for index in range(2):
        result, context, _, _, actor, planner, _ = run_graph(tmp_path/str(index),
            [code("quote('same')"), code('exit()')], graph=loaded.graph)
        assert result.status is RunStatus.SUCCESS, result.error
        assert len(actor.calls[0]['history']) == 2
        assert planner.calls[0]['system_prompt'] == prompts.plan_system_prompt
        assert len(payload(context)['history']) == 4


def test_one_compiled_recipe_has_fresh_plan_and_memory_each_run(tmp_path):
    """Reuse a single SDK recipe without sharing components, State or Memory buffers.

    Args:
        tmp_path: Separate artifact roots.
    Returns:
        None.
    """
    actor, planner, examples = Model([code('exit()')],repeat=True), Model(['1. Done State: [Done]'],repeat=True), Examples()
    recipe = compile_agent(build_androidgen_graph(),dependencies={'llm':actor,'planner_llm':planner,'examples':examples})
    for index in range(2):
        raw, context = RawEnv(), RuntimeContext(max_steps=32)
        result = recipe.run(GOAL,AgentRunConfig(artifact_root=tmp_path/str(index),max_steps=32),
            device=AndroidGenEnvironment(raw,adb=Adb(raw.events),geometry=lambda env:{
                'orientation':env.orientation,'physical_frame_boundary':env.physical_frame_boundary}),runtime=context)
        assert result.status is RunStatus.SUCCESS,result.error
        assert len(actor.calls[-1]['history']) == 2
        assert planner.calls[-1]['system_prompt'] == prompts.plan_system_prompt
        assert len(payload(context)['history']) == 2
    assert len(examples.calls) == 2


def test_nested_graph_uses_all_six_existing_families():
    """Validate the representative graph's actual role declarations, including nested Planner.

    Returns:
        None.
    """
    def roles(graph):
        """Walk nested definitions. Args: graph: AgentGraph. Returns: set: Declared roles."""
        found = {node.role.value for node in graph.nodes if node.role is not None}
        for node in graph.nodes:
            if node.loop:
                found.update(roles(node.loop.body.graph))
        return found
    assert roles(build_androidgen_graph()) == {'perception','planner','reasoning','memory','verifier','action_executor'}


def test_disabled_features_preserve_default_example_and_action_checks(tmp_path):
    """Original ablations stay explicit without being used as full-configuration proof.

    Args:
        tmp_path: Graph artifacts.
    Returns:
        None.
    """
    result, context, _, _, actor, planner, examples = run_graph(tmp_path,
        [code("quote('')"), code('exit()')], expsearch=False, reflectplan=False, autocheck=False)
    assert result.status is RunStatus.SUCCESS, result.error
    assert not planner.calls and not examples.calls
    assert actor.calls[0]['system_prompt'] == prompts.system_prompt % prompts.default_example
    assert 'plan' not in payload(context)['records'][0]
    assert payload(context)['records'][0]['parsed_action']['operation'] == 'fail'


@pytest.mark.parametrize('database,expected,tasks', [
    ({}, None, []),
    ({'a':{'complete':True,'env':'other','task':'other','example':'bad'}}, None, []),
    ({'a':{'complete':False,'env':'android','task':'bad','example':'bad'},
      'b':{'complete':True,'env':'android','task':GOAL,'example':'same','init_state':'other app'},
      'c':{'complete':True,'env':'android','task':'candidate','example':'selected'}}, 'selected', [GOAL,'candidate']),
])
def test_expsearch_matches_original_library_filters(tmp_path, database, expected, tasks):
    """Retain same-task eligibility, commented App filter and selected raw example.

    Args:
        tmp_path: Library directory.
        database: Source experience mapping.
        expected: Selected example or None.
        tasks: Expected unmodified candidate tasks.
    Returns:
        None.
    """
    path = tmp_path/'library.json'
    path.write_text(json.dumps(database))
    calls = []
    def select(query, references, k):
        """Record the external ranker. Args: query,references,k: Original inputs. Returns: Any: Top-k result."""
        calls.append((query,references,k))
        return SimpleNamespace(indices=[len(references)-1])
    ranker = SimpleNamespace(select_topk=select)
    source_module = official('model/example_retrieval/__init__.py', {'json':json, 'Retriever':lambda *args:ranker}, {'ExampleRetriever'})
    original = source_module.ExampleRetriever(str(path), 'external')
    adapter = AndroidGenExamples(str(path), retriever=ranker)
    assert adapter.retrieve_example(GOAL,'android','Settings') == original.retrieve_example(GOAL,'android','Settings') == expected
    assert calls == ([(GOAL,tasks,1)] * 2 if tasks else [])


def test_dot_product_ranking_is_not_normalized_cosine():
    """Run original tensor scoring without loading a checkpoint or calling a service.

    Raises:
        AssertionError: Adapted retrieval normalizes vectors or changes top-k.
    Returns:
        None.
    """
    import torch
    from zhixing.plugins.agent.androidgen._retriever import Retriever

    retriever = Retriever.__new__(Retriever)
    retriever.max_batch_size = 400
    vectors = {'query':[1.,0.], 'angle':[1.,0.], 'length':[2.,2.]}
    retriever.get_embeddings = lambda sentences: torch.tensor([vectors[sentence] for sentence in sentences])
    assert retriever.select_topk('query',['angle','length']).indices.tolist() == [1]
    assert retriever.get_scores('query',['angle','length']).tolist() == [1.,2.]


def test_original_attention_mask_mean_pooling_without_checkpoint():
    """Exercise real tensor pooling with substituted tokenizer/encoder outputs only.

    Raises:
        AssertionError: Padding, averaging or source embedding magnitudes change.
    Returns:
        None.
    """
    import torch
    from zhixing.plugins.agent.androidgen._retriever import Retriever

    def tokenize(sentences, **kwargs):
        """Return original tokenizer-shaped tensors. Args: sentences,kwargs: Request. Returns: dict: Mask."""
        return {'attention_mask':torch.tensor([[1,1,0],[1,0,0]])}
    def encode(**kwargs):
        """Return original encoder-shaped hidden states. Args: kwargs: Tensors. Returns: tuple: Embeddings."""
        return (torch.tensor([[[2.,4.],[4.,8.],[100.,100.]],[[7.,9.],[100.,100.],[100.,100.]]]),)
    retriever = Retriever.__new__(Retriever)
    retriever.tokenizer, retriever.encoder, retriever.device = tokenize, encode, 'cpu'
    assert retriever.get_embeddings(['one','two']).tolist() == [[3.,6.],[7.,9.]]


def test_real_library_adapter_executes_once_in_full_graph(tmp_path):
    """Exercise actual database read/filter/top-one integration with all features enabled.

    Args:
        tmp_path: Source library and graph artifacts.
    Returns:
        None.
    """
    path = tmp_path/'examples.json'
    path.write_text(json.dumps({'x': {'complete':True,'env':'android','init_state':'Different App',
        'task':GOAL,'example':'Real library example'}}))
    calls = []
    def select(query, references, k):
        """Substitute checkpoint scoring only. Args: query,references,k: Original request. Returns: Any: Ranking."""
        calls.append((query,references,k))
        return SimpleNamespace(indices=[0])
    adapter = AndroidGenExamples(str(path), retriever=SimpleNamespace(select_topk=select))
    result, _, _, _, actor, *_ = run_graph(tmp_path/'graph', [code("quote('x')"),code('exit()')], examples=adapter)
    assert result.status is RunStatus.SUCCESS, result.error
    assert calls == [(GOAL,[GOAL],1)]
    assert all('Real library example' in call['system_prompt'] for call in actor.calls)


def test_no_matching_example_uses_source_default(tmp_path):
    """An enabled but unmatched retrieval still uses the original default demonstration.

    Args:
        tmp_path: Graph artifacts.
    Returns:
        None.
    """
    result, _, _, _, actor, _, examples = run_graph(tmp_path,[code('exit()')],examples=Examples(None))
    assert result.status is RunStatus.SUCCESS, result.error
    assert len(examples.calls) == 1
    assert actor.calls[0]['system_prompt'] == prompts.system_prompt % prompts.default_example


def test_original_gpt_messages_images_sampling_and_lazy_adapter(tmp_path, monkeypatch):
    """Compare actual original transport payloads while replacing only external SDK I/O.

    Args:
        tmp_path: Lossless image artifact.
        monkeypatch: Explicit test-only SDK dependency injection.
    Raises:
        AssertionError: Messages, encoded bytes, sampling or lazy initialization differ.
    Returns:
        None.
    """
    backoff = pytest.importorskip('backoff', reason='install the declared androidgen optional extra')
    import base64
    import os
    from openai import APIConnectionError, APIError, RateLimitError
    from zhixing.plugins.agent.androidgen import _gpt
    from zhixing.plugins.llm.androidgen_llm import AndroidGenLLM

    calls = []
    def create(**kwargs):
        """Record only external SDK inputs. Args: kwargs: Original payload. Returns: Any: Completion."""
        calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='raw response'))])
    def client(**kwargs):
        """Substitute original SDK initialization. Args: kwargs: Credential argument. Returns: Any: Fake SDK."""
        assert kwargs == {'api_key':'androidgen-test-placeholder'}
        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    monkeypatch.setenv('OPENAI_TOKEN','androidgen-test-placeholder')
    monkeypatch.setattr(_gpt,'OpenAI',client)
    original = official('model/llms/gpt.py', {'os':os,'backoff':backoff,'base64':base64,'OpenAI':client,
        'APIConnectionError':APIConnectionError,'APIError':APIError,'RateLimitError':RateLimitError},
        {'handle_giveup','handle_backoff','OpenaiEngine'}).OpenaiEngine()
    wrapper = AndroidGenLLM()
    assert wrapper._client is None
    image = tmp_path/'screen.png'
    Image.fromarray(np.zeros((2,3,3),dtype=np.uint8)).save(image)
    history = [{'role':'user','content':{'text':'past','image_url':str(image)}},
        {'role':'assistant','content':{'text':'raw output'}}]
    request = {'prompt':{'text':'current','image_url':str(image)}, 'system_prompt':'system', 'history':history}
    assert wrapper.generate(**request) == original.generate(**request) == 'raw response'
    assert calls[0] == calls[1]
    assert calls[0]['temperature'] == calls[0]['top_p'] == 0.5
    assert calls[0]['max_tokens'] == 4096
    assert [item['role'] for item in calls[0]['messages']] == ['system','user','assistant','user']


def test_generated_algorithm_bodies_match_original_runtime_and_prompts():
    """Verify retained transport/retrieval methods and every original prompt constant.

    Raises:
        AssertionError: A retained executable body changes without an explicit delta.
    Returns:
        None.
    """
    for filename, original_path in (('_gpt.py','model/llms/gpt.py'),('_retriever.py','model/example_retrieval/retriever.py')):
        actual = ast.parse((ROOT/'zhixing/plugins/agent/androidgen'/filename).read_text())
        expected = ast.parse((FIXTURES/(original_path.replace('/','__')+'.txt')).read_text())
        left = {node.name:node for node in actual.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        right = {node.name:node for node in expected.body if isinstance(node,(ast.FunctionDef,ast.ClassDef))}
        for nodes in (left,right):
            for top in nodes.values():
                for node in ast.walk(top):
                    if isinstance(node,(ast.FunctionDef,ast.ClassDef)) and ast.get_docstring(node):
                        node.body.pop(0)
        assert {name:ast.dump(node) for name,node in left.items()} == {name:ast.dump(node) for name,node in right.items()}
    for path in ('model/prompt/android.py','model/planning/prompt.py'):
        tree = ast.parse((FIXTURES/(path.replace('/','__')+'.txt')).read_text())
        namespace = {}
        exec(compile(tree,path,'exec'),namespace)
        for name,value in namespace.items():
            if not name.startswith('__'):
                assert getattr(prompts,name) == value


def test_scoped_adb_and_constructor_do_not_connect():
    """Keep target selection local and optional imports/I/O out of construction.

    Returns:
        None.
    """
    raw = RawEnv()
    AndroidGenEnvironment(raw, adb=Adb(raw.events))
    assert raw.events == []
    bridge = AndroidGenAdb('/tmp/my adb', 'emulator-5554')
    assert bridge._command('adb shell input keyevent 66') == "'/tmp/my adb' -s emulator-5554 shell input keyevent 66"
    with pytest.raises(ValueError):
        bridge._command('other command')


def test_source_hashes_and_mechanical_action_delta():
    """Audit frozen official files and allow only the declared executable differences.

    Raises:
        AssertionError: Upstream evidence or source action semantics changed.
    Returns:
        None.
    """
    manifest = json.loads((FIXTURES/'manifest.json').read_text())
    for info in manifest['files'].values():
        assert hashlib.sha256((FIXTURES/info['fixture']).read_bytes()).hexdigest() == info['sha256']
    original_tree = ast.parse((FIXTURES/'environment__android__env.py.txt').read_text())
    actual_tree = ast.parse(inspect.getsource(source))
    expected_class = next(node for node in original_tree.body if isinstance(node,ast.ClassDef))
    actual_class = next(node for node in actual_tree.body if isinstance(node,ast.ClassDef))
    original_methods = {node.name:node for node in expected_class.body if isinstance(node,ast.FunctionDef)}
    for method in actual_class.body:
        if not isinstance(method,ast.FunctionDef) or method.name in ('__init__','get_current_state','close'):
            continue
        text = ast.unparse(original_methods[method.name])
        text = text.replace('os.system(', 'self.adb.system(').replace('os.popen(', 'self.adb.popen(')
        text = text.replace('_PATTERN_TO_ACTIVITY.items()', 'self.adb.patterns.items()')
        text = text.replace('get_adb_activity(app_name)', 'self.adb.get_adb_activity(app_name)')
        if method.name == '_format_element':
            text = text.replace('tooltip="{tooltip}"', 'tooltip="{ui_element.tooltip}"')
        expected = ast.parse(text).body[0]
        for node in (method,expected):
            if ast.get_docstring(node):
                node.body.pop(0)
        assert ast.dump(method,include_attributes=False) == ast.dump(expected,include_attributes=False), method.name
    expected = next(node for node in ast.parse((FIXTURES/'run.py.txt').read_text()).body
        if isinstance(node,ast.FunctionDef) and node.name == 'get_code_snippet')
    actual = next(node for node in actual_tree.body if isinstance(node,ast.FunctionDef) and node.name == 'get_code_snippet')
    actual.body.pop(0)
    assert ast.dump(actual) == ast.dump(expected)


@pytest.mark.parametrize('response', ['plain', '```python\nquote(1)\n```', '```\nquote(1)\n```\n```\nexit()\n```', '```\n\n```'])
def test_first_code_fence_matches_original_extraction(response):
    """Retain the original first-block regex and its fatal no-match behavior.

    Args:
        response: Source model output.
    Returns:
        None.
    """
    original = official('run.py',{'re':re},{'get_code_snippet'}).get_code_snippet
    try:
        expected = original(response)
    except RuntimeError:
        with pytest.raises(RuntimeError):
            source.get_code_snippet(response)
    else:
        assert source.get_code_snippet(response) == expected


@pytest.mark.parametrize('settings', [{'max_rounds':0}, {'max_rounds':True}, {'max_plan_attempts':0},
    {'reflectplan':1}, {'model_type':'other'}, {'planner_model_type':'other'}, {'model_params':{'api_key':'forbidden'}},
    {'example_params':{'retriever':object()}}])
def test_invalid_public_construction_settings(settings):
    """Reject unsupported declarations before any service is constructed.

    Args:
        settings: Invalid public configuration.
    Returns:
        None.
    """
    with pytest.raises(ValueError):
        build_androidgen_graph(**settings)
