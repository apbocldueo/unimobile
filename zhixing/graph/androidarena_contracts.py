"""Inert AndroidArena stage contracts using only the existing six role families."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare portable stage data and an explicit I/O effect policy.

    Args:
        name: Stable stage suffix.
        inputs: Ordered input name/type pairs.
        outputs: Ordered output name/type pairs.
        effect: Explicit read/device effect classification.
    Returns:
        NodeContract: An additive contract; core DTOs and roles are unchanged.
    """
    return NodeContract(ref=NodeContractRef(id='zhixing.androidarena.' + name, version='1.0'),
        ports=(ContractPort(id='control', direction=PortDirection.INPUT, data_types=('control',)),
            *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                cardinality=PortCardinality.MULTIPLE if key == 'values' else PortCardinality.SINGLE)
                for key, kind in inputs),
            *(ContractPort(id='result' if key == 'frame' else key,
                direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


F = 'androidarena_frame'
ANDROIDARENA_NODE_CONTRACTS = (
    _contract('initialize', (('task', 'task_input'),), (('frame', F),)),
    _contract('trial', (('initial', F), ('previous', 'any')), (('frame', F),)),
    _contract('resume', (('initial', F), ('previous', 'any')), (('frame', F),)),
    _contract('reset', (('frame', F),), (('frame', F),), SideEffectKind.DEVICE_ACTION),
    _contract('observe', (('frame', F),), (('frame', F), ('observation', 'any')), SideEffectKind.READ),
    _contract('perception', (('frame', F), ('observation', 'any')), (('frame', F),)),
    _contract('screen', (('frame', F),), (('frame', F),), SideEffectKind.READ),
    _contract('start', (('frame', F),), (('frame', F),)),
    _contract('reasoning', (('frame', F),), (('frame', F),)),
    _contract('execute', (('frame', F),), (('frame', F), ('ack', 'action_result')), SideEffectKind.DEVICE_ACTION),
    _contract('judge', (('frame', F),), (('frame', F),)),
    _contract('pass', (('frame', F),), (('frame', F),)),
    _contract('commit', (('values', F),), (('frame', F),)),
    _contract('reflection', (('frame', F),), (('frame', F),)),
    _contract('end_trial', (('values', F),), (('frame', F),)),
    _contract('finish', (('frame', F),), (('result', 'any'),)),
)
