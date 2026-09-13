"""Coverage-aware Core Benchmark fake-fixture Contract Test contracts."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Mapping

import pytest
import yaml

from zhixing.benchmark import compile_benchmark_package
from zhixing.benchmark.authoring import (
    BenchmarkContractStatus,
    BenchmarkContractTestCapacityError,
    BenchmarkFixtureDescriptor,
    BenchmarkFixtureKind,
    BenchmarkFixtureProfile,
    BenchmarkFixtureProfileRegistry,
    discover_benchmark_contract_cases,
    run_benchmark_contract_tests,
)

from .helpers import task, write_package


def _fixture(value: Any):
    """Create a fresh constant fake fixture factory.

    Args:
        value: JSON-compatible fixture output.

    Returns:
        Factory producing fresh deterministic fixture callables.
    """
    def factory():
        """Create one fresh callable scope.

        Returns:
            Fresh deterministic fixture callable.
        """
        def runner(params: Mapping[str, Any], rng: random.Random) -> Any:
            """Return the configured safe value without external access.

            Args:
                params: Declared fixture parameters.
                rng: Case-local deterministic random source.

            Returns:
                Configured JSON-compatible value.
            """
            del params, rng
            return value

        return runner

    return factory


def _all_kind_plan(tmp_path: Path):
    """Compile one Plan containing every supported fixture occurrence kind.

    Args:
        tmp_path: Pytest Package destination root.

    Raises:
        AssertionError: Test Package does not compile.

    Returns:
        Compiled Benchmark Plan.
    """
    document = task("contract-all")
    document["task_initializer"] = {
        "target": {
            "name": "random_choice",
            "params": {"candidates": ["alpha", "beta"]},
        }
    }
    document["cleanup_initializer"] = [
        {"name": "cleanup_fixture", "params": {"label": "logical"}}
    ]
    package = write_package(tmp_path / "all-kinds", tasks=[document])
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["plugins"].extend(
        [
            {"id": "random_choice", "optional": False},
            {"id": "cleanup_fixture", "optional": False},
        ]
    )
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    result = compile_benchmark_package(package)
    assert result.plan is not None
    return result.plan


def _all_kind_profile() -> BenchmarkFixtureProfile:
    """Build a reviewed test profile covering all logical references.

    Returns:
        Immutable complete fake-fixture profile.
    """
    return BenchmarkFixtureProfile(
        profile_id="tests-all-kinds",
        version="1.0.0",
        title="All kinds",
        description="Deterministic in-process test fixtures.",
        evidence_level="fake-contract",
        fixtures=(
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.INITIALIZER,
                "random_choice",
                "tests.initializer",
                "1.0.0",
                _fixture({"value": "alpha"}),
            ),
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.ENVIRONMENT,
                "cleanup_fixture",
                "tests.cleanup",
                "1.0.0",
                _fixture({"cleaned": True}),
            ),
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.ENVIRONMENT,
                "push_file",
                "tests.environment",
                "1.0.0",
                _fixture({"prepared": True}),
            ),
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.EVALUATOR,
                "file_exist",
                "tests.evaluator",
                "1.0.0",
                _fixture(True),
            ),
        ),
    )


def test_all_contract_kinds_have_stable_cases_and_role_checks(tmp_path: Path) -> None:
    """Expose deterministic initializer/environment/evaluator case facts."""
    plan = _all_kind_plan(tmp_path)
    first = run_benchmark_contract_tests(plan, _all_kind_profile(), seed=41)
    second = run_benchmark_contract_tests(plan, _all_kind_profile(), seed=41)

    assert first.to_safe_dict() == second.to_safe_dict()
    assert first.coverage.total == 4
    assert first.coverage.passed == 4
    assert first.coverage.complete is True
    assert first.coverage.executed_checks_passed is True
    assert {item.kind for item in first.cases} == set(BenchmarkFixtureKind)
    environment_phases = {
        item.phase
        for item in first.cases
        if item.kind is BenchmarkFixtureKind.ENVIRONMENT
    }
    assert environment_phases == {"setup", "cleanup"}
    evaluator = next(
        item for item in first.cases if item.kind is BenchmarkFixtureKind.EVALUATOR
    )
    assert "evaluator_normalization" in evaluator.checks
    assert "determinism" in evaluator.checks
    assert all(item.status is BenchmarkContractStatus.PASSED for item in first.cases)


def test_missing_fixture_is_skipped_not_implicit_pass(tmp_path: Path) -> None:
    """Keep executed success independent from incomplete fixture coverage."""
    plan = _all_kind_plan(tmp_path)
    partial = BenchmarkFixtureProfile(
        profile_id="tests-partial",
        version="1.0.0",
        title="Partial",
        description="Only one reviewed fake.",
        evidence_level="fake-contract",
        fixtures=(_all_kind_profile().fixtures[0],),
    )
    report = run_benchmark_contract_tests(plan, partial)
    assert report.coverage.passed == 1
    assert report.coverage.skipped == 3
    assert report.coverage.failed == 0
    assert report.coverage.complete is False
    assert report.coverage.executed_checks_passed is True
    assert report.is_success is False


def test_fresh_scope_and_unsafe_evidence_fail_closed(tmp_path: Path) -> None:
    """Detect observable scope reuse and secret-shaped fixture evidence."""
    plan = _all_kind_plan(tmp_path)

    shared = _fixture({"ok": True})()
    leaking = BenchmarkFixtureDescriptor(
        BenchmarkFixtureKind.INITIALIZER,
        "random_choice",
        "tests.leaking",
        "1.0.0",
        lambda: shared,
    )
    unsafe = BenchmarkFixtureDescriptor(
        BenchmarkFixtureKind.ENVIRONMENT,
        "push_file",
        "tests.unsafe",
        "1.0.0",
        _fixture({"api_key": "must-not-serialize"}),
    )
    profile = BenchmarkFixtureProfile(
        profile_id="tests-failures",
        version="1.0.0",
        title="Failure fixtures",
        description="Controlled fixture contract failures.",
        evidence_level="fake-contract",
        fixtures=(leaking, unsafe),
    )
    report = run_benchmark_contract_tests(plan, profile)
    codes = {item.code for item in report.diagnostics}
    assert "benchmark.ctk.fixture_scope_not_isolated" in codes
    assert "benchmark.ctk.unsafe_evidence" in codes
    assert "must-not-serialize" not in str(report.to_safe_dict())


def test_case_seeds_do_not_depend_on_unrelated_traversal_order(tmp_path: Path) -> None:
    """Derive existing case seeds from identity instead of list position."""
    first = task("first-contract")
    first["task_initializer"] = {
        "target": {
            "name": "random_choice",
            "params": {"candidates": ["alpha", "beta"]},
        }
    }
    second = task("second-contract")
    package = write_package(tmp_path / "reordered-cases", tasks=[first, second])
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["plugins"].append({"id": "random_choice", "optional": False})
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    compiled = compile_benchmark_package(package)
    assert compiled.plan is not None
    plan = compiled.plan
    baseline = discover_benchmark_contract_cases(plan, seed=88)
    changed = plan.model_copy(update={"tasks": tuple(reversed(plan.tasks))})
    reordered = discover_benchmark_contract_cases(changed, seed=88)
    assert {item.case_id: item.seed for item in baseline} == {
        item.case_id: item.seed for item in reordered
    }


def test_environment_lifecycle_occurrences_keep_declaration_order(
    tmp_path: Path,
) -> None:
    """Keep setup before cleanup and use fresh deterministic scopes."""
    plan = _all_kind_plan(tmp_path)
    calls: list[tuple[str, int]] = []

    def recording_factory(label: str):
        """Create one lifecycle fixture factory that records invocation order.

        Args:
            label: Stable lifecycle fixture label.

        Returns:
            Factory producing a fresh recording runner.
        """
        def factory():
            """Create one fresh recording runner.

            Returns:
                Fresh lifecycle fake fixture.
            """
            def runner(
                params: Mapping[str, Any],
                rng: random.Random,
            ) -> dict[str, bool]:
                """Record one deterministic lifecycle invocation.

                Args:
                    params: Safe copied lifecycle parameters.
                    rng: Case-local deterministic random source.

                Returns:
                    Bounded lifecycle evidence.
                """
                del params
                calls.append((label, rng.randrange(1_000_000)))
                return {"ok": True}

            return runner

        return factory

    profile = BenchmarkFixtureProfile(
        profile_id="tests-lifecycle",
        version="1.0.0",
        title="Lifecycle",
        description="Stable lifecycle order fixture.",
        evidence_level="fake-contract",
        fixtures=(
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.ENVIRONMENT,
                "push_file",
                "tests.setup",
                "1.0.0",
                recording_factory("setup"),
            ),
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.ENVIRONMENT,
                "cleanup_fixture",
                "tests.cleanup",
                "1.0.0",
                recording_factory("cleanup"),
            ),
        ),
    )
    report = run_benchmark_contract_tests(plan, profile, seed=9)
    environment = [
        item for item in report.cases
        if item.kind is BenchmarkFixtureKind.ENVIRONMENT
    ]
    assert [(item.logical_name, item.phase) for item in environment] == [
        ("push_file", "setup"),
        ("cleanup_fixture", "cleanup"),
    ]
    assert [label for label, _ in calls] == [
        "setup", "setup", "cleanup", "cleanup"
    ]
    assert calls[0][1] == calls[1][1]
    assert calls[2][1] == calls[3][1]


def test_case_and_diagnostic_bounds_are_fail_closed(tmp_path: Path) -> None:
    """Cap public diagnostics and reject over-capacity before fixture calls."""
    many = [task(f"case-{index}") for index in range(51)]
    compiled = compile_benchmark_package(
        write_package(tmp_path / "diagnostics", tasks=many)
    )
    assert compiled.plan is not None
    empty = BenchmarkFixtureProfile(
        profile_id="tests-empty",
        version="1.0.0",
        title="Empty profile",
        description="No matching fixtures.",
        evidence_level="fake-contract",
        fixtures=(),
    )
    report = run_benchmark_contract_tests(compiled.plan, empty)
    assert len(report.cases) == 102
    assert len(report.diagnostics) == 100
    assert report.diagnostics_truncated is True

    oversized = [task(f"oversized-{index}") for index in range(501)]
    too_large = compile_benchmark_package(
        write_package(tmp_path / "too-large", tasks=oversized)
    )
    assert too_large.plan is not None
    invoked = False

    def forbidden_factory():
        """Fail if pre-execution cardinality protection is bypassed.

        Raises:
            AssertionError: Always.
        """
        nonlocal invoked
        invoked = True
        raise AssertionError("fixture must not be created")

    canary = BenchmarkFixtureProfile(
        profile_id="tests-canary",
        version="1.0.0",
        title="Canary",
        description="Capacity canary.",
        evidence_level="fake-contract",
        fixtures=(
            BenchmarkFixtureDescriptor(
                BenchmarkFixtureKind.ENVIRONMENT,
                "push_file",
                "tests.canary",
                "1.0.0",
                forbidden_factory,
            ),
        ),
    )
    with pytest.raises(BenchmarkContractTestCapacityError):
        run_benchmark_contract_tests(too_large.plan, canary)
    assert invoked is False


@pytest.mark.parametrize(
    "capability",
    (
        "device",
        "model",
        "network",
        "secret",
        "agent-execution",
        "experiment",
        "output-publication",
        "output-path",
        "real-runtime",
        "runtime-resolver",
    ),
)
def test_registry_rejects_forbidden_runtime_capabilities(capability: str) -> None:
    """Keep default fixture contexts free of runtime/external capabilities."""
    profile = BenchmarkFixtureProfile(
        profile_id="tests-forbidden",
        version="1.0.0",
        title="Forbidden",
        description="Capability rejection canary.",
        evidence_level="fake-contract",
        fixtures=(),
        capabilities=(capability,),
    )
    with pytest.raises(ValueError):
        BenchmarkFixtureProfileRegistry((profile,))


def test_registry_rejects_ambiguous_profile_versions() -> None:
    """Prevent one profile ID from resolving an arbitrary registered version."""
    first = BenchmarkFixtureProfile(
        profile_id="tests-versioned",
        version="1.0.0",
        title="First",
        description="First registered version.",
        evidence_level="fake-contract",
        fixtures=(),
    )
    second = BenchmarkFixtureProfile(
        profile_id="tests-versioned",
        version="2.0.0",
        title="Second",
        description="Conflicting registered version.",
        evidence_level="fake-contract",
        fixtures=(),
    )
    with pytest.raises(ValueError, match="one version"):
        BenchmarkFixtureProfileRegistry((first, second))
