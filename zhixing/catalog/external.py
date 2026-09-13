"""Explicit discovery and immutable catalogs for external components."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from importlib import metadata as importlib_metadata
from types import MappingProxyType
from typing import Any

from zhixing.components import (
    BUILTIN_RUNTIME_TYPES,
    ComponentBundle,
    ComponentDefinitionError,
    ComponentSpec,
    RuntimeTypeCatalog,
    construct_component,
    validate_component_spec,
)
from zhixing.components.models import redact_mapping
from zhixing.graph import GraphComponentRef, GraphRole, SecretRef
from zhixing.graph.contracts import NodeContractCatalog
from zhixing.runtime.models import ResolvedComponentDefinition

from .builtins import (
    BUILTIN_COMPONENT_CATALOG,
    BuiltInComponentCatalog,
    create_builtin_resolver,
)


ENTRY_POINT_GROUP = "zhixing.components"
_PROVIDER_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_ENTRY_POINT_TARGET = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_.]*(?::[A-Za-z_][A-Za-z0-9_.]*)?$"
)


class ExternalComponentError(ValueError):
    """Base sanitized error for discovery, loading, and catalog resolution."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        """Create a bounded public error without plugin repr or traceback.

        Args:
            code (str): Stable machine-readable error code.
            message (str): Bounded non-sensitive explanation.
            details (Mapping[str, Any] | None): Safe structured details.

        Returns:
            None: Initializes the error.
        """
        safe_message = str(message).replace("\n", " ")[:500]
        super().__init__(safe_message)
        self.code = code
        self.details = MappingProxyType(dict(redact_mapping(details or {})))

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the stable diagnostic without implementation objects.

        Returns:
            dict[str, Any]: JSON-compatible safe diagnostic.
        """
        return {"code": self.code, "message": str(self), "details": dict(self.details)}


class ComponentDiscoveryError(ExternalComponentError):
    """The installed provider metadata cannot be selected deterministically."""


class ComponentCatalogError(ExternalComponentError, LookupError):
    """An external component catalog is conflicting or cannot resolve a ref."""


@dataclass(frozen=True)
class PluginOrigin:
    """Sanitized installed-distribution provenance for one provider."""

    distribution: str
    version: str
    source_kind: str = "index"
    vcs: str = ""
    requested_revision: str = ""
    commit_id: str = ""

    def to_safe_dict(self) -> dict[str, str]:
        """Return provenance without local paths, URLs, or credentials.

        Returns:
            dict[str, str]: Safe JSON-compatible provenance.
        """
        return {
            "distribution": self.distribution,
            "version": self.version,
            "source_kind": self.source_kind,
            "vcs": self.vcs,
            "requested_revision": self.requested_revision,
            "commit_id": self.commit_id,
        }


@dataclass(frozen=True)
class PluginCandidate:
    """Metadata-only Entry Point candidate that has not been imported."""

    provider_id: str
    target: str
    origin: PluginOrigin
    entry_point: Any = field(repr=False, compare=False)

    def to_safe_dict(self) -> dict[str, Any]:
        """Return stable candidate metadata without the EntryPoint object.

        Returns:
            dict[str, Any]: Safe JSON-compatible metadata.
        """
        return {
            "provider_id": self.provider_id,
            "target": self.target,
            "origin": self.origin.to_safe_dict(),
        }


@dataclass(frozen=True)
class PluginLoadFailure:
    """Bounded failure for one independently loaded provider."""

    provider_id: str
    stage: str
    code: str
    error_type: str
    message: str

    def to_safe_dict(self) -> dict[str, str]:
        """Return a safe provider failure without arbitrary exception text.

        Returns:
            dict[str, str]: Stable failure fields.
        """
        return {
            "provider_id": self.provider_id,
            "stage": self.stage,
            "code": self.code,
            "error_type": self.error_type,
            "message": self.message,
        }


@dataclass(frozen=True)
class DiscoveryReport:
    """Complete safe report for one explicit discovery operation."""

    candidates: tuple[PluginCandidate, ...]
    selected_provider_ids: tuple[str, ...]
    skipped_provider_ids: tuple[str, ...]
    loaded_provider_ids: tuple[str, ...]
    failures: tuple[PluginLoadFailure, ...]

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the report without EntryPoint or component objects.

        Returns:
            dict[str, Any]: JSON-compatible discovery report.
        """
        return {
            "candidates": [item.to_safe_dict() for item in self.candidates],
            "selected_provider_ids": list(self.selected_provider_ids),
            "skipped_provider_ids": list(self.skipped_provider_ids),
            "loaded_provider_ids": list(self.loaded_provider_ids),
            "failures": [item.to_safe_dict() for item in self.failures],
        }


@dataclass(frozen=True)
class ComponentCatalogEntry:
    """One immutable external catalog entry and its safe provider identity."""

    provider_id: str
    specification: ComponentSpec = field(repr=False)
    origin: PluginOrigin | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        """Return public metadata without factories or component instances.

        Returns:
            dict[str, Any]: Safe catalog entry metadata.
        """
        return {
            "provider_id": self.provider_id,
            "component": self.specification.safe_metadata(),
            "origin": self.origin.to_safe_dict() if self.origin else None,
        }


class ComponentCatalog:
    """Immutable exact-version catalog built from validated provider bundles."""

    def __init__(
        self,
        bundles: Iterable[tuple[str, ComponentBundle]] = (),
        *,
        origins: Mapping[str, PluginOrigin] | None = None,
        built_in_catalog: BuiltInComponentCatalog = BUILTIN_COMPONENT_CATALOG,
    ) -> None:
        """Build deterministic indexes and merged contract/type catalogs.

        Args:
            bundles (Iterable[tuple[str, ComponentBundle]]): Provider declarations.
            origins (Mapping[str, PluginOrigin] | None): Optional safe provenance.
            built_in_catalog (BuiltInComponentCatalog): Framework-owned catalog
                used only for collision checks.

        Raises:
            ComponentCatalogError: Provider/component identities conflict.
            ComponentDefinitionError: Contracts or runtime types conflict.

        Returns:
            None: Initializes immutable catalog state.
        """
        source_origins = origins or {}
        entries: dict[tuple[str, str, str], ComponentCatalogEntry] = {}
        provider_ids: set[str] = set()
        contracts = []
        runtime_types = BUILTIN_RUNTIME_TYPES

        ordered = sorted(tuple(bundles), key=lambda item: item[0])
        for provider_id, bundle in ordered:
            _validate_provider_id(provider_id)
            if provider_id in provider_ids:
                raise ComponentCatalogError(
                    "plugin.provider_duplicate",
                    "Multiple installed candidates declare the same provider ID.",
                    details={"provider_id": provider_id},
                )
            provider_ids.add(provider_id)
            for specification in sorted(bundle.components, key=lambda item: item.identifier):
                validate_component_spec(specification)
                key = (specification.namespace, specification.name, specification.version)
                if key in entries:
                    raise ComponentCatalogError(
                        "component.catalog_identity_conflict",
                        "External providers declare the same component identity.",
                        details={
                            "component": specification.identifier,
                            "providers": sorted(
                                {entries[key].provider_id, provider_id}
                            ),
                        },
                    )
                built_in = built_in_catalog.get(specification.namespace, specification.name)
                if built_in is not None and built_in.version == specification.version:
                    raise ComponentCatalogError(
                        "component.catalog_builtin_conflict",
                        "An external component conflicts with a built-in identity.",
                        details={"component": specification.identifier},
                    )
                entries[key] = ComponentCatalogEntry(
                    provider_id=provider_id,
                    specification=specification,
                    origin=source_origins.get(provider_id),
                )
                contracts.append(specification.contract)
                runtime_types = runtime_types.merge(
                    RuntimeTypeCatalog(specification.runtime_types, strict=True)
                )

        try:
            contract_catalog = NodeContractCatalog(contracts)
        except ValueError as error:
            raise ComponentCatalogError(
                "component.catalog_contract_conflict",
                "External providers declare conflicting node contracts.",
                details={"error_type": type(error).__name__},
            ) from error

        self._entries = MappingProxyType(entries)
        self._providers = tuple(sorted(provider_ids))
        self._contract_catalog = contract_catalog
        self._runtime_types = runtime_types

    @property
    def contract_catalog(self) -> NodeContractCatalog:
        """Return the immutable external NodeContract catalog.

        Returns:
            NodeContractCatalog: Contracts declared by external providers.
        """
        return self._contract_catalog

    @property
    def runtime_types(self) -> RuntimeTypeCatalog:
        """Return built-in plus external logical runtime type bindings.

        Returns:
            RuntimeTypeCatalog: Strict merged runtime types.
        """
        return self._runtime_types

    def providers(self) -> tuple[str, ...]:
        """Return loaded provider IDs in deterministic order.

        Returns:
            tuple[str, ...]: Sorted provider identities.
        """
        return self._providers

    def entries(self) -> tuple[ComponentCatalogEntry, ...]:
        """Return catalog entries sorted by full component identity.

        Returns:
            tuple[ComponentCatalogEntry, ...]: Immutable deterministic entries.
        """
        return tuple(self._entries[key] for key in sorted(self._entries))

    def available_versions(self, namespace: str, name: str) -> tuple[str, ...]:
        """Return external versions for one namespace/name pair.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Returns:
            tuple[str, ...]: Sorted exact component versions.
        """
        return tuple(
            sorted(
                key[2]
                for key in self._entries
                if key[0] == namespace and key[1] == name
            )
        )

    def resolve(self, reference: GraphComponentRef) -> ComponentCatalogEntry:
        """Resolve an exact version or an unambiguous namespace/name reference.

        Args:
            reference (GraphComponentRef): Declarative graph component reference.

        Raises:
            ComponentCatalogError: Component/version is missing or ambiguous.

        Returns:
            ComponentCatalogEntry: Matching immutable entry.
        """
        matches = [
            entry
            for key, entry in self._entries.items()
            if key[0] == reference.namespace and key[1] == reference.name
        ]
        versions = sorted(entry.specification.version for entry in matches)
        identity = f"{reference.namespace}:{reference.name}"
        if reference.version is not None:
            entry = self._entries.get((reference.namespace, reference.name, reference.version))
            if entry is None:
                raise ComponentCatalogError(
                    "component.catalog_version_not_found",
                    "The requested external component version is unavailable.",
                    details={
                        "component": identity,
                        "requested_version": reference.version,
                        "available_versions": versions,
                    },
                )
            return entry
        if not matches:
            raise ComponentCatalogError(
                "component.catalog_not_found",
                "The requested external component is not installed.",
                details={"component": identity},
            )
        if len(matches) > 1:
            raise ComponentCatalogError(
                "component.catalog_version_ambiguous",
                "The external component reference requires an explicit version.",
                details={"component": identity, "available_versions": versions},
            )
        return matches[0]

    def to_safe_dict(self) -> dict[str, Any]:
        """Return catalog metadata without implementation or service objects.

        Returns:
            dict[str, Any]: Safe JSON-compatible catalog view.
        """
        return {
            "providers": list(self._providers),
            "components": [entry.to_safe_dict() for entry in self.entries()],
        }


@dataclass(frozen=True)
class DiscoveredComponentEnvironment:
    """Immutable result used explicitly by high-level SDK/runtime bootstrap."""

    catalog: ComponentCatalog = field(repr=False)
    report: DiscoveryReport

    @property
    def contract_catalog(self) -> NodeContractCatalog:
        """Return contracts contributed by successfully loaded providers.

        Returns:
            NodeContractCatalog: External contract catalog.
        """
        return self.catalog.contract_catalog

    @property
    def runtime_types(self) -> RuntimeTypeCatalog:
        """Return merged built-in and external runtime type bindings.

        Returns:
            RuntimeTypeCatalog: Strict runtime type catalog.
        """
        return self.catalog.runtime_types

    def to_safe_dict(self) -> dict[str, Any]:
        """Return only safe report and catalog metadata.

        Returns:
            dict[str, Any]: JSON-compatible environment summary.
        """
        return {"report": self.report.to_safe_dict(), "catalog": self.catalog.to_safe_dict()}


def _validate_provider_id(provider_id: str) -> None:
    """Reject unstable provider identifiers before import.

    Args:
        provider_id (str): Entry Point provider identity.

    Raises:
        ComponentDiscoveryError: The identity is blank or malformed.

    Returns:
        None: Validation succeeds.
    """
    if not isinstance(provider_id, str) or not _PROVIDER_ID.fullmatch(provider_id):
        raise ComponentDiscoveryError(
            "plugin.provider_id_invalid",
            "A component provider ID must be a stable identifier.",
            details={"provider_id": str(provider_id)[:128]},
        )


def _distribution_origin(entry_point: Any) -> PluginOrigin:
    """Read optional installed provenance while removing URLs and local paths.

    Args:
        entry_point (Any): Importlib EntryPoint-like metadata object.

    Returns:
        PluginOrigin: Safe origin with index defaults for missing metadata.
    """
    distribution = getattr(entry_point, "dist", None)
    metadata = getattr(distribution, "metadata", {}) or {}
    distribution_name = str(
        metadata.get("Name")
        or getattr(distribution, "name", "unknown-distribution")
    )[:200]
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,200}", distribution_name):
        distribution_name = "unknown-distribution"
    version = str(getattr(distribution, "version", "unknown"))[:100]
    if not re.fullmatch(r"[A-Za-z0-9_.+!-]{1,100}", version):
        version = "unknown"
    direct_url: Mapping[str, Any] = {}
    try:
        raw = distribution.read_text("direct_url.json") if distribution is not None else None
        decoded = json.loads(raw) if raw else {}
        if isinstance(decoded, Mapping):
            direct_url = decoded
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
        direct_url = {}

    vcs_info = direct_url.get("vcs_info")
    if isinstance(vcs_info, Mapping):
        return PluginOrigin(
            distribution=distribution_name,
            version=version,
            source_kind="vcs",
            vcs=str(vcs_info.get("vcs", ""))[:50],
            requested_revision=str(vcs_info.get("requested_revision", ""))[:128],
            commit_id=str(vcs_info.get("commit_id", ""))[:128],
        )
    if isinstance(direct_url.get("dir_info"), Mapping):
        return PluginOrigin(distribution_name, version, source_kind="local")
    if direct_url:
        return PluginOrigin(distribution_name, version, source_kind="archive")
    return PluginOrigin(distribution_name, version)


def _installed_entry_points() -> Iterable[Any]:
    """Enumerate only the fixed ZhiXing component Entry Point group.

    Returns:
        Iterable[Any]: Importlib EntryPoint objects without loading targets.
    """
    return importlib_metadata.entry_points(group=ENTRY_POINT_GROUP)


def enumerate_component_plugins(
    entry_points_provider: Callable[[], Iterable[Any]] | None = None,
) -> tuple[PluginCandidate, ...]:
    """Enumerate metadata-only candidates without calling ``EntryPoint.load``.

    Args:
        entry_points_provider (Callable[[], Iterable[Any]] | None): Injectable
            metadata boundary used by tests and embedded environments.

    Raises:
        ComponentDiscoveryError: A provider identity is invalid.

    Returns:
        tuple[PluginCandidate, ...]: Stable sorted candidates.
    """
    provider = entry_points_provider or _installed_entry_points
    candidates = []
    for entry_point in provider():
        if getattr(entry_point, "group", ENTRY_POINT_GROUP) != ENTRY_POINT_GROUP:
            continue
        provider_id = str(getattr(entry_point, "name", ""))
        _validate_provider_id(provider_id)
        target = str(getattr(entry_point, "value", ""))[:300]
        candidates.append(
            PluginCandidate(
                provider_id=provider_id,
                target=(
                    target
                    if _ENTRY_POINT_TARGET.fullmatch(target)
                    else "<invalid-entry-point-target>"
                ),
                origin=_distribution_origin(entry_point),
                entry_point=entry_point,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                item.provider_id,
                item.origin.distribution,
                item.origin.version,
                item.target,
            ),
        )
    )


def select_component_plugins(
    candidates: Iterable[PluginCandidate],
    *,
    allowlist: Iterable[str] | None = None,
    denylist: Iterable[str] = (),
) -> tuple[tuple[PluginCandidate, ...], tuple[str, ...]]:
    """Apply deterministic provider policy and reject duplicate provider IDs.

    Args:
        candidates (Iterable[PluginCandidate]): Metadata-only candidates.
        allowlist (Iterable[str] | None): Optional exact provider allowlist.
        denylist (Iterable[str]): Exact provider denylist, which takes priority.

    Raises:
        ComponentDiscoveryError: Duplicate installed provider IDs are present.

    Returns:
        tuple[tuple[PluginCandidate, ...], tuple[str, ...]]: Selected candidates
            and sorted skipped provider IDs.
    """
    ordered = tuple(sorted(candidates, key=lambda item: item.provider_id))
    seen: set[str] = set()
    for candidate in ordered:
        if candidate.provider_id in seen:
            raise ComponentDiscoveryError(
                "plugin.provider_duplicate",
                "Multiple installed Entry Points declare the same provider ID.",
                details={"provider_id": candidate.provider_id},
            )
        seen.add(candidate.provider_id)
    allowed = set(allowlist) if allowlist is not None else None
    denied = set(denylist)
    selected = tuple(
        candidate
        for candidate in ordered
        if candidate.provider_id not in denied
        and (allowed is None or candidate.provider_id in allowed)
    )
    skipped = tuple(
        candidate.provider_id for candidate in ordered if candidate not in selected
    )
    return selected, skipped


def load_component_plugins(
    candidates: Iterable[PluginCandidate],
    *,
    allowlist: Iterable[str] | None = None,
    denylist: Iterable[str] = (),
    built_in_catalog: BuiltInComponentCatalog = BUILTIN_COMPONENT_CATALOG,
) -> DiscoveredComponentEnvironment:
    """Load selected providers independently and build one immutable catalog.

    Args:
        candidates (Iterable[PluginCandidate]): Metadata-only candidates.
        allowlist (Iterable[str] | None): Optional exact provider allowlist.
        denylist (Iterable[str]): Exact provider denylist.
        built_in_catalog (BuiltInComponentCatalog): Built-in collision boundary.

    Raises:
        ComponentDiscoveryError: Candidate selection is ambiguous.
        ComponentCatalogError: Successfully loaded bundles conflict globally.

    Returns:
        DiscoveredComponentEnvironment: Catalog plus complete safe report.
    """
    all_candidates = tuple(candidates)
    selected, skipped = select_component_plugins(
        all_candidates, allowlist=allowlist, denylist=denylist
    )
    loaded: list[tuple[str, ComponentBundle]] = []
    origins: dict[str, PluginOrigin] = {}
    failures: list[PluginLoadFailure] = []
    for candidate in selected:
        try:
            bundle = candidate.entry_point.load()
            if not isinstance(bundle, ComponentBundle):
                raise ComponentDefinitionError(
                    "component.bundle_return_invalid",
                    "A component provider must export a ComponentBundle object.",
                )
            # Recreate the immutable value so a forged subclass cannot bypass validation.
            validated_bundle = ComponentBundle(
                components=tuple(bundle.components),
                schema_version=bundle.schema_version,
            )
        except Exception as error:
            code = getattr(error, "code", "plugin.provider_load_failed")
            failures.append(
                PluginLoadFailure(
                    provider_id=candidate.provider_id,
                    stage="load",
                    code=str(code),
                    error_type=type(error).__name__,
                    message=f"Provider loading failed ({type(error).__name__}).",
                )
            )
            continue
        loaded.append((candidate.provider_id, validated_bundle))
        origins[candidate.provider_id] = candidate.origin

    catalog = ComponentCatalog(
        loaded,
        origins=origins,
        built_in_catalog=built_in_catalog,
    )
    report = DiscoveryReport(
        candidates=tuple(sorted(all_candidates, key=lambda item: item.provider_id)),
        selected_provider_ids=tuple(item.provider_id for item in selected),
        skipped_provider_ids=skipped,
        loaded_provider_ids=catalog.providers(),
        failures=tuple(failures),
    )
    return DiscoveredComponentEnvironment(catalog=catalog, report=report)


def discover_components(
    *,
    allowlist: Iterable[str] | None = None,
    denylist: Iterable[str] = (),
    entry_points_provider: Callable[[], Iterable[Any]] | None = None,
    built_in_catalog: BuiltInComponentCatalog = BUILTIN_COMPONENT_CATALOG,
) -> DiscoveredComponentEnvironment:
    """Explicitly enumerate and load external component providers.

    Args:
        allowlist (Iterable[str] | None): Optional exact provider allowlist.
        denylist (Iterable[str]): Exact provider denylist.
        entry_points_provider (Callable[[], Iterable[Any]] | None): Injectable
            metadata boundary.
        built_in_catalog (BuiltInComponentCatalog): Built-in collision boundary.

    Returns:
        DiscoveredComponentEnvironment: Immutable discovery environment.
    """
    candidates = enumerate_component_plugins(entry_points_provider)
    return load_component_plugins(
        candidates,
        allowlist=allowlist,
        denylist=denylist,
        built_in_catalog=built_in_catalog,
    )


def empty_component_environment() -> DiscoveredComponentEnvironment:
    """Create an explicit no-provider environment without scanning metadata.

    Returns:
        DiscoveredComponentEnvironment: Empty catalog and report.
    """
    return DiscoveredComponentEnvironment(
        catalog=ComponentCatalog(),
        report=DiscoveryReport((), (), (), (), ()),
    )


class CatalogComponentResolver:
    """Resolve formal external specifications and explicit run dependencies."""

    def __init__(
        self,
        catalog: ComponentCatalog,
        *,
        secret_provider: Mapping[str, Any] | Callable[[str], Any] | None = None,
        dependency_provider: Mapping[str, Any] | None = None,
        fallback: Any | None = None,
    ) -> None:
        """Configure external resolution and a non-shadowing fallback resolver.

        Args:
            catalog (ComponentCatalog): Immutable external catalog.
            secret_provider (Mapping[str, Any] | Callable[[str], Any] | None):
                Runtime-only SecretRef source.
            dependency_provider (Mapping[str, Any] | None): Explicit services.
            fallback (Any | None): Built-in or compatibility resolver used only
                when an identity is absent from the external catalog.

        Returns:
            None: Initializes a run-scoped resolver.
        """
        self.catalog = catalog
        self.secret_provider = secret_provider or {}
        self.dependency_provider = dict(dependency_provider or {})
        self.fallback = fallback

    def _secret(self, name: str) -> Any:
        """Resolve one SecretRef without serializing its value.

        Args:
            name (str): Stable secret name.

        Raises:
            LookupError: The configured provider has no matching value.

        Returns:
            Any: Runtime-only secret value.
        """
        try:
            if callable(self.secret_provider):
                return self.secret_provider(name)
            return self.secret_provider[name]
        except (KeyError, LookupError) as error:
            raise LookupError(f"secret reference {name!r} is unavailable") from error

    def _value(self, name: str, value: Any) -> Any:
        """Resolve explicit dependency literals and nested SecretRef values.

        Args:
            name (str): Dependency slot name.
            value (Any): Declarative dependency value.

        Returns:
            Any: Run-scoped dependency value.
        """
        if name in self.dependency_provider:
            return self.dependency_provider[name]
        if isinstance(value, SecretRef):
            return self._secret(value.secret_ref)
        if isinstance(value, Mapping) and set(value) == {"secret_ref"}:
            return self._secret(str(value["secret_ref"]))
        if isinstance(value, Mapping):
            return {key: self._value(str(key), item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(self._value(name, item) for item in value)
        if isinstance(value, list):
            return [self._value(name, item) for item in value]
        return value

    def resolve(
        self,
        reference: GraphComponentRef,
        role: GraphRole | None = None,
    ) -> Any:
        """Resolve a graph reference to a formal definition or fallback value.

        Args:
            reference (GraphComponentRef): Declarative component reference.
            role (GraphRole | None): Expected core role.

        Raises:
            ComponentCatalogError: External identity/version is invalid.
            ComponentDefinitionError: Formal role or spec is invalid.
            LookupError: Neither catalog nor fallback can resolve the identity.

        Returns:
            Any: ResolvedComponentDefinition for formal external components, or
                the fallback resolver's compatible result.
        """
        fallback_catalog = getattr(self.fallback, "catalog", None)
        built_in = (
            fallback_catalog.get(reference.namespace, reference.name)
            if fallback_catalog is not None
            else None
        )
        external_versions = self.catalog.available_versions(
            reference.namespace,
            reference.name,
        )
        if reference.version is None and built_in is not None and external_versions:
            raise ComponentCatalogError(
                "component.catalog_version_ambiguous",
                "The component reference requires an explicit version.",
                details={
                    "component": f"{reference.namespace}:{reference.name}",
                    "available_versions": sorted(
                        {*external_versions, built_in.version}
                    ),
                },
            )
        try:
            entry = self.catalog.resolve(reference)
        except ComponentCatalogError as error:
            fallback_matches = built_in is not None and (
                reference.version is None or reference.version == built_in.version
            )
            if (
                error.code
                not in {
                    "component.catalog_not_found",
                    "component.catalog_version_not_found",
                }
                or self.fallback is None
                or not fallback_matches
            ):
                raise
            return self.fallback.resolve(reference, role)
        specification = entry.specification
        validate_component_spec(specification)
        if role is not None and specification.role is not None and specification.role.value != role.value:
            raise ComponentDefinitionError(
                "component.role_mismatch",
                "The component role does not match the graph node role.",
                component_id=specification.identifier,
                details={"expected_role": role.value, "actual_role": specification.role.value},
            )
        dependencies = {
            name: self._value(name, value)
            for name, value in reference.dependencies.items()
        }
        return ResolvedComponentDefinition(specification, MappingProxyType(dependencies))


def create_component_resolver(
    environment: DiscoveredComponentEnvironment,
    *,
    secrets: Mapping[str, Any] | Callable[[str], Any] | None = None,
    dependencies: Mapping[str, Any] | None = None,
) -> CatalogComponentResolver:
    """Create a fresh composite external-plus-built-in resolver for one run.

    Args:
        environment (DiscoveredComponentEnvironment): Explicit discovery result.
        secrets (Mapping[str, Any] | Callable[[str], Any] | None): Secret provider.
        dependencies (Mapping[str, Any] | None): Prebuilt runtime services.

    Returns:
        CatalogComponentResolver: Fresh run-scoped composite resolver.
    """
    fallback = create_builtin_resolver(secrets=secrets, dependencies=dependencies)
    return CatalogComponentResolver(
        environment.catalog,
        secret_provider=secrets,
        dependency_provider=dependencies,
        fallback=fallback,
    )


__all__ = [
    "ENTRY_POINT_GROUP",
    "CatalogComponentResolver",
    "ComponentCatalog",
    "ComponentCatalogEntry",
    "ComponentCatalogError",
    "ComponentDiscoveryError",
    "DiscoveredComponentEnvironment",
    "DiscoveryReport",
    "ExternalComponentError",
    "PluginCandidate",
    "PluginLoadFailure",
    "PluginOrigin",
    "create_component_resolver",
    "discover_components",
    "empty_component_environment",
    "enumerate_component_plugins",
    "load_component_plugins",
    "select_component_plugins",
]
