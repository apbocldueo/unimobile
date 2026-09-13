"""Packaging boundary tests for independently distributed Benchmark content."""

from __future__ import annotations

import zipfile
from pathlib import Path


def test_core_wheel_excludes_first_party_benchmark_assets(wheel_path: Path) -> None:
    """Keep large first-party Benchmark resources out of the core wheel.

    Args:
        wheel_path (Path): Session-built ZhiXing wheel.

    Raises:
        AssertionError: A top-level Benchmark resource entered the wheel.

    Returns:
        None.
    """
    with zipfile.ZipFile(wheel_path) as archive:
        names = tuple(archive.namelist())
    assert any(name.startswith("zhixing/benchmark/") for name in names)
    assert not any(name.startswith("benchmarks/") for name in names)
    assert not any("AndroidWorld_33.mp4" in name for name in names)

