"""Immutable typed contracts for Benchmark packages, plans, and protocols."""

from __future__ import annotations

import random
import re
from enum import Enum
from typing import Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from zhixing.config.contracts import BenchmarkSuite, BenchmarkTask
from zhixing.config.contracts.common import ensure_json_compatible

from ..constants import (
    BENCHMARK_CANONICALIZATION_VERSION,
    BENCHMARK_SCHEMA_VERSION,
)
from ..identity import canonical_hash, canonical_primitive

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")
_SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_LOGICAL_URI = re.compile(r"^(asset|groundtruth)://([a-z][a-z0-9_.-]{0,127})$")


class BenchmarkModel(BaseModel):
    """Strict immutable base model for definition-layer values."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=False,
        validate_default=True,
    )


class PackageIdentity(BenchmarkModel):
    """Human-readable publisher/name semantic-version identity."""

    publisher: str
    name: str
    version: str

    @field_validator("publisher", "name")
    @classmethod
    def _valid_identifier(cls, value: str) -> str:
        """Validate one stable package identity segment.

        Args:
            value (str): Publisher or package name.

        Raises:
            ValueError: Value is not a lowercase stable identifier.

        Returns:
            str: Validated identity segment.
        """
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("must match [a-z][a-z0-9_.-]{0,127}")
        return value

    @field_validator("version")
    @classmethod
    def _valid_semver(cls, value: str) -> str:
        """Validate semantic version syntax.

        Args:
            value (str): Package semantic version.

        Raises:
            ValueError: Version is not SemVer-compatible.

        Returns:
            str: Validated semantic version.
        """
        if not _SEMVER.fullmatch(value):
            raise ValueError("must be a semantic version such as 1.0.0")
        return value

    @property
    def identifier(self) -> str:
        """Return the stable readable package identity.

        Returns:
            str: ``publisher/name@version``.
        """
        return f"{self.publisher}/{self.name}@{self.version}"


class TaskSplit(BenchmarkModel):
    """One named collection of BenchmarkTask files."""

    files: tuple[str, ...] = Field(min_length=1)


class ResourceKind(str, Enum):
    """Supported package resource categories."""

    ASSET = "asset"
    GROUND_TRUTH = "ground_truth"


class ResourceRef(BenchmarkModel):
    """Content-addressed Package-relative resource declaration."""

    id: str
    kind: ResourceKind
    path: str
    media_type: str
    sha256: str
    size: StrictInt = Field(ge=0)

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        """Validate a logical resource ID.

        Args:
            value (str): Logical resource identifier.

        Raises:
            ValueError: Identifier is invalid.

        Returns:
            str: Validated identifier.
        """
        if not _IDENTIFIER.fullmatch(value):
            raise ValueError("resource id must be a stable lowercase identifier")
        return value

    @field_validator("media_type")
    @classmethod
    def _valid_media_type(cls, value: str) -> str:
        """Reject blank media types.

        Args:
            value (str): MIME-style media type.

        Raises:
            ValueError: Value is blank.

        Returns:
            str: Validated media type.
        """
        if not value.strip():
            raise ValueError("media_type must not be blank")
        return value

    @field_validator("sha256")
    @classmethod
    def _valid_digest(cls, value: str) -> str:
        """Validate a prefixed SHA-256 digest.

        Args:
            value (str): Digest to validate.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            str: Validated digest.
        """
        if not _DIGEST.fullmatch(value):
            raise ValueError("sha256 must use sha256:<64 lowercase hex>")
        return value


class GroundTruthBinding(BenchmarkModel):
    """Inline or resource-backed ground truth for one task."""

    inline: Any = None
    ref: str | None = None

    @model_validator(mode="after")
    def _exactly_one_value(self) -> "GroundTruthBinding":
        """Require exactly one JSON value or groundtruth URI.

        Raises:
            ValueError: Both or neither representations are present.

        Returns:
            GroundTruthBinding: Validated binding.
        """
        has_inline = "inline" in self.model_fields_set
        has_ref = "ref" in self.model_fields_set
        if has_inline == has_ref:
            raise ValueError("exactly one of inline or ref is required")
        if has_inline:
            ensure_json_compatible(self.inline)
            canonical_primitive(self.inline)
        if self.ref is not None:
            match = _LOGICAL_URI.fullmatch(self.ref)
            if match is None or match.group(1) != "groundtruth":
                raise ValueError("ref must use groundtruth://<id>")
        return self


class AppRequirement(BenchmarkModel):
    """Logical application requirement independent of a concrete device."""

    id: str
    platform: Literal["android", "harmonyos"]
    package_id: str | None = None
    version: str | None = None
    requires_login: StrictBool = False

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        """Validate an App logical ID.

        Args:
            value (str): Logical application ID.

        Raises:
            ValueError: Identifier is invalid.

        Returns:
            str: Validated ID.
        """
        if not value.strip() or len(value) > 255:
            raise ValueError("app id must be non-blank and bounded")
        return value

    @field_validator("package_id", "version")
    @classmethod
    def _optional_non_blank(cls, value: str | None) -> str | None:
        """Reject blank optional App fields.

        Args:
            value (str | None): Optional field.

        Raises:
            ValueError: Field is blank.

        Returns:
            str | None: Validated value.
        """
        if value is not None and not value.strip():
            raise ValueError("value must not be blank")
        return value


class PluginRequirement(BenchmarkModel):
    """Logical plugin dependency without importing an implementation."""

    id: str
    version: str | None = None
    optional: StrictBool = False

    @field_validator("id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        """Validate a plugin logical ID.

        Args:
            value (str): Plugin identifier.

        Raises:
            ValueError: Identifier is invalid.

        Returns:
            str: Validated ID.
        """
        if not value.strip() or len(value) > 255:
            raise ValueError("plugin id must be non-blank and bounded")
        return value


class BenchmarkPackageManifest(BenchmarkModel):
    """Serializable manifest for one Benchmark Package."""

    schema_version: Literal["1.0"] = BENCHMARK_SCHEMA_VERSION
    identity: PackageIdentity
    title: str
    platforms: tuple[Literal["android", "harmonyos"], ...] = Field(min_length=1)
    splits: dict[str, TaskSplit] = Field(min_length=1)
    resources: tuple[ResourceRef, ...] = ()
    ground_truth: dict[str, GroundTruthBinding] = Field(default_factory=dict)
    apps: tuple[AppRequirement, ...] = ()
    plugins: tuple[PluginRequirement, ...] = ()
    default_protocol: str | None = None

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        """Reject a blank Package title.

        Args:
            value (str): Reader-facing title.

        Raises:
            ValueError: Title is blank.

        Returns:
            str: Validated title.
        """
        if not value.strip():
            raise ValueError("title must not be blank")
        return value

    @field_validator("splits")
    @classmethod
    def _valid_split_names(cls, value: dict[str, TaskSplit]) -> dict[str, TaskSplit]:
        """Validate split identifiers.

        Args:
            value (dict[str, TaskSplit]): Split definitions.

        Raises:
            ValueError: A split name is invalid.

        Returns:
            dict[str, TaskSplit]: Validated mapping.
        """
        invalid = [name for name in value if not _IDENTIFIER.fullmatch(name)]
        if invalid:
            raise ValueError(f"invalid split names: {sorted(invalid)}")
        return value

    @model_validator(mode="after")
    def _unique_requirement_ids(self) -> "BenchmarkPackageManifest":
        """Reject duplicate resource, App, and plugin identities.

        Raises:
            ValueError: One identity is duplicated.

        Returns:
            BenchmarkPackageManifest: Validated manifest.
        """
        for label, values in (
            ("resource", [item.id for item in self.resources]),
            ("app", [item.id for item in self.apps]),
            ("plugin", [item.id for item in self.plugins]),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"duplicate {label} ids")
        if self.default_protocol is not None and not self.default_protocol.strip():
            raise ValueError("default_protocol must not be blank")
        return self


class BenchmarkPackage(BenchmarkModel):
    """Source-neutral semantic content loaded from one Package."""

    manifest: BenchmarkPackageManifest
    suites: dict[str, BenchmarkSuite]

    @model_validator(mode="after")
    def _splits_match(self) -> "BenchmarkPackage":
        """Require loaded suites to match manifest split names.

        Raises:
            ValueError: Manifest and loaded suites disagree.

        Returns:
            BenchmarkPackage: Validated package.
        """
        if set(self.suites) != set(self.manifest.splits):
            raise ValueError("loaded suites must match manifest splits")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        """Project Package content independent of source path and task order.

        Returns:
            dict[str, Any]: Stable package semantics.
        """
        return {
            "schema_version": self.manifest.schema_version,
            "identity": self.manifest.identity.model_dump(mode="json"),
            "title": self.manifest.title,
            "platforms": sorted(set(self.manifest.platforms)),
            "splits": {
                name: sorted(
                    (task.canonical_dict() for task in suite.root),
                    key=lambda item: item["id"],
                )
                for name, suite in sorted(self.suites.items())
            },
            "resources": sorted(
                (
                    item.model_dump(mode="json", exclude_none=True)
                    for item in self.manifest.resources
                ),
                key=lambda item: item["id"],
            ),
            "ground_truth": self.manifest.ground_truth,
            "apps": sorted(
                (
                    item.model_dump(mode="json", exclude_none=True)
                    for item in self.manifest.apps
                ),
                key=lambda item: item["id"],
            ),
            "plugins": sorted(
                (
                    item.model_dump(mode="json", exclude_none=True)
                    for item in self.manifest.plugins
                ),
                key=lambda item: item["id"],
            ),
            "default_protocol": self.manifest.default_protocol,
        }

    @property
    def content_identity(self) -> str:
        """Return content identity independent of Package location.

        Returns:
            str: SHA-256 package identity.
        """
        return canonical_hash(self.canonical_payload())


class BenchmarkPlan(BenchmarkModel):
    """Pure compiled Benchmark semantic representation."""

    schema_version: Literal["1.0"] = BENCHMARK_SCHEMA_VERSION
    canonicalization_version: Literal["1.0"] = BENCHMARK_CANONICALIZATION_VERSION
    package_identity: str | None = None
    package_content_identity: str | None = None
    split: str = "default"
    tasks: tuple[BenchmarkTask, ...] = Field(min_length=1)
    resources: tuple[ResourceRef, ...] = ()
    ground_truth: dict[str, GroundTruthBinding] = Field(default_factory=dict)
    apps: tuple[AppRequirement, ...] = ()
    plugins: tuple[PluginRequirement, ...] = ()

    @model_validator(mode="after")
    def _unique_task_ids(self) -> "BenchmarkPlan":
        """Reject duplicate Plan task IDs.

        Raises:
            ValueError: Task IDs are duplicated.

        Returns:
            BenchmarkPlan: Validated plan.
        """
        ids = [task.id for task in self.tasks]
        if len(ids) != len(set(ids)):
            raise ValueError("BenchmarkPlan task ids must be unique")
        return self

    def canonical_payload(self) -> dict[str, Any]:
        """Project semantic Plan data while excluding source/runtime state.

        Returns:
            dict[str, Any]: Stable Plan payload.
        """
        return {
            "schema_version": self.schema_version,
            "package_identity": self.package_identity,
            "split": self.split,
            "tasks": sorted(
                (task.canonical_dict() for task in self.tasks),
                key=lambda item: item["id"],
            ),
            "resources": sorted(
                (
                    item.model_dump(mode="json", exclude_none=True)
                    for item in self.resources
                ),
                key=lambda item: item["id"],
            ),
            "ground_truth": self.ground_truth,
            "apps": sorted(
                (
                    item.model_dump(mode="json", exclude_none=True)
                    for item in self.apps
                ),
                key=lambda item: item["id"],
            ),
            "plugins": sorted(
                (
                    item.model_dump(mode="json", exclude_none=True)
                    for item in self.plugins
                ),
                key=lambda item: item["id"],
            ),
        }

    def canonical_hash(self) -> str:
        """Return the stable BenchmarkPlan semantic identity.

        Returns:
            str: SHA-256 Plan identity.
        """
        return canonical_hash(self.canonical_payload())


class TaskInstance(BenchmarkModel):
    """A pre-materialized dynamic or static task instance."""

    schema_version: Literal["1.0"] = BENCHMARK_SCHEMA_VERSION
    plan_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    task_id: str
    repeat: StrictInt = Field(ge=0)
    seed: StrictInt
    generated_params: dict[str, Any] = Field(default_factory=dict)
    instruction: str
    ground_truth: Any = None
    app: str | None = None
    environment_initializer: tuple[dict[str, Any], ...] = ()
    evaluator: dict[str, Any] = Field(default_factory=dict)
    cleanup_initializer: tuple[dict[str, Any], ...] = ()
    materialization_notes: tuple[str, ...] = ()

    @field_validator("task_id", "instruction")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Reject blank task identity or instruction.

        Args:
            value (str): Field value.

        Raises:
            ValueError: Value is blank.

        Returns:
            str: Validated value.
        """
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @model_validator(mode="after")
    def _safe_values(self) -> "TaskInstance":
        """Validate generated and ground-truth values as safe JSON.

        Raises:
            ValueError: Values are non-JSON or contain forbidden identity data.

        Returns:
            TaskInstance: Validated instance.
        """
        ensure_json_compatible(self.generated_params)
        ensure_json_compatible(self.ground_truth)
        ensure_json_compatible(list(self.environment_initializer))
        ensure_json_compatible(self.evaluator)
        ensure_json_compatible(list(self.cleanup_initializer))
        canonical_primitive(self.generated_params)
        canonical_primitive(self.ground_truth)
        canonical_primitive(list(self.environment_initializer))
        canonical_primitive(self.evaluator)
        canonical_primitive(list(self.cleanup_initializer))
        return self

    def canonical_payload(self) -> dict[str, Any]:
        """Project concrete task semantics independent of Agent and device.

        Returns:
            dict[str, Any]: Stable TaskInstance payload.
        """
        return self.model_dump(mode="json", exclude_none=True)

    def canonical_hash(self) -> str:
        """Return the stable TaskInstance identity.

        Returns:
            str: SHA-256 instance identity.
        """
        return canonical_hash(self.canonical_payload())


class TaskOrderStrategy(str, Enum):
    """Supported deterministic task ordering policies."""

    FIXED = "fixed"
    SEEDED = "seeded"


class TaskOrder(BenchmarkModel):
    """Task ordering policy."""

    strategy: TaskOrderStrategy = TaskOrderStrategy.FIXED


class TaskMaterialization(BenchmarkModel):
    """Dynamic task reuse policy across compared Agents."""

    reuse_across_agents: StrictBool = True
    strict_fairness: StrictBool = False


class DeviceConstraints(BenchmarkModel):
    """Logical device requirements without a concrete serial."""

    platform: Literal["android", "harmonyos"] = "android"
    locale: str = "en-US"
    orientation: Literal["portrait", "landscape", "any"] = "portrait"
    version_policy: Literal["exact", "compatible", "any"] = "compatible"
    os_version: str | None = None

    @field_validator("locale", "os_version")
    @classmethod
    def _optional_non_blank(cls, value: str | None) -> str | None:
        """Reject blank device constraint strings.

        Args:
            value (str | None): Constraint value.

        Raises:
            ValueError: Value is blank.

        Returns:
            str | None: Validated value.
        """
        if value is not None and not value.strip():
            raise ValueError("value must not be blank")
        return value


class ExecutionBudget(BenchmarkModel):
    """Agent-paradigm-independent experiment budgets."""

    max_interactions: StrictInt = Field(gt=0)
    max_activations: StrictInt = Field(gt=0)
    timeout_seconds: StrictInt = Field(gt=0)
    token_limit: StrictInt | None = Field(default=None, gt=0)
    require_observable_tokens: StrictBool = False


class IsolationPolicy(BenchmarkModel):
    """Reset and cleanup timing requirements."""

    reset: Literal["before_each_agent", "before_each_task", "once"] = (
        "before_each_agent"
    )
    cleanup: Literal["after_each_run", "after_each_task", "once"] = "after_each_run"
    require_verified_reset: StrictBool = True


class FailureOutcome(str, Enum):
    """Stage outcome used by the future Experiment Runtime."""

    INVALIDATE = "invalidate"
    FAIL = "fail"
    EVALUATE_IF_POSSIBLE = "evaluate_if_possible"
    PRESERVE = "preserve"


class FailureRule(BenchmarkModel):
    """One stage-specific failure handling rule."""

    outcome: FailureOutcome
    continue_suite: StrictBool = True
    preserve_evidence: StrictBool = True


class FailurePolicy(BenchmarkModel):
    """Failure semantics for independently observable lifecycle stages."""

    initializer: FailureRule = FailureRule(outcome=FailureOutcome.INVALIDATE)
    agent: FailureRule = FailureRule(outcome=FailureOutcome.EVALUATE_IF_POSSIBLE)
    evaluator: FailureRule = FailureRule(outcome=FailureOutcome.INVALIDATE)
    cleanup: FailureRule = FailureRule(outcome=FailureOutcome.INVALIDATE)


class ExperimentProtocol(BenchmarkModel):
    """Fairness and isolation controls independent of BenchmarkPlan."""

    schema_version: Literal["1.0"] = BENCHMARK_SCHEMA_VERSION
    seed: StrictInt = 0
    repeats: StrictInt = Field(default=1, gt=0)
    task_order: TaskOrder = TaskOrder()
    task_materialization: TaskMaterialization = TaskMaterialization()
    device: DeviceConstraints = DeviceConstraints()
    apps: tuple[AppRequirement, ...] = ()
    budget: ExecutionBudget = ExecutionBudget(
        max_interactions=15,
        max_activations=200,
        timeout_seconds=600,
    )
    isolation: IsolationPolicy = IsolationPolicy()
    failure: FailurePolicy = FailurePolicy()

    @property
    def fairness_warnings(self) -> tuple[str, ...]:
        """Return explicit deviations from the default paired comparison.

        Returns:
            tuple[str, ...]: Stable warning codes.
        """
        if not self.task_materialization.reuse_across_agents:
            return ("benchmark.protocol.unpaired_materialization",)
        return ()

    def canonical_payload(self) -> dict[str, Any]:
        """Project fairness semantics without runtime bindings.

        Returns:
            dict[str, Any]: Stable Protocol payload.
        """
        return self.model_dump(mode="json", exclude_none=True)

    def canonical_hash(self) -> str:
        """Return the independent ExperimentProtocol identity.

        Returns:
            str: SHA-256 Protocol identity.
        """
        return canonical_hash(self.canonical_payload())

    def ordered_task_ids(
        self,
        task_ids: tuple[str, ...] | list[str],
        *,
        plan_identity: str,
        repeat: int,
    ) -> tuple[str, ...]:
        """Derive a deterministic task order without executing any task.

        Args:
            task_ids (tuple[str, ...] | list[str]): Task identities.
            plan_identity (str): BenchmarkPlan canonical identity.
            repeat (int): Zero-based repeat index.

        Raises:
            ValueError: Repeat is negative.

        Returns:
            tuple[str, ...]: Stable task ordering.
        """
        if repeat < 0:
            raise ValueError("repeat must be non-negative")
        ordered = sorted(task_ids)
        if self.task_order.strategy is TaskOrderStrategy.FIXED:
            return tuple(ordered)
        seed_material = canonical_hash(
            {
                "plan_identity": plan_identity,
                "protocol_identity": self.canonical_hash(),
                "repeat": repeat,
                "seed": self.seed,
            }
        )
        seed_value = int(seed_material.removeprefix("sha256:")[:16], 16)
        random.Random(seed_value).shuffle(ordered)
        return tuple(ordered)


class BenchmarkSuiteMap(RootModel[dict[str, BenchmarkSuite]]):
    """Internal typed mapping used for Package suite validation."""
