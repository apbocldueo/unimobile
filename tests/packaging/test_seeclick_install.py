"""SeeClick base-wheel execution outside the checkout without optional runtimes."""

import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest


@pytest.mark.packaging_acceptance
def test_seeclick_from_installed_base_wheel(wheel_path,tmp_path):
    """Install only the base wheel, then run its YAML and copied SDK example.

    Args:
        wheel_path: Freshly built core wheel.
        tmp_path: Isolated virtual environment and unrelated working directory.
    Raises:
        AssertionError: Installation, lazy imports, resources or execution fail.
    Returns:
        None.
    """
    environment,work = tmp_path / "venv", tmp_path / "work"
    work.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    site = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    # Offline installation copies only declared base distributions, never the
    # development site-packages tree or optional model libraries.
    for name in ("pydantic","pydantic-core","typing-extensions","typing-inspection","annotated-types","PyYAML","Pillow"):
        distribution = importlib.metadata.distribution(name)
        for member in distribution.files or ():
            if member.is_absolute() or ".." in member.parts:
                continue
            source,target = distribution.locate_file(member),site / member
            if source.is_file():
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copy2(source,target)
    env = {key:value for key,value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONNOUSERSITE"] = "1"
    install = subprocess.run([str(python),"-m","pip","install","--no-index",str(wheel_path)],
        cwd=work,env=env,capture_output=True,text=True,timeout=90,check=False)
    assert install.returncode == 0, install.stdout + install.stderr
    root = Path(__file__).resolve().parents[2]
    for source,name in ((Path(__file__).with_name("seeclick_probe.py"),"probe.py"),
        (root / "examples/graphs/seeclick_online.yaml","seeclick_online.yaml"),
        (root / "tests/fixtures/seeclick/source_contract.json","source_contract.json"),
        (root / "examples/sdk/seeclick_online.py","example.py")):
        shutil.copyfile(source,work / name)
    probe = subprocess.run([str(python),"-I","probe.py"],cwd=work,env=env,
        capture_output=True,text=True,timeout=90,check=False)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "seeclick-installed:" in probe.stdout
    example = subprocess.run([str(python),"-I","example.py","--dry-run"],cwd=work,env=env,
        capture_output=True,text=True,timeout=90,check=False)
    assert example.returncode == 0, example.stdout + example.stderr
    assert json.loads(example.stdout)["execution_evidence"] is False
