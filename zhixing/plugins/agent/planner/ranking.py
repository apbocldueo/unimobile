"""General ordered score selection, independent of any particular Agent strategy."""

from __future__ import annotations

import math
from dataclasses import dataclass

from zhixing.core.factory import PluginRegistry


@dataclass(frozen=True)
class ScoredOptions:
    """An ordered collection of text options and their corresponding rewards."""

    options: tuple[str, ...]
    scores: tuple[float, ...]

    def __post_init__(self) -> None:
        """Reject missing, non-finite or misaligned scores before selecting.

        Raises:
            ValueError: Options/scores are empty, mutable, malformed or misaligned.
        Returns:
            None.
        """
        if (not isinstance(self.options, tuple) or not isinstance(self.scores, tuple)
                or not self.options or len(self.options) != len(self.scores)
                or any(not isinstance(option, str) for option in self.options)
                or any(type(score) not in (float, int) or not math.isfinite(score) for score in self.scores)):
            raise ValueError("ordered options require aligned finite numeric scores")


@dataclass(frozen=True)
class RankedOption:
    """The selected original option, its stable position and reward."""

    option: str
    index: int
    score: float


@PluginRegistry.register(namespace="agent.planner", name="ordered_argmax")
class OrderedArgmax:
    """Select the first maximum; preserve order and never call a model."""

    def invoke(self, input: ScoredOptions, runtime) -> RankedOption:
        """Select a scored text option using a strict greater-than comparison.

        Args:
            input: Validated ordered options and finite scores.
            runtime: Unused shared runtime context.
        Raises:
            TypeError: Input does not implement the declared score contract.
        Returns:
            RankedOption: First maximum, including its unchanged original text.
        """
        del runtime
        if not isinstance(input, ScoredOptions):
            raise TypeError("ordered_argmax requires ScoredOptions")
        index = max(range(len(input.scores)), key=input.scores.__getitem__)
        return RankedOption(input.options[index], index, float(input.scores[index]))
