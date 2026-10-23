"""Strict, import-safe authoring API for reusable ZhiXing components."""

from __future__ import annotations

import inspect
import json
import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, ClassVar, Generic, TypeVar, get_type_hints

from pydantic import BaseModel, ConfigDict, ValidationError

from zhixing.core.agent.protocol import (
    Action,
    PerceptionResult,
    PlanInput,
    PlanResult,
    VerifierInput,
    VerifierResult,
)
from zhixing.graph.contracts import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    ContractPort,
    InvocationAdapterKind,
    NodeContract,
    NodeContractRef,
    SideEffectKind,
    contract_ref_for_role,
)
from zhixing.graph.enums import GraphRole, PortDirection

from .errors import ComponentConfigurationError, ComponentDefinitionError
from .models import (
    ActionExecutionInput,
    ActionResult,
    BenchmarkInitInput,
    BenchmarkInitResult,
    DeviceObservation,
    DeviceRequest,
    DeviceResult,
    EvaluationInput,
    EvaluationResult,
    EvaluationResultV2,
    GroundingInput,
    GroundingResult,
    LLMInput,
    LLMResult,
    MemoryInput,
    MemoryResult,
    ObservationRequest,
    ReasoningInput,
    RunResult,
    RuntimeContext,
    TaskInput,
)
from .protocols import ComponentRole, get_role_descriptor


InputT = TypeVar("InputT")
OutputT = TypeVar("OutputT")
ComponentTargetT = TypeVar("ComponentTargetT")
RuntimeType = type[Any] | tuple[type[Any], ...]
ComponentFactory = Callable[[Mapping[str, Any], Mapping[str, Any]], Any]

_IDENTIFIER = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9]+){0,3}(?:[-+][A-Za-z0-9_.-]+)?$")
_FRAMEWORK_API_VERSION = "0.1.0"
_MAX_DEPENDENCY_SLOTS = 32
_MAX_DEPENDENCY_SCHEMA_BYTES = 32 * 1024


def _freeze_json_metadata(value: Any) -> Any:
    """Recursively freeze previously validated JSON-compatible metadata.

    Args:
        value: JSON-compatible metadata value.

    Raises:
        None.

    Returns:
        Any: Immutable mapping/tuple form of the value.
    """
    if isinstance(value, Mapping):
        return MappingProxyType(
            {str(key): _freeze_json_metadata(item) for key, item in value.items()}
        )
    if isinstance(value, list):
        return tuple(_freeze_json_metadata(item) for item in value)
    return value


def _thaw_json_metadata(value: Any) -> Any:
    """Return a detached JSON-compatible copy of frozen metadata.

    Args:
        value: Frozen JSON metadata value.

    Raises:
        None.

    Returns:
        Any: Mutable dictionary/list form safe for serialization.
    """
    if isinstance(value, Mapping):
        return {str(key): _thaw_json_metadata(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json_metadata(item) for item in value]
    return value


def _strip_schema_value_examples(value: Any) -> Any:
    """Remove value-bearing JSON-Schema hints from public dependency metadata.

    Args:
        value: JSON-compatible schema fragment.

    Raises:
        None.

    Returns:
        Any: Detached schema without defaults or example values.
    """
    if isinstance(value, Mapping):
        return {
            str(key): _strip_schema_value_examples(item)
            for key, item in value.items()
            if key not in {"default", "example", "examples"}
        }
    if isinstance(value, list):
        return [_strip_schema_value_examples(item) for item in value]
    return value


class ComponentCategory(str, Enum):
    """Architectural category of one public component definition."""

    CORE_AGENT = "core_agent"
    EXTENSION = "extension"
    RUNTIME_SERVICE = "runtime_service"
    BENCHMARK = "benchmark"


class EmptyComponentConfig(BaseModel):
    """Strict empty configuration used by parameter-free components."""

    model_config = ConfigDict(extra="forbid")


@dataclass(frozen=True)
class ComponentDependencySlot:
    """Describe one declarative, metadata-only component dependency slot."""

    name: str
    required: bool = False
    accepted_namespaces: tuple[str, ...] = ()
    accepted_categories: tuple[ComponentCategory, ...] = ()
    config_schema: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and freeze safe authoring metadata.

        Args:
            None.

        Raises:
            ComponentDefinitionError: Identity, constraints, or JSON Schema are
                invalid, unsafe, or unbounded.

        Returns:
            None.
        """
        if not _IDENTIFIER.fullmatch(self.name):
            raise ComponentDefinitionError(
                "component.dependency_slot_name_invalid",
                "Dependency slot name must be a stable identifier",
            )
        namespaces = tuple(self.accepted_namespaces)
        if len(namespaces) != len(set(namespaces)) or any(
            not _IDENTIFIER.fullmatch(item) for item in namespaces
        ):
            raise ComponentDefinitionError(
                "component.dependency_slot_namespace_invalid",
                "Dependency slot namespaces must be unique stable identifiers",
                details={"slot": self.name},
            )
        try:
            categories = tuple(ComponentCategory(item) for item in self.accepted_categories)
        except ValueError as error:
            raise ComponentDefinitionError(
                "component.dependency_slot_category_invalid",
                "Dependency slot category is unsupported",
                details={"slot": self.name},
            ) from error
        if len(categories) != len(set(categories)):
            raise ComponentDefinitionError(
                "component.dependency_slot_category_invalid",
                "Dependency slot categories must be unique",
                details={"slot": self.name},
            )
        schema = _strip_schema_value_examples(deepcopy(dict(self.config_schema)))
        try:
            encoded = json.dumps(
                schema,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ComponentDefinitionError(
                "component.dependency_slot_schema_invalid",
                "Dependency slot schema must be finite JSON metadata",
                details={"slot": self.name},
            ) from error
        if len(encoded) > _MAX_DEPENDENCY_SCHEMA_BYTES:
            raise ComponentDefinitionError(
                "component.dependency_slot_schema_too_large",
                "Dependency slot schema exceeds the size limit",
                details={"slot": self.name},
            )
        object.__setattr__(self, "accepted_namespaces", namespaces)
        object.__setattr__(self, "accepted_categories", categories)
        object.__setattr__(self, "config_schema", _freeze_json_metadata(schema))

    def to_safe_dict(self) -> dict[str, Any]:
        """Return deterministic JSON-compatible authoring metadata.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Detached safe dependency-slot metadata.
        """
        return {
            "name": self.name,
            "required": self.required,
            "acceptedNamespaces": list(self.accepted_namespaces),
            "acceptedCategories": [item.value for item in self.accepted_categories],
            "configSchema": _thaw_json_metadata(self.config_schema),
        }


@dataclass(frozen=True)
class RuntimeTypeCatalog:
    """Immutable mapping from logical contract IDs to Python runtime types."""

    bindings: Mapping[str, RuntimeType] = field(default_factory=dict)
    strict: bool = True

    def __post_init__(self) -> None:
        """Validate and freeze logical runtime type bindings.

        Args:
            None.

        Raises:
            ComponentDefinitionError: A logical ID or runtime type is invalid.

        Returns:
            None.
        """
        normalized: dict[str, RuntimeType] = {}
        for logical_id, runtime_type in self.bindings.items():
            if not isinstance(logical_id, str) or not logical_id.strip():
                raise ComponentDefinitionError(
                    "component.runtime_type_id_invalid",
                    "Runtime type identifiers must be non-empty strings",
                )
            types = runtime_type if isinstance(runtime_type, tuple) else (runtime_type,)
            if not types or any(not isinstance(item, type) for item in types):
                raise ComponentDefinitionError(
                    "component.runtime_type_invalid",
                    f"Runtime type binding {logical_id!r} must contain Python types",
                    details={"logical_type": logical_id},
                )
            normalized[logical_id] = runtime_type
        object.__setattr__(self, "bindings", MappingProxyType(normalized))

    def resolve(self, logical_id: str) -> RuntimeType | None:
        """Resolve one logical data type.

        Args:
            logical_id (str): Stable NodeContract data type identifier.

        Raises:
            None.

        Returns:
            RuntimeType | None: Bound Python type or tuple of types.
        """
        if logical_id == "any":
            return object
        return self.bindings.get(logical_id)

    def accepts(self, logical_id: str, value: Any) -> bool:
        """Check one value against a logical runtime type.

        Args:
            logical_id (str): Stable logical data type identifier.
            value (Any): Runtime port value.

        Raises:
            ComponentDefinitionError: Strict catalog has no binding.

        Returns:
            bool: Whether the value satisfies the binding.
        """
        runtime_type = self.resolve(logical_id)
        if runtime_type is None:
            if self.strict:
                raise ComponentDefinitionError(
                    "component.runtime_type_unknown",
                    f"Logical runtime type {logical_id!r} has no binding",
                    details={"logical_type": logical_id},
                )
            return True
        return True if runtime_type is object else isinstance(value, runtime_type)

    def merge(self, extension: "RuntimeTypeCatalog") -> "RuntimeTypeCatalog":
        """Merge catalogs while rejecting incompatible duplicate IDs.

        Args:
            extension (RuntimeTypeCatalog): Explicit external bindings.

        Raises:
            ComponentDefinitionError: The same logical ID has different types.

        Returns:
            RuntimeTypeCatalog: Deterministic merged catalog.
        """
        merged = dict(self.bindings)
        for logical_id, runtime_type in extension.bindings.items():
            previous = merged.get(logical_id)
            if previous is not None and previous != runtime_type:
                raise ComponentDefinitionError(
                    "component.runtime_type_conflict",
                    f"Conflicting runtime type binding for {logical_id!r}",
                    details={"logical_type": logical_id},
                )
            merged[logical_id] = runtime_type
        return RuntimeTypeCatalog(merged, strict=self.strict or extension.strict)

    def validate_contract(self, contract: NodeContract) -> None:
        """Require bindings for all non-``any`` contract port types.

        Args:
            contract (NodeContract): Contract whose port types are checked.

        Raises:
            ComponentDefinitionError: A strict binding is missing.

        Returns:
            None.
        """
        for port in contract.ports:
            for logical_id in port.data_types:
                if logical_id != "any" and self.resolve(logical_id) is None:
                    raise ComponentDefinitionError(
                        "component.runtime_type_unknown",
                        f"Contract type {logical_id!r} has no runtime binding",
                        details={
                            "contract": f"{contract.ref.id}@{contract.ref.version}",
                            "port": port.id,
                            "logical_type": logical_id,
                        },
                    )


BUILTIN_RUNTIME_TYPES = RuntimeTypeCatalog(
    {
        "text": str,
        "task_input": TaskInput,
        "observation_request": ObservationRequest,
        "action_execution_input": ActionExecutionInput,
        "device_observation": DeviceObservation,
        "plan_result": PlanResult,
        "perception_result": PerceptionResult,
        "memory_context": (tuple, list),
        "action": Action,
        "action_result": ActionResult,
        "verifier_result": VerifierResult,
        "control": (bool, str, dict),
        "semantic_target": (str, dict),
        "grounding_input": GroundingInput,
        "grounding_result": GroundingResult,
        "llm_input": LLMInput,
        "llm_result": LLMResult,
        "device_request": DeviceRequest,
        "device_result": DeviceResult,
        "memory_input": MemoryInput,
        "memory_result": MemoryResult,
        "benchmark_init_input": BenchmarkInitInput,
        "benchmark_init_result": BenchmarkInitResult,
        "evaluation_input": EvaluationInput,
        "evaluation_result": EvaluationResultV2,
        "run_result": RunResult,
    }
)


def _simple_contract(
    contract_id: str,
    input_type: str,
    output_type: str,
    *,
    side_effect: SideEffectKind = SideEffectKind.NONE,
) -> NodeContract:
    """Build a single-input/single-output authoring contract.

    Args:
        contract_id (str): Stable contract identifier.
        input_type (str): Logical input type identifier.
        output_type (str): Logical output type identifier.
        side_effect (SideEffectKind): Static side-effect classification.

    Raises:
        ValueError: NodeContract validation fails.

    Returns:
        NodeContract: Versioned typed-invoke contract.
    """
    return NodeContract(
        ref=NodeContractRef(id=contract_id, version="1.0"),
        ports=(
            ContractPort(
                id="input",
                direction=PortDirection.INPUT,
                data_types=(input_type,),
                required=True,
            ),
            ContractPort(
                id="result",
                direction=PortDirection.OUTPUT,
                data_types=(output_type,),
            ),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
        side_effect=side_effect,
        idempotent=side_effect is not SideEffectKind.DEVICE_ACTION,
    )


_AUXILIARY_CONTRACTS = {
    ComponentRole.LLM: _simple_contract(
        "zhixing.integration.llm",
        "llm_input",
        "llm_result",
        side_effect=SideEffectKind.READ,
    ),
    ComponentRole.DEVICE: _simple_contract(
        "zhixing.integration.device",
        "device_request",
        "device_result",
        side_effect=SideEffectKind.DEVICE_ACTION,
    ),
    ComponentRole.BENCHMARK_INITIALIZER: _simple_contract(
        "zhixing.benchmark.initializer",
        "benchmark_init_input",
        "benchmark_init_result",
        side_effect=SideEffectKind.WRITE,
    ),
    ComponentRole.EVALUATOR: _simple_contract(
        "zhixing.benchmark.evaluator",
        "evaluation_input",
        "evaluation_result",
        side_effect=SideEffectKind.READ,
    ),
}


def _contract_for_role(role: ComponentRole) -> NodeContract | None:
    """Return the default public NodeContract for one known component role.

    Args:
        role (ComponentRole): Public invocation role.

    Raises:
        None.

    Returns:
        NodeContract | None: Built-in or auxiliary contract.
    """
    if role in {
        ComponentRole.PERCEPTION,
        ComponentRole.PLANNER,
        ComponentRole.REASONING,
        ComponentRole.MEMORY,
        ComponentRole.VERIFIER,
        ComponentRole.ACTION_EXECUTOR,
    }:
        reference = contract_ref_for_role(GraphRole(role.value))
        return BUILTIN_NODE_CONTRACT_CATALOG.resolve(reference)
    if role is ComponentRole.GROUNDER:
        return BUILTIN_NODE_CONTRACT_CATALOG.resolve(
            NodeContractRef(id="zhixing.extension.grounder", version="1.0")
        )
    return _AUXILIARY_CONTRACTS.get(role)


def _category_for_role(role: ComponentRole | None) -> ComponentCategory:
    """Return the architectural category for a known invocation role.

    Args:
        role (ComponentRole | None): Optional component role.

    Raises:
        None.

    Returns:
        ComponentCategory: Stable public category.
    """
    if role in {
        ComponentRole.PERCEPTION,
        ComponentRole.PLANNER,
        ComponentRole.REASONING,
        ComponentRole.MEMORY,
        ComponentRole.ACTION_EXECUTOR,
        ComponentRole.VERIFIER,
    }:
        return ComponentCategory.CORE_AGENT
    if role in {ComponentRole.LLM, ComponentRole.DEVICE}:
        return ComponentCategory.RUNTIME_SERVICE
    if role in {
        ComponentRole.BENCHMARK_INITIALIZER,
        ComponentRole.EVALUATOR,
    }:
        return ComponentCategory.BENCHMARK
    return ComponentCategory.EXTENSION


class BaseComponent(ABC, Generic[InputT, OutputT]):
    """Base author contract for one synchronous typed component."""

    component_category: ClassVar[ComponentCategory] = ComponentCategory.EXTENSION
    component_role: ClassVar[ComponentRole | None] = None
    input_type: ClassVar[type[Any] | None] = None
    output_type: ClassVar[type[Any] | None] = None

    @abstractmethod
    def invoke(self, input: InputT, runtime: RuntimeContext) -> OutputT:
        """Execute one synchronous component invocation.

        Args:
            input (InputT): Typed component business input.
            runtime (RuntimeContext): Run-scoped services and state.

        Raises:
            Exception: Domain failures cross the component boundary.

        Returns:
            OutputT: Typed component result.
        """
        raise NotImplementedError


class BasePerception(BaseComponent[DeviceObservation, PerceptionResult]):
    """Author base for the core Perception role."""

    component_category = ComponentCategory.CORE_AGENT
    component_role = ComponentRole.PERCEPTION
    input_type = DeviceObservation
    output_type = PerceptionResult


class BasePlanner(BaseComponent[PlanInput, PlanResult]):
    """Author base for the core Planner role."""

    component_category = ComponentCategory.CORE_AGENT
    component_role = ComponentRole.PLANNER
    input_type = PlanInput
    output_type = PlanResult


class BaseReasoning(BaseComponent[ReasoningInput, Action]):
    """Author base for the core Reasoning role."""

    component_category = ComponentCategory.CORE_AGENT
    component_role = ComponentRole.REASONING
    input_type = ReasoningInput
    output_type = Action


class BaseMemory(BaseComponent[MemoryInput, MemoryResult]):
    """Author base for the core Memory role."""

    component_category = ComponentCategory.CORE_AGENT
    component_role = ComponentRole.MEMORY
    input_type = MemoryInput
    output_type = MemoryResult


class BaseActionExecutor(BaseComponent[ActionExecutionInput, ActionResult]):
    """Author base for the core ActionExecutor role."""

    component_category = ComponentCategory.CORE_AGENT
    component_role = ComponentRole.ACTION_EXECUTOR
    input_type = ActionExecutionInput
    output_type = ActionResult


class BaseVerifier(BaseComponent[VerifierInput, VerifierResult]):
    """Author base for the core Verifier role."""

    component_category = ComponentCategory.CORE_AGENT
    component_role = ComponentRole.VERIFIER
    input_type = VerifierInput
    output_type = VerifierResult


class BaseGrounder(BaseComponent[GroundingInput, GroundingResult]):
    """Author base for the Grounder extension role."""

    component_category = ComponentCategory.EXTENSION
    component_role = ComponentRole.GROUNDER
    input_type = GroundingInput
    output_type = GroundingResult


class BaseLLM(BaseComponent[LLMInput, LLMResult]):
    """Author base for LLM runtime integrations."""

    component_category = ComponentCategory.RUNTIME_SERVICE
    component_role = ComponentRole.LLM
    input_type = LLMInput
    output_type = LLMResult


class BaseDevice(BaseComponent[DeviceRequest, DeviceResult]):
    """Author base for Device runtime integrations."""

    component_category = ComponentCategory.RUNTIME_SERVICE
    component_role = ComponentRole.DEVICE
    input_type = DeviceRequest
    output_type = DeviceResult


class BaseBenchmarkInitializer(
    BaseComponent[BenchmarkInitInput, BenchmarkInitResult]
):
    """Author base for BenchmarkTask initialization components."""

    component_category = ComponentCategory.BENCHMARK
    component_role = ComponentRole.BENCHMARK_INITIALIZER
    input_type = BenchmarkInitInput
    output_type = BenchmarkInitResult


class BaseEvaluator(BaseComponent[EvaluationInput, EvaluationResultV2]):
    """Author base for BenchmarkTask evaluators."""

    component_category = ComponentCategory.BENCHMARK
    component_role = ComponentRole.EVALUATOR
    input_type = EvaluationInput
    output_type = EvaluationResultV2


@dataclass(frozen=True)
class ComponentSpec:
    """Immutable formal definition of one reusable component implementation."""

    namespace: str
    name: str
    version: str
    contract: NodeContract
    implementation: Any = field(repr=False, compare=False)
    category: ComponentCategory = ComponentCategory.EXTENSION
    role: ComponentRole | None = None
    config_model: type[BaseModel] = EmptyComponentConfig
    zhixing_compatibility: str = "*"
    runtime_types: Mapping[str, RuntimeType] = field(default_factory=dict)
    capabilities: Mapping[str, str | bool | int | float | None] = field(
        default_factory=dict,
        repr=False,
    )
    dependency_slots: tuple[ComponentDependencySlot, ...] = ()
    factory: ComponentFactory | None = field(default=None, repr=False, compare=False)
    input_type: type[Any] | None = field(default=None, repr=False)
    output_type: type[Any] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Freeze mappings and reject unsafe basic definition shapes.

        Args:
            None.

        Raises:
            ComponentDefinitionError: Basic identity or model shape is invalid.

        Returns:
            None.
        """
        if not _IDENTIFIER.fullmatch(self.namespace):
            raise ComponentDefinitionError(
                "component.namespace_invalid",
                f"Invalid component namespace {self.namespace!r}",
            )
        if not _IDENTIFIER.fullmatch(self.name):
            raise ComponentDefinitionError(
                "component.name_invalid",
                f"Invalid component name {self.name!r}",
            )
        if not _VERSION.fullmatch(self.version):
            raise ComponentDefinitionError(
                "component.version_invalid",
                f"Invalid component version {self.version!r}",
                component_id=f"{self.namespace}:{self.name}",
            )
        if not isinstance(self.config_model, type) or not issubclass(
            self.config_model, BaseModel
        ):
            raise ComponentDefinitionError(
                "component.config_model_invalid",
                "config_model must be a Pydantic BaseModel subclass",
                component_id=self.identifier,
            )
        slots = tuple(self.dependency_slots)
        if len(slots) > _MAX_DEPENDENCY_SLOTS:
            raise ComponentDefinitionError(
                "component.dependency_slots_too_many",
                "Component declares too many dependency slots",
                component_id=self.identifier,
            )
        if any(not isinstance(item, ComponentDependencySlot) for item in slots):
            raise ComponentDefinitionError(
                "component.dependency_slot_invalid",
                "Component dependency slots must use ComponentDependencySlot",
                component_id=self.identifier,
            )
        names = [item.name for item in slots]
        if len(names) != len(set(names)):
            raise ComponentDefinitionError(
                "component.dependency_slot_duplicate",
                "Component dependency slot names must be unique",
                component_id=self.identifier,
            )
        object.__setattr__(
            self,
            "runtime_types",
            MappingProxyType(dict(self.runtime_types)),
        )
        object.__setattr__(
            self,
            "capabilities",
            MappingProxyType(dict(self.capabilities)),
        )
        object.__setattr__(self, "dependency_slots", slots)

    @property
    def identifier(self) -> str:
        """Return the safe component namespace/name/version identity.

        Args:
            None.

        Raises:
            None.

        Returns:
            str: Stable public identifier.
        """
        return f"{self.namespace}:{self.name}@{self.version}"

    @property
    def contract_ref(self) -> NodeContractRef:
        """Return the exact NodeContract reference.

        Args:
            None.

        Raises:
            None.

        Returns:
            NodeContractRef: Contract identity.
        """
        return self.contract.ref

    def safe_metadata(self) -> dict[str, Any]:
        """Return full public Contract metadata without executable or secret state.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible public definition summary.
        """
        from .models import redact_mapping

        contract_metadata = self.contract.model_dump(mode="json")
        contract_reference = contract_metadata.pop("ref")
        return {
            "identifier": self.identifier,
            "namespace": self.namespace,
            "name": self.name,
            "version": self.version,
            # Keep the established id/version fields while exposing the complete
            # port, adapter, side-effect, and execution-feature declaration.
            "contract": redact_mapping(
                {
                    "id": contract_reference["id"],
                    "version": contract_reference["version"],
                    **contract_metadata,
                }
            ),
            "category": self.category.value,
            "role": self.role.value if self.role else None,
            "zhixing_compatibility": self.zhixing_compatibility,
            "config_schema": redact_mapping(
                self.config_model.model_json_schema()
            ),
            "runtime_types": sorted(self.runtime_types),
            "capabilities": redact_mapping(self.capabilities),
            "dependency_slots": [
                item.to_safe_dict() for item in self.dependency_slots
            ],
        }


class _FunctionComponent:
    """Invocation wrapper for one decorated synchronous function."""

    def __init__(self, function: Callable[[Any, RuntimeContext], Any]) -> None:
        """Store the decorated function.

        Args:
            function (Callable[[Any, RuntimeContext], Any]): Typed function.

        Raises:
            None.

        Returns:
            None.
        """
        self._function = function

    def invoke(self, input: Any, runtime: RuntimeContext) -> Any:
        """Forward one invocation to the decorated function.

        Args:
            input (Any): Typed function input.
            runtime (RuntimeContext): Run-scoped context.

        Raises:
            Exception: Function failures propagate.

        Returns:
            Any: Function output.
        """
        return self._function(input, runtime)


def _version_tuple(value: str) -> tuple[int, ...]:
    """Parse the numeric release segment used by compatibility checks.

    Args:
        value (str): Version or compatible release boundary.

    Raises:
        ComponentDefinitionError: No numeric release segment is present.

    Returns:
        tuple[int, ...]: Comparable release components.
    """
    release = value.split("+", 1)[0].split("-", 1)[0]
    if not release or any(not item.isdigit() for item in release.split(".")):
        raise ComponentDefinitionError(
            "component.compatibility_invalid",
            f"Invalid compatibility version {value!r}",
        )
    return tuple(int(item) for item in release.split("."))


def _compare_versions(left: str, right: str) -> int:
    """Compare two numeric release versions.

    Args:
        left (str): First release.
        right (str): Second release.

    Raises:
        ComponentDefinitionError: A release cannot be parsed.

    Returns:
        int: Negative, zero, or positive comparison result.
    """
    first = _version_tuple(left)
    second = _version_tuple(right)
    width = max(len(first), len(second))
    first += (0,) * (width - len(first))
    second += (0,) * (width - len(second))
    return (first > second) - (first < second)


def _version_satisfies(current: str, constraint: str) -> bool:
    """Evaluate a small deterministic comma-separated version range.

    Args:
        current (str): Current ZhiXing API version.
        constraint (str): ``*`` or comma-separated comparison clauses.

    Raises:
        ComponentDefinitionError: A clause uses unsupported syntax.

    Returns:
        bool: Whether the current version satisfies every clause.
    """
    if constraint.strip() in {"", "*"}:
        return True
    for clause in (item.strip() for item in constraint.split(",")):
        operator = next(
            (candidate for candidate in (">=", "<=", "==", ">", "<") if clause.startswith(candidate)),
            None,
        )
        if operator is None:
            raise ComponentDefinitionError(
                "component.compatibility_invalid",
                f"Unsupported compatibility clause {clause!r}",
            )
        boundary = clause[len(operator) :].strip()
        comparison = _compare_versions(current, boundary)
        matches = {
            ">=": comparison >= 0,
            "<=": comparison <= 0,
            "==": comparison == 0,
            ">": comparison > 0,
            "<": comparison < 0,
        }[operator]
        if not matches:
            return False
    return True


def _callable_signature(target: Any) -> tuple[inspect.Signature, Mapping[str, Any]]:
    """Return the invocation signature and resolved annotations.

    Args:
        target (Any): Component class, callable, or instance.

    Raises:
        ComponentDefinitionError: No inspectable synchronous invocation exists.

    Returns:
        tuple[inspect.Signature, Mapping[str, Any]]: Signature and type hints.
    """
    invocation = target
    if inspect.isclass(target):
        invocation = getattr(target, "invoke", None)
    elif not inspect.isfunction(target):
        invocation = getattr(target, "invoke", None)
    if not callable(invocation):
        raise ComponentDefinitionError(
            "component.invoke_missing",
            "Formal component must expose invoke(input, runtime)",
        )
    if inspect.iscoroutinefunction(invocation) or inspect.isgeneratorfunction(invocation):
        raise ComponentDefinitionError(
            "component.invoke_not_synchronous",
            "Component V1 invoke must be a synchronous non-generator callable",
        )
    try:
        return inspect.signature(invocation), get_type_hints(invocation)
    except (TypeError, ValueError, NameError) as error:
        raise ComponentDefinitionError(
            "component.signature_unavailable",
            f"Component invocation annotations cannot be resolved ({type(error).__name__})",
        ) from error


def _annotation_compatible(annotation: Any, expected: type[Any]) -> bool:
    """Check one concrete annotation against an expected runtime class.

    Args:
        annotation (Any): Resolved function annotation.
        expected (type[Any]): Required public DTO class.

    Raises:
        None.

    Returns:
        bool: True when the annotation is the same class or a subtype.
    """
    if annotation in {inspect.Signature.empty, Any, None}:
        return False
    try:
        return annotation is expected or (
            isinstance(annotation, type) and issubclass(annotation, expected)
        )
    except TypeError:
        return False


def _expected_types(spec: ComponentSpec) -> tuple[type[Any] | None, type[Any] | None]:
    """Resolve expected input/output types from the spec or author base.

    Args:
        spec (ComponentSpec): Formal component definition.

    Raises:
        None.

    Returns:
        tuple[type[Any] | None, type[Any] | None]: Expected invocation types.
    """
    author_type = spec.implementation if inspect.isclass(spec.implementation) else None
    input_type = spec.input_type or getattr(author_type, "input_type", None)
    output_type = spec.output_type or getattr(author_type, "output_type", None)
    if spec.role is not None:
        descriptor = get_role_descriptor(spec.role)
        input_type = input_type or descriptor.input_type
        output_type = output_type or descriptor.output_type
    return input_type, output_type


def validate_component_spec(
    spec: ComponentSpec,
    *,
    expected_contract: NodeContract | NodeContractRef | None = None,
    expected_role: ComponentRole | GraphRole | str | None = None,
    framework_version: str = _FRAMEWORK_API_VERSION,
) -> RuntimeTypeCatalog:
    """Validate a formal component definition without constructing it.

    Args:
        spec (ComponentSpec): Definition to validate.
        expected_contract (NodeContract | NodeContractRef | None): Binding contract.
        expected_role (ComponentRole | GraphRole | str | None): Binding role.
        framework_version (str): Current public API version.

    Raises:
        ComponentDefinitionError: Definition, compatibility, or signature is invalid.

    Returns:
        RuntimeTypeCatalog: Strict merged type catalog for the component.
    """
    if not _version_satisfies(framework_version, spec.zhixing_compatibility):
        raise ComponentDefinitionError(
            "component.version_incompatible",
            f"Component requires ZhiXing {spec.zhixing_compatibility}",
            component_id=spec.identifier,
            details={"framework_version": framework_version},
        )
    expected_ref = (
        expected_contract.ref
        if isinstance(expected_contract, NodeContract)
        else expected_contract
    )
    if expected_ref is not None and spec.contract.ref != expected_ref:
        raise ComponentDefinitionError(
            "component.contract_mismatch",
            "ComponentSpec contract does not match the graph node contract",
            component_id=spec.identifier,
            details={
                "declared": f"{spec.contract.ref.id}@{spec.contract.ref.version}",
                "expected": f"{expected_ref.id}@{expected_ref.version}",
            },
        )
    selected_role = (
        ComponentRole(expected_role.value)
        if isinstance(expected_role, GraphRole)
        else ComponentRole(expected_role)
        if expected_role is not None
        else None
    )
    if selected_role is not None and spec.role is not selected_role:
        raise ComponentDefinitionError(
            "component.role_mismatch",
            f"Component role {spec.role.value if spec.role else 'none'} does not match {selected_role.value}",
            component_id=spec.identifier,
        )
    if spec.role is not None:
        default_contract = _contract_for_role(spec.role)
        if default_contract is not None and spec.contract.ref != default_contract.ref:
            raise ComponentDefinitionError(
                "component.role_contract_mismatch",
                "Component role and declared contract are incompatible",
                component_id=spec.identifier,
                details={
                    "role": spec.role.value,
                    "contract": f"{spec.contract.ref.id}@{spec.contract.ref.version}",
                },
            )
    author_role = getattr(spec.implementation, "component_role", None)
    if author_role is not None and spec.role is not author_role:
        raise ComponentDefinitionError(
            "component.author_role_mismatch",
            "ComponentSpec role differs from its author base",
            component_id=spec.identifier,
        )
    author_category = getattr(spec.implementation, "component_category", None)
    expected_category = (
        author_category
        if author_category is not None
        else _category_for_role(spec.role)
    )
    if spec.category is not expected_category:
        raise ComponentDefinitionError(
            "component.category_mismatch",
            "ComponentSpec category differs from its author role or base",
            component_id=spec.identifier,
            details={
                "declared": spec.category.value,
                "expected": expected_category.value,
            },
        )
    attached_spec = getattr(
        spec.implementation,
        "__zhixing_component_spec__",
        None,
    )
    uses_author_base = (
        inspect.isclass(spec.implementation)
        and issubclass(spec.implementation, BaseComponent)
    )
    if not uses_author_base and attached_spec is not spec:
        raise ComponentDefinitionError(
            "component.authoring_model_invalid",
            "Formal components must inherit BaseComponent or use @component",
            component_id=spec.identifier,
        )
    signature, hints = _callable_signature(spec.implementation)
    parameters = list(signature.parameters.values())
    if inspect.isclass(spec.implementation):
        parameters = [item for item in parameters if item.name != "self"]
    if [item.name for item in parameters] != ["input", "runtime"]:
        raise ComponentDefinitionError(
            "component.signature_invalid",
            "Component invoke must declare exactly input and runtime parameters",
            component_id=spec.identifier,
            details={"parameters": [item.name for item in parameters]},
        )
    input_type, output_type = _expected_types(spec)
    if input_type is None or output_type is None:
        raise ComponentDefinitionError(
            "component.types_missing",
            "Component input_type and output_type must be explicit",
            component_id=spec.identifier,
        )
    if not _annotation_compatible(hints.get("input"), input_type):
        raise ComponentDefinitionError(
            "component.input_annotation_mismatch",
            f"Component input annotation must be {input_type.__name__}",
            component_id=spec.identifier,
        )
    if hints.get("runtime") is not RuntimeContext:
        raise ComponentDefinitionError(
            "component.runtime_annotation_mismatch",
            "Component runtime annotation must be RuntimeContext",
            component_id=spec.identifier,
        )
    if not _annotation_compatible(hints.get("return"), output_type):
        raise ComponentDefinitionError(
            "component.output_annotation_mismatch",
            f"Component return annotation must be {output_type.__name__}",
            component_id=spec.identifier,
        )
    catalog = BUILTIN_RUNTIME_TYPES.merge(
        RuntimeTypeCatalog(spec.runtime_types, strict=True)
    )
    catalog.validate_contract(spec.contract)
    return catalog


def validate_component_params(
    spec: ComponentSpec,
    params: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate and normalize component constructor parameters.

    Args:
        spec (ComponentSpec): Formal component definition.
        params (Mapping[str, Any] | None): Declarative parameter mapping.

    Raises:
        ComponentConfigurationError: Pydantic rejects the parameters.

    Returns:
        dict[str, Any]: Normalized constructor keyword arguments.
    """
    try:
        model = spec.config_model.model_validate(dict(params or {}))
    except ValidationError as error:
        fields = [
            ".".join(str(item) for item in issue.get("loc", ()))
            for issue in error.errors(include_input=False, include_url=False)
        ]
        raise ComponentConfigurationError(
            "component.config_invalid",
            "Component parameters do not satisfy the declared schema",
            component_id=spec.identifier,
            details={"fields": fields},
        ) from error
    return model.model_dump(mode="python")


def construct_component(
    spec: ComponentSpec,
    params: Mapping[str, Any] | None = None,
    *,
    dependencies: Mapping[str, Any] | None = None,
    expected_contract: NodeContract | NodeContractRef | None = None,
    expected_role: ComponentRole | GraphRole | str | None = None,
    framework_version: str = _FRAMEWORK_API_VERSION,
) -> Any:
    """Validate and construct one run-scoped formal component instance.

    Args:
        spec (ComponentSpec): Formal component definition.
        params (Mapping[str, Any] | None): Declarative configuration.
        dependencies (Mapping[str, Any] | None): Explicit pre-resolved dependencies.
        expected_contract (NodeContract | NodeContractRef | None): Binding contract.
        expected_role (ComponentRole | GraphRole | str | None): Binding role.
        framework_version (str): Current public API version.

    Raises:
        ComponentDefinitionError: Definition or construction is invalid.
        ComponentConfigurationError: Parameters fail schema validation.

    Returns:
        Any: Fresh component instance exposing ``invoke``.
    """
    validate_component_spec(
        spec,
        expected_contract=expected_contract,
        expected_role=expected_role,
        framework_version=framework_version,
    )
    config = validate_component_params(spec, params)
    supplied_dependencies = dict(dependencies or {})
    duplicate = sorted(set(config) & set(supplied_dependencies))
    if duplicate:
        raise ComponentDefinitionError(
            "component.dependency_conflict",
            "Configuration and dependency names overlap",
            component_id=spec.identifier,
            details={"names": duplicate},
        )
    try:
        if spec.factory is not None:
            instance = spec.factory(config, supplied_dependencies)
        elif inspect.isclass(spec.implementation):
            instance = spec.implementation(**config, **supplied_dependencies)
        elif inspect.isfunction(spec.implementation):
            if config or supplied_dependencies:
                raise ComponentDefinitionError(
                    "component.function_configuration_unsupported",
                    "Function components require an explicit factory when configuration or dependencies are used",
                    component_id=spec.identifier,
                )
            instance = _FunctionComponent(spec.implementation)
        else:
            raise ComponentDefinitionError(
                "component.implementation_invalid",
                "Component implementation must be a class or function",
                component_id=spec.identifier,
            )
    except ComponentDefinitionError:
        raise
    except Exception as error:
        raise ComponentDefinitionError(
            "component.construction_failed",
            f"Component construction failed ({type(error).__name__})",
            component_id=spec.identifier,
        ) from error
    if not callable(getattr(instance, "invoke", None)):
        raise ComponentDefinitionError(
            "component.instance_protocol_invalid",
            "Constructed component does not expose invoke(input, runtime)",
            component_id=spec.identifier,
        )
    try:
        setattr(instance, "__zhixing_component_spec__", spec)
    except (AttributeError, TypeError) as error:
        if get_component_spec(instance) is not spec:
            raise ComponentDefinitionError(
                "component.instance_metadata_unavailable",
                "Constructed component cannot retain its formal ComponentSpec",
                component_id=spec.identifier,
            ) from error
    return instance


def get_component_spec(target: Any) -> ComponentSpec | None:
    """Read a formal ComponentSpec from a definition, class, function, or instance.

    Args:
        target (Any): Candidate definition or implementation.

    Raises:
        None.

    Returns:
        ComponentSpec | None: Attached formal definition.
    """
    if isinstance(target, ComponentSpec):
        return target
    specification = getattr(target, "__zhixing_component_spec__", None)
    return specification if isinstance(specification, ComponentSpec) else None


def component(
    *,
    namespace: str,
    name: str,
    version: str = "1.0.0",
    role: ComponentRole | GraphRole | str | None = None,
    contract: NodeContract | None = None,
    category: ComponentCategory | str | None = None,
    config_model: type[BaseModel] = EmptyComponentConfig,
    zhixing_compatibility: str = "*",
    runtime_types: Mapping[str, RuntimeType] | None = None,
    capabilities: Mapping[str, str | bool | int | float | None] | None = None,
    dependency_slots: tuple[ComponentDependencySlot, ...] = (),
    input_type: type[Any] | None = None,
    output_type: type[Any] | None = None,
    factory: ComponentFactory | None = None,
) -> Callable[[ComponentTargetT], ComponentTargetT]:
    """Decorate a typed class or function with a formal ComponentSpec.

    Args:
        namespace (str): Stable publisher namespace.
        name (str): Stable component name.
        version (str): Component semantic version.
        role (ComponentRole | GraphRole | str | None): Optional known role.
        contract (NodeContract | None): Exact typed NodeContract.
        category (ComponentCategory | str | None): Architectural category.
        config_model (type[BaseModel]): Pydantic constructor schema.
        zhixing_compatibility (str): Supported ZhiXing version range.
        runtime_types (Mapping[str, RuntimeType] | None): Custom logical types.
        capabilities (Mapping[str, str | bool | int | float | None] | None):
            Static safe capability metadata.
        dependency_slots (tuple[ComponentDependencySlot, ...]): Declarative
            runtime dependency authoring metadata.
        input_type (type[Any] | None): Explicit callable input type.
        output_type (type[Any] | None): Explicit callable result type.
        factory (ComponentFactory | None): Optional run-scoped constructor.

    Raises:
        ComponentDefinitionError: The decorated definition is invalid.

    Returns:
        Callable[[ComponentTargetT], ComponentTargetT]: Definition decorator.
    """
    selected_role = (
        ComponentRole(role.value)
        if isinstance(role, GraphRole)
        else ComponentRole(role)
        if role is not None
        else None
    )

    def decorate(target: ComponentTargetT) -> ComponentTargetT:
        """Attach and validate one immutable formal component definition.

        Args:
            target (ComponentTargetT): Typed class or synchronous function.

        Raises:
            ComponentDefinitionError: Metadata or invocation is incompatible.

        Returns:
            ComponentTargetT: The unchanged callable with attached metadata.
        """
        inferred_role = selected_role or getattr(target, "component_role", None)
        selected_contract = contract or (
            _contract_for_role(inferred_role) if inferred_role is not None else None
        )
        if selected_contract is None:
            raise ComponentDefinitionError(
                "component.contract_missing",
                "Formal component requires a role with a known contract or an explicit NodeContract",
            )
        inferred_category = category or getattr(
            target,
            "component_category",
            _category_for_role(inferred_role),
        )
        specification = ComponentSpec(
            namespace=namespace,
            name=name,
            version=version,
            contract=selected_contract,
            implementation=target,
            category=ComponentCategory(inferred_category),
            role=inferred_role,
            config_model=config_model,
            zhixing_compatibility=zhixing_compatibility,
            runtime_types=runtime_types or {},
            capabilities=capabilities or {},
            dependency_slots=dependency_slots,
            factory=factory,
            input_type=input_type,
            output_type=output_type,
        )
        previous = getattr(target, "__zhixing_component_spec__", None)
        setattr(target, "__zhixing_component_spec__", specification)
        try:
            validate_component_spec(specification)
        except Exception:
            if previous is None:
                delattr(target, "__zhixing_component_spec__")
            else:
                setattr(target, "__zhixing_component_spec__", previous)
            raise
        return target

    return decorate


__all__ = [
    "BUILTIN_RUNTIME_TYPES",
    "BaseActionExecutor",
    "BaseBenchmarkInitializer",
    "BaseComponent",
    "BaseDevice",
    "BaseEvaluator",
    "BaseGrounder",
    "BaseLLM",
    "BaseMemory",
    "BasePerception",
    "BasePlanner",
    "BaseReasoning",
    "BaseVerifier",
    "ComponentCategory",
    "ComponentFactory",
    "ComponentSpec",
    "EmptyComponentConfig",
    "RuntimeType",
    "RuntimeTypeCatalog",
    "component",
    "construct_component",
    "get_component_spec",
    "validate_component_params",
    "validate_component_spec",
]
