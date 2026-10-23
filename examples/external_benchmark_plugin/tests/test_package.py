"""Contract tests for the standalone external Benchmark distribution."""

from __future__ import annotations

from pathlib import Path

from zhixing.benchmark import (
    BenchmarkValidationLevel,
    compile_benchmark_package,
    declaration_fixture_set,
    dry_run_benchmark,
    run_benchmark_contract_tests,
)


PACKAGE_ROOT = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "zhixing_photo_smoke_benchmark"
    / "package"
)


def test_external_photo_package_compiles_without_device() -> None:
    """Compile the packaged photo task without connecting a device.

    Args:
        None.

    Raises:
        AssertionError: Package, Plan, or Protocol validation fails.

    Returns:
        None.
    """
    result = compile_benchmark_package(
        PACKAGE_ROOT,
        split="test",
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    assert result.is_success
    assert result.plan is not None
    assert result.protocol is not None
    assert [task.id for task in result.plan.tasks] == ["PhotoSmoke_1"]


def test_external_photo_package_contract_and_dry_run_are_device_free() -> None:
    """Validate fake fixtures and schedule compilation without Android.

    Args:
        None.

    Raises:
        AssertionError: Contract fixtures or side-effect-free dry-run fail.

    Returns:
        None.
    """
    compiled = compile_benchmark_package(
        PACKAGE_ROOT,
        split="test",
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    assert compiled.plan is not None
    contract = run_benchmark_contract_tests(
        compiled.plan,
        declaration_fixture_set(compiled.plan),
        seed=42,
    )
    dry_run = dry_run_benchmark(
        PACKAGE_ROOT,
        split="test",
        task_ids=("PhotoSmoke_1",),
    )
    assert contract.is_success
    assert contract.checked_components == 2
    assert dry_run.ok
    assert len(dry_run.schedule) == 1
    assert dry_run.schedule[0]["task_id"] == "PhotoSmoke_1"
