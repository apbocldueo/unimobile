"""Bind validated AgentGraph declarations to runtime component instances."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from inspect import isclass
from typing import Any, Protocol

from zhixing.components import (
    ComponentDefinitionError,
    ComponentRole,
    RuntimeContext,
    adapt_component,
    construct_component,
    get_component_spec,
)
from zhixing.core.factory import PluginRegistry
from zhixing.graph import (
    AgentGraph,
    CompilationResult,
    GraphComponentRef,
    GraphRole,
    NodeKind,
    SecretRef,
    validate_graph,
)

from .errors import GraphBindingError, GraphExecutionError
from .models import BoundAgentGraph, BoundCandidate, BoundComponent


class ComponentResolver(Protocol):
    """Resolve one declarative component candidate without running it."""

    def resolve(self, reference: GraphComponentRef, role: GraphRole) -> Any:
        """Resolve a component reference into an instance.

        Args:
            reference (GraphComponentRef): Declarative component reference.
            role (GraphRole): Expected graph role.

        Raises:
            Exception: Indicates that this candidate could not be resolved.

        Returns:
            Any: Component instance implementing invoke or a supported legacy method.
        """
        ...


class MappingComponentResolver:
    """Side-effect-free resolver backed by explicit instances or factories."""

    def __init__(self, components: Mapping[tuple[str, str] | str, Any]) -> None:
        """Create a resolver from explicit component entries.

        Args:
            components (Mapping[tuple[str, str] | str, Any]): Entries keyed by
                ``(namespace, name)`` or by name.

        Raises:
            None.

        Returns:
            None: Initializes the resolver.
        """
        self.components = dict(components)
        self.calls: list[tuple[str, str, GraphRole]] = []

    def resolve(self, reference: GraphComponentRef, role: GraphRole) -> Any:
        """Resolve one explicit entry and instantiate class/factory values.

        Args:
            reference (GraphComponentRef): Declarative component reference.
            role (GraphRole): Expected graph role.

        Raises:
            ComponentDefinitionError: A formal component fails strict preflight.
            LookupError: No matching explicit component exists.

        Returns:
            Any: Resolved component instance.
        """
        self.calls.append((reference.namespace, reference.name, role))
        key = (reference.namespace, reference.name)
        if key in self.components:
            target = self.components[key]
        elif reference.name in self.components:
            target = self.components[reference.name]
        else:
            raise LookupError(f"component {reference.namespace}:{reference.name} is not provided")
        specification = get_component_spec(target)
        if specification is not None:
            try:
                return construct_component(
                    specification,
                    reference.params,
                    expected_role=role,
                )
            except ComponentDefinitionError:
                # A formal definition is never reinterpreted as a structural or
                # legacy component after strict validation fails.
                raise
        if isclass(target):
            return target(**reference.params)
        if callable(target) and not callable(getattr(target, "invoke", None)):
            return target(**reference.params)
        return target


class RegistryComponentResolver:
    """Resolve components from the current registry with injected providers."""

    def __init__(
        self,
        *,
        registry: type[PluginRegistry] = PluginRegistry,
        secret_provider: Mapping[str, Any] | Callable[[str], Any] | None = None,
        dependency_provider: Mapping[str, Any] | None = None,
        constructor_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Configure registry binding without triggering autodiscovery.

        Args:
            registry (type[PluginRegistry]): Registry implementation to query.
            secret_provider (Mapping[str, Any] | Callable[[str], Any] | None):
                Explicit source for SecretRef values.
            dependency_provider (Mapping[str, Any] | None): Prebuilt named dependencies.
            constructor_kwargs (Mapping[str, Any] | None): Framework objects explicitly
                injected into compatible constructors.

        Raises:
            None.

        Returns:
            None: Initializes the resolver without importing plugin packages.
        """
        self.registry = registry
        self.secret_provider = secret_provider
        self.dependency_provider = dict(dependency_provider or {})
        self.constructor_kwargs = dict(constructor_kwargs or {})

    def _secret(self, name: str) -> Any:
        """Resolve one secret reference from the explicit provider.

        Args:
            name (str): Stable secret reference name.

        Raises:
            LookupError: No secret provider or value is available.

        Returns:
            Any: Secret value used only for construction.
        """
        if self.secret_provider is None:
            raise LookupError(f"secret reference {name!r} has no provider")
        if callable(self.secret_provider):
            return self.secret_provider(name)
        if name not in self.secret_provider:
            raise LookupError(f"secret reference {name!r} is unavailable")
        return self.secret_provider[name]

    def _resolve_value(self, value: Any) -> Any:
        """Resolve nested SecretRef values without mutating AgentGraph data.

        Args:
            value (Any): Declarative parameter value.

        Raises:
            LookupError: A referenced secret cannot be resolved.

        Returns:
            Any: Runtime-only resolved copy.
        """
        if isinstance(value, SecretRef):
            return self._secret(value.secret_ref)
        if isinstance(value, Mapping):
            if (
                set(value) == {"secret_ref"}
                and isinstance(value.get("secret_ref"), str)
            ):
                return self._secret(str(value["secret_ref"]))
            return {key: self._resolve_value(item) for key, item in value.items()}
        if isinstance(value, tuple):
            return tuple(self._resolve_value(item) for item in value)
        if isinstance(value, list):
            return [self._resolve_value(item) for item in value]
        return value

    def _dependency(self, name: str, specification: Any) -> Any:
        """Resolve a named dependency from a provider or nested plugin reference.

        Args:
            name (str): Constructor argument name.
            specification (Any): Declarative dependency specification.

        Raises:
            LookupError: The dependency cannot be resolved.

        Returns:
            Any: Runtime dependency instance or resolved literal.
        """
        if name in self.dependency_provider:
            return self.dependency_provider[name]
        if isinstance(specification, Mapping) and specification.get("name"):
            namespace = str(specification.get("namespace") or ("llm" if name == "llm" else f"agent.{name}"))
            plugin_class = self.registry.get_plugin(namespace, str(specification["name"]))
            params = self._resolve_value(specification.get("params", {}))
            return plugin_class(**params)
        return self._resolve_value(specification)

    def resolve(self, reference: GraphComponentRef, role: GraphRole) -> Any:
        """Instantiate one registered candidate with explicit dependencies.

        Args:
            reference (GraphComponentRef): Declarative candidate.
            role (GraphRole): Expected role, retained for resolver diagnostics.

        Raises:
            ValueError: Registry lookup fails.
            TypeError: Component construction arguments are incompatible.

        Returns:
            Any: Newly constructed component instance.
        """
        plugin_class = self.registry.get_plugin(reference.namespace, reference.name)
        kwargs = self._resolve_value(reference.params)
        for dependency_name, specification in reference.dependencies.items():
            constructor_name = "llm_client" if dependency_name == "llm" else dependency_name
            kwargs[constructor_name] = self._dependency(dependency_name, specification)
        for key, value in self.constructor_kwargs.items():
            kwargs.setdefault(key, value)
        return plugin_class(**kwargs)


def _safe_resolution_error(error: Exception) -> str:
    """Return a bounded error category without copying secret-bearing text.

    Args:
        error (Exception): Candidate resolution exception.

    Raises:
        None.

    Returns:
        str: Stable exception class marker.
    """
    return f"{type(error).__module__}.{type(error).__qualname__}"


def bind_agent_graph(
    source: AgentGraph | CompilationResult,
    resolver: ComponentResolver,
) -> BoundAgentGraph:
    """Validate and bind an AgentGraph to runtime component instances.

    Args:
        source (AgentGraph | CompilationResult): Graph or successful compilation result.
        resolver (ComponentResolver): Explicit runtime component resolver.

    Raises:
        GraphBindingError: Compilation, validation, resolution, or role adaptation fails.

    Returns:
        BoundAgentGraph: Validated graph paired with adapted candidates.
    """
    if isinstance(source, CompilationResult):
        if not source.is_success or source.graph is None:
            raise GraphBindingError(
                "runtime.compilation_incomplete",
                "CompilationResult must be successful before binding",
                phase="binding",
                details={"diagnostic_count": len(source.diagnostics)},
            )
        graph = source.graph
    elif isinstance(source, AgentGraph):
        graph = source
    else:
        raise GraphBindingError(
            "runtime.source_type",
            "Graph runtime binding requires AgentGraph or CompilationResult",
            phase="binding",
        )
    validation = validate_graph(graph)
    if not validation.is_valid:
        raise GraphBindingError(
            "runtime.graph_invalid",
            "AgentGraph validation failed before component resolution",
            phase="binding",
            details={"diagnostics": [item.code for item in validation.errors]},
        )

    components: dict[str, BoundComponent] = {}
    for node in graph.nodes:
        if node.kind is not NodeKind.COMPONENT or node.component is None or node.role is None:
            continue
        candidates: list[BoundCandidate] = []
        for reference in node.component.candidates:
            try:
                instance = resolver.resolve(reference, node.role)
                adapted = adapt_component(ComponentRole(node.role.value), instance)
                candidates.append(BoundCandidate(reference=reference, instance=adapted))
            except Exception as error:
                candidates.append(
                    BoundCandidate(
                        reference=reference,
                        error=_safe_resolution_error(error),
                    )
                )
        if not any(candidate.instance is not None for candidate in candidates):
            raise GraphBindingError(
                "runtime.component_unresolved",
                f"No candidate could be resolved for node {node.id!r}",
                node_id=node.id,
                phase="binding",
                details={
                    "candidates": [
                        f"{item.reference.namespace}:{item.reference.name}" for item in candidates
                    ],
                    "errors": [item.error for item in candidates],
                },
            )
        components[node.id] = BoundComponent(node=node, candidates=tuple(candidates))
    return BoundAgentGraph(graph=graph, components=components)


def invoke_bound_component(
    bound: BoundComponent,
    input_value: Any,
    runtime: RuntimeContext,
) -> tuple[Any, BoundCandidate]:
    """Invoke a bound node using ordered, run-sticky fallback semantics.

    Args:
        bound (BoundComponent): Bound logical node.
        input_value (Any): Role-specific typed input.
        runtime (RuntimeContext): Shared run context.

    Raises:
        GraphExecutionError: Every usable candidate fails or no candidate exists.

    Returns:
        tuple[Any, BoundCandidate]: Component output and selected candidate.
    """
    state_key = f"runtime.fallback.{bound.node_id}"
    selected = runtime.state.strategy_state.get(state_key)
    start_index = int(selected) if isinstance(selected, int) else 0
    indices = list(range(start_index, len(bound.candidates)))
    if start_index > 0:
        indices.extend(range(0, start_index))
    # Device actions are not generally idempotent, so an ActionExecutor never
    # changes candidate after a call has started.
    if bound.node.role is GraphRole.ACTION_EXECUTOR:
        indices = indices[:1]
    failures: list[str] = []
    for index in indices:
        candidate = bound.candidates[index]
        if candidate.instance is None:
            failures.append(candidate.error or "unresolved")
            continue
        try:
            output = candidate.instance.invoke(input_value, runtime)
            previous = runtime.state.strategy_state.get(state_key)
            runtime.state.strategy_state[state_key] = index
            if previous != index and (previous is not None or index > 0):
                runtime.emit(
                    phase="fallback",
                    role=bound.node.role.value,
                    component=candidate.reference.name,
                    kind="fallback_selected",
                    node_id=bound.node_id,
                    payload={"candidate_index": index},
                )
            return output, candidate
        except Exception as error:
            failures.append(_safe_resolution_error(error))
            runtime.emit(
                phase="fallback",
                role=bound.node.role.value,
                component=candidate.reference.name,
                kind="fallback_candidate_failed",
                node_id=bound.node_id,
                payload={"candidate_index": index, "error_type": failures[-1]},
            )
            if bound.node.role is GraphRole.ACTION_EXECUTOR:
                break
    raise GraphExecutionError(
        "runtime.component_candidates_exhausted",
        f"All component candidates failed for node {bound.node_id!r}",
        node_id=bound.node_id,
        phase=bound.node.lifecycle.value,
        details={"error_types": failures},
    )
