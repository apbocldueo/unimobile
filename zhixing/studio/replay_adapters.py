"""Versioned native and legacy source adapters for Studio Replay."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Mapping

import yaml

from zhixing.benchmark.reporting.safety import safe_export
from zhixing.graph import AgentGraph, load_graph_yaml

from .replay_contracts import (
    ReplayImportArtifact,
    ReplayImportCandidate,
    ReplayImportError,
)
from .replay_models import (
    NormalizedReplayMoment,
    ReplayAction,
    ReplayArtifactDescriptor,
    ReplayBenchmarkContext,
    ReplayBenchmarkPhase,
    ReplayEvidenceAvailability,
    ReplayEvidenceEnvelope,
    ReplayIntegrityDiagnostic,
    ReplayObservation,
    ReplayRunResultSummary,
    ReplayRunSnapshot,
)
from .evidence_origin import replay_import_origin


REPLAY_PACKAGE_SCHEMA_VERSION = 1
_MAX_PACKAGE_MEMBERS = 10_000
_MAX_PACKAGE_MEMBER_BYTES = 512 * 1024 * 1024
_MAX_PACKAGE_BYTES = 4 * 1024 * 1024 * 1024
_ALLOWED_CONTENT_TYPES = {
    "application/json",
    "application/jsonl",
    "application/xml",
    "application/zip",
    "image/jpeg",
    "image/png",
    "text/plain",
}


def _sha256_bytes(content: bytes) -> str:
    """Return a prefixed SHA-256 digest.

    Args:
        content (bytes): Content to hash.

    Raises:
        None.

    Returns:
        str: Prefixed digest.
    """
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _sha256_file(path: Path) -> str:
    """Hash one regular file without exposing its host path.

    Args:
        path (Path): File to hash.

    Raises:
        OSError: File cannot be read.

    Returns:
        str: Prefixed SHA-256 digest.
    """
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _stable_id(prefix: str, *parts: object) -> str:
    """Build one deterministic opaque identifier.

    Args:
        prefix (str): Non-sensitive identifier namespace.
        *parts (object): Stable semantic identity parts.

    Raises:
        None.

    Returns:
        str: Prefix plus 32 lowercase hexadecimal characters.
    """
    payload = "\x1f".join(str(item) for item in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
    return f"{prefix}-{digest}"


def _safe_member(reference: str) -> PurePosixPath:
    """Validate one bundle or artifact relative member.

    Args:
        reference (str): POSIX-style relative member.

    Raises:
        ReplayImportError: Member is absolute, blank, or traversing.

    Returns:
        PurePosixPath: Validated member.
    """
    pure = PurePosixPath(str(reference))
    if not pure.parts or pure.is_absolute() or ".." in pure.parts:
        raise ReplayImportError(
            "studio.replay.path_unsafe",
            "Replay source contains an unsafe relative member",
        )
    return pure


def _content_type(reference: str) -> str:
    """Infer an allowlisted replay artifact media type.

    Args:
        reference (str): Safe relative artifact reference.

    Raises:
        ReplayImportError: Media type is unsupported.

    Returns:
        str: Allowlisted content type.
    """
    suffix = PurePosixPath(reference).suffix.lower()
    if suffix == ".jsonl":
        selected = "application/jsonl"
    elif suffix == ".xml":
        selected = "application/xml"
    else:
        selected = mimetypes.guess_type(reference)[0] or "application/octet-stream"
    if selected not in _ALLOWED_CONTENT_TYPES:
        raise ReplayImportError(
            "studio.replay.content_type_unsupported",
            "Replay artifact content type is unsupported",
        )
    return selected


def _sanitize_native_envelope(
    envelope: ReplayEvidenceEnvelope,
) -> ReplayEvidenceEnvelope:
    """Sanitize native package diagnostics without altering graph semantics.

    Args:
        envelope (ReplayEvidenceEnvelope): Strict decoded package envelope.

    Raises:
        ValueError: Sanitized values violate Replay contracts.

    Returns:
        ReplayEvidenceEnvelope: Safe persistence and HTTP representation.
    """
    snapshot = envelope.snapshot.model_copy(
        update={
            "presentation": (
                safe_export(envelope.snapshot.presentation)
                if envelope.snapshot.presentation is not None
                else None
            ),
            "source_map": tuple(safe_export(envelope.snapshot.source_map)),
            "capability_document": (
                safe_export(envelope.snapshot.capability_document)
                if envelope.snapshot.capability_document is not None
                else None
            ),
        }
    )
    result = envelope.result.model_copy(
        update={
            "error": safe_export(envelope.result.error),
            "usage": safe_export(envelope.result.usage),
        }
    )
    moments = tuple(
        item.model_copy(update={"payload": safe_export(item.payload)})
        for item in envelope.moments
    )
    observations = tuple(
        item.model_copy(
            update={
                "device_id": safe_export({"device_id": item.device_id})[
                    "device_id"
                ],
                "overlay": tuple(safe_export(item.overlay)),
            }
        )
        for item in envelope.observations
    )
    actions = tuple(
        item.model_copy(
            update={
                "message": safe_export(item.message),
                "error": safe_export(item.error),
            }
        )
        for item in envelope.actions
    )
    benchmark = envelope.benchmark
    if benchmark is not None:
        benchmark = benchmark.model_copy(
            update={
                "phases": tuple(
                    item.model_copy(
                        update={
                            "message": safe_export(item.message),
                            "evidence": safe_export(item.evidence),
                        }
                    )
                    for item in benchmark.phases
                ),
                "evaluation": (
                    safe_export(benchmark.evaluation)
                    if benchmark.evaluation is not None
                    else None
                ),
            }
        )
    return envelope.model_copy(
        update={
            "snapshot": snapshot,
            "result": result,
            "moments": moments,
            "observations": observations,
            "actions": actions,
            "benchmark": benchmark,
        }
    )


def _load_graph_snapshot(path: Path | None) -> AgentGraph | None:
    """Load an explicit graph body without component or device side effects.

    Args:
        path (Path | None): Optional JSON or graph-native YAML path.

    Raises:
        ReplayImportError: Graph file is invalid or compilation fails.
        OSError: Source cannot be read.

    Returns:
        AgentGraph | None: Parsed graph body when supplied.
    """
    if path is None:
        return None
    if path.suffix.lower() in {".yaml", ".yml"}:
        result = load_graph_yaml(path)
        if not result.is_success or result.graph is None:
            raise ReplayImportError(
                "studio.replay.graph_invalid",
                "Explicit AgentGraph snapshot is invalid",
            )
        return result.graph
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, Mapping) and raw.get("kind") == "agent_graph":
            raw = dict(raw)
            raw.pop("kind", None)
        return AgentGraph.model_validate(raw)
    except (json.JSONDecodeError, ValueError, TypeError) as error:
        raise ReplayImportError(
            "studio.replay.graph_invalid",
            "Explicit AgentGraph snapshot is invalid",
        ) from error


def _ordered_events(
    records: Iterable[Mapping[str, Any]],
) -> list[tuple[str, Mapping[str, Any]]]:
    """Flatten lifecycle records while retaining Benchmark/Graph nesting.

    Args:
        records (Iterable[Mapping[str, Any]]): Ordered trajectory records.

    Raises:
        ReplayImportError: A record has an invalid lifecycle shape.

    Returns:
        list[tuple[str, Mapping[str, Any]]]: Source-tagged causal events.
    """
    ordered: list[tuple[str, Mapping[str, Any]]] = []
    for record in sorted(records, key=lambda item: int(item.get("record_index", 0))):
        lifecycle = sorted(
            [
                item
                for item in record.get("lifecycle_events", ())
                if isinstance(item, Mapping)
            ],
            key=lambda item: int(item.get("sequence", 0)),
        )
        if record.get("phase") == "agent":
            starts = [item for item in lifecycle if item.get("kind") == "start"]
            terminals = [item for item in lifecycle if item.get("kind") != "start"]
            ordered.extend(("benchmark_lifecycle", item) for item in starts)
            graph = record.get("agent_graph")
            if isinstance(graph, Mapping):
                events = sorted(
                    [
                        item
                        for item in graph.get("events", ())
                        if isinstance(item, Mapping)
                    ],
                    key=lambda item: int(item.get("sequence", 0)),
                )
                ordered.extend(("agent_graph", item) for item in events)
            ordered.extend(("benchmark_lifecycle", item) for item in terminals)
        else:
            ordered.extend(("benchmark_lifecycle", item) for item in lifecycle)
    return ordered


def _declared_sequence_events(
    records: Iterable[Mapping[str, Any]],
) -> list[tuple[str, Mapping[str, Any]]]:
    """Collect source events in their declared file order for diagnostics.

    Args:
        records (Iterable[Mapping[str, Any]]): Trajectory records.

    Raises:
        None.

    Returns:
        list[tuple[str, Mapping[str, Any]]]: Unsorted source-tagged events.
    """
    declared: list[tuple[str, Mapping[str, Any]]] = []
    for record in sorted(records, key=lambda item: int(item.get("record_index", 0))):
        lifecycle = [
            item
            for item in record.get("lifecycle_events", ())
            if isinstance(item, Mapping)
        ]
        declared.extend(("benchmark_lifecycle", item) for item in lifecycle)
        graph = record.get("agent_graph")
        if isinstance(graph, Mapping):
            declared.extend(
                ("agent_graph", item)
                for item in graph.get("events", ())
                if isinstance(item, Mapping)
            )
    return declared


def _sequence_diagnostics(
    events: Iterable[tuple[str, Mapping[str, Any]]],
) -> tuple[tuple[ReplayIntegrityDiagnostic, ...], str]:
    """Detect source-local sequence gaps and conflicts.

    Args:
        events (Iterable[tuple[str, Mapping[str, Any]]]): Causal source events.

    Raises:
        None.

    Returns:
        tuple[tuple[ReplayIntegrityDiagnostic, ...], str]: Diagnostics and
        complete/partial integrity state.
    """
    diagnostics: list[ReplayIntegrityDiagnostic] = []
    seen: dict[tuple[str, int], str] = {}
    last: dict[str, int] = {}
    for source, event in events:
        sequence = int(event.get("sequence", 0))
        fingerprint = _sha256_bytes(
            json.dumps(safe_export(event), sort_keys=True).encode("utf-8")
        )
        identity = (source, sequence)
        if identity in seen:
            diagnostics.append(
                ReplayIntegrityDiagnostic(
                    code=(
                        "studio.replay.sequence_duplicate"
                        if seen[identity] == fingerprint
                        else "studio.replay.sequence_conflict"
                    ),
                    message="Replay source sequence repeats",
                    severity=(
                        "warning" if seen[identity] == fingerprint else "error"
                    ),
                    source=source,
                )
            )
            continue
        previous = last.get(source)
        if previous is not None and sequence > previous + 1:
            diagnostics.append(
                ReplayIntegrityDiagnostic(
                    code="studio.replay.sequence_gap",
                    message="Replay source sequence has a gap",
                    severity="warning",
                    source=source,
                )
            )
        if previous is not None and sequence < previous:
            diagnostics.append(
                ReplayIntegrityDiagnostic(
                    code="studio.replay.sequence_order",
                    message="Replay source sequence moved backwards",
                    severity="error",
                    source=source,
                )
            )
        seen[identity] = fingerprint
        last[source] = max(sequence, previous or sequence)
    state = "complete" if not diagnostics else "partial"
    return tuple(diagnostics), state


class NativeReplayPackageAdapter:
    """Read integrity-checked native Replay ZIP packages."""

    def load(self, source: Path, **options: object) -> ReplayImportCandidate:
        """Parse a native Replay package without extracting unsafe members.

        Args:
            source (Path): Explicit local ZIP package.
            **options (object): Reserved adapter options, currently unused.

        Raises:
            ReplayImportError: Package schema, members, or hashes are invalid.
            OSError: Package cannot be read.

        Returns:
            ReplayImportCandidate: Verified envelope and ZIP-member sources.
        """
        del options
        package = Path(source).expanduser().resolve()
        try:
            with zipfile.ZipFile(package, "r") as archive:
                infos = {item.filename: item for item in archive.infolist()}
                if (
                    len(infos) > _MAX_PACKAGE_MEMBERS
                    or sum(item.file_size for item in infos.values())
                    > _MAX_PACKAGE_BYTES
                ):
                    raise ReplayImportError(
                        "studio.replay.package_too_large",
                        "Replay package exceeds bounded import limits",
                    )
                if "replay-manifest.json" not in infos:
                    raise ReplayImportError(
                        "studio.replay.manifest_missing",
                        "Replay package manifest is missing",
                    )
                for info in infos.values():
                    _safe_member(info.filename)
                    if (
                        info.is_dir()
                        or info.file_size > _MAX_PACKAGE_MEMBER_BYTES
                        or (info.external_attr >> 16) & 0o170000 == 0o120000
                    ):
                        raise ReplayImportError(
                            "studio.replay.member_unsafe",
                            "Replay package contains a directory or symlink member",
                        )
                manifest = json.loads(archive.read("replay-manifest.json"))
                if (
                    not isinstance(manifest, Mapping)
                    or manifest.get("schemaVersion") != REPLAY_PACKAGE_SCHEMA_VERSION
                    or manifest.get("kind") != "studio_replay_package"
                ):
                    raise ReplayImportError(
                        "studio.replay.schema_unsupported",
                        "Replay package schema is unsupported",
                    )
                members = manifest.get("members")
                if not isinstance(members, Mapping):
                    raise ReplayImportError(
                        "studio.replay.manifest_invalid",
                        "Replay package members are invalid",
                    )
                declared = set(str(item) for item in members) | {
                    "replay-manifest.json"
                }
                if declared != set(infos):
                    raise ReplayImportError(
                        "studio.replay.members_undeclared",
                        "Replay package contains undeclared or missing members",
                    )
                for name, expected in members.items():
                    _safe_member(str(name))
                    if not isinstance(expected, Mapping):
                        raise ReplayImportError(
                            "studio.replay.manifest_invalid",
                            "Replay package member metadata is invalid",
                        )
                    content = archive.read(str(name))
                    if (
                        _sha256_bytes(content) != expected.get("sha256")
                        or len(content) != expected.get("size")
                    ):
                        raise ReplayImportError(
                            "studio.replay.hash_mismatch",
                            "Replay package member failed integrity verification",
                        )
                envelope = ReplayEvidenceEnvelope.model_validate(
                    json.loads(archive.read("envelope.json"))
                )
                if envelope.snapshot.agent_graph is not None:
                    try:
                        graph = AgentGraph.model_validate(
                            envelope.snapshot.agent_graph
                        )
                    except ValueError as error:
                        raise ReplayImportError(
                            "studio.replay.graph_invalid",
                            "Replay package AgentGraph snapshot is invalid",
                        ) from error
                    if graph.canonical_hash() != envelope.snapshot.canonical_hash:
                        raise ReplayImportError(
                            "studio.replay.graph_identity_mismatch",
                            "Replay package AgentGraph hash is inconsistent",
                        )
                envelope = _sanitize_native_envelope(envelope)
                envelope = envelope.model_copy(
                    update={
                        "evidence_origin": (
                            envelope.evidence_origin.with_acquisition(
                                "imported_excerpt"
                            )
                        )
                    }
                )
        except (zipfile.BadZipFile, KeyError, json.JSONDecodeError) as error:
            raise ReplayImportError(
                "studio.replay.package_invalid",
                "Replay package cannot be decoded",
            ) from error

        imports: dict[str, ReplayImportArtifact] = {}
        for descriptor in envelope.artifacts:
            if descriptor.availability not in {"available", "redacted"}:
                continue
            if descriptor.content_type not in _ALLOWED_CONTENT_TYPES:
                raise ReplayImportError(
                    "studio.replay.content_type_unsupported",
                    "Replay artifact content type is unsupported",
                )
            member = f"artifacts/{descriptor.artifact_id}"
            if member not in members:
                raise ReplayImportError(
                    "studio.replay.artifact_member_missing",
                    "Replay package artifact member is missing",
                )
            imports[descriptor.artifact_id] = ReplayImportArtifact(
                descriptor=descriptor,
                source_path=package,
                bundle_member=member,
            )
        return ReplayImportCandidate(envelope=envelope, artifacts=imports)


class LegacyBenchmarkReplayAdapter:
    """Adapt one explicit Benchmark task-run directory into Replay V1."""

    def load(self, source: Path, **options: object) -> ReplayImportCandidate:
        """Load a legacy result/trajectory plus explicit artifact and graph roots.

        Args:
            source (Path): Directory containing benchmark-result.json and
                trajectory.jsonl.
            **options (object): ``artifact_root`` (Path), ``graph_snapshot``
                (Path), and optional ``provenance``.

        Raises:
            ReplayImportError: Source facts are missing, unsafe, or inconsistent.
            OSError: Explicit files cannot be read.

        Returns:
            ReplayImportCandidate: Unified safe Replay evidence.
        """
        run_dir = Path(source).expanduser().resolve()
        artifact_option = options.get("artifact_root")
        artifact_root = (
            Path(artifact_option).expanduser().resolve()
            if artifact_option is not None
            else None
        )
        graph_option = options.get("graph_snapshot")
        graph_path = (
            Path(graph_option).expanduser().resolve()
            if graph_option is not None
            else None
        )
        provenance = str(options.get("provenance") or "legacy_benchmark_import")
        result_option = options.get("benchmark_result")
        result_path = (
            Path(result_option).expanduser().resolve()
            if result_option is not None
            else run_dir / "benchmark-result.json"
        )
        trajectory_path = run_dir / "trajectory.jsonl"
        try:
            document = json.loads(result_path.read_text(encoding="utf-8"))
            result = (
                document.get("result", document)
                if isinstance(document, Mapping)
                else None
            )
            if not isinstance(result, Mapping):
                raise ReplayImportError(
                    "studio.replay.result_invalid",
                    "Benchmark result document is invalid",
                )
            records = [
                json.loads(line)
                for line in trajectory_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (FileNotFoundError, json.JSONDecodeError) as error:
            raise ReplayImportError(
                "studio.replay.legacy_source_invalid",
                "Legacy Benchmark source is missing or invalid",
            ) from error
        if not all(isinstance(item, Mapping) for item in records):
            raise ReplayImportError(
                "studio.replay.trajectory_invalid",
                "Legacy trajectory records must be objects",
            )

        run_id = str(result.get("task_run_id") or "")
        if not run_id or run_dir.name != run_id:
            raise ReplayImportError(
                "studio.replay.run_identity_invalid",
                "Legacy source run identity is missing or inconsistent",
            )
        agent_result = result.get("agent_result")
        if not isinstance(agent_result, Mapping):
            agent_result = {}
        identities = result.get("identities")
        if not isinstance(identities, Mapping):
            identities = {}
        expected_graph_hash = str(identities.get("agent_graph") or "") or None
        graph = _load_graph_snapshot(graph_path)
        graph_body: dict[str, Any] | None = None
        if graph is not None:
            actual_hash = graph.canonical_hash()
            if expected_graph_hash is not None and actual_hash != expected_graph_hash:
                raise ReplayImportError(
                    "studio.replay.graph_identity_mismatch",
                    "AgentGraph snapshot does not match the recorded run identity",
                )
            expected_graph_hash = actual_hash
            graph_body = graph.model_dump(mode="json", exclude_none=True)

        graph_record = next(
            (
                item.get("agent_graph")
                for item in records
                if item.get("phase") == "agent"
                and isinstance(item.get("agent_graph"), Mapping)
            ),
            {},
        )
        observations_raw = (
            graph_record.get("observations", ())
            if isinstance(graph_record, Mapping)
            else ()
        )
        actions_raw = (
            graph_record.get("actions", ())
            if isinstance(graph_record, Mapping)
            else ()
        )
        artifact_imports: dict[str, ReplayImportArtifact] = {}
        descriptors: dict[str, ReplayArtifactDescriptor] = {}

        def register_artifact(reference: object, kind: str) -> str | None:
            """Register one safe legacy relative artifact reference.

            Args:
                reference (object): Candidate safe relative reference.
                kind (str): Reader-facing artifact kind.

            Raises:
                ReplayImportError: Reference or media type is unsafe.

            Returns:
                str | None: Opaque artifact identity, if declared.
            """
            if not isinstance(reference, str) or not reference:
                return None
            pure = _safe_member(reference)
            artifact_id = _stable_id("artifact", run_id, pure.as_posix())
            content_type = _content_type(pure.as_posix())
            source_path = (
                artifact_root.joinpath(*pure.parts)
                if artifact_root is not None
                else None
            )
            available = (
                source_path is not None
                and source_path.is_file()
                and not source_path.is_symlink()
            )
            descriptor = ReplayArtifactDescriptor(
                artifact_id=artifact_id,
                kind=kind,
                availability="available" if available else "missing",
                content_type=content_type,
                size=source_path.stat().st_size if available else 0,
                sha256=_sha256_file(source_path) if available else None,
                provenance=provenance,
            )
            descriptors[artifact_id] = descriptor
            if available and source_path is not None and artifact_root is not None:
                resolved = source_path.resolve()
                if artifact_root != resolved and artifact_root not in resolved.parents:
                    raise ReplayImportError(
                        "studio.replay.path_escape",
                        "Legacy artifact escapes the trusted root",
                    )
                artifact_imports[artifact_id] = ReplayImportArtifact(
                    descriptor=descriptor,
                    source_path=source_path,
                    trusted_root=artifact_root,
                )
            return artifact_id

        observations: list[ReplayObservation] = []
        screenshot_ids: dict[str, str] = {}
        observation_by_ref: dict[str, str] = {}
        for index, item in enumerate(observations_raw):
            if not isinstance(item, Mapping):
                continue
            screenshot_ref = item.get("screenshot_artifact")
            ui_ref = item.get("ui_artifact")
            screenshot_id = register_artifact(screenshot_ref, "screenshot")
            ui_id = register_artifact(ui_ref, "ui_xml")
            if isinstance(screenshot_ref, str) and screenshot_id is not None:
                screenshot_ids[screenshot_ref] = screenshot_id
                observation_by_ref[screenshot_ref] = f"observation-{index:04d}"
            observations.append(
                ReplayObservation(
                    observation_id=f"observation-{index:04d}",
                    sequence=int(item.get("sequence", index)),
                    interaction_step=int(item.get("interaction_step", 0)),
                    screenshot_artifact_id=screenshot_id,
                    ui_artifact_id=ui_id,
                )
            )

        actions: list[ReplayAction] = []
        for index, item in enumerate(actions_raw):
            if not isinstance(item, Mapping):
                continue
            metadata = item.get("metadata")
            artifact_ref = (
                metadata.get("artifact") if isinstance(metadata, Mapping) else None
            )
            artifact_id = register_artifact(artifact_ref, "action")
            actions.append(
                ReplayAction(
                    action_id=f"action-{index:04d}",
                    sequence=index,
                    interaction_step=index,
                    status=str(item.get("status") or ""),
                    action_type=str(item.get("action_type") or ""),
                    effect_performed=bool(item.get("effect_performed", False)),
                    effect_kind=str(item.get("effect_kind") or ""),
                    terminal_status=(
                        str(item.get("terminal_status"))
                        if item.get("terminal_status") is not None
                        else None
                    ),
                    message=str(item.get("message") or "")[:1000],
                    error=str(item.get("error") or "")[:1000],
                    artifact_id=artifact_id,
                )
            )

        ordered = _ordered_events(records)
        diagnostics, integrity_state = _sequence_diagnostics(
            _declared_sequence_events(records)
        )
        action_index = 0
        moments: list[NormalizedReplayMoment] = []
        for causal_index, (source_kind, raw_event) in enumerate(ordered):
            event = safe_export(raw_event)
            if not isinstance(event, Mapping):
                continue
            payload = event.get("payload")
            payload = dict(payload) if isinstance(payload, Mapping) else {}
            screenshot_ref = _find_nested_value(payload, "screenshot_artifact")
            observation_id = (
                observation_by_ref.get(str(screenshot_ref))
                if screenshot_ref is not None
                else None
            )
            action_id: str | None = None
            if (
                source_kind == "agent_graph"
                and event.get("kind") == "complete"
                and "action_executor" in str(event.get("role") or "")
                and action_index < len(actions)
            ):
                action_id = actions[action_index].action_id
                action_index += 1
            artifact_ids = tuple(
                item
                for item in (
                    screenshot_ids.get(str(screenshot_ref))
                    if screenshot_ref is not None
                    else None,
                    next(
                        (
                            action.artifact_id
                            for action in actions
                            if action.action_id == action_id
                        ),
                        None,
                    ),
                )
                if item is not None
            )
            moments.append(
                NormalizedReplayMoment(
                    moment_id=_stable_id(
                        "moment",
                        run_id,
                        source_kind,
                        event.get("sequence", causal_index),
                        event.get("kind", ""),
                        causal_index,
                    ),
                    causal_index=causal_index,
                    source_kind=source_kind,
                    source_sequence=int(event.get("sequence", 0)),
                    timestamp=(
                        float(event["timestamp"])
                        if event.get("timestamp") is not None
                        else None
                    ),
                    phase=str(event.get("phase") or ""),
                    kind=str(event.get("kind") or ""),
                    role=str(event.get("role") or ""),
                    component=str(event.get("component") or ""),
                    node_id=str(event.get("node_id") or ""),
                    node_path=str(event.get("node_path") or ""),
                    activation_id=str(event.get("activation_id") or ""),
                    parent_activation_id=str(
                        event.get("parent_activation_id") or ""
                    ),
                    loop_path=str(event.get("loop_path") or ""),
                    loop_iteration=(
                        int(event["loop_iteration"])
                        if event.get("loop_iteration") is not None
                        else None
                    ),
                    interaction_step=int(event.get("interaction_step", 0)),
                    duration_ms=(
                        float(event["duration_ms"])
                        if event.get("duration_ms") is not None
                        else None
                    ),
                    payload=payload,
                    observation_id=observation_id,
                    action_id=action_id,
                    artifact_ids=artifact_ids,
                )
            )

        stages = result.get("stages")
        phases = tuple(
            ReplayBenchmarkPhase(
                phase=str(item.get("phase") or ""),
                status=str(item.get("status") or ""),
                duration_ms=(
                    float(item["duration_ms"])
                    if item.get("duration_ms") is not None
                    else None
                ),
                error_code=str(item.get("error_code") or ""),
                message=str(item.get("message") or "")[:1000],
                evidence=safe_export(item.get("evidence") or {}),
            )
            for item in (stages if isinstance(stages, list) else ())
            if isinstance(item, Mapping)
        )
        evaluation = result.get("evaluation")
        benchmark = ReplayBenchmarkContext(
            experiment_id=str(result.get("experiment_id") or ""),
            task_id=str(result.get("task_id") or ""),
            agent_id=str(result.get("agent_id") or ""),
            repeat=int(result.get("repeat", 0)),
            outcome=str(result.get("outcome") or "invalid"),
            identities={
                str(key): str(value)
                for key, value in identities.items()
                if isinstance(value, str)
            },
            phases=phases,
            evaluation=(
                safe_export(evaluation) if isinstance(evaluation, Mapping) else None
            ),
        )
        screenshot_states = {
            item.availability
            for item in descriptors.values()
            if item.kind == "screenshot"
        }
        ui_states = {
            item.availability
            for item in descriptors.values()
            if item.kind == "ui_xml"
        }
        availability = {
            "agentGraph": ReplayEvidenceAvailability(
                state="available" if graph_body is not None else "not_captured",
                reason_code=(
                    "" if graph_body is not None else "studio.replay.graph_not_captured"
                ),
            ),
            "screenshots": ReplayEvidenceAvailability(
                state=(
                    "available"
                    if "available" in screenshot_states
                    else "missing"
                    if screenshot_states
                    else "not_captured"
                ),
            ),
            "uiXml": ReplayEvidenceAvailability(
                state=(
                    "available"
                    if "available" in ui_states
                    else "missing"
                    if ui_states
                    else "not_captured"
                ),
            ),
            "modelResponse": ReplayEvidenceAvailability(
                state="not_captured",
                reason_code="studio.replay.legacy_debug_not_captured",
            ),
            "prompt": ReplayEvidenceAvailability(
                state="excluded",
                reason_code="studio.replay.prompt_not_in_legacy_export",
            ),
            "debugPayload": ReplayEvidenceAvailability(
                state="not_captured",
                reason_code="studio.replay.legacy_debug_not_captured",
            ),
        }
        envelope = ReplayEvidenceEnvelope(
            run_id=run_id,
            imported_at=time.time_ns() // 1_000_000,
            provenance=provenance,
            evidence_origin=replay_import_origin(provenance),
            integrity_state=integrity_state,
            snapshot=ReplayRunSnapshot(
                agent_id=str(result.get("agent_id") or ""),
                contract_version=(
                    graph.contract_version if graph is not None else "1.1"
                ),
                canonical_hash=expected_graph_hash,
                graph_status="available" if graph_body is not None else "not_captured",
                agent_graph=graph_body,
                presentation=(
                    graph.presentation.model_dump(
                        mode="json",
                        exclude_none=True,
                    )
                    if graph is not None and graph.presentation is not None
                    else None
                ),
            ),
            result=ReplayRunResultSummary(
                status=str(agent_result.get("status") or "unknown"),
                kernel_status=str(agent_result.get("kernel_status") or ""),
                error=str(agent_result.get("error") or "")[:1000],
                step_count=int(agent_result.get("steps", 0)),
                activation_count=int(agent_result.get("activation_count", 0)),
                interaction_count=int(agent_result.get("interaction_count", 0)),
                usage=safe_export(agent_result.get("usage") or {}),
            ),
            moments=tuple(moments),
            observations=tuple(observations),
            actions=tuple(actions),
            benchmark=benchmark,
            artifacts=tuple(
                descriptors[key] for key in sorted(descriptors)
            ),
            availability=availability,
            integrity=diagnostics,
        )
        return ReplayImportCandidate(
            envelope=envelope,
            artifacts=artifact_imports,
        )


def _find_nested_value(value: object, key: str) -> object | None:
    """Find the first named value in a bounded JSON-compatible structure.

    Args:
        value (object): Candidate mapping/list structure.
        key (str): Exact mapping key to find.

    Raises:
        None.

    Returns:
        object | None: First matching value.
    """
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for item in value.values():
            found = _find_nested_value(item, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_nested_value(item, key)
            if found is not None:
                return found
    return None


__all__ = [
    "LegacyBenchmarkReplayAdapter",
    "NativeReplayPackageAdapter",
    "REPLAY_PACKAGE_SCHEMA_VERSION",
]
