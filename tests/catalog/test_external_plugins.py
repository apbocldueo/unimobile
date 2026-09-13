"""Contract tests for external component discovery and immutable catalogs."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import FrozenInstanceError, dataclass
from typing import Any

import pytest

from zhixing.catalog import (
    BUILTIN_COMPONENT_CATALOG,
    CatalogComponentResolver,
    ComponentCatalog,
    ComponentCatalogError,
    ComponentDiscoveryError,
    enumerate_component_plugins,
    load_component_plugins,
    select_component_plugins,
)
from zhixing.components import (
    BaseVerifier,
    BaseComponent,
    ComponentBundle,
    ComponentCategory,
    ComponentRole,
    ComponentSpec,
    RuntimeContext,
    VerifierInput,
    VerifierResult,
)
from zhixing.graph import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    GraphComponentRef,
    GraphRole,
    ContractPort,
    InvocationAdapterKind,
    NodeContract,
    NodeContractRef,
    PortDirection,
    contract_ref_for_role,
)


class _Verifier(BaseVerifier):
    """Minimal valid formal verifier used by catalog tests."""

    def invoke(self, input: VerifierInput, runtime: RuntimeContext) -> VerifierResult:
        """Return a deterministic success result.

        Args:
            input (VerifierInput): Verification evidence.
            runtime (RuntimeContext): Run-scoped context.

        Returns:
            VerifierResult: Successful result.
        """
        del input, runtime
        return VerifierResult(True)


@dataclass(frozen=True)
class _TokenA:
    """First Python runtime type for conflict tests."""

    value: str


@dataclass(frozen=True)
class _TokenB:
    """Second Python runtime type for conflict tests."""

    value: str


class _TokenAComponent(BaseComponent[_TokenA, _TokenA]):
    """Typed extension using the first logical runtime binding."""

    component_category = ComponentCategory.EXTENSION
    input_type = _TokenA
    output_type = _TokenA

    def invoke(self, input: _TokenA, runtime: RuntimeContext) -> _TokenA:
        """Return the first token unchanged.

        Args:
            input (_TokenA): Typed token.
            runtime (RuntimeContext): Run context.

        Returns:
            _TokenA: Original token.
        """
        del runtime
        return input


class _TokenBComponent(BaseComponent[_TokenB, _TokenB]):
    """Typed extension using the second logical runtime binding."""

    component_category = ComponentCategory.EXTENSION
    input_type = _TokenB
    output_type = _TokenB

    def invoke(self, input: _TokenB, runtime: RuntimeContext) -> _TokenB:
        """Return the second token unchanged.

        Args:
            input (_TokenB): Typed token.
            runtime (RuntimeContext): Run context.

        Returns:
            _TokenB: Original token.
        """
        del runtime
        return input


def _spec(
    *,
    namespace: str = "example.external",
    name: str = "verifier",
    version: str = "1.0.0",
) -> ComponentSpec:
    """Create a valid formal verifier specification.

    Args:
        namespace (str): Component namespace.
        name (str): Component name.
        version (str): Exact component version.

    Returns:
        ComponentSpec: Valid immutable specification.
    """
    contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(
        contract_ref_for_role(GraphRole.VERIFIER)
    )
    assert contract is not None
    return ComponentSpec(
        namespace=namespace,
        name=name,
        version=version,
        contract=contract,
        implementation=_Verifier,
        category=ComponentCategory.CORE_AGENT,
        role=ComponentRole.VERIFIER,
    )


def _token_spec(
    *,
    name: str,
    implementation: type[BaseComponent[Any, Any]],
    runtime_type: type[Any],
    contract_id: str = "fixture.shared.token",
    input_port: str = "input",
) -> ComponentSpec:
    """Create a custom extension spec for merge-conflict tests.

    Args:
        name (str): Component name.
        implementation (type[BaseComponent[Any, Any]]): Typed author class.
        runtime_type (type[Any]): Python type bound to the shared logical ID.
        contract_id (str): Exact contract ID.
        input_port (str): Input port used to vary contract definitions.

    Returns:
        ComponentSpec: Valid formal extension specification.
    """
    contract = NodeContract(
        ref=NodeContractRef(id=contract_id, version="1.0"),
        ports=(
            ContractPort(
                id=input_port,
                direction=PortDirection.INPUT,
                data_types=("fixture.shared_token",),
                required=True,
            ),
            ContractPort(
                id="result",
                direction=PortDirection.OUTPUT,
                data_types=("fixture.shared_token",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )
    return ComponentSpec(
        namespace="fixture.merge",
        name=name,
        version="1.0.0",
        contract=contract,
        implementation=implementation,
        category=ComponentCategory.EXTENSION,
        runtime_types={"fixture.shared_token": runtime_type},
        input_type=runtime_type,
        output_type=runtime_type,
    )
class _Distribution:
    """Small importlib distribution double with optional direct_url metadata."""

    def __init__(self, name: str, version: str, direct_url: str | None = None) -> None:
        """Store fake installed metadata.

        Args:
            name (str): Distribution name.
            version (str): Distribution version.
            direct_url (str | None): Raw direct_url.json content.
        """
        self.metadata = {"Name": name}
        self.version = version
        self._direct_url = direct_url

    def read_text(self, filename: str) -> str | None:
        """Return fake direct URL metadata.

        Args:
            filename (str): Metadata filename.

        Returns:
            str | None: Configured content for direct_url.json.
        """
        return self._direct_url if filename == "direct_url.json" else None


class _EntryPoint:
    """EntryPoint double that records whether provider code was loaded."""

    group = "zhixing.components"

    def __init__(
        self,
        name: str,
        value: str,
        result: Any,
        *,
        distribution: _Distribution | None = None,
    ) -> None:
        """Configure fake metadata and load result.

        Args:
            name (str): Provider ID.
            value (str): Entry Point target string.
            result (Any): Returned value or exception raised by load.
            distribution (_Distribution | None): Installed provenance.
        """
        self.name = name
        self.value = value
        self.dist = distribution or _Distribution("fixture", "1.0.0")
        self.result = result
        self.load_count = 0

    def load(self) -> Any:
        """Return or raise the configured provider result.

        Raises:
            Exception: Configured provider failure.

        Returns:
            Any: Configured provider object.
        """
        self.load_count += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_component_bundle_is_versioned_non_empty_and_immutable() -> None:
    """Validate the bundle protocol and reject duplicate identities."""
    specification = _spec()
    bundle = ComponentBundle((specification,))
    assert bundle.schema_version == "1"
    with pytest.raises(FrozenInstanceError):
        bundle.schema_version = "2"  # type: ignore[misc]
    with pytest.raises(ValueError) as duplicate:
        ComponentBundle((specification, specification))
    assert duplicate.value.code == "component.bundle_identity_duplicate"
    with pytest.raises(ValueError) as empty:
        ComponentBundle(())
    assert empty.value.code == "component.bundle_empty"


def test_enumeration_is_sorted_metadata_only_and_sanitizes_vcs_origin() -> None:
    """Enumerate without import and remove credential-bearing origin URLs."""
    direct_url = json.dumps(
        {
            "url": "https://user:secret@example.test/private.git",
            "vcs_info": {
                "vcs": "git",
                "requested_revision": "main",
                "commit_id": "abcdef",
            },
        }
    )
    second = _EntryPoint("z-provider", "z.module:bundle", object())
    first = _EntryPoint(
        "a-provider",
        "a.module:bundle",
        object(),
        distribution=_Distribution("git-fixture", "2.0.0", direct_url),
    )
    candidates = enumerate_component_plugins(lambda: (second, first))
    assert [item.provider_id for item in candidates] == ["a-provider", "z-provider"]
    assert first.load_count == second.load_count == 0
    payload = json.dumps([item.to_safe_dict() for item in candidates])
    assert "secret" not in payload
    assert "example.test" not in payload
    assert candidates[0].origin.source_kind == "vcs"
    assert candidates[0].origin.commit_id == "abcdef"


def test_missing_and_malformed_origin_metadata_falls_back_safely() -> None:
    """Treat unavailable or malformed direct URL metadata as index origin."""
    entry_point = _EntryPoint(
        "provider",
        "module:bundle",
        object(),
        distribution=_Distribution("fixture", "1.0.0", "{broken"),
    )
    candidate = enumerate_component_plugins(lambda: (entry_point,))[0]
    assert candidate.origin.source_kind == "index"
    assert candidate.origin.distribution == "fixture"


def test_policy_skips_unselected_providers_without_importing_them() -> None:
    """Apply allowlist and denylist before provider code is loaded."""
    bundle = ComponentBundle((_spec(),))
    good = _EntryPoint("good", "good:bundle", bundle)
    skipped = _EntryPoint("skipped", "skipped:bundle", bundle)
    candidates = enumerate_component_plugins(lambda: (skipped, good))
    environment = load_component_plugins(
        candidates,
        allowlist=("good", "skipped"),
        denylist=("skipped",),
    )
    assert environment.catalog.providers() == ("good",)
    assert good.load_count == 1
    assert skipped.load_count == 0
    assert environment.report.skipped_provider_ids == ("skipped",)


def test_duplicate_provider_id_is_rejected_before_import() -> None:
    """Reject ambiguous provider identities without loading either target."""
    bundle = ComponentBundle((_spec(),))
    first = _EntryPoint("duplicate", "first:bundle", bundle)
    second = _EntryPoint("duplicate", "second:bundle", bundle)
    candidates = enumerate_component_plugins(lambda: (first, second))
    with pytest.raises(ComponentDiscoveryError) as captured:
        select_component_plugins(candidates)
    assert captured.value.code == "plugin.provider_duplicate"
    assert first.load_count == second.load_count == 0


def test_bad_provider_is_isolated_and_report_contains_no_exception_message() -> None:
    """Load a good provider when another raises credential-bearing ImportError."""
    good = _EntryPoint("good", "good:bundle", ComponentBundle((_spec(),)))
    bad = _EntryPoint("bad", "bad:bundle", ImportError("token=super-secret"))
    environment = load_component_plugins(
        enumerate_component_plugins(lambda: (bad, good))
    )
    assert environment.catalog.providers() == ("good",)
    assert environment.report.loaded_provider_ids == ("good",)
    assert environment.report.failures[0].provider_id == "bad"
    payload = json.dumps(environment.to_safe_dict())
    assert "super-secret" not in payload
    assert "traceback" not in payload.lower()


def test_catalog_resolves_exact_and_unique_versions_and_rejects_ambiguity() -> None:
    """Implement deterministic exact, unique, missing, and ambiguous resolution."""
    catalog = ComponentCatalog(
        (
            ("first", ComponentBundle((_spec(version="1.0.0"),))),
            ("second", ComponentBundle((_spec(version="2.0.0"),))),
        )
    )
    exact = catalog.resolve(
        GraphComponentRef(
            namespace="example.external",
            name="verifier",
            version="2.0.0",
        )
    )
    assert exact.provider_id == "second"
    with pytest.raises(ComponentCatalogError) as ambiguous:
        catalog.resolve(
            GraphComponentRef(namespace="example.external", name="verifier")
        )
    assert ambiguous.value.code == "component.catalog_version_ambiguous"
    assert ambiguous.value.details["available_versions"] == ["1.0.0", "2.0.0"]
    with pytest.raises(ComponentCatalogError) as unavailable:
        catalog.resolve(
            GraphComponentRef(
                namespace="example.external",
                name="verifier",
                version="3.0.0",
            )
        )
    assert unavailable.value.code == "component.catalog_version_not_found"


def test_catalog_rejects_provider_and_builtin_identity_conflicts() -> None:
    """Prevent external providers from shadowing each other or built-ins."""
    specification = _spec()
    with pytest.raises(ComponentCatalogError) as providers:
        ComponentCatalog(
            (
                ("first", ComponentBundle((specification,))),
                ("second", ComponentBundle((specification,))),
            )
        )
    assert providers.value.code == "component.catalog_identity_conflict"

    built_in_collision = _spec(
        namespace="agent.verifier",
        name="llm_reflect_verifier",
        version="1",
    )
    with pytest.raises(ComponentCatalogError) as built_in:
        ComponentCatalog((("external", ComponentBundle((built_in_collision,))),))
    assert built_in.value.code == "component.catalog_builtin_conflict"

    distinct_version = _spec(
        namespace="agent.verifier",
        name="llm_reflect_verifier",
        version="2.0.0",
    )
    catalog = ComponentCatalog(
        (("external", ComponentBundle((distinct_version,))),)
    )
    assert catalog.available_versions(
        "agent.verifier",
        "llm_reflect_verifier",
    ) == ("2.0.0",)

    class Fallback:
        """Built-in resolver double used for cross-catalog version selection."""

        catalog = BUILTIN_COMPONENT_CATALOG

        def resolve(self, reference: GraphComponentRef, role=None) -> str:
            """Return a marker for an exact built-in resolution.

            Args:
                reference (GraphComponentRef): Built-in component reference.
                role (Any): Optional expected role.

            Returns:
                str: Built-in resolution marker.
            """
            del reference, role
            return "builtin"

    resolver = CatalogComponentResolver(catalog, fallback=Fallback())
    with pytest.raises(ComponentCatalogError) as ambiguous:
        resolver.resolve(
            GraphComponentRef(
                namespace="agent.verifier",
                name="llm_reflect_verifier",
            )
        )
    assert ambiguous.value.code == "component.catalog_version_ambiguous"
    assert resolver.resolve(
        GraphComponentRef(
            namespace="agent.verifier",
            name="llm_reflect_verifier",
            version="1",
        )
    ) == "builtin"


def test_catalog_result_is_independent_of_provider_enumeration_order() -> None:
    """Build identical safe catalogs from reversed provider input order."""
    first = ("a", ComponentBundle((_spec(name="a"),)))
    second = ("b", ComponentBundle((_spec(name="b"),)))
    forward = ComponentCatalog((first, second)).to_safe_dict()
    reverse = ComponentCatalog((second, first)).to_safe_dict()
    assert forward == reverse


def test_catalog_rejects_contract_and_runtime_type_conflicts() -> None:
    """Reject incompatible contract bodies and logical Python type bindings."""
    first = _token_spec(
        name="first",
        implementation=_TokenAComponent,
        runtime_type=_TokenA,
    )
    conflicting_type = _token_spec(
        name="second",
        implementation=_TokenBComponent,
        runtime_type=_TokenB,
        contract_id="fixture.other.token",
    )
    with pytest.raises(ValueError) as runtime_type:
        ComponentCatalog(
            (
                ("first", ComponentBundle((first,))),
                ("second", ComponentBundle((conflicting_type,))),
            )
        )
    assert runtime_type.value.code == "component.runtime_type_conflict"

    conflicting_contract = _token_spec(
        name="third",
        implementation=_TokenAComponent,
        runtime_type=_TokenA,
        input_port="request",
    )
    with pytest.raises(ComponentCatalogError) as contract:
        ComponentCatalog(
            (
                ("first", ComponentBundle((first,))),
                ("third", ComponentBundle((conflicting_contract,))),
            )
        )
    assert contract.value.code == "component.catalog_contract_conflict"


def test_public_imports_do_not_enumerate_or_change_root_exports() -> None:
    """Prove root/component imports remain side-effect free in a subprocess."""
    script = """
import importlib.metadata
def forbidden(*args, **kwargs):
    raise AssertionError('entry point enumeration during import')
importlib.metadata.entry_points = forbidden
import zhixing
before = tuple(zhixing.__all__)
import zhixing.components
assert tuple(zhixing.__all__) == before
assert 'discover_components' not in zhixing.__all__
assert 'openai' not in __import__('sys').modules
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_provider_loading_receives_no_runtime_abilities_or_component_construction() -> None:
    """Keep loading limited to a zero-argument declaration boundary."""

    class ConstructionCounter(_Verifier):
        """Verifier whose constructor exposes accidental eager construction."""

        constructed = 0

        def __init__(self) -> None:
            """Record every concrete component construction."""
            type(self).constructed += 1

    specification = _spec()
    object.__setattr__(specification, "implementation", ConstructionCounter)
    provider = _EntryPoint(
        "declaration-only",
        "fixture:bundle",
        ComponentBundle((specification,)),
    )
    environment = load_component_plugins(
        enumerate_component_plugins(lambda: (provider,))
    )
    assert environment.catalog.providers() == ("declaration-only",)
    assert provider.load_count == 1
    assert ConstructionCounter.constructed == 0
