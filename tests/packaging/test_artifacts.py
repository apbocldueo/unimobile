from __future__ import annotations

import email
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


REQUIRED_WHEEL = {
    "zhixing/__init__.py",
    "zhixing/resources.py",
    "zhixing/config/contracts/agent.py",
    "zhixing/prompts/reasoning_general.md",
    "zhixing/studio/data/agent_registry_skeleton.json",
    "zhixing/studio/data/flow_templates/manifest.yaml",
    "zhixing/studio/data/flow_templates/modular_baseline.json",
}
PROHIBITED_PARTS = {
    "/node_modules/",
    "/temp/",
    "secrets.yaml",
    ".env",
    "__pycache__",
    ".ds_store",
}


def _wheel_names(path: Path) -> set[str]:
    with zipfile.ZipFile(path) as archive:
        return set(archive.namelist())


def _assert_clean(names: set[str]):
    for raw_name in names:
        parts = raw_name.lower().strip("/").split("/")
        if parts and parts[0] == "zhixing-0.1.0":
            parts = parts[1:]
        assert not parts or parts[0] not in {"data", "examples", "tests", "openspec", "temp"}, raw_name
        name = "/" + "/".join(parts)
        assert not any(part in name for part in PROHIBITED_PARTS), name


def test_wheel_manifest_and_metadata(wheel_path: Path):
    """Verify the wheel boundary and its Twine-compatible Core Metadata."""
    names = _wheel_names(wheel_path)
    assert REQUIRED_WHEEL <= names
    assert sum(name.startswith("zhixing/prompts/") and name.endswith(".md") for name in names) == 15
    _assert_clean(names)

    metadata_name = next(name for name in names if name.endswith(".dist-info/METADATA"))
    with zipfile.ZipFile(wheel_path) as archive:
        metadata = email.message_from_bytes(archive.read(metadata_name))
    assert metadata["Name"] == "zhixing"
    assert metadata["Metadata-Version"] == "2.4"
    assert metadata["Version"] == "0.1.0"
    assert metadata["Requires-Python"] == ">=3.10"
    assert metadata["License-Expression"] == "Apache-2.0"
    assert set(metadata.get_all("Provides-Extra")) >= {
        "openai",
        "vision",
        "harmony",
        "benchmark",
        "all",
        "dev",
    }


def test_sdist_manifest_is_clean_and_complete(built_dist_dir: Path):
    """Verify the sdist boundary and its Twine-compatible Core Metadata."""
    sdist = built_dist_dir / "zhixing-0.1.0.tar.gz"
    with tarfile.open(sdist, "r:gz") as archive:
        names = set(archive.getnames())
        pkg_info = email.message_from_binary_file(
            archive.extractfile("zhixing-0.1.0/PKG-INFO")
        )
    prefix = "zhixing-0.1.0/"
    assert pkg_info["Metadata-Version"] == "2.4"
    assert {prefix + name for name in REQUIRED_WHEEL} <= names
    assert prefix + "pyproject.toml" in names
    assert prefix + "README.md" in names
    assert prefix + "LICENSE" in names
    _assert_clean(names)


def test_wheel_rebuilt_from_sdist_has_same_public_resources(built_dist_dir: Path, tmp_path: Path):
    sdist = built_dist_dir / "zhixing-0.1.0.tar.gz"
    rebuilt = tmp_path / "rebuilt"
    rebuilt.mkdir()
    source = tmp_path / "source"
    source.mkdir()
    with tarfile.open(sdist, "r:gz") as archive:
        archive.extractall(source)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--outdir",
            str(rebuilt),
            str(source / "zhixing-0.1.0"),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    direct_names = _wheel_names(built_dist_dir / "zhixing-0.1.0-py3-none-any.whl")
    rebuilt_names = _wheel_names(rebuilt / "zhixing-0.1.0-py3-none-any.whl")
    direct_public = {name for name in direct_names if name.startswith("zhixing/")}
    rebuilt_public = {name for name in rebuilt_names if name.startswith("zhixing/")}
    assert rebuilt_public == direct_public
