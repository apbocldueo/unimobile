"""Import-safe contracts for UI selection adapters and reusable ordered ranking."""

from .contracts import ContractPort, InvocationAdapterKind, NodeContract, NodeContractRef
from .enums import PortDirection


def _contract(name: str, incoming: str, outgoing: str) -> NodeContract:
    """Declare one typed data transform without importing runtime plugins.

    Args:
        name: Stable namespaced contract ID.
        incoming: Single required value-port type.
        outgoing: Single result-port type.
    Returns:
        NodeContract: Side-effect-free transform declaration.
    """
    return NodeContract(
        ref=NodeContractRef(id=name, version="1.0"),
        ports=(ContractPort(id="value", direction=PortDirection.INPUT, data_types=(incoming,), required=True),
               ContractPort(id="result", direction=PortDirection.OUTPUT, data_types=(outgoing,))),
        adapter=InvocationAdapterKind.TYPED_INVOKE,
    )


VDROID_NODE_CONTRACTS = (
    _contract("zhixing.vdroid.html", "vdroid_decision_request", "vdroid_ui_context"),
    _contract("zhixing.vdroid.candidates", "vdroid_ui_context", "vdroid_candidate_context"),
    _contract("zhixing.vdroid.scores", "vdroid_candidate_context", "scored_text_options"),
    _contract("zhixing.selection.ordered_argmax", "scored_text_options", "ranked_text_option"),
)
