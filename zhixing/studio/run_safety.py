"""Bounded serialization and redaction shared by Studio Run evidence surfaces."""

from __future__ import annotations

import dataclasses
import math
import re
from collections.abc import Mapping, Sequence
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel


_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "credential",
    "token",
    "password",
    "secret",
    "authorization",
    "cookie",
)
_DEVICE_SERIAL_KEYS = {
    "adb_argument",
    "adb_arguments",
    "adb_args",
    "adb_serial",
    "binding_fingerprint",
    "config_path",
    "configuration_path",
    "device_handle",
    "device_id",
    "device_serial",
    "raw_serial",
    "serial",
    "target_key",
}
_ABSOLUTE_PATH = re.compile(
    r"(?<![A-Za-z0-9_.-])(?:/[A-Za-z0-9_.~+@%=-]+(?:/[A-Za-z0-9_.~+@%=-]+)+"
    r"|[A-Za-z]:[\\/][^\s'\"<>]+)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{6,}")
_ASSIGNED_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*"
    r"[^\s,;}\]]+"
)
_ANDROID_SERIAL = re.compile(
    r"(?i)\b(?:emulator-\d{3,6}|[A-Za-z0-9]{8,32}:[0-9]{3,5})\b"
)
_ADB_COMMAND = re.compile(r"(?i)\badb(?:\.exe)?\s+-[^\r\n]{1,256}")


@dataclasses.dataclass(frozen=True)
class SanitizationPolicy:
    """Resource limits used while converting runtime values to safe JSON."""

    max_depth: int = 6
    max_members: int = 50
    max_text: int = 4000
    max_total_text: int = 64 * 1024


@dataclasses.dataclass(frozen=True)
class SanitizationResult:
    """One bounded JSON value plus non-sensitive transformation facts."""

    value: Any
    redacted: bool = False
    truncated: bool = False
    excluded: bool = False
    original_size: int | None = None


def is_sensitive_key(key: str) -> bool:
    """Return whether a field name represents secret or raw-device material.

    Args:
        key (str): Candidate mapping key.

    Raises:
        None.

    Returns:
        bool: True when values under the key must never be persisted.
    """
    normalized = re.sub(
        r"(?<!^)(?=[A-Z])",
        "_",
        str(key).strip(),
    ).lower().replace("-", "_")
    if normalized in {
        "completion_tokens",
        "prompt_tokens",
        "reasoning_tokens",
        "total_tokens",
    }:
        return False
    return normalized in _DEVICE_SERIAL_KEYS or any(
        part in normalized for part in _SENSITIVE_KEY_PARTS
    )


def redact_text(value: str, *, max_length: int = 4000) -> tuple[str, bool, bool]:
    """Redact common credentials and host paths, then bound one text value.

    Args:
        value (str): Candidate text.
        max_length (int): Largest returned character count.

    Raises:
        None.

    Returns:
        tuple[str, bool, bool]: Safe text, redaction flag, and truncation flag.
    """
    text = str(value)
    cleaned = _BEARER.sub("[REDACTED]", text)
    cleaned = _ASSIGNED_SECRET.sub(
        lambda match: f"{match.group(1)}=[REDACTED]",
        cleaned,
    )
    cleaned = _ANDROID_SERIAL.sub("[DEVICE_ID_REDACTED]", cleaned)
    cleaned = _ADB_COMMAND.sub("[ADB_COMMAND_REDACTED]", cleaned)
    cleaned = _ABSOLUTE_PATH.sub("[HOST_PATH_REDACTED]", cleaned)
    redacted = cleaned != text
    truncated = len(cleaned) > max_length
    if truncated:
        cleaned = cleaned[: max(0, max_length - 15)] + "…[truncated]"
    return cleaned, redacted, truncated


def sanitize_runtime_value(
    value: Any,
    *,
    policy: SanitizationPolicy | None = None,
) -> SanitizationResult:
    """Convert one runtime value into deterministic bounded safe JSON.

    Known Pydantic models, dataclasses, mappings, and sequences are traversed.
    Unknown live objects are represented only by their type name.

    Args:
        value (Any): Runtime value to sanitize.
        policy (SanitizationPolicy | None): Optional resource limits.

    Raises:
        None.

    Returns:
        SanitizationResult: Safe JSON value and transformation diagnostics.
    """
    limits = policy or SanitizationPolicy()
    text_budget = [0]

    def visit(candidate: Any, depth: int, key: str = "") -> SanitizationResult:
        """Sanitize one nested candidate while sharing a text budget.

        Args:
            candidate (Any): Nested runtime value.
            depth (int): Current collection depth.
            key (str): Owning mapping or model field name.

        Raises:
            None.

        Returns:
            SanitizationResult: Nested safe result.
        """
        if is_sensitive_key(key):
            return SanitizationResult("[REDACTED]", redacted=True)
        if depth > limits.max_depth:
            return SanitizationResult(
                {"$truncated": "max_depth"},
                truncated=True,
            )
        if candidate is None or isinstance(candidate, bool):
            return SanitizationResult(candidate)
        if isinstance(candidate, int):
            return SanitizationResult(candidate)
        if isinstance(candidate, float):
            if math.isfinite(candidate):
                return SanitizationResult(candidate)
            return SanitizationResult(
                {"$excluded": "non_finite_number"},
                excluded=True,
            )
        if isinstance(candidate, Enum):
            return visit(candidate.value, depth, key)
        if isinstance(candidate, Path):
            return SanitizationResult("[HOST_PATH_REDACTED]", redacted=True)
        if isinstance(candidate, str):
            remaining = max(0, limits.max_total_text - text_budget[0])
            allowed = min(limits.max_text, remaining)
            safe, redacted, truncated = redact_text(
                candidate,
                max_length=allowed,
            )
            text_budget[0] += len(safe)
            return SanitizationResult(
                safe,
                redacted=redacted,
                truncated=truncated or allowed < min(len(candidate), limits.max_text),
                original_size=len(candidate) if truncated else None,
            )
        if isinstance(candidate, (bytes, bytearray, memoryview)):
            return SanitizationResult(
                {
                    "$excluded": "binary_content",
                    "size": len(candidate),
                },
                excluded=True,
                original_size=len(candidate),
            )
        if isinstance(candidate, BaseModel):
            return visit(
                candidate.model_dump(mode="python", by_alias=True, exclude_none=True),
                depth,
                key,
            )
        if dataclasses.is_dataclass(candidate) and not isinstance(candidate, type):
            return visit(
                {
                    field.name: getattr(candidate, field.name)
                    for field in dataclasses.fields(candidate)
                },
                depth,
                key,
            )
        if isinstance(candidate, Mapping):
            output: dict[str, Any] = {}
            redacted = False
            truncated = False
            excluded = False
            for index, (raw_key, item) in enumerate(candidate.items()):
                if index >= limits.max_members:
                    output["$truncated"] = "max_members"
                    truncated = True
                    break
                if not isinstance(raw_key, str):
                    output[f"$excluded_key_{index}"] = type(raw_key).__name__
                    excluded = True
                    continue
                child = visit(item, depth + 1, raw_key)
                output[raw_key[:160]] = child.value
                redacted = redacted or child.redacted
                truncated = truncated or child.truncated
                excluded = excluded or child.excluded
            return SanitizationResult(
                output,
                redacted=redacted,
                truncated=truncated,
                excluded=excluded,
            )
        if isinstance(candidate, Sequence):
            output_items: list[Any] = []
            redacted = False
            truncated = False
            excluded = False
            for index, item in enumerate(candidate):
                if index >= limits.max_members:
                    output_items.append({"$truncated": "max_members"})
                    truncated = True
                    break
                child = visit(item, depth + 1)
                output_items.append(child.value)
                redacted = redacted or child.redacted
                truncated = truncated or child.truncated
                excluded = excluded or child.excluded
            return SanitizationResult(
                output_items,
                redacted=redacted,
                truncated=truncated,
                excluded=excluded,
            )
        return SanitizationResult(
            {"$excluded": "live_object", "type": type(candidate).__name__},
            excluded=True,
        )

    return visit(value, 0)


def reject_unsafe_run_metadata(
    value: Mapping[str, Any],
    *,
    max_depth: int = 8,
    max_members: int = 200,
    max_bytes: int = 64 * 1024,
) -> dict[str, Any]:
    """Validate strict request metadata without transforming caller input.

    Args:
        value (Mapping[str, Any]): Candidate request metadata.
        max_depth (int): Maximum nested collection depth.
        max_members (int): Maximum aggregate collection member count.
        max_bytes (int): Maximum deterministic JSON byte size.

    Raises:
        ValueError: Metadata is unsafe, not finite JSON, or exceeds limits.

    Returns:
        dict[str, Any]: Detached JSON-compatible metadata copy.
    """
    import json

    members = [0]

    def visit(candidate: Any, depth: int, path: tuple[Any, ...]) -> Any:
        """Validate and detach one nested metadata value.

        Args:
            candidate (Any): Nested value.
            depth (int): Current depth.
            path (tuple[Any, ...]): Reader-facing field location.

        Raises:
            ValueError: Value violates request safety or resource limits.

        Returns:
            Any: Detached JSON-compatible value.
        """
        if depth > max_depth:
            raise ValueError(f"metadata exceeds maximum depth at {path}")
        if candidate is None or isinstance(candidate, (bool, int)):
            return candidate
        if isinstance(candidate, float):
            if not math.isfinite(candidate):
                raise ValueError(f"metadata has non-finite number at {path}")
            return candidate
        if isinstance(candidate, str):
            if (
                candidate.startswith(("/", "\\\\"))
                or re.match(r"^[A-Za-z]:[\\/]", candidate)
            ):
                raise ValueError(f"host path is not allowed at {path}")
            return candidate
        if isinstance(candidate, Mapping):
            output: dict[str, Any] = {}
            for raw_key, item in candidate.items():
                members[0] += 1
                if members[0] > max_members:
                    raise ValueError("metadata exceeds maximum member count")
                if not isinstance(raw_key, str):
                    raise ValueError(f"metadata key is not text at {path}")
                if is_sensitive_key(raw_key):
                    raise ValueError(f"sensitive metadata key is not allowed at {path}")
                output[raw_key] = visit(item, depth + 1, path + (raw_key,))
            return output
        if isinstance(candidate, (list, tuple)):
            output_items = []
            for index, item in enumerate(candidate):
                members[0] += 1
                if members[0] > max_members:
                    raise ValueError("metadata exceeds maximum member count")
                output_items.append(visit(item, depth + 1, path + (index,)))
            return output_items
        raise ValueError(f"metadata contains non-JSON value at {path}")

    detached = visit(value, 0, ("metadata",))
    encoded = json.dumps(
        detached,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    if len(encoded) > max_bytes:
        raise ValueError("metadata exceeds maximum serialized size")
    return detached


__all__ = [
    "SanitizationPolicy",
    "SanitizationResult",
    "is_sensitive_key",
    "redact_text",
    "reject_unsafe_run_metadata",
    "sanitize_runtime_value",
]
