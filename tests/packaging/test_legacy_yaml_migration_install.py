"""Offline clean-wheel acceptance for all nine sequential migration results."""

import importlib.metadata
import os
from pathlib import Path
import shutil
import subprocess
import sys
import venv

import pytest


@pytest.mark.packaging_acceptance
def test_nine_migrated_graphs_from_installed_wheel(wheel_path, tmp_path):
    """Install only declared base/vision requirements and execute copied graphs.

    Args:
        wheel_path: Fresh package built from the current worktree.
        tmp_path: Isolated environment outside the repository.
    Raises:
        AssertionError: Offline install, compilation boundaries or any graph fails.
    Returns:
        None.
    """
    environment, work = tmp_path / "venv", tmp_path / "work"
    work.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin/python"
    site = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    for name in ("pydantic", "pydantic-core", "typing-extensions", "typing-inspection", "annotated-types", "PyYAML", "Pillow", "numpy", "opencv-python"):
        distribution = importlib.metadata.distribution(name)
        for member in distribution.files or ():
            if member.is_absolute() or ".." in member.parts:
                continue
            source, target = distribution.locate_file(member), site / member
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONNOUSERSITE"] = "1"
    install = subprocess.run([str(python), "-m", "pip", "install", "--no-index", str(wheel_path)], cwd=work,
        env=env, capture_output=True, text=True, timeout=90, check=False)
    assert install.returncode == 0, install.stdout + install.stderr
    root = Path(__file__).resolve().parents[2]
    for name in ("appagent", "guicourse", "showui", "os_genesis", "gui_schema_cn", "mobile_agent", "mobile_agent_v2_migrated", "mobile_use", "uground"):
        shutil.copyfile(root / "examples/graphs" / (name + ".yaml"), work / (name + ".yaml"))
    shutil.copyfile(Path(__file__).with_name("legacy_yaml_migration_probe.py"), work / "probe.py")
    probe = subprocess.run([str(python), "-I", "probe.py"], cwd=work, env=env,
        capture_output=True, text=True, timeout=90, check=False)
    assert probe.returncode == 0, probe.stdout + probe.stderr
    assert "legacy-yaml-installed:" in probe.stdout
