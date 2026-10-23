"""Strict DTOs for revision-bound Benchmark authoring analysis."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any, Iterable, Literal, Mapping

from pydantic import Field, StrictBool, StrictInt, field_validator, model_validator

from zhixing.benchmark import BenchmarkDiagnostic, canonical_hash

from .benchmark_authoring_models import (
    STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS,
    StudioBenchmarkAuthoringDocumentV1,
    validate_benchmark_authoring_revision_id,
)
from .models import StudioModel


STUDIO_BENCHMARK_ANALYSIS_MAX_AGENTS = 16
STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS = 100
STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES = 10_000

_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_SPLIT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
_ABSOLUTE_PATH = re.compile(
    r"(?:^|[\s\"'(])(?:/[A-Za-z0-9_.~/-]+|[A-Za-z]:[\\/][^\s\"']+)"
)
_CONTENT_ID = re.compile(r"benchmark-content-[a-f0-9]{64}")


def _safe_text(value: object, *, limit: int) -> str:
    """Return bounded single-line analysis text without private capabilities.

    Args:
        value: Candidate text-like value.
        limit: Maximum returned character count.

    Raises:
        None.

    Returns:
        Redacted bounded text.
    """
    text = str(value).replace("\r", " ").replace("\n", " ")
    text = _ABSOLUTE_PATH.sub(" [redacted-path]", text)
    return _CONTENT_ID.sub("[redacted-content]", text)[:limit]


def _safe_member_path(value: str, inventory: frozenset[str]) -> str | None:
    """Return one declared safe Package-relative member path.

    Args:
        value: Candidate Core diagnostic source.
        inventory: Exact revision closed member inventory.

    Raises:
        None.

    Returns:
        The path when it is normalized and declared, otherwise ``None``.
    """
    if value not in inventory or "\x00" in value or "\\" in value:
        return None
    logical = PurePosixPath(value)
    if (
        logical.is_absolute()
        or ".." in logical.parts
        or "." in logical.parts
        or logical.as_posix() != value
    ):
        return None
    return value


def _stable_identity(value: str) -> str:
    """Validate one bounded Studio resource identity.

    Args:
        value: Candidate identity.

    Raises:
        ValueError: Identity is malformed.

    Returns:
        Validated identity.
    """
    if _STABLE_ID.fullmatch(value) is None:
        raise ValueError("identity must be stable and bounded")
    return value


def _split_name(value: str) -> str:
    """Validate one explicit Benchmark split name.

    Args:
        value: Candidate split name.

    Raises:
        ValueError: Split name is malformed.

    Returns:
        Validated split name.
    """
    if _SPLIT.fullmatch(value) is None:
        raise ValueError("split must be explicit, stable, and bounded")
    return value


class StudioBenchmarkAuthoringValidationRequestV1(StudioModel):
    """Strict request to validate one exact current authoring revision."""

    schema_version: Literal[1] = 1
    revision_id: str
    split: str

    @field_validator("revision_id")
    @classmethod
    def _revision(cls, value: str) -> str:
        """Validate the exact immutable authoring revision identity.

        Args:
            value: Candidate revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("split")
    @classmethod
    def _split(cls, value: str) -> str:
        """Validate the explicitly selected split.

        Args:
            value: Candidate split name.

        Raises:
            ValueError: Split name is malformed.

        Returns:
            Validated split name.
        """
        return _split_name(value)

    @property
    def fingerprint(self) -> str:
        """Return a deterministic validation request fingerprint.

        Args:
            None.

        Raises:
            None.

        Returns:
            Canonical SHA-256 request fingerprint.
        """
        return canonical_hash(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class StudioBenchmarkAuthoringAgentRevisionSelectionV1(StudioModel):
    """One exact saved Agent revision selected for authoring dry-run."""

    agent_id: str
    revision_id: str

    @field_validator("agent_id", "revision_id")
    @classmethod
    def _identity(cls, value: str) -> str:
        """Validate an Agent or Agent revision identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _stable_identity(value)


class StudioBenchmarkAuthoringDryRunRequestV1(StudioModel):
    """Strict request for deterministic revision-bound dry-run planning."""

    schema_version: Literal[1] = 1
    revision_id: str
    split: str
    task_ids: tuple[str, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS,
    )
    agent_revisions: tuple[
        StudioBenchmarkAuthoringAgentRevisionSelectionV1, ...
    ] = Field(
        min_length=1,
        max_length=STUDIO_BENCHMARK_ANALYSIS_MAX_AGENTS,
    )

    @field_validator("revision_id")
    @classmethod
    def _revision(cls, value: str) -> str:
        """Validate the exact immutable authoring revision identity.

        Args:
            value: Candidate revision identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated revision identity.
        """
        return validate_benchmark_authoring_revision_id(value)

    @field_validator("split")
    @classmethod
    def _split(cls, value: str) -> str:
        """Validate the explicitly selected split.

        Args:
            value: Candidate split name.

        Raises:
            ValueError: Split is malformed.

        Returns:
            Validated split name.
        """
        return _split_name(value)

    @field_validator("task_ids")
    @classmethod
    def _tasks(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        """Require unique bounded task identities while allowing all-tasks.

        Args:
            value: Explicit task identities, or an empty all-tasks selection.

        Raises:
            ValueError: A task identity is malformed or repeated.

        Returns:
            Original ordered task identities.
        """
        if any(not item.strip() or len(item) > 256 for item in value):
            raise ValueError("task identities must be non-blank and bounded")
        if len(value) != len(set(value)):
            raise ValueError("task identities must be unique")
        return value

    @model_validator(mode="after")
    def _unique_agents(self) -> "StudioBenchmarkAuthoringDryRunRequestV1":
        """Reject multiple revisions in one Agent comparison dimension.

        Args:
            None.

        Raises:
            ValueError: Agent identities are repeated.

        Returns:
            Validated dry-run request.
        """
        agent_ids = [item.agent_id for item in self.agent_revisions]
        if len(agent_ids) != len(set(agent_ids)):
            raise ValueError("Agent identities must be unique")
        return self

    @property
    def fingerprint(self) -> str:
        """Return a deterministic dry-run request fingerprint.

        Args:
            None.

        Raises:
            None.

        Returns:
            Canonical SHA-256 request fingerprint.
        """
        return canonical_hash(
            self.model_dump(mode="json", by_alias=True, exclude_none=True)
        )


class StudioBenchmarkAuthoringDiagnosticV1(StudioModel):
    """One safe field-addressable authoring analysis diagnostic."""

    code: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=1, max_length=500)
    severity: Literal["error", "warning", "info"] = "error"
    member_kind: Literal["manifest", "task", "protocol", "resource", "agent"]
    member_path: str | None = Field(default=None, max_length=512)
    field_path: tuple[str | int, ...] = ()
    task_id: str | None = Field(default=None, max_length=256)
    resource_id: str | None = Field(default=None, max_length=128)
    agent_id: str | None = Field(default=None, max_length=160)
    revision_id: str | None = Field(default=None, max_length=160)

    @field_validator("field_path")
    @classmethod
    def _bounded_path(
        cls,
        value: tuple[str | int, ...],
    ) -> tuple[str | int, ...]:
        """Bound diagnostic path depth and string segment length.

        Args:
            value: Candidate field path.

        Raises:
            ValueError: Path is too deep or contains an unsafe segment.

        Returns:
            Validated path.
        """
        if len(value) > 16:
            raise ValueError("diagnostic field path is too deep")
        for item in value:
            if isinstance(item, bool) or not isinstance(item, (str, int)):
                raise ValueError("diagnostic field path is invalid")
            if isinstance(item, str) and len(item) > 160:
                raise ValueError("diagnostic field path segment is too long")
        return value


class StudioBenchmarkAuthoringAnalysisIdentitiesV1(StudioModel):
    """Independently gated canonical identities from authoring validation."""

    package: str | None = Field(default=None, max_length=384)
    package_content: str | None = None
    benchmark_plan: str | None = None
    experiment_protocol: str | None = None

    @field_validator(
        "package_content",
        "benchmark_plan",
        "experiment_protocol",
    )
    @classmethod
    def _digest(cls, value: str | None) -> str | None:
        """Validate an optional canonical SHA-256 identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest or ``None``.
        """
        if value is not None and _DIGEST.fullmatch(value) is None:
            raise ValueError("canonical analysis identity is invalid")
        return value


class StudioBenchmarkVerifiedAgentRevisionV1(StudioModel):
    """Verified identity facts for one immutable Agent revision."""

    agent_id: str
    revision_id: str
    agent_graph_identity: str

    @field_validator("agent_id", "revision_id")
    @classmethod
    def _resource_identity(cls, value: str) -> str:
        """Validate an Agent resource identity.

        Args:
            value: Candidate identity.

        Raises:
            ValueError: Identity is malformed.

        Returns:
            Validated identity.
        """
        return _stable_identity(value)

    @field_validator("agent_graph_identity")
    @classmethod
    def _graph_identity(cls, value: str) -> str:
        """Validate the recomputed AgentGraph canonical identity.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("AgentGraph identity is invalid")
        return value


class StudioBenchmarkAuthoringScheduleEntryV1(StudioModel):
    """One deterministic definition-level dry-run schedule entry."""

    repeat: StrictInt = Field(ge=0)
    task_id: str = Field(min_length=1, max_length=256)
    agent_id: str = Field(min_length=1, max_length=160)
    seed: StrictInt = Field(ge=0)
    shared_instance_key: str = Field(min_length=1, max_length=768)


class StudioBenchmarkAuthoringBudgetV1(StudioModel):
    """Declared ExperimentProtocol execution budget projection."""

    max_interactions: StrictInt = Field(gt=0)
    max_activations: StrictInt = Field(gt=0)
    timeout_seconds: StrictInt = Field(gt=0)
    token_limit: StrictInt | None = Field(default=None, gt=0)
    require_observable_tokens: StrictBool = False


class StudioBenchmarkAuthoringOutputLayoutV1(StudioModel):
    """Safe relative placeholders for planned runtime output layout."""

    experiment_report: Literal[
        "<artifact-root>/<experiment-id>/experiment-report.json"
    ]
    run_report: Literal[
        "<artifact-root>/<experiment-id>/runs/<task-run-id>/run-report.json"
    ]
    trajectory: Literal[
        "<artifact-root>/<experiment-id>/runs/<task-run-id>/trajectory.jsonl"
    ]
    bundle: Literal["<artifact-root>/<experiment-id>/trajectory-bundle.zip"]


class StudioBenchmarkAuthoringValidationResultV1(StudioModel):
    """Revision-bound semantic validation facts for one current draft."""

    schema_version: Literal[1] = 1
    mode: Literal["validation"] = "validation"
    draft_id: str
    revision_id: str
    document_fingerprint: str
    split: str
    valid: StrictBool
    identities: StudioBenchmarkAuthoringAnalysisIdentitiesV1
    diagnostics: tuple[StudioBenchmarkAuthoringDiagnosticV1, ...] = ()
    diagnostics_truncated: StrictBool = False
    unverified_checks: tuple[str, ...] = ()
    execution_evidence: Literal[False] = False

    @field_validator("document_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        """Validate the bound authoring document fingerprint.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("authoring document fingerprint is invalid")
        return value


class StudioBenchmarkAuthoringDryRunResultV1(StudioModel):
    """Complete bounded deterministic dry-run facts for one current revision."""

    schema_version: Literal[1] = 1
    mode: Literal["side-effect-free-dry-run"] = "side-effect-free-dry-run"
    draft_id: str
    revision_id: str
    document_fingerprint: str
    split: str
    ok: StrictBool
    identities: StudioBenchmarkAuthoringAnalysisIdentitiesV1
    agent_revisions: tuple[StudioBenchmarkVerifiedAgentRevisionV1, ...] = ()
    schedule: tuple[StudioBenchmarkAuthoringScheduleEntryV1, ...] = Field(
        default=(),
        max_length=STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES,
    )
    budget: StudioBenchmarkAuthoringBudgetV1 | None = None
    fairness_warnings: tuple[str, ...] = ()
    output_layout: StudioBenchmarkAuthoringOutputLayoutV1 | None = None
    unverified_checks: tuple[str, ...] = ()
    diagnostics: tuple[StudioBenchmarkAuthoringDiagnosticV1, ...] = ()
    diagnostics_truncated: StrictBool = False
    execution_evidence: Literal[False] = False

    @field_validator("document_fingerprint")
    @classmethod
    def _fingerprint(cls, value: str) -> str:
        """Validate the bound authoring document fingerprint.

        Args:
            value: Candidate digest.

        Raises:
            ValueError: Digest is malformed.

        Returns:
            Validated digest.
        """
        if _DIGEST.fullmatch(value) is None:
            raise ValueError("authoring document fingerprint is invalid")
        return value

    @model_validator(mode="after")
    def _complete_or_empty_schedule(
        self,
    ) -> "StudioBenchmarkAuthoringDryRunResultV1":
        """Prevent failed dry-runs from carrying partial planning facts.

        Args:
            None.

        Raises:
            ValueError: A failed result contains schedule/output facts.

        Returns:
            Validated result.
        """
        if not self.ok and (
            self.schedule or self.budget is not None or self.output_layout is not None
        ):
            raise ValueError("failed dry-run cannot expose partial schedule facts")
        return self


def _task_origins(
    document: StudioBenchmarkAuthoringDocumentV1,
    split: str,
) -> tuple[tuple[str, int, str | None], ...]:
    """Build aggregate task-index provenance from the parsed authoring document.

    Args:
        document: Exact immutable authoring document.
        split: Explicit selected split.

    Raises:
        None: Invalid manifest fragments produce an empty or partial map.

    Returns:
        Package member, local index, and optional task identity per aggregate row.
    """
    splits = document.manifest.document.get("splits")
    if not isinstance(splits, Mapping):
        return ()
    selected = splits.get(split)
    if not isinstance(selected, Mapping):
        return ()
    files = selected.get("files")
    if not isinstance(files, (list, tuple)):
        return ()
    by_path = {item.path: item for item in document.task_files}
    origins: list[tuple[str, int, str | None]] = []
    for raw_path in files:
        if not isinstance(raw_path, str) or raw_path not in by_path:
            continue
        for index, raw_task in enumerate(by_path[raw_path].tasks):
            task_id = (
                str(raw_task.get("id"))
                if isinstance(raw_task, Mapping) and raw_task.get("id") is not None
                else None
            )
            origins.append((raw_path, index, task_id))
    return tuple(origins)


def project_authoring_diagnostics(
    diagnostics: Iterable[BenchmarkDiagnostic],
    *,
    document: StudioBenchmarkAuthoringDocumentV1,
    split: str,
) -> tuple[tuple[StudioBenchmarkAuthoringDiagnosticV1, ...], bool]:
    """Project Core diagnostics into bounded revision-addressable Studio facts.

    Args:
        diagnostics: Core Benchmark diagnostics to project.
        document: Exact immutable authoring document providing safe inventory.
        split: Explicit selected split used for aggregate task provenance.

    Raises:
        ValueError: A projected diagnostic violates the strict DTO.

    Returns:
        Bounded deterministic diagnostics and an explicit truncation flag.
    """
    task_paths = {item.path for item in document.task_files}
    protocol_paths = {item.path for item in document.protocol_files}
    resources_by_id = {item.id: item for item in document.resources}
    resources_by_index = tuple(document.resources)
    default_protocol = document.manifest.document.get("default_protocol")
    inventory = frozenset(
        {
            "benchmark.yaml",
            *task_paths,
            *protocol_paths,
            *(item.path for item in document.resources),
        }
    )
    origins = _task_origins(document, split)
    projected: list[StudioBenchmarkAuthoringDiagnosticV1] = []
    for item in diagnostics:
        source = item.source
        path = tuple(item.path)
        member_kind: Literal[
            "manifest", "task", "protocol", "resource", "agent"
        ] = "manifest"
        member_path: str | None = None
        task_id = item.task_id
        resource_id: str | None = None
        if source in task_paths:
            member_kind = "task"
            member_path = _safe_member_path(source, inventory)
        elif source in protocol_paths or source == "default-protocol":
            member_kind = "protocol"
            candidate = source if source in protocol_paths else default_protocol
            if isinstance(candidate, str):
                member_path = _safe_member_path(candidate, inventory)
        elif source in resources_by_id:
            member_kind = "resource"
            resource_id = source
            member_path = _safe_member_path(
                resources_by_id[source].path,
                inventory,
            )
        elif path and path[0] == "resources" and len(path) > 1:
            index = path[1]
            if isinstance(index, int) and 0 <= index < len(resources_by_index):
                resource = resources_by_index[index]
                member_kind = "resource"
                resource_id = resource.id
                member_path = _safe_member_path(resource.path, inventory)
                path = path[2:]
        if path and path[0] == "tasks" and len(path) > 1:
            aggregate_index = path[1]
            if isinstance(aggregate_index, int) and 0 <= aggregate_index < len(origins):
                origin_path, local_index, origin_task_id = origins[aggregate_index]
                member_kind = "task"
                member_path = _safe_member_path(origin_path, inventory)
                path = (local_index, *path[2:])
                task_id = task_id or origin_task_id
        projected.append(
            StudioBenchmarkAuthoringDiagnosticV1(
                code=_safe_text(item.code, limit=160),
                message=_safe_text(item.message, limit=500),
                severity=item.severity.value,
                member_kind=member_kind,
                member_path=member_path,
                field_path=tuple(
                    value
                    if isinstance(value, int)
                    else _safe_text(value, limit=160)
                    for value in path[:16]
                ),
                task_id=(
                    _safe_text(task_id, limit=256)
                    if task_id is not None
                    else None
                ),
                resource_id=resource_id,
            )
        )
    ordered = sorted(
        projected,
        key=lambda value: (
            value.severity,
            value.member_kind,
            value.member_path or "",
            tuple(str(part) for part in value.field_path),
            value.code,
            value.task_id or "",
            value.resource_id or "",
            value.message,
        ),
    )
    truncated = len(ordered) > STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS
    return (
        tuple(ordered[:STUDIO_BENCHMARK_AUTHORING_MAX_DIAGNOSTICS]),
        truncated,
    )


__all__ = [
    "STUDIO_BENCHMARK_ANALYSIS_MAX_AGENTS",
    "STUDIO_BENCHMARK_ANALYSIS_MAX_SCHEDULE_ENTRIES",
    "STUDIO_BENCHMARK_ANALYSIS_MAX_TASKS",
    "StudioBenchmarkAuthoringAgentRevisionSelectionV1",
    "StudioBenchmarkAuthoringAnalysisIdentitiesV1",
    "StudioBenchmarkAuthoringBudgetV1",
    "StudioBenchmarkAuthoringDiagnosticV1",
    "StudioBenchmarkAuthoringDryRunRequestV1",
    "StudioBenchmarkAuthoringDryRunResultV1",
    "StudioBenchmarkAuthoringOutputLayoutV1",
    "StudioBenchmarkAuthoringScheduleEntryV1",
    "StudioBenchmarkAuthoringValidationRequestV1",
    "StudioBenchmarkAuthoringValidationResultV1",
    "StudioBenchmarkVerifiedAgentRevisionV1",
    "project_authoring_diagnostics",
]
