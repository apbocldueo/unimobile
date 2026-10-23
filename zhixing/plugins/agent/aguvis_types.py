"""Inert values for the published Aguvis CLI protocol and online adaptation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from zhixing.components import Action, ActionResult, DeviceObservation, MemoryFragment, RunStatus


@dataclass(frozen=True)
class AguvisRequest:
    """One source-style prediction; no device or live model handles."""

    instruction: str
    screenshot_path: str
    previous_actions: tuple[str, ...] = ()
    mode: Literal["self-plan", "force-plan", "grounding"] = "self-plan"
    low_level_instruction: str | None = None


@dataclass(frozen=True)
class AguvisCommand:
    """Either one existing typed device/control action or an inert answer."""

    action: Action | None = None
    answer: str | None = None


@dataclass(frozen=True)
class AguvisDecision:
    """One model decision, potentially containing several ordered commands."""

    commands: tuple[AguvisCommand, ...]
    description: str
    step: int = 1


@dataclass(frozen=True)
class AguvisBatch:
    """Portable graph cursor with confirmed prefix and separate answer output."""

    decision: AguvisDecision
    observation: DeviceObservation
    index: int = 0
    completed: tuple[ActionResult, ...] = ()
    answers: tuple[str, ...] = ()

    @property
    def next_is_answer(self) -> bool:
        """Select the inert answer branch for the current command.

        Returns:
            bool: Whether the next command has no device action.
        """
        return self.decision.commands[self.index].action is None

    @property
    def terminal_status(self) -> RunStatus | None:
        """Read actual terminal/failure acknowledgments, never answer text.

        Returns:
            RunStatus | None: Terminal Agent state, independent of Benchmark.
        """
        if self.completed:
            last = self.completed[-1]
            return last.terminal_status or (RunStatus.FAILURE if not last.succeeded else None)
        return None

    @property
    def finished(self) -> bool:
        """Indicate command exhaustion or an acknowledged failure/terminal.

        Returns:
            bool: Whether the inner command loop must stop.
        """
        return self.index >= len(self.decision.commands) or self.terminal_status is not None

    @property
    def history_fragment(self) -> MemoryFragment | None:
        """Expose only fully completed nonterminal decisions as exact TEXT.

        Returns:
            MemoryFragment | None: Successful decision description, or no append.
        """
        if not self.finished or self.terminal_status is not None:
            return None
        from zhixing.core.agent.protocol import FragmentType
        return MemoryFragment("assistant", FragmentType.TEXT,
            f"Step {self.decision.step}: {self.decision.description}",
            {"source": "aguvis.low_level", "decision": self.decision.step})
