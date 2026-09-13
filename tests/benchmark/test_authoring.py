"""Benchmark authoring, dry-run, Contract Test Kit, and CLI tests."""

from __future__ import annotations

import io
import json
import shutil
from pathlib import Path

import pytest
import yaml

from zhixing.benchmark import compile_benchmark_package
from zhixing.benchmark.authoring import (
    BenchmarkFixtureSet,
    declaration_fixture_set,
    dry_run_benchmark,
    run_benchmark_contract_tests,
    scaffold_benchmark_package,
)
from zhixing.cli import main

from .helpers import write_package

ROOT = Path(__file__).resolve().parents[2]
AGENT = ROOT / "examples/graphs/builtin_android_agent.yaml"


@pytest.mark.parametrize(
    "template",
    ("minimal", "dynamic-task", "composite-evaluation"),
)
def test_scaffold_templates_compile_without_runtime_access(
    tmp_path: Path,
    template: str,
) -> None:
    """Require every small template to compile as a Package definition."""
    package = scaffold_benchmark_package(
        tmp_path / template,
        name=f"{template}-example",
        template=template,
    )
    result = compile_benchmark_package(package)
    assert result.is_success
    assert result.plan is not None
    assert not (tmp_path / "temp").exists()


def test_scaffold_refuses_nonempty_destination_without_force(
    tmp_path: Path,
) -> None:
    """Protect unrelated developer files from implicit replacement."""
    destination = tmp_path / "existing"
    destination.mkdir()
    (destination / "owned.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError):
        scaffold_benchmark_package(destination, name="demo")
    assert (destination / "owned.txt").read_text(encoding="utf-8") == "keep"


def test_dry_run_compiles_agent_and_builds_schedule_only(
    tmp_path: Path,
) -> None:
    """Expose identities, budget, layout, and schedule without artifacts."""
    package = scaffold_benchmark_package(
        tmp_path / "dynamic",
        name="dynamic-example",
        template="dynamic-task",
    )
    report = dry_run_benchmark(
        package,
        agent_paths={"candidate": AGENT},
    )
    assert report.ok
    assert report.agent_graph_identities["candidate"].startswith("sha256:")
    assert report.schedule[0]["agent_id"] == "candidate"
    assert report.budget["max_interactions"] == 5
    assert "dynamic-task-materialization" in report.unverified_checks
    assert not (tmp_path / "benchmark-runs").exists()


def test_multi_file_task_provenance_and_plan_identity_are_stable(
    tmp_path: Path,
) -> None:
    """Localize second-file errors without making source layout semantic."""
    baseline = scaffold_benchmark_package(
        tmp_path / "baseline",
        name="provenance-example",
    )
    first_tasks = json.loads(
        (baseline / "tasks/test.json").read_text(encoding="utf-8")
    )
    second_task = dict(first_tasks[0])
    second_task["id"] = "second-task"
    (baseline / "tasks/test.json").write_text(
        json.dumps([*first_tasks, second_task]),
        encoding="utf-8",
    )
    baseline_result = compile_benchmark_package(baseline)
    assert baseline_result.plan is not None

    split = tmp_path / "split"
    shutil.copytree(baseline, split)
    (split / "tasks/test.json").write_text(
        json.dumps(first_tasks),
        encoding="utf-8",
    )
    (split / "tasks/second.json").write_text(
        json.dumps([second_task]),
        encoding="utf-8",
    )
    manifest_path = split / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["splits"]["test"]["files"] = [
        "tasks/test.json",
        "tasks/second.json",
    ]
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    split_result = compile_benchmark_package(split)
    assert split_result.plan is not None
    assert split_result.plan.canonical_hash() == (
        baseline_result.plan.canonical_hash()
    )

    second_task["max_steps"] = 0
    (split / "tasks/second.json").write_text(
        json.dumps([second_task]),
        encoding="utf-8",
    )
    invalid = compile_benchmark_package(split)
    diagnostic = next(
        item
        for item in invalid.diagnostics
        if item.code == "benchmark.structure.invalid"
    )
    assert diagnostic.source == "tasks/second.json"
    assert diagnostic.path == (0, "max_steps")
    assert diagnostic.task_id == "second-task"


def test_cross_file_duplicate_task_id_points_to_later_member(
    tmp_path: Path,
) -> None:
    """Address duplicate IDs at the concrete later task member."""
    package = scaffold_benchmark_package(
        tmp_path / "duplicate",
        name="duplicate-example",
    )
    task_path = package / "tasks/test.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))[0]
    second_path = package / "tasks/second.json"
    second_path.write_text(json.dumps([task]), encoding="utf-8")
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["splits"]["test"]["files"].append("tasks/second.json")
    manifest_path.write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    result = compile_benchmark_package(package)
    diagnostic = next(
        item
        for item in result.diagnostics
        if item.code == "benchmark.tasks.duplicate_id"
    )
    assert diagnostic.source == "tasks/second.json"
    assert diagnostic.path == (0, "id")
    assert diagnostic.task_id == "example-task"


def test_contract_test_uses_deterministic_explicit_fake_fixtures(
    tmp_path: Path,
) -> None:
    """Check task, evaluator, and environment contracts without a device."""
    package = write_package(tmp_path / "package")
    compiled = compile_benchmark_package(package)
    assert compiled.plan is not None
    fixtures = declaration_fixture_set(compiled.plan)
    first = run_benchmark_contract_tests(compiled.plan, fixtures, seed=7)
    second = run_benchmark_contract_tests(compiled.plan, fixtures, seed=7)
    assert first.is_success
    assert first.to_safe_dict() == second.to_safe_dict()
    assert first.checked_components == 2
    assert first.to_safe_dict()["real_device_evidence"] is False


def test_contract_test_rejects_missing_and_live_object_fixtures(
    tmp_path: Path,
) -> None:
    """Fail closed when fixture coverage or serializability is absent."""
    package = write_package(tmp_path / "package")
    compiled = compile_benchmark_package(package)
    assert compiled.plan is not None

    def live_fixture(params, rng):
        """Return an intentionally unsafe live object.

        Args:
            params: Ignored declaration parameters.
            rng: Ignored deterministic random source.

        Raises:
            None.

        Returns:
            object: Unsupported runtime object.
        """
        del params, rng
        return object()

    report = run_benchmark_contract_tests(
        compiled.plan,
        BenchmarkFixtureSet(
            environments={"push_file": live_fixture},
        ),
    )
    codes = {item.code for item in report.diagnostics}
    assert "benchmark.ctk.fixture_missing" in codes
    assert "benchmark.ctk.output_not_serializable" in codes


def test_authoring_cli_init_dry_run_and_contract_test(
    tmp_path: Path,
) -> None:
    """Keep installed command dispatch stable for the authoring loop."""
    package = tmp_path / "cli-package"
    stdout = io.StringIO()
    assert (
        main(
            [
                "benchmark",
                "init",
                str(package),
                "--name",
                "cli-example",
                "--template",
                "dynamic-task",
                "--json",
            ],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        == 0
    )
    assert json.loads(stdout.getvalue())["device_accessed"] is False

    stdout = io.StringIO()
    assert (
        main(
            [
                "benchmark",
                "dry-run",
                str(package),
                "--agent",
                f"candidate={AGENT}",
                "--json",
            ],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        == 0
    )
    assert json.loads(stdout.getvalue())["mode"] == "side-effect-free-dry-run"

    stdout = io.StringIO()
    assert (
        main(
            [
                "benchmark",
                "contract-test",
                str(package),
                "--json",
            ],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        == 0
    )
    contract_payload = json.loads(stdout.getvalue())
    assert contract_payload["mode"] == "fake-fixture"
    assert contract_payload["profile"]["evidence_level"] == "declaration-only"
    assert contract_payload["safety"]["package_code_executed"] is False


def test_report_and_trajectory_cli_reject_unsupported_documents(
    tmp_path: Path,
) -> None:
    """Return stable non-runtime errors for unsupported artifact schemas."""
    document = tmp_path / "unsupported.json"
    document.write_text(
        json.dumps({"schema_version": "99", "kind": "future"}),
        encoding="utf-8",
    )
    for command in ("report", "trajectory"):
        stdout = io.StringIO()
        code = main(
            ["benchmark", command, str(document), "--json"],
            stdout=stdout,
            stderr=io.StringIO(),
        )
        assert code == 2
        assert json.loads(stdout.getvalue())["error"]["code"] == (
            "benchmark.authoring.invalid"
        )
