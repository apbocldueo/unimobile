"""Deterministic, side-effect-free Component Catalog for Studio authoring."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from typing import Any, Literal, Mapping

from pydantic import Field

from zhixing.catalog import (
    BUILTIN_COMPONENT_CATALOG,
    BuiltInComponentCatalog,
    DiscoveredComponentEnvironment,
    empty_component_environment,
)
from zhixing.components import ComponentCategory
from zhixing.graph import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    ContractPort,
    DiagnosticSeverity,
    ExecutionFeatures,
    GraphDiagnostic,
    GraphRole,
    InvocationAdapterKind,
    NodeContract,
    NodeContractCatalog,
    NodeContractRef,
    PortDirection,
    SideEffectKind,
    contract_ref_for_role,
)

from .models import StudioCapabilityFamily, StudioModel


StudioCatalogPlacement = Literal[
    "agent_capability",
    "dependency_only",
    "runtime_internal",
    "benchmark_only",
]


_ROLE_BY_NAMESPACE = {
    f"agent.{role.value}": role
    for role in (
        GraphRole.PERCEPTION,
        GraphRole.PLANNER,
        GraphRole.REASONING,
        GraphRole.MEMORY,
        GraphRole.ACTION_EXECUTOR,
        GraphRole.VERIFIER,
    )
}
_CONTRACT_REF_BY_COMPONENT = {
    ("agent.grounder", "uground_grounder"): NodeContractRef(
        id="zhixing.extension.grounder",
        version="1.0",
    ),
    ("zhixing.control", "action_request"): NodeContractRef(
        id="zhixing.control.action_request",
        version="1.0",
    ),
    ("zhixing.control", "verification_terminal_action"): NodeContractRef(
        id="zhixing.control.transform",
        version="1.0",
    ),
    ("zhixing.runtime", "device_observe"): NodeContractRef(
        id="zhixing.service.device_observe",
        version="2.0",
    ),
    ("zhixing.runtime", "action_executor"): NodeContractRef(
        id="zhixing.service.action_executor",
        version="1.0",
    ),
}
_LLM_CONTRACT = NodeContract(
    ref=NodeContractRef(id="zhixing.integration.llm", version="1.0"),
    ports=(
        ContractPort(
            id="input",
            direction=PortDirection.INPUT,
            data_types=("llm_input",),
            required=True,
        ),
        ContractPort(
            id="result",
            direction=PortDirection.OUTPUT,
            data_types=("llm_result",),
        ),
    ),
    adapter=InvocationAdapterKind.TYPED_INVOKE,
    side_effect=SideEffectKind.READ,
    idempotent=True,
)


def _object_schema(
    properties: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    required: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Build a strict safe object schema for a built-in descriptor.

    Args:
        properties (Mapping[str, Mapping[str, Any]] | None): JSON Schema
            property declarations.
        required (tuple[str, ...]): Required property names.

    Raises:
        None.

    Returns:
        dict[str, Any]: Strict JSON Schema object.
    """
    schema: dict[str, Any] = {
        "type": "object",
        "properties": dict(properties or {}),
        "additionalProperties": False,
    }
    if required:
        schema["required"] = list(required)
    return schema


_BUILTIN_CONFIG_SCHEMAS: dict[tuple[str, str], dict[str, Any]] = {
    ("agent.perception", "screenshot_perception"): _object_schema(
        {"prompt_note": {"type": "string", "default": ""}}
    ),
    ("agent.perception", "coordinate_perception"): _object_schema(
        {
            "include_non_clickable_text": {"type": "boolean", "default": True},
            "max_elements": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 120},
            "keyboard_y_ratio": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.9},
        }
    ),
    ("agent.memory", "sliding_window_memory"): _object_schema(
        {
            "window_size": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 10},
            "include_thought": {"type": "boolean", "default": True},
            "include_raw": {"type": "boolean", "default": False},
        }
    ),
    ("agent.memory", "summary_memory"): _object_schema(
        {
            "max_history_len": {"type": "integer", "minimum": 1, "maximum": 10000, "default": 10},
            "compress_ratio": {"type": "number", "exclusiveMinimum": 0, "maximum": 1, "default": 0.5},
        }
    ),
    ("agent.planner", "universal_planner"): _object_schema(
        {
            "preset": {"type": "string", "default": "manager_style"},
            "prompt_file": {"type": ["string", "null"]},
            "parser_name": {"type": ["string", "null"]},
            "use_rag": {"type": ["boolean", "null"]},
        }
    ),
    ("agent.reasoning", "universal_reasoning"): _object_schema(
        {
            "preset": {"type": ["string", "null"]},
            "prompt_file": {"type": ["string", "null"]},
            "parser_name": {"type": ["string", "null"]},
            "input_mode": {"type": ["string", "null"]},
            "parse_max_retries": {"type": "integer", "minimum": 0, "maximum": 20, "default": 3},
        }
    ),
    ("agent.verifier", "screen_diff_verifier"): _object_schema(
        {"threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.01}}
    ),
    ("agent.verifier", "llm_reflect_verifier"): _object_schema(
        {
            "prompt_file": {"type": "string", "default": "verifier_mobileagent_reflect.md"},
            "add_info": {"type": "string", "default": ""},
        }
    ),
    ("agent.verifier", "android_content_delta_verifier"): _object_schema(
        {
            "uri": {"type": "string", "default": "content://media/external/images/media"},
            "id_column": {"type": "string", "default": "_id"},
            "minimum_added": {"type": "integer", "minimum": 1, "default": 1},
            "baseline_actions": {"type": "array", "items": {"type": "string"}},
            "baseline_key": {"type": "string", "default": "android_content"},
        }
    ),
    ("agent.grounder", "uground_grounder"): _object_schema(
        {
            "model": {"type": "string", "default": "osunlp/UGround-V1-7B"},
            "resized_width": {"type": "integer", "minimum": 1, "default": 882},
            "resized_height": {"type": "integer", "minimum": 1, "default": 1960},
            "coordinate_scale_max": {"type": "integer", "minimum": 1, "default": 1000},
        }
    ),
    ("llm", "openai_llm"): _object_schema(
        {
            "api_key": {
                "type": "object",
                "properties": {"secret_ref": {"type": "string", "minLength": 1}},
                "required": ["secret_ref"],
                "additionalProperties": False,
                "x-zhixing-secret-ref": True,
            },
            "model": {"type": "string", "default": "gpt-4o"},
            "base_url": {
                "oneOf": [
                    {"type": ["string", "null"]},
                    {
                        "type": "object",
                        "properties": {
                            "secret_ref": {"type": "string", "minLength": 1}
                        },
                        "required": ["secret_ref"],
                        "additionalProperties": False,
                    },
                ],
                "x-zhixing-secret-ref": True,
            },
            "temperature": {"type": "number", "minimum": 0, "maximum": 2, "default": 0.1},
            "max_tokens": {"type": "integer", "minimum": 1, "default": 4096},
            "request_timeout": {"type": "number", "minimum": 1, "maximum": 600, "default": 45},
            "max_retries": {"type": "integer", "minimum": 0, "maximum": 10, "default": 0},
        },
        required=("api_key",),
    ),
}


class StudioComponentAvailability(StudioModel):
    """Safe import availability for one authorable component."""

    available: bool = True
    extra: str = ""
    error_type: str = ""


class StudioComponentDescriptor(StudioModel):
    """Complete safe authoring descriptor for one exact component version."""

    identifier: str
    namespace: str
    name: str
    version: str
    provider_id: str
    contract: NodeContract
    category: str
    role: str | None = None
    placement: StudioCatalogPlacement
    capability_family: StudioCapabilityFamily | None = None
    termination: dict[str, Any] | None = None
    config_schema: dict[str, Any] = Field(default_factory=dict)
    dependency_slots: tuple[dict[str, Any], ...] = ()
    availability: StudioComponentAvailability = Field(
        default_factory=StudioComponentAvailability
    )
    capabilities: dict[str, str | bool | int | float | None] = Field(
        default_factory=dict
    )
    provenance: dict[str, Any] = Field(default_factory=dict)
    display: dict[str, str] = Field(default_factory=dict)


class StudioCapabilityFamilyDescriptor(StudioModel):
    """Backend-authoritative capability family exposed by the Studio Palette."""

    family: StudioCapabilityFamily
    label: str
    extension: bool = False
    available_implementation_count: int = Field(default=0, ge=0)


class StudioProviderReport(StudioModel):
    """Bounded safe report for explicitly loaded component providers."""

    loaded_provider_ids: tuple[str, ...] = ()
    skipped_provider_ids: tuple[str, ...] = ()
    failures: tuple[dict[str, str], ...] = ()


class StudioComponentCatalog(StudioModel):
    """Versioned deterministic Studio Catalog response."""

    schema_version: int = 1
    catalog_version: str
    components: tuple[StudioComponentDescriptor, ...]
    capability_families: tuple[StudioCapabilityFamilyDescriptor, ...] = ()
    provider_report: StudioProviderReport = Field(default_factory=StudioProviderReport)
    diagnostics: tuple[GraphDiagnostic, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the Catalog without implementation or runtime objects.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Camel-case JSON response.
        """
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)

    def node_contract_catalog(self) -> NodeContractCatalog:
        """Return explicit non-core contracts required by Studio compilation.

        Args:
            None.

        Raises:
            ValueError: Catalog descriptors conflict at the same contract
                identity.

        Returns:
            NodeContractCatalog: Deterministic contract extension catalog.
        """
        contracts: dict[tuple[str, str], NodeContract] = {}
        for component in self.components:
            key = (component.contract.ref.id, component.contract.ref.version)
            previous = contracts.get(key)
            if previous is not None and previous != component.contract:
                raise ValueError(f"conflicting Studio contract {key[0]}@{key[1]}")
            if BUILTIN_NODE_CONTRACT_CATALOG.resolve(component.contract.ref) is None:
                contracts[key] = component.contract
        return NodeContractCatalog(contracts.values())


def _contract_for_builtin(namespace: str, name: str) -> NodeContract | None:
    """Resolve a formal contract for one built-in declaration.

    Args:
        namespace (str): Built-in component namespace.
        name (str): Built-in component name.

    Raises:
        None.

    Returns:
        NodeContract | None: Formal contract when authorable as a graph node.
    """
    role = _ROLE_BY_NAMESPACE.get(namespace)
    if role is not None:
        return BUILTIN_NODE_CONTRACT_CATALOG.resolve(contract_ref_for_role(role))
    if (namespace, name) == ("llm", "openai_llm"):
        return _LLM_CONTRACT
    reference = _CONTRACT_REF_BY_COMPONENT.get((namespace, name))
    return (
        BUILTIN_NODE_CONTRACT_CATALOG.resolve(reference)
        if reference is not None
        else None
    )


def _availability(specification: Any) -> StudioComponentAvailability:
    """Inspect declared optional modules without importing component code.

    Args:
        specification (BuiltInComponentSpec): Import-safe built-in declaration.

    Raises:
        None.

    Returns:
        StudioComponentAvailability: Bounded availability result.
    """
    missing = tuple(
        module
        for module in specification.required_modules
        if importlib.util.find_spec(module) is None
    )
    if missing:
        return StudioComponentAvailability(
            available=False,
            extra=specification.extra,
            error_type="optional_dependency_missing",
        )
    return StudioComponentAvailability(available=True, extra=specification.extra)


def _category_for_builtin(namespace: str) -> str:
    """Map a built-in namespace to a stable display category.

    Args:
        namespace (str): Component namespace.

    Raises:
        None.

    Returns:
        str: ComponentCategory value.
    """
    if namespace in _ROLE_BY_NAMESPACE:
        return ComponentCategory.CORE_AGENT.value
    if namespace.startswith("zhixing.runtime") or namespace == "llm":
        return ComponentCategory.RUNTIME_SERVICE.value
    return ComponentCategory.EXTENSION.value


def _catalog_authoring_classification(
    *,
    namespace: str,
    name: str,
    category: str,
    role: GraphRole | None,
    contract: NodeContract,
    capabilities: Mapping[str, Any],
) -> tuple[StudioCatalogPlacement, StudioCapabilityFamily | None, dict[str, Any] | None]:
    """Classify one safe descriptor without treating Catalog membership as placement.

    Args:
        namespace: Exact component namespace.
        name: Exact component name.
        category: Stable ComponentCategory value.
        role: Formal graph role, when declared.
        contract: Exact NodeContract implemented by the component.
        capabilities: Safe provider capability metadata.

    Raises:
        None: Unknown or inconsistent declarations fail closed to dependency-only.

    Returns:
        Placement, optional capability family, and optional termination metadata.
    """
    if category == ComponentCategory.BENCHMARK.value:
        return "benchmark_only", None, None
    if namespace == "llm":
        return "dependency_only", None, None
    if namespace.startswith("zhixing.runtime") or namespace.startswith(
        "zhixing.control"
    ):
        return "runtime_internal", None, None
    if namespace == "agent.action_executor" and name == "legacy_action_executor":
        return "runtime_internal", None, None
    core_roles = {
        GraphRole.PERCEPTION,
        GraphRole.PLANNER,
        GraphRole.REASONING,
        GraphRole.MEMORY,
        GraphRole.ACTION_EXECUTOR,
        GraphRole.VERIFIER,
    }
    if role in core_roles and contract.ref == contract_ref_for_role(role):
        termination = (
            {
                "predicate": {"field": "terminal_status", "operator": "exists"},
                "sourcePort": "result",
            }
            if role in {GraphRole.ACTION_EXECUTOR, GraphRole.VERIFIER}
            else None
        )
        return "agent_capability", role.value, termination
    requested = capabilities.get("studio_capability_family")
    if (
        requested in {"grounder", "tool"}
        and category == ComponentCategory.EXTENSION.value
        and contract.adapter is InvocationAdapterKind.TYPED_INVOKE
        and not contract.features.runtime_service
    ):
        return "agent_capability", requested, None
    if namespace == "agent.grounder" and name == "uground_grounder":
        return "agent_capability", "grounder", None
    return "dependency_only", None, None


def _capability_family_descriptors(
    components: tuple[StudioComponentDescriptor, ...],
) -> tuple[StudioCapabilityFamilyDescriptor, ...]:
    """Build the stable six-core-plus-approved-extension Palette inventory.

    Args:
        components: Ordered safe Catalog component descriptors.

    Raises:
        None.

    Returns:
        Ordered backend-authoritative family descriptors.
    """
    order: tuple[StudioCapabilityFamily, ...] = (
        "perception",
        "planner",
        "reasoning",
        "memory",
        "action_executor",
        "verifier",
        "grounder",
        "tool",
    )
    labels = {
        "perception": "Perception",
        "planner": "Planner",
        "reasoning": "Reasoning",
        "memory": "Memory",
        "action_executor": "Action Executor",
        "verifier": "Verifier",
        "grounder": "Grounder",
        "tool": "Tool",
    }
    counts = {
        family: sum(
            item.placement == "agent_capability"
            and item.capability_family == family
            and item.availability.available
            for item in components
        )
        for family in order
    }
    return tuple(
        StudioCapabilityFamilyDescriptor(
            family=family,
            label=labels[family],
            extension=family in {"grounder", "tool"},
            available_implementation_count=counts[family],
        )
        for family in order
    )


def _catalog_version(
    components: tuple[StudioComponentDescriptor, ...],
    provider_report: StudioProviderReport,
) -> str:
    """Hash only safe semantic Catalog metadata.

    Args:
        components (tuple[StudioComponentDescriptor, ...]): Ordered descriptors.
        provider_report (StudioProviderReport): Safe provider state.

    Raises:
        ValueError: Metadata is not JSON serializable.

    Returns:
        str: SHA-256-prefixed Catalog identity.
    """
    payload = {
        "components": [
            item.model_dump(mode="json", by_alias=True, exclude_none=True)
            for item in components
        ],
        "providerReport": provider_report.model_dump(
            mode="json",
            by_alias=True,
            exclude_none=True,
        ),
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def build_studio_component_catalog(
    *,
    built_in_catalog: BuiltInComponentCatalog = BUILTIN_COMPONENT_CATALOG,
    external_environment: DiscoveredComponentEnvironment | None = None,
) -> StudioComponentCatalog:
    """Assemble built-in and explicitly discovered external declarations.

    This function does not scan entry points, instantiate components, resolve
    secrets, connect devices, or create a Runtime. Callers must supply an
    already explicit external environment when external components are wanted.

    Args:
        built_in_catalog (BuiltInComponentCatalog): Import-safe built-in
            declaration catalog.
        external_environment (DiscoveredComponentEnvironment | None): Explicit
            external declaration result.

    Raises:
        None: Provider and contract failures are represented as diagnostics.

    Returns:
        StudioComponentCatalog: Deterministic safe authoring Catalog.
    """
    environment = external_environment or empty_component_environment()
    descriptors: list[StudioComponentDescriptor] = []
    diagnostics: list[GraphDiagnostic] = []
    contract_by_key: dict[tuple[str, str], NodeContract] = {}

    for specification in built_in_catalog.entries():
        contract = _contract_for_builtin(specification.namespace, specification.name)
        if contract is None:
            diagnostics.append(
                GraphDiagnostic(
                    code="studio.catalog.contract_missing",
                    message=(
                        f"Built-in component {specification.identifier} has no "
                        "authoring NodeContract"
                    ),
                    severity=DiagnosticSeverity.WARNING,
                )
            )
            continue
        contract_by_key[(contract.ref.id, contract.ref.version)] = contract
        role = _ROLE_BY_NAMESPACE.get(specification.namespace)
        safe_capabilities = {
            "fallback": contract.features.fallback,
            "local_loop": contract.features.local_loop,
            "state_access": contract.features.state_access,
            "runtime_service": contract.features.runtime_service,
        }
        placement, family, termination = _catalog_authoring_classification(
            namespace=specification.namespace,
            name=specification.name,
            category=_category_for_builtin(specification.namespace),
            role=role,
            contract=contract,
            capabilities=safe_capabilities,
        )
        descriptors.append(
            StudioComponentDescriptor(
                identifier=(
                    f"{specification.namespace}:{specification.name}@"
                    f"{specification.version}"
                ),
                namespace=specification.namespace,
                name=specification.name,
                version=specification.version,
                provider_id="zhixing",
                contract=contract,
                category=_category_for_builtin(specification.namespace),
                role=role.value if role else None,
                placement=placement,
                capability_family=family,
                termination=termination,
                config_schema=_BUILTIN_CONFIG_SCHEMAS.get(
                    (specification.namespace, specification.name),
                    _object_schema(),
                ),
                dependency_slots=tuple(
                    item.to_safe_dict() for item in specification.dependency_slots
                ),
                availability=_availability(specification),
                capabilities=safe_capabilities,
                provenance={
                    "kind": "framework",
                    "module": specification.module,
                },
                display={
                    "label": specification.name.replace("_", " ").title(),
                    "group": (
                        role.value
                        if role
                        else _category_for_builtin(specification.namespace)
                    ),
                },
            )
        )

    action_contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(
        contract_ref_for_role(GraphRole.ACTION_EXECUTOR)
    )
    if action_contract is not None:
        descriptors.append(
            StudioComponentDescriptor(
                identifier="studio.capability:action_executor@1",
                namespace="studio.capability",
                name="action_executor",
                version="1",
                provider_id="zhixing",
                contract=action_contract,
                category=ComponentCategory.CORE_AGENT.value,
                role=GraphRole.ACTION_EXECUTOR.value,
                placement="agent_capability",
                capability_family="action_executor",
                termination={
                    "predicate": {
                        "field": "terminal_status",
                        "operator": "exists",
                    },
                    "sourcePort": "result",
                },
                config_schema=_object_schema(),
                capabilities={"framework_lowered": True},
                provenance={"kind": "framework", "loweredService": True},
                display={"label": "Action Executor", "group": "action_executor"},
            )
        )

    for entry in environment.catalog.entries():
        metadata = entry.specification.safe_metadata()
        contract = entry.specification.contract
        key = (contract.ref.id, contract.ref.version)
        previous = contract_by_key.get(key)
        if previous is not None and previous != contract:
            diagnostics.append(
                GraphDiagnostic(
                    code="studio.catalog.contract_conflict",
                    message=(
                        f"Provider {entry.provider_id!r} declares a conflicting "
                        f"NodeContract {key[0]}@{key[1]}"
                    ),
                )
            )
            continue
        contract_by_key[key] = contract
        external_capabilities = dict(metadata["capabilities"])
        role = entry.specification.role
        placement, family, termination = _catalog_authoring_classification(
            namespace=entry.specification.namespace,
            name=entry.specification.name,
            category=entry.specification.category.value,
            role=role,
            contract=contract,
            capabilities=external_capabilities,
        )
        descriptors.append(
            StudioComponentDescriptor(
                identifier=entry.specification.identifier,
                namespace=entry.specification.namespace,
                name=entry.specification.name,
                version=entry.specification.version,
                provider_id=entry.provider_id,
                contract=contract,
                category=entry.specification.category.value,
                role=(
                    role.value
                    if role is not None
                    else None
                ),
                placement=placement,
                capability_family=family,
                termination=termination,
                config_schema=dict(metadata["config_schema"]),
                dependency_slots=tuple(metadata.get("dependency_slots", ())),
                availability=StudioComponentAvailability(available=True),
                capabilities=external_capabilities,
                provenance=entry.origin.to_safe_dict() if entry.origin else {},
                display={
                    "label": entry.specification.name.replace("_", " ").title(),
                    "group": entry.specification.category.value,
                },
            )
        )

    report = StudioProviderReport(
        loaded_provider_ids=environment.report.loaded_provider_ids,
        skipped_provider_ids=environment.report.skipped_provider_ids,
        failures=tuple(
            {
                "providerId": failure.provider_id,
                "stage": failure.stage,
                "code": failure.code,
                "errorType": failure.error_type,
                "message": failure.message,
            }
            for failure in environment.report.failures
        ),
    )
    for failure in environment.report.failures:
        diagnostics.append(
            GraphDiagnostic(
                code=failure.code,
                message=(
                    f"Component provider {failure.provider_id!r} failed during "
                    f"{failure.stage} ({failure.error_type})"
                ),
                severity=DiagnosticSeverity.WARNING,
            )
        )
    ordered = tuple(
        sorted(
            descriptors,
            key=lambda item: (
                item.namespace,
                item.name,
                item.version,
                item.provider_id,
            ),
        )
    )
    return StudioComponentCatalog(
        catalog_version=_catalog_version(ordered, report),
        components=ordered,
        capability_families=_capability_family_descriptors(ordered),
        provider_report=report,
        diagnostics=tuple(sorted(diagnostics, key=lambda item: item.sort_key())),
    )


__all__ = [
    "StudioCapabilityFamilyDescriptor",
    "StudioComponentAvailability",
    "StudioComponentCatalog",
    "StudioComponentDescriptor",
    "StudioProviderReport",
    "build_studio_component_catalog",
]
