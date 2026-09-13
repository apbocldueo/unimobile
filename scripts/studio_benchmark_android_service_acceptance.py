#!/usr/bin/env python3
"""Run and validate bounded Stage 5.6C-1 Android service acceptance.

The command is deliberately outside the product package.  It drives the
production Studio Benchmark composition, but its proof ledger is disposable
validation evidence rather than a new public DTO, database table, or lifecycle.
"""

from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
import hashlib
import http.client
import json
from pathlib import Path
import re
import sys
import threading
import time
from typing import Any, Mapping, Sequence
import zipfile

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


SUMMARY_SCHEMA_VERSION = 1
CAMPAIGN_VERSION = "studio-benchmark-android-service-5.6c1-v1"
PACKAGE_IDENTITY = "zhixing/android-world@1.0.0"
TASK_ID = "AndroidWorld_6"
SPLIT = "test"
PROTOCOL_SEED = 42
MAX_ARTIFACTS = 256
MAX_EVENTS = 500
MAX_COMMANDS = 32
MAX_TEXT = 1000
MAX_SCAN_DOCUMENTS = 1024
REQUIRED_ARTIFACT_KINDS = (
    "experiment_report",
    "task_report",
    "task_trajectory",
    "studio_publication_manifest",
    "experiment_bundle",
)
REQUIRED_CLAIM_LIMITS = (
    "Evidence is limited to the selected profile, Android context, Package, "
    "task, Protocol, Agent revisions, and one repeat.",
    "No broad Android compatibility, arbitrary task success, model quality, "
    "or statistical significance is claimed.",
    "Studio Worker remains limited to 1 Agent x 1 Task x 1 repeat.",
    "Browser-level real Android acceptance remains Stage 5.6C-2.",
)

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,255}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s\"'(])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\s\"']+)"
)
_SAFE_ABSOLUTE_PREFIXES = (
    "/api/studio/",
    "/studio/",
    "/data/",
    "/storage/emulated/",
    "/sdcard/",
)
_PRIVATE_KEYS = {
    "serial",
    "adbserial",
    "deviceserial",
    "rawserial",
    "configpath",
    "configurationpath",
    "bindingfingerprint",
    "privatefingerprint",
    "targetkey",
    "apikey",
    "password",
    "devicehandle",
    "livecomponent",
    "hostpath",
    "storageref",
}


class AndroidServiceScenarioId(str, Enum):
    """Stable required real-Android scenario order."""

    POSITIVE = "real_android_positive"
    CONTROLLED_FAIL = "real_android_controlled_fail"


REQUIRED_SCENARIOS = tuple(AndroidServiceScenarioId)


def _contains_host_absolute_path(value: str) -> bool:
    """Distinguish host paths from public service and Android-device paths.

    Args:
        value: Candidate evidence text.

    Returns:
        ``True`` when an absolute path is not an accepted service/device path.
    """
    for match in _ABSOLUTE_PATH.finditer(value):
        candidate = match.group(0).lstrip(" \t\"'(")
        if candidate.startswith(_SAFE_ABSOLUTE_PREFIXES):
            continue
        return True
    return False


def _assert_safe_string(value: str, *, field: str) -> str:
    """Reject host paths, control data, raw ADB commands, and secret-shaped text.

    Args:
        value: Candidate public evidence text.
        field: Reader-facing diagnostic label.

    Raises:
        ValueError: Text is unsafe or unbounded.

    Returns:
        The unchanged validated string.
    """
    if len(value) > MAX_TEXT:
        raise ValueError(f"{field} exceeds the text bound")
    if any(
        ord(character) < 32 and character not in "\t\r\n"
        for character in value
    ):
        raise ValueError(f"{field} contains control characters")
    if _contains_host_absolute_path(value):
        raise ValueError(f"{field} contains a host absolute path")
    lowered = value.lower()
    if "adb -s " in lowered or "object at 0x" in lowered:
        raise ValueError(f"{field} contains private runtime authority")
    if re.search(r"\b(?:sk|api)[-_][A-Za-z0-9_-]{12,}\b", value):
        raise ValueError(f"{field} contains secret-shaped text")
    return value


def _assert_safe_json(value: Any, *, field: str = "acceptance evidence") -> None:
    """Recursively reject private keys, bytes, paths, and live objects.

    Args:
        value: Candidate JSON-compatible evidence.
        field: Reader-facing diagnostic label.

    Raises:
        ValueError: A key or value crosses the public evidence boundary.

    Returns:
        None.
    """
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
            if normalized in _PRIVATE_KEYS:
                raise ValueError(f"{field} contains forbidden private field")
            _assert_safe_string(str(key), field=f"{field} key")
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
        raise ValueError(f"{field} contains a live or non-JSON value")


def assert_forbidden_values_absent(
    value: Any,
    *,
    forbidden_values: Sequence[str],
    field: str,
) -> None:
    """Scan serialized evidence for exact private values supplied at runtime.

    Args:
        value: JSON-compatible value or text/bytes to inspect.
        forbidden_values: Exact private canaries that must not occur.
        field: Reader-facing evidence label.

    Raises:
        ValueError: A non-empty private value is present.

    Returns:
        None.
    """
    if isinstance(value, bytes):
        payload = value
    elif isinstance(value, str):
        payload = value.encode("utf-8", errors="replace")
    else:
        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    for forbidden in forbidden_values:
        if forbidden and forbidden.encode("utf-8") in payload:
            raise ValueError(f"{field} contains forbidden private value")


class SafeAcceptanceSelection(BaseModel):
    """Safe immutable inputs shared by both real-Android Experiments."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    device_profile_id: StrictStr = Field(alias="deviceProfileId")
    package_identity: StrictStr = Field(
        default=PACKAGE_IDENTITY,
        alias="packageIdentity",
    )
    task_id: StrictStr = Field(default=TASK_ID, alias="taskId")
    split: StrictStr = SPLIT
    protocol_seed: StrictInt = Field(default=PROTOCOL_SEED, alias="protocolSeed")
    repeats: StrictInt = Field(default=1, ge=1, le=1)
    locale: StrictStr = "en-US"
    orientation: StrictStr = "portrait"

    @field_validator(
        "device_profile_id",
        "package_identity",
        "task_id",
        "split",
        "locale",
        "orientation",
    )
    @classmethod
    def _safe_selection_text(cls, value: str) -> str:
        """Validate path-free bounded selected identities and context.

        Args:
            value: Candidate selection text.

        Raises:
            ValueError: Text is unsafe.

        Returns:
            Validated text.
        """
        _assert_safe_string(value, field="acceptance selection")
        return value

    @model_validator(mode="after")
    def _fixed_matrix(self) -> Self:
        """Require the accepted first service-level Android matrix.

        Raises:
            ValueError: Package, task, split, Protocol, or context drifts.

        Returns:
            Validated fixed selection.
        """
        if self.package_identity != PACKAGE_IDENTITY:
            raise ValueError("5.6C-1 requires the built-in AndroidWorld Package")
        if self.task_id != TASK_ID or self.split != SPLIT:
            raise ValueError("5.6C-1 requires AndroidWorld_6 from test split")
        if self.protocol_seed != PROTOCOL_SEED:
            raise ValueError("5.6C-1 requires Protocol seed 42")
        if self.locale != "en-US" or self.orientation != "portrait":
            raise ValueError("5.6C-1 requires en-US portrait context")
        return self


class SafeEvidenceOrigin(BaseModel):
    """One exact acquisition/environment claim used by the proof ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    acquisition: StrictStr
    environment: StrictStr
    real_device_evidence: StrictBool = Field(alias="realDeviceEvidence")

    @model_validator(mode="after")
    def _truthful_origin(self) -> Self:
        """Derive the real-evidence boolean from the two independent axes.

        Raises:
            ValueError: Typed axes and boolean disagree.

        Returns:
            Validated origin.
        """
        expected = (
            self.acquisition == "fresh_execution"
            and self.environment == "real_android"
        )
        if self.real_device_evidence != expected:
            raise ValueError("real-device evidence disagrees with source facts")
        return self


class AndroidDeviceDeltaEvidence(BaseModel):
    """Bounded independent MediaStore observation without row identities."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    collection: StrictStr = "media_images"
    method: StrictStr = "content_query_delta"
    added_count: StrictInt = Field(alias="addedCount", ge=0, le=1000)
    conclusive: StrictBool


class AndroidServiceOutcomeEvidence(BaseModel):
    """Independent terminal Agent, Benchmark, and evaluator facts."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    experiment_lifecycle: StrictStr = Field(alias="experimentLifecycle")
    experiment_terminal_reason: StrictStr = Field(alias="experimentTerminalReason")
    task_run_lifecycle: StrictStr = Field(alias="taskRunLifecycle")
    task_run_terminal_reason: StrictStr = Field(alias="taskRunTerminalReason")
    agent_status: StrictStr = Field(alias="agentStatus")
    benchmark_outcome: StrictStr = Field(alias="benchmarkOutcome")
    evaluator_pass: StrictBool = Field(alias="evaluatorPass")
    invalid_count: StrictInt = Field(alias="invalidCount", ge=0, le=1)


class AndroidServiceEffectCounters(BaseModel):
    """Bounded source-effect counts derived from authoritative result/events."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    initializer_count: StrictInt = Field(alias="initializerCount", ge=0, le=8)
    agent_count: StrictInt = Field(alias="agentCount", ge=0, le=8)
    evaluator_count: StrictInt = Field(alias="evaluatorCount", ge=0, le=8)
    action_count: StrictInt = Field(alias="actionCount", ge=0, le=100)

    @model_validator(mode="after")
    def _single_task_effects(self) -> Self:
        """Require one normal setup, Agent, and evaluator lifecycle.

        Raises:
            ValueError: The one-TaskRun matrix did not execute each stage once.

        Returns:
            Validated bounded effect counters.
        """
        if (
            self.initializer_count != 1
            or self.agent_count != 1
            or self.evaluator_count != 1
        ):
            raise ValueError("service scenario did not execute each source stage once")
        return self


class AndroidServiceCausalIdentities(BaseModel):
    """Safe authoritative identities spanning service through Replay."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    experiment_id: StrictStr = Field(alias="experimentId")
    planned_task_run_id: StrictStr = Field(alias="plannedTaskRunId")
    core_task_run_id: StrictStr = Field(alias="coreTaskRunId")
    agent_run_id: StrictStr = Field(alias="agentRunId")
    agent_id: StrictStr = Field(alias="agentId")
    agent_revision_id: StrictStr = Field(alias="agentRevisionId")
    agent_graph_identity: StrictStr = Field(alias="agentGraphIdentity")
    benchmark_plan_identity: StrictStr = Field(alias="benchmarkPlanIdentity")
    experiment_protocol_identity: StrictStr = Field(
        alias="experimentProtocolIdentity"
    )
    task_instance_identity: StrictStr = Field(alias="taskInstanceIdentity")
    replay_id: StrictStr = Field(alias="replayId")

    @field_validator("*")
    @classmethod
    def _opaque_identifiers(cls, value: str) -> str:
        """Reject blank, path-shaped, or unbounded causal identities.

        Args:
            value: Candidate public identity.

        Raises:
            ValueError: Identity is not safe and opaque.

        Returns:
            Validated identity.
        """
        _assert_safe_string(value, field="causal identity")
        if _STABLE_ID.fullmatch(value) is None and _DIGEST.fullmatch(value) is None:
            raise ValueError("causal identity must be stable and path-free")
        return value


class ManagedArtifactEvidence(BaseModel):
    """One exact managed member verified through GET and HEAD."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    artifact_id: StrictStr = Field(alias="artifactId")
    task_run_id: StrictStr | None = Field(default=None, alias="taskRunId")
    kind: StrictStr
    content_type: StrictStr = Field(alias="contentType")
    size: StrictInt = Field(ge=0)
    sha256: StrictStr
    get_verified: StrictBool = Field(alias="getVerified")
    head_verified: StrictBool = Field(alias="headVerified")

    @field_validator("artifact_id", "task_run_id", "kind", "content_type")
    @classmethod
    def _safe_metadata(cls, value: str | None) -> str | None:
        """Validate safe bounded artifact metadata.

        Args:
            value: Candidate optional descriptor field.

        Raises:
            ValueError: Field is unsafe.

        Returns:
            Validated field.
        """
        if value is not None:
            _assert_safe_string(value, field="artifact metadata")
        return value

    @field_validator("sha256")
    @classmethod
    def _artifact_digest(cls, value: str) -> str:
        """Require a prefixed SHA-256 artifact digest.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest syntax is invalid.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("managed artifact digest must be SHA-256")
        return value

    @model_validator(mode="after")
    def _read_closed(self) -> Self:
        """Require both exact transport methods to verify successfully.

        Raises:
            ValueError: GET or HEAD verification is absent.

        Returns:
            Closed artifact proof.
        """
        if not self.get_verified or not self.head_verified:
            raise ValueError("managed artifact requires exact GET and HEAD proof")
        return self


class ManagedPublicationEvidence(BaseModel):
    """Bounded complete managed publication and export closure."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    artifacts: tuple[ManagedArtifactEvidence, ...] = Field(
        min_length=1,
        max_length=MAX_ARTIFACTS,
    )
    report_get_head_verified: StrictBool = Field(alias="reportGetHeadVerified")
    bundle_get_head_verified: StrictBool = Field(alias="bundleGetHeadVerified")
    replay_resource_verified: StrictBool = Field(alias="replayResourceVerified")
    replay_bundle_verified: StrictBool = Field(alias="replayBundleVerified")

    @model_validator(mode="after")
    def _complete_publication(self) -> Self:
        """Require kinds, unique identities, and every aggregate resource.

        Raises:
            ValueError: Publication evidence is incomplete or ambiguous.

        Returns:
            Validated publication closure.
        """
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("managed artifact identities must be unique")
        kinds = {item.kind for item in self.artifacts}
        missing = set(REQUIRED_ARTIFACT_KINDS) - kinds
        if missing:
            raise ValueError("managed publication is missing required kinds")
        if not all(
            (
                self.report_get_head_verified,
                self.bundle_get_head_verified,
                self.replay_resource_verified,
                self.replay_bundle_verified,
            )
        ):
            raise ValueError("aggregate publication resources are incomplete")
        return self


class TerminalRestartEvidence(BaseModel):
    """Proof that terminal startup reconstructs without source effects."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    identities_stable: StrictBool = Field(alias="identitiesStable")
    event_high_water_stable: StrictBool = Field(alias="eventHighWaterStable")
    unique_terminal_event: StrictBool = Field(alias="uniqueTerminalEvent")
    source_effect_count_before: StrictInt = Field(alias="sourceEffectCountBefore", ge=0)
    source_effect_count_after: StrictInt = Field(alias="sourceEffectCountAfter", ge=0)
    restart_media_added_count: StrictInt = Field(
        alias="restartMediaAddedCount",
        ge=0,
        le=1000,
    )

    @model_validator(mode="after")
    def _no_replay(self) -> Self:
        """Require stable facts and zero additional source/device effects.

        Raises:
            ValueError: Restart changed identity, events, effects, or media.

        Returns:
            Validated terminal restart proof.
        """
        if not all(
            (
                self.identities_stable,
                self.event_high_water_stable,
                self.unique_terminal_event,
            )
        ):
            raise ValueError("terminal restart identities or events changed")
        if self.source_effect_count_after != self.source_effect_count_before:
            raise ValueError("terminal restart replayed a source effect")
        if self.restart_media_added_count != 0:
            raise ValueError("terminal restart changed Android device state")
        return self


class AndroidServiceScenarioEvidence(BaseModel):
    """Complete authoritative proof for one required real-Android scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    scenario_id: AndroidServiceScenarioId = Field(alias="scenarioId")
    verification: StrictStr = Field(pattern=r"^passed$")
    identities: AndroidServiceCausalIdentities
    outcome: AndroidServiceOutcomeEvidence
    effect_counters: AndroidServiceEffectCounters = Field(alias="effectCounters")
    device_delta: AndroidDeviceDeltaEvidence = Field(alias="deviceDelta")
    source_origin: SafeEvidenceOrigin = Field(alias="sourceOrigin")
    replay_origin: SafeEvidenceOrigin = Field(alias="replayOrigin")
    publication: ManagedPublicationEvidence
    restart: TerminalRestartEvidence

    @model_validator(mode="after")
    def _scenario_semantics(self) -> Self:
        """Enforce independent positive and controlled-negative semantics.

        Raises:
            ValueError: Outcome, device evidence, or provenance is wrong.

        Returns:
            Validated scenario evidence.
        """
        common = self.outcome
        if (
            common.experiment_lifecycle != "terminal"
            or common.experiment_terminal_reason != "completed"
            or common.task_run_lifecycle != "terminal"
            or common.task_run_terminal_reason != "completed"
            or common.agent_status != "success"
        ):
            raise ValueError("scenario did not complete with normal Agent success")
        if not self.device_delta.conclusive:
            raise ValueError("independent Android observation is inconclusive")
        if self.source_origin.model_dump(by_alias=True) != {
            "acquisition": "fresh_execution",
            "environment": "real_android",
            "realDeviceEvidence": True,
        }:
            raise ValueError("source result lacks fresh real-Android provenance")
        if self.replay_origin.model_dump(by_alias=True) != {
            "acquisition": "replay_projection",
            "environment": "real_android",
            "realDeviceEvidence": False,
        }:
            raise ValueError("Replay provenance does not preserve projection truth")
        if self.scenario_id is AndroidServiceScenarioId.POSITIVE:
            if (
                common.benchmark_outcome != "pass"
                or not common.evaluator_pass
                or common.invalid_count != 0
                or self.effect_counters.action_count < 1
                or self.device_delta.added_count < 1
            ):
                raise ValueError("positive scenario lacks PASS and device delta")
        elif (
            common.benchmark_outcome != "fail"
            or common.evaluator_pass
            or common.invalid_count != 0
            or self.device_delta.added_count != 0
        ):
            raise ValueError("controlled failure is not a normal evaluator FAIL")
        return self


class AcceptanceCommandEvidence(BaseModel):
    """One path-free reproducible command and bounded observation."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    suite_id: StrictStr = Field(alias="suiteId")
    command: StrictStr
    observed: StrictStr
    verification: StrictStr = Field(pattern=r"^passed$")

    @field_validator("suite_id", "command", "observed")
    @classmethod
    def _safe_command(cls, value: str) -> str:
        """Reject host-specific or secret-bearing command evidence.

        Args:
            value: Candidate command field.

        Raises:
            ValueError: Text is unsafe.

        Returns:
            Validated text.
        """
        return _assert_safe_string(value, field="command evidence")


class StudioBenchmarkAndroidServiceAcceptanceSummaryV1(BaseModel):
    """Complete Stage 5.6C-1 bounded real-Android proof ledger."""

    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    schema_version: StrictInt = Field(default=SUMMARY_SCHEMA_VERSION, alias="schemaVersion")
    campaign_version: StrictStr = Field(default=CAMPAIGN_VERSION, alias="campaignVersion")
    selection: SafeAcceptanceSelection
    scenarios: tuple[AndroidServiceScenarioEvidence, ...] = Field(
        min_length=2,
        max_length=2,
    )
    commands: tuple[AcceptanceCommandEvidence, ...] = Field(
        min_length=1,
        max_length=MAX_COMMANDS,
    )
    scanned_documents: StrictInt = Field(alias="scannedDocuments", ge=1, le=MAX_SCAN_DOCUMENTS)
    private_values_found: StrictInt = Field(alias="privateValuesFound", ge=0, le=0)
    claim_limits: tuple[StrictStr, ...] = Field(alias="claimLimits")

    @model_validator(mode="after")
    def _complete_campaign(self) -> Self:
        """Require both scenarios, distinct revisions, scans, and claim limits.

        Raises:
            ValueError: Campaign evidence is incomplete or overclaims.

        Returns:
            Complete validated proof ledger.
        """
        if self.schema_version != SUMMARY_SCHEMA_VERSION:
            raise ValueError("unsupported Android service summary schema")
        if self.campaign_version != CAMPAIGN_VERSION:
            raise ValueError("unknown Android service acceptance campaign")
        if tuple(item.scenario_id for item in self.scenarios) != REQUIRED_SCENARIOS:
            raise ValueError("required Android scenarios must be stable and complete")
        revisions = tuple(item.identities.agent_revision_id for item in self.scenarios)
        if len(set(revisions)) != 2:
            raise ValueError("positive and control require distinct immutable revisions")
        if self.claim_limits != REQUIRED_CLAIM_LIMITS:
            raise ValueError("Stage 5.6C-1 claim limits changed")
        _assert_safe_json(
            self.model_dump(mode="json", by_alias=True),
            field="Android service acceptance summary",
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


def validate_summary_file(
    path: str | Path,
) -> StudioBenchmarkAndroidServiceAcceptanceSummaryV1:
    """Read and strictly validate one Stage 5.6C-1 proof ledger.

    Args:
        path: Existing summary JSON path.

    Raises:
        OSError: The file cannot be read.
        ValueError: JSON or the strict contract is invalid.

    Returns:
        Validated Android service acceptance summary.
    """
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return StudioBenchmarkAndroidServiceAcceptanceSummaryV1.model_validate(payload)


def write_summary(
    summary: StudioBenchmarkAndroidServiceAcceptanceSummaryV1,
    path: str | Path,
) -> Path:
    """Write one validated summary to an explicit disposable destination.

    Args:
        summary: Complete validated proof ledger.
        path: Destination beneath the campaign workspace.

    Raises:
        OSError: Parent or destination cannot be written.

    Returns:
        Resolved written path.
    """
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(summary.canonical_json() + "\n", encoding="utf-8")
    return destination


@dataclass(frozen=True)
class HTTPResponse:
    """One bounded local Studio HTTP response."""

    status: int
    headers: Mapping[str, str]
    body: bytes

    def json(self) -> Any:
        """Decode the response body as JSON.

        Raises:
            UnicodeDecodeError: Body is not UTF-8.
            json.JSONDecodeError: Body is not JSON.

        Returns:
            Decoded JSON-compatible value.
        """
        return json.loads(self.body.decode("utf-8"))


def _request(
    address: tuple[str, int],
    method: str,
    path: str,
    payload: Mapping[str, Any] | None = None,
    *,
    timeout: float = 30.0,
) -> HTTPResponse:
    """Issue one bounded request to the loopback Studio service.

    Args:
        address: Loopback host and port.
        method: HTTP method.
        path: Absolute Studio resource path.
        payload: Optional JSON request body.
        timeout: Socket timeout in seconds.

    Raises:
        OSError: The local service cannot be reached.
        ValueError: Payload cannot be serialized.

    Returns:
        Complete status, normalized headers, and body.
    """
    body = None
    headers = {"Host": "127.0.0.1"}
    if payload is not None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["Content-Length"] = str(len(body))
    connection = http.client.HTTPConnection(*address, timeout=timeout)
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        content = response.read()
        normalized = {
            key.lower(): value for key, value in response.getheaders()
        }
        return HTTPResponse(response.status, normalized, content)
    finally:
        connection.close()


@dataclass(frozen=True)
class RunningStudioServer:
    """Owned loopback HTTP server thread for one scenario composition."""

    server: Any
    thread: threading.Thread
    address: tuple[str, int]

    def close(self) -> None:
        """Stop the listener and wait for bounded handler teardown.

        Raises:
            TimeoutError: The server thread does not terminate.

        Returns:
            None.
        """
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.thread.is_alive():
            raise TimeoutError("Android service acceptance HTTP server did not stop")


def _sha256_bytes(value: bytes) -> str:
    """Return one prefixed SHA-256 digest.

    Args:
        value: Artifact bytes.

    Returns:
        Prefixed lowercase SHA-256 digest.
    """
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _safe_disposable_root(path: Path) -> Path:
    """Require acceptance output beneath the repository's ignored temp root.

    Args:
        path: Candidate campaign workspace.

    Raises:
        ValueError: Destination is outside the disposable root.

    Returns:
        Resolved safe workspace path.
    """
    resolved = path.expanduser().resolve()
    allowed = (ROOT / "temp").resolve()
    if resolved == allowed or allowed not in resolved.parents:
        raise ValueError("acceptance workspace must be a child of repository temp/")
    return resolved


def _assert_unchanged_profile_authority(
    original_profiles: Any,
    restarted_profiles: Any,
    *,
    device_profile_id: str,
) -> None:
    """Require the exact private binding to survive terminal restart.

    Args:
        original_profiles: Resolver used for source execution.
        restarted_profiles: Resolver freshly loaded for terminal reopen.
        device_profile_id: Safe selected public profile identity.

    Raises:
        RuntimeError: Binding fingerprint or target key drifted.

    Returns:
        None.
    """
    original = original_profiles.resolve(device_profile_id)
    restarted = restarted_profiles.resolve(device_profile_id)
    if (
        restarted.binding_fingerprint != original.binding_fingerprint
        or restarted.target_key != original.target_key
    ):
        raise RuntimeError("trusted Android profile authority drifted before restart")


class ScriptedCameraLLM:
    """Emit deterministic camera actions without network or secret authority."""

    def __init__(self, *, x: int, y: int) -> None:
        """Create one run-scoped scripted positive dependency.

        Args:
            x: Shutter horizontal coordinate.
            y: Shutter vertical coordinate.

        Raises:
            ValueError: A coordinate is negative.

        Returns:
            None.
        """
        if x < 0 or y < 0:
            raise ValueError("camera coordinates must be non-negative")
        self.x = x
        self.y = y
        self.calls = 0

    def generate(
        self,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        """Return START_APP, preview WAIT, TAP, and settle WAIT actions.

        Args:
            prompt: Rendered Agent reasoning prompt.
            images: Current screenshot references.

        Raises:
            RuntimeError: The verified graph asks for an unexpected decision.

        Returns:
            One deterministic Mobile Agent action.
        """
        del prompt, images
        self.calls += 1
        if self.calls == 1:
            return (
                '{"action":"start_app","arguments":{"app":"camera"},'
                '"thought":"open the selected camera app"}'
            )
        if self.calls == 2:
            return (
                '{"action":"wait","arguments":{"seconds":3},'
                '"thought":"wait for the camera preview"}'
            )
        if self.calls == 3:
            return (
                '{"action":"tap","arguments":'
                f'{{"x":{self.x},"y":{self.y}}},'
                '"thought":"press the shutter"}'
            )
        if self.calls == 4:
            return (
                '{"action":"wait","arguments":{"seconds":3},'
                '"thought":"allow MediaStore to publish the captured photo"}'
            )
        raise RuntimeError("positive Agent did not terminate after the shutter action")


class ControlledFinishLLM:
    """End normally without performing the task success action."""

    def __init__(self) -> None:
        """Create one call-counted controlled-negative dependency."""
        self.calls = 0

    def generate(
        self,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        """Return one normal terminal action without touching the camera.

        Args:
            prompt: Rendered Agent reasoning prompt.
            images: Current screenshot references.

        Returns:
            Parser-compatible terminal action.
        """
        del prompt, images
        self.calls += 1
        if self.calls != 1:
            raise RuntimeError("controlled Agent requested an extra decision")
        return '{"action":"DONE","params":{},"thought":"controlled normal finish"}'


class FailIfCalledLLM:
    """Fail-fast sentinel proving terminal restart does not rerun the Agent."""

    def __init__(self) -> None:
        """Create a zero-call restart sentinel."""
        self.calls = 0

    def generate(
        self,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        """Reject any post-terminal Agent activation.

        Args:
            prompt: Unexpected reasoning prompt.
            images: Unexpected screenshot references.

        Raises:
            RuntimeError: Always; terminal startup must not call the Agent.

        Returns:
            Never returns.
        """
        del prompt, images
        self.calls += 1
        raise RuntimeError("terminal restart attempted to replay the Agent")


def _studio_document_from_graph(
    graph: Any,
    *,
    document_id: str,
    agent_id: str,
    component_catalog: Any,
) -> dict[str, Any]:
    """Project the selected contract-1.1 graph into Studio schema 2.

    The 5.6C-1 graph has no inline subgraph or loop declarations.  Rejecting
    either construct keeps this acceptance-only projection narrow and avoids a
    second general-purpose compiler.

    Args:
        graph: Validated AgentGraph value.
        document_id: Stable provisional document identity.
        agent_id: Stable provisional Agent identity rebound on create.
        component_catalog: Authoritative Studio Catalog used to pin versions.

    Raises:
        ValueError: Contract version or graph shape is outside this harness.

    Returns:
        Strict Studio schema-2 document mapping.
    """
    if graph.contract_version != "1.1":
        raise ValueError("Android acceptance requires AgentGraph contract 1.1")
    nodes: list[dict[str, Any]] = []
    presentation: dict[str, dict[str, Any]] = {}
    for index, node in enumerate(graph.nodes):
        if node.subgraph is not None or node.loop is not None:
            raise ValueError("Android acceptance graph must remain non-nested")
        canvas_id = f"canvas-{node.id}"
        raw: dict[str, Any] = {
            "canvasId": canvas_id,
            "logicalId": node.id,
            "kind": node.kind.value,
            "lifecycle": node.lifecycle.value,
            "primary": node.primary,
            "metadata": deepcopy(node.metadata),
        }
        for field_name in (
            "role",
            "contract",
            "component",
            "predicate",
            "execution",
            "router",
            "state",
        ):
            value = getattr(node, field_name)
            if value is None:
                continue
            if field_name == "role":
                raw[field_name] = value.value
                continue
            projected = value.model_dump(mode="json", exclude_none=True)
            if field_name == "component":
                for reference in projected.get("candidates", ()):
                    dependencies = reference.get("dependencies", {})
                    llm_dependency = dependencies.get("llm")
                    if isinstance(llm_dependency, dict):
                        # Keep the graph's safe SecretRef placeholders and
                        # bounded connection parameters so the authoritative
                        # Catalog can validate the dependency configuration.
                        # The acceptance composition still injects the
                        # deterministic LLM object by dependency name, so no
                        # secret is resolved and no model connection occurs.
                        reference["dependencies"]["llm"] = deepcopy(
                            llm_dependency
                        )
                    if reference.get("version") is not None:
                        continue
                    versions = {
                        item.version
                        for item in component_catalog.components
                        if item.namespace == reference.get("namespace")
                        and item.name == reference.get("name")
                    }
                    if len(versions) != 1:
                        raise ValueError(
                            "Android acceptance component version is ambiguous"
                        )
                    reference["version"] = versions.pop()
            raw[field_name] = projected
        nodes.append(raw)
        presentation[canvas_id] = {
            "x": index * 180,
            "y": 0,
            "label": node.id,
            "icon": "",
            "description": "",
        }
    edges: list[dict[str, Any]] = []
    for index, edge in enumerate(graph.edges):
        raw_edge: dict[str, Any] = {
            "canvasId": f"edge-{index + 1}",
            "source": {
                "canvasId": f"canvas-{edge.source.node}",
                "portId": edge.source.port,
            },
            "target": {
                "canvasId": f"canvas-{edge.target.node}",
                "portId": edge.target.port,
            },
            "kind": edge.kind.value,
        }
        if edge.condition is not None:
            raw_edge["condition"] = edge.condition.model_dump(mode="json")
        if edge.feedback is not None:
            raw_edge["feedback"] = edge.feedback.model_dump(mode="json")
        edges.append(raw_edge)
    semantic: dict[str, Any] = {
        "profile": graph.profile,
        "policies": graph.policies.model_dump(mode="json"),
        "nodes": nodes,
        "edges": edges,
    }
    if graph.interface is not None:
        semantic["interface"] = graph.interface.model_dump(mode="json")
    return {
        "schemaVersion": 2,
        "contractVersion": "1.1",
        "documentId": document_id,
        "agentId": agent_id,
        "name": document_id,
        "semantic": semantic,
        "presentation": {
            "nodes": presentation,
            "viewport": {"x": 0, "y": 0, "zoom": 1},
        },
        "authoring": {
            "description": "Stage 5.6C-1 deterministic acceptance Agent",
            "createdAt": 0,
            "updatedAt": 0,
        },
    }


def _preview_definition(
    *,
    catalog_entry_id: str,
    task_id: str,
    agent_id: str,
    revision_id: str,
    device_profile_id: str,
) -> dict[str, Any]:
    """Build the exact one-by-one-by-one browser definition.

    Args:
        catalog_entry_id: Selected immutable Catalog entry.
        task_id: Exact selected task identity.
        agent_id: Selected Agent identity.
        revision_id: Selected immutable Agent revision.
        device_profile_id: Safe selected profile identity.

    Returns:
        Strict preview/create definition mapping.
    """
    return {
        "schemaVersion": 1,
        "agentRevisions": [
            {"agentId": agent_id, "revisionId": revision_id}
        ],
        "benchmark": {
            "catalogEntryId": catalog_entry_id,
            "split": SPLIT,
            "taskIds": [task_id],
        },
        "protocol": {
            "schemaVersion": "1.0",
            "seed": PROTOCOL_SEED,
            "repeats": 1,
            "taskOrder": {"strategy": "fixed"},
            "taskMaterialization": {
                "reuseAcrossAgents": True,
                "strictFairness": False,
            },
            "device": {
                "platform": "android",
                "locale": "en-US",
                "orientation": "portrait",
                "versionPolicy": "compatible",
            },
            "apps": [],
            "budget": {
                "maxInteractions": 15,
                "maxActivations": 200,
                "timeoutSeconds": 600,
                "requireObservableTokens": False,
            },
            "isolation": {
                "reset": "before_each_agent",
                "cleanup": "after_each_run",
                "requireVerifiedReset": True,
            },
            "failure": {
                "initializer": {
                    "outcome": "invalidate",
                    "continueSuite": True,
                    "preserveEvidence": True,
                },
                "agent": {
                    "outcome": "evaluate_if_possible",
                    "continueSuite": True,
                    "preserveEvidence": True,
                },
                "evaluator": {
                    "outcome": "invalidate",
                    "continueSuite": True,
                    "preserveEvidence": True,
                },
                "cleanup": {
                    "outcome": "invalidate",
                    "continueSuite": True,
                    "preserveEvidence": True,
                },
            },
        },
        "deviceProfileId": device_profile_id,
    }


@dataclass(frozen=True)
class ScenarioRuntime:
    """Owned production Studio composition for one isolated scenario."""

    scenario_id: AndroidServiceScenarioId
    workspace: Path
    database: Path
    composition: Any
    application_service: Any
    server: RunningStudioServer
    llm: Any
    agent_id: str
    revision_id: str
    catalog_entry_id: str
    task_id: str
    definition: Mapping[str, Any]

    def close(self) -> None:
        """Stop HTTP and process-local worker ownership without deleting facts.

        Raises:
            TimeoutError: HTTP handlers do not stop.

        Returns:
            None.
        """
        try:
            self.server.close()
        finally:
            self.composition.shutdown(wait=True)


def _start_server(application_service: Any, composition: Any) -> RunningStudioServer:
    """Start the actual Studio HTTP surface over one production composition.

    Args:
        application_service: Agent/Replay application service.
        composition: Complete Benchmark composition.

    Raises:
        OSError: Loopback listener cannot be created.

    Returns:
        Owned running server.
    """
    from zhixing.studio.httpd import create_http_server

    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=application_service,
        benchmark_composition=composition,
        sse_heartbeat_seconds=0.25,
        sse_write_timeout_seconds=1.0,
        benchmark_sse_max_connections=4,
    )
    thread = threading.Thread(
        target=server.serve_forever,
        name="zhixing-android-service-acceptance-http",
        daemon=True,
    )
    thread.start()
    return RunningStudioServer(
        server=server,
        thread=thread,
        address=("127.0.0.1", int(server.server_address[1])),
    )


def _build_scenario_runtime(
    workspace: Path,
    *,
    scenario_id: AndroidServiceScenarioId,
    profiles: Any,
    device_profile_id: str,
    x: int,
    y: int,
    restart_agent: tuple[str, str] | None = None,
) -> ScenarioRuntime:
    """Build one production Studio composition and immutable Agent selection.

    Args:
        workspace: Isolated scenario durable workspace.
        scenario_id: Positive or controlled-negative scenario.
        profiles: Trusted safe/private Android profile resolver.
        device_profile_id: Explicit safe public profile identity.
        x: Shutter horizontal coordinate.
        y: Shutter vertical coordinate.
        restart_agent: Existing Agent/revision pair for terminal reopen.

    Raises:
        ValueError: Agent, Catalog, task, or composition contracts drift.
        OSError: Durable resources cannot be created or opened.

    Returns:
        Owned runtime; caller must close it.
    """
    from examples.sdk.android_content_verified_agent import (
        build_android_content_verified_agent,
    )
    from zhixing.studio import (
        SQLiteAgentDocumentRepository,
        StudioApplicationService,
        build_default_replay_service,
        build_default_studio_benchmark_composition,
        build_studio_component_catalog,
    )
    from zhixing.studio.benchmark_service import StudioBenchmarkSource
    from zhixing.studio.run_execution import ProductionComponentResolverFactory

    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "studio.sqlite3"
    graph_catalog = build_studio_component_catalog()
    agents = SQLiteAgentDocumentRepository(database)
    application_service = StudioApplicationService(
        catalog=graph_catalog,
        repository=agents,
        replay_service=build_default_replay_service(database),
    )
    if restart_agent is None:
        max_steps = 4 if scenario_id is AndroidServiceScenarioId.POSITIVE else 1
        graph = build_android_content_verified_agent(max_steps=max_steps)
        document = _studio_document_from_graph(
            graph,
            document_id=f"document-{scenario_id.value}",
            agent_id=f"agent-{scenario_id.value}",
            component_catalog=graph_catalog,
        )
        agent, revision = application_service.create_agent(
            (
                "Android Service Positive Acceptance"
                if scenario_id is AndroidServiceScenarioId.POSITIVE
                else "Android Service Controlled Failure"
            ),
            initial_document=document,
        )
        if revision.compile_snapshot.status != "valid":
            diagnostics = revision.compile_snapshot.diagnostics
            first = diagnostics[0] if diagnostics else None
            detail = (
                f" ({first.code}: {first.message})"
                if first is not None
                else ""
            )
            raise ValueError(
                "Android service acceptance Agent did not compile" + detail
            )
        agent_id = agent.agent_id
        revision_id = revision.revision_id
        llm: Any = (
            ScriptedCameraLLM(x=x, y=y)
            if scenario_id is AndroidServiceScenarioId.POSITIVE
            else ControlledFinishLLM()
        )
    else:
        agent_id, revision_id = restart_agent
        agents.get_revision(agent_id, revision_id)
        llm = FailIfCalledLLM()
    package_root = ROOT / "benchmarks" / "android_world"
    composition = build_default_studio_benchmark_composition(
        workspace,
        agents=agents,
        profiles=profiles,
        contract_catalog=graph_catalog.node_contract_catalog(),
        sources=(
            StudioBenchmarkSource(
                source_id="android-service-acceptance-package",
                kind="package",
                locator=package_root,
            ),
        ),
        include_installed=False,
        database_path=database,
        component_resolvers=ProductionComponentResolverFactory(
            dependency_provider={"llm": llm}
        ),
    )
    entries = composition.catalog.list_entries(limit=100).items
    entry = next(
        (item for item in entries if item.package_identity == PACKAGE_IDENTITY),
        None,
    )
    if entry is None:
        composition.shutdown(wait=True)
        raise ValueError("selected AndroidWorld Package identity is unavailable")
    tasks = composition.catalog.list_tasks(
        entry.catalog_entry_id,
        split=SPLIT,
        limit=100,
    ).items
    if not any(item.task_id == TASK_ID for item in tasks):
        composition.shutdown(wait=True)
        raise ValueError("selected AndroidWorld_6 task identity is unavailable")
    definition = _preview_definition(
        catalog_entry_id=entry.catalog_entry_id,
        task_id=TASK_ID,
        agent_id=agent_id,
        revision_id=revision_id,
        device_profile_id=device_profile_id,
    )
    try:
        server = _start_server(application_service, composition)
    except Exception:
        composition.shutdown(wait=True)
        raise
    return ScenarioRuntime(
        scenario_id=scenario_id,
        workspace=workspace,
        database=database,
        composition=composition,
        application_service=application_service,
        server=server,
        llm=llm,
        agent_id=agent_id,
        revision_id=revision_id,
        catalog_entry_id=entry.catalog_entry_id,
        task_id=TASK_ID,
        definition=definition,
    )


def _expect_status(response: HTTPResponse, expected: int, *, resource: str) -> Any:
    """Require one exact HTTP status and return decoded JSON when present.

    Args:
        response: Complete local HTTP response.
        expected: Required status code.
        resource: Safe diagnostic resource label.

    Raises:
        RuntimeError: Status differs from the required contract.

    Returns:
        Decoded JSON body, or ``None`` for an empty body.
    """
    if response.status != expected:
        message = response.body.decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"{resource} returned {response.status}: {message}")
    return response.json() if response.body else None


def _create_experiment(runtime: ScenarioRuntime) -> str:
    """Preview and create one Experiment through authoritative HTTP resources.

    Args:
        runtime: Owned scenario service.

    Raises:
        RuntimeError: Preview or create does not satisfy the HTTP contract.

    Returns:
        Created opaque Experiment identity.
    """
    preview = _expect_status(
        _request(
            runtime.server.address,
            "POST",
            "/studio/benchmark-experiments/preview",
            runtime.definition,
        ),
        200,
        resource="Benchmark preview",
    )
    create_payload = {
        "schemaVersion": 1,
        "clientRequestId": f"android-service-{runtime.scenario_id.value}",
        "previewFingerprint": preview["previewFingerprint"],
        "definition": runtime.definition,
    }
    created = _expect_status(
        _request(
            runtime.server.address,
            "POST",
            "/studio/benchmark-experiments",
            create_payload,
        ),
        202,
        resource="Benchmark create",
    )
    experiment = created["experiment"]
    if experiment["lifecycle"] not in {
        "accepted",
        "starting",
        "running",
        "evaluating",
        "cleaning_up",
        "finalizing",
        "terminal",
    }:
        raise RuntimeError("Benchmark create returned an unknown lifecycle")
    return str(experiment["experimentId"])


def _wait_terminal(
    address: tuple[str, int],
    experiment_id: str,
    *,
    timeout_seconds: float,
) -> Mapping[str, Any]:
    """Poll one durable Experiment until terminal.

    Args:
        address: Loopback service address.
        experiment_id: Opaque Experiment identity.
        timeout_seconds: Positive bounded polling duration.

    Raises:
        TimeoutError: Experiment does not become terminal.
        RuntimeError: HTTP resource becomes unavailable.

    Returns:
        Terminal public Experiment resource.
    """
    if timeout_seconds <= 0 or timeout_seconds > 3600:
        raise ValueError("acceptance timeout must be within (0, 3600]")
    deadline = time.monotonic() + timeout_seconds
    path = f"/studio/benchmark-experiments/{experiment_id}"
    while time.monotonic() < deadline:
        resource = _expect_status(
            _request(address, "GET", path),
            200,
            resource="Benchmark Experiment",
        )
        if resource["lifecycle"] == "terminal":
            return resource
        time.sleep(0.25)
    raise TimeoutError("real-Android Experiment did not become terminal")


def _read_events(
    address: tuple[str, int],
    experiment_id: str,
) -> tuple[Mapping[str, Any], ...]:
    """Read the complete bounded durable event journal through pagination.

    Args:
        address: Loopback service address.
        experiment_id: Opaque Experiment identity.

    Raises:
        RuntimeError: Journal is discontinuous or exceeds the bound.

    Returns:
        Ordered durable event mappings.
    """
    after = 0
    events: list[Mapping[str, Any]] = []
    high_water = None
    while True:
        page = _expect_status(
            _request(
                address,
                "GET",
                f"/studio/benchmark-experiments/{experiment_id}/events"
                f"?after={after}&limit=100",
            ),
            200,
            resource="Benchmark event page",
        )
        items = tuple(page["items"])
        if any(int(item["sequence"]) != after + index + 1 for index, item in enumerate(items)):
            raise RuntimeError("Benchmark event journal is discontinuous")
        events.extend(items)
        if len(events) > MAX_EVENTS:
            raise RuntimeError("Benchmark event journal exceeds acceptance bound")
        after = int(page["nextCursor"])
        high_water = int(page["highWaterMark"])
        if after >= high_water:
            break
        if not items:
            raise RuntimeError("Benchmark event pagination made no progress")
    if high_water != len(events):
        raise RuntimeError("Benchmark event high-water mark is inconsistent")
    return tuple(events)


def _verify_binary_resource(
    address: tuple[str, int],
    path: str,
    *,
    expected_size: int | None = None,
    expected_sha256: str | None = None,
    expected_content_type: str | None = None,
    require_head: bool = True,
) -> bytes:
    """Verify exact GET and optional HEAD behavior for one managed resource.

    Args:
        address: Loopback service address.
        path: Authoritative same-service resource path.
        expected_size: Optional descriptor byte count.
        expected_sha256: Optional descriptor digest.
        expected_content_type: Optional descriptor media type.
        require_head: Whether the route must support exact HEAD.

    Raises:
        RuntimeError: Transport metadata, size, or digest disagrees.

    Returns:
        Verified GET body bytes.
    """
    get = _request(address, "GET", path)
    if get.status != 200:
        raise RuntimeError(f"managed GET failed with status {get.status}")
    if int(get.headers.get("content-length", "-1")) != len(get.body):
        raise RuntimeError("managed GET Content-Length is inconsistent")
    if expected_size is not None and len(get.body) != expected_size:
        raise RuntimeError("managed GET size disagrees with descriptor")
    if expected_sha256 is not None and _sha256_bytes(get.body) != expected_sha256:
        raise RuntimeError("managed GET digest disagrees with descriptor")
    if (
        expected_content_type is not None
        and get.headers.get("content-type") != expected_content_type
    ):
        raise RuntimeError("managed GET Content-Type disagrees with descriptor")
    if require_head:
        head = _request(address, "HEAD", path)
        if head.status != 200 or head.body:
            raise RuntimeError("managed HEAD did not return empty success")
        if head.headers.get("content-length") != get.headers.get("content-length"):
            raise RuntimeError("managed HEAD Content-Length disagrees with GET")
        if head.headers.get("content-type") != get.headers.get("content-type"):
            raise RuntimeError("managed HEAD Content-Type disagrees with GET")
    return get.body


def _publication_evidence(
    address: tuple[str, int],
    experiment: Mapping[str, Any],
    task_run: Mapping[str, Any],
) -> tuple[ManagedPublicationEvidence, Mapping[str, Any], tuple[Any, ...]]:
    """Close inventory, managed bytes, aggregate resources, and Replay.

    Args:
        address: Loopback service address.
        experiment: Terminal Experiment resource.
        task_run: Terminal TaskRun resource.

    Raises:
        RuntimeError: Publication, integrity, ownership, or Replay is incomplete.

    Returns:
        Strict publication proof, Replay JSON, and captured scan documents.
    """
    experiment_id = str(experiment["experimentId"])
    task_run_id = str(task_run["taskRunId"])
    inventory = _expect_status(
        _request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/artifacts?limit=100",
        ),
        200,
        resource="Benchmark artifact inventory",
    )
    if inventory.get("nextCursor"):
        raise RuntimeError("acceptance artifact inventory exceeds one bounded page")
    artifacts: list[ManagedArtifactEvidence] = []
    captured: list[Any] = [experiment, task_run, inventory]
    for item in inventory["items"]:
        descriptor = item["descriptor"]
        content_path = item.get("links", {}).get("content")
        if not content_path:
            continue
        body = _verify_binary_resource(
            address,
            content_path,
            expected_size=int(descriptor["size"]),
            expected_sha256=str(descriptor["sha256"]),
            expected_content_type=str(descriptor["contentType"]),
        )
        captured.append(body)
        artifacts.append(
            ManagedArtifactEvidence(
                artifactId=descriptor["artifactId"],
                taskRunId=descriptor.get("taskRunId"),
                kind=descriptor["kind"],
                contentType=descriptor["contentType"],
                size=descriptor["size"],
                sha256=descriptor["sha256"],
                getVerified=True,
                headVerified=True,
            )
        )
    report_path = experiment.get("links", {}).get("report")
    bundle_path = experiment.get("links", {}).get("bundle")
    if not report_path or not bundle_path:
        raise RuntimeError("terminal Experiment lacks report or bundle link")
    report = _verify_binary_resource(address, report_path)
    bundle = _verify_binary_resource(address, bundle_path)
    captured.extend((report, bundle))
    replay_id = task_run.get("replayId")
    replay_path = task_run.get("links", {}).get("replay")
    if not replay_id or not replay_path:
        raise RuntimeError("terminal TaskRun lacks native Replay identity")
    replay = _expect_status(
        _request(address, "GET", replay_path),
        200,
        resource="native Benchmark Replay",
    )
    replay_bundle = _verify_binary_resource(
        address,
        f"/studio/replays/{replay_id}/bundle",
        require_head=False,
    )
    captured.extend((replay, replay_bundle))
    return (
        ManagedPublicationEvidence(
            artifacts=tuple(sorted(artifacts, key=lambda item: item.artifact_id)),
            reportGetHeadVerified=True,
            bundleGetHeadVerified=True,
            replayResourceVerified=True,
            replayBundleVerified=True,
        ),
        replay,
        tuple(captured),
    )


def _task_run(
    address: tuple[str, int],
    experiment_id: str,
) -> Mapping[str, Any]:
    """Load the exactly one planned TaskRun and its strict result.

    Args:
        address: Loopback service address.
        experiment_id: Owning Experiment identity.

    Raises:
        RuntimeError: Cardinality or result availability is wrong.

    Returns:
        Terminal TaskRun resource.
    """
    page = _expect_status(
        _request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/task-runs?limit=10",
        ),
        200,
        resource="Benchmark TaskRun page",
    )
    if len(page["items"]) != 1 or page.get("nextCursor"):
        raise RuntimeError("Studio acceptance requires exactly one TaskRun")
    task_run_id = page["items"][0]["taskRunId"]
    task = _expect_status(
        _request(
            address,
            "GET",
            f"/studio/benchmark-experiments/{experiment_id}/task-runs/{task_run_id}",
        ),
        200,
        resource="Benchmark TaskRun",
    )
    if task.get("resultAvailability") != "available" or not task.get("result"):
        raise RuntimeError("terminal TaskRun lacks immutable TaskResult")
    return task


def _scan_archive(
    path: Path,
    *,
    forbidden_values: Sequence[str],
) -> int:
    """Scan one ZIP archive's decompressed bounded members for private data.

    Args:
        path: Existing ZIP archive.
        forbidden_values: Exact private runtime values.

    Raises:
        ValueError: Archive is unsafe, too large, or contains private data.
        OSError: Archive cannot be read.

    Returns:
        Number of decompressed members scanned.
    """
    count = 0
    total = 0
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        if len(members) > MAX_ARTIFACTS:
            raise ValueError("acceptance ZIP contains too many members")
        for member in members:
            total += member.file_size
            if total > 128 * 1024 * 1024:
                raise ValueError("acceptance ZIP exceeds decompression bound")
            if member.is_dir():
                continue
            body = archive.read(member)
            assert_forbidden_values_absent(
                body,
                forbidden_values=forbidden_values,
                field="managed ZIP member",
            )
            if member.filename.endswith((".json", ".jsonl", ".txt", ".xml")):
                text = body.decode("utf-8", errors="replace")
                if _contains_host_absolute_path(text):
                    raise ValueError("managed ZIP member contains a host path")
            count += 1
    return count


def _scan_campaign(
    scenario_roots: Sequence[Path],
    captured_documents: Sequence[Any],
    *,
    forbidden_values: Sequence[str],
) -> int:
    """Scan databases, managed files, HTTP resources, and summaries.

    Args:
        scenario_roots: Isolated durable workspaces to inspect.
        captured_documents: JSON and byte resources observed over HTTP.
        forbidden_values: Exact raw target/configuration canaries.

    Raises:
        ValueError: Private data or a host path appears in managed evidence.
        OSError: Durable evidence cannot be read.

    Returns:
        Number of files/documents scanned.
    """
    count = 0
    for document in captured_documents:
        assert_forbidden_values_absent(
            document,
            forbidden_values=forbidden_values,
            field="captured service evidence",
        )
        if isinstance(document, (Mapping, list, tuple)):
            _assert_safe_json(document, field="captured service JSON")
        elif isinstance(document, bytes):
            try:
                decoded = document.decode("utf-8")
            except UnicodeDecodeError:
                decoded = ""
            if decoded and _contains_host_absolute_path(decoded):
                raise ValueError("captured service evidence contains a host path")
        count += 1
    for root in scenario_roots:
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            if path.name.endswith((".sqlite3", ".sqlite3-wal", ".sqlite3-shm")):
                # The profile binding is intentionally private durable authority.
                # Public DTOs reconstructed from it were scanned above; treating
                # raw SQLite/WAL bytes as public evidence would reject the very
                # private fingerprint and target key the database must retain.
                count += 1
                continue
            body = path.read_bytes()
            assert_forbidden_values_absent(
                body,
                forbidden_values=forbidden_values,
                field="durable acceptance evidence",
            )
            if path.suffix.lower() == ".zip":
                count += _scan_archive(
                    path,
                    forbidden_values=forbidden_values,
                )
            elif path.suffix.lower() in {
                ".json",
                ".jsonl",
                ".txt",
                ".xml",
                ".log",
            }:
                text = body.decode("utf-8", errors="replace")
                if _contains_host_absolute_path(text):
                    raise ValueError("durable managed evidence contains a host path")
            count += 1
            if count > MAX_SCAN_DOCUMENTS:
                raise ValueError("acceptance scan exceeds document bound")
    return count


def _origin(value: Mapping[str, Any]) -> SafeEvidenceOrigin:
    """Parse the three public provenance fields from a product resource.

    Args:
        value: Product evidence-origin mapping.

    Raises:
        ValueError: Required fields are absent or inconsistent.

    Returns:
        Strict acceptance provenance projection.
    """
    return SafeEvidenceOrigin(
        acquisition=value["acquisition"],
        environment=value["environment"],
        realDeviceEvidence=value["realDeviceEvidence"],
    )


def _source_effect_count(
    events: Sequence[Mapping[str, Any]],
    *,
    llm_calls: int,
) -> int:
    """Project one stable count of source Core events plus Agent decisions.

    Args:
        events: Complete durable Experiment journal.
        llm_calls: Deterministic reasoning dependency call count.

    Returns:
        Non-negative source-effect count used only for restart comparison.
    """
    core_events = sum(item.get("source") == "core" for item in events)
    return int(core_events) + int(llm_calls)


def _effect_counters(
    events: Sequence[Mapping[str, Any]],
    task_run: Mapping[str, Any],
) -> AndroidServiceEffectCounters:
    """Project setup/Agent/evaluator starts and Agent interaction count.

    Args:
        events: Complete durable Experiment journal.
        task_run: Terminal public TaskRun with immutable result phases.

    Raises:
        RuntimeError: The result does not expose one Agent phase counter.
        ValueError: Counts violate the fixed one-TaskRun matrix.

    Returns:
        Strict bounded source-effect counters.
    """
    kinds = tuple(str(item.get("kind") or "") for item in events)
    result = task_run.get("result")
    if not isinstance(result, Mapping):
        raise RuntimeError("TaskRun lacks a result for effect counting")
    agent_phase = next(
        (
            phase
            for phase in result.get("phases", ())
            if isinstance(phase, Mapping) and phase.get("phase") == "agent"
        ),
        None,
    )
    if not isinstance(agent_phase, Mapping):
        raise RuntimeError("TaskResult lacks an Agent phase for effect counting")
    phase_evidence = agent_phase.get("evidence")
    if not isinstance(phase_evidence, Mapping):
        raise RuntimeError("TaskResult Agent phase lacks interaction evidence")
    interaction_count = phase_evidence.get(
        "interactionCount",
        phase_evidence.get("interaction_count"),
    )
    if isinstance(interaction_count, bool) or not isinstance(interaction_count, int):
        raise RuntimeError("TaskResult Agent phase lacks an interaction count")
    return AndroidServiceEffectCounters(
        initializerCount=kinds.count("benchmark.setup.start"),
        agentCount=kinds.count("benchmark.agent.start"),
        evaluatorCount=kinds.count("benchmark.evaluation.start"),
        actionCount=interaction_count,
    )


def _run_scenario(
    workspace: Path,
    *,
    scenario_id: AndroidServiceScenarioId,
    profiles: Any,
    device_profile_id: str,
    device_profile_config: Path,
    probe: Any,
    probe_device: Any,
    x: int,
    y: int,
    timeout_seconds: float,
) -> tuple[AndroidServiceScenarioEvidence, tuple[Any, ...]]:
    """Execute, publish, restart, and validate one real-Android scenario.

    Args:
        workspace: Scenario-isolated durable workspace.
        scenario_id: Positive or controlled-negative identity.
        profiles: Trusted Android profile resolver.
        device_profile_id: Explicit safe public profile identity.
        device_profile_config: Trusted local profile configuration to reload.
        probe: Independent Android content probe.
        probe_device: Exact selected probe device.
        x: Shutter horizontal coordinate.
        y: Shutter vertical coordinate.
        timeout_seconds: Bounded terminal wait.

    Raises:
        RuntimeError: Any service, outcome, publication, or restart gate fails.
        ValueError: Strict evidence contract rejects observed facts.

    Returns:
        Complete scenario proof and captured scan documents.
    """
    runtime = _build_scenario_runtime(
        workspace,
        scenario_id=scenario_id,
        profiles=profiles,
        device_profile_id=device_profile_id,
        x=x,
        y=y,
    )
    before = probe.snapshot(probe_device)
    captured: list[Any] = []
    try:
        experiment_id = _create_experiment(runtime)
        experiment = _wait_terminal(
            runtime.server.address,
            experiment_id,
            timeout_seconds=timeout_seconds,
        )
        task = _task_run(runtime.server.address, experiment_id)
        events = _read_events(runtime.server.address, experiment_id)
        effect_counters = _effect_counters(events, task)
        after = probe.snapshot(probe_device)
        delta = probe.diff(before, after)
        publication, replay, publication_documents = _publication_evidence(
            runtime.server.address,
            experiment,
            task,
        )
        captured.extend(publication_documents)
        result = task["result"]
        evaluation = result.get("evaluation")
        if not isinstance(evaluation, Mapping) or evaluation.get("isPass") is None:
            raise RuntimeError("TaskResult lacks executed evaluator evidence")
        source_origin = _origin(result["evidenceOrigin"])
        replay_origin = _origin(replay["evidenceOrigin"])
        identities = AndroidServiceCausalIdentities(
            experimentId=experiment_id,
            plannedTaskRunId=task["taskRunId"],
            coreTaskRunId=result["coreTaskRunId"],
            agentRunId=result["agentRunId"],
            agentId=result["agentId"],
            agentRevisionId=result["agentRevisionId"],
            agentGraphIdentity=result["agentGraphIdentity"],
            benchmarkPlanIdentity=result["benchmarkPlanIdentity"],
            experimentProtocolIdentity=result["experimentProtocolIdentity"],
            taskInstanceIdentity=result["taskInstanceIdentity"],
            replayId=task["replayId"],
        )
        terminal_events = sum(
            item.get("kind") == "experiment.terminal" for item in events
        )
        before_source_count = _source_effect_count(
            events,
            llm_calls=int(runtime.llm.calls),
        )
        before_high_water = int(experiment["eventHighWaterMark"])
        artifact_projection = tuple(
            (
                item.artifact_id,
                item.task_run_id,
                item.kind,
                item.content_type,
                item.size,
                item.sha256,
            )
            for item in publication.artifacts
        )
        restart_agent = (runtime.agent_id, runtime.revision_id)
    finally:
        runtime.close()

    from zhixing.studio.device_profiles import load_android_device_profiles

    restarted_profiles = load_android_device_profiles(device_profile_config)
    _assert_unchanged_profile_authority(
        profiles,
        restarted_profiles,
        device_profile_id=device_profile_id,
    )
    restart_before = probe.snapshot(probe_device)
    restarted = _build_scenario_runtime(
        workspace,
        scenario_id=scenario_id,
        profiles=restarted_profiles,
        device_profile_id=device_profile_id,
        x=x,
        y=y,
        restart_agent=restart_agent,
    )
    try:
        reopened_experiment = _expect_status(
            _request(
                restarted.server.address,
                "GET",
                f"/studio/benchmark-experiments/{identities.experiment_id}",
            ),
            200,
            resource="restarted Benchmark Experiment",
        )
        reopened_task = _task_run(
            restarted.server.address,
            identities.experiment_id,
        )
        reopened_events = _read_events(
            restarted.server.address,
            identities.experiment_id,
        )
        reopened_publication, reopened_replay, reopened_documents = (
            _publication_evidence(
                restarted.server.address,
                reopened_experiment,
                reopened_task,
            )
        )
        captured.extend(reopened_documents)
        restart_after = probe.snapshot(probe_device)
        restart_delta = probe.diff(restart_before, restart_after)
        reopened_result = reopened_task["result"]
        reopened_identities = (
            reopened_experiment["experimentId"],
            reopened_task["taskRunId"],
            reopened_result["coreTaskRunId"],
            reopened_result["agentRunId"],
            reopened_task["replayId"],
        )
        original_identities = (
            identities.experiment_id,
            identities.planned_task_run_id,
            identities.core_task_run_id,
            identities.agent_run_id,
            identities.replay_id,
        )
        reopened_artifacts = tuple(
            (
                item.artifact_id,
                item.task_run_id,
                item.kind,
                item.content_type,
                item.size,
                item.sha256,
            )
            for item in reopened_publication.artifacts
        )
        restart_proof = TerminalRestartEvidence(
            identitiesStable=(
                reopened_identities == original_identities
                and reopened_artifacts == artifact_projection
                and reopened_replay["runId"] == replay["runId"]
            ),
            eventHighWaterStable=(
                int(reopened_experiment["eventHighWaterMark"])
                == before_high_water
                == len(reopened_events)
            ),
            uniqueTerminalEvent=(
                terminal_events == 1
                and sum(
                    item.get("kind") == "experiment.terminal"
                    for item in reopened_events
                )
                == 1
            ),
            sourceEffectCountBefore=before_source_count,
            sourceEffectCountAfter=_source_effect_count(
                reopened_events,
                llm_calls=(
                    int(runtime.llm.calls) + int(restarted.llm.calls)
                ),
            ),
            restartMediaAddedCount=len(restart_delta.added_ids),
        )
        if restarted.llm.calls != 0:
            raise RuntimeError("terminal restart called the Agent sentinel")
    finally:
        restarted.close()

    outcome = AndroidServiceOutcomeEvidence(
        experimentLifecycle=experiment["lifecycle"],
        experimentTerminalReason=experiment["terminalReason"],
        taskRunLifecycle=task["lifecycle"],
        taskRunTerminalReason=task["terminalReason"],
        agentStatus=result["agentStatus"],
        benchmarkOutcome=result["benchmarkOutcome"],
        evaluatorPass=bool(evaluation["isPass"]),
        invalidCount=(1 if result["benchmarkOutcome"] == "invalid" else 0),
    )
    evidence = AndroidServiceScenarioEvidence(
        scenarioId=scenario_id,
        verification="passed",
        identities=identities,
        outcome=outcome,
        effectCounters=effect_counters,
        deviceDelta=AndroidDeviceDeltaEvidence(
            addedCount=len(delta.added_ids),
            conclusive=True,
        ),
        sourceOrigin=source_origin,
        replayOrigin=replay_origin,
        publication=publication,
        restart=restart_proof,
    )
    captured.extend((experiment, task, tuple(events), reopened_experiment, reopened_task))
    return evidence, tuple(captured)


def run_campaign(
    *,
    device_profile_id: str,
    device_profile_config: Path,
    workspace_root: Path,
    x: int,
    y: int,
    timeout_seconds: float,
) -> StudioBenchmarkAndroidServiceAcceptanceSummaryV1:
    """Run the complete explicit positive/control service acceptance matrix.

    Args:
        device_profile_id: Safe configured Studio profile identity.
        device_profile_config: Trusted local configuration path.
        workspace_root: New disposable campaign directory under ``temp/``.
        x: Positive shutter horizontal coordinate.
        y: Positive shutter vertical coordinate.
        timeout_seconds: Per-scenario terminal timeout.

    Raises:
        FileExistsError: Campaign workspace already exists.
        StudioRunValidationError: Exact selected target is not ready.
        ValueError: Selection, evidence, redaction, or outcome gate fails.

    Returns:
        Complete validated Stage 5.6C-1 proof ledger.
    """
    from zhixing.devices.probes import AndroidContentProbe
    from zhixing.studio.device_profiles import (
        load_android_device_profiles,
        resolve_exact_android_session,
    )

    root = _safe_disposable_root(workspace_root)
    profiles = load_android_device_profiles(device_profile_config)
    profile = profiles.resolve(device_profile_id)
    if device_profile_id in {
        profile.serial,
        profile.binding_fingerprint,
        profile.target_key,
    }:
        raise ValueError("device profile identity must not expose private authority")
    session = resolve_exact_android_session(profile)
    if session.environment_candidate != "real_android" or session.serial is None:
        raise ValueError("acceptance requires an exact configured real Android target")
    root.mkdir(parents=True, exist_ok=False)
    selection = SafeAcceptanceSelection(deviceProfileId=device_profile_id)
    probe = AndroidContentProbe()
    scenario_evidence: list[AndroidServiceScenarioEvidence] = []
    captured: list[Any] = []
    for scenario_id in REQUIRED_SCENARIOS:
        evidence, documents = _run_scenario(
            root / scenario_id.value,
            scenario_id=scenario_id,
            profiles=profiles,
            device_profile_id=device_profile_id,
            device_profile_config=device_profile_config,
            probe=probe,
            probe_device=session.device,
            x=x,
            y=y,
            timeout_seconds=timeout_seconds,
        )
        scenario_evidence.append(evidence)
        captured.extend(documents)
    config_path = device_profile_config.expanduser().resolve()
    scanned = _scan_campaign(
        tuple(root / item.value for item in REQUIRED_SCENARIOS),
        tuple(captured),
        forbidden_values=(
            session.serial,
            str(config_path),
            str(root),
            profile.binding_fingerprint,
            profile.target_key,
        ),
    )
    command = (
        "uv run python scripts/studio_benchmark_android_service_acceptance.py run "
        "--confirm-real-android --device-profile-id <safe-profile-id> "
        "--device-profile-config $ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG "
        "--workspace-root temp/studio-benchmark-android-service/<campaign-id>"
    )
    summary = StudioBenchmarkAndroidServiceAcceptanceSummaryV1(
        selection=selection,
        scenarios=tuple(scenario_evidence),
        commands=(
            AcceptanceCommandEvidence(
                suiteId="real-android-service-matrix",
                command=command,
                observed=(
                    "positive PASS and controlled evaluator FAIL closed with "
                    "terminal restart non-replay"
                ),
                verification="passed",
            ),
        ),
        scannedDocuments=scanned + 1,
        privateValuesFound=0,
        claimLimits=REQUIRED_CLAIM_LIMITS,
    )
    assert_forbidden_values_absent(
        summary.model_dump(mode="json", by_alias=True),
        forbidden_values=(
            session.serial,
            str(config_path),
            profile.binding_fingerprint,
            profile.target_key,
            str(root),
        ),
        field="Android service acceptance summary",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    """Build the explicit run/validate command parser.

    Returns:
        Configured narrow command parser.
    """
    parser = argparse.ArgumentParser(
        description="Run or validate Stage 5.6C-1 real-Android service acceptance."
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    validate = subcommands.add_parser("validate", help="validate one summary")
    validate.add_argument("summary", type=Path)
    run = subcommands.add_parser("run", help="perform the opt-in real-device matrix")
    run.add_argument("--confirm-real-android", action="store_true", required=True)
    run.add_argument("--device-profile-id", required=True)
    run.add_argument("--device-profile-config", type=Path, required=True)
    run.add_argument("--workspace-root", type=Path, required=True)
    run.add_argument("--x", type=int, default=540)
    run.add_argument("--y", type=int, default=2052)
    run.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Validate a summary or execute the explicitly confirmed campaign.

    Args:
        argv: Optional arguments excluding the executable name.

    Raises:
        OSError: Required local resources cannot be read or written.
        ValueError: Inputs or evidence violate the acceptance contract.

    Returns:
        Zero only after the requested operation completes successfully.
    """
    args = _parser().parse_args(argv)
    if args.command == "validate":
        summary = validate_summary_file(args.summary)
        print(
            json.dumps(
                {
                    "schemaVersion": summary.schema_version,
                    "campaignVersion": summary.campaign_version,
                    "scenarioCount": len(summary.scenarios),
                    "verification": "passed",
                    "realDeviceEvidence": True,
                },
                sort_keys=True,
            )
        )
        return 0
    workspace = _safe_disposable_root(args.workspace_root)
    summary = run_campaign(
        device_profile_id=args.device_profile_id,
        device_profile_config=args.device_profile_config,
        workspace_root=workspace,
        x=args.x,
        y=args.y,
        timeout_seconds=args.timeout_seconds,
    )
    destination = write_summary(summary, workspace / "acceptance-summary.json")
    print(
        json.dumps(
            {
                "schemaVersion": summary.schema_version,
                "campaignVersion": summary.campaign_version,
                "scenarioCount": len(summary.scenarios),
                "verification": "passed",
                "summary": destination.relative_to(ROOT).as_posix(),
                "realDeviceEvidence": True,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
