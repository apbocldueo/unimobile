"""Strict, versioned authoring models for ZhiXing Studio documents."""

from __future__ import annotations

import math
import re
import hashlib
import json
from typing import Any, Literal, Mapping, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, field_validator, model_validator

from zhixing.graph import (
    CompilationResult,
    ComponentBinding,
    EdgeKind,
    ExecutionPolicy,
    FeedbackPolicy,
    GraphInterface,
    GraphPolicies,
    GraphRole,
    LoopExhaustedPolicy,
    NodeContractRef,
    NodeKind,
    NodeLifecycle,
    Predicate,
    RouterSpec,
    StateSpec,
    SubgraphErrorPolicy,
    SubgraphReference,
)


_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_LOGICAL_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")
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

STUDIO_CAPABILITY_AUTHORING_POLICY = "studio.capability-authoring@1"
STUDIO_CAPABILITY_LOWERING_PROFILE = "studio.mobile-agent-lowering@1"
STUDIO_GENERATED_ID_PREFIX = "studio_generated."

StudioCapabilityFamily = Literal[
    "perception",
    "planner",
    "reasoning",
    "memory",
    "action_executor",
    "verifier",
    "grounder",
    "tool",
]
StudioCapabilityRelationKind = Literal[
    "data",
    "activation",
    "feedback",
    "termination",
]
StudioProjectionOwnerKind = Literal[
    "capability",
    "relation",
    "input",
    "output",
    "graph_policy",
    "unmapped",
]


def _validate_safe_metadata(value: Any, path: tuple[Any, ...] = ()) -> None:
    """Reject non-JSON objects, raw secrets, and host absolute paths.

    Args:
        value (Any): Candidate authoring metadata value.
        path (tuple[Any, ...]): Current property location.

    Raises:
        ValueError: The value is unsafe for Studio persistence.

    Returns:
        None.
    """
    if value is None or isinstance(value, (bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float at {path or ('<root>',)}")
        return
    if isinstance(value, str):
        if value.startswith(("/", "\\\\")) or re.match(r"^[A-Za-z]:[\\/]", value):
            raise ValueError(f"host absolute path is not allowed at {path or ('<root>',)}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_safe_metadata(item, path + (index,))
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string mapping key at {path + (key,)}")
            normalized = key.strip().lower().replace("-", "_")
            is_secret = normalized in _SECRET_KEYS or normalized.endswith(
                ("_api_key", "_password", "_secret")
            )
            if is_secret:
                allowed = (
                    isinstance(item, Mapping)
                    and set(item.keys()) == {"secret_ref"}
                    and isinstance(item.get("secret_ref"), str)
                ) or (
                    isinstance(item, str)
                    and re.fullmatch(r"\$\{[A-Za-z_][A-Za-z0-9_.-]*\}", item)
                    is not None
                )
                if not allowed:
                    raise ValueError(
                        f"resolved secret value is not allowed at {path + (key,)}"
                    )
            _validate_safe_metadata(item, path + (key,))
        return
    raise ValueError(
        f"non-JSON value {type(value).__name__} at {path or ('<root>',)}"
    )


def _to_camel(value: str) -> str:
    """Convert a snake-case field name to the Studio JSON camel-case form.

    Args:
        value (str): Python field name.

    Raises:
        None.

    Returns:
        str: Camel-case JSON key.
    """
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


class StudioModel(BaseModel):
    """Immutable strict base for Studio HTTP and persistence DTOs."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
        alias_generator=_to_camel,
    )


class StudioPortAddress(StudioModel):
    """Reference one stable authoring node and one contract port."""

    canvas_id: str
    port_id: str

    @field_validator("canvas_id")
    @classmethod
    def _valid_canvas_id(cls, value: str) -> str:
        """Validate an authoring canvas identity.

        Args:
            value (str): Candidate canvas identity.

        Raises:
            ValueError: The identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("canvas_id must be a stable identifier")
        return value

    @field_validator("port_id")
    @classmethod
    def _valid_port_id(cls, value: str) -> str:
        """Validate an exact NodeContract port identifier.

        Args:
            value (str): Candidate port identity.

        Raises:
            ValueError: The identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("port_id must be a stable contract port identifier")
        return value


class StudioEdge(StudioModel):
    """One stable authoring edge between contract ports."""

    canvas_id: str
    source: StudioPortAddress
    target: StudioPortAddress
    kind: EdgeKind
    condition: Predicate | None = None
    feedback: FeedbackPolicy | None = None

    @field_validator("canvas_id")
    @classmethod
    def _valid_canvas_id(cls, value: str) -> str:
        """Validate a stable edge identity.

        Args:
            value (str): Candidate edge identity.

        Raises:
            ValueError: The identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("edge canvas_id must be a stable identifier")
        return value

    @model_validator(mode="after")
    def _feedback_shape(self) -> "StudioEdge":
        """Require bounded feedback metadata only on feedback edges.

        Args:
            None.

        Raises:
            ValueError: Feedback metadata and edge kind disagree.

        Returns:
            StudioEdge: Validated edge.
        """
        if self.kind is EdgeKind.FEEDBACK and self.feedback is None:
            raise ValueError("feedback edge requires feedback policy")
        if self.kind is not EdgeKind.FEEDBACK and self.feedback is not None:
            raise ValueError("only feedback edges may define feedback policy")
        return self


class StudioSubgraphSpec(StudioModel):
    """Inline Studio document or fixed graph-catalog reference."""

    document: StudioFlowDocument | None = None
    reference: SubgraphReference | None = None
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    shared_state: tuple[str, ...] = ()
    max_activations: StrictInt = Field(default=100, ge=1, le=10000)
    error_policy: SubgraphErrorPolicy = SubgraphErrorPolicy.PROPAGATE

    @field_validator("inputs", "outputs")
    @classmethod
    def _stable_mappings(cls, value: dict[str, str]) -> dict[str, str]:
        """Validate parent/child port mappings.

        Args:
            value (dict[str, str]): Parent-to-child stable port mapping.

        Raises:
            ValueError: A mapping key or value is unstable.

        Returns:
            dict[str, str]: Validated mapping.
        """
        if any(
            not _LOGICAL_ID.fullmatch(parent) or not _LOGICAL_ID.fullmatch(child)
            for parent, child in value.items()
        ):
            raise ValueError("subgraph mappings require stable identifiers")
        return value

    @field_validator("shared_state")
    @classmethod
    def _stable_shared_state(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate explicitly shared state keys.

        Args:
            value (tuple[str, ...]): Shared state keys.

        Raises:
            ValueError: Keys are duplicated or unstable.

        Returns:
            tuple[str, ...]: Validated keys.
        """
        if len(value) != len(set(value)) or any(
            not _LOGICAL_ID.fullmatch(item) for item in value
        ):
            raise ValueError("shared state keys must be unique stable identifiers")
        return value

    @model_validator(mode="after")
    def _exactly_one_source(self) -> "StudioSubgraphSpec":
        """Require exactly one inline document or immutable reference.

        Args:
            None.

        Raises:
            ValueError: Both or neither source forms are supplied.

        Returns:
            StudioSubgraphSpec: Validated source declaration.
        """
        if (self.document is None) == (self.reference is None):
            raise ValueError("subgraph requires exactly one document or reference")
        return self


class StudioLoopSpec(StudioModel):
    """Bounded authoring loop around a Studio subgraph body."""

    body: StudioSubgraphSpec
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: dict[str, str] = Field(default_factory=dict)
    until: Predicate
    max_iterations: StrictInt = Field(ge=1, le=1000)
    on_exhausted: LoopExhaustedPolicy = LoopExhaustedPolicy.FAIL
    max_activations: StrictInt = Field(default=1000, ge=1, le=100000)

    @field_validator("inputs", "outputs")
    @classmethod
    def _stable_mappings(cls, value: dict[str, str]) -> dict[str, str]:
        """Validate loop boundary mappings.

        Args:
            value (dict[str, str]): Parent-to-body port mapping.

        Raises:
            ValueError: A mapping key or value is unstable.

        Returns:
            dict[str, str]: Validated mapping.
        """
        if any(
            not _LOGICAL_ID.fullmatch(parent) or not _LOGICAL_ID.fullmatch(child)
            for parent, child in value.items()
        ):
            raise ValueError("loop mappings require stable identifiers")
        return value


class StudioNode(StudioModel):
    """One schema 2 authoring node with separate canvas and logical identity."""

    canvas_id: str
    logical_id: str
    kind: NodeKind
    lifecycle: NodeLifecycle
    role: GraphRole | None = None
    contract: NodeContractRef | None = None
    component: ComponentBinding | None = None
    primary: StrictBool = False
    predicate: Predicate | None = None
    execution: ExecutionPolicy | None = None
    router: RouterSpec | None = None
    state: StateSpec | None = None
    loop: StudioLoopSpec | None = None
    subgraph: StudioSubgraphSpec | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _safe_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Validate authoring metadata before it can reach persistence.

        Args:
            value (dict[str, Any]): Candidate metadata.

        Raises:
            ValueError: Metadata embeds a raw secret, live object, non-finite
                number, or host absolute path.

        Returns:
            dict[str, Any]: Validated JSON-safe metadata.
        """
        _validate_safe_metadata(value)
        return value

    @field_validator("canvas_id")
    @classmethod
    def _valid_canvas_id(cls, value: str) -> str:
        """Validate a stable canvas identity.

        Args:
            value (str): Candidate canvas identity.

        Raises:
            ValueError: The identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("canvas_id must be a stable identifier")
        return value

    @field_validator("logical_id")
    @classmethod
    def _valid_logical_id(cls, value: str) -> str:
        """Validate the future AgentGraph node identity.

        Args:
            value (str): Candidate logical identity.

        Raises:
            ValueError: The identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _LOGICAL_ID.fullmatch(value):
            raise ValueError("logical_id must be a stable AgentGraph identifier")
        return value

    @model_validator(mode="after")
    def _kind_shape(self) -> "StudioNode":
        """Reject declarations that do not match the selected node kind.

        Args:
            None.

        Raises:
            ValueError: Required structure is absent or incompatible structure
                is present.

        Returns:
            StudioNode: Validated node declaration.
        """
        structures = {
            NodeKind.ROUTER: self.router,
            NodeKind.STATE: self.state,
            NodeKind.LOOP: self.loop,
            NodeKind.SUBGRAPH: self.subgraph,
        }
        if self.kind is NodeKind.COMPONENT:
            if (self.role is None and self.contract is None) or self.component is None:
                raise ValueError("component node requires role or contract and component")
            if any(candidate.version is None for candidate in self.component.candidates):
                raise ValueError("Studio component candidates require exact versions")
            if self.predicate is not None or any(item is not None for item in structures.values()):
                raise ValueError("component node mixes incompatible node declarations")
        else:
            if self.role is not None or self.contract is not None or self.component is not None:
                raise ValueError("built-in node cannot define component binding")
            if self.kind is NodeKind.CONDITION and self.predicate is None:
                raise ValueError("condition node requires predicate")
            if self.kind is not NodeKind.CONDITION and self.predicate is not None:
                raise ValueError("only condition node may define predicate")
            for kind, declaration in structures.items():
                if kind is self.kind and declaration is None:
                    raise ValueError(f"{kind.value} node requires its structure")
                if kind is not self.kind and declaration is not None:
                    raise ValueError(f"only {kind.value} node may define {kind.value} structure")
        if self.kind is NodeKind.OUTPUT and self.lifecycle is not NodeLifecycle.TERMINAL:
            raise ValueError("output node lifecycle must be terminal")
        return self


class StudioSemanticGraph(StudioModel):
    """Semantic authoring draft that compiles to AgentGraph 1.1."""

    profile: Literal["mobile_agent"] = "mobile_agent"
    interface: GraphInterface | None = None
    policies: GraphPolicies = Field(default_factory=GraphPolicies)
    nodes: tuple[StudioNode, ...] = ()
    edges: tuple[StudioEdge, ...] = ()

    @model_validator(mode="after")
    def _unique_identities(self) -> "StudioSemanticGraph":
        """Require stable canvas, logical, and edge identities per graph scope.

        Args:
            None.

        Raises:
            ValueError: Duplicate identities are present.

        Returns:
            StudioSemanticGraph: Validated graph scope.
        """
        canvas_ids = [node.canvas_id for node in self.nodes]
        logical_ids = [node.logical_id for node in self.nodes]
        edge_ids = [edge.canvas_id for edge in self.edges]
        if len(canvas_ids) != len(set(canvas_ids)):
            raise ValueError("canvas node identities must be unique per graph scope")
        if len(logical_ids) != len(set(logical_ids)):
            raise ValueError("logical node identities must be unique per graph scope")
        if len(edge_ids) != len(set(edge_ids)):
            raise ValueError("edge identities must be unique per graph scope")
        return self


class StudioNodePresentation(StudioModel):
    """Presentation-only state for one canvas node."""

    x: float = 0.0
    y: float = 0.0
    label: str = ""
    icon: str = ""
    description: str = ""
    collapsed: bool = False
    render_mode: Literal["card", "inline", "boundary"] | None = None

    @field_validator("x", "y")
    @classmethod
    def _finite_coordinate(cls, value: float) -> float:
        """Reject non-finite canvas coordinates.

        Args:
            value (float): Coordinate value.

        Raises:
            ValueError: Value is NaN or infinite.

        Returns:
            float: Finite coordinate.
        """
        if not math.isfinite(value):
            raise ValueError("presentation coordinates must be finite")
        return value


class StudioViewport(StudioModel):
    """Presentation-only XYFlow viewport."""

    x: float = 0.0
    y: float = 0.0
    zoom: float = Field(default=1.0, gt=0.0, le=8.0)

    @field_validator("x", "y", "zoom")
    @classmethod
    def _finite_value(cls, value: float) -> float:
        """Reject non-finite viewport values.

        Args:
            value (float): Candidate viewport value.

        Raises:
            ValueError: Value is NaN or infinite.

        Returns:
            float: Finite value.
        """
        if not math.isfinite(value):
            raise ValueError("viewport values must be finite")
        return value


class StudioPresentation(StudioModel):
    """Document presentation excluded from AgentGraph canonical identity."""

    nodes: dict[str, StudioNodePresentation] = Field(default_factory=dict)
    viewport: StudioViewport = Field(default_factory=StudioViewport)
    theme: Literal["light", "dark", "system"] | None = None

    @field_validator("nodes")
    @classmethod
    def _stable_node_keys(
        cls,
        value: dict[str, StudioNodePresentation],
    ) -> dict[str, StudioNodePresentation]:
        """Validate presentation keys as canvas identities.

        Args:
            value (dict[str, StudioNodePresentation]): Node presentation map.

        Raises:
            ValueError: A canvas key is unstable.

        Returns:
            dict[str, StudioNodePresentation]: Validated map.
        """
        if any(not _STABLE_ID.fullmatch(item) for item in value):
            raise ValueError("presentation node keys must be stable canvas identifiers")
        return value


class StudioAuthoringMetadata(StudioModel):
    """Human authoring metadata excluded from AgentGraph identity."""

    description: str = Field(default="", max_length=4000)
    created_at: StrictInt = Field(default=0, ge=0)
    updated_at: StrictInt = Field(default=0, ge=0)


class StudioCapabilityBoundary(StudioModel):
    """One system-provisioned top-level capability-document boundary."""

    canvas_id: str
    logical_id: str
    kind: Literal["input", "output"]

    @field_validator("canvas_id", "logical_id")
    @classmethod
    def _stable_boundary_identity(cls, value: str) -> str:
        """Validate a stable non-generated boundary identity.

        Args:
            value: Candidate boundary identity.

        Raises:
            ValueError: Identity is unstable or occupies the generated namespace.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value) or value.startswith(
            STUDIO_GENERATED_ID_PREFIX
        ):
            raise ValueError("boundary identity must be stable and user-owned")
        return value


class StudioCapabilityEndpoint(StudioModel):
    """Address one capability or boundary port in a schema-3 relation."""

    owner_id: str
    port_id: str

    @field_validator("owner_id", "port_id")
    @classmethod
    def _stable_endpoint_identity(cls, value: str) -> str:
        """Validate a relation endpoint identity.

        Args:
            value: Candidate owner or port identity.

        Raises:
            ValueError: Identity is unstable or generated.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value) or value.startswith(
            STUDIO_GENERATED_ID_PREFIX
        ):
            raise ValueError("endpoint identity must be stable and user-owned")
        return value


class StudioCapabilityNode(StudioModel):
    """One user-visible capability instance with exact implementation choices."""

    canvas_id: str
    logical_id: str
    family: StudioCapabilityFamily
    lifecycle: NodeLifecycle = NodeLifecycle.PER_STEP
    implementation: ComponentBinding
    primary: StrictBool = False
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canvas_id", "logical_id")
    @classmethod
    def _stable_capability_identity(cls, value: str) -> str:
        """Validate a user-owned capability identity.

        Args:
            value: Candidate canvas or logical identity.

        Raises:
            ValueError: Identity is unstable or occupies the generated namespace.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value) or value.startswith(
            STUDIO_GENERATED_ID_PREFIX
        ):
            raise ValueError("capability identity must be stable and user-owned")
        return value

    @field_validator("metadata")
    @classmethod
    def _safe_capability_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Reject unsafe capability metadata.

        Args:
            value: Candidate JSON metadata.

        Raises:
            ValueError: Metadata contains secrets, paths, live values, or non-finite data.

        Returns:
            Validated metadata.
        """
        _validate_safe_metadata(value)
        return value

    @model_validator(mode="after")
    def _exact_implementations(self) -> "StudioCapabilityNode":
        """Require every selected implementation to have an exact version.

        Raises:
            ValueError: A candidate version is not exact.

        Returns:
            Validated capability node.
        """
        if any(candidate.version is None for candidate in self.implementation.candidates):
            raise ValueError("capability implementations require exact versions")
        return self


class StudioCapabilityFeedbackPolicy(StudioModel):
    """Bounded schema-3 feedback policy with camel-case wire aliases."""

    predicate: Predicate
    max_iterations: StrictInt = Field(ge=1, le=10)
    on_exhausted: Literal["fail", "continue", "terminate"]


class StudioCapabilityRelation(StudioModel):
    """One typed user-authored relation between capabilities and boundaries."""

    canvas_id: str
    source: StudioCapabilityEndpoint
    target: StudioCapabilityEndpoint
    kind: StudioCapabilityRelationKind
    feedback: StudioCapabilityFeedbackPolicy | None = None

    @field_validator("canvas_id")
    @classmethod
    def _stable_relation_identity(cls, value: str) -> str:
        """Validate a user-owned relation identity.

        Args:
            value: Candidate relation identity.

        Raises:
            ValueError: Identity is unstable or generated.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value) or value.startswith(
            STUDIO_GENERATED_ID_PREFIX
        ):
            raise ValueError("relation identity must be stable and user-owned")
        return value

    @model_validator(mode="after")
    def _feedback_shape(self) -> "StudioCapabilityRelation":
        """Keep bounded feedback policy exclusive to feedback relations.

        Raises:
            ValueError: Relation kind and feedback policy disagree.

        Returns:
            Validated relation.
        """
        if self.kind == "feedback" and self.feedback is None:
            raise ValueError("feedback relation requires a bounded feedback policy")
        if self.kind != "feedback" and self.feedback is not None:
            raise ValueError("only feedback relations may define feedback policy")
        return self


class StudioCapabilityPolicies(StudioModel):
    """Bounded graph-level execution policies owned by capability authoring."""

    max_steps: StrictInt = Field(default=15, ge=1, le=10000)
    max_feedback_iterations: StrictInt = Field(default=10, ge=0, le=1000)


class StudioProjectionOwner(StudioModel):
    """Identify the schema-3 authoring fact that owns generated execution data."""

    kind: StudioProjectionOwnerKind
    owner_id: str | None = None

    @model_validator(mode="after")
    def _owner_shape(self) -> "StudioProjectionOwner":
        """Require an identity for mapped owners and forbid one for unmapped facts.

        Raises:
            ValueError: Owner kind and identity disagree.

        Returns:
            Validated projection owner.
        """
        if self.kind == "unmapped":
            if self.owner_id is not None:
                raise ValueError("unmapped projection owner cannot have an identity")
            return self
        if self.owner_id is None or not _STABLE_ID.fullmatch(self.owner_id):
            raise ValueError("mapped projection owner requires a stable identity")
        return self


class StudioProjectionEntry(StudioModel):
    """Map one exact generated graph object to a capability authoring owner."""

    graph_kind: Literal["node", "edge", "path"]
    graph_id: str
    owner: StudioProjectionOwner
    property_path: tuple[str | int, ...] = ()

    @field_validator("graph_id")
    @classmethod
    def _stable_graph_identity(cls, value: str) -> str:
        """Validate one exact generated graph identity.

        Args:
            value: Generated node, edge, or path identity.

        Raises:
            ValueError: Identity is blank or unstable.

        Returns:
            Validated graph identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("projection graph identity must be stable")
        return value


class StudioCapabilityCompilationResult(CompilationResult):
    """Schema-3 compile result with immutable policy and projection evidence."""

    authoring_policy: str
    lowering_profile: str
    capability_hash: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    projection_map: tuple[StudioProjectionEntry, ...] = ()


class StudioCapabilityDocument(StudioModel):
    """Strict schema-3 Studio document containing only capabilities and boundaries."""

    schema_version: Literal[3] = 3
    contract_version: Literal["1.1"] = "1.1"
    authoring_policy: Literal[STUDIO_CAPABILITY_AUTHORING_POLICY] = (
        STUDIO_CAPABILITY_AUTHORING_POLICY
    )
    lowering_profile: Literal[STUDIO_CAPABILITY_LOWERING_PROFILE] = (
        STUDIO_CAPABILITY_LOWERING_PROFILE
    )
    document_id: str
    agent_id: str
    name: str = Field(min_length=1, max_length=256)
    input: StudioCapabilityBoundary
    output: StudioCapabilityBoundary
    capabilities: tuple[StudioCapabilityNode, ...] = ()
    relations: tuple[StudioCapabilityRelation, ...] = ()
    policies: StudioCapabilityPolicies = Field(default_factory=StudioCapabilityPolicies)
    presentation: StudioPresentation = Field(default_factory=StudioPresentation)
    authoring: StudioAuthoringMetadata = Field(default_factory=StudioAuthoringMetadata)

    @field_validator("document_id", "agent_id")
    @classmethod
    def _stable_resource_identity(cls, value: str) -> str:
        """Validate a stable schema-3 resource identity.

        Args:
            value: Candidate document or Agent identity.

        Raises:
            ValueError: Identity is unstable.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("document and Agent identities must be stable")
        return value

    @field_validator("name")
    @classmethod
    def _non_blank_capability_name(cls, value: str) -> str:
        """Reject a whitespace-only capability document name.

        Args:
            value: Candidate name.

        Raises:
            ValueError: Name is blank.

        Returns:
            Validated name.
        """
        if not value.strip():
            raise ValueError("document name must not be blank")
        return value

    @model_validator(mode="after")
    def _document_shape(self) -> "StudioCapabilityDocument":
        """Validate boundaries, identities, relations, and presentation references.

        Raises:
            ValueError: The capability topology is ambiguous or malformed.

        Returns:
            Validated schema-3 document.
        """
        if self.input.kind != "input" or self.output.kind != "output":
            raise ValueError("schema-3 requires exact Input and Output boundaries")
        objects = (self.input, self.output, *self.capabilities)
        canvas_ids = [item.canvas_id for item in objects]
        logical_ids = [item.logical_id for item in objects]
        relation_ids = [item.canvas_id for item in self.relations]
        if len(canvas_ids) != len(set(canvas_ids)):
            raise ValueError("capability canvas identities must be unique")
        if len(logical_ids) != len(set(logical_ids)):
            raise ValueError("capability logical identities must be unique")
        if len(relation_ids) != len(set(relation_ids)):
            raise ValueError("capability relation identities must be unique")
        known = set(logical_ids)
        for relation in self.relations:
            if relation.source.owner_id not in known or relation.target.owner_id not in known:
                raise ValueError(
                    f"relation {relation.canvas_id} references an unknown owner"
                )
            if relation.target.owner_id == self.input.logical_id:
                raise ValueError("Input cannot be a relation target")
            if relation.source.owner_id == self.output.logical_id:
                raise ValueError("Output cannot be a relation source")
            touches_output = relation.target.owner_id == self.output.logical_id
            if touches_output != (relation.kind == "termination"):
                raise ValueError(
                    "Output accepts only termination relations and every termination targets Output"
                )
        unknown_presentation = set(self.presentation.nodes) - set(canvas_ids)
        if unknown_presentation:
            raise ValueError(
                "presentation references unknown capability canvas nodes: "
                f"{sorted(unknown_presentation)}"
            )
        return self

    def semantic_payload(self) -> dict[str, Any]:
        """Return the finite presentation-independent capability semantics.

        Raises:
            ValueError: Semantic metadata is unsafe or not finite JSON.

        Returns:
            Canonicalizable schema-3 semantic payload.
        """
        payload = {
            "schemaVersion": self.schema_version,
            "contractVersion": self.contract_version,
            "authoringPolicy": self.authoring_policy,
            "loweringProfile": self.lowering_profile,
            "input": self.input.model_dump(mode="json", by_alias=True),
            "output": self.output.model_dump(mode="json", by_alias=True),
            "capabilities": [
                item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for item in self.capabilities
            ],
            "relations": [
                item.model_dump(mode="json", by_alias=True, exclude_none=True)
                for item in self.relations
            ],
            "policies": self.policies.model_dump(mode="json", by_alias=True),
        }
        _validate_safe_metadata(payload)
        return payload

    def semantic_hash(self) -> str:
        """Return the canonical capability-semantic SHA-256 identity.

        Raises:
            TypeError: Semantic values cannot be JSON encoded.
            ValueError: Semantic values are unsafe or non-finite.

        Returns:
            SHA-256-prefixed canonical identity.
        """
        encoded = json.dumps(
            self.semantic_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        return f"sha256:{hashlib.sha256(encoded).hexdigest()}"

    def to_json_dict(self) -> dict[str, Any]:
        """Return the strict camel-case schema-3 JSON representation.

        Returns:
            JSON-compatible document mapping.
        """
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class StudioFlowDocument(StudioModel):
    """Versioned schema 2 Studio authoring document."""

    schema_version: Literal[2] = 2
    contract_version: Literal["1.1"] = "1.1"
    document_id: str
    agent_id: str
    name: str = Field(min_length=1, max_length=256)
    semantic: StudioSemanticGraph
    presentation: StudioPresentation = Field(default_factory=StudioPresentation)
    authoring: StudioAuthoringMetadata = Field(default_factory=StudioAuthoringMetadata)

    @field_validator("document_id", "agent_id")
    @classmethod
    def _stable_resource_id(cls, value: str) -> str:
        """Validate stable document and Agent identities.

        Args:
            value (str): Candidate resource identity.

        Raises:
            ValueError: The identity is blank or unstable.

        Returns:
            str: Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("document_id and agent_id must be stable identifiers")
        return value

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        """Reject whitespace-only Agent names.

        Args:
            value (str): Candidate name.

        Raises:
            ValueError: The name is blank.

        Returns:
            str: Validated name.
        """
        if not value.strip():
            raise ValueError("document name must not be blank")
        return value

    @model_validator(mode="after")
    def _presentation_references_nodes(self) -> "StudioFlowDocument":
        """Reject presentation records for unknown canvas nodes.

        Args:
            None.

        Raises:
            ValueError: Presentation references an unknown canvas identity.

        Returns:
            StudioFlowDocument: Validated document.
        """
        canvas_ids = {node.canvas_id for node in self.semantic.nodes}
        unknown = set(self.presentation.nodes) - canvas_ids
        if unknown:
            raise ValueError(f"presentation references unknown canvas nodes: {sorted(unknown)}")
        return self

    def to_json_dict(self) -> dict[str, Any]:
        """Return the canonical Studio JSON representation.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Camel-case JSON-compatible document.
        """
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


StudioSubgraphSpec.model_rebuild()
StudioLoopSpec.model_rebuild()
StudioNode.model_rebuild()
StudioFlowDocument.model_rebuild()

StudioAuthoringDocument: TypeAlias = StudioFlowDocument | StudioCapabilityDocument


def parse_studio_authoring_document(value: Any) -> StudioAuthoringDocument:
    """Parse one strict Studio schema-2 or schema-3 document envelope.

    Args:
        value: Untrusted document value.

    Raises:
        ValueError: Schema version is unsupported.
        pydantic.ValidationError: The selected version violates its contract.

    Returns:
        Strict immutable authoring document.
    """
    if isinstance(value, (StudioFlowDocument, StudioCapabilityDocument)):
        return value
    if not isinstance(value, Mapping):
        raise ValueError("Studio document must be an object")
    schema_version = value.get("schemaVersion", value.get("schema_version"))
    if schema_version == 3:
        return StudioCapabilityDocument.model_validate(value)
    if schema_version == 2:
        return StudioFlowDocument.model_validate(value)
    raise ValueError("Studio authoring supports only schema 2 and schema 3")


__all__ = [
    "STUDIO_CAPABILITY_AUTHORING_POLICY",
    "STUDIO_CAPABILITY_LOWERING_PROFILE",
    "STUDIO_GENERATED_ID_PREFIX",
    "StudioAuthoringMetadata",
    "StudioAuthoringDocument",
    "StudioCapabilityBoundary",
    "StudioCapabilityCompilationResult",
    "StudioCapabilityDocument",
    "StudioCapabilityEndpoint",
    "StudioCapabilityFamily",
    "StudioCapabilityFeedbackPolicy",
    "StudioCapabilityNode",
    "StudioCapabilityPolicies",
    "StudioCapabilityRelation",
    "StudioEdge",
    "StudioFlowDocument",
    "StudioLoopSpec",
    "StudioModel",
    "StudioNode",
    "StudioNodePresentation",
    "StudioPortAddress",
    "StudioPresentation",
    "StudioProjectionEntry",
    "StudioProjectionOwner",
    "StudioSemanticGraph",
    "StudioSubgraphSpec",
    "StudioViewport",
    "parse_studio_authoring_document",
]
