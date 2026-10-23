"""Explicit component-invocation debug capture for Studio Runs."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel

from zhixing.components import (
    RAW_RESPONSE_METADATA_KEY,
    ComponentInvocationTrace,
    LLMInput,
    LLMResult,
    TaskInput,
)

from .run_artifacts import LocalStudioRunArtifactStore
from .run_events import DurableRunEventService
from .run_models import (
    DebugEvidenceReferenceV1,
    DebugPayloadEnvelopeV1,
    RunEvidenceAvailability,
)
from .run_safety import SanitizationPolicy, sanitize_runtime_value


_PROMPT_KEYS = {"prompt", "system_prompt", "user_prompt", "messages"}
_RESPONSE_KEYS = {
    "model_response",
    "raw_response",
    "response_text",
    RAW_RESPONSE_METADATA_KEY,
}


def _object_fields(value: Any) -> Mapping[str, Any] | None:
    """Return explicit structured fields for known model/dataclass values.

    Args:
        value (Any): Candidate structured runtime value.

    Raises:
        None.

    Returns:
        Mapping[str, Any] | None: Explicit fields or no traversable shape.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", by_alias=False, exclude_none=True)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: getattr(value, field.name)
            for field in dataclasses.fields(value)
        }
    if isinstance(value, Mapping):
        return value
    return None


def _find_named_text(
    value: Any,
    keys: set[str],
    *,
    depth: int = 0,
) -> str | None:
    """Find one explicitly named text field within a bounded known structure.

    Args:
        value (Any): Candidate runtime value.
        keys (set[str]): Exact normalized field names to inspect.
        depth (int): Current traversal depth.

    Raises:
        None.

    Returns:
        str | None: First explicit text value, when captured.
    """
    if depth > 5:
        return None
    structured = _object_fields(value)
    if structured is not None:
        for raw_key, item in structured.items():
            key = str(raw_key).strip().lower()
            if key in keys and isinstance(item, str) and item:
                return item
        for item in structured.values():
            found = _find_named_text(item, keys, depth=depth + 1)
            if found is not None:
                return found
        return None
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for item in value[:50]:
            found = _find_named_text(item, keys, depth=depth + 1)
            if found is not None:
                return found
    return None


def _find_prompt(value: Any) -> str | None:
    """Extract a full Prompt only from approved typed or named fields.

    Args:
        value (Any): Invocation input structure.

    Raises:
        None.

    Returns:
        str | None: Captured Prompt or no evidence.
    """
    if isinstance(value, LLMInput):
        return value.prompt
    return _find_named_text(value, _PROMPT_KEYS)


def _find_response(value: Any) -> str | None:
    """Extract a full model response only from approved result fields.

    Args:
        value (Any): Invocation output structure.

    Raises:
        None.

    Returns:
        str | None: Captured model response or no evidence.
    """
    if isinstance(value, LLMResult):
        return value.text
    named = _find_named_text(value, _RESPONSE_KEYS)
    if named is not None:
        return named
    structured = _object_fields(value)
    if structured is not None:
        for item in structured.values():
            if isinstance(item, LLMResult):
                return item.text
    return None


def _find_usage(value: Any, *, depth: int = 0) -> dict[str, Any]:
    """Extract bounded model usage only from approved structured fields.

    Args:
        value (Any): Invocation output structure.
        depth (int): Current bounded traversal depth.

    Raises:
        None.

    Returns:
        dict[str, Any]: Safe token counters when explicitly captured.
    """
    if depth > 5:
        return {}
    if isinstance(value, LLMResult) and value.usage is not None:
        safe = sanitize_runtime_value(value.usage).value
        return safe if isinstance(safe, dict) else {}
    structured = _object_fields(value)
    if structured is not None:
        for key, item in structured.items():
            if str(key).strip().lower() == "usage":
                safe = sanitize_runtime_value(item).value
                if isinstance(safe, dict):
                    return safe
        for item in structured.values():
            found = _find_usage(item, depth=depth + 1)
            if found:
                return found
    elif isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        for item in value[:50]:
            found = _find_usage(item, depth=depth + 1)
            if found:
                return found
    return {}


def _find_task(value: Any, *, depth: int = 0) -> str | None:
    """Extract an Agent task from known TaskInput structures.

    Args:
        value (Any): Invocation input structure.
        depth (int): Current bounded traversal depth.

    Raises:
        None.

    Returns:
        str | None: Task instruction when present.
    """
    if depth > 5:
        return None
    if isinstance(value, TaskInput):
        return value.instruction
    structured = _object_fields(value)
    if structured is not None:
        for key, item in structured.items():
            if str(key).lower() in {"task", "instruction"} and isinstance(
                item,
                str,
            ):
                return item
        for item in structured.values():
            found = _find_task(item, depth=depth + 1)
            if found is not None:
                return found
    return None


def _scrub_model_text(value: Any) -> Any:
    """Replace model Prompt/response fields in an already-safe summary.

    Args:
        value (Any): Sanitized JSON value.

    Raises:
        None.

    Returns:
        Any: Summary with full model text replaced by evidence markers.
    """
    if isinstance(value, dict):
        looks_like_llm_result = (
            "text" in value
            and any(key in value for key in ("usage", "model", "metadata"))
        )
        output: dict[str, Any] = {}
        for raw_key, item in value.items():
            normalized = str(raw_key).strip().lower()
            if looks_like_llm_result and normalized == "text":
                output[raw_key] = {"$evidence": "model_response_artifact"}
            elif normalized in _PROMPT_KEYS:
                output[raw_key] = {"$evidence": "hidden_prompt"}
            elif normalized in _RESPONSE_KEYS:
                output[raw_key] = {"$evidence": "model_response_artifact"}
            else:
                output[raw_key] = _scrub_model_text(item)
        return output
    if isinstance(value, list):
        return [_scrub_model_text(item) for item in value]
    return value


class StudioRunDebugCapture:
    """Convert invocation traces into safe events and managed artifacts."""

    def __init__(
        self,
        *,
        artifacts: LocalStudioRunArtifactStore,
        events: DurableRunEventService,
        summary_policy: SanitizationPolicy | None = None,
    ) -> None:
        """Configure explicit debug evidence sinks.

        Args:
            artifacts (LocalStudioRunArtifactStore): Managed content boundary.
            events (DurableRunEventService): Durable debug envelope journal.
            summary_policy (SanitizationPolicy | None): Inline summary limits.

        Raises:
            None.

        Returns:
            None.
        """
        self.artifacts = artifacts
        self.events = events
        self.summary_policy = summary_policy or SanitizationPolicy(
            max_depth=6,
            max_members=50,
            max_text=1000,
            max_total_text=16 * 1024,
        )

    def capture(self, trace: ComponentInvocationTrace) -> DebugPayloadEnvelopeV1:
        """Persist one explicit component attempt stage.

        Args:
            trace (ComponentInvocationTrace): Runtime invocation facts.

        Raises:
            StudioRunEvidenceError: Debug evidence cannot be safely stored.
            StudioRunError: Descriptor or journal persistence fails.

        Returns:
            DebugPayloadEnvelopeV1: Persisted safe debug envelope.
        """
        identity_source = (
            f"{trace.activation_id}:{trace.component}:"
            f"{trace.candidate_index}:{trace.stage}"
        ).encode("utf-8")
        debug_id = "debug-" + hashlib.sha256(identity_source).hexdigest()[:32]
        artifact_ids: list[str] = []
        evidence_refs: dict[str, DebugEvidenceReferenceV1] = {}
        availability = {
            "prompt": RunEvidenceAvailability.NOT_CAPTURED,
            "modelResponse": RunEvidenceAvailability.NOT_CAPTURED,
            "debugPayload": RunEvidenceAvailability.NOT_CAPTURED,
        }
        diagnostics: list[str] = []

        prompt = _find_prompt(trace.inputs) if trace.stage == "start" else None
        if prompt is not None:
            descriptor = self.artifacts.write_text(
                trace.run_id,
                kind="sensitive_prompt",
                text=prompt,
                hidden=True,
                provenance="component_invocation",
                causal_identity=debug_id,
            )
            artifact_ids.append(descriptor.artifact_id)
            availability["prompt"] = RunEvidenceAvailability.HIDDEN
            evidence_refs["prompt"] = DebugEvidenceReferenceV1.from_descriptor(
                descriptor,
                expose_artifact_id=False,
            )

        response = (
            _find_response(trace.outputs)
            if trace.stage == "complete"
            else None
        )
        if response is not None:
            descriptor = self.artifacts.write_text(
                trace.run_id,
                kind="model_response",
                text=response,
                hidden=False,
                provenance="component_invocation",
                causal_identity=debug_id,
            )
            artifact_ids.append(descriptor.artifact_id)
            availability["modelResponse"] = descriptor.availability
            evidence_refs["modelResponse"] = (
                DebugEvidenceReferenceV1.from_descriptor(descriptor)
            )

        input_result = sanitize_runtime_value(
            trace.inputs,
            policy=self.summary_policy,
        )
        output_result = sanitize_runtime_value(
            trace.outputs,
            policy=self.summary_policy,
        )
        if input_result.redacted or output_result.redacted:
            diagnostics.append("studio.run.debug.redacted")
        if input_result.truncated or output_result.truncated:
            diagnostics.append("studio.run.debug.truncated")
        if input_result.excluded or output_result.excluded:
            diagnostics.append("studio.run.debug.excluded")
        task = sanitize_runtime_value(
            _find_task(trace.inputs),
            policy=self.summary_policy,
        ).value
        envelope = DebugPayloadEnvelopeV1(
            debug_id=debug_id,
            run_id=trace.run_id,
            node_path=trace.node_path,
            activation_id=trace.activation_id,
            component_identity=trace.component,
            role=trace.role,
            stage=trace.stage,
            task=task,
            input_summary=_scrub_model_text(input_result.value),
            output_summary=_scrub_model_text(output_result.value),
            duration_ms=trace.duration_ms,
            error=trace.error_type,
            usage=_find_usage(trace.outputs),
            artifact_ids=tuple(artifact_ids),
            evidence_refs=evidence_refs,
            availability=availability,
            diagnostics=tuple(sorted(set(diagnostics))),
        )
        debug_content = (
            json.dumps(
                envelope.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        debug_descriptor = self.artifacts.write_bytes(
            trace.run_id,
            kind="debug_payload",
            content_type="application/json",
            content=debug_content,
            provenance="component_invocation",
            causal_identity=debug_id,
        )
        event_envelope = envelope.model_copy(
            update={
                "artifact_ids": tuple(
                    [*artifact_ids, debug_descriptor.artifact_id]
                ),
                "evidence_refs": {
                    **evidence_refs,
                    "debugPayload": (
                        DebugEvidenceReferenceV1.from_descriptor(
                            debug_descriptor
                        )
                    ),
                },
                "availability": {
                    **availability,
                    "debugPayload": debug_descriptor.availability,
                },
            }
        )
        self.events.append(
            trace.run_id,
            self.events.service_event(
                kind=f"component.debug.{trace.stage}",
                source="storage",
                event_id=f"storage-{debug_id}",
                payload=event_envelope.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
            ),
        )
        return event_envelope


__all__ = ["StudioRunDebugCapture"]
