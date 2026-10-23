#!/usr/bin/env python3
"""Validate bounded Stage 5.6C-2 Android browser acceptance evidence.

The module deliberately remains acceptance-only tooling.  It consumes the
strict Stage 5.6C-1 service summary before any browser or device authority is
resolved, and it validates a disposable browser proof ledger.  It does not add
an HTTP DTO, database table, runtime branch, or source of product truth.
"""

from __future__ import annotations

import argparse
from enum import Enum
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any, Callable, Mapping, Sequence, TypeVar

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
from typing_extensions import Self


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Direct ``python scripts/...`` execution otherwise exposes only scripts/.
    sys.path.insert(0, str(ROOT))

from scripts.studio_benchmark_android_service_acceptance import (  # noqa: E402
    CAMPAIGN_VERSION as SERVICE_CAMPAIGN_VERSION,
    REQUIRED_SCENARIOS as SERVICE_SCENARIOS,
    AndroidServiceScenarioId,
    SafeAcceptanceSelection,
    SafeEvidenceOrigin,
    StudioBenchmarkAndroidServiceAcceptanceSummaryV1,
    assert_forbidden_values_absent,
    validate_summary_file as validate_service_summary_file,
)


SUMMARY_SCHEMA_VERSION = 1
CAMPAIGN_VERSION = "studio-benchmark-android-view-5.6c2-v1"
MAX_TEXT = 1000
MAX_ROUTE = 500
MAX_OBSERVATIONS = 256
MAX_NETWORK_OBSERVATIONS = 256
MAX_ARTIFACTS = 256
MAX_COMMANDS = 64
MAX_SCREENSHOTS = 64
MAX_EVENTS = 1000
MAX_SCAN_DOCUMENTS = 4096
REQUIRED_CLAIM_LIMITS = (
    "Evidence is limited to the selected Android target, en-US portrait "
    "context, AndroidWorld_6 test task, Protocol seed 42, two immutable "
    "Agent revisions, and one repeat.",
    "The browser campaign proves bounded Studio presentation and resource "
    "continuity, not broad Android compatibility, arbitrary task success, "
    "model quality, automatic diagnosis, or statistical significance.",
    "Fresh source, historical Replay projection, and fake fixture provenance "
    "remain distinct; screenshots, titles, URLs, profiles, and artifacts do "
    "not upgrade execution evidence.",
    "Studio Worker remains limited to 1 Agent x 1 Task x 1 repeat.",
)

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_ROUTE = re.compile(
    r"^/(?:studio|api/studio)/[A-Za-z0-9_./:@+-]{1,480}"
    r"(?:\?[A-Za-z0-9_.:@%&=+-]{1,240})?$"
)
_HOST_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s\"'(])(?:/(?:Users|home|private|var|tmp|opt|etc)/[^\s\"']+"
    r"|[A-Za-z]:[\\/][^\s\"']+)"
)
_SECRET_SHAPE = re.compile(
    r"(?:\b(?:sk|api|token|secret|password)[-_][A-Za-z0-9_-]{12,}\b"
    r"|-----BEGIN [A-Z ]+PRIVATE KEY-----)",
    re.IGNORECASE,
)
_PRIVATE_KEYS = {
    "serial",
    "adbserial",
    "deviceserial",
    "rawserial",
    "adbarguments",
    "adbcommand",
    "configpath",
    "configurationpath",
    "bindingfingerprint",
    "privatefingerprint",
    "targetkey",
    "apikey",
    "accesstoken",
    "password",
    "secret",
    "devicehandle",
    "livecomponent",
    "hostpath",
    "storageref",
    "responsebody",
    "artifactbody",
}


class AndroidViewScenarioId(str, Enum):
    """Stable browser campaign scenario order."""

    POSITIVE = "real_android_positive"
    CONTROLLED_FAIL = "real_android_controlled_fail"


class BrowserSurface(str, Enum):
    """Allowlisted product surfaces retained in the browser ledger."""

    CATALOG = "catalog"
    COMPOSER = "composer"
    MONITOR = "monitor"
    REPORT = "report"
    EVIDENCE = "evidence"
    REPLAY = "replay"
    EXPORT = "export"


REQUIRED_SCENARIOS = tuple(AndroidViewScenarioId)
_StartedT = TypeVar("_StartedT")


def _assert_safe_text(value: str, *, field: str, limit: int = MAX_TEXT) -> str:
    """Reject host authority, controls, secrets, and unbounded browser text.

    Args:
        value: Candidate retained text.
        field: Reader-facing diagnostic label.
        limit: Maximum accepted Unicode code-point count.

    Raises:
        ValueError: Text is unsafe or exceeds the declared bound.

    Returns:
        The unchanged validated text.
    """
    if not value or len(value) > limit:
        raise ValueError(f"{field} must contain 1..{limit} characters")
    if any(ord(character) < 32 and character not in "\t" for character in value):
        raise ValueError(f"{field} contains control characters")
    if _HOST_ABSOLUTE_PATH.search(value):
        raise ValueError(f"{field} contains a host absolute path")
    lowered = value.lower()
    if (
        "adb -s " in lowered
        or "object at 0x" in lowered
        or "file://" in lowered
        or _SECRET_SHAPE.search(value)
    ):
        raise ValueError(f"{field} contains private runtime authority")
    return value


def _assert_safe_route(value: str, *, field: str = "browser route") -> str:
    """Require one bounded product route without host or private query data.

    Args:
        value: Candidate route beginning at the product root.
        field: Reader-facing diagnostic label.

    Raises:
        ValueError: Route is outside the accepted Studio path grammar.

    Returns:
        The unchanged validated route.
    """
    _assert_safe_text(value, field=field, limit=MAX_ROUTE)
    if not _SAFE_ROUTE.fullmatch(value):
        raise ValueError(f"{field} is not an allowlisted Studio route")
    return value


def _assert_safe_json(value: Any, *, field: str = "browser evidence") -> None:
    """Recursively reject private keys, bodies, paths, and live objects.

    Args:
        value: Candidate JSON-compatible evidence.
        field: Reader-facing diagnostic label.

    Raises:
        ValueError: Evidence crosses the bounded public proof boundary.

    Returns:
        None.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in _PRIVATE_KEYS:
                raise ValueError(f"{field} contains forbidden private field")
            _assert_safe_text(str(key), field=f"{field} key", limit=160)
            _assert_safe_json(item, field=field)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _assert_safe_json(item, field=field)
        return
    if isinstance(value, str):
        _assert_safe_text(value, field=field)
        return
    if isinstance(value, (bytes, bytearray, memoryview)):
        raise ValueError(f"{field} must not contain retained response bytes")
    if value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError(f"{field} contains a live or non-JSON value")


def _sha256_bytes(value: bytes) -> str:
    """Return one prefixed lowercase SHA-256 digest.

    Args:
        value: Bytes whose exact identity is required.

    Returns:
        Prefixed deterministic digest.
    """
    return "sha256:" + hashlib.sha256(value).hexdigest()


class BrowserPrerequisiteScenario(BaseModel):
    """Causal C-1 scenario identities accepted by the C-2 launcher."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    scenario_id: AndroidServiceScenarioId = Field(alias="scenarioId")
    agent_id: StrictStr = Field(alias="agentId")
    agent_revision_id: StrictStr = Field(alias="agentRevisionId")
    source_effect_count: StrictInt = Field(alias="sourceEffectCount", ge=3, le=10000)

    @field_validator("agent_id", "agent_revision_id")
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Require one safe stable Agent identity.

        Args:
            value: Candidate Agent or revision identity.

        Raises:
            ValueError: Identity is not stable and bounded.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("prerequisite Agent identity is invalid")
        return value


class BrowserPrerequisiteEvidence(BaseModel):
    """Machine-checkable receipt proving C-1 passed before C-2 effects."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    service_campaign_version: StrictStr = Field(alias="serviceCampaignVersion")
    service_summary_sha256: StrictStr = Field(alias="serviceSummarySha256")
    selection: SafeAcceptanceSelection
    scenarios: tuple[BrowserPrerequisiteScenario, ...] = Field(
        min_length=2,
        max_length=2,
    )
    managed_closure_verified: StrictBool = Field(alias="managedClosureVerified")
    restart_non_replay_verified: StrictBool = Field(alias="restartNonReplayVerified")
    redaction_verified: StrictBool = Field(alias="redactionVerified")
    completion: StrictStr = Field(pattern=r"^passed$")

    @model_validator(mode="after")
    def _complete_prerequisite(self) -> Self:
        """Require exact C-1 version, scenarios, and completion gates.

        Raises:
            ValueError: The prerequisite is incomplete or from another campaign.

        Returns:
            Validated prerequisite receipt.
        """
        if self.service_campaign_version != SERVICE_CAMPAIGN_VERSION:
            raise ValueError("unsupported Stage 5.6C-1 campaign")
        if not _DIGEST.fullmatch(self.service_summary_sha256):
            raise ValueError("C-1 summary digest is invalid")
        if tuple(item.scenario_id for item in self.scenarios) != SERVICE_SCENARIOS:
            raise ValueError("C-1 prerequisite scenarios are incomplete or reordered")
        if len({item.agent_revision_id for item in self.scenarios}) != 2:
            raise ValueError("C-1 prerequisite requires two immutable revisions")
        if not (
            self.managed_closure_verified
            and self.restart_non_replay_verified
            and self.redaction_verified
        ):
            raise ValueError("C-1 prerequisite completion gates are not all verified")
        return self


class BrowserDeviceCheck(BaseModel):
    """One safe device-context fact retained from authoritative TaskResult."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: StrictStr = Field(pattern=r"^(platform|locale|orientation|apps)$")
    passed: StrictBool
    observed: StrictStr

    @field_validator("observed")
    @classmethod
    def _safe_observed(cls, value: str) -> str:
        """Bound retained device-check copy.

        Args:
            value: Candidate safe public observation.

        Raises:
            ValueError: Observation contains private or unbounded text.

        Returns:
            Validated observation.
        """
        return _assert_safe_text(value, field="device check", limit=160)


class BrowserProvenanceEvidence(BaseModel):
    """Independent acquisition, environment, profile, and device-check facts."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    origin: SafeEvidenceOrigin
    device_profile_id: StrictStr | None = Field(alias="deviceProfileId")
    device_checks: tuple[BrowserDeviceCheck, ...] = Field(
        alias="deviceChecks",
        max_length=4,
    )

    @field_validator("device_profile_id")
    @classmethod
    def _safe_profile_id(cls, value: str | None) -> str | None:
        """Require a safe public profile identity when present.

        Args:
            value: Candidate safe profile ID or ``None``.

        Raises:
            ValueError: Profile identity is malformed.

        Returns:
            Validated profile identity.
        """
        if value is not None and not _STABLE_ID.fullmatch(value):
            raise ValueError("deviceProfileId is invalid")
        return value

    @model_validator(mode="after")
    def _unique_checks(self) -> Self:
        """Reject duplicated check labels.

        Raises:
            ValueError: A check name appears more than once.

        Returns:
            Validated provenance evidence.
        """
        if len({item.name for item in self.device_checks}) != len(self.device_checks):
            raise ValueError("deviceChecks contains duplicate names")
        return self


class BrowserOutcomeAxes(BaseModel):
    """Independent terminal service, Agent, Benchmark, and evaluator facts."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    experiment_lifecycle: StrictStr = Field(alias="experimentLifecycle")
    experiment_terminal_reason: StrictStr = Field(alias="experimentTerminalReason")
    task_run_lifecycle: StrictStr = Field(alias="taskRunLifecycle")
    task_run_terminal_reason: StrictStr = Field(alias="taskRunTerminalReason")
    agent_status: StrictStr = Field(alias="agentStatus")
    benchmark_outcome: StrictStr = Field(alias="benchmarkOutcome")
    evaluator_pass: StrictBool = Field(alias="evaluatorPass")
    invalid_count: StrictInt = Field(alias="invalidCount", ge=0, le=1)


class BrowserCausalIdentities(BaseModel):
    """Exact causal resource identities joined across the browser journey."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    experiment_id: StrictStr = Field(alias="experimentId")
    task_run_id: StrictStr = Field(alias="taskRunId")
    core_task_run_id: StrictStr = Field(alias="coreTaskRunId")
    agent_run_id: StrictStr = Field(alias="agentRunId")
    agent_id: StrictStr = Field(alias="agentId")
    agent_revision_id: StrictStr = Field(alias="agentRevisionId")
    replay_id: StrictStr = Field(alias="replayId")
    report_route: StrictStr = Field(alias="reportRoute")
    replay_route: StrictStr = Field(alias="replayRoute")

    @field_validator(
        "experiment_id",
        "task_run_id",
        "core_task_run_id",
        "agent_run_id",
        "agent_id",
        "agent_revision_id",
        "replay_id",
    )
    @classmethod
    def _stable_identity(cls, value: str) -> str:
        """Require one bounded opaque resource identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is unsafe or unstable.

        Returns:
            Validated identity.
        """
        if not _STABLE_ID.fullmatch(value):
            raise ValueError("browser causal identity is invalid")
        return value

    @field_validator("report_route", "replay_route")
    @classmethod
    def _product_route(cls, value: str) -> str:
        """Require one safe product route.

        Args:
            value: Candidate Report or Replay route.

        Raises:
            ValueError: Route is outside Studio.

        Returns:
            Validated route.
        """
        return _assert_safe_route(value)


class BrowserEventContinuity(BaseModel):
    """Durable cursor continuity and non-reexecution facts."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    committed_cursor: StrictInt = Field(alias="committedCursor", ge=1)
    reconnect_cursor: StrictInt = Field(alias="reconnectCursor", ge=1)
    terminal_high_water: StrictInt = Field(alias="terminalHighWater", ge=1)
    observed_event_ids: tuple[StrictInt, ...] = Field(
        alias="observedEventIds",
        min_length=1,
        max_length=MAX_EVENTS,
    )
    last_event_id_used: StrictBool = Field(alias="lastEventIdUsed")
    terminal_drain_verified: StrictBool = Field(alias="terminalDrainVerified")
    initializer_count: StrictInt = Field(alias="initializerCount", ge=1, le=1)
    agent_count: StrictInt = Field(alias="agentCount", ge=1, le=1)
    evaluator_count: StrictInt = Field(alias="evaluatorCount", ge=1, le=1)
    worker_source_count: StrictInt = Field(alias="workerSourceCount", ge=1, le=1)
    source_effect_count_before_reload: StrictInt = Field(
        alias="sourceEffectCountBeforeReload",
        ge=4,
    )
    source_effect_count_after_reload: StrictInt = Field(
        alias="sourceEffectCountAfterReload",
        ge=4,
    )

    @model_validator(mode="after")
    def _continuous_and_non_replaying(self) -> Self:
        """Require gap-free unique events and stable effect counts.

        Raises:
            ValueError: Recovery has a gap, duplicate, or source replay.

        Returns:
            Validated continuity evidence.
        """
        if not self.last_event_id_used or not self.terminal_drain_verified:
            raise ValueError("SSE recovery or terminal drain is unverified")
        if self.committed_cursor > self.reconnect_cursor:
            raise ValueError("reconnect cursor precedes committed browser cursor")
        if self.reconnect_cursor > self.terminal_high_water:
            raise ValueError("reconnect cursor exceeds terminal high-water mark")
        if tuple(sorted(self.observed_event_ids)) != self.observed_event_ids:
            raise ValueError("observed event identities are not ordered")
        if len(set(self.observed_event_ids)) != len(self.observed_event_ids):
            raise ValueError("observed events contain a duplicate identity")
        expected = tuple(
            range(self.observed_event_ids[0], self.terminal_high_water + 1)
        )
        if self.observed_event_ids != expected:
            raise ValueError("observed events do not close the terminal cursor range")
        if self.source_effect_count_after_reload != self.source_effect_count_before_reload:
            raise ValueError("browser recovery triggered a second source effect")
        return self


class BrowserArtifactFact(BaseModel):
    """Safe metadata-only managed artifact observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    artifact_id: StrictStr = Field(alias="artifactId")
    task_run_id: StrictStr | None = Field(alias="taskRunId")
    kind: StrictStr
    availability: StrictStr
    exact_scope_verified: StrictBool = Field(alias="exactScopeVerified")
    head_verified: StrictBool = Field(alias="headVerified")

    @field_validator("artifact_id", "task_run_id", "kind", "availability")
    @classmethod
    def _safe_fact(cls, value: str | None) -> str | None:
        """Require path-free bounded artifact metadata.

        Args:
            value: Candidate artifact fact or ``None``.

        Raises:
            ValueError: Fact is unsafe or unbounded.

        Returns:
            Validated fact.
        """
        if value is not None:
            _assert_safe_text(value, field="artifact fact", limit=256)
        return value


class BrowserSurfaceFacts(BaseModel):
    """Required Report, Evidence, Replay, and Export observations."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    evaluation_visible: StrictBool = Field(alias="evaluationVisible")
    evidence_exact_scope: StrictBool = Field(alias="evidenceExactScope")
    replay_reloaded: StrictBool = Field(alias="replayReloaded")
    replay_read_only: StrictBool = Field(alias="replayReadOnly")
    export_prepared: StrictBool = Field(alias="exportPrepared")
    export_handed_off: StrictBool = Field(alias="exportHandedOff")
    export_completion_claimed: StrictBool = Field(alias="exportCompletionClaimed")

    @model_validator(mode="after")
    def _required_surface_gates(self) -> Self:
        """Require bounded surface checks without a download-completion claim.

        Raises:
            ValueError: A required surface is missing or overclaims handoff.

        Returns:
            Validated surface facts.
        """
        if not all(
            (
                self.evaluation_visible,
                self.evidence_exact_scope,
                self.replay_reloaded,
                self.replay_read_only,
                self.export_prepared,
                self.export_handed_off,
            )
        ):
            raise ValueError("one or more browser surface gates are incomplete")
        if self.export_completion_claimed:
            raise ValueError("browser handoff must not claim download completion")
        return self


class BrowserObservation(BaseModel):
    """One bounded DOM or route assertion without raw page content."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    surface: BrowserSurface
    route: StrictStr
    assertion: StrictStr
    verification: StrictStr = Field(pattern=r"^passed$")
    screenshot_reference: StrictStr | None = Field(
        default=None,
        alias="screenshotReference",
    )

    @field_validator("route")
    @classmethod
    def _safe_product_route(cls, value: str) -> str:
        """Validate the observed URL-owned product route.

        Args:
            value: Candidate product route.

        Raises:
            ValueError: Route is unsafe.

        Returns:
            Validated route.
        """
        return _assert_safe_route(value)

    @field_validator("assertion", "screenshot_reference")
    @classmethod
    def _safe_observation(cls, value: str | None) -> str | None:
        """Bound retained DOM copy and screenshot references.

        Args:
            value: Candidate safe observation or ``None``.

        Raises:
            ValueError: Observation contains private authority.

        Returns:
            Validated observation.
        """
        if value is not None:
            _assert_safe_text(value, field="browser observation", limit=MAX_TEXT)
        return value


class BrowserNetworkObservation(BaseModel):
    """Metadata-only local network observation with no response body."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    method: StrictStr = Field(pattern=r"^(GET|HEAD|POST|DELETE)$")
    route: StrictStr
    status: StrictInt = Field(ge=100, le=599)
    content_type: StrictStr | None = Field(alias="contentType")

    @field_validator("route")
    @classmethod
    def _safe_product_route(cls, value: str) -> str:
        """Validate one retained local resource route.

        Args:
            value: Candidate resource route.

        Raises:
            ValueError: Route is unsafe.

        Returns:
            Validated route.
        """
        return _assert_safe_route(value, field="network route")

    @field_validator("content_type")
    @classmethod
    def _safe_content_type(cls, value: str | None) -> str | None:
        """Bound optional media-type metadata.

        Args:
            value: Media type or ``None``.

        Raises:
            ValueError: Value contains unsafe text.

        Returns:
            Validated media type.
        """
        if value is not None:
            _assert_safe_text(value, field="content type", limit=160)
        return value


class BrowserSecurityEvidence(BaseModel):
    """Bounded browser/ledger redaction and diagnostics result."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    console_observations: tuple[StrictStr, ...] = Field(
        alias="consoleObservations",
        max_length=MAX_OBSERVATIONS,
    )
    network_observations: tuple[BrowserNetworkObservation, ...] = Field(
        alias="networkObservations",
        max_length=MAX_NETWORK_OBSERVATIONS,
    )
    screenshot_references: tuple[StrictStr, ...] = Field(
        alias="screenshotReferences",
        max_length=MAX_SCREENSHOTS,
    )
    scanned_documents: StrictInt = Field(
        alias="scannedDocuments",
        ge=1,
        le=MAX_SCAN_DOCUMENTS,
    )
    private_values_found: StrictInt = Field(alias="privateValuesFound", ge=0, le=0)

    @field_validator("console_observations", "screenshot_references")
    @classmethod
    def _safe_collection(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Validate bounded console and screenshot metadata.

        Args:
            values: Candidate safe retained strings.

        Raises:
            ValueError: Any string contains private authority.

        Returns:
            Validated tuple.
        """
        for value in values:
            _assert_safe_text(value, field="browser security evidence")
        return values


class BrowserCommandEvidence(BaseModel):
    """One reproducible path-free command and observed gate."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    suite_id: StrictStr = Field(alias="suiteId")
    command: StrictStr
    observed: StrictStr
    verification: StrictStr = Field(pattern=r"^passed$")

    @field_validator("suite_id", "command", "observed")
    @classmethod
    def _safe_command_text(cls, value: str) -> str:
        """Reject host-specific or secret-bearing command evidence.

        Args:
            value: Candidate command field.

        Raises:
            ValueError: Text is unsafe.

        Returns:
            Validated text.
        """
        return _assert_safe_text(value, field="browser command evidence")


class AndroidViewScenarioEvidence(BaseModel):
    """Complete browser proof for one positive or controlled-negative run."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    scenario_id: AndroidViewScenarioId = Field(alias="scenarioId")
    verification: StrictStr = Field(pattern=r"^passed$")
    identities: BrowserCausalIdentities
    outcome: BrowserOutcomeAxes
    source_provenance: BrowserProvenanceEvidence = Field(alias="sourceProvenance")
    replay_provenance: BrowserProvenanceEvidence = Field(alias="replayProvenance")
    continuity: BrowserEventContinuity
    surfaces: BrowserSurfaceFacts
    artifacts: tuple[BrowserArtifactFact, ...] = Field(
        min_length=1,
        max_length=MAX_ARTIFACTS,
    )
    observations: tuple[BrowserObservation, ...] = Field(
        min_length=7,
        max_length=MAX_OBSERVATIONS,
    )

    @model_validator(mode="after")
    def _scenario_semantics(self) -> Self:
        """Enforce terminal axes, provenance, ownership, and surface coverage.

        Raises:
            ValueError: Scenario substitutes an infrastructure failure or drift.

        Returns:
            Validated scenario evidence.
        """
        outcome = self.outcome
        if (
            outcome.experiment_lifecycle != "terminal"
            or outcome.experiment_terminal_reason != "completed"
            or outcome.task_run_lifecycle != "terminal"
            or outcome.task_run_terminal_reason != "completed"
            or outcome.agent_status != "success"
            or outcome.invalid_count != 0
        ):
            raise ValueError("browser scenario lacks normal terminal Agent completion")
        positive = self.scenario_id is AndroidViewScenarioId.POSITIVE
        if (
            outcome.benchmark_outcome != ("pass" if positive else "fail")
            or outcome.evaluator_pass is not positive
        ):
            raise ValueError("browser outcome axes do not match the fixed scenario")
        if self.source_provenance.origin.model_dump(by_alias=True) != {
            "acquisition": "fresh_execution",
            "environment": "real_android",
            "realDeviceEvidence": True,
        }:
            raise ValueError("browser source result lacks fresh real provenance")
        if self.replay_provenance.origin.model_dump(by_alias=True) != {
            "acquisition": "replay_projection",
            "environment": "real_android",
            "realDeviceEvidence": False,
        }:
            raise ValueError("browser Replay lacks historical real-source provenance")
        if self.source_provenance.device_profile_id is None:
            raise ValueError("fresh source provenance lacks safe profile identity")
        if self.replay_provenance.device_profile_id != self.source_provenance.device_profile_id:
            raise ValueError("Replay source profile identity drifted")
        if any(item.task_run_id not in (None, self.identities.task_run_id) for item in self.artifacts):
            raise ValueError("artifact inventory crosses the selected TaskRun")
        if not all(item.exact_scope_verified for item in self.artifacts):
            raise ValueError("one or more managed artifacts lack exact scope")
        if set(item.surface for item in self.observations) != set(BrowserSurface):
            raise ValueError("browser journey does not cover every required surface")
        return self


class StudioBenchmarkAndroidViewAcceptanceSummaryV1(BaseModel):
    """Complete Stage 5.6C-2 bounded real-browser proof ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: StrictInt = Field(default=SUMMARY_SCHEMA_VERSION, alias="schemaVersion")
    campaign_version: StrictStr = Field(default=CAMPAIGN_VERSION, alias="campaignVersion")
    prerequisite: BrowserPrerequisiteEvidence
    scenarios: tuple[AndroidViewScenarioEvidence, ...] = Field(
        min_length=2,
        max_length=2,
    )
    fake_fixture_provenance: BrowserProvenanceEvidence = Field(
        alias="fakeFixtureProvenance"
    )
    security: BrowserSecurityEvidence
    commands: tuple[BrowserCommandEvidence, ...] = Field(
        min_length=1,
        max_length=MAX_COMMANDS,
    )
    claim_limits: tuple[StrictStr, ...] = Field(alias="claimLimits")

    @model_validator(mode="after")
    def _complete_campaign(self) -> Self:
        """Require both scenarios, exact C-1 joins, triad, and claim limits.

        Raises:
            ValueError: Browser evidence is incomplete, cross-owned, or overclaims.

        Returns:
            Complete validated browser proof ledger.
        """
        if self.schema_version != SUMMARY_SCHEMA_VERSION:
            raise ValueError("unsupported Android view summary schema")
        if self.campaign_version != CAMPAIGN_VERSION:
            raise ValueError("unknown Android view acceptance campaign")
        if tuple(item.scenario_id for item in self.scenarios) != REQUIRED_SCENARIOS:
            raise ValueError("required browser scenarios must be stable and complete")
        if self.claim_limits != REQUIRED_CLAIM_LIMITS:
            raise ValueError("Stage 5.6C-2 claim limits changed")
        expected_agents = {
            item.scenario_id.value: (item.agent_id, item.agent_revision_id)
            for item in self.prerequisite.scenarios
        }
        profile_id = self.prerequisite.selection.device_profile_id
        for scenario in self.scenarios:
            if (
                scenario.identities.agent_id,
                scenario.identities.agent_revision_id,
            ) != expected_agents[scenario.scenario_id.value]:
                raise ValueError("browser Agent selection conflicts with C-1 evidence")
            if scenario.source_provenance.device_profile_id != profile_id:
                raise ValueError("browser profile selection conflicts with C-1 evidence")
        experiments = {item.identities.experiment_id for item in self.scenarios}
        task_runs = {item.identities.task_run_id for item in self.scenarios}
        if len(experiments) != 2 or len(task_runs) != 2:
            raise ValueError("browser scenarios require distinct Experiment/TaskRun resources")
        if self.fake_fixture_provenance.origin.model_dump(by_alias=True) != {
            "acquisition": "contract_fixture",
            "environment": "fake_device",
            "realDeviceEvidence": False,
        }:
            raise ValueError("supporting fixture provenance is not explicitly fake")
        _assert_safe_json(
            self.model_dump(mode="json", by_alias=True),
            field="Android view acceptance summary",
        )
        return self

    def canonical_json(self) -> str:
        """Return deterministic compact JSON for disposable evidence.

        Returns:
            Canonical sorted JSON without host-dependent whitespace.
        """
        return json.dumps(
            self.model_dump(mode="json", by_alias=True),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )


def validate_prerequisite_file(path: str | Path) -> BrowserPrerequisiteEvidence:
    """Validate C-1 completely and return a bounded C-2 prerequisite receipt.

    This function is the first operation required by the real C-2 launcher.  A
    caller must not resolve a profile, start a server/browser/Worker, or touch a
    device before it returns successfully.

    Args:
        path: Existing strict Stage 5.6C-1 summary path.

    Raises:
        OSError: The summary cannot be read.
        ValueError: JSON or any C-1 completion gate is invalid.

    Returns:
        Safe receipt joined to the exact canonical C-1 summary digest.
    """
    summary = validate_service_summary_file(path)
    canonical = summary.canonical_json().encode("utf-8")
    return prerequisite_from_service_summary(summary, canonical_bytes=canonical)


def start_after_prerequisite(
    *,
    confirm_real_android: bool,
    service_summary: str | Path,
    device_profile_id: str,
    starter: Callable[[BrowserPrerequisiteEvidence], _StartedT],
) -> _StartedT:
    """Invoke a browser/backend/device starter only after the strict C-1 gate.

    The callback owns profile configuration loading, profile resolution,
    browser/server/Worker startup, and all Android effects.  Keeping those
    operations behind one callback makes the ordering observable in no-device
    tests and prevents partial launch when prerequisite evidence is absent.

    Args:
        confirm_real_android: Explicit operator acknowledgement of real effects.
        service_summary: Existing strict C-1 summary path.
        device_profile_id: Requested safe public profile identity.
        starter: Effectful callback invoked only after every gate passes.

    Raises:
        ValueError: Confirmation, prerequisite, or selected profile is invalid.
        OSError: The prerequisite summary cannot be read.

    Returns:
        The effectful starter's result.
    """
    if not confirm_real_android:
        raise ValueError("explicit real-Android confirmation is required")
    receipt = validate_prerequisite_file(service_summary)
    if not _STABLE_ID.fullmatch(device_profile_id):
        raise ValueError("requested deviceProfileId is invalid")
    if device_profile_id != receipt.selection.device_profile_id:
        raise ValueError("requested profile conflicts with C-1 selection")
    return starter(receipt)


def prerequisite_from_service_summary(
    summary: StudioBenchmarkAndroidServiceAcceptanceSummaryV1,
    *,
    canonical_bytes: bytes | None = None,
) -> BrowserPrerequisiteEvidence:
    """Project one already validated C-1 summary into a safe receipt.

    Args:
        summary: Strict complete Stage 5.6C-1 summary.
        canonical_bytes: Optional exact canonical bytes for digesting.

    Raises:
        ValueError: A completion fact cannot be projected safely.

    Returns:
        Complete bounded prerequisite receipt.
    """
    payload = canonical_bytes or summary.canonical_json().encode("utf-8")
    scenarios = tuple(
        BrowserPrerequisiteScenario(
            scenarioId=item.scenario_id,
            agentId=item.identities.agent_id,
            agentRevisionId=item.identities.agent_revision_id,
            sourceEffectCount=item.restart.source_effect_count_after,
        )
        for item in summary.scenarios
    )
    return BrowserPrerequisiteEvidence(
        serviceCampaignVersion=summary.campaign_version,
        serviceSummarySha256=_sha256_bytes(payload),
        selection=summary.selection,
        scenarios=scenarios,
        managedClosureVerified=all(
            item.publication.report_get_head_verified
            and item.publication.bundle_get_head_verified
            and item.publication.replay_resource_verified
            and item.publication.replay_bundle_verified
            for item in summary.scenarios
        ),
        restartNonReplayVerified=all(
            item.restart.identities_stable
            and item.restart.event_high_water_stable
            and item.restart.unique_terminal_event
            and item.restart.source_effect_count_before
            == item.restart.source_effect_count_after
            and item.restart.restart_media_added_count == 0
            for item in summary.scenarios
        ),
        redactionVerified=summary.private_values_found == 0,
        completion="passed",
    )


def validate_summary_file(
    path: str | Path,
) -> StudioBenchmarkAndroidViewAcceptanceSummaryV1:
    """Read and strictly validate one Stage 5.6C-2 proof ledger.

    Args:
        path: Existing summary JSON path.

    Raises:
        OSError: The file cannot be read.
        ValueError: JSON or the strict browser contract is invalid.

    Returns:
        Validated Android browser acceptance summary.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return StudioBenchmarkAndroidViewAcceptanceSummaryV1.model_validate(payload)


def write_summary(
    summary: StudioBenchmarkAndroidViewAcceptanceSummaryV1,
    path: str | Path,
    *,
    forbidden_values: Sequence[str] = (),
) -> Path:
    """Write one redaction-checked summary to an explicit destination.

    Args:
        summary: Complete validated proof ledger.
        path: Explicit disposable destination.
        forbidden_values: Runtime private canaries that must remain absent.

    Raises:
        OSError: Parent or destination cannot be written.
        ValueError: A private canary occurs in the canonical ledger.

    Returns:
        Resolved written path.
    """
    canonical = summary.canonical_json()
    assert_forbidden_values_absent(
        canonical,
        forbidden_values=forbidden_values,
        field="Android view acceptance summary",
    )
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(canonical + "\n", encoding="utf-8")
    return destination


def _parser() -> argparse.ArgumentParser:
    """Build the narrow prerequisite/ledger validation command parser.

    Returns:
        Configured acceptance-only command parser.
    """
    parser = argparse.ArgumentParser(
        description="Validate Stage 5.6C-2 Android browser acceptance evidence."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    prerequisite = subcommands.add_parser(
        "validate-prerequisite",
        help="validate one complete C-1 summary before browser/device effects",
    )
    prerequisite.add_argument("summary", type=Path)
    validate = subcommands.add_parser("validate", help="validate one C-2 ledger")
    validate.add_argument("summary", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate one C-1 prerequisite or one completed C-2 ledger.

    Args:
        argv: Optional arguments excluding the executable name.

    Raises:
        OSError: Requested evidence cannot be read.
        ValueError: Evidence violates the strict contract.

    Returns:
        Zero only after the requested validation succeeds.
    """
    args = _parser().parse_args(argv)
    if args.command == "validate-prerequisite":
        receipt = validate_prerequisite_file(args.summary)
        output = {
            "schemaVersion": SUMMARY_SCHEMA_VERSION,
            "serviceCampaignVersion": receipt.service_campaign_version,
            "scenarioCount": len(receipt.scenarios),
            "verification": receipt.completion,
            "realDeviceEvidence": True,
        }
    else:
        summary = validate_summary_file(args.summary)
        output = {
            "schemaVersion": summary.schema_version,
            "campaignVersion": summary.campaign_version,
            "scenarioCount": len(summary.scenarios),
            "verification": "passed",
            "realDeviceEvidence": True,
        }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
