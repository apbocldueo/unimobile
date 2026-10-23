"""Data-only episode plumbing around the existing sliding-window Memory component."""

from dataclasses import replace

from zhixing.components import Action, ActionResult, ActionType, ExecutionStatus, RunStatus
from zhixing.core.agent.protocol import FragmentType, MemoryFragment
from zhixing.core.factory import PluginRegistry

from .types import M3AFrame


@PluginRegistry.register(namespace="agent.memory", name="m3a_pass")
class M3APass:
    """Forward a branch value or wait for the explicitly connected Memory result."""

    def invoke(self, input, runtime):
        """Preserve frame identity after graph control/data dependencies are satisfied.

        Args:
            input: One frame, or frame/memory ports for the read/flush barrier.
            runtime: Unused context.
        Returns:
            M3AFrame: Unmodified selected frame.
        """
        del runtime
        return input["frame"] if isinstance(input, dict) else input


@PluginRegistry.register(namespace="agent.memory", name="m3a_resume")
class M3AResume:
    """Resume typed graph State without storing an Agent object or live service."""

    def __init__(self, max_rounds: int = 30) -> None:
        """Remember the independent official decision-round bound.

        Args:
            max_rounds: Maximum source step calls in one episode.
        Returns:
            None.
        """
        self.max_rounds = max_rounds

    def invoke(self, input, runtime):
        """Select the preceding committed round and route before new observations.

        Args:
            input: Task and optional previous run-scoped frame.
            runtime: Unused context.
        Raises:
            TypeError: State is neither empty nor a typed M3AFrame.
        Returns:
            M3AFrame: Continue, terminal flush, or budget flush route.
        """
        del runtime
        previous = input["previous"]
        if previous is not None and not isinstance(previous, M3AFrame):
            raise TypeError("invalid M3A episode state")
        frame = previous or M3AFrame(input["task"])
        return replace(frame, route="finish" if frame.done or frame.environment_done or frame.round_number >= self.max_rounds else "continue")


@PluginRegistry.register(namespace="agent.memory", name="m3a_history")
class M3AHistory:
    """Extract exact TEXT writes for a reusable, episode-sized Memory window."""

    def invoke(self, input, runtime):
        """Append the previous source summary exactly once, including terminal flush.

        Args:
            input: Resumed frame before the current Memory activation.
            runtime: Unused context.
        Returns:
            MemoryFragment | None: Exact source summary or no write for excluded errors.
        """
        del runtime
        if not input.append_history or input.step is None:
            return None
        return MemoryFragment("assistant", FragmentType.TEXT, input.step.summary,
            {"source": "m3a.summary", "decision_round": input.round_number})


@PluginRegistry.register(namespace="agent.memory", name="m3a_commit")
class M3ACommit:
    """Commit one selected branch as an official episode step and optional history."""

    def invoke(self, input, runtime):
        """Merge mutually exclusive branch values, then advance one decision round.

        Args:
            input: One-element list of terminal/feedback/execution/summary frames.
            runtime: Unused context.
        Raises:
            ValueError: The graph delivered zero or multiple branch results.
        Returns:
            M3AFrame: Committed round; finish routes only flush memory and stop.
        """
        del runtime
        if not isinstance(input, (tuple, list)) or len(input) != 1:
            raise ValueError("M3A must commit exactly one selected branch")
        frame = input[0]
        if frame.route == "finish":
            return replace(frame, finished=True)
        return replace(frame, round_number=frame.round_number + 1,
            episode=(*frame.episode, frame.step),
            history=(*frame.history, frame.step) if frame.append_history else frame.history)


@PluginRegistry.register(namespace="agent.memory", name="m3a_finish")
class M3AFinish:
    """Publish all acknowledgments and truthful terminal/decision-budget evidence."""

    def invoke(self, input, runtime):
        """Separate source episode_done, agent outcome and external Benchmark verdict.

        Args:
            input: Finished episode frame after its final Memory flush.
            runtime: Run-owned artifact and evidence services.
        Raises:
            Exception: Final source episode evidence cannot be persisted.
        Returns:
            tuple: Ordered acknowledged actions and one nonphysical terminal result.
        """
        status = RunStatus.SUCCESS if input.environment_done else RunStatus.STEP_LIMIT if not input.done else (
            RunStatus.SUCCESS if input.goal_status == "complete" else RunStatus.FAILURE)
        payload = {"source_commit": "f8e78c0ab0bb8b5daa681afd0296ed0193a98f1f",
                   "episode_done": input.done or input.environment_done, "agent_done": input.done,
                   "environment_done": input.environment_done, "goal_status": input.goal_status,
                   "decision_rounds": input.round_number,
                   "episode": [step.evidence() for step in input.episode],
                   "history": [step.evidence() for step in input.history],
                   "benchmark_evaluated": False}
        path = runtime.artifacts.namespace / "m3a-episode.json"
        runtime.artifacts.write_json(path, payload)
        result = ActionResult(Action(ActionType.DONE if status is RunStatus.SUCCESS else ActionType.FAIL),
            ExecutionStatus.TERMINAL, terminal_status=status,
            metadata={"m3a": payload, "artifact": runtime.artifacts.reference(path)})
        runtime.state.last_action, runtime.state.last_action_result = result.action, result
        return (*input.actions, result)
