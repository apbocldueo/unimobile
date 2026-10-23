"""Native Replay projection for durable Studio Benchmark TaskRuns."""

from __future__ import annotations

import json
import hashlib
from typing import Any

from zhixing.benchmark.identity import canonical_hash

from .benchmark_experiment_models import (
    StudioBenchmarkExperimentRecordV1,
    StudioBenchmarkTaskRunRecordV1,
)
from .benchmark_experiment_protocols import (
    StudioBenchmarkExperimentRepository,
)
from .benchmark_publication_models import (
    StudioBenchmarkArtifactAvailability,
    StudioBenchmarkManagedArtifactRecordV1,
)
from .benchmark_publication_protocols import (
    StudioBenchmarkManagedArtifactStore,
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


def _moment_id(run_id: str, index: int, kind: str) -> str:
    """Derive one stable opaque Replay moment identity.

    Args:
        run_id: Owning Replay identity.
        index: Causal moment index.
        kind: Stable event kind.

    Returns:
        Stable moment identity.
    """
    suffix = canonical_hash(
        {
            "contract": "native-benchmark-replay-moment-v1",
            "runId": run_id,
            "causalIndex": index,
            "kind": kind,
        }
    ).removeprefix("sha256:")[:32]
    return f"moment-{suffix}"


def _evidence_id(
    prefix: str,
    run_id: str,
    index: int,
    sequence: object,
) -> str:
    """Derive one stable observation or action identity.

    Args:
        prefix: Public identity prefix.
        run_id: Owning Replay identity.
        index: Source-local item index.
        sequence: Optional source sequence value.

    Returns:
        Stable opaque evidence identity.
    """
    suffix = canonical_hash(
        {
            "run": run_id,
            "index": index,
            "sequence": sequence,
            "kind": prefix,
        }
    ).removeprefix("sha256:")[:32]
    return f"{prefix}-{suffix}"


def _replay_availability(
    availability: StudioBenchmarkArtifactAvailability,
) -> str:
    """Map managed Benchmark availability into Replay vocabulary.

    Args:
        availability: Managed artifact state.

    Returns:
        Compatible Replay availability state.
    """
    mapping = {
        StudioBenchmarkArtifactAvailability.AVAILABLE: "available",
        StudioBenchmarkArtifactAvailability.EXCLUDED: "excluded",
        StudioBenchmarkArtifactAvailability.HIDDEN: "hidden",
        StudioBenchmarkArtifactAvailability.MISSING: "missing",
        StudioBenchmarkArtifactAvailability.CORRUPT: "corrupt",
        StudioBenchmarkArtifactAvailability.REDACTED: "redacted",
        StudioBenchmarkArtifactAvailability.TRUNCATED: "truncated",
    }
    return mapping.get(availability, "not_captured")


def _artifact_ids_for_value(
    value: object,
    references: dict[str, str],
) -> tuple[str, ...]:
    """Find managed identities referenced by one safe trajectory value.

    Args:
        value: Safe nested trajectory value.
        references: Runtime reference suffix to managed identity mapping.

    Returns:
        Sorted unique managed artifact identities.
    """
    found: set[str] = set()

    def visit(item: object) -> None:
        """Visit one nested JSON value.

        Args:
            item: Current nested value.

        Returns:
            None.
        """
        if isinstance(item, str):
            for reference, artifact_id in references.items():
                if item == reference or item.endswith(reference):
                    found.add(artifact_id)
        elif isinstance(item, dict):
            for child in item.values():
                visit(child)
        elif isinstance(item, list):
            for child in item:
                visit(child)

    visit(value)
    return tuple(sorted(found))


class NativeStudioBenchmarkReplayPublisher:
    """Project immutable Benchmark facts into a native Replay envelope."""

    def __init__(
        self,
        repository: StudioBenchmarkExperimentRepository,
        artifact_store: StudioBenchmarkManagedArtifactStore,
    ) -> None:
        """Configure durable journal and managed artifact inputs.

        Args:
            repository: Durable Experiment and event source.
            artifact_store: Verified managed artifact resolver.

        Returns:
            None.
        """
        self.repository = repository
        self.artifact_store = artifact_store

    def _trajectory_records(
        self,
        experiment_id: str,
        artifacts: tuple[StudioBenchmarkManagedArtifactRecordV1, ...],
    ) -> tuple[dict[str, Any], ...]:
        """Load the formal task trajectory through managed verification.

        Args:
            experiment_id: Owning Experiment identity.
            artifacts: Publication artifact inventory.

        Raises:
            ValueError: JSONL records are malformed.
            StudioBenchmarkError: Managed resolution fails.

        Returns:
            Ordered trajectory records, or an empty tuple when absent.
        """
        candidate = next(
            (
                record
                for record in artifacts
                if record.descriptor.kind == "task_trajectory"
                and record.descriptor.availability
                is StudioBenchmarkArtifactAvailability.AVAILABLE
            ),
            None,
        )
        if candidate is None:
            return ()
        del experiment_id
        path = self.artifact_store.storage_path(candidate)
        content = path.read_bytes()
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        if (
            digest != candidate.descriptor.sha256
            or len(content) != candidate.descriptor.size
        ):
            raise ValueError("managed trajectory failed integrity checks")
        try:
            records = []
            for raw_line in content.splitlines():
                if not raw_line.strip():
                    continue
                value = json.loads(raw_line)
                if not isinstance(value, dict):
                    raise ValueError("trajectory record must be an object")
                records.append(value)
            return tuple(records)
        finally:
            content = b""

    def build(
        self,
        *,
        experiment: StudioBenchmarkExperimentRecordV1,
        task_run: StudioBenchmarkTaskRunRecordV1,
        replay_id: str,
        imported_at: int,
        artifacts: tuple[StudioBenchmarkManagedArtifactRecordV1, ...],
    ) -> ReplayEvidenceEnvelope:
        """Build a validated native Benchmark Replay from durable facts.

        Args:
            experiment: Immutable Experiment definition and aggregate facts.
            task_run: Terminal TaskRun including bounded result facts.
            replay_id: Explicit stable Replay identity.
            imported_at: Unix epoch milliseconds for History ordering.
            artifacts: Managed publication artifact inventory.

        Raises:
            ValueError: Required TaskResult or immutable snapshot is absent.
            StudioBenchmarkError: Journal or artifact resolution fails.

        Returns:
            Complete native Replay envelope.
        """
        if task_run.result is None or task_run.benchmark_outcome is None:
            raise ValueError("native Benchmark Replay requires a TaskResult")
        agent_snapshot = next(
            (
                item
                for item in experiment.definition.agent_snapshots
                if item.agent_id == task_run.agent_id
                and item.revision_id == task_run.revision_id
            ),
            None,
        )
        if agent_snapshot is None:
            raise ValueError("native Benchmark Replay snapshot is absent")
        event_page = self.repository.query_events(
            experiment.experiment_id,
            after=0,
            limit=500,
        )
        journal_events = list(event_page.items)
        cursor = event_page.next_cursor
        while cursor < event_page.high_water_mark:
            event_page = self.repository.query_events(
                experiment.experiment_id,
                after=cursor,
                limit=500,
            )
            journal_events.extend(event_page.items)
            if event_page.next_cursor <= cursor:
                raise ValueError("Benchmark event cursor did not advance")
            cursor = event_page.next_cursor
        trajectory_records = self._trajectory_records(
            experiment.experiment_id,
            artifacts,
        )
        runtime_references = {
            record.descriptor.causal_identity.removeprefix("runtime/"): (
                record.descriptor.artifact_id
            )
            for record in artifacts
            if record.descriptor.causal_identity.startswith("runtime/")
        }
        moments: list[NormalizedReplayMoment] = []
        observations: list[ReplayObservation] = []
        actions: list[ReplayAction] = []
        for event in journal_events:
            index = len(moments)
            moments.append(
                NormalizedReplayMoment(
                    moment_id=_moment_id(
                        replay_id,
                        index,
                        event.kind,
                    ),
                    causal_index=index,
                    source_kind="benchmark_lifecycle",
                    source_sequence=event.sequence,
                    timestamp=float(event.timestamp),
                    phase=event.phase,
                    kind=event.kind,
                    payload=event.payload,
                )
            )
        for record in trajectory_records:
            phase = str(record.get("phase") or "")
            index = len(moments)
            moments.append(
                NormalizedReplayMoment(
                    moment_id=_moment_id(
                        replay_id,
                        index,
                        f"trajectory.{phase}",
                    ),
                    causal_index=index,
                    source_kind="benchmark_lifecycle",
                    phase=phase,
                    kind=str(record.get("kind") or "benchmark_phase"),
                    payload={
                        "stage": record.get("stage"),
                        "lifecycleEvents": record.get("lifecycle_events", []),
                    },
                )
            )
            agent_graph = record.get("agent_graph")
            if not isinstance(agent_graph, dict):
                continue
            for event in agent_graph.get("events", []):
                if not isinstance(event, dict):
                    continue
                index = len(moments)
                kind = str(event.get("kind") or "agent.event")
                moments.append(
                    NormalizedReplayMoment(
                        moment_id=_moment_id(replay_id, index, kind),
                        causal_index=index,
                        source_kind="agent_graph",
                        source_sequence=(
                            int(event["sequence"])
                            if isinstance(event.get("sequence"), int)
                            else None
                        ),
                        timestamp=(
                            float(event["timestamp"])
                            if isinstance(event.get("timestamp"), (int, float))
                            else None
                        ),
                        phase=phase,
                        kind=kind,
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
                            if isinstance(event.get("loop_iteration"), int)
                            else None
                        ),
                        interaction_step=int(
                            event.get("interaction_step") or 0
                        ),
                        payload=(
                            event.get("payload")
                            if isinstance(event.get("payload"), dict)
                            else {}
                        ),
                        artifact_ids=_artifact_ids_for_value(
                            event,
                            runtime_references,
                        ),
                    )
                )
            for item_index, observation in enumerate(
                agent_graph.get("observations", [])
            ):
                if not isinstance(observation, dict):
                    continue
                observations.append(
                    ReplayObservation(
                        observation_id=_evidence_id(
                            "observation",
                            replay_id,
                            item_index,
                            observation.get("sequence"),
                        ),
                        sequence=max(0, int(observation.get("sequence") or 0)),
                        interaction_step=max(
                            0,
                            int(observation.get("interaction_step") or 0),
                        ),
                        screenshot_artifact_id=next(
                            iter(
                                _artifact_ids_for_value(
                                    observation.get(
                                        "screenshot_artifact"
                                    ),
                                    runtime_references,
                                )
                            ),
                            None,
                        ),
                        ui_artifact_id=next(
                            iter(
                                _artifact_ids_for_value(
                                    observation.get("ui_artifact"),
                                    runtime_references,
                                )
                            ),
                            None,
                        ),
                    )
                )
            for item_index, action in enumerate(
                agent_graph.get("actions", [])
            ):
                if not isinstance(action, dict):
                    continue
                actions.append(
                    ReplayAction(
                        action_id=_evidence_id(
                            "action",
                            replay_id,
                            item_index,
                            action.get("sequence"),
                        ),
                        sequence=max(0, int(action.get("sequence") or 0)),
                        interaction_step=max(
                            0,
                            int(action.get("interaction_step") or 0),
                        ),
                        status=str(action.get("status") or ""),
                        action_type=str(
                            action.get("action_type")
                            or action.get("actionType")
                            or ""
                        ),
                        effect_performed=bool(
                            action.get("effect_performed")
                            or action.get("effectPerformed")
                        ),
                        effect_kind=str(
                            action.get("effect_kind")
                            or action.get("effectKind")
                            or ""
                        ),
                        message=str(action.get("message") or ""),
                        error=str(action.get("error") or ""),
                        artifact_id=next(
                            iter(
                                _artifact_ids_for_value(
                                    action,
                                    runtime_references,
                                )
                            ),
                            None,
                        ),
                    )
                )
        replay_artifacts = tuple(
            ReplayArtifactDescriptor(
                artifact_id=record.descriptor.artifact_id,
                kind=record.descriptor.kind,
                availability=_replay_availability(
                    record.descriptor.availability
                ),
                content_type=record.descriptor.content_type,
                size=record.descriptor.size,
                sha256=record.descriptor.sha256,
                provenance=record.descriptor.provenance,
                hidden=record.descriptor.hidden,
            )
            for record in artifacts
        )
        has_trajectory = bool(trajectory_records)
        return ReplayEvidenceEnvelope(
            run_id=replay_id,
            imported_at=imported_at,
            provenance="native_benchmark_task_run",
            evidence_origin=task_run.result.evidence_origin.with_acquisition(
                "replay_projection"
            ),
            integrity_state="complete" if has_trajectory else "partial",
            snapshot=ReplayRunSnapshot(
                agent_id=agent_snapshot.agent_id,
                revision_id=agent_snapshot.revision_id,
                contract_version=agent_snapshot.contract_version,
                canonical_hash=agent_snapshot.canonical_hash,
                graph_status="available",
                agent_graph=agent_snapshot.agent_graph,
                presentation=agent_snapshot.presentation,
                source_map=agent_snapshot.source_map,
                authoring_policy=agent_snapshot.authoring_policy,
                lowering_profile=agent_snapshot.lowering_profile,
                capability_hash=agent_snapshot.capability_hash,
                capability_document=agent_snapshot.capability_document,
                projection_map=agent_snapshot.projection_map,
                provider_identities=agent_snapshot.provider_identities,
            ),
            result=ReplayRunResultSummary(
                status=(
                    task_run.agent_status.value
                    if task_run.agent_status is not None
                    else task_run.terminal_reason.value
                ),
                kernel_status=(
                    task_run.agent_status.value
                    if task_run.agent_status is not None
                    else ""
                ),
                step_count=len(moments),
                activation_count=sum(
                    1 for item in moments if item.activation_id
                ),
                interaction_count=max(
                    (
                        item.interaction_step
                        for item in (*observations, *actions)
                    ),
                    default=0,
                ),
                usage=task_run.result.usage,
            ),
            moments=tuple(moments),
            observations=tuple(observations),
            actions=tuple(actions),
            benchmark=ReplayBenchmarkContext(
                experiment_id=experiment.experiment_id,
                task_id=task_run.task_id,
                agent_id=task_run.agent_id,
                repeat=task_run.repeat,
                outcome=task_run.benchmark_outcome.value,
                identities={
                    "agentGraph": task_run.result.agent_graph_identity,
                    "benchmarkPlan": task_run.result.benchmark_plan_identity,
                    "experimentProtocol": (
                        task_run.result.experiment_protocol_identity
                    ),
                    "taskInstance": task_run.result.task_instance_identity,
                },
                phases=tuple(
                    ReplayBenchmarkPhase(
                        phase=phase.phase,
                        status=phase.status,
                        duration_ms=phase.duration_ms,
                        error_code=phase.error_code,
                        evidence=phase.evidence,
                    )
                    for phase in task_run.phases
                ),
                evaluation=(
                    task_run.evaluation.model_dump(
                        mode="json",
                        by_alias=True,
                        exclude_none=True,
                    )
                    if task_run.evaluation is not None
                    else None
                ),
            ),
            artifacts=replay_artifacts,
            availability={
                "snapshot": ReplayEvidenceAvailability(state="available"),
                "journal": ReplayEvidenceAvailability(state="available"),
                "trajectory": ReplayEvidenceAvailability(
                    state="available" if has_trajectory else "not_captured"
                ),
                "artifacts": ReplayEvidenceAvailability(
                    state="available" if artifacts else "not_captured"
                ),
            },
            integrity=(
                ()
                if has_trajectory
                else (
                    ReplayIntegrityDiagnostic(
                        code="benchmark.replay.trajectory_unavailable",
                        message=(
                            "Formal TaskRun trajectory was not available "
                            "during Replay publication"
                        ),
                        severity="warning",
                        source="benchmark_publication",
                    ),
                )
            ),
        )


__all__ = ["NativeStudioBenchmarkReplayPublisher"]
