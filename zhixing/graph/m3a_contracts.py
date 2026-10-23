"""Import-safe explicit M3A stage contracts; no optional runtime imports."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare one independently scheduled source operation.

    Args:
        name: Stable contract suffix.
        inputs: Ordered input port/logical-type pairs.
        outputs: Ordered output port/logical-type pairs.
        effect: Explicit device-effect policy.
    Returns:
        NodeContract: Import-safe typed stage declaration.
    """
    return NodeContract(ref=NodeContractRef(id="zhixing.m3a." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                    cardinality=PortCardinality.MULTIPLE if key == "values" else PortCardinality.SINGLE)
                 for key, kind in inputs),
               *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


M3A_NODE_CONTRACTS = (
    _contract("pass", (("frame", "m3a_frame"),), (("result", "m3a_frame"),)),
    _contract("termination", (("frame", "m3a_frame"),), (("result", "m3a_frame"),), SideEffectKind.READ),
    _contract("ready", (("frame", "m3a_frame"), ("memory", "memory_context")), (("result", "m3a_frame"),)),
    _contract("setup", (("task", "task_input"),), (("result", "task_input"),), SideEffectKind.DEVICE_ACTION),
    _contract("resume", (("task", "task_input"), ("previous", "any")), (("frame", "m3a_frame"),)),
    _contract("history", (("frame", "m3a_frame"),), (("fragment", "memory_fragment"),)),
    _contract("observe", (("frame", "m3a_frame"),), (("observation", "device_observation"),), SideEffectKind.READ),
    _contract("perceive", (("observation", "device_observation"),), (("view", "m3a_view"),)),
    _contract("select", (("frame", "m3a_frame"), ("view", "m3a_view"), ("memory", "memory_context")), (("result", "m3a_frame"),)),
    _contract("execute", (("frame", "m3a_frame"),), (("result", "m3a_frame"), ("ack", "action_result")), SideEffectKind.DEVICE_ACTION),
    _contract("summary", (("frame", "m3a_frame"), ("view", "m3a_view")), (("result", "m3a_frame"),)),
    _contract("commit", (("values", "m3a_frame"),), (("result", "m3a_frame"),)),
    _contract("finish", (("frame", "m3a_frame"),), (("result", "any"),)),
)
