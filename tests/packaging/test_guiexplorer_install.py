"""Offline isolated-wheel authoring and complete installed online-graph acceptance."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest

from tests.packaging.test_m3a_install import copy_distribution


@pytest.mark.packaging_acceptance
def test_guiexplorer_installed_base_and_complete_graph(wheel_path, tmp_path):
    """Verify base import isolation, packaged provenance and installed YAML execution.

    Args:
        wheel_path: Fresh wheel built from the current project.
        tmp_path: External working directory and clean virtual environment.
    Raises:
        AssertionError: Isolation, resource closure or installed execution fails.
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
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH" and not key.startswith(("OPENAI_", "RAG_"))}
    env["PYTHONNOUSERSITE"] = "1"
    install = subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel_path)],
        cwd=work, env=env, capture_output=True, text=True, timeout=90)
    assert install.returncode == 0, install.stdout + install.stderr
    for source, target in ((root / "examples/graphs/guiexplorer_online.yaml", "guiexplorer_online.yaml"),
            (root / "examples/sdk/guiexplorer_online.py", "example.py"),
            (Path(__file__).with_name("guiexplorer_probe.py"), "probe.py")):
        shutil.copyfile(source, work / target)
    dry = subprocess.run([str(python), "-I", "example.py", "--dry-run"], cwd=work, env=env,
        capture_output=True, text=True, timeout=30)
    assert dry.returncode == 0, dry.stdout + dry.stderr
    assert json.loads(dry.stdout)["execution_evidence"] is False
    check = subprocess.run([str(python), "-I", "-c", "from importlib.resources import files; import sys; from zhixing.graph import load_graph_yaml; from zhixing.sdk import compile_agent; from zhixing.guiexplorer import build_guiexplorer_graph; assert compile_agent(load_graph_yaml('guiexplorer_online.yaml')).canonical_hash == build_guiexplorer_graph().canonical_hash(); assert not {'numpy','cv2','requests','aiohttp','uiautomator2','imagehash','openai','torch','transformers'} & set(sys.modules); assert all(files('zhixing.plugins.agent.guiexplorer').joinpath(p).is_file() for p in ('LICENSE','NOTICE','source-origin.json')); from importlib.metadata import metadata; assert 'guiexplorer' in metadata('zhixing').get_all('Provides-Extra')"],
        cwd=work, env=env, capture_output=True, text=True, timeout=30)
    assert check.returncode == 0, check.stdout + check.stderr
    for name in ("numpy", "opencv-python"):
        copy_distribution(name, site)
    probe = subprocess.run([str(python), "-I", "probe.py"], cwd=work, env=env,
        capture_output=True, text=True, timeout=60)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "guiexplorer-installed:" in probe.stdout
