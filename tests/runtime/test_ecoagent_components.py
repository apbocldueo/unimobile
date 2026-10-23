"""Source closure, protocol repairs, finite HTTP and portable boundary tests."""

import ast
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from zhixing.components import RunStatus
from zhixing.ecoagent import build_ecoagent_graph
from zhixing.plugins.agent.ecoagent.protocol import commands, parse_plan, needs_model
from zhixing.plugins.llm.ecoagent_llm import EcoAgentLLM
from tests.runtime.ecoagent_support import OFFICIAL, plan, run_graph, definitions


def test_source_hashes_and_copied_prompt_constants():
    """Check every official byte and compare shipped prompts to frozen definitions.

    Returns:
        None.
    """
    manifest=json.loads((OFFICIAL.parent/'source-origin.json').read_text())
    for name,digest in manifest['files'].items():
        assert hashlib.sha256((OFFICIAL/name).read_bytes()).hexdigest()==digest
    from zhixing.plugins.agent.ecoagent import prompts
    text=(OFFICIAL/'prompt.py').read_text()
    original=definitions(text,{n.targets[0].id for n in ast.parse(text).body if isinstance(n,ast.Assign)},{})
    for name in ('PLANNING_PROMPT','REPLANNING_PROMPT','ACTION_PROMPT_UITARS','DESCRIPTION_PROMPT','SUMARRY_PROMPT'):
        assert getattr(prompts,name)==original[name]


def test_full_official_cli_with_recorded_repairs(tmp_path):
    """Import the entire official package and run its actual CLI, not only extracted AST.

    Args:
        tmp_path: Disposable copy, preserving immutable official files.
    Returns:
        None.
    """
    target=tmp_path/'source'
    shutil.copytree(OFFICIAL,target)
    applied=subprocess.run(['git','apply',str(OFFICIAL.parent/'compatibility.patch')],cwd=target,capture_output=True,text=True)
    assert applied.returncode==0,applied.stderr
    env={**os.environ,'OPENAI_API_KEY':'fixture-only','PYTHONNOUSERSITE':'1'}
    probe=subprocess.run([sys.executable,str(OFFICIAL.parent/'cli_probe.py'),str(target)],cwd=target,
        env=env,capture_output=True,text=True,timeout=20)
    assert probe.returncode==0,probe.stdout+probe.stderr
    assert 'official-cli:' in probe.stdout and '"completed": true' in probe.stdout


@pytest.mark.parametrize('output', ['no plan','```JSON\n{}\n```','```JSON\n[]\n```',
    '```JSON\n{"1":{"step":"PRESS_BACK"}}\n```','```JSON\nnot json\n```'])
def test_invalid_initial_plan_fails_before_first_task_action(tmp_path,output):
    """Verify documented fail-fast repair rather than source's invalid-state continuation.

    Args:
        tmp_path,output: Artifacts and malformed external reply.
    Returns:
        None.
    """
    result,runtime,device,models,jobs=run_graph(tmp_path,[output])
    assert result.status is RunStatus.FAILURE
    assert [e for e in device.events if e[0]=='device']==[('device',('input','keyevent','KEYCODE_HOME'))]
    assert not models.calls['action'] and jobs.closed


def test_empty_replan_and_almost_no_replan_fail_without_old_action(tmp_path):
    """Reject missing new instructions and never execute a rejected cached tap.

    Args:
        tmp_path: Isolated artifacts.
    Returns:
        None.
    """
    for index,output in enumerate(('```JSON\n{}\n```','No need to replan.\n')):
        result,runtime,device,models,jobs=run_graph(tmp_path/str(index),
            [plan('INPUT [hi]','TAP Save'),output],summaries=('not correct',))
        assert result.status is RunStatus.FAILURE and jobs.closed
        assert not any(e[0]=='device' and 'tap' in e[1] for e in device.events)


def test_protocol_repairs_are_switchable_and_open_app_remains_unsupported():
    """Keep semantic changes explicit and preserve source unknown/finished rules.

    Returns:
        None.
    """
    with pytest.raises(ValueError): parse_plan(plan('PRESS_HOME',fence='json'),fix_protocol=False)
    assert parse_plan(plan('PRESS_HOME',fence='json'))[0]==('PRESS_HOME',)
    assert commands("Action: click(point='<point>10 20</point>')",fix_protocol=False)==()
    assert commands("Action: click(point='<point>10 20</point>')")==('adb shell input tap 10 20',)
    assert commands("Action: open_app(app_name='Contacts') finished(content='done') press_home()")==()
    assert not needs_model('INPUT invalid') and needs_model('Input [lowercase]')


@pytest.mark.parametrize('operation,expected_cap,expected_images', [('planning',2000,1),('action',256,1),
    ('description',256,1),('summary',256,2)])
def test_http_payload_order_and_role_defaults(tmp_path,monkeypatch,operation,expected_cap,expected_images):
    """Inspect the actual outgoing HTTP body without network or provider substitutions.

    Args:
        tmp_path,monkeypatch: Isolated images and scoped HTTP substitution.
        operation,expected_cap,expected_images: Original role settings.
    Returns:
        None.
    """
    from zhixing.components import DeviceObservation
    from tests.runtime.ecoagent_support import pixels
    from zhixing.plugins.llm import ecoagent_llm as module
    images=[]
    for i in range(expected_images):
        path=tmp_path/f'{i}.png';path.write_bytes(pixels(i))
        images.append(DeviceObservation(str(path),32,48))
    calls=[]
    def http(request,timeout):
        """Inspect transport. Args: request,timeout: HTTP parameters. Returns: BytesIO: JSON reply."""
        calls.append((json.loads(request.data),request.headers,timeout))
        return io.BytesIO(json.dumps({'choices':[{'message':{'content':'reply'}}],'usage':{'total_tokens':9}}).encode())
    monkeypatch.setattr(module,'urlopen',http)
    response=EcoAgentLLM(api_key='fixture-only').complete(operation,'prompt',tuple(images))
    body,headers,timeout=calls[0]
    assert body['max_tokens']==expected_cap and body['temperature']==0
    parts=body['messages'][0]['content']
    assert parts[0]=={'type':'text','text':'prompt'} and len(parts)==expected_images+1
    assert all(set(p['image_url'])=={'url'} for p in parts[1:])
    assert response.total_tokens==9 and headers['Authorization']=='Bearer fixture-only'
    assert timeout==60


@pytest.mark.parametrize('failure', ['http','json','shape'])
def test_http_failure_is_finite_and_sanitized(monkeypatch,failure):
    """Verify bounded failure repairs instead of the original infinite non-OK loop.

    Args:
        monkeypatch,failure: Scoped transport failure scenario.
    Returns:
        None.
    """
    from zhixing.plugins.llm import ecoagent_llm as module
    calls,waits=[],[]
    def http(*args,**kwargs):
        """Fail HTTP. Args: args,kwargs: Request. Raises: OSError: Fixture. Returns: BytesIO: Malformed reply."""
        calls.append(1)
        if failure=='http':raise OSError('private fixture credential')
        return io.BytesIO(b'not json' if failure=='json' else b'{}')
    monkeypatch.setattr(module,'urlopen',http)
    monkeypatch.setattr(module.time,'sleep',waits.append)
    with pytest.raises(RuntimeError,match='finite attempts') as error:
        EcoAgentLLM(api_key='private fixture credential',max_attempts=2).complete('planning','prompt',())
    assert len(calls)==2 and waits==[20]
    assert 'private' not in str(error.value)


@pytest.mark.parametrize('primitive',['shell','screenshot'])
def test_device_failures_are_normalized_and_jobs_close(tmp_path,primitive):
    """Keep real device failure separate from model/plan failure, preserving artifact evidence.

    Args:
        tmp_path,primitive: Artifact root and failing external boundary.
    Returns:
        None.
    """
    from tests.runtime.ecoagent_support import Device
    result,runtime,device,models,jobs=run_graph(tmp_path,[plan('PRESS_BACK')],device=Device(fail=primitive))
    assert result.status is RunStatus.DEVICE_FAILURE,result.error
    assert jobs.closed and not jobs.futures
    assert not models.calls['planning']


def test_real_android_command_builder_keeps_explicit_serial(monkeypatch):
    """Use the existing AndroidDevice command implementation without connecting a device.

    Args:
        monkeypatch: Scoped system-command replacement.
    Returns:
        None.
    """
    from zhixing.devices import android
    from zhixing.plugins.agent.ecoagent.environment import EcoEnvironment
    from zhixing.devices.base import CommandResult
    calls=[]
    def command(argv,**kwargs):
        """Record system argv. Args: argv,kwargs: Device transport. Returns: CommandResult: Success."""
        calls.append(argv)
        return CommandResult('', '', 0)
    monkeypatch.setattr(android,'_execute_command',command)
    native=object.__new__(android.AndroidDevice)
    native.serial='fixture-target'
    with EcoEnvironment(native) as environment:
        assert environment.execute_command('adb shell input tap 10 20')
    assert calls and all(argv[:3]==['adb','-s','fixture-target'] for argv in calls)


def test_pure_decoder_algorithms_match_original_ignoring_documentation():
    """Expanded docstrings are the only changes to copied pure decoder functions.

    Returns:
        None.
    """
    from zhixing.plugins.agent.ecoagent import _decoder
    original=ast.parse((OFFICIAL/'utils/ui_tars_utils.py').read_text())
    copied=ast.parse(Path(_decoder.__file__).read_text())
    def algorithms(tree):
        """Normalize documentation only. Args: tree: Module AST. Returns: dict: Function AST dumps."""
        result={}
        for node in tree.body:
            if isinstance(node,ast.FunctionDef):
                if ast.get_docstring(node):node.body=node.body[1:]
                result[node.name]=ast.dump(node)
        return result
    baseline,actual=algorithms(original),algorithms(copied)
    assert actual and all(baseline[name]==body for name,body in actual.items())
