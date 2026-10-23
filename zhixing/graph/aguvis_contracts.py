"""Import-safe extension contracts for Aguvis and exact fragment Memory writes."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs) -> NodeContract:
    """Declare pure typed ports; device effects stay in the shared service.

    Args:
        name: Aguvis contract suffix.
        inputs: Input port/type pairs, with values accepting branch alternatives.
        outputs: Output port/type pairs.
    Returns:
        NodeContract: Static declaration with no plugin/model imports.
    """
    return NodeContract(ref=NodeContractRef(id="zhixing.aguvis." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                    cardinality=PortCardinality.MULTIPLE if key == "values" else PortCardinality.SINGLE)
                 for key, kind in inputs),
               *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE)


AGUVIS_NODE_CONTRACTS = (
    _contract("reason", (("task", "task_input"), ("perception", "perception_result"),
                         ("memory", "memory_context")), (("decision", "aguvis_decision"),)),
    _contract("prepare", (("decision", "aguvis_decision"), ("observation", "device_observation")), (("batch", "aguvis_batch"),)),
    _contract("resume", (("initial", "aguvis_batch"), ("previous", "any")), (("batch", "aguvis_batch"),)),
    _contract("request", (("value", "aguvis_batch"),), (("request", "action_execution_input"),)),
    _contract("advance", (("value", "aguvis_batch"), ("ack", "action_result")), (("batch", "aguvis_batch"),)),
    _contract("answer", (("value", "aguvis_batch"),), (("batch", "aguvis_batch"),)),
    _contract("merge", (("values", "aguvis_batch"),), (("batch", "aguvis_batch"),)),
    _contract("history", (("value", "any"),), (("fragment", "memory_fragment"),)),
    # This extension reuses the existing Memory role adapter without changing
    # zhixing.core.memory:1.0 or its canonical/default role-contract mapping.
    NodeContract(ref=NodeContractRef(id="zhixing.memory.fragments", version="1.0"),
        ports=(ContractPort(id="write", direction=PortDirection.INPUT, data_types=("memory_fragment",),
                            cardinality=PortCardinality.MULTIPLE),
               ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               ContractPort(id="context", direction=PortDirection.OUTPUT, data_types=("memory_context",))),
        adapter=InvocationAdapterKind.CORE_ROLE),
)
