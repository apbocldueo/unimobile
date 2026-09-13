"""Typed role adapters between AgentGraph ports and component DTOs."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionResult,
    DeviceObservation,
    ExecutionStatus,
    MemoryFragment,
    MemoryInput,
    MemoryOperation,
    MemoryResult,
    PerceptionResult,
    PlanInput,
    PlanResult,
    ReasoningInput,
    RuntimeContext,
    TaskInput,
    VerifierInput,
    VerifierResult,
)
from zhixing.core.agent.protocol import FragmentType
from zhixing.graph import GraphRole

from .binding import invoke_bound_component
from .errors import GraphExecutionError
from .models import BoundComponent, StepFrame


@dataclass(frozen=True)
class RoleInvocation:
    """Normalized role invocation output and selected component identity."""

    output: Any
    component_name: str


def _require(inputs: Mapping[str, Any], name: str, expected: type, node_id: str) -> Any:
    """Read and type-check one required logical input.

    Args:
        inputs (Mapping[str, Any]): Values delivered to the node ports.
        name (str): Required port name.
        expected (type): Runtime DTO type.
        node_id (str): Logical node used in diagnostics.

    Raises:
        GraphExecutionError: The input is absent or has an incompatible type.

    Returns:
        Any: Required typed value.
    """
    value = inputs.get(name)
    if not isinstance(value, expected):
        raise GraphExecutionError(
            "runtime.input_type",
            f"Node {node_id!r} requires {name!r} as {expected.__name__}",
            node_id=node_id,
            phase="assembly",
            details={"port": name, "actual": type(value).__name__},
        )
    return value


def _memory_fragment(value: Any, step: int) -> MemoryFragment:
    """Convert one supported graph value into a stable memory fragment.

    Args:
        value (Any): Task, plan, action, action result, or verifier result.
        step (int): Current interaction step.

    Raises:
        GraphExecutionError: The write value is not supported by the Memory port contract.

    Returns:
        MemoryFragment: Canonical fragment passed to the Memory component.
    """
    metadata = {"runtime_step": step, "source_type": type(value).__name__}
    if isinstance(value, TaskInput):
        return MemoryFragment("user", FragmentType.TEXT, value.instruction, metadata)
    if isinstance(value, PlanResult):
        return MemoryFragment("system", FragmentType.PLAN, value.content, {**metadata, **value.data})
    if isinstance(value, Action):
        return MemoryFragment("assistant", FragmentType.ACTION, value, metadata)
    if isinstance(value, ActionResult):
        if value.succeeded:
            return MemoryFragment(
                "assistant",
                FragmentType.ACTION,
                value.action,
                {
                    **metadata,
                    "execution_status": value.status.value,
                    "effect_performed": value.effect_performed,
                },
            )
        return MemoryFragment(
            "system",
            FragmentType.ERROR,
            value.error or value.message or value.status.value,
            {
                **metadata,
                "action_type": value.action.type.value,
                "execution_status": value.status.value,
            },
        )
    if isinstance(value, VerifierResult):
        fragment_type = FragmentType.TEXT if value.is_success else FragmentType.ERROR
        return MemoryFragment("system", fragment_type, value.feedback, {**metadata, "success": value.is_success})
    raise GraphExecutionError(
        "runtime.memory_write_type",
        f"Unsupported Memory write value {type(value).__name__}",
        phase="assembly",
    )


def _write_signature(fragment: MemoryFragment) -> str:
    """Create a stable run-local signature used to avoid duplicate writes.

    Args:
        fragment (MemoryFragment): Candidate memory fragment.

    Raises:
        None.

    Returns:
        str: SHA-256 signature of non-secret structural values.
    """
    payload = f"{fragment.role}|{fragment.type.value}|{fragment.content!r}|{fragment.metadata!r}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def assemble_role_input(
    role: GraphRole,
    inputs: Mapping[str, Any],
    frame: StepFrame,
    runtime: RuntimeContext,
    node_id: str,
) -> Any:
    """Build the public component DTO for one graph role.

    Args:
        role (GraphRole): Target component role.
        inputs (Mapping[str, Any]): Delivered port values.
        frame (StepFrame): Current pre/post-action state.
        runtime (RuntimeContext): Shared run context.
        node_id (str): Logical node identifier.

    Raises:
        GraphExecutionError: Required input is absent or the role is unsupported.

    Returns:
        Any: Role-specific typed component input.
    """
    if role is GraphRole.PERCEPTION:
        return _require(inputs, "observation", DeviceObservation, node_id)
    if role is GraphRole.PLANNER:
        task = _require(inputs, "task", TaskInput, node_id)
        observation = inputs.get("observation")
        screenshot = observation.screenshot_path if isinstance(observation, DeviceObservation) else ""
        return PlanInput(task=task.instruction, screenshot_path=screenshot)
    if role is GraphRole.REASONING:
        task = _require(inputs, "task", TaskInput, node_id)
        perception = _require(inputs, "perception", PerceptionResult, node_id)
        plan = inputs.get("plan")
        if plan is None:
            plan = PlanResult(content="")
        if not isinstance(plan, PlanResult):
            raise GraphExecutionError(
                "runtime.input_type",
                f"Node {node_id!r} requires optional plan as PlanResult",
                node_id=node_id,
                phase="assembly",
            )
        memory = inputs.get("memory", ())
        if isinstance(memory, MemoryResult):
            memory = memory.fragments
        if memory is None:
            memory = ()
        if not isinstance(memory, (tuple, list)) or not all(isinstance(item, MemoryFragment) for item in memory):
            raise GraphExecutionError(
                "runtime.input_type",
                f"Node {node_id!r} requires memory as MemoryFragment sequence",
                node_id=node_id,
                phase="assembly",
            )
        verification = inputs.get("verification")
        if verification is not None and not isinstance(verification, VerifierResult):
            raise GraphExecutionError(
                "runtime.input_type",
                f"Node {node_id!r} requires verification as VerifierResult",
                node_id=node_id,
                phase="assembly",
            )
        return ReasoningInput(
            task=task,
            plan=plan,
            perception=perception,
            memory_context=tuple(memory),
            available_apps=str(runtime.metadata.get("available_apps", "")),
            verification=verification,
        )
    if role is GraphRole.ACTION_EXECUTOR:
        action = _require(inputs, "action", Action, node_id)
        observation = inputs.get("observation")
        if observation is not None and not isinstance(observation, DeviceObservation):
            raise GraphExecutionError(
                "runtime.input_type",
                f"Node {node_id!r} requires observation as DeviceObservation",
                node_id=node_id,
                phase="assembly",
            )
        return ActionExecutionInput(action=action, observation=observation)
    if role is GraphRole.VERIFIER:
        task = _require(inputs, "task", TaskInput, node_id)
        action = _require(inputs, "action", Action, node_id)
        before = frame.pre_observation or _require(inputs, "before", DeviceObservation, node_id)
        after = frame.post_observation or _require(inputs, "after", DeviceObservation, node_id)
        action_result = inputs.get("action_result", frame.action_result)
        if action_result is not None and not isinstance(action_result, ActionResult):
            raise GraphExecutionError(
                "runtime.input_type",
                f"Node {node_id!r} requires action_result as ActionResult",
                node_id=node_id,
                phase="assembly",
            )
        return VerifierInput(
            task=task.instruction,
            screenshot_before=before.screenshot_path,
            screenshot_after=after.screenshot_path,
            action=action,
            action_result=action_result,
            metadata={"before": before, "after": after},
        )
    if role is GraphRole.MEMORY:
        return inputs.get("write", [])
    raise GraphExecutionError(
        "runtime.role_unsupported",
        f"Graph role {role.value!r} is not supported by the mobile runtime",
        node_id=node_id,
        phase="assembly",
    )


def _expected_output(role: GraphRole) -> type:
    """Return the canonical output DTO class for one graph role.

    Args:
        role (GraphRole): Component role.

    Raises:
        GraphExecutionError: The role is unknown to the runtime.

    Returns:
        type: Expected component output class.
    """
    expected = {
        GraphRole.PERCEPTION: PerceptionResult,
        GraphRole.PLANNER: PlanResult,
        GraphRole.REASONING: Action,
        GraphRole.MEMORY: MemoryResult,
        GraphRole.ACTION_EXECUTOR: ActionResult,
        GraphRole.VERIFIER: VerifierResult,
    }.get(role)
    if expected is None:
        raise GraphExecutionError(
            "runtime.role_unsupported",
            f"Graph role {role.value!r} has no output contract",
            phase="normalization",
        )
    return expected


def invoke_role(
    bound: BoundComponent,
    inputs: Mapping[str, Any],
    frame: StepFrame,
    runtime: RuntimeContext,
) -> RoleInvocation:
    """Assemble, invoke, and normalize one logical role node.

    Args:
        bound (BoundComponent): Bound component node.
        inputs (Mapping[str, Any]): Values delivered to node input ports.
        frame (StepFrame): Current interaction step state.
        runtime (RuntimeContext): Shared run context.

    Raises:
        GraphExecutionError: Input assembly, candidate invocation, or output validation fails.

    Returns:
        RoleInvocation: Canonical output and selected component name.
    """
    role = bound.node.role
    if role is None:
        raise GraphExecutionError(
            "runtime.role_missing",
            f"Component node {bound.node_id!r} has no role",
            node_id=bound.node_id,
            phase="assembly",
        )
    input_value = assemble_role_input(role, inputs, frame, runtime, bound.node_id)
    if role is GraphRole.MEMORY:
        writes = input_value if isinstance(input_value, list) else [input_value]
        seen_key = f"runtime.memory.seen.{bound.node_id}"
        seen = runtime.state.strategy_state.setdefault(seen_key, [])
        selected_name = ""
        for value in writes:
            fragment = _memory_fragment(value, runtime.step)
            signature = _write_signature(fragment)
            if signature in seen:
                continue
            _ignored, selected = invoke_bound_component(
                bound,
                MemoryInput(MemoryOperation.APPEND, fragment=fragment),
                runtime,
            )
            selected_name = selected.reference.name
            seen.append(signature)
        output, selected = invoke_bound_component(
            bound,
            MemoryInput(MemoryOperation.READ),
            runtime,
        )
        selected_name = selected.reference.name or selected_name
    else:
        output, selected = invoke_bound_component(bound, input_value, runtime)
        selected_name = selected.reference.name
    expected = _expected_output(role)
    if not isinstance(output, expected):
        raise GraphExecutionError(
            "runtime.output_type",
            f"Node {bound.node_id!r} returned {type(output).__name__}; expected {expected.__name__}",
            node_id=bound.node_id,
            phase="normalization",
        )
    normalized_output = output.fragments if role is GraphRole.MEMORY else output
    return RoleInvocation(output=normalized_output, component_name=selected_name)


def reset_memory(bound: BoundComponent, runtime: RuntimeContext) -> None:
    """Reset one stateful Memory component at run start.

    Args:
        bound (BoundComponent): Bound Memory node.
        runtime (RuntimeContext): Shared run context.

    Raises:
        GraphExecutionError: Memory reset fails for every candidate.

    Returns:
        None: Memory state is reset in place.
    """
    output, _candidate = invoke_bound_component(
        bound,
        MemoryInput(MemoryOperation.RESET),
        runtime,
    )
    if not isinstance(output, MemoryResult) or output.operation is not MemoryOperation.RESET:
        raise GraphExecutionError(
            "runtime.memory_reset_output",
            f"Memory node {bound.node_id!r} returned an invalid reset result",
            node_id=bound.node_id,
            phase="on_run_start",
        )
