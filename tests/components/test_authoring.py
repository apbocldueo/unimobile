from __future__ import annotations

import json
import subprocess
import sys
from typing import Any

import pytest
from pydantic import BaseModel, ConfigDict

import zhixing
from zhixing.components import (
    Action,
    ActionType,
    BaseVerifier,
    ComponentCategory,
    ComponentConfigurationError,
    ComponentDependencySlot,
    ComponentDefinitionError,
    ComponentRole,
    ComponentSpec,
    RuntimeContext,
    RuntimeTypeCatalog,
    VerifierInput,
    VerifierResult,
    component,
    construct_component,
    get_component_spec,
    validate_component_spec,
)
from zhixing.core.factory import PluginRegistry
from zhixing.graph import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    ContractPort,
    InvocationAdapterKind,
    NodeContract,
    NodeContractRef,
    PortDirection,
    contract_ref_for_role,
)
from zhixing.graph.enums import GraphRole
from zhixing.graph import GraphComponentRef
from zhixing.runtime import MappingComponentResolver


def _contract(role: GraphRole) -> NodeContract:
    """Resolve one built-in core role contract for authoring tests.

    Args:
        role (GraphRole): Core AgentGraph role.

    Raises:
        AssertionError: The built-in contract is missing.

    Returns:
        NodeContract: Exact built-in contract.
    """
    contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(contract_ref_for_role(role))
    assert contract is not None
    return contract


class AcceptingVerifier(BaseVerifier):
    """Minimal formal Verifier used by authoring tests."""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Return a deterministic verification result.

        Args:
            input (VerifierInput): Verification evidence.
            runtime (RuntimeContext): Isolated run context.

        Raises:
            None.

        Returns:
            VerifierResult: Successful result containing the run ID.
        """
        return VerifierResult(
            True,
            metadata={"run_id": runtime.run_id, "task": input.task},
        )


def _verifier_spec(**overrides: Any) -> ComponentSpec:
    """Build a valid formal Verifier definition with optional overrides.

    Args:
        **overrides (Any): ComponentSpec fields to replace.

    Raises:
        ComponentDefinitionError: An override breaks basic dataclass validation.

    Returns:
        ComponentSpec: Formal Verifier definition.
    """
    values: dict[str, Any] = {
        "namespace": "tests",
        "name": "accepting_verifier",
        "version": "1.0.0",
        "contract": _contract(GraphRole.VERIFIER),
        "implementation": AcceptingVerifier,
        "category": ComponentCategory.CORE_AGENT,
        "role": ComponentRole.VERIFIER,
    }
    values.update(overrides)
    return ComponentSpec(**values)


def test_abstract_role_requires_invoke_implementation() -> None:
    """Reject an incomplete role subclass before runtime binding.

    Args:
        None.

    Raises:
        AssertionError: The ABC can be instantiated without ``invoke``.

    Returns:
        None.
    """

    class IncompleteVerifier(BaseVerifier):
        """Deliberately incomplete formal Verifier."""

    with pytest.raises(TypeError):
        IncompleteVerifier()


def test_component_spec_is_safe_and_does_not_mutate_registry() -> None:
    """Expose static metadata without registration or secret leakage.

    Args:
        None.

    Raises:
        AssertionError: Metadata or registry behavior is unsafe.

    Returns:
        None.
    """
    before = {
        namespace: tuple(sorted(entries))
        for namespace, entries in PluginRegistry._registry.items()
    }
    class UnsafeDefaultConfig(BaseModel):
        """Configuration that intentionally contains an unsafe default."""

        api_key: str = "schema-secret-value"

    specification = _verifier_spec(
        config_model=UnsafeDefaultConfig,
        capabilities={
            "streaming": False,
            "api_key": "should-never-appear",
        }
    )
    validate_component_spec(specification)
    metadata = specification.safe_metadata()
    encoded = json.dumps(metadata, sort_keys=True)
    after = {
        namespace: tuple(sorted(entries))
        for namespace, entries in PluginRegistry._registry.items()
    }
    assert before == after
    assert "should-never-appear" not in encoded
    assert "schema-secret-value" not in encoded
    assert metadata["capabilities"]["api_key"] == "<redacted>"
    assert metadata["contract"]["adapter"] == "core_role"
    assert metadata["contract"]["ports"]
    assert metadata["contract"]["ports"][0]["direction"] in {"input", "output"}
    assert "features" in metadata["contract"]
    assert "implementation" not in metadata
    assert "factory" not in metadata
    assert "AcceptingVerifier" not in repr(specification)
    assert "should-never-appear" not in repr(specification)


def test_dependency_slots_are_immutable_bounded_and_safely_serialized() -> None:
    """Freeze dependency metadata and exclude value-bearing schema hints.

    Args:
        None.

    Raises:
        AssertionError: Slot metadata is mutable, unsafe, or nondeterministic.

    Returns:
        None.
    """
    slot = ComponentDependencySlot(
        name="llm",
        required=True,
        accepted_namespaces=("llm",),
        accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "object",
                    "default": {"secret_ref": "must-not-be-public"},
                }
            },
        },
    )
    specification = _verifier_spec(dependency_slots=(slot,))
    metadata = specification.safe_metadata()
    encoded = json.dumps(metadata, sort_keys=True)
    assert metadata["dependency_slots"][0]["acceptedNamespaces"] == ["llm"]
    assert metadata["dependency_slots"][0]["acceptedCategories"] == [
        "runtime_service"
    ]
    assert "must-not-be-public" not in encoded
    with pytest.raises(TypeError):
        slot.config_schema["properties"]["api_key"] = {"type": "string"}
    with pytest.raises(ComponentDefinitionError) as captured:
        _verifier_spec(dependency_slots=(slot, slot))
    assert captured.value.code == "component.dependency_slot_duplicate"


def test_dependency_slot_rejects_invalid_and_unbounded_metadata() -> None:
    """Reject malformed identities, non-JSON values, and oversized schemas.

    Args:
        None.

    Raises:
        AssertionError: Invalid dependency metadata is accepted.

    Returns:
        None.
    """
    with pytest.raises(ComponentDefinitionError):
        ComponentDependencySlot(name="not a slot")
    with pytest.raises(ComponentDefinitionError) as captured:
        ComponentDependencySlot(name="llm", config_schema={"type": {"object"}})
    assert captured.value.code == "component.dependency_slot_schema_invalid"
    with pytest.raises(ComponentDefinitionError) as captured:
        ComponentDependencySlot(
            name="llm",
            config_schema={"description": "x" * (33 * 1024)},
        )
    assert captured.value.code == "component.dependency_slot_schema_too_large"


def test_decorated_function_keeps_callable_and_avoids_global_registration() -> None:
    """Create a lightweight function component without import side effects.

    Args:
        None.

    Raises:
        AssertionError: Decoration changes callable or registry semantics.

    Returns:
        None.
    """
    before = {
        namespace: tuple(sorted(entries))
        for namespace, entries in PluginRegistry._registry.items()
    }

    @component(
        namespace="tests",
        name="function_verifier",
        role=ComponentRole.VERIFIER,
    )
    def verify(
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Verify one fixture without external services.

        Args:
            input (VerifierInput): Verification evidence.
            runtime (RuntimeContext): Run context.

        Raises:
            None.

        Returns:
            VerifierResult: Successful fixture result.
        """
        return VerifierResult(bool(input.task), metadata={"run": runtime.run_id})

    assert verify(
        VerifierInput(
            task="fixture",
            screenshot_before="before",
            screenshot_after="after",
            action=Action(ActionType.DONE),
        ),
        RuntimeContext(run_id="decorator-test"),
    ).is_success
    assert get_component_spec(verify) is not None
    assert before == {
        namespace: tuple(sorted(entries))
        for namespace, entries in PluginRegistry._registry.items()
    }


def test_formal_definition_requires_base_or_decorator() -> None:
    """Reject a manually declared duck-typed formal component.

    Args:
        None.

    Raises:
        AssertionError: A loose object enters the strict formal path.

    Returns:
        None.
    """

    class LooseVerifier:
        """Duck-typed object without an authoring marker."""

        def invoke(
            self,
            input: VerifierInput,
            runtime: RuntimeContext,
        ) -> VerifierResult:
            """Return a result while intentionally skipping formal authoring.

            Args:
                input (VerifierInput): Verification evidence.
                runtime (RuntimeContext): Run context.

            Raises:
                None.

            Returns:
                VerifierResult: Successful result.
            """
            del input, runtime
            return VerifierResult(True)

    specification = _verifier_spec(implementation=LooseVerifier)
    with pytest.raises(
        ComponentDefinitionError,
        match="BaseComponent or use @component",
    ) as captured:
        validate_component_spec(specification)
    assert captured.value.code == "component.authoring_model_invalid"


def test_decorator_rejects_invalid_signature_and_cleans_marker() -> None:
    """Reject an incorrectly annotated decorated function.

    Args:
        None.

    Raises:
        AssertionError: Invalid definition retains a formal marker.

    Returns:
        None.
    """

    def invalid(input: str, runtime: RuntimeContext) -> VerifierResult:
        """Return a result for an intentionally wrong input annotation.

        Args:
            input (str): Incorrect input.
            runtime (RuntimeContext): Run context.

        Raises:
            None.

        Returns:
            VerifierResult: Fixture result.
        """
        del input, runtime
        return VerifierResult(True)

    with pytest.raises(ComponentDefinitionError) as captured:
        component(
            namespace="tests",
            name="invalid_signature",
            role=ComponentRole.VERIFIER,
        )(invalid)
    assert captured.value.code == "component.input_annotation_mismatch"
    assert get_component_spec(invalid) is None


def test_config_validation_precedes_construction() -> None:
    """Normalize valid parameters and reject invalid fields before construction.

    Args:
        None.

    Raises:
        AssertionError: Constructor runs for invalid configuration.

    Returns:
        None.
    """

    class VerifierConfig(BaseModel):
        """Strict configuration for the fixture component."""

        model_config = ConfigDict(extra="forbid")
        threshold: float = 0.5

    class ConfiguredVerifier(BaseVerifier):
        """Formal component that records constructor calls."""

        calls = 0

        def __init__(self, threshold: float) -> None:
            """Store one normalized threshold.

            Args:
                threshold (float): Acceptance threshold.

            Raises:
                None.

            Returns:
                None.
            """
            type(self).calls += 1
            self.threshold = threshold

        def invoke(
            self,
            input: VerifierInput,
            runtime: RuntimeContext,
        ) -> VerifierResult:
            """Return whether the threshold is within the fixture range.

            Args:
                input (VerifierInput): Verification evidence.
                runtime (RuntimeContext): Run context.

            Raises:
                None.

            Returns:
                VerifierResult: Deterministic result.
            """
            del input, runtime
            return VerifierResult(self.threshold <= 1.0)

    specification = _verifier_spec(
        name="configured_verifier",
        implementation=ConfiguredVerifier,
        config_model=VerifierConfig,
    )
    instance = construct_component(specification, {"threshold": 0.75})
    assert instance.threshold == 0.75
    assert ConfiguredVerifier.calls == 1
    with pytest.raises(ComponentConfigurationError) as captured:
        construct_component(specification, {"unknown": "secret-token-value"})
    assert captured.value.code == "component.config_invalid"
    assert ConfiguredVerifier.calls == 1
    assert "secret-token-value" not in json.dumps(captured.value.to_safe_dict())


def test_mapping_resolver_preserves_formal_definition_identity() -> None:
    """Keep ComponentSpec attached after explicit resolver construction.

    Args:
        None.

    Raises:
        AssertionError: Resolver construction loses strict formal metadata.

    Returns:
        None.
    """
    specification = _verifier_spec()
    resolver = MappingComponentResolver(
        {("tests", "accepting_verifier"): specification}
    )
    instance = resolver.resolve(
        GraphComponentRef(
            namespace="tests",
            name="accepting_verifier",
        ),
        GraphRole.VERIFIER,
    )
    assert get_component_spec(instance) is specification


def test_version_and_custom_runtime_type_bindings_are_strict() -> None:
    """Reject incompatible versions, missing types, and conflicting type IDs.

    Args:
        None.

    Raises:
        AssertionError: Definition/type preflight accepts invalid declarations.

    Returns:
        None.
    """
    incompatible = _verifier_spec(zhixing_compatibility=">=99.0")
    with pytest.raises(ComponentDefinitionError) as captured:
        validate_component_spec(incompatible)
    assert captured.value.code == "component.version_incompatible"

    custom_contract = NodeContract(
        ref=NodeContractRef(id="tests.custom", version="1.0"),
        ports=(
            ContractPort(
                id="input",
                direction=PortDirection.INPUT,
                data_types=("tests.payload",),
                required=True,
            ),
            ContractPort(
                id="result",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )

    def custom(input: dict, runtime: RuntimeContext) -> str:
        """Read one custom payload.

        Args:
            input (dict): Custom payload.
            runtime (RuntimeContext): Run context.

        Raises:
            None.

        Returns:
            str: Payload value.
        """
        del runtime
        return str(input["value"])

    with pytest.raises(ComponentDefinitionError) as captured:
        component(
            namespace="tests",
            name="missing_custom_type",
            contract=custom_contract,
            input_type=dict,
            output_type=str,
        )(custom)
    assert captured.value.code == "component.runtime_type_unknown"
    assert get_component_spec(custom) is None


def test_runtime_type_catalog_rejects_conflicting_bindings() -> None:
    """Reject nondeterministic duplicate logical type bindings.

    Args:
        None.

    Raises:
        AssertionError: Conflicting catalogs merge successfully.

    Returns:
        None.
    """
    with pytest.raises(ComponentDefinitionError) as captured:
        RuntimeTypeCatalog({"tests.payload": dict}).merge(
            RuntimeTypeCatalog({"tests.payload": list})
        )
    assert captured.value.code == "component.runtime_type_conflict"


def test_root_public_surface_and_import_safety_remain_unchanged() -> None:
    """Keep authoring API scoped to ``zhixing.components`` and import-safe.

    Args:
        None.

    Raises:
        AssertionError: Root exports or import isolation regresses.

    Returns:
        None.
    """
    assert "ComponentSpec" not in zhixing.__all__
    script = """
import json
import sys
import zhixing.components
forbidden = [
    "openai",
    "cv2",
    "torch",
    "zhixing.devices.android",
    "zhixing.devices.harmony",
]
print(json.dumps([name for name in forbidden if name in sys.modules]))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert json.loads(completed.stdout) == []
