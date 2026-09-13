from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


@pytest.mark.packaging_acceptance
def test_wheel_from_unrelated_cwd(
    isolated_install: tuple[Path, Path, dict[str, str]],
):
    """Install the wheel outside the repository and exercise public contracts.

    Args:
        isolated_install (tuple[Path, Path, dict[str, str]]): Isolated Python,
            unrelated work directory, and clean environment.

    Raises:
        AssertionError: Installation or any public API acceptance check fails.

    Returns:
        None.
    """
    python, workdir, clean_env = isolated_install
    agent = workdir / "agent.yaml"
    agent.write_text(
        """\
schema_version: 1
agent_type: modular_agent
device:
  name: android
  params: {}
agent:
  components:
    perception: {name: custom_perception, params: {}}
    reasoning: {name: custom_reasoning, params: {}}
    memory: {name: custom_memory, params: {}}
""",
        encoding="utf-8",
    )
    benchmark = workdir / "benchmark.json"
    benchmark.write_text(
        json.dumps(
            [
                {
                    "id": "installed-001",
                    "instruction": "Verify installed contracts",
                    "type": "static",
                    "task_initializer": {},
                    "environment_initializer": [],
                    "evaluator": {
                        "name": "system_state",
                        "params": {"method": "file_exist"},
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    graph = workdir / "graph.yaml"
    graph.write_text(
        """\
kind: agent_graph
schema_version: 1
contract_version: "1.0"
profile: mobile_agent
nodes:
  - {id: input, kind: input, lifecycle: on_run_start}
  - id: perception
    kind: component
    role: perception
    lifecycle: per_step
    component: {policy: single, candidates: [{namespace: agent.perception, name: custom_perception}]}
  - id: reasoning
    kind: component
    role: reasoning
    lifecycle: per_step
    component: {policy: single, candidates: [{namespace: agent.reasoning, name: custom_reasoning}]}
  - id: action_executor
    kind: component
    role: action_executor
    lifecycle: per_step
    primary: true
    component: {policy: single, candidates: [{namespace: agent.action_executor, name: legacy_action_executor}]}
  - {id: output, kind: output, lifecycle: terminal}
edges:
  - {source: {node: input, port: task}, target: {node: reasoning, port: task}, kind: data}
  - {source: {node: input, port: observation}, target: {node: perception, port: observation}, kind: data}
  - {source: {node: perception, port: perception}, target: {node: reasoning, port: perception}, kind: data}
  - {source: {node: reasoning, port: action}, target: {node: action_executor, port: action}, kind: data}
  - {source: {node: action_executor, port: result}, target: {node: output, port: result}, kind: data}
""",
        encoding="utf-8",
    )
    script = r"""
import http.client
import json
import pathlib
import sqlite3
import sys
import threading
import time
from dataclasses import replace
from types import SimpleNamespace
import zhixing
import zhixing.components as components
from zhixing.config.contracts import load_agent_yaml, load_benchmark_json
from zhixing.graph import load_graph_yaml, multi_agent_template, react_template
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan
from zhixing.agents import build_builtin_mobile_agent_graph
from zhixing.resources import read_prompt
assert zhixing.__version__ == '0.1.0'
assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve())
assert set(zhixing.__all__) == {
    'AgentConfig',
    'AgentGraphBuilder',
    'AgentRunConfig',
    'BenchmarkSuite',
    'BenchmarkTask',
    'ExecutableAgent',
    'ValidationIssue',
    '__version__',
    'compile_agent',
    'load_agent',
    'predicate',
}
assert len(components.ComponentRole) == 11
assert components.Action is __import__('zhixing.core.agent.protocol', fromlist=['Action']).Action
assert load_agent_yaml('agent.yaml').schema_version == 1
assert load_benchmark_json('benchmark.json').root[0].id == 'installed-001'
compiled = load_graph_yaml('graph.yaml')
assert compiled.is_success, compiled.to_safe_dict()
assert compiled.graph.validate_graph().is_valid
assert compiled.graph.canonical_hash().startswith('sha256:')
react = react_template()
assert react.validate_graph().is_valid
assert react.canonical_hash().startswith('sha256:')
class Component:
    def invoke(self, value, runtime):
        return {'component': 'fake', 'input': value, 'decision': 'finish'}
multi = multi_agent_template()
components = {
    'manager_component': Component(),
    'operator_component': Component(),
    'critic_component': Component(),
    'revision': Component(),
    'revised_multi_action': Component(),
    'multi_action': Component(),
    'multi_finish': Component(),
}
result = GraphExecutionKernel().run(
    bind_execution_plan(multi, components),
    {'value': {'task': 'installed composition'}},
)
assert result.status is KernelStatus.SUCCESS, (result.error_code, result.error)
assert result.outputs
assert read_prompt('reasoning_general.md').strip()
bad = sorted(name for name in sys.modules if name.split('.')[0] in {'torch', 'transformers', 'cv2', 'hmdriver2', 'openai'})
assert not bad, bad
assert not any(name.startswith(('zhixing.plugins', 'zhixing.devices')) for name in sys.modules)
sdk_graph = build_builtin_mobile_agent_graph()
assert sdk_graph.validate_graph().is_valid
assert zhixing.compile_agent(sdk_graph).canonical_hash == sdk_graph.canonical_hash()
from zhixing.components import (
    Action,
    ActionType,
    ObservationRequest,
    RunStatus,
    RuntimeContext,
)
from zhixing.runtime import AndroidGraphRuntime, build_android_smoke_plan
class FakeAndroidDevice:
    serial = 'installed-fake'
    platform = 'android'
    w = 80
    h = 120
    def screenshot(self, path):
        pathlib.Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'x' * 64)
        return path
    def get_xml(self, path):
        value = '<hierarchy/>'
        pathlib.Path(path).write_text(value, encoding='utf-8')
        return value
    def go_home(self):
        return None
installed_artifacts = pathlib.Path.cwd() / 'artifacts'
installed_result = AndroidGraphRuntime().run(
    build_android_smoke_plan(),
    {'value': ObservationRequest()},
    artifact_root=installed_artifacts,
    runtime=RuntimeContext(run_id='installed-android-runtime'),
    device=FakeAndroidDevice(),
)
assert installed_result.status is RunStatus.SUCCESS, installed_result.to_safe_dict()
assert installed_result.artifact_namespace == 'installed-android-runtime'
assert (installed_artifacts / 'installed-android-runtime' / 'manifest.json').is_file()
from zhixing.graph import (
    AgentGraph,
    ComponentBinding,
    EdgeKind,
    GraphComponentRef,
    GraphEdge,
    GraphNode,
    GraphPolicies,
    NodeKind,
    NodeLifecycle,
    PortAddress,
)
from zhixing.runtime import MappingComponentResolver
from zhixing.runtime.android import (
    ACTION_EXECUTOR_CONTRACT,
    DEVICE_OBSERVE_CONTRACT,
    TRANSFORM_CONTRACT,
    FixedActionComponent,
)
from zhixing.studio import (
    BenchmarkEventNotifier,
    DurableBenchmarkEventService,
    ExperimentDefinitionSnapshotV1,
    SQLiteAgentDocumentRepository,
    SQLiteStudioBenchmarkExperimentRepository,
    StudioApplicationService,
    StudioBenchmarkExperimentApplicationService,
    StudioBenchmarkExperimentCreateRequestV1,
    StudioBenchmarkEventPageV1,
    build_default_replay_service,
    build_default_studio_run_composition,
    build_studio_component_catalog,
)
import zhixing.studio as studio
from zhixing.studio.httpd import create_http_server
from zhixing.studio.flow_template_loader import get_flow_template_document
from zhixing.catalog import BUILTIN_COMPONENT_CATALOG, BuiltInComponentCatalog
from zhixing.studio.run_execution import (
    AndroidDeviceProfile,
    AndroidDeviceProfileResolver,
    ProductionComponentResolverFactory,
)
assert ExperimentDefinitionSnapshotV1 is not None
assert StudioBenchmarkExperimentApplicationService is not None
assert StudioBenchmarkExperimentCreateRequestV1 is not None
assert StudioBenchmarkEventPageV1 is not None
assert not hasattr(studio, 'PreparedStudioBenchmarkDefinition')
installed_experiment_repository = SQLiteStudioBenchmarkExperimentRepository(
    pathlib.Path.cwd() / 'stage5-experiment.sqlite3'
)
installed_benchmark_notifier = BenchmarkEventNotifier()
installed_benchmark_events = DurableBenchmarkEventService(
    installed_experiment_repository,
    notifier=installed_benchmark_notifier,
)
assert installed_benchmark_events.repository is installed_experiment_repository
assert installed_benchmark_events.notifier is installed_benchmark_notifier
assert installed_experiment_repository.find_by_client_request_id(
    'clean-wheel-missing-request'
) is None

class InstalledLLM:
    '''Return one deterministic terminal response without network access.'''

    def generate(self, prompt, images=None):
        '''Return a parser-compatible completion response.'''
        del prompt, images
        return json.dumps({'action': 'DONE', 'params': {}, 'thought': 'done'})

stage3_database = pathlib.Path.cwd() / 'stage3-studio.sqlite3'
stage3_test_specs = tuple(
    replace(item, required_modules=())
    if (item.namespace, item.name) == ('llm', 'openai_llm')
    else item
    for item in BUILTIN_COMPONENT_CATALOG.entries()
)
stage3_catalog = build_studio_component_catalog(
    built_in_catalog=BuiltInComponentCatalog(stage3_test_specs),
)
stage3_agents = SQLiteAgentDocumentRepository(stage3_database)
stage3_replay = build_default_replay_service(stage3_database)
stage3_authoring = StudioApplicationService(
    catalog=stage3_catalog,
    repository=stage3_agents,
    replay_service=stage3_replay,
)
stage3_agent, stage3_revision = stage3_authoring.create_agent(
    'Installed Stage 3 Agent',
    initial_document=get_flow_template_document('modular_baseline'),
)
assert stage3_revision.compile_snapshot.authoring_policy == (
    'studio.capability-authoring@1'
), stage3_revision.compile_snapshot.model_dump()
assert stage3_revision.compile_snapshot.projection_map, (
    stage3_revision.compile_snapshot.model_dump()
)
stage3_composition = build_default_studio_run_composition(
    stage3_database,
    agents=stage3_agents,
    replay_service=stage3_replay,
    profiles=AndroidDeviceProfileResolver(
        {
            'installed-fake': AndroidDeviceProfile(
                'installed-fake',
                device=FakeAndroidDevice(),
            )
        }
    ),
    components=ProductionComponentResolverFactory(
        dependency_provider={'llm': InstalledLLM()},
    ),
    component_catalog=stage3_catalog,
    enforce_readiness=False,
)
stage3_server = create_http_server(
    '127.0.0.1',
    0,
    application_service=stage3_authoring,
    run_composition=stage3_composition,
    sse_heartbeat_seconds=0.05,
)
stage3_thread = threading.Thread(
    target=stage3_server.serve_forever,
    daemon=True,
)
stage3_thread.start()
stage3_address = ('127.0.0.1', int(stage3_server.server_address[1]))

def installed_http(method, path, payload=None):
    '''Send one JSON request to the installed Stage 3 server.'''
    connection = http.client.HTTPConnection(*stage3_address, timeout=5)
    headers = {'Accept': 'application/json'}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers['Content-Type'] = 'application/json'
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read())
    finally:
        connection.close()

try:
    stage3_status, stage3_created = installed_http(
        'POST',
        '/api/studio/runs',
        {
            'schemaVersion': 1,
            'clientRequestId': 'installed-stage3-request',
            'agentId': stage3_agent.agent_id,
            'revisionId': stage3_revision.revision_id,
            'task': {'text': 'Observe and finish from the installed wheel'},
            'deviceProfileId': 'installed-fake',
        },
    )
    assert stage3_status == 202, stage3_created
    stage3_run_id = stage3_created['runId']
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        stage3_status, stage3_result = installed_http(
            'GET',
            f'/api/studio/runs/{stage3_run_id}',
        )
        assert stage3_status == 200, stage3_result
        if (
            stage3_result['lifecycle'] == 'terminal'
            and stage3_result['replayAvailability'] != 'not_captured'
        ):
            stage3_event_status, stage3_event_page = installed_http(
                'GET',
                f'/api/studio/runs/{stage3_run_id}/events?after=0&limit=100',
            )
            assert stage3_event_status == 200, stage3_event_page
            if any(
                item['kind'] == 'run.terminal'
                for item in stage3_event_page['items']
            ):
                break
        time.sleep(0.02)
    else:
        raise AssertionError('installed Stage 3 Run did not terminate')
    assert stage3_result['result']['status'] == 'success', stage3_result
    stage3_status, stage3_events = installed_http(
        'GET',
        f'/api/studio/runs/{stage3_run_id}/events?after=0&limit=100',
    )
    assert stage3_status == 200, stage3_events
    assert stage3_events['terminal'] is True
    assert any(
        item['kind'] == 'run.terminal'
        for item in stage3_events['items']
    )
    stage3_status, stage3_replay_json = installed_http(
        'GET',
        f'/api/studio/replays/{stage3_run_id}',
    )
    assert stage3_status == 200, stage3_replay_json
    assert stage3_replay_json['provenance'] == 'native_studio_run'
    assert stage3_database.is_file()
finally:
    stage3_server.shutdown()
    stage3_server.server_close()
    stage3_thread.join(timeout=3)
from zhixing.benchmark import (
    BenchmarkExperimentRuntime,
    BenchmarkRunConfig,
    BenchmarkSuiteResult,
    BenchmarkTaskResult,
    EmptyBenchmarkResourceProvider,
)
assert BenchmarkExperimentRuntime is not None
assert BenchmarkRunConfig().artifact_root.as_posix() == 'temp/benchmarks'
assert BenchmarkSuiteResult is not None
assert BenchmarkTaskResult is not None
assert EmptyBenchmarkResourceProvider is not None
print(zhixing.__file__)
"""
    completed = subprocess.run(
        [str(python), "-c", script],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert str(workdir.parents[0] / "venv") in completed.stdout

    cli = subprocess.run(
        [str(python.parent / "zhixing"), "--help"],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert cli.returncode == 0, cli.stderr
    assert "Build and run graph-native ZhiXing Mobile Agents" in cli.stdout

    benchmark_help = subprocess.run(
        [str(python.parent / "zhixing"), "benchmark", "run", "--help"],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert benchmark_help.returncode == 0, benchmark_help.stderr
    assert "--agent NAME=PATH" in benchmark_help.stdout
    assert "--artifact-root" in benchmark_help.stdout

    checked = subprocess.run(
        [str(python), "-m", "pip", "check"],
        cwd=workdir,
        env=clean_env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert checked.returncode == 0, checked.stdout + checked.stderr
