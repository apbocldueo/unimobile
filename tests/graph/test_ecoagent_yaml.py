"""SDK/YAML semantic identity and side-effect-free authoring."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from zhixing.ecoagent import build_ecoagent_graph
from zhixing.graph import GraphRole, load_graph_yaml
from zhixing.sdk import compile_agent

ROOT=Path(__file__).resolve().parents[2]
YAML=ROOT/'examples/graphs/ecoagent_online.yaml'


def test_yaml_sdk_identity_and_exact_six_families():
    """Compare complete explicit graphs. Returns: None."""
    expected=compile_agent(build_ecoagent_graph())
    actual=compile_agent(load_graph_yaml(YAML))
    assert actual.graph==expected.graph and actual.canonical_hash==expected.canonical_hash
    loop=next(n for n in actual.graph.nodes if n.id=='rounds').loop.body.graph
    assert {n.role for n in loop.nodes if n.role}==set(GraphRole)
    assert len(YAML.read_text().splitlines())<=65


def test_dry_run_is_inert(tmp_path):
    """Compile in a fresh interpreter without network, devices, credentials or threads.

    Args:
        tmp_path: Empty external artifact location.
    Returns:
        None.
    """
    code='''
import sys,threading
from zhixing.ecoagent import build_ecoagent_graph
from zhixing.sdk import compile_agent
from zhixing.graph import load_graph_yaml
before=set(threading.enumerate())
assert compile_agent(load_graph_yaml(sys.argv[1])).canonical_hash==compile_agent(build_ecoagent_graph()).canonical_hash
assert set(threading.enumerate())==before
assert not {'openai','requests','uiautomator2','torch','transformers'} & set(sys.modules)
'''
    env={k:v for k,v in os.environ.items() if k!='OPENAI_API_KEY'}
    result=subprocess.run([sys.executable,'-c',code,str(YAML)],cwd=ROOT,env=env,capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stdout+result.stderr
    dry=subprocess.run([sys.executable,str(ROOT/'examples/sdk/ecoagent_online.py'),'--dry-run','--artifact-root',str(tmp_path)],
        cwd=ROOT,env={**env,'PYTHONPATH':str(ROOT)},capture_output=True,text=True,timeout=20)
    assert dry.returncode==0,dry.stdout+dry.stderr
    assert json.loads(dry.stdout)=={'graph_hash':compile_agent(build_ecoagent_graph()).canonical_hash,'execution_evidence':False}
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('settings',[{'max_rounds':0},{'max_rounds':True},{'max_rounds':1000},
    {'fix_protocol':'yes'},{'wait_seconds':-1},{'model_params':{'unknown':{}}}])
def test_invalid_public_configuration(settings):
    """Reject invalid authoring inputs. Args: settings: Invalid configuration. Returns: None."""
    with pytest.raises(ValueError):build_ecoagent_graph(**settings)
