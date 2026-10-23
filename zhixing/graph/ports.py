"""Single source of truth for AgentGraph role and built-in node ports."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType

from .contracts import ContractPort, NodeContractCatalog
from .enums import DataTypeId, GraphRole, NodeKind, PortCardinality, PortDirection


@dataclass(frozen=True)
class PortDescriptor:
    id: str
    direction: PortDirection
    data_types: tuple[DataTypeId, ...]
    required: bool = False
    cardinality: PortCardinality = PortCardinality.SINGLE

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "direction": self.direction.value,
            "data_types": [item.value for item in self.data_types],
            "required": self.required,
            "cardinality": self.cardinality.value,
        }


def _control() -> PortDescriptor:
    return PortDescriptor("control", PortDirection.INPUT, (DataTypeId.CONTROL,), False)


ROLE_PORTS = MappingProxyType(
    {
        GraphRole.PERCEPTION: (
            PortDescriptor("observation", PortDirection.INPUT, (DataTypeId.DEVICE_OBSERVATION,), True),
            _control(),
            PortDescriptor("perception", PortDirection.OUTPUT, (DataTypeId.PERCEPTION_RESULT,)),
        ),
        GraphRole.PLANNER: (
            PortDescriptor("task", PortDirection.INPUT, (DataTypeId.TASK_INPUT,), True),
            PortDescriptor("observation", PortDirection.INPUT, (DataTypeId.DEVICE_OBSERVATION,), False),
            _control(),
            PortDescriptor("plan", PortDirection.OUTPUT, (DataTypeId.PLAN_RESULT,)),
        ),
        GraphRole.REASONING: (
            PortDescriptor("task", PortDirection.INPUT, (DataTypeId.TASK_INPUT,), True),
            PortDescriptor("perception", PortDirection.INPUT, (DataTypeId.PERCEPTION_RESULT,), True),
            PortDescriptor("plan", PortDirection.INPUT, (DataTypeId.PLAN_RESULT,), False),
            PortDescriptor("memory", PortDirection.INPUT, (DataTypeId.MEMORY_CONTEXT,), False),
            PortDescriptor("verification", PortDirection.INPUT, (DataTypeId.VERIFIER_RESULT,), False),
            _control(),
            PortDescriptor("action", PortDirection.OUTPUT, (DataTypeId.ACTION,)),
        ),
        GraphRole.MEMORY: (
            PortDescriptor(
                "write",
                PortDirection.INPUT,
                (
                    DataTypeId.TASK_INPUT,
                    DataTypeId.PLAN_RESULT,
                    DataTypeId.ACTION,
                    DataTypeId.ACTION_RESULT,
                    DataTypeId.VERIFIER_RESULT,
                ),
                False,
                PortCardinality.MULTIPLE,
            ),
            _control(),
            PortDescriptor("context", PortDirection.OUTPUT, (DataTypeId.MEMORY_CONTEXT,)),
        ),
        GraphRole.ACTION_EXECUTOR: (
            PortDescriptor("action", PortDirection.INPUT, (DataTypeId.ACTION,), True),
            PortDescriptor("observation", PortDirection.INPUT, (DataTypeId.DEVICE_OBSERVATION,), False),
            _control(),
            PortDescriptor("result", PortDirection.OUTPUT, (DataTypeId.ACTION_RESULT,)),
        ),
        GraphRole.VERIFIER: (
            PortDescriptor("task", PortDirection.INPUT, (DataTypeId.TASK_INPUT,), True),
            PortDescriptor("before", PortDirection.INPUT, (DataTypeId.DEVICE_OBSERVATION,), True),
            PortDescriptor("after", PortDirection.INPUT, (DataTypeId.DEVICE_OBSERVATION,), True),
            PortDescriptor("action", PortDirection.INPUT, (DataTypeId.ACTION,), True),
            PortDescriptor("action_result", PortDirection.INPUT, (DataTypeId.ACTION_RESULT,), False),
            _control(),
            PortDescriptor("result", PortDirection.OUTPUT, (DataTypeId.VERIFIER_RESULT,)),
        ),
    }
)


BUILTIN_PORTS = MappingProxyType(
    {
        NodeKind.INPUT: (
            PortDescriptor("task", PortDirection.OUTPUT, (DataTypeId.TASK_INPUT,)),
            PortDescriptor("observation", PortDirection.OUTPUT, (DataTypeId.DEVICE_OBSERVATION,)),
        ),
        NodeKind.CONDITION: (
            PortDescriptor(
                "value",
                PortDirection.INPUT,
                (DataTypeId.VERIFIER_RESULT, DataTypeId.ACTION_RESULT),
                True,
            ),
            PortDescriptor("true", PortDirection.OUTPUT, (DataTypeId.CONTROL,)),
            PortDescriptor("false", PortDirection.OUTPUT, (DataTypeId.CONTROL,)),
        ),
        NodeKind.OUTPUT: (
            PortDescriptor("result", PortDirection.INPUT, (DataTypeId.ACTION_RESULT, DataTypeId.RUN_RESULT), False),
            PortDescriptor("control", PortDirection.INPUT, (DataTypeId.CONTROL,), False, PortCardinality.MULTIPLE),
        ),
    }
)


def ports_for_node(node) -> tuple[PortDescriptor, ...]:
    if node.kind == NodeKind.COMPONENT:
        return ROLE_PORTS.get(node.role, ())
    return BUILTIN_PORTS.get(node.kind, ())


def port_for_node(node, port_id: str) -> PortDescriptor | None:
    return next((port for port in ports_for_node(node) if port.id == port_id), None)


def port_catalog_payload() -> dict[str, object]:
    return {
        "roles": {
            role.value: [port.to_dict() for port in ports]
            for role, ports in ROLE_PORTS.items()
        },
        "builtins": {
            kind.value: [port.to_dict() for port in ports]
            for kind, ports in BUILTIN_PORTS.items()
        },
        "dataTypes": [item.value for item in DataTypeId],
    }


def contract_ports_for_node(
    node,
    catalog: NodeContractCatalog,
) -> tuple[ContractPort, ...]:
    """Resolve contract 1.1 ports without instantiating components.

    Args:
        node (GraphNode): AgentGraph node declaration.
        catalog (NodeContractCatalog): Explicit contract catalog.

    Raises:
        None.

    Returns:
        tuple[ContractPort, ...]: Declared ports, or an empty tuple when the
        node contract cannot be resolved.
    """
    if node.kind is NodeKind.COMPONENT:
        reference = node.contract
        if reference is None and node.role is not None:
            from .contracts import contract_ref_for_role

            reference = contract_ref_for_role(node.role)
        contract = catalog.resolve(reference) if reference is not None else None
        return contract.ports if contract is not None else ()
    if node.kind is NodeKind.ROUTER and node.router is not None:
        return (
            ContractPort(
                id="value",
                direction=PortDirection.INPUT,
                data_types=("any",),
                required=True,
            ),
            *tuple(
                ContractPort(
                    id=case.id,
                    direction=PortDirection.OUTPUT,
                    data_types=("control",),
                )
                for case in node.router.cases
            ),
            ContractPort(
                id=node.router.default,
                direction=PortDirection.OUTPUT,
                data_types=("control",),
            ),
        )
    if node.kind is NodeKind.STATE and node.state is not None:
        ports = [
            ContractPort(
                id="control",
                direction=PortDirection.INPUT,
                data_types=("control",),
            )
        ]
        if node.state.operation.value == "write":
            ports.append(
                ContractPort(
                    id="write",
                    direction=PortDirection.INPUT,
                    data_types=(node.state.data_type,),
                    required=True,
                )
            )
        ports.append(
            ContractPort(
                id="value",
                direction=PortDirection.OUTPUT,
                data_types=(node.state.data_type,),
            )
        )
        return tuple(ports)
    if node.kind in {NodeKind.LOOP, NodeKind.SUBGRAPH}:
        specification = node.loop if node.kind is NodeKind.LOOP else node.subgraph
        if specification is None:
            return ()
        return (
            *tuple(
                ContractPort(
                    id=parent_port,
                    direction=PortDirection.INPUT,
                    data_types=("any",),
                    required=True,
                )
                for parent_port in specification.inputs
            ),
            *tuple(
                ContractPort(
                    id=parent_port,
                    direction=PortDirection.OUTPUT,
                    data_types=("any",),
                )
                for parent_port in specification.outputs
            ),
        )
    if node.kind is NodeKind.INPUT:
        return (
            ContractPort(id="task", direction=PortDirection.OUTPUT, data_types=("task_input",)),
            ContractPort(
                id="observation",
                direction=PortDirection.OUTPUT,
                data_types=("device_observation",),
            ),
            ContractPort(id="value", direction=PortDirection.OUTPUT, data_types=("any",)),
        )
    if node.kind is NodeKind.OUTPUT:
        return (
            ContractPort(
                id="result",
                direction=PortDirection.INPUT,
                data_types=("any",),
                required=False,
                cardinality=PortCardinality.MULTIPLE,
            ),
            ContractPort(
                id="control",
                direction=PortDirection.INPUT,
                data_types=("control",),
                required=False,
                cardinality=PortCardinality.MULTIPLE,
            ),
        )
    return tuple(
        ContractPort(
            id=port.id,
            direction=port.direction,
            data_types=tuple(item.value for item in port.data_types),
            required=port.required,
            cardinality=port.cardinality,
        )
        for port in ports_for_node(node)
    )
