"""Bounded, run-owned SeeClick action history through the existing Memory role."""

from __future__ import annotations

from dataclasses import dataclass, field

from zhixing.components import Action, BaseMemory, MemoryInput, MemoryOperation, MemoryResult, RuntimeContext
from zhixing.core.agent.protocol import FragmentType, MemoryFragment
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.seeclick_action_parser import HISTORY_KEY, MAX_RESPONSE_CHARS


@dataclass
class _History:
    """Keep only inert task identity and the last four executed predictions."""

    task: str = ""
    actions: list[str] = field(default_factory=list)


@PluginRegistry.register(namespace="agent.memory", name="seeclick_memory")
class SeeClickMemory(BaseMemory):
    """Preserve source action text rather than generic Action/Thought summaries."""

    def invoke(self, input: MemoryInput, runtime: RuntimeContext) -> MemoryResult:
        """Append executed actions, read four fragments, or reset this run's state.

        Args:
            input: RESET, APPEND or READ using the shared Memory contract.
            runtime: Owner of the private task/history state.
        Raises:
            ValueError: An operation, task transition or action source is invalid.
        Returns:
            MemoryResult: At most four exact prediction strings in temporal order.
        """
        key = "seeclick.memory"
        if input.operation is MemoryOperation.RESET:
            runtime.state.strategy_state.pop(key, None)
            return MemoryResult(input.operation)
        state = runtime.state.strategy_state.setdefault(key, _History())
        if input.operation is MemoryOperation.APPEND:
            fragment = input.fragment
            if fragment is None:
                raise ValueError("SeeClick APPEND requires a fragment")
            if fragment.role == "user" and fragment.type is FragmentType.TEXT:
                task = str(fragment.content)
                if state.task and state.task != task:
                    raise ValueError("a new SeeClick task requires a fresh run")
                state.task = task
            elif fragment.type is FragmentType.ACTION:
                action = fragment.content
                raw = action.metadata.get(HISTORY_KEY) if isinstance(action, Action) else None
                if not isinstance(raw, str) or not 0 < len(raw) <= MAX_RESPONSE_CHARS:
                    raise ValueError("SeeClick history requires an original prediction")
                state.actions = [*state.actions[-3:], raw]
            # System/error fragments are not actions and must not displace the
            # four-action window. Device failures terminate via the executor.
            return MemoryResult(input.operation)
        if input.operation is not MemoryOperation.READ:
            raise ValueError("SeeClick Memory supports RESET, APPEND and READ")
        return MemoryResult(input.operation, fragments=tuple(
            MemoryFragment("assistant", FragmentType.TEXT, raw, {"source": "seeclick.action"})
            for raw in state.actions
        ))
