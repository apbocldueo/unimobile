"""Trusted native conversion from terminal Studio Runs to immutable Replay."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .replay_contracts import (
    ReplayConflictError,
    ReplayImportArtifact,
    ReplayImportCandidate,
)
from .replay_models import (
    NormalizedReplayMoment,
    ReplayAction,
    ReplayArtifactDescriptor,
    ReplayEvidenceAvailability,
    ReplayEvidenceEnvelope,
    ReplayIntegrityDiagnostic,
    ReplayObservation,
    ReplayRunResultSummary,
    ReplayRunSnapshot,
)
from .evidence_origin import StudioExecutionEvidenceOriginV1
from .replay_storage import ReplayArtifactStore
from .run_artifacts import LocalStudioRunArtifactStore
from .run_models import (
    RunEvidenceAvailability,
    StudioRunArtifactRecordV1,
    StudioRunEventEnvelopeV1,
)
from .run_protocols import (
    StudioRunArtifactRepository,
    StudioRunEventRepository,
    StudioRunRepository,
)


_READABLE = {
    RunEvidenceAvailability.AVAILABLE,
    RunEvidenceAvailability.REDACTED,
    RunEvidenceAvailability.TRUNCATED,
    RunEvidenceAvailability.HIDDEN,
}


def _nested_value(value: object, key: str) -> object | None:
    """Find the first exact key within bounded journal JSON.

    Args:
        value (object): Persisted safe JSON value.
        key (str): Exact key to locate.

    Raises:
        None.

    Returns:
        object | None: First matching value.
    """
    if isinstance(value, Mapping):
        if key in value:
            return value[key]
        for item in value.values():
            found = _nested_value(item, key)
            if found is not None:
                return found
    elif isinstance(value, (list, tuple)):
        for item in value:
            found = _nested_value(item, key)
            if found is not None:
                return found
    return None


def _activation_output_value(
    payload: object,
    output_name: str,
    key: str,
) -> object | None:
    """Read one field from the formal Kernel activation output summary.

    Args:
        payload (object): Persisted journal payload.
        output_name (str): Declared output value name such as ``observation``.
        key (str): Exact typed summary field.

    Raises:
        None.

    Returns:
        object | None: Formal output field, with a bounded legacy-fixture
        fallback when the payload predates the nested values envelope.
    """
    if isinstance(payload, Mapping):
        runtime_payload = payload.get("payload")
        for candidate in (runtime_payload, payload):
            if not isinstance(candidate, Mapping):
                continue
            outputs = candidate.get("outputs")
            if not isinstance(outputs, Mapping):
                continue
            values = outputs.get("values")
            if isinstance(values, Mapping):
                output = values.get(output_name)
                if isinstance(output, Mapping) and key in output:
                    return output[key]
            output = outputs.get(output_name)
            if isinstance(output, Mapping) and key in output:
                return output[key]
    return _nested_value(payload, key)


def _artifact_ids(value: object) -> tuple[str, ...]:
    """Collect opaque artifact identities from safe journal JSON.

    Args:
        value (object): Persisted safe JSON value.

    Raises:
        None.

    Returns:
        tuple[str, ...]: Stable first-seen artifact identities.
    """
    found: list[str] = []

    def visit(item: object) -> None:
        """Traverse bounded JSON values.

        Args:
            item (object): Nested safe JSON value.

        Raises:
            None.

        Returns:
            None.
        """
        if isinstance(item, str) and item.startswith("artifact-"):
            found.append(item)
        elif isinstance(item, Mapping):
            for nested in item.values():
                visit(nested)
        elif isinstance(item, (list, tuple)):
            for nested in item:
                visit(nested)

    visit(value)
    return tuple(dict.fromkeys(found))


def _text(value: object, default: str = "") -> str:
    """Return one bounded scalar text value.

    Args:
        value (object): Candidate safe value.
        default (str): Fallback for containers or missing data.

    Raises:
        None.

    Returns:
        str: Bounded text.
    """
    if value is None or isinstance(value, (Mapping, list, tuple)):
        return default
    return str(value).replace("\n", " ")[:1000]


def _integer(value: object, default: int = 0) -> int:
    """Return one non-negative integer from safe persisted JSON.

    Args:
        value (object): Candidate value.
        default (int): Fallback value.

    Raises:
        None.

    Returns:
        int: Non-negative integer.
    """
    if isinstance(value, bool):
        return default
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return default


def _source_kind(event: StudioRunEventEnvelopeV1) -> str:
    """Map one journal event to the existing Replay source vocabulary.

    Args:
        event (StudioRunEventEnvelopeV1): Durable journal event.

    Raises:
        None.

    Returns:
        str: Replay source kind.
    """
    role = _text(_nested_value(event.payload, "role")).lower()
    if role == "zhixing.service.device_observe":
        return "observation"
    if role == "zhixing.service.action_executor":
        return "action"
    if event.source == "result" or event.kind == "run.terminal":
        return "run_result"
    return "agent_graph"


class NativeStudioRunReplayFinalizer:
    """Build Replay only from trusted Run repositories and managed content."""

    def __init__(
        self,
        *,
        runs: StudioRunRepository,
        events: StudioRunEventRepository,
        artifacts: StudioRunArtifactRepository,
        live_store: LocalStudioRunArtifactStore,
        replay_store: ReplayArtifactStore,
    ) -> None:
        """Bind trusted native Run and Replay persistence boundaries.

        Args:
            runs (StudioRunRepository): Terminal Run metadata source.
            events (StudioRunEventRepository): Durable journal source.
            artifacts (StudioRunArtifactRepository): Managed inventory source.
            live_store (LocalStudioRunArtifactStore): Verified content resolver.
            replay_store (ReplayArtifactStore): Atomic Replay destination.

        Raises:
            None.

        Returns:
            None.
        """
        self.runs = runs
        self.events = events
        self.artifacts = artifacts
        self.live_store = live_store
        self.replay_store = replay_store

    def _all_events(
        self,
        run_id: str,
    ) -> tuple[StudioRunEventEnvelopeV1, ...]:
        """Read one continuous journal through bounded repository pages.

        Args:
            run_id (str): Stable Run identity.

        Raises:
            StudioRunError: Journal is missing, corrupt, or discontinuous.

        Returns:
            tuple[StudioRunEventEnvelopeV1, ...]: Complete committed prefix.
        """
        cursor = 0
        items: list[StudioRunEventEnvelopeV1] = []
        while True:
            page = self.events.query_events(run_id, after=cursor, limit=500)
            items.extend(page.items)
            cursor = page.next_cursor
            if cursor >= page.high_water_mark:
                return tuple(items)

    @staticmethod
    def _descriptors(
        records: tuple[StudioRunArtifactRecordV1, ...],
    ) -> tuple[ReplayArtifactDescriptor, ...]:
        """Convert live descriptors without changing opaque identities.

        Args:
            records (tuple[StudioRunArtifactRecordV1, ...]): Live inventory.

        Raises:
            ValueError: A descriptor violates Replay contracts.

        Returns:
            tuple[ReplayArtifactDescriptor, ...]: Replay descriptors.
        """
        converted: list[ReplayArtifactDescriptor] = []
        for record in records:
            item = record.descriptor
            availability = (
                "available"
                if item.availability is RunEvidenceAvailability.HIDDEN
                else item.availability.value
            )
            converted.append(
                ReplayArtifactDescriptor(
                    artifact_id=item.artifact_id,
                    kind=item.kind,
                    availability=availability,
                    content_type=item.content_type,
                    size=item.size,
                    sha256=item.sha256,
                    provenance=item.provenance,
                    hidden=item.hidden,
                )
            )
        return tuple(converted)

    @staticmethod
    def _moments(
        events: tuple[StudioRunEventEnvelopeV1, ...],
    ) -> tuple[
        tuple[NormalizedReplayMoment, ...],
        tuple[ReplayObservation, ...],
        tuple[ReplayAction, ...],
    ]:
        """Project the same journal facts into normalized Replay structures.

        Args:
            events (tuple[StudioRunEventEnvelopeV1, ...]): Journal prefix.

        Raises:
            ValueError: Projected evidence violates Replay contracts.

        Returns:
            tuple: Moments, observations, and actions.
        """
        moments: list[NormalizedReplayMoment] = []
        observations: list[ReplayObservation] = []
        actions: list[ReplayAction] = []
        for causal_index, event in enumerate(events):
            payload = event.payload
            source_kind = _source_kind(event)
            artifact_ids = _artifact_ids(payload)
            observation_id: str | None = None
            action_id: str | None = None
            if source_kind == "observation" and event.kind == "complete":
                observation_id = f"observation-{event.sequence:08d}"
                observations.append(
                    ReplayObservation(
                        observation_id=observation_id,
                        sequence=_integer(
                            _activation_output_value(
                                payload,
                                "observation",
                                "sequence",
                            ),
                            len(observations),
                        ),
                        interaction_step=event.interaction_step or 0,
                        screenshot_artifact_id=_text(
                            _activation_output_value(
                                payload,
                                "observation",
                                "screenshot_artifact",
                            )
                        )
                        or None,
                        ui_artifact_id=_text(
                            _activation_output_value(
                                payload,
                                "observation",
                                "ui_artifact",
                            )
                        )
                        or None,
                        width=_integer(
                            _activation_output_value(payload, "observation", "width")
                        ),
                        height=_integer(
                            _activation_output_value(payload, "observation", "height")
                        ),
                        platform=_text(
                            _activation_output_value(payload, "observation", "platform")
                        ),
                        device_id=_text(
                            _activation_output_value(payload, "observation", "device_id")
                        ),
                    )
                )
            elif source_kind == "action" and event.kind == "complete":
                action_id = f"action-{event.sequence:08d}"
                actions.append(
                    ReplayAction(
                        action_id=action_id,
                        sequence=len(actions),
                        interaction_step=event.interaction_step or 0,
                        status=_text(
                            _activation_output_value(payload, "result", "status"),
                            "unknown",
                        ),
                        action_type=_text(
                            _activation_output_value(payload, "result", "action_type"),
                            "unknown",
                        ),
                        effect_performed=bool(
                            _activation_output_value(
                                payload,
                                "result",
                                "effect_performed",
                            )
                            or False
                        ),
                        effect_kind=_text(
                            _activation_output_value(payload, "result", "effect_kind")
                        ),
                        terminal_status=_text(
                            _activation_output_value(
                                payload,
                                "result",
                                "terminal_status",
                            )
                        )
                        or None,
                        message=_text(
                            _activation_output_value(payload, "result", "message")
                        ),
                        error=_text(
                            _activation_output_value(payload, "result", "error")
                        ),
                        artifact_id=(artifact_ids[0] if artifact_ids else None),
                    )
                )
            moments.append(
                NormalizedReplayMoment(
                    moment_id=f"moment-{event.sequence:08d}",
                    causal_index=causal_index,
                    source_kind=source_kind,
                    source_sequence=event.sequence,
                    timestamp=event.timestamp,
                    phase=_text(_nested_value(payload, "phase")),
                    kind=event.kind,
                    role=_text(_nested_value(payload, "role")),
                    component=_text(_nested_value(payload, "component")),
                    node_id=_text(_nested_value(payload, "node_id")),
                    node_path=event.node_path,
                    activation_id=event.activation_id,
                    parent_activation_id=_text(
                        _nested_value(payload, "parent_activation_id")
                    ),
                    loop_path=_text(_nested_value(payload, "loop_path")),
                    loop_iteration=(
                        _integer(_nested_value(payload, "loop_iteration"))
                        if _nested_value(payload, "loop_iteration") is not None
                        else None
                    ),
                    interaction_step=event.interaction_step or 0,
                    duration_ms=(
                        float(_nested_value(payload, "duration_ms"))
                        if isinstance(
                            _nested_value(payload, "duration_ms"),
                            (int, float),
                        )
                        else None
                    ),
                    payload=payload,
                    observation_id=observation_id,
                    action_id=action_id,
                    artifact_ids=artifact_ids,
                )
            )
        return tuple(moments), tuple(observations), tuple(actions)

    @staticmethod
    def _availability(
        records: tuple[StudioRunArtifactRecordV1, ...],
    ) -> dict[str, ReplayEvidenceAvailability]:
        """Summarize captured evidence classes without fabricating content.

        Args:
            records (tuple[StudioRunArtifactRecordV1, ...]): Live inventory.

        Raises:
            ValueError: Availability state is invalid.

        Returns:
            dict[str, ReplayEvidenceAvailability]: Evidence-class states.
        """
        by_kind: dict[str, list[RunEvidenceAvailability]] = {}
        for record in records:
            by_kind.setdefault(record.descriptor.kind, []).append(
                record.descriptor.availability
            )

        def state(*kinds: str, hidden: bool = False) -> ReplayEvidenceAvailability:
            """Resolve one evidence-class state.

            Args:
                *kinds (str): Artifact kinds in the evidence class.
                hidden (bool): Whether captured evidence stays intentionally hidden.

            Raises:
                None.

            Returns:
                ReplayEvidenceAvailability: Accurate aggregate state.
            """
            values = [item for kind in kinds for item in by_kind.get(kind, ())]
            if not values:
                return ReplayEvidenceAvailability(state="not_captured")
            if any(item is RunEvidenceAvailability.CORRUPT for item in values):
                return ReplayEvidenceAvailability(
                    state="corrupt",
                    reason_code="studio.run.artifact_corrupt",
                )
            if any(item is RunEvidenceAvailability.MISSING for item in values):
                return ReplayEvidenceAvailability(
                    state="missing",
                    reason_code="studio.run.artifact_missing",
                )
            if hidden:
                return ReplayEvidenceAvailability(state="hidden")
            if any(item is RunEvidenceAvailability.TRUNCATED for item in values):
                return ReplayEvidenceAvailability(state="truncated")
            if any(item is RunEvidenceAvailability.REDACTED for item in values):
                return ReplayEvidenceAvailability(state="redacted")
            return ReplayEvidenceAvailability(state="available")

        return {
            "agentGraph": ReplayEvidenceAvailability(state="available"),
            "journal": ReplayEvidenceAvailability(state="available"),
            "result": ReplayEvidenceAvailability(state="available"),
            "screenshots": state("screenshot"),
            "uiTree": state("ui_tree"),
            "actions": state("action"),
            "modelResponse": state("model_response"),
            "debugPayload": state("debug_payload"),
            "prompt": state("sensitive_prompt", hidden=True),
        }

    def finalize(self, run_id: str) -> ReplayEvidenceEnvelope:
        """Atomically create or return Replay for one terminal managed Run.

        Args:
            run_id (str): Stable terminal Run identity.

        Raises:
            ValueError: Run is nonterminal or evidence violates contracts.
            StudioRunError: Native Run evidence cannot be read.
            ReplayImportError: Managed content fails verification.
            OSError: Replay storage cannot be written.

        Returns:
            ReplayEvidenceEnvelope: Immutable native Replay.
        """
        record = self.runs.get_run(run_id)
        if record.result is None or record.terminal_at is None:
            raise ValueError("Native Replay requires a terminal Studio Run")
        events = self._all_events(run_id)
        artifact_records = self.artifacts.list_artifacts(run_id)
        replay_descriptors = self._descriptors(artifact_records)
        moments, observations, actions = self._moments(events)
        bad = tuple(
            item
            for item in artifact_records
            if item.descriptor.availability
            in {
                RunEvidenceAvailability.MISSING,
                RunEvidenceAvailability.CORRUPT,
            }
        )
        diagnostics = tuple(
            ReplayIntegrityDiagnostic(
                code=(
                    "studio.run.artifact_corrupt"
                    if item.descriptor.availability
                    is RunEvidenceAvailability.CORRUPT
                    else "studio.run.artifact_missing"
                ),
                message="Native Run artifact content is unavailable",
                source=item.descriptor.kind,
            )
            for item in bad
        )
        envelope = ReplayEvidenceEnvelope(
            run_id=run_id,
            imported_at=record.terminal_at,
            provenance="native_studio_run",
            evidence_origin=StudioExecutionEvidenceOriginV1(
                acquisition="replay_projection",
                environment="unverified",
            ),
            integrity_state=("partial" if bad else "complete"),
            snapshot=ReplayRunSnapshot(
                agent_id=record.snapshot.agent_id,
                revision_id=record.snapshot.revision_id,
                contract_version=record.snapshot.contract_version,
                canonical_hash=record.snapshot.canonical_hash,
                graph_status="available",
                agent_graph=record.snapshot.agent_graph,
                presentation=record.snapshot.presentation,
                source_map=record.snapshot.source_map,
                authoring_policy=record.snapshot.authoring_policy,
                lowering_profile=record.snapshot.lowering_profile,
                capability_hash=record.snapshot.capability_hash,
                capability_document=record.snapshot.capability_document,
                projection_map=record.snapshot.projection_map,
                provider_identities=record.snapshot.provider_identities,
            ),
            result=ReplayRunResultSummary(
                status=record.result.status,
                kernel_status=record.result.kernel_status,
                error=record.result.error,
                step_count=record.result.step_count,
                activation_count=record.result.activation_count,
                interaction_count=record.result.interaction_count,
                usage=record.result.usage,
            ),
            moments=moments,
            observations=observations,
            actions=actions,
            artifacts=replay_descriptors,
            availability=self._availability(artifact_records),
            integrity=diagnostics,
        )
        imports = {
            item.descriptor.artifact_id: ReplayImportArtifact(
                descriptor=descriptor,
                source_path=self.live_store.path_for_record(item),
                trusted_root=self.live_store.root,
            )
            for item, descriptor in zip(
                artifact_records,
                replay_descriptors,
                strict=True,
            )
            if item.descriptor.availability in _READABLE
        }
        try:
            return self.replay_store.import_candidate(
                ReplayImportCandidate(
                    envelope=envelope,
                    artifacts=imports,
                )
            )
        except ReplayConflictError:
            existing = self.replay_store.repository.get_replay(run_id)
            if existing.provenance != "native_studio_run":
                raise
            return existing


__all__ = ["NativeStudioRunReplayFinalizer"]
