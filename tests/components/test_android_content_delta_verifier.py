"""Tests for the task-independent Android content-delta verifier."""

from __future__ import annotations

from dataclasses import dataclass

from zhixing.components import (
    Action,
    ActionResult,
    ActionType,
    ExecutionStatus,
    RuntimeContext,
    VerifierInput,
)
from zhixing.plugins.agent.verifier.android_content_delta import (
    AndroidContentDeltaVerifier,
)
from zhixing.runtime.transforms import VerificationTerminalAction


@dataclass(frozen=True)
class ShellResult:
    """Represent one deterministic Android shell result."""

    output: str
    exit_code: int = 0


class ScriptedContentDevice:
    """Return a finite sequence of Android content query results."""

    def __init__(self, outputs: list[str]) -> None:
        """Store deterministic query outputs.

        Args:
            outputs (list[str]): Content-provider rows returned in order.

        Raises:
            ValueError: No output is provided.

        Returns:
            None: Initializes the fake shell-capable device.
        """
        if not outputs:
            raise ValueError("ScriptedContentDevice requires outputs")
        self.outputs = list(outputs)

    def shell(self, command: str) -> ShellResult:
        """Return the next content query result.

        Args:
            command (str): Validated Android content command.

        Raises:
            AssertionError: A non-content command reaches the verifier.
            IndexError: No scripted output remains.

        Returns:
            ShellResult: Next deterministic query response.
        """
        assert command.startswith("content query --uri ")
        return ShellResult(self.outputs.pop(0))


def _input(action_type: ActionType) -> VerifierInput:
    """Build one verifier input with the selected action.

    Args:
        action_type (ActionType): Action represented by the input.

    Raises:
        None.

    Returns:
        VerifierInput: Minimal typed verifier request.
    """
    action = Action(action_type)
    return VerifierInput(
        task="create one item",
        screenshot_before="before.png",
        screenshot_after="after.png",
        action=action,
        action_result=ActionResult(action, ExecutionStatus.SUCCESS),
    )


def test_content_delta_verifier_establishes_baseline_then_detects_addition() -> None:
    """Complete only after a later query adds the configured number of rows.

    Args:
        None.

    Raises:
        AssertionError: Baseline or delta behavior is incorrect.

    Returns:
        None.
    """
    runtime = RuntimeContext(
        run_id="content-run",
        device=ScriptedContentDevice(
            [
                "Row: 0 _id=7",
                "Row: 0 _id=7\nRow: 1 _id=8",
            ]
        ),
    )
    verifier = AndroidContentDeltaVerifier()
    baseline = verifier.invoke(_input(ActionType.START_APP), runtime)
    completed = verifier.invoke(_input(ActionType.TAP), runtime)
    assert not baseline.is_success
    assert baseline.should_retry
    assert baseline.metadata["baseline_captured"]
    assert completed.is_success
    assert not completed.should_retry
    assert completed.metadata["added_ids"] == ("8",)


def test_content_delta_verifier_uses_run_metadata_baseline() -> None:
    """Allow a GUI or runner to inject a pre-run baseline without task logic.

    Args:
        None.

    Raises:
        AssertionError: Caller baseline is ignored.

    Returns:
        None.
    """
    runtime = RuntimeContext(
        run_id="metadata-run",
        device=ScriptedContentDevice(["Row: 0 _id=4\nRow: 1 _id=5"]),
        metadata={"android_content_baselines": {"images": ["4"]}},
    )
    verifier = AndroidContentDeltaVerifier(baseline_key="images")
    result = verifier.invoke(_input(ActionType.TAP), runtime)
    assert result.is_success
    assert result.metadata["added_ids"] == ("5",)


def test_verification_terminal_action_is_deterministic() -> None:
    """Map only final verification decisions into typed terminal actions.

    Args:
        None.

    Raises:
        AssertionError: Success and failure terminal actions are inverted.

    Returns:
        None.
    """
    transform = VerificationTerminalAction()
    success = transform.invoke(
        AndroidContentDeltaVerifier().invoke(
            _input(ActionType.TAP),
            RuntimeContext(
                run_id="terminal",
                device=ScriptedContentDevice(["Row: 0 _id=1"]),
                metadata={"android_content_baselines": {"android_content": []}},
            ),
        ),
        RuntimeContext(),
    )
    assert success.type is ActionType.DONE
