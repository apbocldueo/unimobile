"""Import-safe contracts for source-aligned VisionTasker component stages."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef, SideEffectKind
from .enums import PortCardinality, PortDirection


def _contract(name, inputs, outputs, effect=SideEffectKind.NONE):
    """Declare one scheduled source stage without importing runtime implementations.

    Args:
        name: Stable stage suffix.
        inputs, outputs: Ordered port names and logical types.
        effect: Explicit external-effect classification.
    Returns:
        NodeContract: Versioned invocation metadata.
    """
    return NodeContract(ref=NodeContractRef(id='zhixing.visiontasker.' + name, version='1.0'),
        ports=(ContractPort(id='control', direction=PortDirection.INPUT, data_types=('control',)),
            *(ContractPort(id=key, direction=PortDirection.INPUT, data_types=(kind,), required=True,
                cardinality=PortCardinality.MULTIPLE if key == 'values' else PortCardinality.SINGLE)
              for key, kind in inputs),
            *(ContractPort(id=key, direction=PortDirection.OUTPUT, data_types=(kind,)) for key, kind in outputs)),
        adapter=InvocationAdapterKind.TYPED_INVOKE, side_effect=effect,
        idempotent=effect is not SideEffectKind.DEVICE_ACTION)


VISIONTASKER_NODE_CONTRACTS = (
    _contract('initialize', (('task', 'task_input'),), (('result', 'visiontasker_frame'),)),
    _contract('resume', (('initial', 'visiontasker_frame'), ('previous', 'any')), (('result', 'visiontasker_frame'),)),
    _contract('observe', (('frame', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),), SideEffectKind.READ),
    _contract('verify', (('frame', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),)),
    _contract('feedback', (('frame', 'visiontasker_frame'),),
        (('result', 'visiontasker_frame'), ('user', 'memory_fragment'), ('assistant', 'memory_fragment'), ('ready', 'control'))),
    _contract('perceive', (('frame', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),)),
    _contract('reason', (('frame', 'visiontasker_frame'), ('memory', 'memory_context')), (('result', 'visiontasker_frame'),)),
    _contract('parse', (('frame', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),)),
    _contract('record', (('frame', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),)),
    _contract('pass', (('frame', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),)),
    _contract('execute', (('frame', 'visiontasker_frame'),),
        (('result', 'visiontasker_frame'), ('ack', 'action_result')), SideEffectKind.DEVICE_ACTION),
    _contract('commit', (('values', 'visiontasker_frame'),), (('result', 'visiontasker_frame'),)),
    _contract('finish', (('frame', 'visiontasker_frame'),), (('result', 'any'),)),
)
