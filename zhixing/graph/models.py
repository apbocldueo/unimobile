"""Strict, side-effect-free models for the canonical AgentGraph V1 IR."""

from __future__ import annotations

import math
import re
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from .enums import (
    BindingPolicy,
    DataTypeId,
    EdgeKind,
    FeedbackExhaustedPolicy,
    GraphRole,
    NodeKind,
    NodeLifecycle,
    PredicateOperator,
    LoopExhaustedPolicy,
    StateMergePolicy,
    StateOperation,
    StateScope,
    SubgraphErrorPolicy,
)
from .contracts import NodeContractRef


_LOGICAL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
_PLACEHOLDER = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_.-]*)\}$")
_SECRET_KEYS = {
    "api_key",
    "apikey",
    "access_token",
    "auth_token",
    "authorization",
    "password",
    "secret",
    "secret_key",
}


class GraphModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True, frozen=True)


def _is_secret_key(value: str) -> bool:
    normalized = value.strip().lower().replace("-", "_")
    return normalized in _SECRET_KEYS or normalized.endswith(("_api_key", "_password", "_secret"))


def _validate_json(value: Any, path: tuple[Any, ...] = ()) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float at {path or ('<root>',)}")
        return
    if isinstance(value, SecretRef):
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_json(item, path + (index,))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string mapping key at {path + (key,)}")
            if _is_secret_key(key):
                allowed = isinstance(item, SecretRef) or (
                    isinstance(item, str) and _PLACEHOLDER.fullmatch(item) is not None
                ) or (
                    isinstance(item, Mapping)
                    and set(item.keys()) == {"secret_ref"}
                    and isinstance(item.get("secret_ref"), str)
                )
                if not allowed:
                    raise ValueError(f"resolved secret value is not allowed at {path + (key,)}")
            _validate_json(item, path + (key,))
        return
    raise ValueError(f"non-JSON value {type(value).__name__} at {path or ('<root>',)}")


class SecretRef(GraphModel):
    secret_ref: str = Field(min_length=1, max_length=128)

    @field_validator("secret_ref")
    @classmethod
    def _valid_name(cls, value: str) -> str:
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("secret_ref must be a stable identifier")
        return value


class GraphComponentRef(GraphModel):
    namespace: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=128)
    version: str | None = Field(default=None, max_length=128)
    params: dict[str, Any] = Field(default_factory=dict)
    dependencies: dict[str, Any] = Field(default_factory=dict)

    @field_validator("namespace", "name")
    @classmethod
    def _non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("component identifiers must not be blank")
        return value

    @field_validator("params", "dependencies")
    @classmethod
    def _json_and_secret_safe(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json(value)
        return value


class ComponentBinding(GraphModel):
    policy: BindingPolicy = BindingPolicy.SINGLE
    candidates: tuple[GraphComponentRef, ...]

    @model_validator(mode="after")
    def _binding_shape(self) -> "ComponentBinding":
        if not self.candidates:
            raise ValueError("component binding requires at least one candidate")
        if self.policy == BindingPolicy.SINGLE and len(self.candidates) != 1:
            raise ValueError("single binding requires exactly one candidate")
        if self.policy == BindingPolicy.FALLBACK and len(self.candidates) < 2:
            raise ValueError("fallback binding requires at least two candidates")
        return self


class PortAddress(GraphModel):
    node: str
    port: str

    @field_validator("node", "port")
    @classmethod
    def _stable_id(cls, value: str) -> str:
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("node and port references must be stable identifiers")
        return value


class Predicate(GraphModel):
    field: str = Field(min_length=1, max_length=256)
    operator: PredicateOperator
    value: Any = None

    @field_validator("field")
    @classmethod
    def _safe_field_path(cls, value: str) -> str:
        if not all(_LOGICAL_ID.fullmatch(part) for part in value.split(".")):
            raise ValueError("predicate field must be a dotted identifier path")
        if any(token in value.lower() for token in ("eval", "exec", "__", "(", ")")):
            raise ValueError("executable predicate expressions are not allowed")
        return value

    @field_validator("value")
    @classmethod
    def _json_value(cls, value: Any) -> Any:
        _validate_json(value)
        return value

    @model_validator(mode="after")
    def _operator_value(self) -> "Predicate":
        if self.operator in {PredicateOperator.TRUTHY, PredicateOperator.FALSY, PredicateOperator.EXISTS}:
            if self.value is not None:
                raise ValueError(f"{self.operator.value} predicate does not accept a value")
        return self


class FeedbackPolicy(GraphModel):
    predicate: Predicate
    max_iterations: StrictInt = Field(ge=1, le=10)
    on_exhausted: FeedbackExhaustedPolicy


class ExecutionPolicy(GraphModel):
    """Generic per-node execution constraints."""

    max_activations: StrictInt = Field(default=100, ge=1, le=10000)
    timeout_ms: StrictInt | None = Field(default=None, ge=1, le=3_600_000)


class RouterCase(GraphModel):
    """One ordered branch in an N-way structured router."""

    id: str
    predicate: Predicate

    @field_validator("id")
    @classmethod
    def _valid_case_id(cls, value: str) -> str:
        """Validate a stable router case identifier.

        Args:
            value (str): Candidate case identifier.

        Raises:
            ValueError: The identifier is not stable.

        Returns:
            str: Validated case identifier.
        """
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("router case id must be a stable logical identifier")
        return value


class RouterSpec(GraphModel):
    """Ordered first-match router definition."""

    cases: tuple[RouterCase, ...]
    default: str = Field(min_length=1, max_length=128)

    @model_validator(mode="after")
    def _validate_router(self) -> "RouterSpec":
        """Validate unique cases and a distinct default output.

        Args:
            None.

        Raises:
            ValueError: Cases are empty, duplicated, or collide with default.

        Returns:
            RouterSpec: Validated router.
        """
        ids = [case.id for case in self.cases]
        if not ids:
            raise ValueError("router requires at least one ordered case")
        if len(ids) != len(set(ids)):
            raise ValueError("router case identifiers must be unique")
        if self.default in set(ids):
            raise ValueError("router default must be distinct from case identifiers")
        if not _LOGICAL_ID.fullmatch(self.default):
            raise ValueError("router default must be a stable logical identifier")
        return self


class StateSpec(GraphModel):
    """Typed state declaration and explicit read/write operation."""

    key: str
    data_type: str = Field(min_length=1, max_length=160)
    scope: StateScope
    operation: StateOperation
    merge: StateMergePolicy = StateMergePolicy.REPLACE
    initial: Any = None

    @field_validator("key")
    @classmethod
    def _valid_state_key(cls, value: str) -> str:
        """Validate a stable state key.

        Args:
            value (str): Candidate state key.

        Raises:
            ValueError: The key is not a stable logical identifier.

        Returns:
            str: Validated state key.
        """
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("state key must be a stable logical identifier")
        return value

    @field_validator("initial")
    @classmethod
    def _json_initial(cls, value: Any) -> Any:
        """Validate JSON-safe initial state.

        Args:
            value (Any): Initial state value.

        Raises:
            ValueError: The value is not JSON-safe or embeds resolved secrets.

        Returns:
            Any: Validated initial value.
        """
        _validate_json(value)
        return value


class GraphInterfacePort(GraphModel):
    """Typed public boundary port for hierarchical composition."""

    id: str
    data_type: str = Field(min_length=1, max_length=160)
    required: bool = True

    @field_validator("id")
    @classmethod
    def _valid_interface_id(cls, value: str) -> str:
        """Validate a stable graph interface port identifier.

        Args:
            value (str): Candidate interface port identifier.

        Raises:
            ValueError: The identifier is not stable.

        Returns:
            str: Validated identifier.
        """
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("interface port id must be a stable logical identifier")
        return value


class GraphInterface(GraphModel):
    """Typed inputs and outputs exposed by one AgentGraph."""

    inputs: tuple[GraphInterfacePort, ...] = ()
    outputs: tuple[GraphInterfacePort, ...] = ()

    @model_validator(mode="after")
    def _unique_ports(self) -> "GraphInterface":
        """Validate unique interface ports per direction.

        Args:
            None.

        Raises:
            ValueError: Duplicate input or output identifiers are declared.

        Returns:
            GraphInterface: Validated interface.
        """
        for ports in (self.inputs, self.outputs):
            ids = [port.id for port in ports]
            if len(ids) != len(set(ids)):
                raise ValueError("graph interface port identifiers must be unique")
        return self


class SubgraphReference(GraphModel):
    """Immutable content-addressed graph catalog reference."""

    id: str
    version: str
    semantic_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _fixed_reference(self) -> "SubgraphReference":
        """Reject mutable graph aliases.

        Args:
            None.

        Raises:
            ValueError: The version is blank or uses a mutable ``latest`` alias.

        Returns:
            SubgraphReference: Validated content-addressed reference.
        """
        if not self.id.strip() or not self.version.strip() or self.version.lower() == "latest":
            raise ValueError("subgraph reference requires fixed id and version")
        return self


class SubgraphSpec(GraphModel):
    """Inline or catalog-resolved hierarchical graph invocation."""

    graph: Any | None = Field(default=None, exclude_if=lambda value: value is None)
    reference: SubgraphReference | None = Field(default=None, exclude_if=lambda value: value is None)
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    shared_state: tuple[str, ...] = ()
    max_activations: StrictInt = Field(default=100, ge=1, le=10000)
    error_policy: SubgraphErrorPolicy = SubgraphErrorPolicy.PROPAGATE

    @field_validator("inputs", "outputs")
    @classmethod
    def _stable_mappings(cls, value: dict[str, str]) -> dict[str, str]:
        """Validate parent/child port mappings as stable identifiers.

        Args:
            value (dict[str, str]): Parent-port to child-port mapping.

        Raises:
            ValueError: A key/value is not a stable logical identifier.

        Returns:
            dict[str, str]: Validated mapping.
        """
        if any(
            not _LOGICAL_ID.fullmatch(parent) or not _LOGICAL_ID.fullmatch(child)
            for parent, child in value.items()
        ):
            raise ValueError("subgraph port mappings require stable identifiers")
        return value

    @field_validator("shared_state")
    @classmethod
    def _stable_shared_state(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate explicitly shared run-state keys.

        Args:
            value (tuple[str, ...]): Shared state keys.

        Raises:
            ValueError: Keys are unstable or duplicated.

        Returns:
            tuple[str, ...]: Validated sharing declaration.
        """
        if len(value) != len(set(value)) or any(
            not _LOGICAL_ID.fullmatch(item) for item in value
        ):
            raise ValueError("shared state keys must be unique stable identifiers")
        return value

    @model_validator(mode="after")
    def _validate_source(self) -> "SubgraphSpec":
        """Require exactly one inline graph or immutable catalog reference.

        Args:
            None.

        Raises:
            ValueError: Both or neither source forms are supplied.

        Returns:
            SubgraphSpec: Validated subgraph invocation.
        """
        if (self.graph is None) == (self.reference is None):
            raise ValueError("subgraph requires exactly one inline graph or reference")
        if isinstance(self.graph, Mapping):
            object.__setattr__(self, "graph", AgentGraph.model_validate(self.graph))
        if self.graph is not None and not isinstance(self.graph, AgentGraph):
            raise ValueError("inline subgraph must be an AgentGraph")
        return self


class LoopSpec(GraphModel):
    """Bounded local loop around an inline or referenced body subgraph."""

    body: SubgraphSpec
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    until: Predicate
    max_iterations: StrictInt = Field(ge=1, le=1000)
    on_exhausted: LoopExhaustedPolicy = LoopExhaustedPolicy.FAIL
    max_activations: StrictInt = Field(default=1000, ge=1, le=100000)


class GraphEdge(GraphModel):
    source: PortAddress
    target: PortAddress
    kind: EdgeKind
    condition: Predicate | None = None
    feedback: FeedbackPolicy | None = None

    @model_validator(mode="after")
    def _edge_policy(self) -> "GraphEdge":
        if self.kind == EdgeKind.FEEDBACK and self.feedback is None:
            raise ValueError("feedback edge requires feedback policy")
        if self.kind != EdgeKind.FEEDBACK and self.feedback is not None:
            raise ValueError("only feedback edges may define feedback policy")
        return self


class GraphNode(GraphModel):
    id: str
    kind: NodeKind
    role: GraphRole | None = None
    contract: NodeContractRef | None = Field(default=None, exclude_if=lambda value: value is None)
    lifecycle: NodeLifecycle
    component: ComponentBinding | None = None
    primary: StrictBool = False
    predicate: Predicate | None = None
    execution: ExecutionPolicy | None = Field(default=None, exclude_if=lambda value: value is None)
    router: RouterSpec | None = Field(default=None, exclude_if=lambda value: value is None)
    state: StateSpec | None = Field(default=None, exclude_if=lambda value: value is None)
    loop: LoopSpec | None = Field(default=None, exclude_if=lambda value: value is None)
    subgraph: SubgraphSpec | None = Field(default=None, exclude_if=lambda value: value is None)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("node id must be a stable logical identifier")
        return value

    @field_validator("metadata")
    @classmethod
    def _json_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json(value)
        return value

    @model_validator(mode="after")
    def _kind_contract(self) -> "GraphNode":
        """Validate the declaration required by each node kind.

        Args:
            None.

        Raises:
            ValueError: The node mixes incompatible declarations or omits one.

        Returns:
            GraphNode: Validated node.
        """
        structures = {
            NodeKind.ROUTER: self.router,
            NodeKind.STATE: self.state,
            NodeKind.LOOP: self.loop,
            NodeKind.SUBGRAPH: self.subgraph,
        }
        if self.kind == NodeKind.COMPONENT:
            if (self.role is None and self.contract is None) or self.component is None:
                raise ValueError("component node requires role or contract and component binding")
            if self.predicate is not None:
                raise ValueError("component node cannot define condition predicate")
            if any(item is not None for item in structures.values()):
                raise ValueError("component node cannot define built-in node structures")
        else:
            if self.role is not None or self.component is not None or self.contract is not None:
                raise ValueError("built-in node cannot define component role or binding")
            if self.kind == NodeKind.CONDITION and self.predicate is None:
                raise ValueError("condition node requires predicate")
            if self.kind != NodeKind.CONDITION and self.predicate is not None:
                raise ValueError("only condition node may define predicate")
            expected = structures.get(self.kind)
            if self.kind in structures and expected is None:
                raise ValueError(f"{self.kind.value} node requires its structure")
            for kind, declaration in structures.items():
                if kind is not self.kind and declaration is not None:
                    raise ValueError(f"only {kind.value} node may define {kind.value} structure")
        if self.kind == NodeKind.OUTPUT and self.lifecycle != NodeLifecycle.TERMINAL:
            raise ValueError("output node lifecycle must be terminal")
        return self


class GraphPolicies(GraphModel):
    max_steps: StrictInt = Field(default=15, ge=1, le=1000)
    max_feedback_iterations: StrictInt = Field(default=10, ge=1, le=10)
    max_activations: StrictInt = Field(
        default=1000,
        ge=1,
        le=100000,
        exclude_if=lambda value: value == 1000,
    )
    max_nesting_depth: StrictInt = Field(
        default=8,
        ge=1,
        le=32,
        exclude_if=lambda value: value == 8,
    )


class NodePresentation(GraphModel):
    x: float = 0.0
    y: float = 0.0
    label: str = ""
    icon: str = ""
    description: str = ""

    @field_validator("x", "y")
    @classmethod
    def _finite(cls, value: float) -> float:
        if not math.isfinite(value):
            raise ValueError("presentation coordinates must be finite")
        return value


class GraphPresentation(GraphModel):
    flow_id: str | None = None
    flow_name: str | None = None
    created_at: int | None = None
    updated_at: int | None = None
    nodes: dict[str, NodePresentation] = Field(default_factory=dict)


class AgentGraph(GraphModel):
    schema_version: Literal[1] = 1
    contract_version: str = "1.0"
    profile: Literal["mobile_agent"] = "mobile_agent"
    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]
    policies: GraphPolicies = Field(default_factory=GraphPolicies)
    interface: GraphInterface | None = Field(default=None, exclude_if=lambda value: value is None)
    metadata: dict[str, Any] = Field(default_factory=dict)
    presentation: GraphPresentation | None = None

    @field_validator("contract_version")
    @classmethod
    def _contract_version(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("contract_version must not be blank")
        return value

    @field_validator("metadata")
    @classmethod
    def _json_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        _validate_json(value)
        return value

    def validate_graph(self, *, contract_catalog=None, graph_catalog=None):
        """Validate this graph against explicit catalogs.

        Args:
            contract_catalog (Any): Optional explicit NodeContractCatalog.
            graph_catalog (Any): Optional explicit GraphCatalog.

        Raises:
            None.

        Returns:
            GraphValidationResult: Deterministic validation diagnostics.
        """
        from .validation import validate_graph

        return validate_graph(
            self,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        )

    def canonical_mapping(self, *, contract_catalog=None, graph_catalog=None) -> dict[str, Any]:
        """Return this graph's stable semantic projection.

        Args:
            contract_catalog (Any): Optional explicit NodeContractCatalog.
            graph_catalog (Any): Optional explicit GraphCatalog.

        Raises:
            ValueError: Graph validation fails.

        Returns:
            dict[str, Any]: Canonical semantic mapping.
        """
        from .canonical import canonical_mapping

        return canonical_mapping(
            self,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        )

    def canonical_json(self, *, contract_catalog=None, graph_catalog=None) -> str:
        """Return compact canonical JSON for this graph.

        Args:
            contract_catalog (Any): Optional explicit NodeContractCatalog.
            graph_catalog (Any): Optional explicit GraphCatalog.

        Raises:
            ValueError: Graph validation fails.

        Returns:
            str: Stable canonical JSON.
        """
        from .canonical import canonical_json

        return canonical_json(
            self,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        )

    def canonical_hash(self, *, contract_catalog=None, graph_catalog=None) -> str:
        """Return this graph's SHA-256 semantic identity.

        Args:
            contract_catalog (Any): Optional explicit NodeContractCatalog.
            graph_catalog (Any): Optional explicit GraphCatalog.

        Raises:
            ValueError: Graph validation fails.

        Returns:
            str: ``sha256:``-prefixed identity.
        """
        from .canonical import canonical_hash

        return canonical_hash(
            self,
            contract_catalog=contract_catalog,
            graph_catalog=graph_catalog,
        )


def normalize_secret_placeholders(value: Any) -> Any:
    """Convert ``${name}`` values into stable SecretRef values recursively."""

    if isinstance(value, str):
        match = _PLACEHOLDER.fullmatch(value)
        return SecretRef(secret_ref=match.group(1)) if match else value
    if isinstance(value, list):
        return [normalize_secret_placeholders(item) for item in value]
    if isinstance(value, tuple):
        return tuple(normalize_secret_placeholders(item) for item in value)
    if isinstance(value, dict):
        return {key: normalize_secret_placeholders(item) for key, item in value.items()}
    return value
