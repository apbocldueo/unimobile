"""Clean-wheel base authoring and installed complete online graph, without network."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest
from test_m3a_install import copy_distribution


@pytest.mark.packaging_acceptance
def test_ecoagent_base_wheel_and_installed_online(wheel_path,tmp_path):
    """Install the wheel in a fresh environment and execute from an unrelated directory.

    Args:
        wheel_path: Fresh distribution built from this checkout.
        tmp_path: Isolated environment and work directory.
    Raises:
        AssertionError: Base imports, resources, dry-run or fake online execution fails.
    Returns:
        None.
    """
    root=Path(__file__).resolve().parents[2]
    environment,work=tmp_path/'venv',tmp_path/'work'
    work.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python=environment/'bin/python'
    site=environment/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'
    for name in ('pydantic','pydantic-core','typing-extensions','typing-inspection','annotated-types','PyYAML','Pillow'):
        copy_distribution(name,site)
    env={key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','OPENAI_API_KEY')}
    env['PYTHONNOUSERSITE']='1'
    install=subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps',str(wheel_path)],
        cwd=work,env=env,capture_output=True,text=True,timeout=60)
    assert install.returncode==0,install.stdout+install.stderr
    for src,name in ((Path(__file__).with_name('ecoagent_probe.py'),'probe.py'),
        (root/'examples/graphs/ecoagent_online.yaml','ecoagent_online.yaml'),
        (root/'examples/sdk/ecoagent_online.py','example.py')):
        shutil.copyfile(src,work/name)
    dry=subprocess.run([str(python),'-I','example.py','--dry-run'],cwd=work,env=env,capture_output=True,text=True,timeout=30)
    assert dry.returncode==0,dry.stdout+dry.stderr
    assert json.loads(dry.stdout)['execution_evidence'] is False
    isolation="""
import sys,threading
from zhixing.graph import load_graph_yaml
from zhixing.sdk import compile_agent
before=set(threading.enumerate())
compile_agent(load_graph_yaml('ecoagent_online.yaml'))
assert not {'openai','requests','torch','transformers','uiautomator2'} & set(sys.modules)
assert set(threading.enumerate())==before
"""
    check=subprocess.run([str(python),'-I','-c',isolation],cwd=work,env=env,capture_output=True,text=True,timeout=30)
    assert check.returncode==0,check.stdout+check.stderr
    probe=subprocess.run([str(python),'-I','probe.py'],cwd=work,env=env,capture_output=True,text=True,timeout=30)
    assert probe.returncode==0,probe.stdout+probe.stderr
    assert 'ecoagent-installed:' in probe.stdout
