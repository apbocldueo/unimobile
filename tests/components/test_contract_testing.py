from __future__ import annotations

import json
from typing import Any

import pytest
from pydantic import BaseModel

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionResult,
    ActionType,
    BaseActionExecutor,
    BaseMemory,
    BaseVerifier,
    ComponentBundle,
    ComponentBundleContractResult,
    ComponentCategory,
    ComponentContractResult,
    ComponentDefinitionError,
    ComponentRole,
    ComponentSpec,
    DeviceEffectKind,
    ExecutionStatus,
    MemoryInput,
    MemoryOperation,
    MemoryResult,
    RuntimeContext,
    VerifierInput,
    VerifierResult,
    assert_component_bundle,
    assert_component_contract,
    check_component_bundle,
    check_component_contract,
    component,
)
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


def _contract(role: GraphRole) -> NodeContract:
    """Resolve one core role contract for Contract Test Kit fixtures.

    Args:
        role (GraphRole): Core AgentGraph role.

    Raises:
        AssertionError: The built-in contract is missing.

    Returns:
        NodeContract: Exact built-in role contract.
    """
    contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(contract_ref_for_role(role))
    assert contract is not None
    return contract


def _spec(
    implementation: Any,
    role: ComponentRole,
    *,
    name: str,
    factory: Any = None,
    config_model: type[BaseModel] | None = None,
) -> ComponentSpec:
    """Build one formal core-role ComponentSpec.

    Args:
        implementation (Any): Authoring base subclass.
        role (ComponentRole): Declared core role.
        name (str): Stable test component name.
        factory (Any): Optional explicit constructor.
        config_model (type[BaseModel] | None): Optional configuration schema.

    Raises:
        ComponentDefinitionError: Basic definition fields are invalid.

    Returns:
        ComponentSpec: Formal component definition.
    """
    graph_role = GraphRole(role.value)
    values: dict[str, Any] = {}
    if factory is not None:
        values["factory"] = factory
    if config_model is not None:
        values["config_model"] = config_model
    return ComponentSpec(
        namespace="tests",
        name=name,
        version="1.0.0",
        contract=_contract(graph_role),
        implementation=implementation,
        category=ComponentCategory.CORE_AGENT,
        role=role,
        **values,
    )


class PassingVerifier(BaseVerifier):
    """Deterministic Verifier fixture."""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Return a valid result using only fixture state.

        Args:
            input (VerifierInput): Verification fixture.
            runtime (RuntimeContext): Fake runtime context.

        Raises:
            None.

        Returns:
            VerifierResult: Successful result.
        """
        return VerifierResult(
            is_success=bool(input.task),
            metadata={"run_id": runtime.run_id},
        )


class DynamicWrongVerifier(BaseVerifier):
    """Verifier whose annotation is correct but runtime value is wrong."""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Return an intentionally invalid dynamic result.

        Args:
            input (VerifierInput): Verification fixture.
            runtime (RuntimeContext): Fake runtime context.

        Raises:
            None.

        Returns:
            VerifierResult: Declared type intentionally violated at runtime.
        """
        del input, runtime
        return "wrong"  # type: ignore[return-value]


class IsolatedMemory(BaseMemory):
    """Small stateful Memory implementation for isolation checks."""

    def __init__(self) -> None:
        """Create independent in-memory storage.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.fragments = []

    def invoke(
        self,
        input: MemoryInput,
        runtime: RuntimeContext,
    ) -> MemoryResult:
        """Apply a minimal append/read/reset memory protocol.

        Args:
            input (MemoryInput): Requested memory operation.
            runtime (RuntimeContext): Fake runtime context.

        Raises:
            ValueError: Append omits a fragment.

        Returns:
            MemoryResult: Current operation result.
        """
        del runtime
        if input.operation is MemoryOperation.APPEND:
            if input.fragment is None:
                raise ValueError("append requires fragment")
            self.fragments.append(input.fragment)
        elif input.operation is MemoryOperation.RESET:
            self.fragments.clear()
        return MemoryResult(
            operation=input.operation,
            fragments=tuple(self.fragments),
        )


class FakeActionExecutor(BaseActionExecutor):
    """ActionExecutor that never accesses a physical device."""

    def invoke(
        self,
        input: ActionExecutionInput,
        runtime: RuntimeContext,
    ) -> ActionResult:
        """Return fake execution evidence.

        Args:
            input (ActionExecutionInput): Fake action request.
            runtime (RuntimeContext): Explicit fake runtime.

        Raises:
            None.

        Returns:
            ActionResult: Successful but side-effect-free result.
        """
        assert runtime.device == "fake-device"
        return ActionResult(
            action=input.action,
            status=ExecutionStatus.SUCCESS,
            effect_performed=False,
            effect_kind=DeviceEffectKind.NONE,
        )


def test_valid_verifier_contract_uses_standard_fixture() -> None:
    """Validate definition, construction, isolation, and invocation.

    Args:
        None.

    Raises:
        AssertionError: A valid Verifier fails the public test kit.

    Returns:
        None.
    """
    result = assert_component_contract(
        _spec(
            PassingVerifier,
            ComponentRole.VERIFIER,
            name="passing_verifier",
        )
    )
    assert result.passed
    assert result.checks == (
        "definition",
        "construction",
        "instance_isolation",
        "invocation",
    )


def test_dynamic_output_mismatch_preserves_definition_success() -> None:
    """Separate static definition success from dynamic invocation failure.

    Args:
        None.

    Raises:
        AssertionError: Dynamic output checking is bypassed.

    Returns:
        None.
    """
    result = check_component_contract(
        _spec(
            DynamicWrongVerifier,
            ComponentRole.VERIFIER,
            name="wrong_verifier",
        )
    )
    assert not result.passed
    assert "definition" in result.checks
    assert result.diagnostics[0].phase == "invocation"
    assert result.diagnostics[0].code == "component.invocation_output_mismatch"


def test_action_executor_is_skipped_without_explicit_fake_runtime() -> None:
    """Prevent default Contract Test Kit calls across device boundaries.

    Args:
        None.

    Raises:
        AssertionError: ActionExecutor invocation occurs without authorization.

    Returns:
        None.
    """
    specification = _spec(
        FakeActionExecutor,
        ComponentRole.ACTION_EXECUTOR,
        name="fake_action_executor",
    )
    skipped = check_component_contract(specification)
    assert skipped.passed
    assert skipped.skipped == ("invocation:side_effect_not_authorized",)

    fake_runtime = RuntimeContext(
        run_id="fake-action-runtime",
        device="fake-device",
    )
    executed = assert_component_contract(
        specification,
        allow_side_effects=True,
        runtime=fake_runtime,
        input_value=ActionExecutionInput(Action(ActionType.DONE)),
    )
    assert "invocation" in executed.checks


def test_memory_instances_are_checked_for_state_isolation() -> None:
    """Detect singleton factories and verify independent Memory state.

    Args:
        None.

    Raises:
        AssertionError: Memory state leakage is not detected.

    Returns:
        None.
    """
    isolated = assert_component_contract(
        _spec(
            IsolatedMemory,
            ComponentRole.MEMORY,
            name="isolated_memory",
        )
    )
    assert "memory_state_isolation" in isolated.checks

    singleton = IsolatedMemory()

    def singleton_factory(
        config: dict[str, Any],
        dependencies: dict[str, Any],
    ) -> IsolatedMemory:
        """Return the same instance to simulate an invalid plugin factory.

        Args:
            config (dict[str, Any]): Validated configuration.
            dependencies (dict[str, Any]): Explicit dependencies.

        Raises:
            None.

        Returns:
            IsolatedMemory: Shared singleton.
        """
        del config, dependencies
        return singleton

    leaked = check_component_contract(
        _spec(
            IsolatedMemory,
            ComponentRole.MEMORY,
            name="singleton_memory",
            factory=singleton_factory,
        )
    )
    assert not leaked.passed
    assert leaked.diagnostics[0].code == "component.instance_isolation_failed"


def test_multi_output_shape_and_secret_failures_are_sanitized() -> None:
    """Report stable shape failures and redact constructor exception secrets.

    Args:
        None.

    Raises:
        AssertionError: Unsafe or ambiguous diagnostics are produced.

    Returns:
        None.
    """
    contract = NodeContract(
        ref=NodeContractRef(id="tests.multi_output", version="1.0"),
        ports=(
            ContractPort(
                id="input",
                direction=PortDirection.INPUT,
                data_types=("text",),
                required=True,
            ),
            ContractPort(
                id="left",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
            ContractPort(
                id="right",
                direction=PortDirection.OUTPUT,
                data_types=("text",),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )

    @component(
        namespace="tests",
        name="bad_multi_output",
        contract=contract,
        input_type=str,
        output_type=dict,
    )
    def bad_multi_output(
        input: str,
        runtime: RuntimeContext,
    ) -> dict:
        """Return an intentionally invalid multi-output value.

        Args:
            input (str): Input fixture.
            runtime (RuntimeContext): Fake runtime.

        Raises:
            None.

        Returns:
            dict: Declared mapping intentionally violated at runtime.
        """
        del input, runtime
        return "not-a-mapping"  # type: ignore[return-value]

    shape = check_component_contract(
        bad_multi_output.__zhixing_component_spec__,
        input_value="fixture",
    )
    assert shape.diagnostics[0].code == (
        "component.invocation_output_mapping_required"
    )

    class SecretConfig(BaseModel):
        """Constructor fixture containing one secret-like field."""

        api_key: str

    class ExplodingVerifier(PassingVerifier):
        """Formal Verifier whose constructor raises a secret-bearing message."""

        def __init__(self, api_key: str) -> None:
            """Raise an intentional constructor failure.

            Args:
                api_key (str): Secret fixture.

            Raises:
                RuntimeError: Always, to test redaction.

            Returns:
                None.
            """
            raise RuntimeError(f"api_key={api_key}")

    secret = check_component_contract(
        _spec(
            ExplodingVerifier,
            ComponentRole.VERIFIER,
            name="exploding_verifier",
            config_model=SecretConfig,
        ),
        params={"api_key": "top-secret-value"},
    )
    encoded = json.dumps(secret.to_safe_dict(), sort_keys=True)
    assert not secret.passed
    assert "top-secret-value" not in encoded
    assert "RuntimeError" in encoded


def test_bundle_contract_results_are_sorted_and_do_not_short_circuit() -> None:
    """Aggregate every component result in deterministic identity order.

    Args:
        None.

    Raises:
        AssertionError: A failing component hides a passing peer or ordering varies.

    Returns:
        None.
    """
    bundle = ComponentBundle(
        (
            _spec(
                PassingVerifier,
                ComponentRole.VERIFIER,
                name="z_passing_verifier",
            ),
            _spec(
                DynamicWrongVerifier,
                ComponentRole.VERIFIER,
                name="a_wrong_verifier",
            ),
            _spec(
                DynamicWrongVerifier,
                ComponentRole.VERIFIER,
                name="m_wrong_verifier",
            ),
        )
    )
    result = check_component_bundle(bundle, provider_id="tests-provider")
    assert not result.passed
    assert [item.component_id for item in result.components] == [
        "tests:a_wrong_verifier@1.0.0",
        "tests:m_wrong_verifier@1.0.0",
        "tests:z_passing_verifier@1.0.0",
    ]
    assert not result.components[0].passed
    assert not result.components[1].passed
    assert result.components[2].passed
    assert result.to_safe_dict()["schema_version"] == "1"
    with pytest.raises(AssertionError):
        result.assert_valid()


def test_bundle_contract_supports_controlled_per_component_fixtures() -> None:
    """Authorize one sensitive component without widening the whole bundle.

    Args:
        None.

    Raises:
        AssertionError: Bundle fixtures bypass component safety boundaries.

    Returns:
        None.
    """
    executor = _spec(
        FakeActionExecutor,
        ComponentRole.ACTION_EXECUTOR,
        name="bundle_action_executor",
    )
    verifier = _spec(
        PassingVerifier,
        ComponentRole.VERIFIER,
        name="bundle_verifier",
    )
    bundle = ComponentBundle((executor, verifier))
    skipped = assert_component_bundle(bundle)
    executor_result = next(
        item for item in skipped.components if item.component_id == executor.identifier
    )
    assert executor_result.skipped == (
        "invocation:side_effect_not_authorized",
    )

    executed = assert_component_bundle(
        bundle,
        fixtures={
            executor.identifier: {
                "allow_side_effects": True,
                "runtime": RuntimeContext(
                    run_id="bundle-action-runtime",
                    device="fake-device",
                ),
                "input_value": ActionExecutionInput(Action(ActionType.DONE)),
            }
        },
    )
    executor_result = next(
        item for item in executed.components if item.component_id == executor.identifier
    )
    assert "invocation" in executor_result.checks


def test_bundle_contract_rejects_unknown_fixtures_and_redacts_provider() -> None:
    """Return bounded bundle diagnostics without leaking provider secrets.

    Args:
        None.

    Raises:
        AssertionError: Unknown fixtures are ignored or safe output leaks a secret.

    Returns:
        None.
    """
    bundle = ComponentBundle(
        (
            _spec(
                PassingVerifier,
                ComponentRole.VERIFIER,
                name="bundle_verifier",
            ),
        )
    )
    result = check_component_bundle(
        bundle,
        provider_id="token=provider-secret",
        fixtures={"tests:missing@1.0.0": {}},
    )
    payload = json.dumps(result.to_safe_dict(), sort_keys=True)
    assert not result.passed
    assert result.diagnostics[0].code == "component.bundle_fixture_unknown"
    assert "provider-secret" not in payload
    with pytest.raises(AssertionError):
        assert_component_bundle(
            bundle,
            fixtures={"tests:missing@1.0.0": {}},
        )


def test_contract_diagnostic_redacts_paths_urls_and_bounds_details() -> None:
    """Sanitize exception evidence and bound nested diagnostic details.

    Args:
        None.

    Raises:
        AssertionError: Diagnostic output leaks credentials or local paths.

    Returns:
        None.
    """
    class UnsafeVerifier(PassingVerifier):
        """Verifier fixture whose constructor exposes unsafe diagnostics."""

        def __init__(self) -> None:
            """Raise a definition error containing unsafe diagnostic values.

            Args:
                None.

            Raises:
                ComponentDefinitionError: Always, with unsafe fixture details.

            Returns:
                None.
            """
            raise ComponentDefinitionError(
                "component.unsafe_fixture",
                (
                    "load failed at /Users/alice/private/plugin.py from "
                    "https://alice:hunter2@example.test/plugin"
                ),
                component_id="tests:unsafe_verifier@1.0.0",
                details={
                    "nested": {
                        "items": list(range(75)),
                        "path": "/tmp/private/provider.json",
                    },
                },
            )

    result = check_component_contract(
        _spec(
            UnsafeVerifier,
            ComponentRole.VERIFIER,
            name="unsafe_verifier",
        )
    )
    payload = json.dumps(result.to_safe_dict(), sort_keys=True)

    assert not result.passed
    assert "/Users/alice" not in payload
    assert "/tmp/private" not in payload
    assert "hunter2" not in payload
    assert "<local-path>" in payload
    assert "<25 items omitted>" in payload


def test_contract_result_serialization_bounds_aggregated_failures() -> None:
    """Keep aggregate failure output bounded while preserving failed status.

    Args:
        None.

    Raises:
        AssertionError: Aggregate diagnostics are truncated without accounting.

    Returns:
        None.
    """
    failing = check_component_contract(
        _spec(
            DynamicWrongVerifier,
            ComponentRole.VERIFIER,
            name="bounded_failure",
        )
    )
    repeated_diagnostics = failing.diagnostics * 75
    repeated_components = (
        ComponentContractResult(
            component_id=f"tests:failure-{index}@1.0.0",
            contract=failing.contract,
            diagnostics=repeated_diagnostics,
        )
        for index in range(125)
    )
    aggregate = ComponentBundleContractResult(
        schema_version="1",
        provider_id="tests-provider",
        components=tuple(repeated_components),
        diagnostics=repeated_diagnostics,
    )

    safe = aggregate.to_safe_dict()
    assert not aggregate.passed
    assert len(safe["components"]) == 100
    assert safe["components_truncated"] == 25
    assert len(safe["diagnostics"]) == 50
    assert safe["diagnostics_truncated"] == 25
    assert len(safe["components"][0]["diagnostics"]) == 50
    assert safe["components"][0]["diagnostics_truncated"] == 25
