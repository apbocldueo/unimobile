from unimobile.core.interfaces import BaseVerifier
from unimobile.core.protocol import VerifierInput, VerifierResult, ActionType
from unimobile.utils.registry import register_verifier


@register_verifier("example_verifier")
class ExampleVerifier(BaseVerifier):
    """
    Example Verifier
    Always marks TAP actions as successful.
    """

    def verify(self, input_data: VerifierInput) -> VerifierResult:
        action = input_data.action

        if action.type == ActionType.TAP:
            return VerifierResult(
                is_success=True,
                feedback="Tap action assumed successful"
            )

        return VerifierResult(
            is_success=True,
            feedback="Action skipped verification"
        )