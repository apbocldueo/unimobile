"""Contracts for the allowlisted public-source release builder."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUILDER = REPOSITORY_ROOT / "scripts/build_public_release.py"


def _run(command: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run one deterministic test command.

    Args:
        command: Executable and arguments.
        cwd: Working directory.

    Raises:
        None.

    Returns:
        Completed process with captured text streams.
    """
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True)


def _repository(tmp_path: Path) -> Path:
    """Create one committed Git fixture with public and private files.

    Args:
        tmp_path: Pytest-owned temporary directory.

    Raises:
        OSError: Fixture files cannot be created.
        subprocess.CalledProcessError: Git fixture setup fails.

    Returns:
        Initialized repository root.
    """
    root = tmp_path / "source"
    (root / "release").mkdir(parents=True)
    (root / "src").mkdir()
    (root / "studio/node_modules/pkg").mkdir(parents=True)
    (root / "src/app.py").write_text("print('safe')\n", encoding="utf-8")
    (root / "private.txt").write_text("not public\n", encoding="utf-8")
    (root / "studio/node_modules/pkg/index.js").write_text(
        "generated\n", encoding="utf-8"
    )
    (root / "release/public.gitignore").write_text(
        "secrets.yaml\n", encoding="utf-8"
    )
    manifest = {
        "schemaVersion": 1,
        "includePaths": ["src", "release/public.gitignore"],
        "excludePaths": [],
        "excludeNames": ["node_modules"],
        "excludeSuffixes": [".pyc"],
        "renames": {"release/public.gitignore": ".gitignore"},
        "maxFileBytes": 10000,
    }
    (root / "release/public-manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    subprocess.run(["git", "init", "-b", "main"], cwd=root, check=True)
    subprocess.run(["git", "add", "."], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release@example.invalid",
            "commit",
            "-m",
            "fixture",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return root


def test_builder_exports_only_allowlisted_tracked_files(tmp_path: Path) -> None:
    """Export selected files, apply renames, and omit private/generated data."""
    root = _repository(tmp_path)
    destination = tmp_path / "public"
    result = _run(
        [
            sys.executable,
            str(BUILDER),
            "--root",
            str(root),
            "--manifest",
            "release/public-manifest.json",
            "--destination",
            str(destination),
        ],
        cwd=root,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert (destination / "src/app.py").is_file()
    assert (destination / ".gitignore").is_file()
    assert not (destination / "private.txt").exists()
    assert not (destination / "studio").exists()
    inventory = json.loads(
        (destination / "RELEASE-MANIFEST.json").read_text(encoding="utf-8")
    )
    assert inventory["dirtyPreview"] is False
    assert {item["path"] for item in inventory["files"]} == {
        ".gitignore",
        "src/app.py",
    }


def test_builder_blocks_dirty_release_by_default(tmp_path: Path) -> None:
    """Refuse to claim reproducibility when tracked content is uncommitted."""
    root = _repository(tmp_path)
    (root / "src/app.py").write_text("print('changed')\n", encoding="utf-8")
    result = _run(
        [
            sys.executable,
            str(BUILDER),
            "--root",
            str(root),
            "--manifest",
            "release/public-manifest.json",
        ],
        cwd=root,
    )
    assert result.returncode == 2
    assert "Working tree is dirty" in result.stdout


def test_builder_blocks_secret_shaped_content(tmp_path: Path) -> None:
    """Reject allowlisted files containing a private-key marker."""
    root = _repository(tmp_path)
    (root / "src/app.py").write_text(
        "-----BEGIN " + "PRIVATE KEY-----\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "src/app.py"], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release@example.invalid",
            "commit",
            "-m",
            "secret fixture",
        ],
        cwd=root,
        check=True,
        capture_output=True,
    )
    result = _run(
        [
            sys.executable,
            str(BUILDER),
            "--root",
            str(root),
            "--manifest",
            "release/public-manifest.json",
        ],
        cwd=root,
    )
    assert result.returncode == 2
    assert "Possible credential" in result.stdout


@pytest.mark.parametrize("target", ["../escape", "C:\\escape", ".", "RELEASE-MANIFEST.json", ".env.production", "local.secrets.yaml"])
def test_builder_rejects_unsafe_rename_before_writing(tmp_path: Path, target: str) -> None:
    """Reject traversal, reserved inventory names and private output paths.

    Args:
        tmp_path: Isolated test directory.
        target: Deliberately unsafe rename target.
    Raises:
        AssertionError: The exporter accepts the path or writes any output.
    Returns:
        None.
    """
    root = _repository(tmp_path)
    manifest_path = root / "release/public-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["renames"]["src/app.py"] = target
    manifest_path.write_text(json.dumps(manifest))
    output = tmp_path / "public"
    result = _run([sys.executable, str(BUILDER), "--root", str(root),
                   "--allow-dirty", "--destination", str(output)], cwd=root)
    assert result.returncode == 2
    assert not output.exists()


def test_new_files_require_explicit_preview(tmp_path: Path) -> None:
    """Keep new files out by default and label opt-in export as preview.

    Args:
        tmp_path: Isolated test directory.
    Raises:
        AssertionError: Selection or preview labeling violates the contract.
    Returns:
        None.
    """
    root = _repository(tmp_path)
    (root / "src/new.py").write_text("# new public code\n")
    for include_new in (False, True):
        output = tmp_path / str(include_new)
        args = [sys.executable, str(BUILDER), "--root", str(root), "--allow-dirty",
                "--destination", str(output)]
        if include_new:
            args.append("--include-untracked")
        result = _run(args, cwd=root)
        assert result.returncode == 0, result.stdout
        assert (output / "src/new.py").exists() is include_new
        assert json.loads((output / "RELEASE-MANIFEST.json").read_text())["dirtyPreview"]


def test_symlink_ancestor_is_rejected(tmp_path: Path) -> None:
    """Prevent traversal through a substituted directory symlink.

    Args:
        tmp_path: Isolated test directory.
    Raises:
        AssertionError: A directory symlink is accepted.
    Returns:
        None.
    """
    root = _repository(tmp_path)
    (root / "src").rename(root / "private-source")
    (root / "src").symlink_to(root / "private-source", target_is_directory=True)
    result = _run([sys.executable, str(BUILDER), "--root", str(root), "--allow-dirty"], cwd=root)
    assert result.returncode == 2
    assert "Symlinks" in result.stdout


def test_existing_destination_is_preserved(tmp_path: Path) -> None:
    """Refuse to merge a release into existing user work.

    Args:
        tmp_path: Isolated test directory.
    Raises:
        AssertionError: Existing content is overwritten or added to.
    Returns:
        None.
    """
    root = _repository(tmp_path)
    output = tmp_path / "public"
    output.mkdir()
    (output / "keep.txt").write_text("keep")
    result = _run([sys.executable, str(BUILDER), "--root", str(root),
                   "--destination", str(output)], cwd=root)
    assert result.returncode == 2
    assert (output / "keep.txt").read_text() == "keep"
    assert len(list(output.iterdir())) == 1


def test_export_is_repeatable_and_retains_public_ignore_template(tmp_path: Path) -> None:
    """Preserve the public ignore template and produce repeatable inventories.

    Args:
        tmp_path: Isolated test directory.
    Raises:
        AssertionError: Template bytes or repeated inventories differ.
    Returns:
        None.
    """
    root = _repository(tmp_path)
    manifest_path = root / "release/public-manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["retainRenamedSources"] = True
    manifest_path.write_text(json.dumps(manifest))
    inventories = []
    for name in ("one", "two"):
        output = tmp_path / name
        result = _run([sys.executable, str(BUILDER), "--root", str(root),
                       "--allow-dirty", "--destination", str(output)], cwd=root)
        assert result.returncode == 0, result.stdout
        assert (output / "release/public.gitignore").read_bytes() == (output / ".gitignore").read_bytes()
        inventories.append((output / "RELEASE-MANIFEST.json").read_bytes())
    assert inventories[0] == inventories[1]
