"""Verify AndroidGen base authoring isolation and installed full YAML execution."""

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
def test_androidgen_base_and_installed_online(wheel_path, tmp_path):
    """Install a fresh wheel outside the source tree and execute all six families.

    Args:
        wheel_path: Fresh wheel built from the current project.
        tmp_path: Clean virtual environment and unrelated execution directory.
    Raises:
        AssertionError: Base import isolation, provenance or installed execution fails.
    Returns:
        None.
    """
    root = Path(__file__).resolve().parents[2]
    environment, work = tmp_path/'venv', tmp_path/'work'
    work.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment/'bin/python'
    site = environment/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'site-packages'
    for name in ('pydantic','pydantic-core','typing-extensions','typing-inspection','annotated-types','PyYAML','Pillow'):
        copy_distribution(name,site)
    env = {key:value for key,value in os.environ.items() if key not in ('PYTHONPATH','OPENAI_API_KEY','OPENAI_TOKEN')}
    env['PYTHONNOUSERSITE'] = '1'
    install = subprocess.run([str(python),'-m','pip','install','--no-index','--no-deps',str(wheel_path)],
        cwd=work,env=env,capture_output=True,text=True,timeout=90)
    assert install.returncode == 0, install.stdout + install.stderr
    for source,name in ((Path(__file__).with_name('androidgen_probe.py'),'probe.py'),
        (root/'examples/graphs/androidgen_online.yaml','androidgen_online.yaml'),
        (root/'examples/sdk/androidgen_online.py','example.py')):
        shutil.copyfile(source,work/name)
    dry = subprocess.run([str(python),'-I','example.py','--dry-run'],cwd=work,env=env,
        capture_output=True,text=True,timeout=90)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    from zhixing.androidgen import build_androidgen_graph

    assert json.loads(dry.stdout) == {'graph_hash':build_androidgen_graph().canonical_hash(), 'execution_evidence':False}
    check = subprocess.run([str(python),'-I','-c',
        "import sys; from importlib.resources import files; from zhixing.graph import load_graph_yaml; "
        "from zhixing.sdk import compile_agent; from zhixing.androidgen import build_androidgen_graph; "
        "a=compile_agent(load_graph_yaml('androidgen_online.yaml')); "
        "assert a.canonical_hash==build_androidgen_graph().canonical_hash(); "
        "assert not {'numpy','cv2','torch','transformers','android_world','openai','backoff'} & set(sys.modules); "
        "assert files('zhixing.plugins.agent.androidgen').joinpath('source-origin.json').is_file(); "
        "assert files('zhixing.plugins.agent.androidgen').joinpath('LICENSE').is_file()"],
        cwd=work,env=env,capture_output=True,text=True,timeout=90)
    assert check.returncode == 0,check.stdout + check.stderr
    for name in ('numpy','opencv-python'):
        copy_distribution(name,site)
    probe = subprocess.run([str(python),'-I','probe.py'],cwd=work,env=env,
        capture_output=True,text=True,timeout=90)
    assert probe.returncode == 0,probe.stdout + probe.stderr
    assert 'androidgen-installed:' in probe.stdout
