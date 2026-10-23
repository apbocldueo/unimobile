"""Stateless typed transforms used by executable Mobile Agent graphs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionType,
    DeviceObservation,
    RuntimeContext,
    VerifierResult,
)
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="zhixing.runtime", name="device_observe")
@PluginRegistry.register(namespace="zhixing.runtime", name="action_executor")
class RuntimeServiceMarker:
    """Mark a node whose implementation is injected by the active runtime."""


@PluginRegistry.register(namespace="zhixing.control", name="action_request")
class ActionRequestAssembler:
    """Combine a decision and its observation into an execution request."""

    def invoke(
        self,
        input: Mapping[str, Any],
        runtime: RuntimeContext,
    ) -> ActionExecutionInput:
        """Build the typed request consumed by Android ActionExecutor.

        Args:
            input (Mapping[str, Any]): ``action`` and optional ``observation`` ports.
            runtime (RuntimeContext): Shared run context, retained for protocol parity.

        Raises:
            TypeError: Action or observation values do not match the contract.

        Returns:
            ActionExecutionInput: Typed device-action request.
        """
        del runtime
        action = input.get("action")
        observation = input.get("observation")
        if not isinstance(action, Action):
            raise TypeError("action_request requires an Action")
        if observation is not None and not isinstance(observation, DeviceObservation):
            raise TypeError("action_request observation must be DeviceObservation")
        return ActionExecutionInput(action=action, observation=observation)


@PluginRegistry.register(
    namespace="zhixing.control",
    name="verification_terminal_action",
)
class VerificationTerminalAction:
    """Convert a completed verification decision into a terminal Agent action."""

    def invoke(
        self,
        input: VerifierResult,
        runtime: RuntimeContext,
    ) -> Action:
        """Create DONE for verified success and FAIL for non-retryable failure.

        Args:
            input (VerifierResult): Typed verifier result selected by graph control.
            runtime (RuntimeContext): Shared run context, retained for protocol parity.

        Raises:
            TypeError: Input is not a VerifierResult.
            ValueError: A retryable result is routed to the terminal branch.

        Returns:
            Action: Deterministic DONE or FAIL action.
        """
        del runtime
        if not isinstance(input, VerifierResult):
            raise TypeError("verification_terminal_action requires VerifierResult")
        if input.should_retry and not input.is_success:
            raise ValueError("retryable verification cannot enter the terminal branch")
        action_type = ActionType.DONE if input.is_success else ActionType.FAIL
        return Action(
            type=action_type,
            thought=input.feedback or "Verifier selected a terminal outcome.",
            metadata={
                "source": "verifier",
                "verification_score": input.score,
            },
        )


__all__ = [
    "ActionRequestAssembler",
    "RuntimeServiceMarker",
    "VerificationTerminalAction",
]
