#!/usr/bin/env python3
"""Validate the disposable Stage 5.6B layered-acceptance proof ledger.

This module is intentionally outside the product package.  It projects bounded
acceptance evidence from authoritative product resources without adding an HTTP
resource, SQLite table, or second lifecycle state machine to Studio.
"""

from __future__ import annotations

import argparse
import json
import re
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from typing_extensions import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)


SUMMARY_SCHEMA_VERSION = 1
SUMMARY_FIXTURE_VERSION = "studio-benchmark-layered-acceptance-5.6b-v1"
MAX_SCENARIOS = 32
MAX_COMMANDS = 64
MAX_FACTS_PER_SCENARIO = 48
MAX_ARTIFACT_IDENTITIES = 64
MAX_TEXT_LENGTH = 512


class AcceptanceScenarioId(str, Enum):
    """Stable scenario identifiers emitted in required execution order."""

    STUDIO_FAKE_PASS = "studio_fake_pass"
    STUDIO_FAKE_FAIL = "studio_fake_fail"
    STUDIO_CONTEXT_INVALID = "studio_context_invalid"
    STUDIO_CANCEL_ACCEPTED = "studio_cancel_accepted"
    STUDIO_CANCEL_ACTIVE = "studio_cancel_active"
    STUDIO_CREATE_RETRY = "studio_create_retry"
    STUDIO_SSE_RECONNECT = "studio_sse_reconnect"
    STUDIO_SLOW_CLIENT = "studio_slow_client"
    STUDIO_RECOVERY_INTERRUPTED = "studio_recovery_interrupted"
    STUDIO_RECOVERY_PUBLICATION = "studio_recovery_publication"
    CORE_MULTI_CARDINALITY = "core_multi_cardinality"
    STUDIO_CARDINALITY_REJECTED = "studio_cardinality_rejected"
    INSTALLED_EXTERNAL_PACKAGE = "installed_external_package"
    ACTUAL_BACKEND_BROWSER = "actual_backend_browser"


REQUIRED_SCENARIOS = tuple(AcceptanceScenarioId)

REQUIRED_ZERO_CANARIES = (
    "adb_discovery",
    "real_device_construction",
    "external_network",
    "model_resolution",
    "secret_resolution",
    "repository_source_fallback",
)

REQUIRED_CLAIM_LIMITS = (
    "no real Android acceptance was executed",
    "Studio Worker remains limited to 1 Agent x 1 Task x 1 repeat",
    "no statistical significance is claimed",
    "Stage 5.6C-1/2 remain required",
)


class AcceptanceGateInventoryEntry(BaseModel):
    """Map one scenario to authoritative supporting gates and its 5.6B gap."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: AcceptanceScenarioId
    supporting_suites: tuple[StrictStr, ...] = Field(min_length=1, max_length=12)
    cross_layer_gap: StrictStr = Field(min_length=1, max_length=MAX_TEXT_LENGTH)


ACCEPTANCE_GATE_INVENTORY = (
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_FAKE_PASS,
        supporting_suites=(
            "tests/studio/test_benchmark_execution_worker.py",
            "tests/studio/test_benchmark_publication_replay.py",
        ),
        cross_layer_gap="Join the production service, Core result, publication, Replay, and managed artifacts in one causal record.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_FAKE_FAIL,
        supporting_suites=("tests/studio/test_benchmark_execution_worker.py",),
        cross_layer_gap="Record Agent SUCCESS and Benchmark FAIL as independent facts in the shared ledger.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_CONTEXT_INVALID,
        supporting_suites=(
            "tests/benchmark/test_experiment_runtime.py",
            "tests/studio/test_benchmark_execution_worker.py",
        ),
        cross_layer_gap="Prove the context rejection precedes every initializer, Agent, model, evaluator, and action effect.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_CANCEL_ACCEPTED,
        supporting_suites=("tests/studio/test_benchmark_experiment_resource.py",),
        cross_layer_gap="Join accepted cancellation to a unique terminal journal fact without inventing SKIPPED.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_CANCEL_ACTIVE,
        supporting_suites=("tests/studio/test_benchmark_execution_worker.py",),
        cross_layer_gap="Preserve confirmed active-work facts through cooperative cancellation and final publication.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_CREATE_RETRY,
        supporting_suites=("tests/studio/test_benchmark_experiment_resource.py",),
        cross_layer_gap="Relate one retry intent to one aggregate, schedule, private binding, and accepted event.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_SSE_RECONNECT,
        supporting_suites=("tests/studio/test_benchmark_event_stream.py",),
        cross_layer_gap="Record the continuous durable cursor relationship used by the actual product journey.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_SLOW_CLIENT,
        supporting_suites=("tests/studio/test_benchmark_event_stream.py",),
        cross_layer_gap="Join slow-subscriber isolation to unblocked worker publication and terminal state.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_RECOVERY_INTERRUPTED,
        supporting_suites=("tests/studio/test_benchmark_startup_recovery.py",),
        cross_layer_gap="Expose the no-replay effect canaries beside the authoritative interrupted recovery decision.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_RECOVERY_PUBLICATION,
        supporting_suites=("tests/studio/test_benchmark_startup_recovery.py",),
        cross_layer_gap="Join immutable result identity to publication-only retry and the unique terminal event.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.CORE_MULTI_CARDINALITY,
        supporting_suites=(
            "tests/benchmark/test_experiment_runtime.py",
            "tests/benchmark/test_reporting.py",
        ),
        cross_layer_gap="Project Core multi-cardinality and fairness separately from the Studio Worker limit.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.STUDIO_CARDINALITY_REJECTED,
        supporting_suites=(
            "tests/studio/test_benchmark_composer.py",
            "tests/studio/test_benchmark_execution_worker.py",
        ),
        cross_layer_gap="Prove public and defensive rejection are whole-request failures before effects rather than truncation.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
        supporting_suites=(
            "tests/packaging/test_benchmark_package_boundary.py",
            "tests/packaging/test_studio_android_profile_install.py",
        ),
        cross_layer_gap="Execute an independently installed Package through the installed durable Studio publication chain.",
    ),
    AcceptanceGateInventoryEntry(
        scenario_id=AcceptanceScenarioId.ACTUAL_BACKEND_BROWSER,
        supporting_suites=(
            "studio/scripts/benchmark-monitor-smoke-fixture.mjs",
            "studio/src/features/benchmark-experiment-monitor",
            "studio/src/features/benchmark-reporting",
        ),
        cross_layer_gap="Replace static-only end-to-end evidence with one browser journey backed by the actual fake Studio service.",
    ),
)


class AcceptanceEvidenceOrigin(BaseModel):
    """Safe two-axis evidence origin for all Stage 5.6B execution facts."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    acquisition: str = Field(default="contract_fixture", pattern=r"^contract_fixture$")
    environment: str = Field(default="fake_device", pattern=r"^fake_device$")
    real_device_evidence: bool = Field(default=False, alias="realDeviceEvidence")

    @model_validator(mode="after")
    def _must_remain_no_device(self) -> Self:
        """Reject any attempt to upgrade no-device acceptance provenance.

        Raises:
            ValueError: The ledger claims real-device evidence.

        Returns:
            Validated fake evidence origin.
        """
        if self.real_device_evidence:
            raise ValueError("Stage 5.6B cannot claim real-device evidence")
        return self


class AcceptanceCausalIdentities(BaseModel):
    """Bounded safe identities joining authoritative cross-layer resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_id: StrictStr | None = Field(default=None, max_length=128)
    planned_task_run_ids: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    core_task_run_ids: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    agent_run_ids: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    event_ids: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    replay_ids: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    report_identities: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    trajectory_identities: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    manifest_identities: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    bundle_identities: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )
    managed_artifact_ids: tuple[StrictStr, ...] = Field(
        default=(), max_length=MAX_ARTIFACT_IDENTITIES
    )

    @field_validator("*")
    @classmethod
    def _safe_identity_fields(cls, value: Any) -> Any:
        """Reject duplicate or unsafe opaque identities.

        Args:
            value: One optional identity or tuple of identities.

        Raises:
            ValueError: Identity content is duplicate, blank, or unsafe.

        Returns:
            Validated identity value.
        """
        values = (value,) if isinstance(value, str) else tuple(value or ())
        if len(values) != len(set(values)):
            raise ValueError("causal identities must be unique within each kind")
        for item in values:
            _assert_safe_string(item, field="causal identity")
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:@+-]{0,127}", item):
                raise ValueError("causal identity must be opaque and path-free")
        return value


class AcceptanceScenarioEvidence(BaseModel):
    """One verified scenario projected from authoritative product resources."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: AcceptanceScenarioId
    verification: str = Field(pattern=r"^passed$")
    suite_ids: tuple[StrictStr, ...] = Field(min_length=1, max_length=12)
    fixture_inputs: dict[StrictStr, StrictStr | StrictInt | StrictBool] = Field(
        default_factory=dict, max_length=24
    )
    identities: AcceptanceCausalIdentities = Field(
        default_factory=AcceptanceCausalIdentities
    )
    facts: dict[StrictStr, StrictStr | StrictInt | StrictBool | None] = Field(
        min_length=1, max_length=MAX_FACTS_PER_SCENARIO
    )
    evidence_origin: AcceptanceEvidenceOrigin = Field(
        default_factory=AcceptanceEvidenceOrigin
    )

    @field_validator("suite_ids")
    @classmethod
    def _safe_suites(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Validate bounded repository-relative suite identities.

        Args:
            value: Suite identities supporting the scenario.

        Raises:
            ValueError: A suite is duplicate, absolute, or unsafe.

        Returns:
            Validated suite identities.
        """
        if len(value) != len(set(value)):
            raise ValueError("suite identities must be unique")
        for item in value:
            _assert_safe_string(item, field="suite identity")
            if item.startswith(("/", "\\")) or ".." in Path(item).parts:
                raise ValueError("suite identity must be repository-relative")
        return value

    @field_validator("fixture_inputs", "facts")
    @classmethod
    def _safe_mappings(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        """Validate bounded scalar evidence mappings.

        Args:
            value: Fixture-input or factual scalar mapping.

        Raises:
            ValueError: A key/value is unsafe or unbounded.

        Returns:
            Validated mapping.
        """
        for key, item in value.items():
            _assert_safe_string(key, field="fact key")
            if isinstance(item, str):
                _assert_safe_string(item, field="fact value")
        return value

    @model_validator(mode="after")
    def _required_causal_facts(self) -> Self:
        """Require the identity closure appropriate to cross-layer scenarios.

        Raises:
            ValueError: A scenario omits an identity it claims to verify.

        Returns:
            Validated scenario evidence.
        """
        identities = self.identities
        requires_experiment = self.scenario_id not in {
            AcceptanceScenarioId.CORE_MULTI_CARDINALITY,
            AcceptanceScenarioId.STUDIO_CARDINALITY_REJECTED,
        }
        if requires_experiment and identities.experiment_id is None:
            raise ValueError("Studio acceptance scenario requires Experiment identity")
        requires_task_run = self.scenario_id in {
            AcceptanceScenarioId.STUDIO_FAKE_PASS,
            AcceptanceScenarioId.STUDIO_FAKE_FAIL,
            AcceptanceScenarioId.STUDIO_CONTEXT_INVALID,
            AcceptanceScenarioId.STUDIO_CANCEL_ACTIVE,
            AcceptanceScenarioId.STUDIO_RECOVERY_INTERRUPTED,
            AcceptanceScenarioId.STUDIO_RECOVERY_PUBLICATION,
            AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
            AcceptanceScenarioId.ACTUAL_BACKEND_BROWSER,
        }
        if requires_task_run and not identities.planned_task_run_ids:
            raise ValueError("scenario requires a planned TaskRun identity")
        if self.scenario_id in {
            AcceptanceScenarioId.STUDIO_FAKE_PASS,
            AcceptanceScenarioId.STUDIO_FAKE_FAIL,
            AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
        } and not identities.core_task_run_ids:
            raise ValueError("executed scenario requires a Core TaskRun identity")
        if self.scenario_id in {
            AcceptanceScenarioId.STUDIO_FAKE_PASS,
            AcceptanceScenarioId.INSTALLED_EXTERNAL_PACKAGE,
            AcceptanceScenarioId.ACTUAL_BACKEND_BROWSER,
        }:
            publication_groups = (
                identities.replay_ids,
                identities.report_identities,
                identities.trajectory_identities,
                identities.manifest_identities,
                identities.bundle_identities,
            )
            if any(not group for group in publication_groups):
                raise ValueError("published scenario requires Replay and publication closure")
        if (
            self.scenario_id is AcceptanceScenarioId.CORE_MULTI_CARDINALITY
            and len(identities.core_task_run_ids) < 8
        ):
            raise ValueError("Core matrix requires at least eight Core TaskRuns")
        return self


class AcceptanceCommandEvidence(BaseModel):
    """One reproducible suite command and its observed bounded result."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    suite_id: StrictStr = Field(min_length=1, max_length=128)
    command: StrictStr = Field(min_length=1, max_length=MAX_TEXT_LENGTH)
    verification: str = Field(pattern=r"^passed$")
    observed: StrictStr = Field(min_length=1, max_length=MAX_TEXT_LENGTH)

    @field_validator("suite_id", "command", "observed")
    @classmethod
    def _safe_command_fields(cls, value: str) -> str:
        """Reject unsafe or host-specific command evidence.

        Args:
            value: One command-evidence string.

        Raises:
            ValueError: Text includes a private or host-specific value.

        Returns:
            Validated string.
        """
        _assert_safe_string(value, field="command evidence")
        return value


class AcceptanceCapabilityBoundary(BaseModel):
    """Keep verified Core capability and Studio product limit separate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    core_multi_cardinality_verified: StrictBool
    core_agents: StrictInt = Field(ge=2, le=16)
    core_tasks: StrictInt = Field(ge=2, le=128)
    core_repeats: StrictInt = Field(ge=2, le=32)
    studio_max_agents: StrictInt = Field(default=1, ge=1, le=1)
    studio_max_tasks: StrictInt = Field(default=1, ge=1, le=1)
    studio_max_repeats: StrictInt = Field(default=1, ge=1, le=1)
    studio_over_limit_rejected_before_effects: StrictBool
    significance_claimed: StrictBool = False

    @model_validator(mode="after")
    def _truthful_boundary(self) -> Self:
        """Require verified Core facts and fail-closed Studio limits.

        Raises:
            ValueError: Capability and limit facts are weakened or conflated.

        Returns:
            Validated capability boundary.
        """
        if not self.core_multi_cardinality_verified:
            raise ValueError("Core multi-cardinality gate is required")
        if not self.studio_over_limit_rejected_before_effects:
            raise ValueError("Studio over-limit zero-effect rejection is required")
        if self.significance_claimed:
            raise ValueError("Stage 5.6B cannot claim statistical significance")
        return self


class StudioBenchmarkLayeredAcceptanceSummaryV1(BaseModel):
    """Complete deterministic no-device Stage 5.6B acceptance proof ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: StrictInt = Field(default=SUMMARY_SCHEMA_VERSION, alias="schemaVersion")
    fixture_version: StrictStr = Field(default=SUMMARY_FIXTURE_VERSION, alias="fixtureVersion")
    environment: str = Field(default="no_device", pattern=r"^no_device$")
    scenarios: tuple[AcceptanceScenarioEvidence, ...] = Field(
        min_length=len(REQUIRED_SCENARIOS), max_length=MAX_SCENARIOS
    )
    commands: tuple[AcceptanceCommandEvidence, ...] = Field(
        min_length=1, max_length=MAX_COMMANDS
    )
    zero_side_effect_canaries: dict[StrictStr, StrictInt] = Field(
        alias="zeroSideEffectCanaries"
    )
    capability_boundary: AcceptanceCapabilityBoundary = Field(alias="capabilityBoundary")
    claim_limits: tuple[StrictStr, ...] = Field(alias="claimLimits")

    @model_validator(mode="after")
    def _complete_and_truthful(self) -> Self:
        """Require exact scenario order, zero canaries, and fixed claim limits.

        Raises:
            ValueError: Required evidence is absent, duplicated, non-zero, or unsafe.

        Returns:
            Complete validated summary.
        """
        if self.schema_version != SUMMARY_SCHEMA_VERSION:
            raise ValueError("unsupported layered acceptance summary schema")
        if self.fixture_version != SUMMARY_FIXTURE_VERSION:
            raise ValueError("unknown layered acceptance fixture version")
        actual = tuple(item.scenario_id for item in self.scenarios)
        if actual != REQUIRED_SCENARIOS:
            raise ValueError("required scenarios must appear exactly once in stable order")
        if tuple(sorted(self.zero_side_effect_canaries)) != tuple(
            sorted(REQUIRED_ZERO_CANARIES)
        ):
            raise ValueError("zero-side-effect canary set is incomplete or unknown")
        if any(value != 0 for value in self.zero_side_effect_canaries.values()):
            raise ValueError("forbidden side-effect canaries must all remain zero")
        if self.claim_limits != REQUIRED_CLAIM_LIMITS:
            raise ValueError("claim limits must preserve the Stage 5.6B boundary")
        _assert_safe_json(
            self.model_dump(mode="json", by_alias=True),
            field="acceptance summary",
        )
        return self

    def canonical_json(self) -> str:
        """Return deterministic compact JSON for storage as disposable evidence.

        Returns:
            Canonical JSON with sorted keys and no host-dependent whitespace.
        """
        return json.dumps(
            self.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    def semantic_projection(self) -> dict[str, Any]:
        """Remove opaque runtime values while preserving causal shape and facts.

        Returns:
            JSON-compatible projection suitable for deterministic rerun comparison.
        """
        projected: list[dict[str, Any]] = []
        for scenario in self.scenarios:
            identity_dump = scenario.identities.model_dump(mode="json")
            projected.append(
                {
                    "scenarioId": scenario.scenario_id.value,
                    "verification": scenario.verification,
                    "fixtureInputs": dict(sorted(scenario.fixture_inputs.items())),
                    "identityPresence": {
                        key: (bool(value) if isinstance(value, list) else value is not None)
                        for key, value in sorted(identity_dump.items())
                    },
                    "identityCardinality": {
                        key: len(value)
                        for key, value in sorted(identity_dump.items())
                        if isinstance(value, list)
                    },
                    "facts": dict(sorted(scenario.facts.items())),
                    "evidenceOrigin": scenario.evidence_origin.model_dump(
                        mode="json", by_alias=True
                    ),
                }
            )
        return {
            "schemaVersion": self.schema_version,
            "fixtureVersion": self.fixture_version,
            "environment": self.environment,
            "scenarios": projected,
            "zeroSideEffectCanaries": dict(
                sorted(self.zero_side_effect_canaries.items())
            ),
            "capabilityBoundary": self.capability_boundary.model_dump(mode="json"),
            "claimLimits": list(self.claim_limits),
        }

    def semantically_equals(
        self,
        other: "StudioBenchmarkLayeredAcceptanceSummaryV1",
    ) -> bool:
        """Compare repeatable semantics while allowing opaque IDs to differ.

        Args:
            other: Independently generated validated summary.

        Returns:
            Whether both summaries preserve identical causal semantics.
        """
        return self.semantic_projection() == other.semantic_projection()


_PRIVATE_VALUE_PATTERNS = (
    re.compile(r"(?:^|[/\\])Users(?:[/\\])", re.IGNORECASE),
    re.compile(r"(?:^|[/\\])home(?:[/\\])", re.IGNORECASE),
    re.compile(r"(?:^|[/\\])private(?:[/\\])", re.IGNORECASE),
    re.compile(r"[A-Za-z]:\\"),
    re.compile(r"\bemulator-\d+\b", re.IGNORECASE),
    re.compile(r"\b(?:api[_-]?key|authorization|bearer|password|secret|token)\s*[:=]", re.IGNORECASE),
    re.compile(r"object at 0x[0-9a-f]+", re.IGNORECASE),
)

_PRIVATE_KEYS = {
    "rawserial",
    "serial",
    "devicehandle",
    "liveobject",
    "privatebinding",
    "privatefingerprint",
    "targetkey",
    "hostpath",
    "artifactbytes",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
}


def _assert_safe_string(value: str, *, field: str) -> None:
    """Reject blank, oversized, host-specific, or secret-shaped strings.

    Args:
        value: Candidate public acceptance string.
        field: Safe diagnostic label.

    Raises:
        ValueError: The candidate is unsafe.

    Returns:
        None.
    """
    if not value or len(value) > MAX_TEXT_LENGTH:
        raise ValueError(f"{field} must be non-empty and bounded")
    if any(pattern.search(value) for pattern in _PRIVATE_VALUE_PATTERNS):
        raise ValueError(f"{field} contains private or host-specific content")


def _assert_safe_json(value: Any, *, field: str) -> None:
    """Recursively reject unsafe keys, strings, bytes, and live objects.

    Args:
        value: Candidate JSON-compatible value.
        field: Safe diagnostic label.

    Raises:
        ValueError: The value contains a forbidden key or representation.

    Returns:
        None.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in _PRIVATE_KEYS:
                raise ValueError(f"{field} contains forbidden private field")
            _assert_safe_json(item, field=field)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_safe_json(item, field=field)
        return
    if isinstance(value, str):
        _assert_safe_string(value, field=field)
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{field} must not contain artifact bytes")
    if value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError(f"{field} must contain JSON scalar values only")


def validate_summary_file(path: str | Path) -> StudioBenchmarkLayeredAcceptanceSummaryV1:
    """Load and strictly validate one generated acceptance summary.

    Args:
        path: JSON proof-ledger path.

    Raises:
        OSError: The file cannot be read.
        ValueError: JSON or the acceptance contract is invalid.

    Returns:
        Strict validated Stage 5.6B summary.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return StudioBenchmarkLayeredAcceptanceSummaryV1.model_validate(payload)


def write_summary(
    summary: StudioBenchmarkLayeredAcceptanceSummaryV1,
    path: str | Path,
) -> Path:
    """Write one validated summary under an explicit disposable artifact root.

    Args:
        summary: Complete validated proof ledger.
        path: Explicit destination JSON file.

    Raises:
        OSError: The parent or file cannot be written.

    Returns:
        Resolved destination path.
    """
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(summary.canonical_json() + "\n", encoding="utf-8")
    return destination


def _parser() -> argparse.ArgumentParser:
    """Build the narrow validation CLI parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Validate a Stage 5.6B no-device acceptance summary."
    )
    parser.add_argument("summary", type=Path)
    parser.add_argument(
        "--compare",
        type=Path,
        help="Optionally compare semantic rerun equivalence to another summary.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate one summary and optionally compare deterministic semantics.

    Args:
        argv: Optional CLI arguments excluding the executable name.

    Raises:
        OSError: An input file cannot be read.
        ValueError: An input ledger is invalid or semantically different.

    Returns:
        Zero after successful validation.
    """
    args = _parser().parse_args(argv)
    summary = validate_summary_file(args.summary)
    if args.compare is not None:
        comparison = validate_summary_file(args.compare)
        if not summary.semantically_equals(comparison):
            raise ValueError("acceptance summaries are not semantically equivalent")
    print(
        json.dumps(
            {
                "schemaVersion": summary.schema_version,
                "fixtureVersion": summary.fixture_version,
                "scenarioCount": len(summary.scenarios),
                "verification": "passed",
                "realDeviceEvidence": False,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
