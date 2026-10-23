"""Inert EcoAgent typed ports, using only existing six-family and generic control contracts."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare one stage. Args: name,inputs,outputs,effect: Schema. Returns: NodeContract: Inert declaration."""
    return NodeContract(ref=NodeContractRef(id='zhixing.ecoagent.' + name, version='1.0'),
        ports=(ContractPort(id='control', direction=PortDirection.INPUT, data_types=('control',)),
            *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                cardinality=PortCardinality.MULTIPLE if key == 'values' else PortCardinality.SINGLE) for key, kind in inputs),
            *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


F = 'ecoagent_frame'
ECOAGENT_NODE_CONTRACTS = (
    _contract('initialize', (('task', 'task_input'),), (('result', F),)),
    _contract('resume', (('initial', F), ('previous', 'any')), (('result', F),)),
    _contract('frame', (('frame', F),), (('result', F),)),
    _contract('read', (('frame', F),), (('result', F),), SideEffectKind.READ),
    _contract('execute', (('frame', F),), (('result', F), ('ack', 'action_result')), SideEffectKind.DEVICE_ACTION),
    _contract('merge', (('values', F),), (('result', F),)),
    _contract('finish', (('frame', F),), (('result', 'any'),)),
)
