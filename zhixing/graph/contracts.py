"""Versioned node contracts and explicit, import-safe contract catalogs."""

from __future__ import annotations

from enum import Enum
from types import MappingProxyType
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import GraphRole, PortCardinality, PortDirection


class GraphContractModel(BaseModel):
    """Immutable, strict base for import-safe contract declarations."""

    model_config = ConfigDict(extra="forbid", validate_default=True, frozen=True)


class InvocationAdapterKind(str, Enum):
    """Stable adapter categories understood by the runtime binder."""

    CORE_ROLE = "core_role"
    TYPED_INVOKE = "typed_invoke"
    RUNTIME_SERVICE = "runtime_service"


class SideEffectKind(str, Enum):
    """Side-effect classification used to constrain fallback behavior."""

    NONE = "none"
    READ = "read"
    WRITE = "write"
    DEVICE_ACTION = "device_action"


class ContractPort(GraphContractModel):
    """One typed input or output in a versioned node contract."""

    id: str = Field(min_length=1, max_length=128)
    direction: PortDirection
    data_types: tuple[str, ...]
    required: bool = False
    cardinality: PortCardinality = PortCardinality.SINGLE

    @model_validator(mode="after")
    def _validate_types(self) -> "ContractPort":
        """Validate that a contract port declares stable data-type identifiers.

        Args:
            None.

        Raises:
            ValueError: The port has no type or contains a blank type identifier.

        Returns:
            ContractPort: The validated immutable port.
        """
        if not self.data_types or any(not item.strip() for item in self.data_types):
            raise ValueError("contract port requires non-blank data type identifiers")
        return self


class NodeContractRef(GraphContractModel):
    """Content-stable reference to one node contract version."""

    id: str = Field(min_length=1, max_length=160)
    version: str = Field(min_length=1, max_length=64)


class ExecutionFeatures(GraphContractModel):
    """Execution features explicitly permitted by a node contract."""

    fallback: bool = True
    local_loop: bool = False
    state_access: bool = False
    runtime_service: bool = False


class NodeContract(GraphContractModel):
    """Versioned node behavior and port declaration."""

    ref: NodeContractRef
    ports: tuple[ContractPort, ...]
    adapter: InvocationAdapterKind
    side_effect: SideEffectKind = SideEffectKind.NONE
    idempotent: bool = True
    features: ExecutionFeatures = Field(default_factory=ExecutionFeatures)
    core_role: GraphRole | None = None

    @model_validator(mode="after")
    def _validate_contract(self) -> "NodeContract":
        """Validate unique ports and safe side-effect fallback semantics.

        Args:
            None.

        Raises:
            ValueError: Duplicate ports or an unsafe idempotency declaration is found.

        Returns:
            NodeContract: The validated immutable contract.
        """
        port_ids = [port.id for port in self.ports]
        if len(port_ids) != len(set(port_ids)):
            raise ValueError("node contract port identifiers must be unique")
        if self.side_effect is SideEffectKind.DEVICE_ACTION and self.idempotent:
            raise ValueError("device action contracts cannot claim implicit idempotency")
        return self

    def port(self, port_id: str) -> ContractPort | None:
        """Look up a port by stable identifier.

        Args:
            port_id (str): Port identifier to resolve.

        Raises:
            None.

        Returns:
            ContractPort | None: Matching port, if present.
        """
        return next((port for port in self.ports if port.id == port_id), None)


class NodeContractCatalog:
    """Explicit catalog with deterministic conflict rejection."""

    def __init__(self, contracts: Iterable[NodeContract] = ()) -> None:
        """Create a catalog without scanning the Python environment.

        Args:
            contracts (Iterable[NodeContract]): Explicit contract declarations.

        Raises:
            ValueError: Two declarations conflict at the same ID and version.

        Returns:
            None.
        """
        entries: dict[tuple[str, str], NodeContract] = {}
        for contract in contracts:
            key = (contract.ref.id, contract.ref.version)
            previous = entries.get(key)
            if previous is not None and previous != contract:
                raise ValueError(f"conflicting node contract {key[0]}@{key[1]}")
            entries[key] = contract
        self._entries = MappingProxyType(entries)

    def resolve(self, reference: NodeContractRef) -> NodeContract | None:
        """Resolve one exact contract reference.

        Args:
            reference (NodeContractRef): Exact ID and version.

        Raises:
            None.

        Returns:
            NodeContract | None: Matching declaration, if registered.
        """
        return self._entries.get((reference.id, reference.version))

    def merge(self, extension: "NodeContractCatalog") -> "NodeContractCatalog":
        """Merge an explicit extension catalog after built-in definitions.

        Args:
            extension (NodeContractCatalog): Explicit caller-provided contracts.

        Raises:
            ValueError: The extension conflicts with an existing definition.

        Returns:
            NodeContractCatalog: New deterministic merged catalog.
        """
        return NodeContractCatalog((*self._entries.values(), *extension._entries.values()))

    def references(self) -> tuple[NodeContractRef, ...]:
        """Return catalog references in stable order.

        Args:
            None.

        Raises:
            None.

        Returns:
            tuple[NodeContractRef, ...]: Sorted exact references.
        """
        return tuple(
            self._entries[key].ref
            for key in sorted(self._entries)
        )


def _port(
    port_id: str,
    direction: PortDirection,
    *data_types: str,
    required: bool = False,
    multiple: bool = False,
) -> ContractPort:
    """Build a concise immutable contract port.

    Args:
        port_id (str): Stable port identifier.
        direction (PortDirection): Input or output direction.
        *data_types (str): Accepted logical data-type identifiers.
        required (bool): Whether an incoming value is required.
        multiple (bool): Whether multiple incoming values are accepted.

    Raises:
        ValueError: ContractPort validation rejects the declaration.

    Returns:
        ContractPort: Validated port declaration.
    """
    return ContractPort(
        id=port_id,
        direction=direction,
        data_types=tuple(data_types),
        required=required,
        cardinality=PortCardinality.MULTIPLE if multiple else PortCardinality.SINGLE,
    )


_IN = PortDirection.INPUT
_OUT = PortDirection.OUTPUT


def _core_contract(
    role: GraphRole,
    ports: tuple[ContractPort, ...],
    *,
    side_effect: SideEffectKind = SideEffectKind.NONE,
    idempotent: bool = True,
) -> NodeContract:
    """Create one stable built-in core-role contract.

    Args:
        role (GraphRole): Legacy role mapped to the contract.
        ports (tuple[ContractPort, ...]): Typed contract ports.
        side_effect (SideEffectKind): Declared side-effect class.
        idempotent (bool): Whether fallback after invocation is safe.

    Raises:
        ValueError: NodeContract validation rejects the declaration.

    Returns:
        NodeContract: Built-in role contract.
    """
    return NodeContract(
        ref=NodeContractRef(id=f"zhixing.core.{role.value}", version="1.0"),
        ports=ports,
        adapter=InvocationAdapterKind.CORE_ROLE,
        side_effect=side_effect,
        idempotent=idempotent,
        core_role=role,
    )


BUILTIN_NODE_CONTRACTS = (
    _core_contract(
        GraphRole.PERCEPTION,
        (
            _port("observation", _IN, "device_observation", required=True),
            _port("control", _IN, "control"),
            _port("perception", _OUT, "perception_result"),
        ),
    ),
    _core_contract(
        GraphRole.PLANNER,
        (
            _port("task", _IN, "task_input", required=True),
            _port("observation", _IN, "device_observation"),
            _port("control", _IN, "control"),
            _port("plan", _OUT, "plan_result"),
        ),
    ),
    _core_contract(
        GraphRole.REASONING,
        (
            _port("task", _IN, "task_input", required=True),
            _port("perception", _IN, "perception_result", required=True),
            _port("plan", _IN, "plan_result"),
            _port("memory", _IN, "memory_context"),
            _port("verification", _IN, "verifier_result"),
            _port("control", _IN, "control"),
            _port("action", _OUT, "action"),
        ),
    ),
    _core_contract(
        GraphRole.MEMORY,
        (
            _port("write", _IN, "task_input", "plan_result", "action", "action_result", "verifier_result", multiple=True),
            _port("control", _IN, "control"),
            _port("context", _OUT, "memory_context"),
        ),
    ),
    _core_contract(
        GraphRole.ACTION_EXECUTOR,
        (
            _port("action", _IN, "action", required=True),
            _port("observation", _IN, "device_observation"),
            _port("control", _IN, "control"),
            _port("result", _OUT, "action_result"),
        ),
        side_effect=SideEffectKind.DEVICE_ACTION,
        idempotent=False,
    ),
    _core_contract(
        GraphRole.VERIFIER,
        (
            _port("task", _IN, "task_input", required=True),
            _port("before", _IN, "device_observation", required=True),
            _port("after", _IN, "device_observation", required=True),
            _port("action", _IN, "action", required=True),
            _port("action_result", _IN, "action_result"),
            _port("control", _IN, "control"),
            _port("result", _OUT, "verifier_result"),
        ),
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.extension.grounder", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("observation", _IN, "device_observation", required=True),
            _port("target", _IN, "semantic_target", required=True),
            _port("result", _OUT, "grounding_result"),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.extension.tool", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("request", _IN, "tool_request", required=True),
            _port("result", _OUT, "tool_result"),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
        side_effect=SideEffectKind.WRITE,
        idempotent=False,
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.service.device_observe", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("request", _IN, "any"),
            _port("observation", _OUT, "device_observation"),
        ),
        adapter=InvocationAdapterKind.RUNTIME_SERVICE,
        side_effect=SideEffectKind.READ,
        features=ExecutionFeatures(runtime_service=True),
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.service.device_observe", version="2.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("request", _IN, "observation_request", required=True),
            _port("observation", _OUT, "device_observation"),
        ),
        adapter=InvocationAdapterKind.RUNTIME_SERVICE,
        side_effect=SideEffectKind.READ,
        features=ExecutionFeatures(runtime_service=True),
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.service.action_executor", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("request", _IN, "action_execution_input", required=True),
            _port("result", _OUT, "action_result"),
        ),
        adapter=InvocationAdapterKind.RUNTIME_SERVICE,
        side_effect=SideEffectKind.DEVICE_ACTION,
        idempotent=False,
        features=ExecutionFeatures(runtime_service=True),
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.control.transform", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("value", _IN, "any", required=True),
            _port("result", _OUT, "any"),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.control.action_request", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("action", _IN, "action", required=True),
            _port("observation", _IN, "device_observation"),
            _port("request", _OUT, "action_execution_input"),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    ),
    NodeContract(
        ref=NodeContractRef(id="zhixing.service.action", version="1.0"),
        ports=(
            _port("control", _IN, "control"),
            _port("request", _IN, "any", required=True),
            _port("result", _OUT, "any"),
        ),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
        side_effect=SideEffectKind.DEVICE_ACTION,
        idempotent=False,
    ),
)

BUILTIN_NODE_CONTRACT_CATALOG = NodeContractCatalog(BUILTIN_NODE_CONTRACTS)

CORE_ROLE_CONTRACT_REFS = MappingProxyType(
    {
        contract.core_role: contract.ref
        for contract in BUILTIN_NODE_CONTRACTS
        if contract.core_role is not None
    }
)


def contract_ref_for_role(role: GraphRole) -> NodeContractRef:
    """Map one legacy core role to its exact built-in contract.

    Args:
        role (GraphRole): Legacy V1 graph role.

    Raises:
        KeyError: The role has no built-in contract.

    Returns:
        NodeContractRef: Exact compatible contract reference.
    """
    return CORE_ROLE_CONTRACT_REFS[role]
