"""GUI-explorer source-stage ports, reusing actual M3A cursor/view types."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortDirection


def _contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare one source operation without optional imports or runtime branching.

    Args:
        name: Stable stage suffix.
        inputs: Ordered input name/logical-type pairs.
        outputs: Ordered output name/logical-type pairs.
        effect: Explicit external-effect classification.
    Returns:
        NodeContract: Side-effect-free invocation metadata.
    """
    return NodeContract(ref=NodeContractRef(id="zhixing.guiexplorer." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True) for key, kind in inputs),
               *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


GUIEXPLORER_NODE_CONTRACTS = (
    _contract("history", (("frame", "m3a_frame"),), (("fragment", "memory_fragment"),)),
    _contract("observe", (("frame", "m3a_frame"),), (("observation", "device_observation"),), SideEffectKind.READ),
    _contract("perceive", (("observation", "device_observation"),), (("view", "m3a_view"),)),
    _contract("retrieve", (("view", "m3a_view"),), (("knowledge", "guiexplorer_knowledge"),), SideEffectKind.READ),
    _contract("rank", (("frame", "m3a_frame"), ("knowledge", "guiexplorer_knowledge")), (("ranked", "guiexplorer_knowledge"),)),
    _contract("select", (("frame", "m3a_frame"), ("knowledge", "guiexplorer_knowledge"), ("memory", "memory_context")), (("result", "m3a_frame"),)),
    _contract("execute", (("frame", "m3a_frame"),), (("result", "m3a_frame"), ("ack", "action_result")), SideEffectKind.DEVICE_ACTION),
    _contract("summary", (("frame", "m3a_frame"), ("view", "m3a_view")), (("result", "m3a_frame"),)),
    _contract("wait_round", (("frame", "m3a_frame"),), (("result", "m3a_frame"),), SideEffectKind.READ),
    _contract("finish", (("frame", "m3a_frame"),), (("result", "any"),)),
)
