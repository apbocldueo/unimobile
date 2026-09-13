"""Bounded fake-fixture Benchmark Package Contract Test Kit."""

from __future__ import annotations

import json
import math
import random
import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Callable, Mapping

from ..compatibility import normalize_evaluation_result
from ..identity import canonical_hash
from ..models import BenchmarkPlan
from ..reporting.safety import sanitize_export

Fixture = Callable[[Mapping[str, Any], random.Random], Any]
FixtureFactory = Callable[[], Fixture]

BENCHMARK_CONTRACT_MAX_CASES = 1_000
BENCHMARK_CONTRACT_MAX_DIAGNOSTICS = 100
BENCHMARK_CONTRACT_MAX_PROFILES = 32
BENCHMARK_CONTRACT_MAX_OUTPUT_BYTES = 65_536

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_FORBIDDEN_CAPABILITIES = frozenset(
    {
        "agent-execution",
        "device",
        "experiment",
        "model",
        "network",
        "output-path",
        "output-publication",
        "real-runtime",
        "runtime-resolver",
        "secret",
    }
)


class BenchmarkFixtureKind(str, Enum):
    """Supported Benchmark fake-fixture contract kinds."""

    INITIALIZER = "initializer"
    ENVIRONMENT = "environment"
    EVALUATOR = "evaluator"


class BenchmarkContractStatus(str, Enum):
    """Stable outcome for one Benchmark fixture occurrence."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class BenchmarkContractTestCapacityError(ValueError):
    """Raised before fixture invocation when public case capacity is exceeded."""


class _FixtureContractFailure(ValueError):
    """Internal typed fixture failure with a stable public diagnostic code."""

    def __init__(self, code: str) -> None:
        """Store one stable failure code without unsafe fixture text.

        Args:
            code: Stable public diagnostic code.

        Raises:
            None.

        Returns:
            None.
        """
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class BenchmarkFixtureDescriptor:
    """One server- or test-owned fake implementation descriptor."""

    kind: BenchmarkFixtureKind
    logical_name: str
    fixture_id: str
    version: str
    factory: FixtureFactory = field(repr=False, compare=False)
    deterministic: bool = True
    isolated: bool = True
    capabilities: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        """Validate stable metadata without invoking the fixture factory.

        Raises:
            ValueError: Descriptor metadata is malformed.

        Returns:
            None.
        """
        for label, value in (
            ("logical_name", self.logical_name),
            ("fixture_id", self.fixture_id),
        ):
            if _STABLE_ID.fullmatch(value) is None:
                raise ValueError(f"{label} must be stable and bounded")
        if _SEMVER.fullmatch(self.version) is None:
            raise ValueError("fixture version must be a simple semantic version")
        if not callable(self.factory):
            raise ValueError("fixture factory must be callable")
        normalized = tuple(sorted(set(self.capabilities)))
        if normalized != self.capabilities:
            raise ValueError("fixture capabilities must be unique and sorted")

    @property
    def key(self) -> tuple[BenchmarkFixtureKind, str]:
        """Return the exact profile lookup key.

        Returns:
            Exact fixture kind and logical reference identity.
        """
        return self.kind, self.logical_name


@dataclass(frozen=True)
class BenchmarkFixtureProfileMetadata:
    """Bounded non-executable fixture-profile metadata."""

    profile_id: str
    version: str
    title: str
    description: str
    evidence_level: str
    supported_kinds: tuple[BenchmarkFixtureKind, ...]
    capabilities: tuple[str, ...]

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize metadata without factories or implementation locations.

        Returns:
            JSON-compatible bounded profile metadata.
        """
        return {
            "profile_id": self.profile_id,
            "version": self.version,
            "title": self.title[:120],
            "description": self.description[:500],
            "evidence_level": self.evidence_level,
            "supported_kinds": [item.value for item in self.supported_kinds],
            "capabilities": list(self.capabilities),
        }


@dataclass(frozen=True)
class BenchmarkFixtureProfile:
    """Immutable trusted fixture profile hidden behind server composition."""

    profile_id: str
    version: str
    title: str
    description: str
    evidence_level: str
    fixtures: tuple[BenchmarkFixtureDescriptor, ...]
    capabilities: tuple[str, ...] = ()
    enabled: bool = True

    def __post_init__(self) -> None:
        """Validate profile identities, bounds, and exact fixture uniqueness.

        Raises:
            ValueError: Profile metadata or fixture inventory is invalid.

        Returns:
            None.
        """
        if _STABLE_ID.fullmatch(self.profile_id) is None:
            raise ValueError("fixture profile identity must be stable and bounded")
        if _SEMVER.fullmatch(self.version) is None:
            raise ValueError("fixture profile version must be semantic")
        if not self.title.strip() or len(self.title) > 120:
            raise ValueError("fixture profile title must be non-blank and bounded")
        if len(self.description) > 500:
            raise ValueError("fixture profile description is too long")
        if _STABLE_ID.fullmatch(self.evidence_level) is None:
            raise ValueError("fixture evidence level must be stable")
        if tuple(sorted(set(self.capabilities))) != self.capabilities:
            raise ValueError("profile capabilities must be unique and sorted")
        keys = [item.key for item in self.fixtures]
        if len(keys) != len(set(keys)):
            raise ValueError("fixture profile contains duplicate logical contracts")
        if len(self.fixtures) > BENCHMARK_CONTRACT_MAX_CASES:
            raise ValueError("fixture profile inventory exceeds the safe limit")

    @property
    def metadata(self) -> BenchmarkFixtureProfileMetadata:
        """Project non-executable bounded profile metadata.

        Returns:
            Safe fixture-profile metadata.
        """
        kinds = tuple(sorted({item.kind for item in self.fixtures}, key=lambda item: item.value))
        return BenchmarkFixtureProfileMetadata(
            profile_id=self.profile_id,
            version=self.version,
            title=self.title,
            description=self.description,
            evidence_level=self.evidence_level,
            supported_kinds=kinds,
            capabilities=self.capabilities,
        )

    @property
    def fixture_map(self) -> dict[tuple[BenchmarkFixtureKind, str], BenchmarkFixtureDescriptor]:
        """Return the exact immutable-inventory lookup projection.

        Returns:
            Mapping keyed by fixture kind and logical reference.
        """
        return {item.key: item for item in self.fixtures}


class BenchmarkFixtureProfileRegistry:
    """Bounded injected registry for trusted fake-fixture profiles."""

    def __init__(self, profiles: tuple[BenchmarkFixtureProfile, ...]) -> None:
        """Validate and retain safe enabled fixture profiles.

        Args:
            profiles: Immutable server-owned fixture profiles.

        Raises:
            ValueError: Inventory is duplicated, oversized, or requests a
                forbidden default capability.

        Returns:
            None.
        """
        if len(profiles) > BENCHMARK_CONTRACT_MAX_PROFILES:
            raise ValueError("fixture profile count exceeds the safe limit")
        identities = [item.profile_id for item in profiles]
        if len(identities) != len(set(identities)):
            raise ValueError("fixture profile identity must resolve one version")
        for profile in profiles:
            requested = set(profile.capabilities)
            for descriptor in profile.fixtures:
                requested.update(descriptor.capabilities)
            if requested & _FORBIDDEN_CAPABILITIES:
                raise ValueError("fixture profile requests a forbidden capability")
        self._profiles = tuple(
            sorted(profiles, key=lambda item: (item.profile_id, item.version))
        )

    def list_metadata(self) -> tuple[BenchmarkFixtureProfileMetadata, ...]:
        """Return enabled profiles as bounded non-executable metadata.

        Returns:
            Stable profile metadata sequence.
        """
        return tuple(item.metadata for item in self._profiles if item.enabled)

    def get(self, profile_id: str) -> BenchmarkFixtureProfile:
        """Resolve one enabled exact profile without guessing a replacement.

        Args:
            profile_id: Stable requested profile identity.

        Raises:
            LookupError: The profile is absent or disabled.

        Returns:
            Exact enabled fixture profile.
        """
        for profile in self._profiles:
            if profile.profile_id == profile_id and profile.enabled:
                return profile
        raise LookupError("fixture profile is unavailable")


@dataclass(frozen=True)
class BenchmarkFixtureSet:
    """Legacy explicit fake implementations used by the public CLI API."""

    task_initializers: Mapping[str, Fixture] = field(default_factory=dict)
    evaluators: Mapping[str, Fixture] = field(default_factory=dict)
    environments: Mapping[str, Fixture] = field(default_factory=dict)
    profile_id: str = "declaration-v1"
    profile_version: str = "1.0.0"
    evidence_level: str = "declaration-only"

    def to_profile(self) -> BenchmarkFixtureProfile:
        """Adapt legacy callable mappings into a truthfully labelled profile.

        Returns:
            Immutable declaration-compatible fixture profile.
        """
        descriptors: list[BenchmarkFixtureDescriptor] = []
        for kind, mapping in (
            (BenchmarkFixtureKind.INITIALIZER, self.task_initializers),
            (BenchmarkFixtureKind.EVALUATOR, self.evaluators),
            (BenchmarkFixtureKind.ENVIRONMENT, self.environments),
        ):
            for logical_name, fixture in sorted(mapping.items()):
                descriptors.append(
                    BenchmarkFixtureDescriptor(
                        kind=kind,
                        logical_name=logical_name,
                        fixture_id=f"legacy-{kind.value}-{logical_name}",
                        version="1.0.0",
                        factory=lambda fixture=fixture: fixture,
                        deterministic=True,
                        isolated=False,
                    )
                )
        return BenchmarkFixtureProfile(
            profile_id=self.profile_id,
            version=self.profile_version,
            title="Declaration compatibility fixtures",
            description=(
                "Explicit declaration-only fake fixtures; no runtime plugin "
                "implementation is executed."
            ),
            evidence_level=self.evidence_level,
            fixtures=tuple(descriptors),
        )


@dataclass(frozen=True)
class BenchmarkContractDiagnostic:
    """One bounded package Contract Test diagnostic."""

    code: str
    path: tuple[str | int, ...]
    message: str

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize one diagnostic without unsafe fixture values.

        Returns:
            Safe bounded diagnostic.
        """
        return {
            "code": self.code[:160],
            "path": [str(item)[:160] for item in self.path[:32]],
            "message": self.message[:300],
        }


@dataclass(frozen=True)
class BenchmarkContractCaseResult:
    """Stable outcome from one logical Benchmark contract occurrence."""

    case_id: str
    task_id: str
    kind: BenchmarkFixtureKind
    logical_name: str
    path: tuple[str | int, ...]
    phase: str | None
    seed: int
    status: BenchmarkContractStatus
    fixture_id: str | None = None
    fixture_version: str | None = None
    checks: tuple[str, ...] = ()
    skipped: tuple[str, ...] = ()
    diagnostics: tuple[BenchmarkContractDiagnostic, ...] = ()

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize a bounded case without fixture parameters or outputs.

        Returns:
            Safe case result.
        """
        return {
            "case_id": self.case_id,
            "task_id": self.task_id[:160],
            "kind": self.kind.value,
            "logical_name": self.logical_name[:160],
            "path": [str(item)[:160] for item in self.path[:32]],
            "phase": self.phase,
            "seed": self.seed,
            "status": self.status.value,
            "fixture_id": self.fixture_id,
            "fixture_version": self.fixture_version,
            "checks": list(self.checks[:32]),
            "skipped": list(self.skipped[:32]),
            "diagnostics": [
                item.to_safe_dict() for item in self.diagnostics
            ],
        }


@dataclass(frozen=True)
class BenchmarkContractCoverage:
    """Independent execution-success and fixture-coverage facts."""

    total: int
    passed: int
    failed: int
    skipped: int
    complete: bool
    executed_checks_passed: bool

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize deterministic aggregate counts.

        Returns:
            Safe aggregate coverage mapping.
        """
        return {
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "complete": self.complete,
            "executed_checks_passed": self.executed_checks_passed,
        }


@dataclass(frozen=True)
class BenchmarkContractSafetyFacts:
    """Truthful fixed evidence boundary for default fake-fixture runs."""

    fixture_execution: bool = True
    package_code_executed: bool = False
    real_device_evidence: bool = False
    process_sandbox: bool = False
    device_capability: bool = False
    model_capability: bool = False
    network_capability: bool = False
    secret_capability: bool = False
    runtime_capability: bool = False
    experiment_capability: bool = False
    output_path_capability: bool = False
    benchmark_execution: bool = False
    agent_execution: bool = False
    publication_eligibility: bool = False
    result_persisted: bool = False

    def to_safe_dict(self) -> dict[str, bool]:
        """Serialize fixed fake-fixture safety facts.

        Returns:
            Safe boolean evidence-boundary mapping.
        """
        return {
            "fixture_execution": self.fixture_execution,
            "package_code_executed": self.package_code_executed,
            "real_device_evidence": self.real_device_evidence,
            "process_sandbox": self.process_sandbox,
            "device_capability": self.device_capability,
            "model_capability": self.model_capability,
            "network_capability": self.network_capability,
            "secret_capability": self.secret_capability,
            "runtime_capability": self.runtime_capability,
            "experiment_capability": self.experiment_capability,
            "output_path_capability": self.output_path_capability,
            "benchmark_execution": self.benchmark_execution,
            "agent_execution": self.agent_execution,
            "publication_eligibility": self.publication_eligibility,
            "result_persisted": self.result_persisted,
        }


@dataclass(frozen=True)
class BenchmarkContractTestReport:
    """Coverage-aware Contract Test report labelled as fake-fixture evidence."""

    plan_identity: str
    profile: BenchmarkFixtureProfileMetadata
    cases: tuple[BenchmarkContractCaseResult, ...]
    diagnostics: tuple[BenchmarkContractDiagnostic, ...]
    coverage: BenchmarkContractCoverage
    diagnostics_truncated: bool = False
    safety: BenchmarkContractSafetyFacts = BenchmarkContractSafetyFacts()
    mode: str = "fake-fixture"

    @property
    def checked_components(self) -> int:
        """Return the legacy count of fixtures that actually executed.

        Returns:
            Number of passed or failed cases.
        """
        return self.coverage.passed + self.coverage.failed

    @property
    def is_success(self) -> bool:
        """Preserve CLI success only for complete failure-free coverage.

        Returns:
            True when all occurrence cases executed and passed.
        """
        return self.coverage.complete and self.coverage.executed_checks_passed

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the bounded coverage-aware Contract Test report.

        Returns:
            Safe fake-fixture result compatible with existing CLI keys.
        """
        return {
            "ok": self.is_success,
            "mode": self.mode,
            "plan_identity": self.plan_identity,
            "profile": self.profile.to_safe_dict(),
            "checked_components": self.checked_components,
            "coverage": self.coverage.to_safe_dict(),
            "cases": [item.to_safe_dict() for item in self.cases],
            "diagnostics": [
                item.to_safe_dict() for item in self.diagnostics
            ],
            "diagnostics_truncated": self.diagnostics_truncated,
            "real_device_evidence": self.safety.real_device_evidence,
            "safety": self.safety.to_safe_dict(),
        }


@dataclass(frozen=True)
class _BenchmarkContractOccurrence:
    """Internal immutable occurrence discovered from one compiled Plan."""

    case_id: str
    task_id: str
    kind: BenchmarkFixtureKind
    logical_name: str
    path: tuple[str | int, ...]
    phase: str | None
    params: Mapping[str, Any]
    seed: int


def _visit_evaluator_occurrences(
    config: Mapping[str, Any],
    *,
    path: tuple[str | int, ...],
) -> tuple[tuple[tuple[str | int, ...], Mapping[str, Any]], ...]:
    """Collect evaluator leaves with their exact tree-local paths.

    Args:
        config: Evaluator node mapping.
        path: Current task-local evaluator path.

    Raises:
        None.

    Returns:
        Stable evaluator leaf path and declaration pairs.
    """
    if config.get("name") == "composite":
        leaves: list[tuple[tuple[str | int, ...], Mapping[str, Any]]] = []
        rules = config.get("params", {}).get("rules", [])
        for index, child in enumerate(rules):
            if isinstance(child, Mapping):
                leaves.extend(
                    _visit_evaluator_occurrences(
                        child,
                        path=(*path, "params", "rules", index),
                    )
                )
        return tuple(leaves)
    return ((path, config),)


def _visit_evaluators(config: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    """Retain the legacy stable evaluator-leaf helper.

    Args:
        config: Evaluator node mapping.

    Raises:
        None.

    Returns:
        Stable evaluator leaf declarations.
    """
    return tuple(
        item
        for _, item in _visit_evaluator_occurrences(
            config,
            path=("evaluator",),
        )
    )


def _case_seed(seed: int, case_id: str) -> int:
    """Derive an order-independent non-negative case-local seed.

    Args:
        seed: Caller-provided root seed.
        case_id: Stable occurrence identity.

    Raises:
        None.

    Returns:
        Stable signed-63-bit-compatible integer seed.
    """
    digest = canonical_hash({"seed": seed, "case_id": case_id})
    return int(digest.removeprefix("sha256:")[:16], 16) & ((1 << 63) - 1)


def _environment_phase(reference: Any, collection: str) -> str:
    """Project one environment reference into reset, setup, or cleanup.

    Args:
        reference: Canonical EnvironmentPluginCall value.
        collection: Owning task collection name.

    Raises:
        None.

    Returns:
        Stable fake lifecycle phase.
    """
    if collection == "cleanup_initializer":
        return "cleanup"
    explicit = getattr(reference, "phase", None)
    if explicit in {"reset", "setup"}:
        return str(explicit)
    namespace = str(getattr(reference, "namespace", "") or "")
    category = str(getattr(reference, "category", "") or "")
    if ".reset" in namespace or category == "reset":
        return "reset"
    return "setup"


def discover_benchmark_contract_cases(
    plan: BenchmarkPlan,
    *,
    seed: int = 0,
) -> tuple[_BenchmarkContractOccurrence, ...]:
    """Discover bounded stable reference occurrences without invoking fixtures.

    Args:
        plan: Pure compiled Benchmark Plan.
        seed: Caller-provided root seed.

    Raises:
        BenchmarkContractTestCapacityError: More than 1,000 cases are needed.

    Returns:
        Stable occurrence inventory with case-local seeds.
    """
    raw: list[tuple[str, BenchmarkFixtureKind, str, tuple[str | int, ...], str | None, Mapping[str, Any]]] = []
    for task_index, task in enumerate(plan.tasks):
        for variable, reference in task.task_initializer.items():
            raw.append(
                (
                    task.id,
                    BenchmarkFixtureKind.INITIALIZER,
                    reference.name,
                    (task_index, "task_initializer", variable),
                    None,
                    reference.params,
                )
            )
        evaluator = task.evaluator.model_dump(mode="json", exclude_none=True)
        for path, leaf in _visit_evaluator_occurrences(
            evaluator,
            path=(task_index, "evaluator"),
        ):
            params = leaf.get("params", {})
            raw.append(
                (
                    task.id,
                    BenchmarkFixtureKind.EVALUATOR,
                    str(params.get("method", "")),
                    path,
                    "evaluation",
                    params,
                )
            )
        for collection, references in (
            ("environment_initializer", task.environment_initializer),
            ("cleanup_initializer", task.cleanup_initializer),
        ):
            for index, reference in enumerate(references):
                raw.append(
                    (
                        task.id,
                        BenchmarkFixtureKind.ENVIRONMENT,
                        reference.name,
                        (task_index, collection, index),
                        _environment_phase(reference, collection),
                        reference.params,
                    )
                )
        if len(raw) > BENCHMARK_CONTRACT_MAX_CASES:
            raise BenchmarkContractTestCapacityError(
                "Benchmark Contract Test case count exceeds 1,000"
            )

    occurrences: list[_BenchmarkContractOccurrence] = []
    for task_id, kind, logical_name, path, phase, params in raw:
        case_id = canonical_hash(
            {
                "task_id": task_id,
                "kind": kind.value,
                "logical_name": logical_name,
                "path": list(path[1:]),
            }
        )
        occurrences.append(
            _BenchmarkContractOccurrence(
                case_id=case_id,
                task_id=task_id,
                kind=kind,
                logical_name=logical_name,
                path=path,
                phase=phase,
                params=dict(params),
                seed=_case_seed(seed, case_id),
            )
        )
    return tuple(occurrences)


def _assert_json_shape(
    value: Any,
    *,
    depth: int = 0,
    budget: list[int] | None = None,
) -> None:
    """Reject non-JSON, non-finite, deep, or excessively wide fixture output.

    Args:
        value: Candidate fixture value.
        depth: Current recursive depth.
        budget: Shared remaining node budget.

    Raises:
        _FixtureContractFailure: Value violates the bounded JSON contract.

    Returns:
        None.
    """
    remaining = budget if budget is not None else [5_000]
    remaining[0] -= 1
    if remaining[0] < 0 or depth > 12:
        raise _FixtureContractFailure("benchmark.ctk.output_capacity_exceeded")
    if value is None or isinstance(value, (str, bool, int)):
        if isinstance(value, str) and len(value) > 4_000:
            raise _FixtureContractFailure("benchmark.ctk.output_capacity_exceeded")
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise _FixtureContractFailure("benchmark.ctk.output_not_serializable")
        return
    if isinstance(value, Mapping):
        if len(value) > 256:
            raise _FixtureContractFailure("benchmark.ctk.output_capacity_exceeded")
        for key, item in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise _FixtureContractFailure("benchmark.ctk.output_not_serializable")
            _assert_json_shape(item, depth=depth + 1, budget=remaining)
        return
    if isinstance(value, (list, tuple)):
        if len(value) > 1_000:
            raise _FixtureContractFailure("benchmark.ctk.output_capacity_exceeded")
        for item in value:
            _assert_json_shape(item, depth=depth + 1, budget=remaining)
        return
    raise _FixtureContractFailure("benchmark.ctk.output_not_serializable")


def _safe_fixture_value(
    value: Any,
    *,
    path: tuple[str | int, ...],
) -> Any:
    """Validate and return one canonical-comparable safe fixture value.

    Args:
        value: Candidate role-specific fixture output.
        path: Safe logical diagnostic path.

    Raises:
        _FixtureContractFailure: Output is unsafe or not bounded JSON.

    Returns:
        Sanitized JSON-compatible value with no redaction actions.
    """
    _assert_json_shape(value)
    safe, diagnostics = sanitize_export(value, path=path)
    if diagnostics:
        raise _FixtureContractFailure("benchmark.ctk.unsafe_evidence")
    encoded = json.dumps(
        safe,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > BENCHMARK_CONTRACT_MAX_OUTPUT_BYTES:
        raise _FixtureContractFailure("benchmark.ctk.output_capacity_exceeded")
    return safe


def _invoke_fixture(
    occurrence: _BenchmarkContractOccurrence,
    descriptor: BenchmarkFixtureDescriptor,
    runner: Fixture,
) -> Any:
    """Invoke one role-specific fake fixture and normalize its output.

    Args:
        occurrence: Exact logical contract occurrence.
        descriptor: Matching trusted fixture descriptor.
        runner: Fresh callable produced by the descriptor factory.

    Raises:
        _FixtureContractFailure: Role-level or evidence contract fails.
        Exception: Trusted fixture invocation fails unexpectedly.

    Returns:
        Safe canonical-comparable fixture result.
    """
    if not callable(runner):
        raise _FixtureContractFailure("benchmark.ctk.fixture_factory_invalid")
    params = _safe_fixture_value(dict(occurrence.params), path=(*occurrence.path, "params"))
    raw = runner(params, random.Random(occurrence.seed))
    if occurrence.kind is BenchmarkFixtureKind.EVALUATOR:
        normalized = normalize_evaluation_result(
            raw,
            evaluator_id=occurrence.logical_name,
            duration_ms=0.0,
        )
        raw = normalized.to_safe_dict()
    return _safe_fixture_value(raw, path=occurrence.path)


def _failed_case(
    occurrence: _BenchmarkContractOccurrence,
    descriptor: BenchmarkFixtureDescriptor,
    checks: list[str],
    error: Exception,
) -> BenchmarkContractCaseResult:
    """Convert a trusted fixture failure into one safe failed case.

    Args:
        occurrence: Exact occurrence being tested.
        descriptor: Matching fixture descriptor.
        checks: Checks completed before failure.
        error: Internal failure without public input echoing.

    Raises:
        None.

    Returns:
        Safe failed case result.
    """
    code = (
        error.code
        if isinstance(error, _FixtureContractFailure)
        else f"benchmark.ctk.{occurrence.kind.value}_failed"
    )
    message = (
        f"{occurrence.kind.value.title()} fake fixture failed "
        f"({type(error).__name__})."
    )
    return BenchmarkContractCaseResult(
        case_id=occurrence.case_id,
        task_id=occurrence.task_id,
        kind=occurrence.kind,
        logical_name=occurrence.logical_name,
        path=occurrence.path,
        phase=occurrence.phase,
        seed=occurrence.seed,
        status=BenchmarkContractStatus.FAILED,
        fixture_id=descriptor.fixture_id,
        fixture_version=descriptor.version,
        checks=tuple(checks),
        diagnostics=(
            BenchmarkContractDiagnostic(
                code=code,
                path=occurrence.path,
                message=message,
            ),
        ),
    )


def _run_occurrence(
    occurrence: _BenchmarkContractOccurrence,
    descriptor: BenchmarkFixtureDescriptor | None,
) -> BenchmarkContractCaseResult:
    """Run one occurrence or return explicit skipped coverage.

    Args:
        occurrence: Exact discovered contract occurrence.
        descriptor: Matching trusted fixture, when available.

    Raises:
        None: Fixture failures become bounded case diagnostics.

    Returns:
        Passed, failed, or skipped occurrence result.
    """
    if descriptor is None:
        diagnostic = BenchmarkContractDiagnostic(
            code="benchmark.ctk.fixture_missing",
            path=occurrence.path,
            message=f"No explicit {occurrence.kind.value} fake fixture is registered.",
        )
        return BenchmarkContractCaseResult(
            case_id=occurrence.case_id,
            task_id=occurrence.task_id,
            kind=occurrence.kind,
            logical_name=occurrence.logical_name,
            path=occurrence.path,
            phase=occurrence.phase,
            seed=occurrence.seed,
            status=BenchmarkContractStatus.SKIPPED,
            skipped=("fixture:not-registered",),
            diagnostics=(diagnostic,),
        )
    if set(descriptor.capabilities) & _FORBIDDEN_CAPABILITIES:
        return _failed_case(
            occurrence,
            descriptor,
            [],
            _FixtureContractFailure("benchmark.ctk.fixture_capability_forbidden"),
        )

    checks = ["parameters"]
    if occurrence.kind is BenchmarkFixtureKind.ENVIRONMENT:
        if occurrence.phase not in {"reset", "setup", "cleanup"}:
            return _failed_case(
                occurrence,
                descriptor,
                checks,
                _FixtureContractFailure("benchmark.ctk.lifecycle_phase_invalid"),
            )
        checks.append("lifecycle")
    try:
        first_runner = descriptor.factory()
        second_runner = None
        if descriptor.deterministic or descriptor.isolated:
            second_runner = descriptor.factory()
            if descriptor.isolated and first_runner is second_runner:
                raise _FixtureContractFailure(
                    "benchmark.ctk.fixture_scope_not_isolated"
                )
            if descriptor.isolated:
                checks.append("fresh_scope")
        first = _invoke_fixture(occurrence, descriptor, first_runner)
        checks.extend(("invocation", "serialization"))
        if occurrence.kind is BenchmarkFixtureKind.EVALUATOR:
            checks.append("evaluator_normalization")
        if second_runner is not None:
            second = _invoke_fixture(occurrence, descriptor, second_runner)
            if first != second:
                code = (
                    "benchmark.ctk.output_not_deterministic"
                    if descriptor.deterministic
                    else "benchmark.ctk.fixture_state_leak"
                )
                raise _FixtureContractFailure(code)
            if descriptor.deterministic:
                checks.append("determinism")
            if descriptor.isolated:
                checks.append("observable_isolation")
    except Exception as error:
        return _failed_case(occurrence, descriptor, checks, error)
    return BenchmarkContractCaseResult(
        case_id=occurrence.case_id,
        task_id=occurrence.task_id,
        kind=occurrence.kind,
        logical_name=occurrence.logical_name,
        path=occurrence.path,
        phase=occurrence.phase,
        seed=occurrence.seed,
        status=BenchmarkContractStatus.PASSED,
        fixture_id=descriptor.fixture_id,
        fixture_version=descriptor.version,
        checks=tuple(checks),
    )


def _bound_case_diagnostics(
    cases: tuple[BenchmarkContractCaseResult, ...],
) -> tuple[
    tuple[BenchmarkContractCaseResult, ...],
    tuple[BenchmarkContractDiagnostic, ...],
    bool,
]:
    """Apply one global deterministic diagnostic cap across case results.

    Args:
        cases: Stable complete case sequence.

    Raises:
        None.

    Returns:
        Cases with bounded diagnostics, flattened diagnostics, truncation flag.
    """
    remaining = BENCHMARK_CONTRACT_MAX_DIAGNOSTICS
    bounded: list[BenchmarkContractCaseResult] = []
    flattened: list[BenchmarkContractDiagnostic] = []
    truncated = False
    for case in cases:
        accepted = case.diagnostics[:remaining]
        remaining -= len(accepted)
        if len(accepted) != len(case.diagnostics):
            truncated = True
        flattened.extend(accepted)
        bounded.append(replace(case, diagnostics=accepted))
    return tuple(bounded), tuple(flattened), truncated


def run_benchmark_contract_tests(
    plan: BenchmarkPlan,
    fixtures: BenchmarkFixtureSet | BenchmarkFixtureProfile,
    *,
    seed: int = 0,
) -> BenchmarkContractTestReport:
    """Run bounded explicit fake fixtures without resolving runtime plugins.

    Args:
        plan: Pure compiled Benchmark Plan.
        fixtures: Legacy fixture set or explicit trusted profile.
        seed: Deterministic caller root seed.

    Raises:
        BenchmarkContractTestCapacityError: Case discovery exceeds 1,000.

    Returns:
        Coverage-aware typed Contract Test evidence.
    """
    profile = fixtures.to_profile() if isinstance(fixtures, BenchmarkFixtureSet) else fixtures
    occurrences = discover_benchmark_contract_cases(plan, seed=seed)
    lookup = profile.fixture_map
    cases = tuple(
        _run_occurrence(occurrence, lookup.get((occurrence.kind, occurrence.logical_name)))
        for occurrence in occurrences
    )
    cases, diagnostics, diagnostics_truncated = _bound_case_diagnostics(cases)
    passed = sum(item.status is BenchmarkContractStatus.PASSED for item in cases)
    failed = sum(item.status is BenchmarkContractStatus.FAILED for item in cases)
    skipped = sum(item.status is BenchmarkContractStatus.SKIPPED for item in cases)
    coverage = BenchmarkContractCoverage(
        total=len(cases),
        passed=passed,
        failed=failed,
        skipped=skipped,
        complete=skipped == 0,
        executed_checks_passed=failed == 0,
    )
    return BenchmarkContractTestReport(
        plan_identity=plan.canonical_hash(),
        profile=profile.metadata,
        cases=cases,
        diagnostics=diagnostics,
        coverage=coverage,
        diagnostics_truncated=diagnostics_truncated,
    )


def declaration_fixture_set(plan: BenchmarkPlan) -> BenchmarkFixtureSet:
    """Build deterministic declaration-only fixtures for CLI smoke checks.

    Args:
        plan: Plan whose logical references need compatibility fixtures.

    Raises:
        None.

    Returns:
        Explicit declaration-only mapping, not real plugin evidence.
    """
    initializer_names = {
        reference.name
        for task in plan.tasks
        for reference in task.task_initializer.values()
    }
    evaluator_names = {
        str(leaf.get("params", {}).get("method", ""))
        for task in plan.tasks
        for leaf in _visit_evaluators(task.evaluator.model_dump(mode="json"))
    }
    environment_names = {
        reference.name
        for task in plan.tasks
        for reference in (
            *task.environment_initializer,
            *task.cleanup_initializer,
        )
    }

    def initializer_fixture(
        params: Mapping[str, Any],
        rng: random.Random,
    ) -> Any:
        """Return a deterministic declaration-only placeholder.

        Args:
            params: Declared parameters.
            rng: Deterministic fixture generator.

        Raises:
            None.

        Returns:
            Stable JSON-compatible placeholder.
        """
        del params
        return {"fixture_value": rng.randint(0, 1_000_000)}

    def evaluator_fixture(
        params: Mapping[str, Any],
        rng: random.Random,
    ) -> bool:
        """Return a deterministic passing declaration-only evaluator result.

        Args:
            params: Declared parameters.
            rng: Unused deterministic random source.

        Raises:
            None.

        Returns:
            Always true declaration-only result.
        """
        del params, rng
        return True

    def environment_fixture(
        params: Mapping[str, Any],
        rng: random.Random,
    ) -> Mapping[str, Any]:
        """Return deterministic lifecycle evidence without device access.

        Args:
            params: Declared environment parameters.
            rng: Deterministic fixture generator.

        Raises:
            None.

        Returns:
            JSON-compatible fake lifecycle evidence.
        """
        del params
        return {"fixture_sequence": rng.randint(0, 1_000_000)}

    return BenchmarkFixtureSet(
        task_initializers={
            name: initializer_fixture for name in initializer_names
        },
        evaluators={name: evaluator_fixture for name in evaluator_names if name},
        environments={
            name: environment_fixture for name in environment_names
        },
    )


def _new_random_choice_fixture() -> Fixture:
    """Create one fresh deterministic random-choice fake initializer.

    Returns:
        Fresh initializer fixture callable.
    """
    def fixture(params: Mapping[str, Any], rng: random.Random) -> Any:
        """Select one declared candidate using only the supplied RNG.

        Args:
            params: Initializer parameters containing candidate values.
            rng: Case-local deterministic random source.

        Raises:
            ValueError: Candidate values are absent.

        Returns:
            Selected JSON-compatible candidate.
        """
        candidates = params.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise ValueError("candidates are required")
        return candidates[rng.randrange(len(candidates))]

    return fixture


def _new_passing_evaluator_fixture() -> Fixture:
    """Create one fresh deterministic fake evaluator callable.

    Returns:
        Fresh evaluator fixture callable.
    """
    def fixture(params: Mapping[str, Any], rng: random.Random) -> bool:
        """Return a deterministic fake pass without inspecting host state.

        Args:
            params: Declared evaluator parameters.
            rng: Case-local deterministic random source.

        Raises:
            None.

        Returns:
            True declaration-contract result.
        """
        del params, rng
        return True

    return fixture


def studio_safe_fixture_profile() -> BenchmarkFixtureProfile:
    """Build the reviewed default Studio fake-fixture profile.

    Raises:
        None.

    Returns:
        Profile covering supported scaffold/example logical contracts only.
    """
    descriptors = [
        BenchmarkFixtureDescriptor(
            kind=BenchmarkFixtureKind.INITIALIZER,
            logical_name="random_choice",
            fixture_id="studio.random-choice",
            version="1.0.0",
            factory=_new_random_choice_fixture,
        )
    ]
    descriptors.extend(
        BenchmarkFixtureDescriptor(
            kind=BenchmarkFixtureKind.EVALUATOR,
            logical_name=name,
            fixture_id=f"studio.{name}",
            version="1.0.0",
            factory=_new_passing_evaluator_fixture,
        )
        for name in ("contains", "file_exist", "snapshot_diff")
    )
    return BenchmarkFixtureProfile(
        profile_id="studio-safe-v1",
        version="1.0.0",
        title="Studio safe fake fixtures",
        description=(
            "Reviewed in-process fake contracts for built-in teaching Packages; "
            "no runtime plugin implementation is resolved."
        ),
        evidence_level="fake-contract",
        fixtures=tuple(descriptors),
    )


def studio_fixture_profile_registry() -> BenchmarkFixtureProfileRegistry:
    """Create the default one-profile Studio registry.

    Returns:
        Bounded registry containing only the reviewed safe profile.
    """
    return BenchmarkFixtureProfileRegistry((studio_safe_fixture_profile(),))


__all__ = [
    "BENCHMARK_CONTRACT_MAX_CASES",
    "BENCHMARK_CONTRACT_MAX_DIAGNOSTICS",
    "BENCHMARK_CONTRACT_MAX_PROFILES",
    "BenchmarkContractCaseResult",
    "BenchmarkContractCoverage",
    "BenchmarkContractDiagnostic",
    "BenchmarkContractSafetyFacts",
    "BenchmarkContractStatus",
    "BenchmarkContractTestCapacityError",
    "BenchmarkContractTestReport",
    "BenchmarkFixtureDescriptor",
    "BenchmarkFixtureKind",
    "BenchmarkFixtureProfile",
    "BenchmarkFixtureProfileMetadata",
    "BenchmarkFixtureProfileRegistry",
    "BenchmarkFixtureSet",
    "declaration_fixture_set",
    "discover_benchmark_contract_cases",
    "run_benchmark_contract_tests",
    "studio_fixture_profile_registry",
    "studio_safe_fixture_profile",
]
