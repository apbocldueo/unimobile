"""Metadata-only discovery and immutable lookup for Benchmark Packages."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from pathlib import Path
from types import MappingProxyType
from typing import Any, Iterable, Sequence

from ..compiler import (
    BenchmarkCompilationResult,
    BenchmarkValidationLevel,
    compile_benchmark_package,
)
from ..constants import BENCHMARK_ENTRY_POINT_GROUP, BENCHMARK_MANIFEST_NAME
from ..diagnostics import BenchmarkDefinitionError, BenchmarkDiagnostic
from ..loaders import load_manifest
from ..models import BenchmarkPackageManifest

_ENTRY_POINT_TARGET = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*$")


@dataclass(frozen=True)
class BenchmarkCandidate:
    """Safe metadata for one local or installed Benchmark Package."""

    identity: str
    title: str
    version: str
    splits: tuple[str, ...]
    source_kind: str
    root: Path = field(repr=False, compare=False)
    manifest: BenchmarkPackageManifest = field(repr=False, compare=False)
    distribution: str = ""
    distribution_version: str = ""

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize candidate metadata without absolute paths.

        Returns:
            dict[str, Any]: Stable metadata-only representation.
        """
        return {
            "identity": self.identity,
            "title": self.title,
            "version": self.version,
            "splits": list(self.splits),
            "source_kind": self.source_kind,
            "distribution": self.distribution,
            "distribution_version": self.distribution_version,
        }


def _candidate_from_root(
    root: Path,
    *,
    source_kind: str,
    distribution: str = "",
    distribution_version: str = "",
) -> BenchmarkCandidate:
    """Create a candidate by reading only the Package manifest.

    Args:
        root (Path): Explicit Package root.
        source_kind (str): Safe source category.
        distribution (str): Optional installed distribution name.
        distribution_version (str): Optional installed distribution version.

    Raises:
        BenchmarkDefinitionError: Manifest is invalid.

    Returns:
        BenchmarkCandidate: Metadata-only candidate.
    """
    manifest = load_manifest(root)
    return BenchmarkCandidate(
        identity=manifest.identity.identifier,
        title=manifest.title,
        version=manifest.identity.version,
        splits=tuple(sorted(manifest.splits)),
        source_kind=source_kind,
        distribution=distribution,
        distribution_version=distribution_version,
        root=root.resolve(),
        manifest=manifest,
    )


def _entry_point_manifest(entry_point: Any) -> tuple[Path, str, str] | None:
    """Locate an installed Package manifest without loading its Entry Point.

    Args:
        entry_point (Any): ``importlib.metadata.EntryPoint``-like object.

    Raises:
        None: Malformed candidates are skipped by metadata enumeration.

    Returns:
        tuple[Path, str, str] | None: Package root and distribution provenance.
    """
    target = str(getattr(entry_point, "value", ""))
    if not _ENTRY_POINT_TARGET.fullmatch(target):
        return None
    distribution = getattr(entry_point, "dist", None)
    if distribution is None:
        return None
    relative_manifest = target.replace(".", "/") + f"/{BENCHMARK_MANIFEST_NAME}"
    files = tuple(getattr(distribution, "files", ()) or ())
    matched = next(
        (
            item
            for item in files
            if str(item).replace("\\", "/") == relative_manifest
        ),
        None,
    )
    if matched is None:
        return None
    manifest_path = Path(distribution.locate_file(matched))
    if not manifest_path.is_file():
        return None
    metadata = getattr(distribution, "metadata", {})
    name = str(metadata.get("Name", ""))
    version = str(getattr(distribution, "version", ""))
    return manifest_path.parent, name, version


def enumerate_installed_benchmarks(
    entry_points: Sequence[Any] | None = None,
) -> tuple[BenchmarkCandidate, ...]:
    """Enumerate installed Benchmark metadata without importing provider code.

    Args:
        entry_points (Sequence[Any] | None): Optional injected metadata fixtures.

    Raises:
        None: Invalid installed candidates are omitted from metadata-only output.

    Returns:
        tuple[BenchmarkCandidate, ...]: Stable installed candidates.
    """
    selected = (
        tuple(entry_points)
        if entry_points is not None
        else tuple(
            importlib_metadata.entry_points(group=BENCHMARK_ENTRY_POINT_GROUP)
        )
    )
    candidates: list[BenchmarkCandidate] = []
    for entry_point in selected:
        located = _entry_point_manifest(entry_point)
        if located is None:
            continue
        root, distribution, version = located
        try:
            candidates.append(
                _candidate_from_root(
                    root,
                    source_kind="installed",
                    distribution=distribution,
                    distribution_version=version,
                )
            )
        except BenchmarkDefinitionError:
            continue
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.identity,
                item.distribution,
                item.distribution_version,
            ),
        )
    )


def discover_benchmark_candidates(
    *,
    package_dirs: Iterable[str | Path] = (),
    catalog_roots: Iterable[str | Path] = (),
    include_installed: bool = True,
    installed_entry_points: Sequence[Any] | None = None,
) -> tuple[BenchmarkCandidate, ...]:
    """Discover only explicit local roots and installed metadata candidates.

    Args:
        package_dirs (Iterable[str | Path]): Explicit Package directories.
        catalog_roots (Iterable[str | Path]): Roots whose immediate children are Packages.
        include_installed (bool): Whether installed metadata is enumerated.
        installed_entry_points (Sequence[Any] | None): Optional test metadata.

    Raises:
        BenchmarkDefinitionError: An explicitly selected local Package is invalid.

    Returns:
        tuple[BenchmarkCandidate, ...]: Stable metadata-only candidates.
    """
    candidates: list[BenchmarkCandidate] = []
    seen_roots: set[Path] = set()
    for raw_root in package_dirs:
        root = Path(raw_root).resolve()
        if root in seen_roots:
            continue
        seen_roots.add(root)
        candidates.append(_candidate_from_root(root, source_kind="local"))
    for raw_catalog in catalog_roots:
        catalog_root = Path(raw_catalog).resolve()
        if not catalog_root.is_dir():
            raise BenchmarkDefinitionError(
                (
                    BenchmarkDiagnostic(
                        code="benchmark.catalog.root_missing",
                        message="Explicit Benchmark Catalog root does not exist.",
                        source="catalog-root",
                    ),
                )
            )
        for manifest_path in sorted(catalog_root.glob(f"*/{BENCHMARK_MANIFEST_NAME}")):
            root = manifest_path.parent.resolve()
            if root in seen_roots:
                continue
            seen_roots.add(root)
            candidates.append(_candidate_from_root(root, source_kind="catalog"))
    if include_installed:
        candidates.extend(
            enumerate_installed_benchmarks(installed_entry_points)
        )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.identity,
                item.source_kind,
                item.distribution,
            ),
        )
    )


class BenchmarkCatalog:
    """Immutable Benchmark Package catalog with deterministic conflicts."""

    def __init__(self, candidates: Iterable[BenchmarkCandidate] = ()) -> None:
        """Index stable candidates without loading tasks or resources.

        Args:
            candidates (Iterable[BenchmarkCandidate]): Metadata-only candidates.

        Raises:
            None.

        Returns:
            None: Initializes an immutable index.
        """
        ordered = tuple(
            sorted(
                candidates,
                key=lambda item: (
                    item.identity,
                    item.source_kind,
                    item.distribution,
                ),
            )
        )
        grouped: dict[str, tuple[BenchmarkCandidate, ...]] = {}
        for identity in sorted({item.identity for item in ordered}):
            grouped[identity] = tuple(
                item for item in ordered if item.identity == identity
            )
        self._candidates = ordered
        self._by_identity = MappingProxyType(grouped)

    def candidates(self) -> tuple[BenchmarkCandidate, ...]:
        """Return candidates in deterministic metadata order.

        Returns:
            tuple[BenchmarkCandidate, ...]: Immutable catalog entries.
        """
        return self._candidates

    def resolve(self, identity: str) -> BenchmarkCandidate:
        """Resolve one readable identity and detect same-version drift.

        Args:
            identity (str): ``publisher/name@version`` identity.

        Raises:
            BenchmarkDefinitionError: Identity is missing or semantically ambiguous.

        Returns:
            BenchmarkCandidate: Deterministically selected equivalent candidate.
        """
        matches = self._by_identity.get(identity, ())
        if not matches:
            raise BenchmarkDefinitionError(
                (
                    BenchmarkDiagnostic(
                        code="benchmark.catalog.not_found",
                        message="Benchmark Package identity was not found.",
                        source="catalog",
                    ),
                )
            )
        if len(matches) == 1:
            return matches[0]
        compiled = [
            (candidate, compile_benchmark_package(candidate.root))
            for candidate in matches
        ]
        identities = {
            result.plan.package_content_identity
            for _, result in compiled
            if result.plan is not None
        }
        if len(identities) != 1 or any(result.plan is None for _, result in compiled):
            raise BenchmarkDefinitionError(
                (
                    BenchmarkDiagnostic(
                        code="benchmark.catalog.identity_ambiguous",
                        message="Multiple sources provide the same readable identity with different content.",
                        source="catalog",
                    ),
                )
            )
        return matches[0]

    def info(self, identity: str) -> dict[str, Any]:
        """Return safe manifest and task-count information.

        Args:
            identity (str): Readable Package identity.

        Raises:
            BenchmarkDefinitionError: Package cannot be resolved or compiled.

        Returns:
            dict[str, Any]: Safe Package summary.
        """
        candidate = self.resolve(identity)
        result = compile_benchmark_package(candidate.root)
        if result.plan is None:
            raise BenchmarkDefinitionError(result.diagnostics)
        package_counts: dict[str, int] = {}
        for split_name in candidate.splits:
            split_result = compile_benchmark_package(
                candidate.root,
                split=split_name,
            )
            if split_result.plan is None:
                raise BenchmarkDefinitionError(split_result.diagnostics)
            package_counts[split_name] = len(split_result.plan.tasks)
        manifest = candidate.manifest
        return {
            **candidate.to_safe_dict(),
            "content_identity": result.plan.package_content_identity,
            "task_counts": package_counts,
            "platforms": list(manifest.platforms),
            "apps": [
                item.model_dump(mode="json", exclude_none=True)
                for item in manifest.apps
            ],
            "plugins": [
                item.model_dump(mode="json", exclude_none=True)
                for item in manifest.plugins
            ],
            "resources": [
                {
                    "id": item.id,
                    "kind": item.kind.value,
                    "media_type": item.media_type,
                    "sha256": item.sha256,
                    "size": item.size,
                }
                for item in manifest.resources
            ],
            "default_protocol": manifest.default_protocol,
        }

    def validate(
        self,
        identity: str,
        *,
        split: str | None = None,
        known_plugins: set[str] | None = None,
    ) -> BenchmarkCompilationResult:
        """Run full definition-layer validation for one Package.

        Args:
            identity (str): Readable Package identity.
            split (str | None): Optional split.
            known_plugins (set[str] | None): Optional metadata-only plugin IDs.

        Raises:
            BenchmarkDefinitionError: Identity cannot be resolved.

        Returns:
            BenchmarkCompilationResult: Full no-device validation result.
        """
        candidate = self.resolve(identity)
        return compile_benchmark_package(
            candidate.root,
            split=split,
            validation_level=BenchmarkValidationLevel.FULL,
            known_plugins=known_plugins,
        )
