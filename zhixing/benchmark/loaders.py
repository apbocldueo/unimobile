"""Safe JSON/YAML loaders for Benchmark Package and Protocol definitions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from zhixing.config.contracts import BenchmarkSuite, parse_benchmark_suite

from .constants import BENCHMARK_MANIFEST_NAME
from .diagnostics import (
    BenchmarkDefinitionError,
    BenchmarkDiagnostic,
    sorted_diagnostics,
)
from .models import BenchmarkPackageManifest, ExperimentProtocol
from .resources import resolve_package_path


def _validation_diagnostics(
    error: ValidationError,
    *,
    code: str,
    source: str,
) -> tuple[BenchmarkDiagnostic, ...]:
    """Convert Pydantic errors without echoing input values.

    Args:
        error (ValidationError): Pydantic validation failure.
        code (str): Stable diagnostic code.
        source (str): Safe logical source name.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Sanitized diagnostics.
    """
    return sorted_diagnostics(
        [
            BenchmarkDiagnostic(
                code=code,
                message=str(item["msg"])[:300],
                source=source,
                path=tuple(item["loc"]),
            )
            for item in error.errors(include_url=False, include_input=False)
        ]
    )


def load_mapping(path: Path) -> dict[str, Any]:
    """Load one JSON/YAML mapping with a side-effect-free safe parser.

    Args:
        path (Path): Definition file.

    Raises:
        BenchmarkDefinitionError: Format, I/O, syntax, or root type is invalid.

    Returns:
        dict[str, Any]: Parsed mapping.
    """
    suffix = path.suffix.lower()
    if suffix not in {".json", ".yaml", ".yml"}:
        raise BenchmarkDefinitionError(
            (
                BenchmarkDiagnostic(
                    code="benchmark.format.invalid",
                    message="Benchmark definition must be JSON or YAML.",
                    source=path.name,
                ),
            )
        )
    try:
        text = path.read_text(encoding="utf-8")
        value = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
    except (OSError, json.JSONDecodeError, yaml.YAMLError) as error:
        raise BenchmarkDefinitionError(
            (
                BenchmarkDiagnostic(
                    code="benchmark.definition.unreadable",
                    message="Benchmark definition cannot be read or parsed.",
                    source=path.name,
                    path=(type(error).__name__,),
                ),
            )
        ) from error
    if not isinstance(value, dict):
        raise BenchmarkDefinitionError(
            (
                BenchmarkDiagnostic(
                    code="benchmark.root.invalid",
                    message="Benchmark definition root must be an object.",
                    source=path.name,
                ),
            )
        )
    return value


def load_manifest(package_root: Path) -> BenchmarkPackageManifest:
    """Load and validate ``benchmark.yaml`` from one explicit Package root.

    Args:
        package_root (Path): Explicit Package directory.

    Raises:
        BenchmarkDefinitionError: Manifest is missing or violates the contract.

    Returns:
        BenchmarkPackageManifest: Strict normalized manifest.
    """
    manifest_path = package_root / BENCHMARK_MANIFEST_NAME
    if not manifest_path.is_file():
        raise BenchmarkDefinitionError(
            (
                BenchmarkDiagnostic(
                    code="benchmark.manifest.missing",
                    message="Package does not contain benchmark.yaml.",
                    source=BENCHMARK_MANIFEST_NAME,
                ),
            )
        )
    data = load_mapping(manifest_path)
    try:
        return BenchmarkPackageManifest.model_validate(data)
    except ValidationError as error:
        raise BenchmarkDefinitionError(
            _validation_diagnostics(
                error,
                code="benchmark.manifest.invalid",
                source=BENCHMARK_MANIFEST_NAME,
            )
        ) from error


def load_protocol(path: Path) -> ExperimentProtocol:
    """Load a strict ExperimentProtocol without consulting devices or Apps.

    Args:
        path (Path): JSON or YAML Protocol file.

    Raises:
        BenchmarkDefinitionError: Protocol is invalid.

    Returns:
        ExperimentProtocol: Normalized side-effect-free protocol.
    """
    data = load_mapping(path)
    try:
        return ExperimentProtocol.model_validate(data)
    except ValidationError as error:
        raise BenchmarkDefinitionError(
            _validation_diagnostics(
                error,
                code="benchmark.protocol.invalid",
                source=path.name,
            )
        ) from error


def load_package_suites(
    package_root: Path,
    manifest: BenchmarkPackageManifest,
) -> dict[str, BenchmarkSuite]:
    """Load all declared Package splits through the existing V1 task contract.

    Args:
        package_root (Path): Explicit Package root.
        manifest (BenchmarkPackageManifest): Validated manifest.

    Raises:
        BenchmarkDefinitionError: A task file is unsafe, invalid, or duplicated.

    Returns:
        dict[str, BenchmarkSuite]: Suites keyed by split name.
    """
    loaded: dict[str, BenchmarkSuite] = {}
    diagnostics: list[BenchmarkDiagnostic] = []
    for split_name, split in sorted(manifest.splits.items()):
        raw_tasks: list[Any] = []
        task_origins: list[tuple[str, int, str | None]] = []
        for file_index, relative_path in enumerate(split.files):
            try:
                task_path = resolve_package_path(package_root, relative_path)
            except ValueError:
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.task_file.path_invalid",
                        message="Task file must remain inside the Benchmark Package.",
                        source=BENCHMARK_MANIFEST_NAME,
                        path=("splits", split_name, "files", file_index),
                    )
                )
                continue
            try:
                value = json.loads(task_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.task_file.unreadable",
                        message="Declared task file cannot be read as JSON.",
                        source=relative_path,
                        path=(type(error).__name__,),
                    )
                )
                continue
            if not isinstance(value, list):
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.task_file.root_invalid",
                        message="Benchmark task file root must be an array.",
                        source=relative_path,
                    )
                )
                continue
            raw_tasks.extend(value)
            task_origins.extend(
                (
                    relative_path,
                    task_index,
                    (
                        str(raw_task.get("id"))
                        if isinstance(raw_task, dict)
                        and raw_task.get("id") is not None
                        else None
                    ),
                )
                for task_index, raw_task in enumerate(value)
            )
        if raw_tasks:
            first_task_ids: dict[str, tuple[str, int]] = {}
            duplicate_task_ids: list[BenchmarkDiagnostic] = []
            for origin_path, local_index, task_id in task_origins:
                if task_id is None:
                    continue
                if task_id in first_task_ids:
                    duplicate_task_ids.append(
                        BenchmarkDiagnostic(
                            code="benchmark.tasks.duplicate_id",
                            message=(
                                "Benchmark task ID is duplicated across the "
                                "selected split."
                            ),
                            source=origin_path,
                            path=(local_index, "id"),
                            task_id=task_id,
                        )
                    )
                else:
                    first_task_ids[task_id] = (origin_path, local_index)
            try:
                loaded[split_name] = parse_benchmark_suite(raw_tasks)
            except Exception as error:
                issues = getattr(error, "issues", ())
                if issues:
                    diagnostics.extend(duplicate_task_ids)
                    for issue in issues:
                        issue_path = tuple(issue.path)
                        if (
                            not issue_path
                            and duplicate_task_ids
                            and "duplicate task ids" in str(issue.message)
                        ):
                            continue
                        source = split_name
                        task_id = getattr(issue, "task_id", None)
                        if issue_path and isinstance(issue_path[0], int):
                            aggregate_index = issue_path[0]
                            if 0 <= aggregate_index < len(task_origins):
                                source, local_index, origin_task_id = task_origins[
                                    aggregate_index
                                ]
                                issue_path = (local_index, *issue_path[1:])
                                task_id = task_id or origin_task_id
                        diagnostics.append(
                            BenchmarkDiagnostic(
                                code=str(issue.code),
                                message=str(issue.message)[:300],
                                source=source,
                                path=issue_path,
                                task_id=task_id,
                            )
                        )
                else:
                    diagnostics.append(
                        BenchmarkDiagnostic(
                            code="benchmark.tasks.invalid",
                            message="Package tasks violate the BenchmarkTask V1 contract.",
                            source=split_name,
                            path=(type(error).__name__,),
                        )
                    )
    missing = sorted(set(manifest.splits) - set(loaded))
    for split_name in missing:
        diagnostics.append(
            BenchmarkDiagnostic(
                code="benchmark.split.empty",
                message="Declared split has no valid tasks.",
                source=split_name,
            )
        )
    if diagnostics:
        raise BenchmarkDefinitionError(sorted_diagnostics(diagnostics))
    return loaded
