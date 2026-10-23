"""Small reusable role operations; YAML owns ordering, branches and task loops.

This module never constructs or invokes a legacy Agent. Frames contain only
task data and component outputs, never models, devices or live components.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any

from zhixing.components import Action, ActionExecutionInput, ActionResult, ActionType, DeviceObservation, ObservationRequest, TaskInput
from zhixing.core.agent.protocol import FragmentType, MemoryFragment, PerceptionInput, PerceptionResult, PlanInput, VerifierInput
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.memory.sliding_window import SlidingWindowMemory


@dataclass(frozen=True)
class WorkflowFrame:
    """Run-owned data passed between individually scheduled graph operations."""

    task: TaskInput
    target: str = "observe"
    route: str = "ok"
    plan: str = "No specific plan, execute step by step."
    memory_params: dict[str, Any] = field(default_factory=dict)
    fragments: tuple[MemoryFragment, ...] = ()
    index: int = 0
    last_screenshot: str | None = None
    last_action: Action | None = None
    observation: DeviceObservation | None = None
    perception: PerceptionResult | None = None
    context: tuple[MemoryFragment, ...] = ()
    action: Action | None = None
    response: str = ""
    ack: ActionResult | None = None
    terminal_status: str | None = None
    summary_pending: bool = False
    last_response: str = ""


def _memory(frame):
    """Restore the configured sliding-window memory from data-only fragments.

    Args:
        frame: Run-owned workflow snapshot.
    Returns:
        SlidingWindowMemory: Fresh view with the same ordering and window rules.
    """
    memory = SlidingWindowMemory(**frame.memory_params)
    for fragment in frame.fragments:
        memory.add(deepcopy(fragment))
    return memory


def _append(frame, *fragments):
    """Append original raw memory fragments without changing window semantics.

    Args:
        frame: Previous workflow snapshot.
        fragments: Exact legacy-compatible memory records.
    Returns:
        WorkflowFrame: Detached snapshot with appended memory.
    """
    return replace(frame, fragments=(*frame.fragments, *deepcopy(fragments)))


def _save(frame, action, response, source, *, hint=True):
    """Commit an action and optional parser hint in the legacy record order.

    Args:
        frame: Current observed snapshot.
        action: Decision, including terminal actions.
        response: Original model/correction text.
        source: Memory provenance tag.
        hint: Apply parser hints only on legacy paths that did so.
    Returns:
        WorkflowFrame: Updated memory and previous-decision fields.
    """
    note = (action.metadata or {}).get("take_note")
    if note:
        frame = _append(frame, MemoryFragment("system", FragmentType.TEXT, f"Memory note: {note}", {"source": "take_note"}))
    frame = _append(frame,
        MemoryFragment("assistant", FragmentType.ACTION, action, {"source": source}),
        MemoryFragment("assistant", FragmentType.TEXT, response, {"source": source}))
    index = frame.index
    metadata = action.metadata or {}
    names = frame.task.metadata.get("perception_names", ())
    if hint and "next_perception_index" in metadata:
        try:
            selected = int(metadata["next_perception_index"])
            if 0 <= selected < len(names):
                index = selected
        except (ValueError, TypeError):
            pass
    elif hint and metadata.get("next_perception_name") in names:
        index = names.index(metadata["next_perception_name"])
    return replace(frame, action=action, index=index,
                   last_action=action, last_screenshot=frame.observation.screenshot_path)


def _verifiable(action):
    """Identify actions verified against the next screenshot by legacy Agents.

    Args:
        action: Previous action or None.
    Returns:
        bool: Whether the legacy pipeline would invoke its verifier.
    """
    return action is not None and action.type in {
        ActionType.TAP, ActionType.LONG_PRESS, ActionType.SWIPE, ActionType.TEXT, ActionType.START_APP}


@PluginRegistry.register(namespace="agent.memory", name="workflow_state")
class WorkflowOperation:
    """Execute one declared data operation, never an Agent step or task loop."""

    OPERATIONS = frozenset({"initialize", "resume", "merge", "transition", "observe_request", "observed",
        "select", "lookup", "commit", "action_request", "executed", "finish", "commit_grounded"})

    def __init__(self, operation, *, target=None, memory_params=None, perception_names=(),
                 source="brain", include_ui_tree=True, tool=None, llm_client=None,
                 component_params=None, component_name=None, perception_index=0,
                 fallback_count=1, feedback_style="modular", use_experience_cache=True,
                 error_prefix="Brain Error", summary_prompt_file="summary_seeact_uground.md", **kwargs):
        """Retain explicit parameters and construct only the selected delegate.

        Args:
            operation: Single named operation executed by this node.
            target: YAML-declared destination for a transition.
            memory_params: Existing sliding-window component parameters.
            perception_names: Ordered perception identifiers for parser hints.
            source: Exact action memory provenance.
            include_ui_tree: Explicit observation request capability.
            tool: Prebound perception/verifier dependency.
            llm_client: Prebound model dependency for reasoning.
            component_params: Original delegate constructor parameters.
            component_name: Existing reasoning/verifier identifier.
            perception_index: Position of this perception delegate.
            fallback_count: Number of configured perception strategies.
            feedback_style: Exact modular or reflection memory/error convention.
            use_experience_cache: Whether this path performs cache retrieval.
            error_prefix: Original role-specific terminal error label.
            summary_prompt_file: Existing prompt resource used by one summary call.
            **kwargs: Reserved binding context, never used as business input.
        Raises:
            ValueError: The operation is unknown.
        Returns:
            None.
        """
        if operation not in self.OPERATIONS:
            raise ValueError("unknown workflow operation")
        self.operation, self.target, self.source = operation, target, source
        self.memory_params, self.names = dict(memory_params or {}), tuple(perception_names)
        self.include_ui_tree, self.tool = include_ui_tree, tool
        self.index, self.count = perception_index, fallback_count
        self.feedback_style, self.use_cache = feedback_style, use_experience_cache
        self.error_prefix = error_prefix
        self.summary_prompt_file = summary_prompt_file
        self.llm = llm_client
        if component_name:
            from zhixing.catalog import BUILTIN_COMPONENT_CATALOG
            namespace = ("agent.grounder" if operation == "ground" else "agent.planner" if operation.startswith("plan_")
                         else "agent.reasoning" if operation == "reason" else "agent.verifier")
            component = BUILTIN_COMPONENT_CATALOG.ensure(namespace, component_name)
            params = dict(component_params or {})
            if llm_client is not None:
                params["llm_client"] = llm_client
            self.tool = component(**params)

    def invoke(self, value, runtime):
        """Execute one operation on an immutable data frame.

        Args:
            value: Typed contract input, or mapping for multiple input ports.
            runtime: Run context used only for declared input metadata.
        Raises:
            TypeError: A role receives incompatible input.
            Exception: An intentionally unhandled delegate failure propagates.
        Returns:
            object: Exact contract output; no live dependency is returned.
        """
        mapping_operations = {"resume", "merge", "observed", "executed"}
        if self.operation not in mapping_operations | {"initialize"} and not isinstance(value, WorkflowFrame):
            raise TypeError("workflow operation requires WorkflowFrame")
        return getattr(self, "op_" + self.operation)(value, runtime)

    def op_initialize(self, task, runtime):
        """Initialize task memory once. Args: task,runtime: Run inputs. Returns: WorkflowFrame."""
        if not isinstance(task, TaskInput):
            raise TypeError("workflow initialization requires TaskInput")
        task = replace(task, metadata={**task.metadata, "perception_names": self.names})
        return WorkflowFrame(task=task, target=self.target or "observe", memory_params=self.memory_params,
            fragments=(MemoryFragment("system", FragmentType.TEXT, f"New task started: {task.instruction}"),))

    def op_resume(self, value, runtime):
        """Select previous state. Args: value,runtime: Initial/previous ports. Returns: WorkflowFrame."""
        return value["previous"] if isinstance(value["previous"], WorkflowFrame) else value["initial"]

    def op_merge(self, values, runtime):
        """Require one selected branch. Args: values,runtime: Branch inputs. Raises: ValueError: Ambiguity. Returns: WorkflowFrame."""
        frames = values if isinstance(values, (list, tuple)) else [values]
        if len(frames) != 1 or not isinstance(frames[0], WorkflowFrame):
            raise ValueError("workflow requires exactly one selected branch")
        return frames[0]

    def op_transition(self, frame, runtime):
        """Follow a YAML destination. Args: frame,runtime: State. Returns: WorkflowFrame."""
        return replace(frame, target=self.target)

    def op_observe_request(self, frame, runtime):
        """Request explicit capture. Args: frame,runtime: State. Returns: ObservationRequest."""
        return ObservationRequest(include_ui_tree=self.include_ui_tree)

    def op_observed(self, value, runtime):
        """Bind the actual observation. Args: value,runtime: Frame/observation ports. Returns: WorkflowFrame."""
        return replace(value["value"], observation=value["observation"], action=None, route="ok")

    def op_select(self, frame, runtime):
        """Expose the active perception index. Args: frame,runtime: State. Returns: WorkflowFrame."""
        return replace(frame, route="p" + str(frame.index))

    def op_verify(self, frame, runtime):
        """Apply modular verification without running perception or reasoning.

        Args:
            frame: Previous decision and newly captured observation.
            runtime: Run context.
        Returns:
            WorkflowFrame: Continue/correction route with exact memory changes.
        """
        if not (frame.last_screenshot and _verifiable(frame.last_action)):
            return replace(frame, route="continue")
        result = self.tool.verify(VerifierInput(task=frame.task.instruction,
            screenshot_before=frame.last_screenshot, screenshot_after=frame.observation.screenshot_path,
            action=frame.last_action))
        if self.feedback_style == "reflection":
            if result.is_success:
                progress = (result.metadata or {}).get("progress")
                if progress:
                    frame = _append(frame, MemoryFragment("system", FragmentType.TEXT,
                        f"Completed contents: {progress}", {"source": "reflection_progress"}))
                return replace(frame, index=0, route="continue")
            feedback = result.feedback or "Previous action did not make expected progress."
            frame = _append(frame, MemoryFragment("system", FragmentType.ERROR,
                f"Reflection feedback: {feedback}. Do not repeat the same failed action.", {"source": "reflection"}))
            correction = result.correction_suggestion
            if correction is not None:
                text = "Critic correction" if self.source == "critic" else "Reflection correction"
                frame = _save(frame, correction, correction.thought or text, self.source)
                return replace(frame, route="correction")
            return replace(frame, route="continue")
        if not result.is_success:
            if result.correction_suggestion is not None:
                frame = _save(frame, result.correction_suggestion, result.feedback, "verifier_correction", hint=False)
                return replace(frame, route="correction")
            if frame.index < self.count - 1:
                frame = replace(frame, index=frame.index + 1)
                content = f"Previous action failed verification. Reason: {result.feedback}. Switching perception strategy."
            else:
                content = (f"Previous action failed verification. Reason: {result.feedback}. "
                    "The UI likely did not change; do not repeat the same tap or grid area—"
                    "try a different cell or action (e.g. keypad, Swipe).")
            frame = _append(frame, MemoryFragment("system", FragmentType.ERROR, content))
        else:
            progress = (result.metadata or {}).get("progress")
            if progress:
                frame = _append(frame, MemoryFragment("system", FragmentType.TEXT,
                    f"Completed contents: {progress}", {"source": "verifier_progress"}))
            frame = replace(frame, index=0)
        return replace(frame, route="continue")

    def op_perceive(self, frame, runtime):
        """Invoke one configured perception; YAML decides retry order.

        Args:
            frame: Current screenshot and active strategy.
            runtime: Run context.
        Returns:
            WorkflowFrame: Success, retry, or terminal failure decision.
        """
        observation = frame.observation
        try:
            result = self.tool.perceive(PerceptionInput(screenshot_path=observation.screenshot_path,
                width=observation.width, height=observation.height, ui_path=observation.ui_path or ""))
            if result is None:
                raise ValueError("Perception returned None")
            return replace(frame, perception=result, route="ok")
        except Exception as error:
            if frame.index < self.count - 1:
                return replace(frame, index=frame.index + 1, route="retry")
            return replace(frame, action=Action(ActionType.FAIL,
                thought=f"All perception strategies crashed: {error}"), route="failed")

    def op_lookup(self, frame, runtime):
        """Use the selected memory's existing cache/context methods.

        Args:
            frame: Current observed and perceived snapshot.
            runtime: Run context.
        Returns:
            WorkflowFrame: Cached decision or exact reasoning context.
        """
        memory = _memory(frame)
        action = memory.retrieve_experience(frame.observation.screenshot_path, frame.task.instruction) if self.use_cache else None
        if action:
            return replace(frame, action=action, response="Loaded from cache", route="hit")
        memory.load_knowledge(query=frame.task.instruction)
        return replace(frame, context=tuple(memory.get_working_context()), route="miss")

    def op_reason(self, frame, runtime):
        """Invoke existing reasoning once, including its original parser policy.

        Args:
            frame: Task, plan, perception and memory context.
            runtime: Run context with optional supplied app catalogue text.
        Returns:
            WorkflowFrame: Decision/raw response or original Brain Error FAIL.
        """
        try:
            action, response = self.tool.think(task=frame.task.instruction, plan=frame.plan,
                perception_result=frame.perception, memory_context=list(frame.context),
                available_apps=str(runtime.metadata.get("available_apps", "")))
            return replace(frame, action=action, response=response, route="ok")
        except Exception as error:
            return replace(frame, action=Action(ActionType.FAIL, thought=f"{self.error_prefix}: {error}"), route="failed")

    def op_commit(self, frame, runtime):
        """Persist a selected decision. Args: frame,runtime: State. Returns: WorkflowFrame."""
        return _save(frame, frame.action, frame.response, self.source, hint=self.source != "memory_cache")

    def op_plan_initial(self, frame, runtime):
        """Run the original reset-time planner once without a screenshot.

        Args:
            frame: Initialized task/memory snapshot.
            runtime: Run context.
        Raises:
            Exception: Initial planning errors propagate, matching legacy reset.
        Returns:
            WorkflowFrame: Plan and original reset-time plan memory.
        """
        result = self.tool.make_plan(PlanInput(task=frame.task.instruction))
        plan = getattr(result, "content", str(result))
        return _append(replace(frame, plan=plan, route="ok"),
            MemoryFragment("system", FragmentType.PLAN, f"Plan: {plan}", getattr(result, "data", {})))

    def op_plan_step(self, frame, runtime):
        """Update Manager plan after perception, retaining old plan on failure.

        Args:
            frame: Current task, perception, screenshot and plan.
            runtime: Run context.
        Returns:
            WorkflowFrame: Updated plan or exact Manager failure memory.
        """
        try:
            result = self.tool.make_plan(PlanInput(task=frame.task.instruction,
                screenshot_path=frame.observation.screenshot_path))
            plan = getattr(result, "content", str(result))
            return _append(replace(frame, plan=plan, route="ok"), MemoryFragment("system", FragmentType.PLAN,
                f"Manager plan: {plan}", {**dict(getattr(result, "data", {}) or {}), "source": "manager_step"}))
        except Exception as error:
            return _append(replace(frame, route="ok"), MemoryFragment("system", FragmentType.ERROR,
                f"Manager planning failed, continue with previous plan. Reason: {error}", {"source": "manager_step"}))

    def op_action_request(self, frame, runtime):
        """Build the explicit device request. Args: frame,runtime: State. Returns: ActionExecutionInput."""
        return ActionExecutionInput(action=frame.action, observation=frame.observation)

    def op_executed(self, value, runtime):
        """Retain confirmed executor facts. Args: value,runtime: Frame/ack ports. Returns: WorkflowFrame."""
        ack = value["ack"]
        terminal = ack.terminal_status
        return replace(value["value"], ack=ack, terminal_status=terminal.value if terminal else None, route="ok")

    def op_finish(self, frame, runtime):
        """Return the terminal evidence. Args: frame,runtime: Final state. Returns: ActionResult."""
        return frame.ack

    def op_setup(self, frame, runtime):
        """Execute the fixed UGround reset operation through the Device adapter.

        Args:
            frame: Initialized task data.
            runtime: Explicit run-scoped device boundary.
        Returns:
            WorkflowFrame: Unchanged task; unsupported or failed reset is optional.
        """
        from zhixing.components.adapters import LegacyDeviceAdapter
        from zhixing.components import DeviceOperation, DeviceRequest
        if hasattr(runtime.device, "shell"):
            LegacyDeviceAdapter(runtime.device).invoke(DeviceRequest(DeviceOperation.SHELL,
                {"command": "settings put system pointer_location 0"}), runtime)
        return replace(frame, route="ok")

    def op_summary(self, frame, runtime):
        """Summarize the previous physical decision using its two real images.

        Args:
            frame: Previous decision and current observation.
            runtime: Run context.
        Returns:
            WorkflowFrame: Optional exact summary memory; summary failures are skipped.
        """
        if not (frame.summary_pending and frame.last_screenshot and frame.last_action):
            return replace(frame, route="ok")
        from zhixing.resources import read_prompt
        action = frame.last_action
        description = str((action.metadata or {}).get("seeact_action") or f"{action.type.value} {action.params}")
        try:
            prompt = read_prompt(self.summary_prompt_file).replace("{task}", frame.task.instruction).replace(
                "{action}", description).replace("{reason}", action.thought or "")
            summary = (self.llm.generate(prompt, images=[frame.last_screenshot, frame.observation.screenshot_path]) or "").strip()
            if summary:
                frame = _append(frame, MemoryFragment("system", FragmentType.TEXT,
                    f"Step summary: Action selected: {description}. {summary}", {"source": "seeact_step_summary"}))
        except Exception:
            pass
        return replace(frame, summary_pending=False, route="ok")

    def op_ground(self, frame, runtime):
        """Resolve only element-targeted actions through the existing grounder.

        Args:
            frame: Parsed planner action and actual observation.
            runtime: Run context.
        Returns:
            WorkflowFrame: Grounded decision, or uncommitted one-second WAIT on error.
        """
        action = deepcopy(frame.action)
        metadata = action.metadata or {}
        try:
            if metadata.get("needs_grounding"):
                x, y = self.tool.ground(frame.observation.screenshot_path, metadata.get("grounding_description", ""),
                    frame.observation.width, frame.observation.height)
                action.params.update(x=x, y=y)
                action.metadata = {**metadata, "grounded_x": x, "grounded_y": y}
            return replace(frame, action=action, route="ok")
        except Exception as error:
            feedback = "Can not ground the described target element. Describe a visible target differently in the next action."
            frame = _append(frame, MemoryFragment("system", FragmentType.ERROR, f"{feedback} Reason: {error}",
                {"source": "uground_grounder"}))
            return replace(frame, action=Action(ActionType.WAIT, params={"seconds": 1.0}, thought=feedback,
                metadata={"raw_response": frame.response}), route="failed")

    def op_commit_grounded(self, frame, runtime):
        """Commit only successfully grounded decisions. Args: frame,runtime: State. Returns: WorkflowFrame."""
        frame = _save(frame, frame.action, frame.response, "seeact_planner")
        return replace(frame, summary_pending=_verifiable(frame.action), last_response=frame.response, route="ok")


@PluginRegistry.register(namespace="agent.perception", name="workflow_perception")
class WorkflowPerception(WorkflowOperation):
    """Single configured perception call with a data-only failure route."""

    OPERATIONS = frozenset({"perceive"})


@PluginRegistry.register(namespace="agent.reasoning", name="workflow_reasoning")
class WorkflowReasoning(WorkflowOperation):
    """Single reasoning invocation, preserving the existing prompt and parser."""

    OPERATIONS = frozenset({"reason", "summary"})


@PluginRegistry.register(namespace="agent.verifier", name="workflow_verifier")
class WorkflowVerifier(WorkflowOperation):
    """Single verifier invocation and its legacy-compatible state projection."""

    OPERATIONS = frozenset({"verify"})


@PluginRegistry.register(namespace="agent.planner", name="workflow_planner")
class WorkflowPlanner(WorkflowOperation):
    """One initial or per-step Manager call; the graph decides when it runs."""

    OPERATIONS = frozenset({"plan_initial", "plan_step"})


@PluginRegistry.register(namespace="agent.grounder", name="workflow_grounder")
class WorkflowGrounder(WorkflowOperation):
    """One grounding call, with a separate graph route for failure."""

    OPERATIONS = frozenset({"ground"})


@PluginRegistry.register(namespace="agent.action_executor", name="workflow_setup")
class WorkflowSetup(WorkflowOperation):
    """Explicit fixed reset effect; never selected or invoked by compilation."""

    OPERATIONS = frozenset({"setup"})
