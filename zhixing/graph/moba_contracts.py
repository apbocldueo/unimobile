"""Import-safe six-role MobA source-stage contracts, with explicit effect boundaries."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs=(('result', 'moba_frame'),), effect=SideEffectKind.NONE):
    """Declare a scheduled stage. Args: name,inputs,outputs: Ports; effect: External effect.

    Returns: NodeContract: Inert typed invocation metadata.
    """
    return NodeContract(ref=NodeContractRef(id='zhixing.moba.' + name, version='1.0'),
        ports=(ContractPort(id='control', direction=PortDirection.INPUT, data_types=('control',)),
            *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                cardinality=PortCardinality.MULTIPLE if key == 'values' else PortCardinality.SINGLE)
              for key, kind in inputs),
            *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


MOBA_NODE_CONTRACTS = (
    _contract('initialize', (('task', 'task_input'),)),
    _contract('resume', (('initial', 'moba_frame'), ('previous', 'any'))),
    _contract('pass', (('frame', 'moba_frame'),)),
    _contract('join', (('values', 'moba_frame'),)),
    _contract('commit', (('values', 'moba_frame'),)),
    _contract('load', (('frame', 'moba_frame'),), effect=SideEffectKind.WRITE),
    _contract('observe', (('frame', 'moba_frame'),), effect=SideEffectKind.READ),
    *(_contract(name, (('frame', 'moba_frame'),)) for name in
      ('prepare', 'perceive', 'reason', 'resolve_app', 'plan', 'verify', 'record', 'split', 'advance')),
    _contract('persist', (('frame', 'moba_frame'),), effect=SideEffectKind.WRITE),
    _contract('execute', (('frame', 'moba_frame'),), (('result', 'moba_frame'), ('ack', 'action_result')),
              SideEffectKind.DEVICE_ACTION),
    _contract('wait_round', (('frame', 'moba_frame'),), effect=SideEffectKind.READ),
    _contract('finish', (('frame', 'moba_frame'),), (('result', 'any'),), SideEffectKind.WRITE),
)
