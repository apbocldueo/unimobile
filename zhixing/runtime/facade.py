"""Public build-and-run facade for AgentGraph runtime execution."""

from __future__ import annotations

from zhixing.components import RunResult, RuntimeContext, TaskInput
from zhixing.graph import AgentGraph, CompilationResult

from .binding import ComponentResolver, bind_agent_graph
from .engine import GraphRuntime
from .models import BoundAgentGraph, ObservationProvider


def build_graph_runtime(
    source: AgentGraph | CompilationResult,
    resolver: ComponentResolver,
) -> BoundAgentGraph:
    """Validate and bind a graph without connecting to a device.

    Args:
        source (AgentGraph | CompilationResult): Graph or successful compiler output.
        resolver (ComponentResolver): Explicit component resolver.

    Raises:
        GraphBindingError: Validation or component binding fails.

    Returns:
        BoundAgentGraph: Executable binding consumed by GraphRuntime.
    """
    return bind_agent_graph(source, resolver)


def run_agent_graph(
    source: AgentGraph | CompilationResult | BoundAgentGraph,
    task: TaskInput,
    observation_provider: ObservationProvider,
    *,
    resolver: ComponentResolver | None = None,
    runtime: RuntimeContext | None = None,
) -> RunResult:
    """Build when necessary and execute one AgentGraph through the shared runtime.

    Args:
        source (AgentGraph | CompilationResult | BoundAgentGraph): Authoring result or bound graph.
        task (TaskInput): Task to execute.
        observation_provider (ObservationProvider): Device observation boundary.
        resolver (ComponentResolver | None): Required for unbound graph inputs.
        runtime (RuntimeContext | None): Optional caller-owned run context.

    Raises:
        ValueError: An unbound graph is supplied without a resolver.

    Returns:
        RunResult: Structured execution evidence.
    """
    if isinstance(source, BoundAgentGraph):
        bound = source
    else:
        if resolver is None:
            raise ValueError("resolver is required when source is not BoundAgentGraph")
        bound = bind_agent_graph(source, resolver)
    return GraphRuntime().run(bound, task, observation_provider, runtime=runtime)

