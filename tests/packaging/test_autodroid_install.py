"""Clean-wheel acceptance for the AutoDroid online template and resources."""

from pathlib import Path
import importlib.metadata
import shutil
import subprocess
import sys
import venv
import os

import pytest


@pytest.mark.packaging_acceptance
def test_autodroid_from_installed_wheel(wheel_path, tmp_path):
    """Execute installed components through public compilation and Android services.

    Args:
        wheel_path: Built core wheel.
        tmp_path: Unrelated work and virtual environment directory.
    Raises:
        AssertionError: A lazy import, packaged resource or execution check fails.
    Returns:
        None.
    """
    environment, workdir = tmp_path / "venv", tmp_path / "work"
    workdir.mkdir()
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "bin" / "python"
    # Seed only base distributions from this interpreter for fully offline
    # acceptance. The venv never inherits the development site-packages path.
    site = environment / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    for name in ("pydantic", "pydantic-core", "typing-extensions", "typing-inspection", "annotated-types", "PyYAML", "Pillow"):
        distribution = importlib.metadata.distribution(name)
        for member in distribution.files or ():
            if member.is_absolute() or ".." in member.parts:
                continue
            source, target = distribution.locate_file(member), site / member
            if source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
    install = subprocess.run([str(python), "-m", "pip", "install", "--no-index", str(wheel_path)],
                             cwd=workdir, capture_output=True, text=True, timeout=90, check=False)
    assert install.returncode == 0, install.stdout + install.stderr
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env["PYTHONNOUSERSITE"] = "1"
    root = Path(__file__).resolve().parents[2]
    script = workdir / "autodroid_probe.py"
    shutil.copyfile(Path(__file__).with_name("autodroid_probe.py"), script)
    shutil.copyfile(root / "examples/graphs/autodroid_online.yaml", workdir / "autodroid_online.yaml")
    result = subprocess.run([str(python), str(script)], cwd=workdir, env=env,
                            capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "autodroid-installed:" in result.stdout
