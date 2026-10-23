"""Static Agent-SAMA extension ports; schema imports never load plugin packages."""

from zhixing.graph.contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from zhixing.graph.enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs, *, effect=SideEffectKind.NONE):
    """Declare one strategy boundary using existing typed-invoke semantics.

    Args:
        name: Stable contract suffix.
        inputs: Input port/type pairs.
        outputs: Output port/type pairs.
        effect: Explicit side-effect classification.
    Returns:
        NodeContract: Immutable extension contract.
    """
    return NodeContract(ref=NodeContractRef(id="zhixing.sama." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True) for key, kind in inputs),
               *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect, idempotent=effect is not SideEffectKind.DEVICE_ACTION)


SAMA_NODE_CONTRACTS = (
    NodeContract(ref=NodeContractRef(id="zhixing.sama.merge", version="1.0"),
        ports=(ContractPort(id="values", direction=PortDirection.INPUT, data_types=("sama_frame",),
                            required=True, cardinality=PortCardinality.MULTIPLE),
               ContractPort(id="result", direction=PortDirection.OUTPUT, data_types=("sama_frame",))),
        adapter=InvocationAdapterKind.TYPED_INVOKE),
    _contract("resume_frame", (("initial", "sama_frame"), ("previous", "any")), (("result", "sama_frame"),)),
    _contract("finish", (("value", "sama_frame"), ("ack", "action_result")), (("result", "any"),)),
    _contract("initialize", (("task", "task_input"),), (("result", "sama_frame"),)),
    _contract("frame", (("value", "sama_frame"),), (("result", "sama_frame"),)),
    _contract("identity_before", (("value", "sama_frame"),), (("result", "sama_frame"),), effect=SideEffectKind.READ),
    _contract("identity_after", (("value", "sama_frame"), ("observation", "device_observation")), (("result", "sama_frame"),), effect=SideEffectKind.READ),
    _contract("observation_request", (("value", "sama_frame"),), (("request", "observation_request"),)),
    _contract("action_request", (("value", "sama_frame"),), (("request", "action_execution_input"),)),
    _contract("record_atom", (("value", "sama_frame"), ("ack", "action_result")), (("result", "sama_frame"),)),
)


def _official_contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare source-profile ports. Args: name,inputs,outputs,effect: Schema. Returns: NodeContract."""
    return NodeContract(ref=NodeContractRef(id="zhixing.sama.official." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                             cardinality=PortCardinality.MULTIPLE if key == "values" else PortCardinality.SINGLE) for key, kind in inputs),
               *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect, idempotent=effect is not SideEffectKind.DEVICE_ACTION)


SAMA_NODE_CONTRACTS += (
    _official_contract("frame", (("value", "sama_official_frame"),), (("result", "sama_official_frame"),)),
    _official_contract("read", (("value", "sama_official_frame"),), (("result", "sama_official_frame"),), SideEffectKind.READ),
    _official_contract("effect", (("value", "sama_official_frame"),), (("result", "sama_official_frame"), ("effect", "action_result")), SideEffectKind.DEVICE_ACTION),
    _official_contract("initialize", (("value", "task_input"),), (("result", "sama_official_frame"),)),
    _official_contract("finish", (("value", "sama_official_frame"),), (("result", "any"),)),
    _official_contract("resume", (("initial", "sama_official_frame"), ("previous", "any")), (("result", "sama_official_frame"),)),
    _official_contract("merge", (("values", "sama_official_frame"),), (("result", "sama_official_frame"),)),
)
