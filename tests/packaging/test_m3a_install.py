"""Verify M3A from an isolated wheel with explicit offline dependency copies."""

import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest


def copy_distribution(name, site):
    """Copy a preinstalled declared dependency into an otherwise isolated environment.

    Args:
        name: Distribution already available in the test environment.
        site: Destination site-packages directory for the same Python ABI.
    Raises:
        Exception: Dependency metadata or file copying fails.
    Returns:
        None.
    """
    distribution = importlib.metadata.distribution(name)
    for member in distribution.files or ():
        if member.is_absolute() or ".." in member.parts:
            continue
        source, target = distribution.locate_file(member), site / member
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


@pytest.mark.packaging_acceptance
def test_m3a_base_and_vision_wheel(wheel_path, tmp_path):
    """Prove base authoring isolation and full installed YAML execution offline.

    Args:
        wheel_path: Fresh project wheel including M3A helpers and provenance.
        tmp_path: Unrelated workdir and clean virtual environment.
    Raises:
        AssertionError: Import isolation, source resources, dry run or execution fails.
    Returns:
        None.
    """
    root = Path(__file__).resolve().parents[2]
    environment, work = tmp_path / "venv", tmp_path / "work"
    work.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    site = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    for name in ("pydantic", "pydantic-core", "typing-extensions", "typing-inspection", "annotated-types", "PyYAML", "Pillow"):
        copy_distribution(name, site)
    env = {key: value for key, value in os.environ.items() if key not in ("PYTHONPATH", "OPENAI_API_KEY")}
    env["PYTHONNOUSERSITE"] = "1"
    install = subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel_path)],
        cwd=work, env=env, capture_output=True, text=True, timeout=90)
    assert install.returncode == 0, install.stdout + install.stderr
    for source, name in ((Path(__file__).with_name("m3a_probe.py"), "probe.py"),
        (root / "examples/graphs/m3a_online.yaml", "m3a_online.yaml"),
        (root / "examples/sdk/m3a_online.py", "example.py")):
        shutil.copyfile(source, work / name)
    dry = subprocess.run([str(python), "-I", "example.py", "--dry-run"], cwd=work, env=env,
        capture_output=True, text=True, timeout=90)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert json.loads(dry.stdout)["execution_evidence"] is False
    from zhixing.m3a import build_m3a_graph
    assert json.loads(dry.stdout)["graph_hash"] == build_m3a_graph().canonical_hash()
    check = subprocess.run([str(python), "-I", "-c", "import sys; from importlib.resources import files; from zhixing.graph import load_graph_yaml; from zhixing.sdk import compile_agent; import zhixing.m3a; agent=compile_agent(load_graph_yaml('m3a_online.yaml')); assert agent.canonical_hash == zhixing.m3a.build_m3a_graph().canonical_hash(); assert not {'numpy','cv2','android_world','openai'} & set(sys.modules); assert files('zhixing.plugins.agent.m3a').joinpath('source-origin.json').is_file()"],
        cwd=work, env=env, capture_output=True, text=True, timeout=90)
    assert check.returncode == 0, check.stdout + check.stderr
    for name in ("numpy", "opencv-python"):
        copy_distribution(name, site)
    probe = subprocess.run([str(python), "-I", "probe.py"], cwd=work, env=env,
        capture_output=True, text=True, timeout=90)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert 'm3a-installed:' in probe.stdout
