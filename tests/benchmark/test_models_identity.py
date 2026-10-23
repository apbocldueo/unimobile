"""Contract, identity, and resource-boundary tests."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from zhixing.benchmark import (
    BenchmarkPackageManifest,
    BenchmarkPlan,
    DeviceConstraints,
    ExperimentProtocol,
    TaskInstance,
    canonical_hash,
    canonical_primitive,
    compile_benchmark_package,
    compile_benchmark_suite,
    load_protocol,
)
from zhixing.benchmark.resources import resolve_package_path
from zhixing.agents import build_builtin_mobile_agent_graph

from .helpers import task, write_package


def test_manifest_is_typed_immutable_and_rejects_unknown_or_secret_fields() -> None:
    """Accept declarative fields but reject arbitrary core and secret fields."""
    manifest = BenchmarkPackageManifest.model_validate(
        {
            "schema_version": "1.0",
            "identity": {
                "publisher": "tests",
                "name": "demo",
                "version": "1.0.0",
            },
            "title": "Demo",
            "platforms": ["android"],
            "splits": {"test": {"files": ["tasks/test.json"]}},
        }
    )
    assert manifest.identity.identifier == "tests/demo@1.0.0"
    with pytest.raises(ValidationError):
        BenchmarkPackageManifest.model_validate(
            {
                **manifest.model_dump(mode="json"),
                "api_key": "do-not-store",
            }
        )
    with pytest.raises(ValidationError):
        manifest.title = "changed"  # type: ignore[misc]


def test_canonical_json_is_stable_across_processes() -> None:
    """Fix canonicalization output across independent Python processes."""
    payload = {"z": [3, 2, 1], "a": {"é": 1, "zero": -0.0}}
    local = canonical_hash(payload)
    script = (
        "from zhixing.benchmark import canonical_hash;"
        f"print(canonical_hash({payload!r}))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == local
    assert local == "sha256:9d835b8b6d1f90e0d964e8b5e35954cc098867f24910dd70952429eaa78b9042"


def test_canonical_projection_rejects_sensitive_and_runtime_values() -> None:
    """Prevent secrets, device bindings, paths, and live objects from identity."""
    for value in (
        {"api_key": "secret"},
        {"device_serial": "emulator-5554"},
        {"artifact_root": "/tmp/run"},
        Path("/tmp/run"),
        object(),
    ):
        with pytest.raises(ValueError):
            canonical_primitive(value)


def test_canonical_projection_accepts_only_strict_secret_ref_placeholders() -> None:
    """Hash a SecretRef identity while still rejecting values and malformed refs."""
    assert canonical_primitive(
        {"api_key": {"secret_ref": "openai_api_key"}}
    ) == {"api_key": {"secret_ref": "openai_api_key"}}
    for value in (
        {"api_key": {"secret_ref": ""}},
        {"api_key": {"secret_ref": "safe", "value": "not-safe"}},
        {"device_serial": {"secret_ref": "device_ref"}},
    ):
        with pytest.raises(ValueError):
            canonical_primitive(value)


def test_package_relocation_and_task_order_do_not_change_plan_identity(
    tmp_path: Path,
) -> None:
    """Keep Package source location and task declaration order non-semantic."""
    first = write_package(
        tmp_path / "first",
        tasks=[task("b"), task("a")],
    )
    second = tmp_path / "second"
    shutil.copytree(first, second)
    task_path = second / "tasks" / "test.json"
    reversed_tasks = list(reversed(json.loads(task_path.read_text(encoding="utf-8"))))
    task_path.write_text(json.dumps(reversed_tasks), encoding="utf-8")
    result_a = compile_benchmark_package(first)
    result_b = compile_benchmark_package(second)
    assert result_a.is_success and result_b.is_success
    assert result_a.plan is not None and result_b.plan is not None
    assert result_a.plan.canonical_hash() == result_b.plan.canonical_hash()
    (second / "README.md").write_text("presentation only", encoding="utf-8")
    result_c = compile_benchmark_package(second)
    assert result_c.plan is not None
    assert result_c.plan.canonical_hash() == result_a.plan.canonical_hash()


def test_semantic_changes_update_only_the_correct_identity(tmp_path: Path) -> None:
    """Separate AgentGraph, Plan, TaskInstance, and Protocol identities."""
    package = write_package(tmp_path / "package")
    result = compile_benchmark_package(package)
    assert result.plan is not None
    plan_hash = result.plan.canonical_hash()
    changed_tasks = tuple(
        item.model_copy(update={"instruction": "Changed instruction"})
        for item in result.plan.tasks
    )
    changed_plan = result.plan.model_copy(update={"tasks": changed_tasks})
    assert changed_plan.canonical_hash() != plan_hash

    protocol = ExperimentProtocol()
    changed_protocol = protocol.model_copy(
        update={
            "budget": protocol.budget.model_copy(
                update={"max_interactions": 16}
            )
        }
    )
    assert changed_protocol.canonical_hash() != protocol.canonical_hash()
    assert result.plan.canonical_hash() == plan_hash

    instance = TaskInstance(
        plan_identity=plan_hash,
        task_id="demo-1",
        repeat=0,
        seed=1,
        generated_params={"name": "one"},
        instruction="Create one",
        ground_truth={"name": "one"},
    )
    changed_instance = instance.model_copy(
        update={"instruction": "Create two"}
    )
    assert instance.canonical_hash() != changed_instance.canonical_hash()

    graph = build_builtin_mobile_agent_graph()
    graph_hash = graph.canonical_hash()
    assert ExperimentProtocol(seed=99).canonical_hash() != protocol.canonical_hash()
    assert graph.canonical_hash() == graph_hash


def test_protocol_rejects_concrete_device_and_derives_deterministic_order() -> None:
    """Keep actual serial out of Protocol and seeded ordering reproducible."""
    with pytest.raises(ValidationError):
        DeviceConstraints.model_validate(
            {"platform": "android", "device_serial": "emulator-5554"}
        )
    protocol = ExperimentProtocol.model_validate(
        {
            "task_order": {"strategy": "seeded"},
            "seed": 12,
        }
    )
    plan_identity = "sha256:" + "1" * 64
    first = protocol.ordered_task_ids(
        ["c", "a", "b"],
        plan_identity=plan_identity,
        repeat=0,
    )
    second = protocol.ordered_task_ids(
        ["b", "c", "a"],
        plan_identity=plan_identity,
        repeat=0,
    )
    assert first == second
    assert set(first) == {"a", "b", "c"}


def test_protocol_reports_unpaired_materialization() -> None:
    """Make departures from paired fairness explicit."""
    protocol = ExperimentProtocol.model_validate(
        {"task_materialization": {"reuse_across_agents": False}}
    )
    assert protocol.fairness_warnings == (
        "benchmark.protocol.unpaired_materialization",
    )


def test_default_protocol_is_independent_of_adb_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Load identical Protocol semantics with or without Android environment hints."""
    path = Path("examples/benchmarks/default_protocol.yaml")
    monkeypatch.setenv("ANDROID_SERIAL", "emulator-5554")
    with_device_hint = load_protocol(path)
    monkeypatch.delenv("ANDROID_SERIAL")
    without_device_hint = load_protocol(path)
    assert with_device_hint.canonical_hash() == without_device_hint.canonical_hash()


def test_failure_policy_keeps_stage_outcomes_independent() -> None:
    """Preserve initializer, Agent, evaluator, and cleanup failure semantics."""
    protocol = ExperimentProtocol()
    assert protocol.failure.initializer.outcome.value == "invalidate"
    assert protocol.failure.agent.outcome.value == "evaluate_if_possible"
    assert protocol.failure.evaluator.preserve_evidence is True
    assert protocol.failure.cleanup.preserve_evidence is True


def test_resource_path_rejects_absolute_traversal_and_symlink_escape(
    tmp_path: Path,
) -> None:
    """Confine Package resources even when a symlink points outside."""
    root = tmp_path / "package"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    (root / "link.txt").symlink_to(outside)
    for value in ("/tmp/x", "../outside.txt", "link.txt"):
        with pytest.raises(ValueError):
            resolve_package_path(root, value)


def test_standalone_json_compiles_without_a_package() -> None:
    """Preserve existing BenchmarkSuite JSON as a first-class source."""
    result = compile_benchmark_suite("examples/benchmark_v1/app_agent.json")
    assert result.is_success
    assert result.plan is not None
    assert result.plan.package_identity is None
    assert len(result.plan.tasks) == 45


def test_benchmark_plan_rejects_live_values() -> None:
    """Reject runtime objects before they can enter a serializable Plan."""
    result = compile_benchmark_suite("examples/benchmark_v1/app_agent.json")
    assert result.plan is not None
    dumped = result.plan.model_dump(mode="python")
    dumped["resources"] = [object()]
    with pytest.raises(ValidationError):
        BenchmarkPlan.model_validate(dumped)


def test_plan_and_task_instance_round_trip_across_processes() -> None:
    """Keep DTO serialization and TaskInstance identity portable."""
    result = compile_benchmark_suite("examples/benchmark_v1/app_agent.json")
    assert result.plan is not None
    plan_dump = result.plan.model_dump(mode="json", exclude_none=True)
    restored_plan = BenchmarkPlan.model_validate(plan_dump)
    assert restored_plan.canonical_hash() == result.plan.canonical_hash()

    instance = TaskInstance(
        plan_identity=result.plan.canonical_hash(),
        task_id="AppAgent_1",
        repeat=0,
        seed=42,
        generated_params={"query": "museum"},
        instruction="Search for museum",
        ground_truth={"query": "museum"},
    )
    instance_dump = instance.model_dump(mode="json", exclude_none=True)
    restored_instance = TaskInstance.model_validate(instance_dump)
    assert restored_instance.canonical_hash() == instance.canonical_hash()
    script = (
        "import json;"
        "from zhixing.benchmark import TaskInstance;"
        f"value=json.loads({json.dumps(json.dumps(instance_dump))});"
        "print(TaskInstance.model_validate(value).canonical_hash())"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == instance.canonical_hash()
