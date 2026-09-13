"""Public, import-safe AgentGraph binding and execution surface."""

from typing import Any

from .binding import (
    ComponentResolver,
    MappingComponentResolver,
    RegistryComponentResolver,
    bind_agent_graph,
    invoke_bound_component,
)
from .engine import GraphRuntime, evaluate_predicate
from .kernel import (
    ActivationFrame,
    BoundExecutionPlan,
    BoundNode,
    ExecutionBudget,
    GraphExecutionKernel,
    InvocationAdapterRegistry,
    KernelResult,
    KernelStatus,
    bind_execution_plan,
)
from .errors import (
    GraphBindingError,
    GraphExecutionError,
    GraphRuntimeError,
    ObservationError,
    RuntimeErrorInfo,
)
from .facade import build_graph_runtime, run_agent_graph
from .models import (
    BoundAgentGraph,
    BoundCandidate,
    BoundComponent,
    CancellationSignal,
    ObservationProvider,
    ResolvedComponentDefinition,
    SimpleCancellationSignal,
    StepFrame,
    ValueStore,
)
from .state import StateStore
from .artifacts import ArtifactStoreError, ObservationArtifactPaths, RunArtifactStore
__all__ = [
    "BoundAgentGraph",
    "BoundCandidate",
    "BoundComponent",
    "BoundExecutionPlan",
    "BoundNode",
    "CancellationSignal",
    "ComponentResolver",
    "GraphBindingError",
    "GraphExecutionError",
    "GraphExecutionKernel",
    "GraphRuntime",
    "GraphRuntimeError",
    "MappingComponentResolver",
    "InvocationAdapterRegistry",
    "KernelResult",
    "KernelStatus",
    "ObservationError",
    "ObservationProvider",
    "ResolvedComponentDefinition",
    "RegistryComponentResolver",
    "RuntimeErrorInfo",
    "SimpleCancellationSignal",
    "StepFrame",
    "StateStore",
    "ValueStore",
    "ActivationFrame",
    "ACTION_EXECUTOR_CONTRACT",
    "ArtifactStoreError",
    "AndroidActionService",
    "AndroidGraphRuntime",
    "AndroidObservationService",
    "DEVICE_OBSERVE_CONTRACT",
    "ExecutionBudget",
    "FixedActionComponent",
    "ObservationArtifactPaths",
    "RunArtifactStore",
    "bind_agent_graph",
    "bind_execution_plan",
    "build_graph_runtime",
    "build_android_smoke_graph",
    "build_android_smoke_plan",
    "evaluate_predicate",
    "invoke_bound_component",
    "run_agent_graph",
    "run_android_agent_graph",
]


_ANDROID_EXPORTS = {
    "ACTION_EXECUTOR_CONTRACT",
    "DEVICE_OBSERVE_CONTRACT",
    "AndroidActionService",
    "AndroidGraphRuntime",
    "AndroidObservationService",
    "FixedActionComponent",
    "build_android_smoke_graph",
    "build_android_smoke_plan",
    "run_android_agent_graph",
}


def __getattr__(name: str):
    """Lazily expose Android runtime symbols without device import side effects.

    Args:
        name (str): Requested public runtime attribute.

    Raises:
        AttributeError: The name is not a lazy Android export.

    Returns:
        Any: Requested symbol from ``zhixing.runtime.android``.
    """
    if name not in _ANDROID_EXPORTS:
        raise AttributeError(name)
    from . import android

    return getattr(android, name)
