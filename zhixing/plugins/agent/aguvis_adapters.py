"""Pure graph plumbing for ordered Aguvis commands and exact Memory writes."""

from dataclasses import replace

from zhixing.components import ActionExecutionInput
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.aguvis_types import AguvisBatch


@PluginRegistry.register(namespace="agent.memory", name="aguvis_resume")
class AguvisResume:
    """Resume a cursor from loop-local state, initialized afresh for each batch."""

    def invoke(self, input, runtime):
        """Select a matching prior cursor or the explicit initial decision.

        Args:
            input: Initial batch and optional loop-local prior cursor.
            runtime: Unused context.
        Returns:
            AguvisBatch: Current cursor for this exact screenshot and decision.
        """
        del runtime
        initial, previous = input["initial"], input["previous"]
        if isinstance(previous, AguvisBatch) and previous.observation == initial.observation and previous.decision == initial.decision:
            return previous
        return initial


@PluginRegistry.register(namespace="agent.action_executor", name="aguvis_prepare")
class AguvisPrepare:
    """Attach the exact pre-decision observation to a new command cursor."""

    def invoke(self, input, runtime):
        """Initialize one logical decision without executing any command.

        Args:
            input: Decision and captured observation ports.
            runtime: Unused context.
        Returns:
            AguvisBatch: Fresh cursor with no confirmed effects.
        """
        del runtime
        return AguvisBatch(input["decision"], input["observation"])


@PluginRegistry.register(namespace="agent.action_executor", name="aguvis_request")
class AguvisAtomRequest:
    """Build a shared executor request only for the current physical/control atom."""

    def invoke(self, input, runtime):
        """Expose the next action; the graph router suppresses answer execution.

        Args:
            input: Current command cursor.
            runtime: Unused context.
        Returns:
            ActionExecutionInput | None: Explicit request or inert answer branch.
        """
        del runtime
        command = input.decision.commands[input.index]
        return ActionExecutionInput(command.action, input.observation) if command.action else None


@PluginRegistry.register(namespace="agent.memory", name="aguvis_advance")
class AguvisAdvance:
    """Commit only an acknowledged action; failures stop the remaining prefix."""

    def invoke(self, input, runtime):
        """Advance once and retain the precise ordered execution evidence.

        Args:
            input: Cursor and shared ActionResult acknowledgment.
            runtime: Unused context.
        Returns:
            AguvisBatch: Cursor after one attempted action.
        """
        del runtime
        batch, ack = input["value"], input["ack"]
        return replace(batch, index=batch.index + 1, completed=(*batch.completed, ack))


@PluginRegistry.register(namespace="agent.memory", name="aguvis_answer")
class AguvisAnswer:
    """Publish answer data without inventing a device effect or task completion."""

    def invoke(self, input, runtime):
        """Append the current answer in order and keep processing the batch.

        Args:
            input: Cursor pointing to an answer command.
            runtime: Run event sink, independent of device effects.
        Returns:
            AguvisBatch: Updated cursor and ordered answer data.
        """
        answer = input.decision.commands[input.index].answer
        runtime.emit(phase="answer", role="reasoning", component="aguvis", kind="answer",
                     payload={"text": answer})
        return replace(input, index=input.index + 1, answers=(*input.answers, answer))


@PluginRegistry.register(namespace="agent.memory", name="aguvis_merge")
class AguvisMerge:
    """Join mutually exclusive command branches without modifying their values."""

    def invoke(self, input, runtime):
        """Select exactly one delivered branch result.

        Args:
            input: One or more alternative cursor values.
            runtime: Unused context.
        Raises:
            ValueError: More than one branch or an invalid value was delivered.
        Returns:
            AguvisBatch: Unchanged selected value.
        """
        del runtime
        values = input if isinstance(input, (list, tuple)) else [input]
        if len(values) != 1 or not isinstance(values[0], AguvisBatch):
            raise ValueError("Aguvis branch must produce one cursor")
        return values[0]


@PluginRegistry.register(namespace="agent.memory", name="aguvis_history")
class AguvisHistory:
    """Convert completed decisions to exact generic TEXT-memory writes."""

    def invoke(self, input, runtime):
        """Return no initial/failed write and preserve successful descriptions.

        Args:
            input: Prior decision cursor or absent initial state.
            runtime: Unused context.
        Returns:
            MemoryFragment | None: One append per successful completed decision.
        """
        del runtime
        return input.history_fragment if isinstance(input, AguvisBatch) else None
