"""Side-effect-safe contract checks for third-party ZhiXing components."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from zhixing.core.agent.protocol import (
    Action,
    ActionType,
    FragmentType,
    MemoryFragment,
    PerceptionResult,
    PlanInput,
    PlanResult,
    VerifierInput,
)
from zhixing.graph import PortDirection

from .authoring import (
    ComponentSpec,
    construct_component,
    validate_component_spec,
)
from .errors import ComponentDefinitionError
from .models import (
    ActionExecutionInput,
    DeviceObservation,
    MemoryInput,
    MemoryOperation,
    MemoryResult,
    ReasoningInput,
    RuntimeContext,
    TaskInput,
    redact_mapping,
)
from .plugins import ComponentBundle
from .protocols import ComponentRole


_UNSET = object()
_SENSITIVE_ROLES = {
    ComponentRole.ACTION_EXECUTOR,
    ComponentRole.DEVICE,
    ComponentRole.LLM,
}
_MAX_RESULT_COMPONENTS = 100
_MAX_RESULT_DIAGNOSTICS = 50


@dataclass(frozen=True)
class ContractDiagnostic:
    """One stable and sanitized Contract Test Kit failure."""

    phase: str
    code: str
    message: str
    component_id: str
    contract: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize one diagnostic without implementation or secret state.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Redacted diagnostic fields.
        """
        return redact_mapping(
            {
                "phase": self.phase,
                "code": self.code,
                "message": self.message,
                "component_id": self.component_id,
                "contract": self.contract,
                "details": self.details,
            }
        )


@dataclass(frozen=True)
class ComponentContractResult:
    """Structured outcome from one component contract test run."""

    component_id: str
    contract: str
    checks: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    diagnostics: tuple[ContractDiagnostic, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether every executed check passed.

        Args:
            None.

        Raises:
            None.

        Returns:
            bool: True when no diagnostic was produced.
        """
        return not self.diagnostics

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize a bounded result suitable for CI output.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible test summary.
        """
        diagnostics = self.diagnostics[:_MAX_RESULT_DIAGNOSTICS]
        checks = self.checks[:_MAX_RESULT_DIAGNOSTICS]
        skipped = self.skipped[:_MAX_RESULT_DIAGNOSTICS]
        return {
            "passed": self.passed,
            "component_id": redact_mapping(
                {"value": self.component_id}
            )["value"],
            "contract": redact_mapping({"value": self.contract})["value"],
            "checks": redact_mapping({"values": checks})["values"],
            "skipped": redact_mapping({"values": skipped})["values"],
            "diagnostics": [
                diagnostic.to_safe_dict() for diagnostic in diagnostics
            ],
            "checks_truncated": len(self.checks) - len(checks),
            "skipped_truncated": len(self.skipped) - len(skipped),
            "diagnostics_truncated": len(self.diagnostics) - len(diagnostics),
        }

    def assert_valid(self) -> None:
        """Raise a pytest-friendly assertion when any check failed.

        Args:
            None.

        Raises:
            AssertionError: At least one contract diagnostic exists.

        Returns:
            None.
        """
        if not self.passed:
            raise AssertionError(
                json.dumps(
                    self.to_safe_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )


@dataclass(frozen=True)
class ComponentBundleContractResult:
    """Structured aggregate outcome for one provider ComponentBundle."""

    schema_version: str
    provider_id: str = ""
    components: tuple[ComponentContractResult, ...] = ()
    diagnostics: tuple[ContractDiagnostic, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether bundle-level and component-level checks passed.

        Args:
            None.

        Raises:
            None.

        Returns:
            bool: True when no bundle or component diagnostic exists.
        """
        return not self.diagnostics and all(
            component.passed for component in self.components
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize a deterministic provider health result.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Redacted JSON-compatible bundle summary.
        """
        identity = redact_mapping({"provider_id": self.provider_id})["provider_id"]
        components = self.components[:_MAX_RESULT_COMPONENTS]
        diagnostics = self.diagnostics[:_MAX_RESULT_DIAGNOSTICS]
        return {
            "passed": self.passed,
            "provider_id": identity,
            "schema_version": redact_mapping(
                {"value": str(self.schema_version)[:32]}
            )["value"],
            "components": [
                component.to_safe_dict() for component in components
            ],
            "diagnostics": [
                diagnostic.to_safe_dict() for diagnostic in diagnostics
            ],
            "components_truncated": len(self.components) - len(components),
            "diagnostics_truncated": len(self.diagnostics) - len(diagnostics),
        }

    def assert_valid(self) -> None:
        """Raise a pytest-friendly assertion when aggregate checks fail.

        Args:
            None.

        Raises:
            AssertionError: A bundle-level or component-level check failed.

        Returns:
            None.
        """
        if not self.passed:
            raise AssertionError(
                json.dumps(
                    self.to_safe_dict(),
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )


def standard_component_input(role: ComponentRole | str) -> Any:
    """Build the minimal side-effect-free input for one core role.

    Args:
        role (ComponentRole | str): Core component role.

    Raises:
        LookupError: No standard fixture exists for the selected role.

    Returns:
        Any: Minimal public DTO accepted by the role.
    """
    selected = ComponentRole(role)
    observation = DeviceObservation(
        screenshot_path="fixture://screen.png",
        width=1080,
        height=1920,
        platform="fake",
        device_id="fake-device",
    )
    action = Action(ActionType.DONE)
    fixtures: dict[ComponentRole, Any] = {
        ComponentRole.PERCEPTION: observation,
        ComponentRole.PLANNER: PlanInput(task="contract fixture"),
        ComponentRole.REASONING: ReasoningInput(
            task=TaskInput("contract fixture"),
            plan=PlanResult(content=""),
            perception=PerceptionResult(
                mode="fixture",
                original_screenshot_path=observation.screenshot_path,
            ),
        ),
        ComponentRole.MEMORY: MemoryInput(MemoryOperation.READ),
        ComponentRole.ACTION_EXECUTOR: ActionExecutionInput(
            action=action,
            observation=observation,
        ),
        ComponentRole.VERIFIER: VerifierInput(
            task="contract fixture",
            screenshot_before="fixture://before.png",
            screenshot_after="fixture://after.png",
            action=action,
        ),
    }
    if selected not in fixtures:
        raise LookupError(
            f"No standard input fixture exists for role {selected.value!r}"
        )
    return fixtures[selected]


def fake_runtime_context() -> RuntimeContext:
    """Create a runtime context that cannot reach a model or physical device.

    Args:
        None.

    Raises:
        None.

    Returns:
        RuntimeContext: Isolated context with no live services.
    """
    return RuntimeContext(
        run_id="component-contract-fixture",
        max_steps=3,
        metadata={"fixture": True},
    )


def _diagnostic(
    spec: ComponentSpec,
    phase: str,
    error: Exception,
    *,
    code: str,
) -> ContractDiagnostic:
    """Convert one exception into a stable sanitized diagnostic.

    Args:
        spec (ComponentSpec): Component under test.
        phase (str): Contract test phase.
        error (Exception): Captured failure.
        code (str): Fallback stable error code.

    Raises:
        None.

    Returns:
        ContractDiagnostic: Safe diagnostic without exception repr.
    """
    if isinstance(error, ComponentDefinitionError):
        code = error.code
        message = str(error)
        details = dict(error.details)
    else:
        name = type(error).__name__
        message = f"Contract check failed ({name})"
        details = {"error_type": name}
    return ContractDiagnostic(
        phase=phase,
        code=code,
        message=message,
        component_id=spec.identifier,
        contract=f"{spec.contract.ref.id}@{spec.contract.ref.version}",
        details=details,
    )


def _validate_invocation_output(spec: ComponentSpec, output: Any) -> None:
    """Validate an actual result against declared Python and port shapes.

    Args:
        spec (ComponentSpec): Formal component definition.
        output (Any): Actual invocation result.

    Raises:
        ComponentDefinitionError: Output type or multi-port shape is invalid.

    Returns:
        None.
    """
    output_ports = tuple(
        port
        for port in spec.contract.ports
        if port.direction is PortDirection.OUTPUT
    )
    if len(output_ports) > 1:
        if not isinstance(output, Mapping):
            raise ComponentDefinitionError(
                "component.invocation_output_mapping_required",
                "Multi-output contract requires a mapping result",
                component_id=spec.identifier,
            )
        unknown = sorted(set(output) - {port.id for port in output_ports})
        if unknown:
            raise ComponentDefinitionError(
                "component.invocation_output_port_unknown",
                "Invocation returned undeclared output ports",
                component_id=spec.identifier,
                details={"ports": unknown},
            )
        return
    expected = spec.output_type or getattr(
        spec.implementation,
        "output_type",
        None,
    )
    if expected is None and spec.role is not None:
        from .protocols import get_role_descriptor

        expected = get_role_descriptor(spec.role).output_type
    if expected is not None and not isinstance(output, expected):
        raise ComponentDefinitionError(
            "component.invocation_output_mismatch",
            f"Invocation result must be {expected.__name__}",
            component_id=spec.identifier,
            details={"actual_type": type(output).__name__},
        )


def _check_memory_isolation(
    spec: ComponentSpec,
    first: Any,
    second: Any,
) -> None:
    """Check that two Memory instances do not share appended fragments.

    Args:
        spec (ComponentSpec): Memory component definition.
        first (Any): First constructed Memory instance.
        second (Any): Second constructed Memory instance.

    Raises:
        ComponentDefinitionError: State leaks between run-scoped instances.

    Returns:
        None.
    """
    fragment = MemoryFragment(
        role="user",
        type=FragmentType.TEXT,
        content="contract-isolation-marker",
    )
    first.invoke(
        MemoryInput(MemoryOperation.APPEND, fragment=fragment),
        fake_runtime_context(),
    )
    observed = second.invoke(
        MemoryInput(MemoryOperation.READ),
        fake_runtime_context(),
    )
    if not isinstance(observed, MemoryResult):
        raise ComponentDefinitionError(
            "component.invocation_output_mismatch",
            "Memory read must return MemoryResult",
            component_id=spec.identifier,
        )
    if fragment in observed.fragments:
        raise ComponentDefinitionError(
            "component.instance_state_leak",
            "Memory state leaked between independently constructed instances",
            component_id=spec.identifier,
        )


def check_component_contract(
    spec: ComponentSpec,
    *,
    params: Mapping[str, Any] | None = None,
    dependencies: Mapping[str, Any] | None = None,
    input_value: Any = _UNSET,
    runtime: RuntimeContext | None = None,
    invoke: bool = True,
    allow_side_effects: bool = False,
    check_isolation: bool = True,
) -> ComponentContractResult:
    """Run definition, construction, invocation, and isolation checks.

    Args:
        spec (ComponentSpec): Formal third-party component definition.
        params (Mapping[str, Any] | None): Configuration fixture.
        dependencies (Mapping[str, Any] | None): Explicit fake dependencies.
        input_value (Any): Invocation fixture or the standard role fixture.
        runtime (RuntimeContext | None): Explicit fake runtime fixture.
        invoke (bool): Whether to attempt an invocation check.
        allow_side_effects (bool): Explicitly authorize a controlled fake call.
        check_isolation (bool): Construct two run-scoped instances.

    Raises:
        None.

    Returns:
        ComponentContractResult: Structured, safe result for pytest or CI.
    """
    checks: list[str] = []
    skipped: list[str] = []
    diagnostics: list[ContractDiagnostic] = []
    try:
        validate_component_spec(spec)
        checks.append("definition")
    except Exception as error:
        diagnostics.append(
            _diagnostic(
                spec,
                "definition",
                error,
                code="component.definition_failed",
            )
        )
        return ComponentContractResult(
            spec.identifier,
            f"{spec.contract.ref.id}@{spec.contract.ref.version}",
            tuple(checks),
            tuple(skipped),
            tuple(diagnostics),
        )
    try:
        first = construct_component(
            spec,
            params,
            dependencies=dependencies,
        )
        checks.append("construction")
        second = None
        if check_isolation:
            second = construct_component(
                spec,
                params,
                dependencies=dependencies,
            )
            if first is second:
                raise ComponentDefinitionError(
                    "component.instance_isolation_failed",
                    "Component factory returned the same instance twice",
                    component_id=spec.identifier,
                )
            checks.append("instance_isolation")
            if spec.role is ComponentRole.MEMORY:
                _check_memory_isolation(spec, first, second)
                checks.append("memory_state_isolation")
    except Exception as error:
        diagnostics.append(
            _diagnostic(
                spec,
                "construction",
                error,
                code="component.construction_failed",
            )
        )
        return ComponentContractResult(
            spec.identifier,
            f"{spec.contract.ref.id}@{spec.contract.ref.version}",
            tuple(checks),
            tuple(skipped),
            tuple(diagnostics),
        )
    selected_role = spec.role
    if not invoke:
        skipped.append("invocation:disabled")
    elif selected_role in _SENSITIVE_ROLES and not allow_side_effects:
        skipped.append("invocation:side_effect_not_authorized")
    else:
        candidate_input = input_value
        if candidate_input is _UNSET:
            try:
                candidate_input = standard_component_input(selected_role)
            except (LookupError, ValueError):
                skipped.append("invocation:fixture_required")
        if candidate_input is not _UNSET:
            if selected_role in _SENSITIVE_ROLES and runtime is None:
                skipped.append("invocation:explicit_fake_runtime_required")
            else:
                try:
                    output = first.invoke(
                        candidate_input,
                        runtime or fake_runtime_context(),
                    )
                    _validate_invocation_output(spec, output)
                    checks.append("invocation")
                except Exception as error:
                    diagnostics.append(
                        _diagnostic(
                            spec,
                            "invocation",
                            error,
                            code="component.invocation_failed",
                        )
                    )
    return ComponentContractResult(
        spec.identifier,
        f"{spec.contract.ref.id}@{spec.contract.ref.version}",
        tuple(checks),
        tuple(skipped),
        tuple(diagnostics),
    )


def assert_component_contract(
    spec: ComponentSpec,
    **fixtures: Any,
) -> ComponentContractResult:
    """Run the Contract Test Kit and assert that every check passed.

    Args:
        spec (ComponentSpec): Formal component definition.
        **fixtures (Any): Keyword fixtures accepted by ``check_component_contract``.

    Raises:
        AssertionError: Any executed contract check fails.

    Returns:
        ComponentContractResult: Passing structured result.
    """
    result = check_component_contract(spec, **fixtures)
    result.assert_valid()
    return result


def check_component_bundle(
    bundle: ComponentBundle,
    *,
    provider_id: str = "",
    fixtures: Mapping[str, Mapping[str, Any]] | None = None,
) -> ComponentBundleContractResult:
    """Run deterministic Contract Test Kit checks for every bundle component.

    Args:
        bundle (ComponentBundle): Valid provider declaration to inspect.
        provider_id (str): Optional installed provider identity for diagnostics.
        fixtures (Mapping[str, Mapping[str, Any]] | None): Per-component
            keyword arguments forwarded to ``check_component_contract``.

    Raises:
        None.

    Returns:
        ComponentBundleContractResult: Aggregate result without short-circuiting.
    """
    component_fixtures = dict(fixtures or {})
    known_identities = {
        specification.identifier for specification in bundle.components
    }
    bundle_diagnostics = [
        ContractDiagnostic(
            phase="bundle",
            code="component.bundle_fixture_unknown",
            message="A bundle fixture targets an unknown component identity.",
            component_id=identity,
            contract="",
        )
        for identity in sorted(set(component_fixtures) - known_identities)
    ]
    results: list[ComponentContractResult] = []
    for specification in sorted(
        bundle.components,
        key=lambda item: item.identifier,
    ):
        options = component_fixtures.get(specification.identifier, {})
        if not isinstance(options, Mapping):
            results.append(
                ComponentContractResult(
                    component_id=specification.identifier,
                    contract=(
                        f"{specification.contract.ref.id}@"
                        f"{specification.contract.ref.version}"
                    ),
                    diagnostics=(
                        ContractDiagnostic(
                            phase="bundle",
                            code="component.bundle_fixture_invalid",
                            message=(
                                "Per-component bundle fixtures must be mappings."
                            ),
                            component_id=specification.identifier,
                            contract=(
                                f"{specification.contract.ref.id}@"
                                f"{specification.contract.ref.version}"
                            ),
                        ),
                    ),
                )
            )
            continue
        try:
            result = check_component_contract(
                specification,
                **dict(options),
            )
        except Exception as error:
            result = ComponentContractResult(
                component_id=specification.identifier,
                contract=(
                    f"{specification.contract.ref.id}@"
                    f"{specification.contract.ref.version}"
                ),
                diagnostics=(
                    _diagnostic(
                        specification,
                        "bundle",
                        error,
                        code="component.bundle_fixture_failed",
                    ),
                ),
            )
        results.append(result)
    return ComponentBundleContractResult(
        schema_version=bundle.schema_version,
        provider_id=str(provider_id)[:128],
        components=tuple(results),
        diagnostics=tuple(bundle_diagnostics),
    )


def assert_component_bundle(
    bundle: ComponentBundle,
    *,
    provider_id: str = "",
    fixtures: Mapping[str, Mapping[str, Any]] | None = None,
) -> ComponentBundleContractResult:
    """Run aggregate bundle checks and assert that every result is valid.

    Args:
        bundle (ComponentBundle): Valid provider declaration to inspect.
        provider_id (str): Optional installed provider identity for diagnostics.
        fixtures (Mapping[str, Mapping[str, Any]] | None): Per-component
            keyword arguments for controlled Contract Test Kit fixtures.

    Raises:
        AssertionError: A bundle-level or component-level check failed.

    Returns:
        ComponentBundleContractResult: Passing aggregate result.
    """
    result = check_component_bundle(
        bundle,
        provider_id=provider_id,
        fixtures=fixtures,
    )
    result.assert_valid()
    return result


__all__ = [
    "ComponentBundleContractResult",
    "ComponentContractResult",
    "ContractDiagnostic",
    "assert_component_bundle",
    "assert_component_contract",
    "check_component_bundle",
    "check_component_contract",
    "fake_runtime_context",
    "standard_component_input",
]
