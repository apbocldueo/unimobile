"""Side-effect-free runtime readiness projections for ordinary Studio Runs."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any, Literal

from pydantic import Field

from zhixing.graph import AgentGraph, EdgeKind, NodeKind, PredicateOperator

from .catalog import StudioComponentCatalog, StudioComponentDescriptor
from .benchmark_models import StudioDeviceProfileV1
from .device_profiles import AndroidDeviceProfileResolver
from .models import StudioModel
from .repository import AgentDocumentRepository
from .revision_verifier import verify_immutable_agent_revision
from .run_errors import StudioRunValidationError
from .run_execution import ProductionComponentResolverFactory
from .run_models import RunSnapshotV1


_SECRET_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_MAX_DIAGNOSTICS = 128


RuntimeReadinessCategory = Literal[
    "revision",
    "component",
    "secret",
    "profile",
    "topology",
]


class RuntimeReadinessDiagnosticV1(StudioModel):
    """One bounded safe static-readiness diagnostic."""

    code: str = Field(min_length=1, max_length=160)
    category: RuntimeReadinessCategory
    message: str = Field(min_length=1, max_length=500)
    subject_identity: str | None = Field(default=None, max_length=160)
    node_id: str | None = Field(default=None, max_length=128)
    remediation_key: str = Field(min_length=1, max_length=160)


class StudioAndroidTopologyFactsV1(StudioModel):
    """Bounded contract-derived facts for one ordinary Android Run graph."""

    schema_version: Literal[1] = 1
    observe_node_ids: tuple[str, ...] = Field(default=(), max_length=128)
    action_request_node_ids: tuple[str, ...] = Field(default=(), max_length=128)
    action_executor_node_ids: tuple[str, ...] = Field(default=(), max_length=128)
    terminal_node_ids: tuple[str, ...] = Field(default=(), max_length=128)
    output_node_ids: tuple[str, ...] = Field(default=(), max_length=128)
    has_typed_action_request: bool
    has_terminal_gated_output: bool
    has_nonterminal_feedback: bool
    policies_bounded: bool


class RuntimeProviderStatusV1(StudioModel):
    """Safe process-level availability for one runtime provider."""

    identifier: str = Field(min_length=1, max_length=300)
    category: str = Field(min_length=1, max_length=80)
    available: bool
    error_type: str = Field(default="", max_length=160)


class RuntimeSecretStatusV1(StudioModel):
    """Expose only whether one known SecretRef identity is configured."""

    secret_ref: str = Field(min_length=1, max_length=128)
    configured: bool


class RuntimeEnvironmentReadinessV1(StudioModel):
    """Versioned process-level static runtime configuration projection."""

    schema_version: Literal[1] = 1
    ready: bool
    providers: tuple[RuntimeProviderStatusV1, ...] = Field(max_length=256)
    secrets: tuple[RuntimeSecretStatusV1, ...] = Field(max_length=256)
    device_profiles: tuple[StudioDeviceProfileV1, ...] = Field(max_length=64)
    diagnostics: tuple[RuntimeReadinessDiagnosticV1, ...] = Field(
        default=(), max_length=_MAX_DIAGNOSTICS
    )


class ExactRevisionReadinessV1(StudioModel):
    """Versioned static readiness for one immutable Agent revision/Profile."""

    schema_version: Literal[1] = 1
    agent_id: str = Field(min_length=1, max_length=160)
    revision_id: str = Field(min_length=1, max_length=160)
    canonical_hash: str | None = Field(
        default=None, pattern=r"^sha256:[0-9a-f]{64}$"
    )
    device_profile_id: str = Field(min_length=1, max_length=160)
    ready: bool
    diagnostics: tuple[RuntimeReadinessDiagnosticV1, ...] = Field(
        default=(), max_length=_MAX_DIAGNOSTICS
    )


def _diagnostic(
    code: str,
    category: RuntimeReadinessCategory,
    message: str,
    remediation_key: str,
    subject_identity: str | None = None,
    node_id: str | None = None,
) -> RuntimeReadinessDiagnosticV1:
    """Build one safe bounded readiness diagnostic.

    Args:
        code: Stable error code.
        category: Readiness layer responsible for the block.
        message: Safe reader-facing explanation.
        remediation_key: Stable UI/documentation action key.
        subject_identity: Optional safe Catalog, SecretRef, or Profile identity.
        node_id: Optional stable AgentGraph source locator.

    Raises:
        ValueError: A caller supplies an invalid bounded identity.

    Returns:
        RuntimeReadinessDiagnosticV1: Strict diagnostic DTO.
    """
    return RuntimeReadinessDiagnosticV1(
        code=code,
        category=category,
        message=message,
        subject_identity=subject_identity,
        node_id=node_id,
        remediation_key=remediation_key,
    )


def _ordinary_reachable_nodes(
    graph: AgentGraph,
    start_node_ids: Iterable[str],
) -> set[str]:
    """Return nodes reachable without crossing a feedback boundary.

    Args:
        graph: Immutable graph under static analysis.
        start_node_ids: Stable starting node identities.

    Raises:
        None.

    Returns:
        set[str]: Starting nodes and ordinary data/control descendants.
    """
    adjacency: dict[str, set[str]] = {}
    for edge in graph.edges:
        if edge.kind is EdgeKind.FEEDBACK:
            continue
        adjacency.setdefault(edge.source.node, set()).add(edge.target.node)
    reachable = set(start_node_ids)
    queue = list(reachable)
    while queue:
        current = queue.pop(0)
        for target in sorted(adjacency.get(current, ())):
            if target in reachable:
                continue
            reachable.add(target)
            queue.append(target)
    return reachable


def analyze_studio_android_topology(
    graph: AgentGraph,
) -> tuple[StudioAndroidTopologyFactsV1, tuple[RuntimeReadinessDiagnosticV1, ...]]:
    """Analyze explicit ordinary-Run observation/action/feedback topology.

    The analysis is contract- and edge-derived. It never binds components,
    resolves secrets, connects a device, mutates the graph, or changes its
    canonical identity.

    Args:
        graph: Valid immutable AgentGraph selected for a Studio Android Run.

    Raises:
        None.

    Returns:
        tuple: Typed topology facts and stable safe blocking diagnostics.
    """
    input_ids = tuple(
        sorted(node.id for node in graph.nodes if node.kind is NodeKind.INPUT)
    )
    reachable = _ordinary_reachable_nodes(graph, input_ids)
    observe_ids = tuple(
        sorted(
            node.id
            for node in graph.nodes
            if node.id in reachable
            and node.contract is not None
            and node.contract.id == "zhixing.service.device_observe"
        )
    )
    action_request_ids = tuple(
        sorted(
            node.id
            for node in graph.nodes
            if node.id in reachable
            and node.contract is not None
            and node.contract.id == "zhixing.control.action_request"
        )
    )
    action_executor_ids = tuple(
        sorted(
            node.id
            for node in graph.nodes
            if node.id in reachable
            and node.contract is not None
            and node.contract.id == "zhixing.service.action_executor"
        )
    )
    terminal_ids = tuple(
        sorted(
            node.id
            for node in graph.nodes
            if node.id in reachable
            and node.kind is NodeKind.CONDITION
            and node.predicate is not None
            and node.predicate.field == "terminal_status"
            and node.predicate.operator
            in {PredicateOperator.EXISTS, PredicateOperator.TRUTHY}
        )
    )
    output_ids = tuple(
        sorted(
            node.id
            for node in graph.nodes
            if node.id in reachable and node.kind is NodeKind.OUTPUT
        )
    )

    has_typed_request = any(
        edge.kind is EdgeKind.DATA
        and edge.source.node in action_request_ids
        and edge.source.port == "request"
        and edge.target.node in action_executor_ids
        and edge.target.port == "request"
        for edge in graph.edges
    )
    terminal_to_output = {
        edge.source.node
        for edge in graph.edges
        if edge.kind is EdgeKind.CONTROL
        and edge.source.node in terminal_ids
        and edge.source.port == "true"
        and edge.target.node in output_ids
        and edge.target.port == "control"
    }
    executor_to_terminal = {
        edge.target.node
        for edge in graph.edges
        if edge.kind is EdgeKind.DATA
        and edge.source.node in action_executor_ids
        and edge.source.port == "result"
        and edge.target.node in terminal_ids
        and edge.target.port == "value"
    }
    executor_to_output = any(
        edge.kind is EdgeKind.DATA
        and edge.source.node in action_executor_ids
        and edge.source.port == "result"
        and edge.target.node in output_ids
        and edge.target.port == "result"
        for edge in graph.edges
    )
    has_terminal_gate = bool(
        terminal_to_output.intersection(executor_to_terminal)
    ) and executor_to_output

    has_feedback = False
    for edge in graph.edges:
        feedback = edge.feedback
        if (
            edge.kind is not EdgeKind.FEEDBACK
            or feedback is None
            or edge.source.node not in action_executor_ids
            or edge.source.port != "result"
            or feedback.predicate.field != "terminal_status"
            or feedback.predicate.operator is not PredicateOperator.FALSY
        ):
            continue
        descendants = _ordinary_reachable_nodes(graph, (edge.target.node,))
        if descendants.intersection(observe_ids):
            has_feedback = True
            break
    policies_bounded = (
        graph.policies.max_steps >= 1
        and graph.policies.max_feedback_iterations >= 1
        and all(
            edge.feedback is None
            or edge.feedback.max_iterations
            <= graph.policies.max_feedback_iterations
            for edge in graph.edges
        )
    )
    facts = StudioAndroidTopologyFactsV1(
        observe_node_ids=observe_ids,
        action_request_node_ids=action_request_ids,
        action_executor_node_ids=action_executor_ids,
        terminal_node_ids=terminal_ids,
        output_node_ids=output_ids,
        has_typed_action_request=has_typed_request,
        has_terminal_gated_output=has_terminal_gate,
        has_nonterminal_feedback=has_feedback,
        policies_bounded=policies_bounded,
    )
    diagnostics: list[RuntimeReadinessDiagnosticV1] = []
    if not observe_ids:
        diagnostics.append(
            _diagnostic(
                "studio.readiness.topology_observation_missing",
                "topology",
                "Android Run requires an explicit reachable DeviceObserve service",
                "rebuild-with-standard-mobile-agent-template",
            )
        )
    if not action_executor_ids:
        legacy = next(
            (
                node
                for node in graph.nodes
                if node.role is not None and node.role.value == "action_executor"
            ),
            None,
        )
        diagnostics.append(
            _diagnostic(
                (
                    "studio.readiness.topology_legacy_action_executor"
                    if legacy is not None
                    else "studio.readiness.topology_action_executor_missing"
                ),
                "topology",
                "Android Run requires the explicit ActionExecutor service boundary",
                "rebuild-with-standard-mobile-agent-template",
                node_id=legacy.id if legacy is not None else None,
            )
        )
    if action_executor_ids and not has_typed_request:
        diagnostics.append(
            _diagnostic(
                "studio.readiness.topology_action_request_missing",
                "topology",
                "ActionExecutor must receive a typed ActionRequest",
                "repair-agent-feedback-loop",
                node_id=action_executor_ids[0],
            )
        )
    if action_executor_ids and not has_terminal_gate:
        diagnostics.append(
            _diagnostic(
                "studio.readiness.topology_terminal_gate_missing",
                "topology",
                "Output must be gated by an explicit DONE/FAIL terminal condition",
                "repair-agent-feedback-loop",
                node_id=action_executor_ids[0],
            )
        )
    if action_executor_ids and not has_feedback:
        diagnostics.append(
            _diagnostic(
                "studio.readiness.topology_feedback_missing",
                "topology",
                "Nonterminal ActionResult must have bounded feedback to DeviceObserve",
                "repair-agent-feedback-loop",
                node_id=action_executor_ids[0],
            )
        )
    if not policies_bounded:
        diagnostics.append(
            _diagnostic(
                "studio.readiness.topology_policy_unbounded",
                "topology",
                "Android feedback and graph policies must use consistent finite limits",
                "repair-agent-feedback-loop",
            )
        )
    return facts, tuple(diagnostics)


def _iter_graphs(graph: AgentGraph) -> Iterable[AgentGraph]:
    """Yield a graph and all inline nested graphs without resolving references.

    Args:
        graph: Valid immutable AgentGraph.

    Raises:
        None.

    Returns:
        Iterable[AgentGraph]: Depth-first graph sequence.
    """
    yield graph
    for node in graph.nodes:
        specs = []
        if node.subgraph is not None:
            specs.append(node.subgraph)
        if node.loop is not None:
            specs.append(node.loop.body)
        for spec in specs:
            if isinstance(spec.graph, AgentGraph):
                yield from _iter_graphs(spec.graph)


def _secret_refs(value: Any) -> set[str]:
    """Collect stable SecretRef identities from safe graph configuration.

    Args:
        value: JSON-compatible component configuration.

    Raises:
        None.

    Returns:
        set[str]: Referenced stable identities; malformed refs are omitted.
    """
    found: set[str] = set()
    if isinstance(value, Mapping):
        if set(value) == {"secret_ref"}:
            candidate = value.get("secret_ref")
            if isinstance(candidate, str) and _SECRET_REF.fullmatch(candidate):
                found.add(candidate)
        for item in value.values():
            found.update(_secret_refs(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(_secret_refs(item))
    return found


def _has_malformed_secret_ref(value: Any) -> bool:
    """Detect SecretRef-shaped mappings that cannot be resolved safely.

    Args:
        value: JSON-compatible component configuration.

    Raises:
        None.

    Returns:
        bool: Whether any nested ``secret_ref`` mapping has an unsafe shape.
    """
    if isinstance(value, Mapping):
        if "secret_ref" in value and (
            set(value) != {"secret_ref"}
            or not isinstance(value.get("secret_ref"), str)
            or _SECRET_REF.fullmatch(str(value.get("secret_ref"))) is None
        ):
            return True
        return any(_has_malformed_secret_ref(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_has_malformed_secret_ref(item) for item in value)
    return False


class StudioRuntimeReadinessService:
    """Evaluate static configuration without constructing or executing resources."""

    def __init__(
        self,
        *,
        agents: AgentDocumentRepository,
        catalog: StudioComponentCatalog,
        components: ProductionComponentResolverFactory,
        profiles: AndroidDeviceProfileResolver,
        secrets: Mapping[str, Any] | None = None,
        contract_catalog: Any | None = None,
        known_secret_refs: tuple[str, ...] = (),
    ) -> None:
        """Configure immutable metadata and trusted presence-only authorities.

        Args:
            agents: Immutable revision repository.
            catalog: Exact process Component Catalog snapshot.
            components: Runtime resolver factory used for static availability.
            profiles: Trusted static Device Profile authority.
            secrets: Process-scoped SecretRef value mapping.
            contract_catalog: Optional exact NodeContract extension catalog.
            known_secret_refs: Safe allowlisted identities shown in Settings.

        Raises:
            ValueError: A known SecretRef identity is malformed or duplicated.

        Returns:
            None.
        """
        configured_secret_refs = tuple(str(item) for item in (secrets or {}))
        visible_secret_refs = tuple(
            sorted(set(known_secret_refs).union(configured_secret_refs))
        )
        if len(known_secret_refs) != len(set(known_secret_refs)) or any(
            _SECRET_REF.fullmatch(item) is None for item in visible_secret_refs
        ):
            raise ValueError("known SecretRef identities must be unique and stable")
        self.agents = agents
        self.catalog = catalog
        self.components = components
        self.profiles = profiles
        self.secrets = secrets or {}
        self.contract_catalog = contract_catalog
        self.known_secret_refs = visible_secret_refs
        self._descriptors = {
            (item.namespace, item.name, item.version): item
            for item in catalog.components
        }

    def process_readiness(self) -> RuntimeEnvironmentReadinessV1:
        """Project process component, known secret, and profile availability.

        Args:
            None.

        Raises:
            None.

        Returns:
            RuntimeEnvironmentReadinessV1: Safe side-effect-free projection.
        """
        providers = tuple(
            RuntimeProviderStatusV1(
                identifier=item.identifier,
                category=item.category,
                available=item.availability.available,
                error_type=item.availability.error_type,
            )
            for item in self.catalog.components
            if item.namespace == "llm" or item.category == "runtime_service"
        )
        secrets = tuple(
            RuntimeSecretStatusV1(
                secret_ref=identity,
                configured=identity in self.secrets,
            )
            for identity in self.known_secret_refs
        )
        profiles = self.profiles.safe_profiles()
        diagnostics: list[RuntimeReadinessDiagnosticV1] = []
        for provider in providers:
            if not provider.available:
                diagnostics.append(
                    _diagnostic(
                        "studio.readiness.provider_unavailable",
                        "component",
                        "A runtime provider is unavailable",
                        "install-provider-dependency",
                        provider.identifier,
                    )
                )
        for secret in secrets:
            if not secret.configured:
                diagnostics.append(
                    _diagnostic(
                        "studio.readiness.secret_missing",
                        "secret",
                        "A known SecretRef is not configured",
                        "configure-studio-secrets",
                        secret.secret_ref,
                    )
                )
        if not profiles:
            diagnostics.append(
                _diagnostic(
                    "studio.readiness.profile_empty",
                    "profile",
                    "No safe Android Device Profile is configured",
                    "configure-device-profile",
                )
            )
        ordered = self._ordered(diagnostics)
        return RuntimeEnvironmentReadinessV1(
            ready=not ordered,
            providers=providers,
            secrets=secrets,
            device_profiles=profiles,
            diagnostics=ordered,
        )

    def revision_readiness(
        self,
        agent_id: str,
        revision_id: str,
        device_profile_id: str,
    ) -> ExactRevisionReadinessV1:
        """Evaluate one immutable revision and selected static Profile authority.

        Args:
            agent_id: Selected Agent identity.
            revision_id: Exact immutable revision identity.
            device_profile_id: Safe selected Device Profile identity.

        Raises:
            AgentRevisionNotFoundError: The exact revision does not exist.

        Returns:
            ExactRevisionReadinessV1: Safe exact readiness result.
        """
        try:
            snapshot = verify_immutable_agent_revision(
                self.agents,
                agent_id,
                revision_id,
                contract_catalog=self.contract_catalog,
                component_catalog=self.catalog,
            )
        except StudioRunValidationError as error:
            return ExactRevisionReadinessV1(
                agent_id=agent_id,
                revision_id=revision_id,
                device_profile_id=device_profile_id,
                ready=False,
                diagnostics=(
                    _diagnostic(
                        error.code,
                        "revision",
                        error.message,
                        "save-valid-agent-revision",
                        revision_id,
                    ),
                ),
            )
        return self.snapshot_readiness(snapshot, device_profile_id)

    def snapshot_readiness(
        self,
        snapshot: RunSnapshotV1,
        device_profile_id: str,
    ) -> ExactRevisionReadinessV1:
        """Evaluate a verified snapshot with metadata-only component authorities.

        Args:
            snapshot: Reverified immutable Run snapshot.
            device_profile_id: Safe selected Device Profile identity.

        Raises:
            ValueError: The snapshot is not a valid AgentGraph DTO.

        Returns:
            ExactRevisionReadinessV1: Bounded static readiness projection.
        """
        graph = AgentGraph.model_validate(snapshot.agent_graph)
        diagnostics: list[RuntimeReadinessDiagnosticV1] = []
        _topology_facts, topology_diagnostics = analyze_studio_android_topology(
            graph
        )
        diagnostics.extend(topology_diagnostics)
        if not self.profiles.contains(device_profile_id):
            diagnostics.append(
                _diagnostic(
                    "studio.device.profile_unknown",
                    "profile",
                    "Selected Android Device Profile is unavailable",
                    "select-device-profile",
                    device_profile_id,
                )
            )
        referenced_secrets: set[str] = set()
        for current in _iter_graphs(graph):
            validate_bindings = getattr(
                self.components, "validate_graph_bindings", None
            )
            if callable(validate_bindings):
                try:
                    validate_bindings(current)
                except StudioRunValidationError as error:
                    diagnostics.append(
                        _diagnostic(
                            error.code,
                            "component",
                            error.message,
                            "select-available-component",
                        )
                    )
            for node in current.nodes:
                if node.component is None:
                    continue
                for candidate in node.component.candidates:
                    descriptor = self._descriptor(
                        candidate.namespace, candidate.name, candidate.version
                    )
                    identity = (
                        f"{candidate.namespace}:{candidate.name}@"
                        f"{candidate.version or '*'}"
                    )
                    if descriptor is None:
                        diagnostics.append(
                            _diagnostic(
                                "studio.readiness.component_unavailable",
                                "component",
                                "An exact AgentGraph component is unavailable",
                                "select-available-component",
                                identity,
                            )
                        )
                        continue
                    if not descriptor.availability.available:
                        diagnostics.append(
                            _diagnostic(
                                "studio.readiness.component_unavailable",
                                "component",
                                "An AgentGraph component is unavailable",
                                "install-provider-dependency",
                                descriptor.identifier,
                            )
                        )
                    for slot in descriptor.dependency_slots:
                        slot_name = str(slot.get("name") or "")
                        dependency = candidate.dependencies.get(slot_name)
                        if dependency is None and slot.get("required") is True:
                            diagnostics.append(
                                _diagnostic(
                                    "studio.readiness.dependency_missing",
                                    "component",
                                    "A required component dependency is missing",
                                    "configure-component-dependency",
                                    f"{node.id}:{slot_name}",
                                )
                            )
                            continue
                        if isinstance(dependency, Mapping):
                            accepted_namespaces = tuple(
                                slot.get("acceptedNamespaces") or ()
                            )
                            dependency_namespace = dependency.get("namespace")
                            if (
                                dependency_namespace is None
                                and len(accepted_namespaces) == 1
                            ):
                                dependency_namespace = accepted_namespaces[0]
                            dependency_descriptor = self._descriptor(
                                str(dependency_namespace or ""),
                                str(dependency.get("name") or ""),
                                dependency.get("version"),
                            )
                            if (
                                dependency_descriptor is None
                                or not dependency_descriptor.availability.available
                            ):
                                diagnostics.append(
                                    _diagnostic(
                                        "studio.readiness.dependency_unavailable",
                                        "component",
                                        "A required component dependency is unavailable",
                                        "select-available-dependency",
                                        f"{node.id}:{slot_name}",
                                    )
                                )
                    if _has_malformed_secret_ref(candidate.params) or (
                        _has_malformed_secret_ref(candidate.dependencies)
                    ):
                        diagnostics.append(
                            _diagnostic(
                                "studio.readiness.secret_ref_invalid",
                                "secret",
                                "An AgentGraph SecretRef has an invalid shape",
                                "save-valid-agent-revision",
                                node.id,
                            )
                        )
                    referenced_secrets.update(_secret_refs(candidate.params))
                    referenced_secrets.update(_secret_refs(candidate.dependencies))
        for identity in sorted(referenced_secrets):
            if identity not in self.secrets:
                diagnostics.append(
                    _diagnostic(
                        "studio.readiness.secret_missing",
                        "secret",
                        "A referenced SecretRef is not configured",
                        "configure-studio-secrets",
                        identity,
                    )
                )
        ordered = self._ordered(diagnostics)
        return ExactRevisionReadinessV1(
            agent_id=snapshot.agent_id,
            revision_id=snapshot.revision_id,
            canonical_hash=snapshot.canonical_hash,
            device_profile_id=device_profile_id,
            ready=not ordered,
            diagnostics=ordered,
        )

    def _descriptor(
        self,
        namespace: str,
        name: str,
        version: Any,
    ) -> StudioComponentDescriptor | None:
        """Resolve one exact or unambiguous Catalog descriptor without imports.

        Args:
            namespace: Candidate namespace.
            name: Candidate component name.
            version: Optional exact version.

        Raises:
            None.

        Returns:
            StudioComponentDescriptor | None: Unique metadata-only descriptor.
        """
        if isinstance(version, str):
            return self._descriptors.get((namespace, name, version))
        matches = [
            item
            for (candidate_namespace, candidate_name, _), item in self._descriptors.items()
            if candidate_namespace == namespace and candidate_name == name
        ]
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _ordered(
        diagnostics: Iterable[RuntimeReadinessDiagnosticV1],
    ) -> tuple[RuntimeReadinessDiagnosticV1, ...]:
        """Deduplicate, order, and bound safe diagnostics deterministically.

        Args:
            diagnostics: Candidate diagnostic sequence.

        Raises:
            None.

        Returns:
            tuple[RuntimeReadinessDiagnosticV1, ...]: Stable bounded diagnostics.
        """
        unique = {
            (
                item.category,
                item.code,
                item.subject_identity or "",
                item.node_id or "",
                item.remediation_key,
            ): item
            for item in diagnostics
        }
        return tuple(unique[key] for key in sorted(unique))[:_MAX_DIAGNOSTICS]


__all__ = [
    "ExactRevisionReadinessV1",
    "RuntimeEnvironmentReadinessV1",
    "RuntimeProviderStatusV1",
    "RuntimeReadinessDiagnosticV1",
    "RuntimeSecretStatusV1",
    "StudioAndroidTopologyFactsV1",
    "StudioRuntimeReadinessService",
    "analyze_studio_android_topology",
]
