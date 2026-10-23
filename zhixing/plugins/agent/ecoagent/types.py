"""Portable EcoAgent state and model replies; no clients or Futures enter State."""

from dataclasses import dataclass

from zhixing.components import ActionResult, DeviceObservation, TaskInput


@dataclass(frozen=True)
class EcoReply:
    """One model text and optional reported usage, without a live HTTP response."""

    text: str
    total_tokens: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    has_usage: bool = False


@dataclass(frozen=True)
class EcoFrame:
    """Original online cursor plus graph-only portable action and routing data."""

    task: TaskInput
    round: int = 0
    steps: tuple[str, ...] = ()
    expectations: tuple[str, ...] = ()
    descriptions: tuple[str, ...] = ()
    before: DeviceObservation | None = None
    after: DeviceObservation | None = None
    summary: str = ''
    description: str = ''
    accepted: bool = False
    next_step: str = ''
    selected_step: str = ''
    action_output: str = ''
    prediction_ticket: str = ''
    description_ticket: str = ''
    summary_ticket: str = ''
    reuse_prediction: bool = False
    cloud_calls: int = 0
    cloud_tokens: int = 0
    success: bool = False
    finished: bool = False
    fix_protocol: bool = True
    actions: tuple[ActionResult, ...] = ()


def reply(value) -> EcoReply:
    """Require a portable model reply instead of guessing provider tuple formats.

    Args:
        value: Model dependency return value.
    Raises:
        TypeError: The dependency violates the explicit EcoAgent protocol.
    Returns:
        EcoReply: Validated portable response.
    """
    if (not isinstance(value, EcoReply) or not isinstance(value.text, str) or
            any(type(v) is not int or v < 0 for v in
                (value.total_tokens, value.prompt_tokens, value.completion_tokens))):
        raise TypeError('EcoAgent complete() must return EcoReply')
    return value
