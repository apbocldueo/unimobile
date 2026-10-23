"""Managed evidence and explicit debug payload tests for Studio Runs."""

from __future__ import annotations

import json
import sqlite3

import pytest
from pydantic import ValidationError

from zhixing.components import (
    ComponentInvocationTrace,
    LLMInput,
    LLMResult,
    LLMUsage,
    RunEvent,
    TaskInput,
)
from zhixing.studio.run_artifacts import (
    LocalStudioRunArtifactStore,
    RuntimeArtifactEventAdapter,
)
from zhixing.studio.run_debug import StudioRunDebugCapture
from zhixing.studio.run_errors import (
    StudioRunArtifactNotFoundError,
    StudioRunEvidenceError,
)
from zhixing.studio.run_events import DurableRunEventService
from zhixing.studio.run_models import (
    DebugEvidenceReferenceV1,
    RunEvidenceAvailability,
    StudioRunArtifactDescriptorV1,
)

from .test_run_models_repository import _request, _run_service


def test_managed_store_preflight_write_open_and_soft_warning(tmp_path) -> None:
    """Persist opaque content, verify reads, and report a non-destructive warning."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    store = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        soft_warning_bytes=1,
        minimum_free_bytes=1,
        max_artifact_bytes=1024,
        max_run_bytes=4096,
    )
    assert store.preflight() == ()
    descriptor = store.write_bytes(
        run.run_id,
        kind="screenshot",
        content_type="image/png",
        content=b"png",
        causal_identity="observation-1",
    )
    assert store.preflight() == ("studio.run.evidence_soft_limit_warning",)
    metadata, stream = store.open_artifact(run.run_id, descriptor.artifact_id)
    try:
        assert stream.read() == b"png"
    finally:
        stream.close()
    assert metadata == descriptor
    assert "objects/" not in str(
        descriptor.model_dump(mode="json", by_alias=True)
    )


def test_hidden_missing_corrupt_and_size_boundaries(tmp_path) -> None:
    """Reject ordinary Prompt reads and expose accurate integrity failures."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    store = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        minimum_free_bytes=1,
        max_artifact_bytes=16,
        max_run_bytes=64,
    )
    prompt = store.write_text(
        run.run_id,
        kind="sensitive_prompt",
        text="hello",
        hidden=True,
    )
    with pytest.raises(StudioRunArtifactNotFoundError):
        store.open_artifact(run.run_id, prompt.artifact_id)
    second, _created = service.create_run(
        _request(agent_id, revision_id, "cross-run-debug-evidence")
    )
    with pytest.raises(StudioRunArtifactNotFoundError):
        store.open_artifact(second.run_id, prompt.artifact_id)
    with pytest.raises(StudioRunArtifactNotFoundError):
        store.open_artifact(run.run_id, "artifact-" + "f" * 32)

    visible = store.write_bytes(
        run.run_id,
        kind="model_response",
        content_type="text/plain",
        content=b"answer",
    )
    record = repository.get_artifact(run.run_id, visible.artifact_id)
    store.path_for_record(record).write_bytes(b"changed")
    with pytest.raises(StudioRunEvidenceError) as captured:
        store.open_artifact(run.run_id, visible.artifact_id)
    assert captured.value.code == "studio.run.artifact_corrupt"
    assert (
        repository.get_artifact(run.run_id, visible.artifact_id)
        .descriptor.availability
        is RunEvidenceAvailability.CORRUPT
    )
    missing = store.write_bytes(
        run.run_id,
        kind="screenshot",
        content_type="image/png",
        content=b"png",
    )
    missing_record = repository.get_artifact(
        run.run_id,
        missing.artifact_id,
    )
    store.path_for_record(missing_record).unlink()
    with pytest.raises(StudioRunEvidenceError) as captured_missing:
        store.open_artifact(run.run_id, missing.artifact_id)
    assert captured_missing.value.code == "studio.run.artifact_missing"
    assert (
        repository.get_artifact(run.run_id, missing.artifact_id)
        .descriptor.availability
        is RunEvidenceAvailability.MISSING
    )
    with pytest.raises(StudioRunEvidenceError):
        store.write_bytes(
            run.run_id,
            kind="large",
            content_type="text/plain",
            content=b"x" * 17,
        )


@pytest.mark.parametrize(
    "availability",
    (
        RunEvidenceAvailability.AVAILABLE,
        RunEvidenceAvailability.REDACTED,
        RunEvidenceAvailability.TRUNCATED,
    ),
)
def test_typed_debug_evidence_reference_availability_shapes(
    availability,
) -> None:
    """Validate readable, unavailable, and hidden typed reference contracts."""
    descriptor = StudioRunArtifactDescriptorV1(
        artifactId="artifact-" + "a" * 32,
        kind="model_response",
        availability=availability,
        contentType="text/plain; charset=utf-8",
        size=12,
        originalSize=20,
        sha256="sha256:" + "b" * 64,
        provenance="component_invocation",
        causalIdentity="debug-fixture",
    )
    reference = DebugEvidenceReferenceV1.from_descriptor(descriptor)
    assert reference.artifact_id == descriptor.artifact_id
    assert reference.availability is availability
    assert reference.sha256 == descriptor.sha256

    not_captured = DebugEvidenceReferenceV1(
        kind="model_response",
        availability=RunEvidenceAvailability.NOT_CAPTURED,
    )
    assert not_captured.artifact_id is None

    hidden_descriptor = descriptor.model_copy(
        update={
            "kind": "sensitive_prompt",
            "availability": RunEvidenceAvailability.HIDDEN,
            "hidden": True,
        }
    )
    hidden = DebugEvidenceReferenceV1.from_descriptor(
        hidden_descriptor,
        expose_artifact_id=False,
    )
    assert hidden.availability is RunEvidenceAvailability.HIDDEN
    assert hidden.artifact_id is None
    assert hidden.content_type == ""
    assert hidden.sha256 is None
    with pytest.raises(ValidationError):
        DebugEvidenceReferenceV1(
            kind="sensitive_prompt",
            artifactId=descriptor.artifact_id,
            availability=RunEvidenceAvailability.HIDDEN,
            hidden=True,
        )


def test_debug_capture_separates_summary_response_and_hidden_prompt(tmp_path) -> None:
    """Capture full model evidence without placing it in inline journal payloads."""
    database = tmp_path / "studio.sqlite3"
    service, repository, agent_id, revision_id = _run_service(database)
    run, _created = service.create_run(_request(agent_id, revision_id))
    events = DurableRunEventService(repository)
    store = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        minimum_free_bytes=1,
        max_artifact_bytes=4096,
        max_run_bytes=16384,
    )
    capture = StudioRunDebugCapture(artifacts=store, events=events)
    prompt = "authorization: secret-debug-canary\nOpen Settings"
    started = capture.capture(
        ComponentInvocationTrace(
            run_id=run.run_id,
            node_path="planner",
            activation_id="activation-1",
            role="zhixing.role.planner",
            component="builtin:planner@1.0.0",
            stage="start",
            inputs={"request": LLMInput(prompt=prompt)},
        )
    )
    completed = capture.capture(
        ComponentInvocationTrace(
            run_id=run.run_id,
            node_path="planner",
            activation_id="activation-1",
            role="zhixing.role.planner",
            component="builtin:planner@1.0.0",
            stage="complete",
            inputs={"request": LLMInput(prompt=prompt)},
            outputs={
                "result": LLMResult(
                    text="full model answer",
                    usage=LLMUsage(total_tokens=4),
                )
            },
            duration_ms=12.0,
        )
    )
    assert started.availability["prompt"] is RunEvidenceAvailability.HIDDEN
    assert started.evidence_refs["prompt"].artifact_id is None
    assert started.evidence_refs["prompt"].hidden is True
    assert (
        completed.availability["modelResponse"]
        is RunEvidenceAvailability.AVAILABLE
    )
    assert (
        completed.evidence_refs["modelResponse"].availability
        is RunEvidenceAvailability.AVAILABLE
    )
    assert (
        completed.evidence_refs["debugPayload"].availability
        is RunEvidenceAvailability.AVAILABLE
    )
    records = repository.list_artifacts(run.run_id)
    prompt_record = next(
        item for item in records if item.descriptor.kind == "sensitive_prompt"
    )
    response_record = next(
        item for item in records if item.descriptor.kind == "model_response"
    )
    debug_record = next(
        item
        for item in records
        if item.descriptor.kind == "debug_payload"
        and item.descriptor.causal_identity == completed.debug_id
    )
    assert (
        completed.evidence_refs["modelResponse"].artifact_id
        == response_record.descriptor.artifact_id
    )
    assert (
        completed.evidence_refs["debugPayload"].artifact_id
        == debug_record.descriptor.artifact_id
    )
    with pytest.raises(StudioRunArtifactNotFoundError):
        store.open_artifact(run.run_id, prompt_record.descriptor.artifact_id)
    _metadata, stream = store.open_artifact(
        run.run_id,
        response_record.descriptor.artifact_id,
    )
    try:
        assert stream.read() == b"full model answer"
    finally:
        stream.close()

    sqlite_dump = ""
    with sqlite3.connect(database) as connection:
        sqlite_dump = "\n".join(connection.iterdump())
    assert "secret-debug-canary" not in sqlite_dump
    assert "authorization: secret-debug-canary" not in sqlite_dump
    page = repository.query_events(run.run_id, after=1, limit=10)
    serialized = str(
        page.model_dump(mode="json", by_alias=True, exclude_none=True)
    )
    assert "evidenceRefs" in serialized
    assert prompt not in serialized
    assert "full model answer" not in serialized
    assert completed.usage["total_tokens"] == 4


def test_runtime_references_become_opaque_and_text_limit_is_byte_exact(
    tmp_path,
) -> None:
    """Register all Runtime evidence types and byte-bound Unicode content."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / "studio.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    store = LocalStudioRunArtifactStore(
        tmp_path / "managed",
        repository,
        minimum_free_bytes=1,
        max_artifact_bytes=32,
        max_run_bytes=4096,
    )
    references = {
        "screenshot_artifact": f"{run.run_id}/observations/0000.png",
        "ui_artifact": f"{run.run_id}/observations/0000.xml",
        "artifact": f"{run.run_id}/actions/0000.json",
    }
    for reference in references.values():
        target = store.runtime_root / reference
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"{}" if target.suffix != ".png" else b"png")
    event = RunEvent(
        run_id=run.run_id,
        sequence=1,
        timestamp=1.0,
        phase="graph_kernel",
        role="fixture",
        component="fixture",
        kind="complete",
        payload={"evidence": references},
    )
    draft = RuntimeArtifactEventAdapter(store).build(event)
    serialized = json.dumps(draft.payload)
    assert f"{run.run_id}/" not in serialized
    assert all(value not in serialized for value in references.values())
    assert len(draft.payload["artifactIds"]) == 3

    descriptor = store.write_text(
        run.run_id,
        kind="model_response",
        text="界" * 100,
    )
    assert descriptor.availability is RunEvidenceAvailability.TRUNCATED
    assert descriptor.original_size == 300
    assert descriptor.size <= 32
    _metadata, stream = store.open_artifact(
        run.run_id,
        descriptor.artifact_id,
    )
    try:
        stream.read().decode("utf-8")
    finally:
        stream.close()


@pytest.mark.parametrize(
    "role",
    (
        "zhixing.role.perception",
        "zhixing.role.planner",
        "zhixing.role.reasoning",
        "zhixing.service.action_executor",
    ),
)
def test_debug_payload_roles_are_bounded_and_safe(tmp_path, role) -> None:
    """Capture role-specific task and summaries without serializing live state."""
    service, repository, agent_id, revision_id = _run_service(
        tmp_path / f"{role.rsplit('.', 1)[-1]}.sqlite3"
    )
    run, _created = service.create_run(_request(agent_id, revision_id))
    events = DurableRunEventService(repository)
    store = LocalStudioRunArtifactStore(
        tmp_path / role.rsplit(".", 1)[-1],
        repository,
        minimum_free_bytes=1,
        max_artifact_bytes=4096,
        max_run_bytes=32768,
    )
    capture = StudioRunDebugCapture(artifacts=store, events=events)
    envelope = capture.capture(
        ComponentInvocationTrace(
            run_id=run.run_id,
            node_path="node",
            activation_id="activation-role",
            role=role,
            component="fixture:component@1.0.0",
            stage="complete",
            inputs={
                "task": TaskInput(instruction="Research task"),
                "nested": {"value": {"deeper": {"tooDeep": object()}}},
            },
            outputs={
                "summary": "x" * 5000,
                "authorization": "secret-role-canary",
            },
            duration_ms=2.5,
        )
    )
    assert envelope.task == "Research task"
    assert envelope.duration_ms == 2.5
    assert (
        envelope.availability["modelResponse"]
        is RunEvidenceAvailability.NOT_CAPTURED
    )
    assert "studio.run.debug.excluded" in envelope.diagnostics
    serialized = json.dumps(
        envelope.model_dump(mode="json", by_alias=True),
        ensure_ascii=False,
    )
    assert "secret-role-canary" not in serialized
    assert "object at 0x" not in serialized
    assert '"$excluded": "live_object"' in serialized
    assert len(serialized) < 20000
