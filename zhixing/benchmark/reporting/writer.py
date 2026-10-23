"""Atomic report, trajectory, and integrity-checked bundle writer."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import zipfile
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..runtime.models import BenchmarkSuiteResult
from .report import (
    BenchmarkExperimentReport,
    BenchmarkRunReport,
    build_experiment_report,
    build_run_report,
)
from .safety import safe_export
from .trajectory import build_task_trajectory

RESULT_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ExperimentArtifacts:
    """Safe relative references produced for one experiment."""

    experiment_root: Path
    report_ref: str
    bundle_ref: str
    member_hashes: Mapping[str, str]


def _json_bytes(value: Any) -> bytes:
    """Encode one safe value deterministically.

    Args:
        value (Any): JSON-compatible value.

    Raises:
        TypeError: Value is not JSON compatible.

    Returns:
        bytes: UTF-8 deterministic JSON bytes.
    """
    return (
        json.dumps(
            safe_export(value),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_write(target: Path, content: bytes) -> None:
    """Atomically write a file inside its prepared parent directory.

    Args:
        target (Path): Destination path.
        content (bytes): Complete file bytes.

    Raises:
        OSError: The write or replacement fails.

    Returns:
        None.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _member_path(root: Path, reference: str) -> Path:
    """Resolve one safe relative output member.

    Args:
        root (Path): Experiment output root.
        reference (str): POSIX relative reference.

    Raises:
        ValueError: Reference is absolute, traversing, or escaping.

    Returns:
        Path: Host target within root.
    """
    pure = PurePosixPath(reference)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError("artifact reference must be relative and non-traversing")
    target = root.joinpath(*pure.parts)
    resolved_root = root.resolve()
    resolved_target = target.resolve(strict=False)
    if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
        raise ValueError("artifact reference escapes experiment root")
    return target


def _sha256(content: bytes) -> str:
    """Return a prefixed SHA-256 digest.

    Args:
        content (bytes): File content.

    Raises:
        None.

    Returns:
        str: Prefixed digest.
    """
    return "sha256:" + hashlib.sha256(content).hexdigest()


def load_json_document(path: Path) -> dict[str, Any]:
    """Load one versioned result or report document without runtime access.

    Args:
        path (Path): JSON document path.

    Raises:
        ValueError: Root or schema version is unsupported.
        OSError: File cannot be read.

    Returns:
        dict[str, Any]: Decoded document.
    """
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Benchmark document root must be an object")
    if value.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise ValueError("unsupported Benchmark document schema")
    return value


def load_run_report(path: Path) -> BenchmarkRunReport:
    """Load one durable run report.

    Args:
        path (Path): Run report path.

    Raises:
        ValueError: Schema or report fields are invalid.
        OSError: File cannot be read.

    Returns:
        BenchmarkRunReport: Typed report.
    """
    return BenchmarkRunReport.from_dict(load_json_document(path))


def load_experiment_report(path: Path) -> BenchmarkExperimentReport:
    """Load one durable experiment report.

    Args:
        path (Path): Experiment report path.

    Raises:
        ValueError: Schema or report fields are invalid.
        OSError: File cannot be read.

    Returns:
        BenchmarkExperimentReport: Typed report.
    """
    return BenchmarkExperimentReport.from_dict(load_json_document(path))


def _create_bundle(
    experiment_root: Path,
    member_hashes: Mapping[str, str],
) -> str:
    """Create a ZIP containing only declared regular safe members.

    Args:
        experiment_root (Path): Experiment output directory.
        member_hashes (Mapping[str, str]): Relative members and expected hashes.

    Raises:
        ValueError: A member is unsafe or a symlink.
        OSError: Bundle creation fails.

    Returns:
        str: Relative bundle reference.
    """
    reference = "trajectory-bundle.zip"
    target = _member_path(experiment_root, reference)
    temporary = target.with_suffix(".zip.tmp")
    with zipfile.ZipFile(
        temporary,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as archive:
        for member in sorted(member_hashes):
            path = _member_path(experiment_root, member)
            if path.is_symlink() or not path.is_file():
                raise ValueError("bundle member must be a regular non-symlink file")
            archive.write(path, arcname=member)
        archive.writestr(
            "bundle-manifest.json",
            _json_bytes(
                {
                    "schema_version": RESULT_SCHEMA_VERSION,
                    "kind": "benchmark_trajectory_bundle",
                    "members": dict(sorted(member_hashes.items())),
                }
            ),
        )
    os.replace(temporary, target)
    return reference


def verify_trajectory_bundle(path: Path) -> bool:
    """Verify declared member paths and SHA-256 hashes in a trajectory bundle.

    Args:
        path (Path): Bundle path.

    Raises:
        ValueError: Manifest or a member path is unsafe.
        OSError: Bundle cannot be read.

    Returns:
        bool: True only when every member is declared and unchanged.
    """
    with zipfile.ZipFile(path, mode="r") as archive:
        names = archive.namelist()
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts:
                raise ValueError("bundle contains unsafe member path")
        manifest = json.loads(archive.read("bundle-manifest.json"))
        members = manifest.get("members")
        if not isinstance(members, dict):
            raise ValueError("bundle manifest members must be an object")
        declared = set(members) | {"bundle-manifest.json"}
        if set(names) != declared:
            return False
        for name, expected in members.items():
            if _sha256(archive.read(name)) != expected:
                return False
    return True


def write_experiment_artifacts(
    result: BenchmarkSuiteResult,
    *,
    artifact_root: Path,
) -> ExperimentArtifacts:
    """Write result facts, reports, trajectories, manifest, and bundle.

    Args:
        result (BenchmarkSuiteResult): Immutable suite facts.
        artifact_root (Path): Runtime-only output root.

    Raises:
        OSError: Output cannot be created.
        ValueError: A member path or artifact is unsafe.

    Returns:
        ExperimentArtifacts: Runtime path plus safe relative references.
    """
    experiment_root = Path(artifact_root) / result.experiment_id
    experiment_root.mkdir(parents=True, exist_ok=True)
    member_hashes: dict[str, str] = {}

    def write_member(reference: str, value: Any, *, jsonl: bool = False) -> None:
        """Write one tracked experiment member.

        Args:
            reference (str): Safe experiment-relative path.
            value (Any): JSON document or JSONL record iterable.
            jsonl (bool): Whether value contains multiple line records.

        Raises:
            OSError: Atomic write fails.
            ValueError: Reference is unsafe.

        Returns:
            None.
        """
        if jsonl:
            content = b"".join(
                (
                    json.dumps(
                        safe_export(item),
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                    + "\n"
                ).encode("utf-8")
                for item in value
            )
        else:
            content = _json_bytes(value)
        _atomic_write(_member_path(experiment_root, reference), content)
        member_hashes[reference] = _sha256(content)

    for task_result in result.results:
        prefix = f"runs/{task_result.task_run_id}"
        write_member(
            f"{prefix}/benchmark-result.json",
            {
                "schema_version": RESULT_SCHEMA_VERSION,
                "kind": "benchmark_task_result",
                "result": task_result.to_safe_dict(),
            },
        )
        write_member(
            f"{prefix}/run-report.json",
            build_run_report(task_result).to_safe_dict(),
        )
        write_member(
            f"{prefix}/trajectory.jsonl",
            build_task_trajectory(task_result),
            jsonl=True,
        )
    experiment_report = build_experiment_report(result)
    write_member("experiment-report.json", experiment_report.to_safe_dict())
    suite_document = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "kind": "benchmark_suite_result",
        "result": result.to_safe_dict(),
    }
    write_member("experiment-result.json", suite_document)
    manifest = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "kind": "benchmark_experiment_manifest",
        "experiment_id": result.experiment_id,
        "members": dict(sorted(member_hashes.items())),
    }
    _atomic_write(
        _member_path(experiment_root, "experiment-manifest.json"),
        _json_bytes(manifest),
    )
    bundle_ref = _create_bundle(experiment_root, member_hashes)
    return ExperimentArtifacts(
        experiment_root=experiment_root,
        report_ref="experiment-report.json",
        bundle_ref=bundle_ref,
        member_hashes=dict(member_hashes),
    )


def finalize_suite_result(
    result: BenchmarkSuiteResult,
    *,
    artifact_root: Path,
) -> BenchmarkSuiteResult:
    """Attach safe artifact references or an independent reporting failure.

    Args:
        result (BenchmarkSuiteResult): Completed immutable suite facts.
        artifact_root (Path): Runtime-only output root.

    Raises:
        None: Writer failures are represented on the returned result.

    Returns:
        BenchmarkSuiteResult: Facts plus reporting status and safe references.
    """
    try:
        artifacts = write_experiment_artifacts(
            result,
            artifact_root=artifact_root,
        )
    except Exception as error:
        return replace(
            result,
            reporting_error_code=(
                f"benchmark.reporting.failed.{type(error).__name__}"
            ),
        )
    return replace(
        result,
        artifact_refs=(artifacts.report_ref, artifacts.bundle_ref),
    )


__all__ = [
    "ExperimentArtifacts",
    "RESULT_SCHEMA_VERSION",
    "finalize_suite_result",
    "load_experiment_report",
    "load_json_document",
    "load_run_report",
    "verify_trajectory_bundle",
    "write_experiment_artifacts",
]
