"""Reusable side-effect-free fixtures for Studio Benchmark Catalog tests."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from tests.benchmark.helpers import task, write_package


def write_studio_benchmark_package(
    root: Path,
    *,
    name: str = "fixture",
    version: str = "1.0.0",
    dynamic: bool = False,
    invalid_tasks: bool = False,
) -> Path:
    """Write a valid or deliberately task-invalid Studio Catalog Package.

    Args:
        root: Destination Package root.
        name: Package semantic name.
        version: Package semantic version.
        dynamic: Whether the single task uses a dynamic initializer.
        invalid_tasks: Whether to corrupt the task JSON after manifest creation.

    Raises:
        OSError: Fixture files cannot be written.

    Returns:
        Created Package root.
    """
    selected = task(f"{name}-task")
    if dynamic:
        selected["type"] = "dynamic"
        selected["instruction"] = "Open ${target}"
        selected["task_initializer"] = {
            "target": {"name": "fixture_generator", "params": {}}
        }
    package = write_package(root, tasks=[selected], version=version)
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["identity"]["name"] = name
    manifest["title"] = f"{name.title()} Benchmark"
    if dynamic:
        manifest["plugins"].append(
            {"id": "fixture_generator", "optional": False}
        )
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    if invalid_tasks:
        (package / "tasks" / "test.json").write_text(
            '[{"id":"broken"}]',
            encoding="utf-8",
        )
    return package


class FakeBenchmarkDistribution:
    """Installed distribution metadata fixture that never imports code."""

    def __init__(self, package_root: Path) -> None:
        """Configure one distribution-owned Package.

        Args:
            package_root: Directory containing the fixture manifest.

        Raises:
            None.

        Returns:
            None.
        """
        self.package_root = package_root
        self.files = (
            PurePosixPath("fixture_benchmark/package/benchmark.yaml"),
        )
        self.metadata = {"Name": "fixture-benchmark"}
        self.version = "1.0.0"

    def locate_file(self, path: PurePosixPath) -> Path:
        """Locate the declared manifest without dynamic imports.

        Args:
            path: Distribution-relative metadata path.

        Raises:
            None.

        Returns:
            Fixture manifest path.
        """
        del path
        return self.package_root / "benchmark.yaml"


class FakeBenchmarkEntryPoint:
    """Installed entry point fixture whose implementation must not load."""

    value = "fixture_benchmark.package"

    def __init__(self, distribution: FakeBenchmarkDistribution) -> None:
        """Attach safe distribution metadata.

        Args:
            distribution: Fake installed distribution.

        Raises:
            None.

        Returns:
            None.
        """
        self.dist = distribution
        self.loaded = False

    def load(self) -> Any:
        """Fail if metadata-only discovery imports provider code.

        Args:
            None.

        Raises:
            AssertionError: Always; loading is forbidden.

        Returns:
            Never returns.
        """
        self.loaded = True
        raise AssertionError("Benchmark EntryPoint.load must not be called")


__all__ = [
    "FakeBenchmarkDistribution",
    "FakeBenchmarkEntryPoint",
    "write_studio_benchmark_package",
]
