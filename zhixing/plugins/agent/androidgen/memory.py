"""Exact Recorder-to-Memory conversion around the existing SlidingWindowMemory."""

from dataclasses import replace

from zhixing.components import Action, ActionResult, ActionType, ExecutionStatus, RunStatus
from zhixing.core.agent.protocol import FragmentType, MemoryFragment
from zhixing.core.factory import PluginRegistry

from .prompts import default_example, system_prompt
from .types import AndroidGenFrame


@PluginRegistry.register(namespace="agent.memory", name="androidgen_pass")
class AndroidGenPass:
    """Carry the selected final-flush branch into the common commit operation."""

    def invoke(self, input, runtime):
        """Forward a frame. Args: input: Selected frame; runtime: Unused. Returns: AndroidGenFrame: Same frame."""
        del runtime
        return input


@PluginRegistry.register(namespace="agent.memory", name="androidgen_bootstrap")
class AndroidGenBootstrap:
    """Perform source ExpSearch once, never in the per-round history window."""

    def __init__(self, examples, enabled: bool = True) -> None:
        """Bind a lazy original knowledge dependency.

        Args:
            examples: Original-compatible retrieve_example service.
            enabled: Original expsearch switch.
        Returns:
            None.
        """
        self.examples, self.enabled = examples, enabled

    def invoke(self, input, runtime):
        """Select one source example or the original default, then create run data.

        Args:
            input: Task and original initial App name.
            runtime: Unused context.
        Raises:
            Exception: Original retrieval or prompt formatting fails.
        Returns:
            AndroidGenFrame: Fresh episode with no shared plan or history.
        """
        del runtime
        example = self.examples.retrieve_example(input.task.instruction, 'android', input.init_state) if self.enabled else None
        return AndroidGenFrame(input.task, system_prompt % (default_example if example is None else example), example=example)


@PluginRegistry.register(namespace="agent.memory", name="androidgen_resume")
class AndroidGenResume:
    """Route source logical-round budgets independently of device-effect counts."""

    def __init__(self, max_rounds: int = 31) -> None:
        """Remember the source default 0..30 inclusive. Args: max_rounds: Bound. Returns: None."""
        self.max_rounds = max_rounds

    def invoke(self, input, runtime):
        """Restore data-only State or initialize from the once-retrieved seed.

        Args:
            input: Initial frame and optional previous committed frame.
            runtime: Unused context.
        Raises:
            TypeError: Restored State is not an AndroidGenFrame.
        Returns:
            AndroidGenFrame: Continue or terminal/budget memory-flush route.
        """
        del runtime
        frame = input["previous"] or input["initial"]
        if not isinstance(frame, AndroidGenFrame):
            raise TypeError("invalid AndroidGen run State")
        return replace(frame, route="finish" if frame.done or frame.round_number >= self.max_rounds else "continue")


@PluginRegistry.register(namespace="agent.memory", name="androidgen_history")
class AndroidGenHistory:
    """Emit one exact TEXT message for the shared stateful Memory node."""

    def __init__(self, role: str = "user") -> None:
        """Choose one half of the source pair. Args: role: user/assistant. Raises: ValueError: Invalid role. Returns: None."""
        if role not in ("user", "assistant"):
            raise ValueError("history role must be user or assistant")
        self.index = 0 if role == "user" else 1

    def invoke(self, input, runtime):
        """Write the previous round once, including the final nonphysical flush.

        Args:
            input: Resumed frame with pending source messages.
            runtime: Unused context.
        Returns:
            dict: Optional original fragment and an explicit ordering control signal.
        """
        del runtime
        if not input.pending:
            return {"fragment": None, "sequence": True}
        message = input.pending[self.index]
        return {"fragment": MemoryFragment(message['role'], FragmentType.TEXT, message['content']['text'],
            {"source": "androidgen.history", "round": input.round_number, "message": self.index}), "sequence": True}


@PluginRegistry.register(namespace="agent.memory", name="androidgen_ready")
class AndroidGenReady:
    """Read exact source history after both pending message writes complete."""

    def invoke(self, input, runtime):
        """Rebuild role/content dictionaries without Action normalization or truncation.

        Args:
            input: Frame and reusable Memory's working context.
            runtime: Unused context.
        Raises:
            RuntimeError: Memory window does not retain the complete episode.
        Returns:
            AndroidGenFrame: Full history for Planner; actor truncates separately.
        """
        del runtime
        frame = input["frame"]
        fragments = [item for item in input["memory"] if item.metadata.get("source") == "androidgen.history"]
        if len(fragments) != len(frame.records) * 2:
            raise RuntimeError("AndroidGen Memory must retain all source history")
        return replace(frame, messages=tuple({"role": item.role, "content": {"text": item.content}} for item in fragments))


@PluginRegistry.register(namespace="agent.memory", name="androidgen_commit")
class AndroidGenCommit:
    """Persist one original source turn, then schedule its exact history pair."""

    def invoke(self, input, runtime):
        """Merge the exclusive execute/flush branch and retain source None-result failure.

        Args:
            input: Exactly one selected frame in a values list.
            runtime: Run-owned artifact services.
        Raises:
            ValueError: Branch selection delivered zero or multiple frames.
            TypeError: Source code produced None instead of an execution result.
            Exception: Persisting evidence fails.
        Returns:
            AndroidGenFrame: One committed round, or completed terminal flush.
        """
        if len(input) != 1:
            raise ValueError("AndroidGen commits exactly one selected branch")
        frame = input[0]
        if frame.route == "finish":
            return replace(frame, finished=True, pending=())
        record = {**frame.view.record, "instruction": frame.task.instruction,
            "trace_id": runtime.run_id, "index": frame.round_number, **frame.output,
            "parsed_action": frame.previous_result}
        records = (*frame.records, record)
        # Save BEFORE the source's operation indexing: code with no result is
        # fatal, but its already executed round remains in the original recorder.
        runtime.artifacts.write_json(runtime.artifacts.namespace / "androidgen-records.json", {"records": list(records)})
        env_input = '**Environment State (Omitted)**'
        if 'error_feedback' in record:
            env_input += f'\n# Error Feedback: {record["error_feedback"]}'
        pending = ({"role": "user", "content": {"text": env_input}},
                   {"role": "assistant", "content": {"text": record['response']}})
        return replace(frame, round_number=frame.round_number + 1, records=records, pending=pending,
                       done=frame.previous_result['operation'] == 'exit')


@PluginRegistry.register(namespace="agent.memory", name="androidgen_finish")
class AndroidGenFinish:
    """Publish source exit/budget facts separately from Benchmark task correctness."""

    def invoke(self, input, runtime):
        """Save the completed episode and expose a nonphysical terminal result.

        Args:
            input: Episode after final pending-history flush.
            runtime: Artifact and terminal-result services.
        Raises:
            Exception: Evidence persistence fails.
        Returns:
            tuple: Source code-block acknowledgments and terminal source outcome.
        """
        payload = {"source_commit": "3f511cff18a842e6583ac7e7d9cabd217c5d3b1b",
            "agent_declared_exit": input.done, "decision_rounds": input.round_number,
            "records": list(input.records), "history": list(input.messages),
            "plan": list(input.plan), "example": input.example, "benchmark_evaluated": False}
        path = runtime.artifacts.namespace / "androidgen-episode.json"
        runtime.artifacts.write_json(path, payload)
        status = RunStatus.SUCCESS if input.done else RunStatus.STEP_LIMIT
        ack = ActionResult(Action(ActionType.DONE if input.done else ActionType.FAIL), ExecutionStatus.TERMINAL,
            terminal_status=status, metadata={"androidgen": payload, "artifact": runtime.artifacts.reference(path)})
        runtime.state.last_action, runtime.state.last_action_result = ack.action, ack
        return (*input.actions, ack)
