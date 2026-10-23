"""Structural protocols for the ZhiXing component programming model."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Generic, Protocol, TypeVar, runtime_checkable

from zhixing.core.agent.protocol import Action, PerceptionResult, PlanInput, PlanResult, VerifierInput, VerifierResult

from .models import (
    ActionExecutionInput,
    ActionResult,
    BenchmarkInitInput,
    BenchmarkInitResult,
    DeviceObservation,
    DeviceRequest,
    DeviceResult,
    EvaluationInput,
    EvaluationResult,
    EvaluationResultV2,
    GroundingInput,
    GroundingResult,
    LLMInput,
    LLMResult,
    MemoryInput,
    MemoryResult,
    ReasoningInput,
    RuntimeContext,
)


InputT = TypeVar("InputT", contravariant=True)
OutputT = TypeVar("OutputT", covariant=True)


@runtime_checkable
class Component(Protocol[InputT, OutputT]):
    def invoke(self, input: InputT, runtime: RuntimeContext) -> OutputT:
        ...


@runtime_checkable
class Perception(Component[DeviceObservation, PerceptionResult], Protocol):
    pass


@runtime_checkable
class Planner(Component[PlanInput, PlanResult], Protocol):
    pass


@runtime_checkable
class Reasoning(Component[ReasoningInput, Action], Protocol):
    pass


@runtime_checkable
class Memory(Component[MemoryInput, MemoryResult], Protocol):
    pass


@runtime_checkable
class Verifier(Component[VerifierInput, VerifierResult], Protocol):
    pass


@runtime_checkable
class Grounder(Component[GroundingInput, GroundingResult], Protocol):
    pass


@runtime_checkable
class LLM(Component[LLMInput, LLMResult], Protocol):
    pass


@runtime_checkable
class Device(Component[DeviceRequest, DeviceResult], Protocol):
    pass


@runtime_checkable
class ActionExecutor(Component[ActionExecutionInput, ActionResult], Protocol):
    pass


@runtime_checkable
class BenchmarkInitializer(Component[BenchmarkInitInput, BenchmarkInitResult], Protocol):
    pass


@runtime_checkable
class Evaluator(Component[EvaluationInput, EvaluationResultV2], Protocol):
    pass


class ComponentRole(str, Enum):
    PERCEPTION = "perception"
    PLANNER = "planner"
    REASONING = "reasoning"
    MEMORY = "memory"
    VERIFIER = "verifier"
    GROUNDER = "grounder"
    LLM = "llm"
    DEVICE = "device"
    ACTION_EXECUTOR = "action_executor"
    BENCHMARK_INITIALIZER = "benchmark_initializer"
    EVALUATOR = "evaluator"


@dataclass(frozen=True)
class RoleDescriptor:
    role: ComponentRole
    input_type: type
    output_type: type
    legacy_methods: tuple[str, ...]


ROLE_DESCRIPTORS = MappingProxyType(
    {
        ComponentRole.PERCEPTION: RoleDescriptor(ComponentRole.PERCEPTION, DeviceObservation, PerceptionResult, ("perceive",)),
        ComponentRole.PLANNER: RoleDescriptor(ComponentRole.PLANNER, PlanInput, PlanResult, ("make_plan",)),
        ComponentRole.REASONING: RoleDescriptor(ComponentRole.REASONING, ReasoningInput, Action, ("think",)),
        ComponentRole.MEMORY: RoleDescriptor(ComponentRole.MEMORY, MemoryInput, MemoryResult, ("add", "get_working_context", "clear")),
        ComponentRole.VERIFIER: RoleDescriptor(ComponentRole.VERIFIER, VerifierInput, VerifierResult, ("verify",)),
        ComponentRole.GROUNDER: RoleDescriptor(ComponentRole.GROUNDER, GroundingInput, GroundingResult, ("ground",)),
        ComponentRole.LLM: RoleDescriptor(ComponentRole.LLM, LLMInput, LLMResult, ("generate",)),
        ComponentRole.DEVICE: RoleDescriptor(ComponentRole.DEVICE, DeviceRequest, DeviceResult, ("screenshot", "tap", "swipe")),
        ComponentRole.ACTION_EXECUTOR: RoleDescriptor(ComponentRole.ACTION_EXECUTOR, ActionExecutionInput, ActionResult, ()),
        ComponentRole.BENCHMARK_INITIALIZER: RoleDescriptor(ComponentRole.BENCHMARK_INITIALIZER, BenchmarkInitInput, BenchmarkInitResult, ("generate", "execute")),
        ComponentRole.EVALUATOR: RoleDescriptor(ComponentRole.EVALUATOR, EvaluationInput, EvaluationResultV2, ("evaluate",)),
    }
)


def get_role_descriptor(role: ComponentRole | str) -> RoleDescriptor:
    return ROLE_DESCRIPTORS[ComponentRole(role)]
