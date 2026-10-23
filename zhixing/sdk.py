"""Public compile-and-run facade for graph-native ZhiXing Mobile Agents."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from zhixing.components import AgentState, ObservationRequest, RunResult, RunStatus, RuntimeContext, TaskInput
from zhixing.graph import AgentGraph, CompilationResult, compile_agent_yaml
from zhixing.graph.contracts import NodeContractCatalog
from zhixing.catalog import (
    BUILTIN_COMPONENT_CATALOG,
    ComponentCatalogError,
    DiscoveredComponentEnvironment,
    DiscoveryReport,
    create_component_resolver,
    discover_components,
    empty_component_environment,
)
from zhixing.runtime.errors import GraphBindingError
from zhixing.runtime.kernel import bind_execution_plan


ResolverFactory = Callable[[], Any]


@dataclass(frozen=True)
class AgentRunConfig:
    """Describe one Android run without changing AgentGraph identity."""

    platform: str = "android"
    serial: str | None = None
    artifact_root: Path = Path("temp/runs")
    max_steps: int = 15
    max_activations: int | None = None
    include_ui_tree: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate and normalize environment-only run configuration.

        Args:
            None.

        Raises:
            ValueError: Platform or maximum step count is unsupported.

        Returns:
            None.
        """
        if self.platform != "android":
            raise ValueError("ExecutableAgent currently supports platform='android' only")
        if not 1 <= self.max_steps <= 1000:
            raise ValueError("max_steps must be between 1 and 1000")
        if self.max_activations is not None and not 1 <= self.max_activations <= 100000:
            raise ValueError("max_activations must be between 1 and 100000")
        object.__setattr__(self, "artifact_root", Path(self.artifact_root))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class ExecutableAgent:
    """Immutable AgentGraph recipe that creates fresh run-scoped components."""

    graph: AgentGraph
    resolver_factory: ResolverFactory = field(repr=False, compare=False)
    contract_catalog: NodeContractCatalog | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    discovery_report: DiscoveryReport | None = field(
        default=None,
        repr=False,
        compare=False,
    )

    @property
    def canonical_hash(self) -> str:
        """Return the semantic identity shared by YAML and SDK definitions.

        Args:
            None.

        Raises:
            ValueError: The graph is no longer valid.

        Returns:
            str: SHA-256-prefixed canonical AgentGraph hash.
        """
        return self.graph.canonical_hash(contract_catalog=self.contract_catalog)

    def run(
        self,
        task: str | TaskInput,
        run_config: AgentRunConfig | None = None,
        *,
        device: Any | None = None,
        event_sink: Any | None = None,
        runtime: RuntimeContext | None = None,
    ) -> RunResult:
        """Bind fresh components and execute one task through AndroidGraphRuntime.

        Args:
            task (str | TaskInput): Natural-language task or typed task input.
            run_config (AgentRunConfig | None): Device and artifact configuration.
            device (Any | None): Explicit fake device for deterministic tests.
            event_sink (Any | None): Optional live RunEvent callback.
            runtime (RuntimeContext | None): Optional caller-owned isolated context.

        Raises:
            None: Binding and execution failures are normalized as RunResult.

        Returns:
            RunResult: Structured outcome and auditable runtime evidence.
        """
        selected_task = task if isinstance(task, TaskInput) else TaskInput(str(task).strip())
        config = run_config or AgentRunConfig()
        if not selected_task.instruction.strip():
            return _failed_run(
                "sdk.task_empty",
                "Mobile Agent task must not be empty",
            )
        selected_runtime = runtime or RuntimeContext(
            max_steps=config.max_steps,
            max_activations=config.max_activations,
            state=AgentState(current_task=selected_task),
            event_sink=event_sink,
            metadata=dict(config.metadata),
        )
        selected_runtime.max_steps = min(selected_runtime.max_steps, config.max_steps)
        if config.max_activations is not None:
            selected_runtime.max_activations = (
                min(selected_runtime.max_activations, config.max_activations)
                if selected_runtime.max_activations is not None
                else config.max_activations
            )
        selected_runtime.state.current_task = selected_task
        if event_sink is not None:
            selected_runtime.event_sink = event_sink
        selected_runtime.metadata.update(dict(config.metadata))
        selected_runtime.metadata["agent_graph_hash"] = self.canonical_hash
        try:
            # A new resolver creates new Memory and fallback state for every run.
            plan = bind_execution_plan(
                self.graph,
                self.resolver_factory(),
                contract_catalog=self.contract_catalog,
            )
        except Exception as error:
            return _failed_run(
                "sdk.binding_failed",
                f"AgentGraph binding failed ({type(error).__name__})",
                runtime=selected_runtime,
            )
        from zhixing.runtime.android import AndroidGraphRuntime

        return AndroidGraphRuntime().run(
            plan,
            {
                "task": selected_task,
                "value": ObservationRequest(
                    include_ui_tree=config.include_ui_tree,
                ),
            },
            artifact_root=config.artifact_root,
            serial=config.serial,
            runtime=selected_runtime,
            device=device,
        )


def _failed_run(
    code: str,
    message: str,
    *,
    runtime: RuntimeContext | None = None,
) -> RunResult:
    """Create a safe pre-execution RunResult.

    Args:
        code (str): Stable failure code.
        message (str): Non-sensitive explanation.
        runtime (RuntimeContext | None): Optional allocated run context.

    Raises:
        None.

    Returns:
        RunResult: Structured failure without a false execution claim.
    """
    context = runtime or RuntimeContext()
    return RunResult(
        run_id=context.run_id,
        status=RunStatus.FAILURE,
        state=context.state,
        error=message,
        error_details={"code": code},
        kernel_status="not_started",
    )


def _unwrap_source(
    source: AgentGraph | CompilationResult,
    *,
    contract_catalog: NodeContractCatalog | None = None,
) -> AgentGraph:
    """Extract one successful contract 1.1 graph.

    Args:
        source (AgentGraph | CompilationResult): Graph or compiler result.
        contract_catalog (NodeContractCatalog | None): Explicit external
            contracts used only for validation.

    Raises:
        GraphBindingError: Compilation failed or the contract is unsupported.

    Returns:
        AgentGraph: Valid contract 1.1 graph.
    """
    if isinstance(source, CompilationResult):
        if not source.is_success or source.graph is None:
            raise GraphBindingError(
                "sdk.compilation_failed",
                "Agent configuration did not compile successfully",
                phase="compilation",
                details={
                    "diagnostics": [item.code for item in source.diagnostics],
                },
            )
        graph = source.graph
    elif isinstance(source, AgentGraph):
        graph = source
    else:
        raise GraphBindingError(
            "sdk.source_type",
            "compile_agent requires AgentGraph or CompilationResult",
            phase="compilation",
        )
    if graph.contract_version != "1.1":
        raise GraphBindingError(
            "sdk.contract_unsupported",
            "The new SDK executes graph-native contract 1.1 only; "
            "use run.py for unsupported AgentConfig V1 strategies",
            phase="compilation",
        )
    validation = graph.validate_graph(contract_catalog=contract_catalog)
    if not validation.is_valid:
        raise GraphBindingError(
            "sdk.graph_invalid",
            "AgentGraph validation failed",
            phase="validation",
            details={"diagnostics": [item.code for item in validation.errors]},
        )
    return graph


def _preflight_component_references(
    graph: AgentGraph,
    environment: DiscoveredComponentEnvironment,
) -> None:
    """Check every reference against external and built-in catalogs.

    Args:
        graph (AgentGraph): Valid contract 1.1 graph.
        environment (DiscoveredComponentEnvironment): Explicit discovery result.

    Raises:
        GraphBindingError: A component or nested dependency is unknown.

    Returns:
        None.
    """
    unknown: list[str] = []
    for node in graph.nodes:
        if node.component is None:
            continue
        for reference in node.component.candidates:
            built_in = BUILTIN_COMPONENT_CATALOG.get(
                reference.namespace,
                reference.name,
            )
            external_versions = environment.catalog.available_versions(
                reference.namespace,
                reference.name,
            )
            if reference.version is None and built_in is not None and external_versions:
                raise GraphBindingError(
                    "component.catalog_version_ambiguous",
                    "The component reference requires an explicit version",
                    phase="preflight",
                    details={
                        "component": f"{reference.namespace}:{reference.name}",
                        "available_versions": sorted(
                            {*external_versions, built_in.version}
                        ),
                    },
                )
            try:
                environment.catalog.resolve(reference)
            except ComponentCatalogError as error:
                builtin_matches = built_in is not None and (
                    reference.version is None or reference.version == built_in.version
                )
                if error.code == "component.catalog_version_not_found" and builtin_matches:
                    continue
                if error.code != "component.catalog_not_found":
                    raise GraphBindingError(
                        error.code,
                        str(error),
                        phase="preflight",
                        details=dict(error.details),
                    ) from error
                if built_in is None:
                    unknown.append(f"{reference.namespace}:{reference.name}")
                elif reference.version is not None and reference.version != built_in.version:
                    unknown.append(
                        f"{reference.namespace}:{reference.name}@{reference.version}"
                    )
            for dependency in reference.dependencies.values():
                if not isinstance(dependency, Mapping) or not dependency.get("name"):
                    continue
                namespace = str(dependency.get("namespace") or "llm")
                name = str(dependency["name"])
                if BUILTIN_COMPONENT_CATALOG.get(namespace, name) is None:
                    unknown.append(f"{namespace}:{name}")
    if unknown:
        failures = [item.to_safe_dict() for item in environment.report.failures]
        raise GraphBindingError(
            "sdk.component_discovery_failed" if failures else "sdk.component_unknown",
            "AgentGraph references components unavailable from loaded catalogs",
            phase="preflight",
            details={
                "components": sorted(set(unknown)),
                "provider_failures": failures,
            },
        )


def compile_agent(
    source: AgentGraph | CompilationResult,
    *,
    secrets: Mapping[str, Any] | Callable[[str], Any] | None = None,
    dependencies: Mapping[str, Any] | None = None,
    resolver_factory: ResolverFactory | None = None,
    component_environment: DiscoveredComponentEnvironment | None = None,
) -> ExecutableAgent:
    """Compile a graph definition into a reusable run-scoped agent recipe.

    Args:
        source (AgentGraph | CompilationResult): Graph or successful compiler output.
        secrets (Mapping[str, Any] | Callable[[str], Any] | None): SecretRef provider.
        dependencies (Mapping[str, Any] | None): Prebuilt runtime dependencies.
        resolver_factory (ResolverFactory | None): Explicit test/extension resolver factory.
        component_environment (DiscoveredComponentEnvironment | None): Explicit
            external discovery result. This function never scans the environment.

    Raises:
        GraphBindingError: Compilation, validation, or reference preflight fails.

    Returns:
        ExecutableAgent: Immutable definition with fresh per-run binding.
    """
    environment = component_environment or empty_component_environment()
    try:
        graph = _unwrap_source(
            source,
            contract_catalog=environment.contract_catalog,
        )
    except GraphBindingError as error:
        failures = [item.to_safe_dict() for item in environment.report.failures]
        if failures and error.info.code in {"sdk.compilation_failed", "sdk.graph_invalid"}:
            raise GraphBindingError(
                "sdk.component_discovery_failed",
                "AgentGraph validation depends on a provider that failed to load",
                phase="preflight",
                details={"provider_failures": failures},
            ) from error
        raise
    if resolver_factory is None:
        _preflight_component_references(graph, environment)

        def default_factory() -> Any:
            """Create fresh external and built-in components for one run.

            Args:
                None.

            Raises:
                None.

            Returns:
                Any: Run-scoped composite production resolver.
            """
            return create_component_resolver(
                environment,
                secrets=secrets,
                dependencies=dependencies,
            )

        selected_factory: ResolverFactory = default_factory
    else:
        selected_factory = resolver_factory
    return ExecutableAgent(
        graph=graph,
        resolver_factory=selected_factory,
        contract_catalog=environment.contract_catalog,
        discovery_report=environment.report,
    )


def load_agent(
    path: str | Path,
    *,
    secrets: Mapping[str, Any] | Callable[[str], Any] | None = None,
    dependencies: Mapping[str, Any] | None = None,
    resolver_factory: ResolverFactory | None = None,
    component_environment: DiscoveredComponentEnvironment | None = None,
    discover_external: bool = True,
    plugin_allowlist: tuple[str, ...] | None = None,
    plugin_denylist: tuple[str, ...] = (),
) -> ExecutableAgent:
    """Load graph-native YAML and return the same SDK executable facade.

    Args:
        path (str | Path): Graph-native YAML or legacy AgentConfig path.
        secrets (Mapping[str, Any] | Callable[[str], Any] | None): SecretRef provider.
        dependencies (Mapping[str, Any] | None): Prebuilt runtime dependencies.
        resolver_factory (ResolverFactory | None): Explicit resolver factory.
        component_environment (DiscoveredComponentEnvironment | None): Explicit
            prebuilt discovery environment, which takes precedence.
        discover_external (bool): Whether this high-level entry point explicitly
            scans installed component Entry Points.
        plugin_allowlist (tuple[str, ...] | None): Optional provider allowlist.
        plugin_denylist (tuple[str, ...]): Provider denylist.

    Raises:
        GraphBindingError: YAML is invalid or compiles to unsupported contract 1.0.

    Returns:
        ExecutableAgent: Reusable run-scoped agent recipe.
    """
    environment = component_environment
    if environment is None:
        environment = (
            discover_components(
                allowlist=plugin_allowlist,
                denylist=plugin_denylist,
            )
            if discover_external
            else empty_component_environment()
        )
    return compile_agent(
        compile_agent_yaml(path, contract_catalog=environment.contract_catalog),
        secrets=secrets,
        dependencies=dependencies,
        resolver_factory=resolver_factory,
        component_environment=environment,
    )


__all__ = [
    "AgentRunConfig",
    "ExecutableAgent",
    "compile_agent",
    "load_agent",
]
