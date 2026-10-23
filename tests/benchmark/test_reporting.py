"""Benchmark report, metrics, trajectory, and durable writer tests."""

from __future__ import annotations

import json
import shutil
import zipfile
from pathlib import Path

import pytest

from zhixing.benchmark import (
    BenchmarkOutcome,
    BenchmarkStageResult,
    BenchmarkStageStatus,
    BenchmarkSuiteResult,
    BenchmarkTaskResult,
)
from zhixing.benchmark.reporting import (
    build_agent_comparisons,
    build_agent_metrics,
    build_experiment_report,
    build_task_trajectory,
    load_experiment_report,
    load_run_report,
    sanitize_export,
    verify_trajectory_bundle,
    write_experiment_artifacts,
)
from zhixing.benchmark.reporting.writer import _create_bundle, _member_path

_HASH_A = "sha256:" + "1" * 64
_HASH_B = "sha256:" + "2" * 64
_HASH_PLAN = "sha256:" + "3" * 64
_HASH_PROTOCOL = "sha256:" + "4" * 64
_HASH_INSTANCE = "sha256:" + "5" * 64


class _LiveObjectCanary:
    """Represent a runtime-only object whose repr must never be exported."""

    def __repr__(self) -> str:
        """Return a deliberately sensitive representation for safety tests.

        Returns:
            str: Canary text that must not appear in durable output.
        """
        return "LiveObject(sk-live-acceptance-canary)"


def _task_result(
    *,
    run_id: str,
    task_id: str,
    agent_id: str,
    outcome: BenchmarkOutcome,
    repeat: int = 0,
    instance_identity: str = _HASH_INSTANCE,
    duration_ms: float = 10.0,
    usage: dict | None = None,
) -> BenchmarkTaskResult:
    """Build one deterministic reporting fixture.

    Args:
        run_id (str): Task-run identity.
        task_id (str): Benchmark task identity.
        agent_id (str): Candidate Agent identity.
        outcome (BenchmarkOutcome): Final Benchmark outcome.
        repeat (int): Repeat index.
        instance_identity (str): TaskInstance canonical identity.
        duration_ms (float): Observable stage duration.
        usage (dict | None): Optional normalized usage.

    Raises:
        None.

    Returns:
        BenchmarkTaskResult: Reporting fixture.
    """
    return BenchmarkTaskResult(
        experiment_id="experiment-reporting",
        task_run_id=run_id,
        task_id=task_id,
        repeat=repeat,
        agent_id=agent_id,
        agent_graph_identity=_HASH_A if agent_id == "a" else _HASH_B,
        benchmark_plan_identity=_HASH_PLAN,
        experiment_protocol_identity=_HASH_PROTOCOL,
        task_instance_identity=instance_identity,
        outcome=outcome,
        stages=(
            BenchmarkStageResult(
                phase="agent",
                status=BenchmarkStageStatus.SUCCESS,
                duration_ms=duration_ms,
                evidence={
                    "nested": {
                        "device_id": "emulator-5554",
                        "api_key": "sk-live-acceptance-canary",
                        "path": "/Users/example/private/file.txt",
                    }
                },
            ),
            BenchmarkStageResult(
                phase="evaluation",
                status=BenchmarkStageStatus.SUCCESS,
                duration_ms=1.0,
            ),
        ),
        usage=usage or {},
        artifact_namespace=run_id,
    )


def _suite(results: tuple[BenchmarkTaskResult, ...]) -> BenchmarkSuiteResult:
    """Build one deterministic suite result.

    Args:
        results (tuple[BenchmarkTaskResult, ...]): Ordered task results.

    Raises:
        None.

    Returns:
        BenchmarkSuiteResult: Suite fixture.
    """
    return BenchmarkSuiteResult(
        experiment_id="experiment-reporting",
        benchmark_plan_identity=_HASH_PLAN,
        experiment_protocol_identity=_HASH_PROTOCOL,
        results=results,
        device_provenance={"device_id": "emulator-5554"},
    )


def test_metrics_keep_invalid_and_skipped_out_of_success_denominator() -> None:
    """Expose all counts while computing success only over PASS and FAIL."""
    results = (
        _task_result(
            run_id="a-pass",
            task_id="t1",
            agent_id="a",
            outcome=BenchmarkOutcome.PASS,
            usage={"total_tokens": 3},
        ),
        _task_result(
            run_id="a-fail",
            task_id="t2",
            agent_id="a",
            outcome=BenchmarkOutcome.FAIL,
            duration_ms=20.0,
        ),
        _task_result(
            run_id="a-invalid",
            task_id="t3",
            agent_id="a",
            outcome=BenchmarkOutcome.INVALID,
        ),
        _task_result(
            run_id="a-skipped",
            task_id="t4",
            agent_id="a",
            outcome=BenchmarkOutcome.SKIPPED,
        ),
    )
    metrics = build_agent_metrics(results)[0]
    assert metrics.counts == {
        "pass": 1,
        "fail": 1,
        "invalid": 1,
        "skipped": 1,
    }
    assert metrics.eligible_count == 2
    assert metrics.success_rate_micro == 0.5
    assert metrics.duration_sample_variance is not None
    assert metrics.usage_available_runs == 1


def test_single_duration_variance_is_unavailable() -> None:
    """Avoid presenting a fabricated zero variance for one observation."""
    metrics = build_agent_metrics(
        (
            _task_result(
                run_id="only",
                task_id="t1",
                agent_id="a",
                outcome=BenchmarkOutcome.PASS,
            ),
        )
    )[0]
    assert metrics.duration_sample_variance is None


def test_comparison_requires_matching_task_instance() -> None:
    """Label only genuinely shared TaskInstances as paired."""
    paired = build_agent_comparisons(
        (
            _task_result(
                run_id="a",
                task_id="t1",
                agent_id="a",
                outcome=BenchmarkOutcome.PASS,
            ),
            _task_result(
                run_id="b",
                task_id="t1",
                agent_id="b",
                outcome=BenchmarkOutcome.FAIL,
            ),
        )
    )[0]
    assert paired.paired is True
    assert paired.left_wins == 1
    assert paired.significance_claimed is False

    unpaired = build_agent_comparisons(
        (
            _task_result(
                run_id="a2",
                task_id="t1",
                agent_id="a",
                outcome=BenchmarkOutcome.PASS,
                instance_identity="sha256:" + "6" * 64,
            ),
            _task_result(
                run_id="b2",
                task_id="t1",
                agent_id="b",
                outcome=BenchmarkOutcome.FAIL,
                instance_identity="sha256:" + "7" * 64,
            ),
        )
    )[0]
    assert unpaired.paired is False
    assert unpaired.matched_count == 0


def test_reports_write_reload_and_verify_bundle(tmp_path: Path) -> None:
    """Persist loadable reports and an integrity-checked trajectory bundle."""
    suite = _suite(
        (
            _task_result(
                run_id="a-pass",
                task_id="t1",
                agent_id="a",
                outcome=BenchmarkOutcome.PASS,
            ),
            _task_result(
                run_id="b-fail",
                task_id="t1",
                agent_id="b",
                outcome=BenchmarkOutcome.FAIL,
            ),
        )
    )
    artifacts = write_experiment_artifacts(suite, artifact_root=tmp_path)
    root = artifacts.experiment_root
    report = load_experiment_report(root / "experiment-report.json")
    run_report = load_run_report(root / "runs/a-pass/run-report.json")
    assert report.counts["pass"] == 1
    assert report.comparisons[0].paired is True
    assert run_report.outcome == "pass"
    assert verify_trajectory_bundle(root / artifacts.bundle_ref) is True
    durable_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in root.rglob("*")
        if path.is_file() and path.suffix in {".json", ".jsonl"}
    )
    with zipfile.ZipFile(root / artifacts.bundle_ref, mode="r") as archive:
        bundle_text = "\n".join(
            archive.read(name).decode("utf-8")
            for name in archive.namelist()
            if name.endswith((".json", ".jsonl"))
        )
    for forbidden in (
        "emulator-5554",
        "sk-live-acceptance-canary",
        "/Users/example/private/file.txt",
    ):
        assert forbidden not in durable_text
        assert forbidden not in bundle_text


def test_bundle_verification_detects_modified_member(tmp_path: Path) -> None:
    """Reject a bundle whose declared trajectory member was altered."""
    suite = _suite(
        (
            _task_result(
                run_id="a-pass",
                task_id="t1",
                agent_id="a",
                outcome=BenchmarkOutcome.PASS,
            ),
        )
    )
    artifacts = write_experiment_artifacts(suite, artifact_root=tmp_path)
    bundle = artifacts.experiment_root / artifacts.bundle_ref
    replacement = tmp_path / "tampered.zip"
    with (
        zipfile.ZipFile(bundle, mode="r") as source,
        zipfile.ZipFile(replacement, mode="w") as target,
    ):
        for name in source.namelist():
            content = source.read(name)
            if name == "runs/a-pass/trajectory.jsonl":
                content = b"tampered\n"
            target.writestr(name, content)
    shutil.copyfile(replacement, bundle)
    assert verify_trajectory_bundle(bundle) is False


def test_bundle_rejects_traversal_and_symlink_members(tmp_path: Path) -> None:
    """Reject members that escape the experiment or resolve through symlinks."""
    with pytest.raises(ValueError, match="relative"):
        _member_path(tmp_path, "../escape.json")
    regular = tmp_path / "regular.json"
    regular.write_text("{}\n", encoding="utf-8")
    link = tmp_path / "link.json"
    link.symlink_to(regular)
    with pytest.raises(ValueError, match="non-symlink"):
        _create_bundle(
            tmp_path,
            {"link.json": "sha256:" + "0" * 64},
        )

    malicious = tmp_path / "malicious.zip"
    with zipfile.ZipFile(malicious, mode="w") as archive:
        archive.writestr("../escape.json", b"{}\n")
        archive.writestr(
            "bundle-manifest.json",
            json.dumps(
                {
                    "schema_version": "1.0",
                    "kind": "benchmark_trajectory_bundle",
                    "members": {"../escape.json": "sha256:" + "0" * 64},
                }
            ),
        )
    with pytest.raises(ValueError, match="unsafe"):
        verify_trajectory_bundle(malicious)


def test_safe_export_reports_nested_redaction_actions() -> None:
    """Hash raw device IDs and redact secrets and host paths recursively."""
    safe, diagnostics = sanitize_export(
        {
            "action_results": [
                {
                    "device_id": "emulator-5554",
                    "token": "do-not-export",
                    "path": "/Users/example/private/file.txt",
                }
            ],
            "usage": {"total_tokens": 12, "token_limit": 100},
            "runtime": _LiveObjectCanary(),
        }
    )
    nested = safe["action_results"][0]
    assert nested["device_id"].startswith("device-sha256:")
    assert nested["token"] == "<redacted>"
    assert nested["path"] == "<host-path>"
    assert safe["usage"] == {"total_tokens": 12, "token_limit": 100}
    assert safe["runtime"] == "<_LiveObjectCanary>"
    assert "sk-live-acceptance-canary" not in json.dumps(safe)
    assert {item.action for item in diagnostics} >= {
        "hashed",
        "redacted",
        "rejected",
    }


def test_trajectory_keeps_phase_order_for_manual_localization() -> None:
    """Represent Agent success and evaluation failure as separate phases."""
    result = _task_result(
        run_id="controlled-fail",
        task_id="t1",
        agent_id="a",
        outcome=BenchmarkOutcome.FAIL,
    )
    records = build_task_trajectory(result)
    assert [record["phase"] for record in records] == ["agent", "evaluation"]
    assert records[0]["stage"]["status"] == "success"
    assert records[1]["stage"]["status"] == "success"
    report = build_experiment_report(_suite((result,)))
    assert report.counts["fail"] == 1


def test_unknown_report_schema_is_rejected(tmp_path: Path) -> None:
    """Fail explicitly instead of silently dropping future report fields."""
    path = tmp_path / "future.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "999.0",
                "kind": "benchmark_experiment_report",
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported"):
        load_experiment_report(path)
