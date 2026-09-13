"""Side-effect-free Studio Benchmark Catalog and preview application services."""

from __future__ import annotations

import base64
import json
import re
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterable, Literal, Mapping, Sequence, TypeVar

from pydantic import ValidationError

from zhixing.benchmark import (
    BenchmarkCandidate,
    BenchmarkPlan,
    BenchmarkValidationLevel,
    ExperimentProtocol,
    build_schedule,
    compile_benchmark_package,
    discover_benchmark_candidates,
)
from zhixing.benchmark.diagnostics import (
    BenchmarkDefinitionError,
    BenchmarkDiagnostic,
    BenchmarkDiagnosticSeverity,
)
from zhixing.benchmark.identity import canonical_hash

from .benchmark_errors import (
    StudioBenchmarkNotFoundError,
    StudioBenchmarkValidationError,
)
from .benchmark_models import (
    StudioBenchmarkCatalogEntryV1,
    StudioBenchmarkCatalogPageV1,
    StudioBenchmarkDetailV1,
    StudioBenchmarkDiagnosticV1,
    StudioBenchmarkPreviewRequestV1,
    StudioBenchmarkPreviewResponseV1,
    StudioBenchmarkRequirementV1,
    StudioBenchmarkResourceSummaryV1,
    StudioBenchmarkSplitSummaryV1,
    StudioBenchmarkTaskMetadataV1,
    StudioBenchmarkTaskPageV1,
    StudioBenchmarkValidationIdentitiesV1,
    StudioBenchmarkValidationResultV1,
    StudioDeviceProfilePageV1,
    StudioPreviewAgentIdentityV1,
    StudioPreviewExecutionLimitsV1,
    StudioPreviewIdentitiesV1,
    StudioPreviewScheduleEntryV1,
    StudioPreviewTaskInstanceV1,
)
from .repository import AgentDocumentRepository, AgentRevisionNotFoundError
from .revision_verifier import verify_immutable_agent_revision
from .catalog import StudioComponentCatalog, build_studio_component_catalog
from .run_errors import StudioRunValidationError
from .run_execution import AndroidDeviceProfileResolver
from .run_models import RunSnapshotV1


StudioBenchmarkSourceKind = Literal[
    "package", "catalog_root", "installed", "managed"
]
_SOURCE_ID = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_ENTRY_ID = re.compile(r"^benchmark-entry-[a-f0-9]{32}$")
_SnapshotResult = TypeVar("_SnapshotResult")


@dataclass(frozen=True)
class StudioBenchmarkSource:
    """Named server-owned Catalog source invisible to browser path input."""

    source_id: str
    kind: StudioBenchmarkSourceKind
    locator: Path | None = None

    def __post_init__(self) -> None:
        """Validate source identity and kind-specific locator shape.

        Args:
            None.

        Raises:
            ValueError: Source identity or locator shape is invalid.

        Returns:
            None.
        """
        if _SOURCE_ID.fullmatch(self.source_id) is None:
            raise ValueError("Benchmark source ID must be stable")
        requires_locator = self.kind in {"package", "catalog_root", "managed"}
        if requires_locator != (self.locator is not None):
            raise ValueError("Benchmark source locator does not match source kind")


@dataclass(frozen=True)
class _StudioBenchmarkEntry:
    """Internal immutable registry entry retaining its formal candidate."""

    catalog_entry_id: str
    source_id: str
    source_kind: Literal["package", "catalog", "installed"]
    relative_key: str
    candidate: BenchmarkCandidate
    split_results: Mapping[str, Any]
    availability: Literal["available", "invalid"]
    diagnostics: tuple[StudioBenchmarkDiagnosticV1, ...]
    release_closure_identity: str | None = None
    @property
    def split_summaries(self) -> tuple[StudioBenchmarkSplitSummaryV1, ...]:
        """Return stable split counts from the definition index.

        Args:
            None.

        Raises:
            None.

        Returns:
            Split summaries ordered by split name.
        """
        return tuple(
            StudioBenchmarkSplitSummaryV1(
                name=split,
                task_count=(
                    len(result.plan.tasks)
                    if result.plan is not None
                    else None
                ),
            )
            for split, result in sorted(self.split_results.items())
        )

    def public_item(self) -> StudioBenchmarkCatalogEntryV1:
        """Project the internal entry into safe Catalog list metadata.

        Args:
            None.

        Raises:
            ValueError: Internal metadata violates the public DTO.

        Returns:
            Safe Catalog entry.
        """
        return StudioBenchmarkCatalogEntryV1(
            catalog_entry_id=self.catalog_entry_id,
            package_identity=self.candidate.identity,
            title=self.candidate.title,
            version=self.candidate.version,
            source_kind=self.source_kind,
            platforms=tuple(self.candidate.manifest.platforms),
            splits=self.split_summaries,
            availability=self.availability,
            warnings=self.diagnostics,
        )


@dataclass(frozen=True)
class StudioBenchmarkCatalogSemanticFact:
    """Safe semantic collision facts for one concrete Catalog source."""

    catalog_entry_id: str
    package_identity: str
    package_content_identity: str | None
    closure_identity: str | None
    source_id: str
    managed: bool


@dataclass(frozen=True)
class PreparedStudioBenchmarkDefinition:
    """One coherently verified definition shared by preview and first create."""

    request: StudioBenchmarkPreviewRequestV1
    source_id: str
    source_kind: Literal["package", "catalog", "installed"]
    relative_key: str
    benchmark_plan: BenchmarkPlan
    agent_snapshots: tuple[RunSnapshotV1, ...]
    preview: StudioBenchmarkPreviewResponseV1


@dataclass(frozen=True)
class StudioBenchmarkAuthoringCatalogSource:
    """Internal path-bearing Catalog source for closed-closure import only."""

    catalog_entry_id: str
    catalog_snapshot_identity: str
    package_identity: str
    package_content_identity: str
    protocol_identity: str | None
    root: Path


def _safe_diagnostics(
    diagnostics: Iterable[BenchmarkDiagnostic],
) -> tuple[StudioBenchmarkDiagnosticV1, ...]:
    """Project and deterministically order bounded definition diagnostics.

    Args:
        diagnostics: Formal Benchmark diagnostics.

    Raises:
        ValueError: A projected diagnostic violates the public DTO.

    Returns:
        Stable safe diagnostics, capped to 100 entries.
    """
    ordered = sorted(diagnostics, key=lambda item: item.sort_key())[:100]
    return tuple(
        StudioBenchmarkDiagnosticV1.from_domain(item) for item in ordered
    )


def _entry_id(source_id: str, relative_key: str, identity: str) -> str:
    """Derive a stable opaque entry ID from safe source coordinates.

    Args:
        source_id: Stable configured source identity.
        relative_key: Source-relative Package coordinate.
        identity: Readable Package semantic identity.

    Raises:
        None.

    Returns:
        Opaque deterministic Catalog entry identity.
    """
    digest = canonical_hash(
        {
            "contract": "studio-benchmark-entry-v1",
            "source_id": source_id,
            "relative_key": relative_key,
            "package_identity": identity,
        }
    ).removeprefix("sha256:")
    return f"benchmark-entry-{digest[:32]}"


def _relative_key(
    source: StudioBenchmarkSource,
    candidate: BenchmarkCandidate,
) -> str:
    """Return a stable safe Package key relative to its named source.

    Args:
        source: Named server-side source.
        candidate: Discovered formal candidate.

    Raises:
        ValueError: Candidate is outside its configured local source.

    Returns:
        Safe non-absolute source-relative key.
    """
    if source.kind == "installed":
        distribution = candidate.distribution or "unknown-distribution"
        return f"{distribution}@{candidate.distribution_version}:{candidate.identity}"
    assert source.locator is not None
    root = source.locator.expanduser().resolve()
    if source.kind in {"package", "managed"}:
        if candidate.root.resolve() != root:
            raise ValueError("Package candidate escaped configured source")
        return source.locator.name if source.kind == "managed" else "."
    relative = candidate.root.resolve().relative_to(root)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Catalog candidate escaped configured source")
    return relative.as_posix()


def _discover_source(
    source: StudioBenchmarkSource,
    *,
    installed_entry_points: Sequence[Any] | None = None,
) -> tuple[BenchmarkCandidate, ...]:
    """Discover candidates from exactly one named server-side source.

    Args:
        source: Typed source configuration.
        installed_entry_points: Optional injected metadata fixtures.

    Raises:
        BenchmarkDefinitionError: An explicit local source is invalid.

    Returns:
        Deterministically ordered candidates.
    """
    if source.kind in {"package", "managed"}:
        assert source.locator is not None
        return discover_benchmark_candidates(
            package_dirs=(source.locator,),
            include_installed=False,
        )
    if source.kind == "catalog_root":
        assert source.locator is not None
        return discover_benchmark_candidates(
            catalog_roots=(source.locator,),
            include_installed=False,
        )
    return discover_benchmark_candidates(
        include_installed=True,
        installed_entry_points=installed_entry_points,
    )


def default_studio_benchmark_sources(
    workspace: str | Path,
    *,
    include_installed: bool = True,
) -> tuple[StudioBenchmarkSource, ...]:
    """Build safe default sources without scanning arbitrary workspace paths.

    Args:
        workspace: Explicit Studio workspace root.
        include_installed: Whether installed Package metadata is allowed.

    Raises:
        OSError: Workspace path resolution fails.

    Returns:
        Named sources; the workspace Catalog root is included only if present.
    """
    workspace_root = Path(workspace).expanduser().resolve()
    sources: list[StudioBenchmarkSource] = []
    builtins = workspace_root / "benchmarks"
    if builtins.is_dir():
        sources.append(
            StudioBenchmarkSource(
                source_id="workspace-benchmarks",
                kind="catalog_root",
                locator=builtins,
            )
        )
    if include_installed:
        sources.append(
            StudioBenchmarkSource(
                source_id="installed-benchmarks",
                kind="installed",
            )
        )
    return tuple(sources)


class StudioBenchmarkCatalogService:
    """Immutable safe Studio projection over formal Benchmark candidates."""

    def __init__(
        self,
        sources: Iterable[StudioBenchmarkSource] = (),
        *,
        installed_entry_points: Sequence[Any] | None = None,
    ) -> None:
        """Discover, index, and freeze one process-level Catalog snapshot.

        Args:
            sources: Explicit named source configurations.
            installed_entry_points: Optional installed metadata fixtures.

        Raises:
            BenchmarkDefinitionError: An explicit source manifest/root is invalid.
            ValueError: Source IDs or derived entry IDs collide.

        Returns:
            None.
        """
        selected_sources = tuple(sources)
        if len({item.source_id for item in selected_sources}) != len(
            selected_sources
        ):
            raise ValueError("Benchmark source IDs must be unique")
        discovered: list[tuple[StudioBenchmarkSource, BenchmarkCandidate]] = []
        for source in selected_sources:
            for candidate in _discover_source(
                source,
                installed_entry_points=installed_entry_points,
            ):
                discovered.append((source, candidate))

        entries = [
            self._entry_for_source(source, candidate)
            for source, candidate in discovered
        ]
        self._install_entries(entries)

    @staticmethod
    def _entry_for_source(
        source: StudioBenchmarkSource,
        candidate: BenchmarkCandidate,
        *,
        closure_identity: str | None = None,
    ) -> _StudioBenchmarkEntry:
        """Compile one candidate into an immutable Catalog entry.

        Args:
            source: Named server-owned source.
            candidate: Discovered formal Package candidate.
            closure_identity: Optional verified managed frozen-closure identity.

        Raises:
            BenchmarkDefinitionError: Candidate definitions are malformed.
            ValueError: Source coordinates are unsafe.

        Returns:
            Complete immutable internal Catalog entry.
        """
        relative_key = _relative_key(source, candidate)
        split_results = {
            split: compile_benchmark_package(
                candidate.root,
                split=split,
                validation_level=BenchmarkValidationLevel.SEMANTIC,
            )
            for split in sorted(candidate.splits)
        }
        diagnostics = tuple(
            diagnostic
            for result in split_results.values()
            for diagnostic in result.diagnostics
        )
        available = all(result.plan is not None for result in split_results.values())
        return _StudioBenchmarkEntry(
            catalog_entry_id=_entry_id(
                source.source_id,
                relative_key,
                candidate.identity,
            ),
            source_id=source.source_id,
            source_kind=(
                "package"
                if source.kind == "package"
                else "installed"
                if source.kind == "installed"
                else "catalog"
            ),
            relative_key=relative_key,
            candidate=candidate,
            split_results=MappingProxyType(split_results),
            availability="available" if available else "invalid",
            diagnostics=_safe_diagnostics(diagnostics),
            release_closure_identity=closure_identity,
        )

    def _install_entries(self, source_entries: Iterable[_StudioBenchmarkEntry]) -> None:
        """Normalize entries and install one immutable snapshot in this object.

        Args:
            source_entries: Complete concrete source entries.

        Raises:
            ValueError: Entry identities collide.

        Returns:
            None.
        """
        catalog_codes = {
            "benchmark.catalog.equivalent_source",
            "benchmark.catalog.identity_ambiguous",
        }
        entries = [
            replace(
                entry,
                diagnostics=tuple(
                    item for item in entry.diagnostics if item.code not in catalog_codes
                ),
            )
            for entry in source_entries
        ]
        grouped: dict[str, list[_StudioBenchmarkEntry]] = {}
        for entry in entries:
            grouped.setdefault(entry.candidate.identity, []).append(entry)
        for identity_entries in grouped.values():
            if len(identity_entries) < 2:
                continue
            content_identities = {
                result.plan.package_content_identity
                for entry in identity_entries
                for result in entry.split_results.values()
                if result.plan is not None
            }
            equivalent = (
                len(content_identities) == 1
                and all(entry.availability == "available" for entry in identity_entries)
            )
            diagnostic = StudioBenchmarkDiagnosticV1(
                code=(
                    "benchmark.catalog.equivalent_source"
                    if equivalent
                    else "benchmark.catalog.identity_ambiguous"
                ),
                message=(
                    "Equivalent Package identity is available from multiple sources."
                    if equivalent
                    else "Package identity has divergent or invalid configured sources."
                ),
                severity="warning",
                source="catalog",
            )
            for index, entry in enumerate(entries):
                if entry in identity_entries:
                    entries[index] = replace(
                        entry,
                        diagnostics=entry.diagnostics + (diagnostic,),
                    )
        entries.sort(
            key=lambda item: (
                item.candidate.identity,
                item.source_kind,
                item.source_id,
                item.relative_key,
            )
        )
        ids = [item.catalog_entry_id for item in entries]
        if len(ids) != len(set(ids)):
            raise ValueError("Derived Benchmark Catalog entry IDs collide")
        self._entries = tuple(entries)
        self._by_id = MappingProxyType(
            {item.catalog_entry_id: item for item in entries}
        )
        self._snapshot_identity = canonical_hash(
            {
                "contract": "studio-benchmark-catalog-v1",
                "entries": [
                    {
                        "id": item.catalog_entry_id,
                        "sourceId": item.source_id,
                        "packageIdentity": item.candidate.identity,
                        "contentIdentities": sorted(
                            {
                                result.plan.package_content_identity
                                for result in item.split_results.values()
                                if result.plan is not None
                            }
                        ),
                        "closureIdentity": item.release_closure_identity,
                        "availability": item.availability,
                    }
                    for item in entries
                ],
            }
        )

    @classmethod
    def _from_entries(
        cls,
        entries: Iterable[_StudioBenchmarkEntry],
    ) -> "StudioBenchmarkCatalogService":
        """Create one snapshot directly from already compiled immutable entries.

        Args:
            entries: Complete entry set from a captured snapshot plus additions.

        Raises:
            ValueError: Entry identities collide.

        Returns:
            New immutable Catalog snapshot without filesystem rescanning.
        """
        result = object.__new__(cls)
        result._install_entries(entries)
        return result

    def semantic_facts(
        self,
        package_identity: str,
    ) -> tuple[StudioBenchmarkCatalogSemanticFact, ...]:
        """Return safe collision facts for one readable Package identity.

        Args:
            package_identity: Exact readable Package version identity.

        Raises:
            None.

        Returns:
            Stable concrete-source semantic facts without paths.
        """
        facts: list[StudioBenchmarkCatalogSemanticFact] = []
        for entry in self._entries:
            if entry.candidate.identity != package_identity:
                continue
            content_identities = {
                result.plan.package_content_identity
                for result in entry.split_results.values()
                if result.plan is not None
            }
            facts.append(
                StudioBenchmarkCatalogSemanticFact(
                    catalog_entry_id=entry.catalog_entry_id,
                    package_identity=entry.candidate.identity,
                    package_content_identity=(
                        next(iter(content_identities))
                        if len(content_identities) == 1
                        else None
                    ),
                    closure_identity=entry.release_closure_identity,
                    source_id=entry.source_id,
                    managed=entry.release_closure_identity is not None,
                )
            )
        return tuple(facts)

    def with_managed_package(
        self,
        *,
        source_id: str,
        publication_id: str,
        package_root: Path,
        package_identity: str,
        package_content_identity: str,
        closure_identity: str,
    ) -> tuple["StudioBenchmarkCatalogService", str]:
        """Prebuild a next snapshot containing one verified managed Package.

        Args:
            source_id: Fixed safe managed source identity.
            publication_id: Opaque publication coordinate.
            package_root: Verified private managed Package tree.
            package_identity: Expected readable Core Package identity.
            package_content_identity: Expected canonical Package content identity.
            closure_identity: Verified frozen-closure identity.

        Raises:
            BenchmarkDefinitionError: Managed Package cannot be compiled.
            ValueError: Compiled identity/content or source coordinate differs.

        Returns:
            Complete next snapshot and stable managed Catalog entry identity.
        """
        source = StudioBenchmarkSource(
            source_id=source_id,
            kind="managed",
            locator=package_root,
        )
        candidates = _discover_source(source)
        if len(candidates) != 1:
            raise ValueError("managed publication must contain one Package")
        entry = self._entry_for_source(
            source,
            candidates[0],
            closure_identity=closure_identity,
        )
        if entry.relative_key != publication_id:
            raise ValueError("managed Package coordinate differs from publication")
        content_identities = {
            result.plan.package_content_identity
            for result in entry.split_results.values()
            if result.plan is not None
        }
        if (
            entry.availability != "available"
            or entry.candidate.identity != package_identity
            or content_identities != {package_content_identity}
        ):
            raise ValueError("managed Package metadata differs from frozen authority")
        return self._from_entries((*self._entries, entry)), entry.catalog_entry_id

    @property
    def snapshot_identity(self) -> str:
        """Return the immutable process Catalog identity.

        Args:
            None.

        Raises:
            None.

        Returns:
            SHA-256-prefixed Catalog snapshot identity.
        """
        return self._snapshot_identity

    def resolve_entry(self, catalog_entry_id: str) -> _StudioBenchmarkEntry:
        """Resolve one opaque Catalog entry without path fallback.

        Args:
            catalog_entry_id: Browser-submitted opaque entry identity.

        Raises:
            StudioBenchmarkValidationError: Identity syntax is invalid.
            StudioBenchmarkNotFoundError: Identity is not in this snapshot.

        Returns:
            Internal immutable Catalog entry.
        """
        if _ENTRY_ID.fullmatch(catalog_entry_id) is None:
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.entry_invalid",
                "Benchmark Catalog entry identity is invalid",
            )
        entry = self._by_id.get(catalog_entry_id)
        if entry is None:
            raise StudioBenchmarkNotFoundError(
                "benchmark.catalog.not_found",
                "Benchmark Catalog entry was not found",
            )
        return entry

    def resolve_authoring_source(
        self,
        catalog_entry_id: str,
    ) -> StudioBenchmarkAuthoringCatalogSource:
        """Resolve an available entry for the internal authoring copy boundary.

        Args:
            catalog_entry_id: Browser-submitted opaque Catalog identity.

        Raises:
            StudioBenchmarkValidationError: Entry is not currently available.
            StudioBenchmarkNotFoundError: Entry is absent from this snapshot.

        Returns:
            Internal source facts, including a path never projected to HTTP.
        """
        entry = self.resolve_entry(catalog_entry_id)
        content_identities = {
            result.plan.package_content_identity
            for result in entry.split_results.values()
            if result.plan is not None
        }
        if entry.availability != "available" or len(content_identities) != 1:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.catalog_unavailable",
                "Benchmark Catalog entry is not available for authoring import",
            )
        protocol_identities = {
            (
                result.protocol.canonical_hash()
                if result.protocol is not None
                else None
            )
            for result in entry.split_results.values()
        }
        if len(protocol_identities) != 1:
            raise StudioBenchmarkValidationError(
                "benchmark.authoring.catalog_unavailable",
                "Benchmark Catalog entry has inconsistent Protocol identity",
            )
        return StudioBenchmarkAuthoringCatalogSource(
            catalog_entry_id=entry.catalog_entry_id,
            catalog_snapshot_identity=self._snapshot_identity,
            package_identity=entry.candidate.identity,
            package_content_identity=next(iter(content_identities)),
            protocol_identity=next(iter(protocol_identities)),
            root=entry.candidate.root,
        )

    def _filter_identity(
        self,
        *,
        query: str,
        platform: str,
        source_kind: str,
    ) -> str:
        """Return a stable cursor-binding filter identity.

        Args:
            query: Normalized text filter.
            platform: Normalized platform filter.
            source_kind: Normalized source-kind filter.

        Raises:
            None.

        Returns:
            SHA-256-prefixed filter identity.
        """
        return canonical_hash(
            {
                "query": query,
                "platform": platform,
                "source_kind": source_kind,
            }
        )

    def _encode_cursor(self, offset: int, filter_identity: str) -> str:
        """Encode a path-free opaque cursor bound to this snapshot.

        Args:
            offset: Next zero-based item offset.
            filter_identity: Canonical filter identity.

        Raises:
            ValueError: Cursor payload cannot be serialized.

        Returns:
            URL-safe opaque cursor.
        """
        raw = json.dumps(
            {
                "v": 1,
                "snapshot": self._snapshot_identity,
                "filter": filter_identity,
                "offset": offset,
            },
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(
        self,
        cursor: str | None,
        filter_identity: str,
    ) -> int:
        """Decode and validate a Catalog/task cursor.

        Args:
            cursor: Optional opaque cursor.
            filter_identity: Expected canonical filter identity.

        Raises:
            StudioBenchmarkValidationError: Cursor is malformed or stale.

        Returns:
            Zero-based offset, defaulting to zero.
        """
        if cursor is None:
            return 0
        try:
            padding = "=" * (-len(cursor) % 4)
            value = json.loads(
                base64.urlsafe_b64decode(cursor + padding).decode("utf-8")
            )
            if (
                not isinstance(value, dict)
                or value.get("v") != 1
                or value.get("snapshot") != self._snapshot_identity
                or value.get("filter") != filter_identity
                or not isinstance(value.get("offset"), int)
                or value["offset"] < 0
            ):
                raise ValueError("cursor contract mismatch")
            return int(value["offset"])
        except Exception as error:
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.cursor_invalid",
                "Benchmark cursor is invalid or stale",
            ) from error

    @staticmethod
    def _limit(limit: int) -> int:
        """Validate a bounded page limit.

        Args:
            limit: Requested page size.

        Raises:
            StudioBenchmarkValidationError: Limit is outside 1..100.

        Returns:
            Validated page size.
        """
        if isinstance(limit, bool) or not 1 <= limit <= 100:
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.limit_invalid",
                "Benchmark page limit must be within 1 and 100",
            )
        return limit

    def list_entries(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        query: str = "",
        platform: str = "",
        source_kind: str = "",
    ) -> StudioBenchmarkCatalogPageV1:
        """List a deterministic filtered page from the frozen snapshot.

        Args:
            limit: Bounded page size.
            cursor: Optional opaque continuation cursor.
            query: Optional title/identity substring filter.
            platform: Optional exact platform filter.
            source_kind: Optional exact safe source-kind filter.

        Raises:
            StudioBenchmarkValidationError: Filters, limit, or cursor are invalid.

        Returns:
            Versioned Catalog page.
        """
        size = self._limit(limit)
        normalized_query = query.strip().casefold()[:256]
        normalized_platform = platform.strip().lower()
        normalized_source = source_kind.strip().lower()
        if normalized_platform not in {"", "android", "harmonyos"}:
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.platform_invalid",
                "Benchmark platform filter is invalid",
            )
        if normalized_source not in {"", "package", "catalog", "installed"}:
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.source_kind_invalid",
                "Benchmark source-kind filter is invalid",
            )
        filter_identity = self._filter_identity(
            query=normalized_query,
            platform=normalized_platform,
            source_kind=normalized_source,
        )
        offset = self._decode_cursor(cursor, filter_identity)
        filtered = tuple(
            item
            for item in self._entries
            if (
                not normalized_query
                or normalized_query in item.candidate.identity.casefold()
                or normalized_query in item.candidate.title.casefold()
            )
            and (
                not normalized_platform
                or normalized_platform in item.candidate.manifest.platforms
            )
            and (
                not normalized_source
                or normalized_source == item.source_kind
            )
        )
        if offset > len(filtered):
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.cursor_invalid",
                "Benchmark cursor is outside the selected page",
            )
        selected = filtered[offset : offset + size]
        next_offset = offset + len(selected)
        return StudioBenchmarkCatalogPageV1(
            items=tuple(item.public_item() for item in selected),
            next_cursor=(
                self._encode_cursor(next_offset, filter_identity)
                if next_offset < len(filtered)
                else None
            ),
        )

    def detail(self, catalog_entry_id: str) -> StudioBenchmarkDetailV1:
        """Return safe manifest and indexed definition detail.

        Args:
            catalog_entry_id: Opaque Catalog entry identity.

        Raises:
            StudioBenchmarkNotFoundError: Entry is absent.
            StudioBenchmarkValidationError: Entry identity is malformed.

        Returns:
            Versioned Package detail, including invalid availability.
        """
        entry = self.resolve_entry(catalog_entry_id)
        manifest = entry.candidate.manifest
        successful = next(
            (
                result
                for result in entry.split_results.values()
                if result.plan is not None
            ),
            None,
        )
        requirements = tuple(
            [
                StudioBenchmarkRequirementV1(
                    id=item.id,
                    kind="app",
                    platform=item.platform,
                    version=item.version or "",
                    requires_login=item.requires_login,
                )
                for item in manifest.apps
            ]
            + [
                StudioBenchmarkRequirementV1(
                    id=item.id,
                    kind="plugin",
                    version=item.version or "",
                    optional=item.optional,
                )
                for item in manifest.plugins
            ]
        )
        resources = tuple(
            StudioBenchmarkResourceSummaryV1(
                id=item.id,
                kind=item.kind.value,
                media_type=item.media_type,
                sha256=item.sha256,
                size=item.size,
            )
            for item in manifest.resources
        )
        return StudioBenchmarkDetailV1(
            catalog_entry_id=entry.catalog_entry_id,
            package_identity=entry.candidate.identity,
            package_content_identity=(
                successful.plan.package_content_identity
                if successful is not None
                else None
            ),
            title=entry.candidate.title,
            version=entry.candidate.version,
            source_kind=entry.source_kind,
            availability=entry.availability,
            platforms=tuple(manifest.platforms),
            splits=entry.split_summaries,
            requirements=requirements,
            resources=resources,
            default_protocol=(
                successful.protocol if successful is not None else None
            ),
            diagnostics=entry.diagnostics,
        )

    def compile_split(
        self,
        catalog_entry_id: str,
        split: str,
        *,
        validation_level: BenchmarkValidationLevel = (
            BenchmarkValidationLevel.SEMANTIC
        ),
    ) -> tuple[_StudioBenchmarkEntry, Any]:
        """Compile an explicitly selected entry and split.

        Args:
            catalog_entry_id: Opaque concrete source identity.
            split: Exact split name.
            validation_level: Formal compiler validation depth.

        Raises:
            StudioBenchmarkValidationError: Split is blank or compilation fails.
            StudioBenchmarkNotFoundError: Entry is absent.

        Returns:
            Internal entry and successful formal compilation result.
        """
        entry = self.resolve_entry(catalog_entry_id)
        if not split.strip() or len(split) > 128:
            raise StudioBenchmarkValidationError(
                "benchmark.split.invalid",
                "Benchmark split is invalid",
            )
        result = compile_benchmark_package(
            entry.candidate.root,
            split=split,
            validation_level=validation_level,
        )
        if result.plan is None:
            diagnostic = result.diagnostics[0] if result.diagnostics else None
            raise StudioBenchmarkValidationError(
                (
                    diagnostic.code
                    if diagnostic is not None
                    else "benchmark.definition.invalid"
                ),
                "Benchmark definition could not be compiled",
            )
        return entry, result

    def list_tasks(
        self,
        catalog_entry_id: str,
        *,
        split: str,
        limit: int = 50,
        cursor: str | None = None,
    ) -> StudioBenchmarkTaskPageV1:
        """Return stable safe task metadata for one split.

        Args:
            catalog_entry_id: Opaque concrete source identity.
            split: Exact split name.
            limit: Bounded page size.
            cursor: Optional opaque continuation cursor.

        Raises:
            StudioBenchmarkValidationError: Query or definition is invalid.
            StudioBenchmarkNotFoundError: Entry is absent.

        Returns:
            Versioned task metadata page.
        """
        size = self._limit(limit)
        _entry, result = self.compile_split(catalog_entry_id, split)
        assert result.plan is not None
        tasks = tuple(sorted(result.plan.tasks, key=lambda item: item.id))
        filter_identity = canonical_hash(
            {
                "kind": "tasks",
                "entry": catalog_entry_id,
                "split": split,
                "plan": result.plan.canonical_hash(),
            }
        )
        offset = self._decode_cursor(cursor, filter_identity)
        if offset > len(tasks):
            raise StudioBenchmarkValidationError(
                "benchmark.catalog.cursor_invalid",
                "Benchmark task cursor is outside the selected page",
            )
        selected = tasks[offset : offset + size]
        items = tuple(
            StudioBenchmarkTaskMetadataV1(
                task_id=task.id,
                split=split,
                instruction=task.instruction,
                app=task.app,
                task_type=task.type,
                requires_login=task.requires_login,
                max_steps=task.max_steps,
                initializer_count=(
                    len(task.task_initializer)
                    + len(task.environment_initializer)
                    + len(task.cleanup_initializer)
                ),
                evaluator_kind=task.evaluator.name,
            )
            for task in selected
        )
        next_offset = offset + len(items)
        return StudioBenchmarkTaskPageV1(
            catalog_entry_id=catalog_entry_id,
            split=split,
            items=items,
            next_cursor=(
                self._encode_cursor(next_offset, filter_identity)
                if next_offset < len(tasks)
                else None
            ),
        )

    def validate_entry(
        self,
        catalog_entry_id: str,
        *,
        split: str | None = None,
    ) -> StudioBenchmarkValidationResultV1:
        """Run full definition/resource validation without runtime binding.

        Args:
            catalog_entry_id: Opaque concrete source identity.
            split: Optional exact split.

        Raises:
            StudioBenchmarkNotFoundError: Entry is absent.
            StudioBenchmarkValidationError: Identity or split syntax is invalid.

        Returns:
            Versioned validation result; invalid definitions are normal results.
        """
        entry = self.resolve_entry(catalog_entry_id)
        if split is not None and (not split.strip() or len(split) > 128):
            raise StudioBenchmarkValidationError(
                "benchmark.split.invalid",
                "Benchmark split is invalid",
            )
        result = compile_benchmark_package(
            entry.candidate.root,
            split=split,
            validation_level=BenchmarkValidationLevel.FULL,
        )
        protocol = result.protocol
        plan = result.plan
        return StudioBenchmarkValidationResultV1(
            catalog_entry_id=catalog_entry_id,
            valid=result.is_success,
            identities=StudioBenchmarkValidationIdentitiesV1(
                package=entry.candidate.identity,
                package_content=(
                    plan.package_content_identity if plan is not None else None
                ),
                benchmark_plan=(
                    plan.canonical_hash() if plan is not None else None
                ),
                experiment_protocol=(
                    protocol.canonical_hash()
                    if protocol is not None
                    else None
                ),
            ),
            diagnostics=_safe_diagnostics(result.diagnostics),
        )


class StudioBenchmarkCatalogSnapshotOwner:
    """Process-owned copy-on-write pointer to immutable Catalog snapshots."""

    def __init__(self, snapshot: StudioBenchmarkCatalogService) -> None:
        """Install the initial complete immutable Catalog snapshot.

        Args:
            snapshot: Fully built initial Catalog.

        Raises:
            None.

        Returns:
            None.
        """
        self._snapshot = snapshot
        self._writer_lock = threading.RLock()

    def capture(self) -> StudioBenchmarkCatalogService:
        """Capture one immutable snapshot for a complete read operation.

        Returns:
            Current immutable Catalog snapshot.
        """
        return self._snapshot

    @property
    def snapshot_identity(self) -> str:
        """Return the identity of one atomically captured snapshot.

        Returns:
            Current Catalog snapshot identity.
        """
        return self.capture().snapshot_identity

    def serialized_update(
        self,
        transform: Callable[
            [StudioBenchmarkCatalogService],
            tuple[StudioBenchmarkCatalogService, _SnapshotResult],
        ],
    ) -> _SnapshotResult:
        """Serialize one publisher and replace only with a complete snapshot.

        Args:
            transform: Callback that prepares all external authority and returns
                a complete next snapshot plus its caller result.

        Raises:
            Exception: Propagates preparation or durable-commit failures before
                the pointer is changed.

        Returns:
            Callback result after non-throwing in-memory pointer replacement.
        """
        with self._writer_lock:
            next_snapshot, result = transform(self._snapshot)
            if not isinstance(next_snapshot, StudioBenchmarkCatalogService):
                raise TypeError("Catalog update must return a complete snapshot")
            # Assignment is the sole visibility boundary and cannot perform I/O.
            self._snapshot = next_snapshot
            return result

    def __getattr__(self, name: str) -> Any:
        """Forward one method/property lookup to an atomically captured snapshot.

        Args:
            name: Public immutable Catalog attribute name.

        Raises:
            AttributeError: Captured Catalog has no such attribute.

        Returns:
            Attribute bound to one captured immutable snapshot.
        """
        return getattr(self.capture(), name)


class StudioBenchmarkApplicationService:
    """Compose Catalog, immutable revisions, profiles, and pure preview."""

    def __init__(
        self,
        *,
        catalog: StudioBenchmarkCatalogService | StudioBenchmarkCatalogSnapshotOwner,
        agents: AgentDocumentRepository,
        profiles: AndroidDeviceProfileResolver,
        contract_catalog: Any | None = None,
        component_catalog: StudioComponentCatalog | None = None,
    ) -> None:
        """Configure explicit side-effect-free preview dependencies.

        Args:
            catalog: Frozen Studio Benchmark Catalog.
            agents: Immutable Agent revision repository.
            profiles: Static profile directory and runtime resolver.
            contract_catalog: Optional extension NodeContract catalog.
            component_catalog: Exact safe Catalog for Agent policy eligibility.

        Raises:
            None.

        Returns:
            None.
        """
        self.catalog = catalog
        self.agents = agents
        self.profiles = profiles
        self.contract_catalog = contract_catalog
        self.component_catalog = component_catalog or build_studio_component_catalog()

    @staticmethod
    def parse_preview_request(
        raw: Mapping[str, Any],
    ) -> StudioBenchmarkPreviewRequestV1:
        """Parse an untrusted preview mapping into the strict DTO.

        Args:
            raw: Untrusted browser request mapping.

        Raises:
            StudioBenchmarkValidationError: Request violates the contract.

        Returns:
            Strict immutable preview request.
        """
        try:
            return StudioBenchmarkPreviewRequestV1.model_validate(dict(raw))
        except ValidationError as error:
            first = error.errors(include_url=False, include_input=False)[0]
            location = ".".join(str(item) for item in first["loc"])
            raise StudioBenchmarkValidationError(
                "benchmark.preview.request_invalid",
                f"Invalid Benchmark preview request at {location}: {first['msg']}",
            ) from error

    def device_profiles(self) -> StudioDeviceProfilePageV1:
        """Return safe configured profiles without runtime resolution.

        Args:
            None.

        Raises:
            ValueError: Static configuration violates the public DTO.

        Returns:
            Versioned safe profile directory.
        """
        return StudioDeviceProfilePageV1(items=self.profiles.safe_profiles())

    def preview(
        self,
        raw: Mapping[str, Any] | StudioBenchmarkPreviewRequestV1,
    ) -> StudioBenchmarkPreviewResponseV1:
        """Build one deterministic preview without persistence or execution.

        Args:
            raw: Strict DTO or untrusted browser request mapping.

        Raises:
            StudioBenchmarkValidationError: Definition or cardinality is invalid.
            StudioBenchmarkNotFoundError: Catalog entry is absent.

        Returns:
            Normalized preview-only schedule and canonical identities.
        """
        return self.prepare_definition(raw).preview

    def prepare_definition(
        self,
        raw: Mapping[str, Any] | StudioBenchmarkPreviewRequestV1,
    ) -> PreparedStudioBenchmarkDefinition:
        """Prepare one verified definition without persistence or execution.

        Args:
            raw: Strict DTO or untrusted browser definition mapping.

        Raises:
            StudioBenchmarkValidationError: Definition or cardinality is invalid.
            StudioBenchmarkNotFoundError: Catalog entry is absent.

        Returns:
            Immutable canonical facts consumed by preview or first create.
        """
        request = (
            raw
            if isinstance(raw, StudioBenchmarkPreviewRequestV1)
            else self.parse_preview_request(raw)
        )
        if (
            len(request.agent_revisions) != 1
            or len(request.benchmark.task_ids) != 1
            or request.protocol.repeats != 1
        ):
            raise StudioBenchmarkValidationError(
                "benchmark.preview.unsupported_cardinality",
                "Stage 5.1 supports one Agent, one task, and one repeat",
            )
        if not self.profiles.contains(request.device_profile_id):
            raise StudioBenchmarkValidationError(
                "benchmark.preview.device_profile_unknown",
                "Selected device profile is unavailable",
            )
        entry, result = self.catalog.compile_split(
            request.benchmark.catalog_entry_id,
            request.benchmark.split,
        )
        assert result.plan is not None
        plan = result.plan
        available_tasks = {task.id: task for task in plan.tasks}
        selected_task_id = request.benchmark.task_ids[0]
        task = available_tasks.get(selected_task_id)
        if task is None:
            raise StudioBenchmarkValidationError(
                "benchmark.preview.task_not_found",
                "Selected Benchmark task does not exist",
            )

        verified = []
        for selected in request.agent_revisions:
            try:
                verified.append(
                    verify_immutable_agent_revision(
                        self.agents,
                        selected.agent_id,
                        selected.revision_id,
                        contract_catalog=self.contract_catalog,
                        component_catalog=self.component_catalog,
                    )
                )
            except (AgentRevisionNotFoundError, StudioRunValidationError) as error:
                raise StudioBenchmarkValidationError(
                    "benchmark.preview.revision_invalid",
                    "Selected Agent revision is unavailable or invalid",
                ) from error

        schedule = build_schedule(
            plan,
            request.protocol,
            [item.agent_id for item in verified],
            task_ids=request.benchmark.task_ids,
        )
        revision_by_agent = {item.agent_id: item for item in verified}
        public_schedule = tuple(
            StudioPreviewScheduleEntryV1(
                planned_entry_id=(
                    "planned-entry-"
                    + canonical_hash(
                        {
                            "contract": "studio-benchmark-planned-entry-v1",
                            "entry": entry.catalog_entry_id,
                            "plan": plan.canonical_hash(),
                            "protocol": request.protocol.canonical_hash(),
                            "agent": item.agent_id,
                            "revision": revision_by_agent[
                                item.agent_id
                            ].revision_id,
                            "task": item.task_id,
                            "repeat": item.repeat,
                            "seed": item.seed,
                        }
                    ).removeprefix("sha256:")[:32]
                ),
                agent_id=item.agent_id,
                revision_id=revision_by_agent[item.agent_id].revision_id,
                task_id=item.task_id,
                repeat=item.repeat,
                order=index,
                derived_seed=item.seed,
                task_instance=StudioPreviewTaskInstanceV1(
                    availability=(
                        "pending_materialization"
                        if task.type == "dynamic"
                        else "template_only"
                    )
                ),
            )
            for index, item in enumerate(schedule)
        )
        if plan.package_identity is None or plan.package_content_identity is None:
            raise StudioBenchmarkValidationError(
                "benchmark.preview.package_identity_missing",
                "Selected Benchmark Package identity is incomplete",
            )
        fingerprint = canonical_hash(
            {
                "contract": "studio-benchmark-preview-v1",
                "catalog_entry_id": entry.catalog_entry_id,
                "source_id": entry.source_id,
                "package_identity": plan.package_identity,
                "package_content_identity": plan.package_content_identity,
                "benchmark_plan_identity": plan.canonical_hash(),
                "agents": [
                    {
                        "agent_id": item.agent_id,
                        "revision_id": item.revision_id,
                        "agent_graph_identity": item.canonical_hash,
                    }
                    for item in verified
                ],
                "task_ids": list(request.benchmark.task_ids),
                "experiment_protocol": request.protocol.canonical_payload(),
                "experiment_protocol_identity": request.protocol.canonical_hash(),
                "device_profile_id": request.device_profile_id,
                "limits": {
                    "max_agents": 1,
                    "max_selected_tasks": 1,
                    "max_repeats": 1,
                    "multi_agent_comparison": False,
                },
            }
        )
        fairness_diagnostics = tuple(
            StudioBenchmarkDiagnosticV1(
                code=code,
                message="Protocol materialization is not paired across Agents.",
                severity="warning",
                source="experiment-protocol",
            )
            for code in request.protocol.fairness_warnings
        )
        preview = StudioBenchmarkPreviewResponseV1(
            preview_fingerprint=fingerprint,
            identities=StudioPreviewIdentitiesV1(
                package=plan.package_identity,
                package_content=plan.package_content_identity,
                benchmark_plan=plan.canonical_hash(),
                experiment_protocol=request.protocol.canonical_hash(),
            ),
            agent_revisions=tuple(
                StudioPreviewAgentIdentityV1(
                    agent_id=item.agent_id,
                    revision_id=item.revision_id,
                    agent_graph=item.canonical_hash,
                )
                for item in verified
            ),
            normalized_protocol=request.protocol,
            device_profile_id=request.device_profile_id,
            execution_limits=StudioPreviewExecutionLimitsV1(),
            schedule=public_schedule,
            diagnostics=fairness_diagnostics,
        )
        return PreparedStudioBenchmarkDefinition(
            request=request,
            source_id=entry.source_id,
            source_kind=entry.source_kind,
            relative_key=entry.relative_key,
            benchmark_plan=plan,
            agent_snapshots=tuple(verified),
            preview=preview,
        )


__all__ = [
    "StudioBenchmarkApplicationService",
    "StudioBenchmarkAuthoringCatalogSource",
    "StudioBenchmarkCatalogService",
    "StudioBenchmarkCatalogSemanticFact",
    "StudioBenchmarkCatalogSnapshotOwner",
    "StudioBenchmarkSource",
    "StudioBenchmarkSourceKind",
    "default_studio_benchmark_sources",
]
