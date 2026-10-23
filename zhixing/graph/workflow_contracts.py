"""Import-safe ports for individually scheduled legacy workflow operations."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs):
    """Declare a data-only role boundary without importing component code.

    Args:
        name: Stable contract suffix.
        inputs: Port/type pairs; a values port accepts selected branch results.
        outputs: Port/type pairs.
    Returns:
        NodeContract: Immutable typed-invoke declaration.
    """
    return NodeContract(
        ref=NodeContractRef(id="zhixing.workflow." + name, version="1.0"),
        ports=(ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
               *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                    cardinality=PortCardinality.MULTIPLE if key == "values" else PortCardinality.SINGLE)
                 for key, kind in inputs),
               *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )


WORKFLOW_NODE_CONTRACTS = (
    _contract("initialize", (("task", "task_input"),), (("result", "workflow_frame"),)),
    _contract("frame", (("value", "workflow_frame"),), (("result", "workflow_frame"),)),
    _contract("resume", (("initial", "workflow_frame"), ("previous", "any")), (("result", "workflow_frame"),)),
    _contract("merge", (("values", "workflow_frame"),), (("result", "workflow_frame"),)),
    _contract("observe_request", (("value", "workflow_frame"),), (("request", "observation_request"),)),
    _contract("observed", (("value", "workflow_frame"), ("observation", "device_observation")), (("result", "workflow_frame"),)),
    _contract("action_request", (("value", "workflow_frame"),), (("request", "action_execution_input"),)),
    _contract("executed", (("value", "workflow_frame"), ("ack", "action_result")), (("result", "workflow_frame"),)),
    _contract("finish", (("value", "workflow_frame"),), (("result", "action_result"),)),
    _contract("setup", (("value", "workflow_frame"),), (("result", "workflow_frame"),)).model_copy(
        update={"side_effect": SideEffectKind.DEVICE_ACTION, "idempotent": False}),
)
