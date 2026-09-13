"""Safe Package-relative resource resolution and logical URI validation."""

from __future__ import annotations

import hashlib
import mimetypes
from pathlib import Path, PurePosixPath
from typing import Any

from .diagnostics import BenchmarkDiagnostic
from .models import ResourceKind, ResourceRef


def file_sha256(path: Path) -> str:
    """Compute a streaming SHA-256 digest for a local resource.

    Args:
        path (Path): Existing regular file.

    Raises:
        OSError: File cannot be read.

    Returns:
        str: ``sha256:``-prefixed digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return f"sha256:{digest.hexdigest()}"


def resolve_package_path(root: Path, relative_path: str) -> Path:
    """Resolve a resource while preventing absolute or symlink escape.

    Args:
        root (Path): Benchmark Package root.
        relative_path (str): POSIX-style Package-relative path.

    Raises:
        ValueError: Path is absolute, traverses upward, or escapes root.

    Returns:
        Path: Resolved path inside the Package root.
    """
    logical = PurePosixPath(relative_path)
    if logical.is_absolute() or ".." in logical.parts or not logical.parts:
        raise ValueError("resource path must remain Package-relative")
    resolved_root = root.resolve()
    candidate = (resolved_root / Path(*logical.parts)).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("resource path escapes Package root") from error
    return candidate


def validate_resources(
    root: Path,
    resources: tuple[ResourceRef, ...],
    *,
    verify_digests: bool,
) -> tuple[BenchmarkDiagnostic, ...]:
    """Validate safe paths, file metadata, and optional content digests.

    Args:
        root (Path): Package root containing resource paths.
        resources (tuple[ResourceRef, ...]): Declared resources.
        verify_digests (bool): Whether to hash full resource content.

    Raises:
        None: All failures become diagnostics.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: All independently detectable failures.
    """
    diagnostics: list[BenchmarkDiagnostic] = []
    for index, resource in enumerate(resources):
        path = ("resources", index)
        try:
            candidate = resolve_package_path(root, resource.path)
        except ValueError:
            diagnostics.append(
                BenchmarkDiagnostic(
                    code="benchmark.resource.path_invalid",
                    message="Resource path must remain inside the Benchmark Package.",
                    path=path + ("path",),
                )
            )
            continue
        if not candidate.is_file():
            diagnostics.append(
                BenchmarkDiagnostic(
                    code="benchmark.resource.missing",
                    message="Declared Benchmark resource does not exist.",
                    path=path + ("path",),
                )
            )
            continue
        actual_size = candidate.stat().st_size
        if actual_size != resource.size:
            diagnostics.append(
                BenchmarkDiagnostic(
                    code="benchmark.resource.size_mismatch",
                    message=(
                        f"Declared size {resource.size} does not match "
                        f"actual size {actual_size}."
                    ),
                    source=resource.id,
                    path=path + ("size",),
                )
            )
        guessed_type = mimetypes.guess_type(candidate.name)[0]
        if guessed_type and resource.media_type != guessed_type:
            diagnostics.append(
                BenchmarkDiagnostic(
                    code="benchmark.resource.media_type_mismatch",
                    message="Declared media type differs from the filename-derived type.",
                    source=resource.id,
                    path=path + ("media_type",),
                )
            )
        if verify_digests:
            actual_digest = file_sha256(candidate)
            if actual_digest != resource.sha256:
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.resource.digest_mismatch",
                        message=(
                            f"Expected {resource.sha256}; actual "
                            f"{actual_digest}."
                        ),
                        source=resource.id,
                        path=path + ("sha256",),
                    )
                )
    return tuple(diagnostics)


def collect_logical_uris(value: Any, *, path: tuple[str | int, ...] = ()) -> tuple[
    tuple[str, str, tuple[str | int, ...]], ...
]:
    """Collect asset and ground-truth URIs recursively from semantic values.

    Args:
        value (Any): JSON-compatible task or manifest data.
        path (tuple[str | int, ...]): Current source path.

    Raises:
        None.

    Returns:
        tuple[tuple[str, str, tuple[str | int, ...]], ...]: Kind, logical ID,
        and occurrence path for every URI.
    """
    found: list[tuple[str, str, tuple[str | int, ...]]] = []
    if isinstance(value, str):
        if value.startswith("asset://"):
            found.append(("asset", value.removeprefix("asset://"), path))
        elif value.startswith("groundtruth://"):
            found.append(
                ("ground_truth", value.removeprefix("groundtruth://"), path)
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(collect_logical_uris(item, path=path + (index,)))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(collect_logical_uris(item, path=path + (key,)))
    return tuple(found)


def validate_logical_references(
    task_data: list[dict[str, Any]],
    resources: tuple[ResourceRef, ...],
) -> tuple[BenchmarkDiagnostic, ...]:
    """Check every logical task URI against the resource manifest.

    Args:
        task_data (list[dict[str, Any]]): Canonical task mappings.
        resources (tuple[ResourceRef, ...]): Package resource declarations.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Missing or kind-mismatched references.
    """
    by_id = {item.id: item for item in resources}
    diagnostics: list[BenchmarkDiagnostic] = []
    for index, task in enumerate(task_data):
        task_id = str(task.get("id", "")) or None
        for kind, logical_id, occurrence in collect_logical_uris(task):
            resource = by_id.get(logical_id)
            expected_kind = (
                ResourceKind.ASSET if kind == "asset" else ResourceKind.GROUND_TRUTH
            )
            if resource is None:
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.resource.reference_missing",
                        message="Task references an undeclared Package resource.",
                        path=("tasks", index) + occurrence,
                        task_id=task_id,
                    )
                )
            elif resource.kind is not expected_kind:
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.resource.kind_mismatch",
                        message="Task logical URI kind differs from the resource declaration.",
                        path=("tasks", index) + occurrence,
                        task_id=task_id,
                    )
                )
    return tuple(diagnostics)


def validate_host_resource_fields(
    task_data: list[dict[str, Any]],
) -> tuple[BenchmarkDiagnostic, ...]:
    """Reject undeclared host-relative resource fields inside Package tasks.

    Args:
        task_data (list[dict[str, Any]]): Canonical Package task mappings.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: CWD-dependent resource diagnostics.
    """
    diagnostics: list[BenchmarkDiagnostic] = []
    host_keys = {"host_path", "local_path", "source_path"}

    def walk(
        value: Any,
        *,
        task_index: int,
        task_id: str | None,
        path: tuple[str | int, ...],
    ) -> None:
        """Inspect one nested value for host resource fields.

        Args:
            value (Any): Nested JSON value.
            task_index (int): Task source index.
            task_id (str | None): Optional task identity.
            path (tuple[str | int, ...]): Nested task field path.

        Raises:
            None.

        Returns:
            None.
        """
        if isinstance(value, list):
            for index, item in enumerate(value):
                walk(
                    item,
                    task_index=task_index,
                    task_id=task_id,
                    path=path + (index,),
                )
            return
        if not isinstance(value, dict):
            return
        for key, item in value.items():
            occurrence = path + (key,)
            if (
                key in host_keys
                and isinstance(item, str)
                and not item.startswith("asset://")
            ):
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.resource.cwd_reference",
                        message="Host resource fields in a Package must use asset:// references.",
                        path=("tasks", task_index) + occurrence,
                        task_id=task_id,
                    )
                )
            walk(
                item,
                task_index=task_index,
                task_id=task_id,
                path=occurrence,
            )

    for task_index, task in enumerate(task_data):
        walk(
            task,
            task_index=task_index,
            task_id=str(task.get("id", "")) or None,
            path=(),
        )
    return tuple(diagnostics)
