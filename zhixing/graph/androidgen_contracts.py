"""Import-safe AndroidGen stage contracts using the existing six role families."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare typed data-only ports and explicit device-effect boundaries.

    Args:
        name: Stable stage suffix.
        inputs: Ordered input name/type pairs.
        outputs: Ordered output name/type pairs.
        effect: Boundary effect policy.
    Returns:
        NodeContract: Exact versioned extension without changing core role DTOs.
    """
    return NodeContract(ref=NodeContractRef(id="zhixing.androidgen." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
            *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                cardinality=PortCardinality.MULTIPLE if key == "values" else PortCardinality.SINGLE) for key, kind in inputs),
            *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


ANDROIDGEN_NODE_CONTRACTS = (
    _contract("setup", (("task", "task_input"),), (("seed", "androidgen_seed"),), SideEffectKind.DEVICE_ACTION),
    _contract("bootstrap", (("seed", "androidgen_seed"),), (("frame", "androidgen_frame"),)),
    _contract("resume", (("initial", "androidgen_frame"), ("previous", "any")), (("frame", "androidgen_frame"),)),
    _contract("history", (("frame", "androidgen_frame"),), (("fragment", "memory_fragment"), ("sequence", "control"))),
    _contract("ready", (("frame", "androidgen_frame"), ("memory", "memory_context")), (("result", "androidgen_frame"),)),
    _contract("pass", (("frame", "androidgen_frame"),), (("result", "androidgen_frame"),)),
    _contract("observe", (("frame", "androidgen_frame"),), (("observation", "device_observation"),), SideEffectKind.READ),
    _contract("perceive", (("frame", "androidgen_frame"), ("observation", "device_observation")), (("result", "androidgen_frame"),)),
    _contract("plan", (("frame", "androidgen_frame"), ("previous", "any")), (("result", "androidgen_frame"),)),
    _contract("feedback", (("frame", "androidgen_frame"),), (("result", "androidgen_frame"),)),
    _contract("reason", (("frame", "androidgen_frame"),), (("result", "androidgen_frame"),)),
    _contract("execute", (("frame", "androidgen_frame"),), (("result", "androidgen_frame"), ("ack", "action_result")), SideEffectKind.DEVICE_ACTION),
    _contract("commit", (("values", "androidgen_frame"),), (("frame", "androidgen_frame"),)),
    _contract("finish", (("frame", "androidgen_frame"),), (("result", "any"),)),
)
