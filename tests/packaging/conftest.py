from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, (
        f"command failed: {command}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
    )
    return completed


@pytest.fixture(scope="session")
def built_dist_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build core artifacts with the development build backend already installed.

    Args:
        tmp_path_factory (pytest.TempPathFactory): Session-scoped temporary
            directory factory.

    Raises:
        AssertionError: The wheel or source distribution is not produced.

    Returns:
        Path: Directory containing the core wheel and source distribution.
    """
    out = tmp_path_factory.mktemp("dist")
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--no-isolation",
            "--outdir",
            str(out),
            str(ROOT),
        ],
        cwd=ROOT,
    )
    assert (out / "zhixing-0.1.0-py3-none-any.whl").is_file()
    assert (out / "zhixing-0.1.0.tar.gz").is_file()
    return out


@pytest.fixture(scope="session")
def wheel_path(built_dist_dir: Path) -> Path:
    return built_dist_dir / "zhixing-0.1.0-py3-none-any.whl"


@pytest.fixture(scope="session")
def isolated_install(
    tmp_path_factory: pytest.TempPathFactory,
    wheel_path: Path,
) -> tuple[Path, Path, dict[str, str]]:
    root = tmp_path_factory.mktemp("isolated-wheel")
    environment = root / "venv"
    workdir = root / "workdir"
    workdir.mkdir()
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)
    clean_env["PYTHONNOUSERSITE"] = "1"
    _run([str(python), "-m", "pip", "install", str(wheel_path)], cwd=workdir, env=clean_env)
    return python, workdir, clean_env


@pytest.fixture(scope="session")
def isolated_openai_install(
    tmp_path_factory: pytest.TempPathFactory,
    wheel_path: Path,
) -> tuple[Path, Path, dict[str, str]]:
    """Install the wheel with its declared OpenAI extra in isolation.

    Args:
        tmp_path_factory: Session-scoped temporary directory factory.
        wheel_path: Built ZhiXing wheel.

    Raises:
        AssertionError: Virtual environment creation or installation fails.

    Returns:
        Isolated Python, unrelated workdir, and clean environment mapping.
    """
    root = tmp_path_factory.mktemp("isolated-openai-wheel")
    environment = root / "venv"
    workdir = root / "workdir"
    workdir.mkdir()
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = environment / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    clean_env = os.environ.copy()
    clean_env.pop("PYTHONPATH", None)
    clean_env["PYTHONNOUSERSITE"] = "1"
    _run(
        [str(python), "-m", "pip", "install", f"{wheel_path}[openai]"],
        cwd=workdir,
        env=clean_env,
    )
    return python, workdir, clean_env
