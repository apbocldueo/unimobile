"""Recursive safe-export policy shared by Benchmark reports and trajectories."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

_SECRET_PARTS = (
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
)
_SAFE_TOKEN_FIELDS = {
    "completion_tokens",
    "input_tokens",
    "output_tokens",
    "prompt_tokens",
    "require_observable_tokens",
    "token_count",
    "token_limit",
    "total_tokens",
}
_DEVICE_KEYS = {
    "device_handle",
    "device_id",
    "device_serial",
    "serial",
    "adb_serial",
}
_PRIVATE_AUTHORITY_KEYS = {
    "adb_argument",
    "adb_arguments",
    "adb_args",
    "binding_fingerprint",
    "config_path",
    "configuration_path",
    "target_key",
}
_ABSOLUTE_PATH = re.compile(
    r"(?:file://)?(?:/Users|/home|/tmp|/private|/var|/opt)/[^\s'\"<>]*"
)
_CREDENTIAL_URL = re.compile(
    r"(?P<scheme>[a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@",
    flags=re.IGNORECASE,
)
_EMULATOR_SERIAL = re.compile(r"\bemulator-\d+\b")
_ADB_COMMAND = re.compile(r"(?i)\badb(?:\.exe)?\s+-[^\r\n]{1,256}")


@dataclass(frozen=True)
class ExportDiagnostic:
    """One field-level safe-export action."""

    code: str
    path: tuple[str | int, ...]
    action: str

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the diagnostic without the rejected value.

        Returns:
            dict[str, Any]: Safe diagnostic mapping.
        """
        return {
            "code": self.code,
            "path": [str(item) for item in self.path],
            "action": self.action,
        }


def _is_secret_key(key: Any) -> bool:
    """Return whether a mapping key identifies likely credential material.

    Args:
        key (Any): Candidate mapping key.

    Raises:
        None.

    Returns:
        bool: True for a recognized secret marker.
    """
    normalized = str(key).lower().replace("-", "_")
    if normalized in _SAFE_TOKEN_FIELDS:
        return False
    return any(part in normalized for part in _SECRET_PARTS)


def _safe_device_id(value: Any) -> str:
    """Return a non-reversible device identity reference.

    Args:
        value (Any): Raw or already-safe device identifier.

    Raises:
        None.

    Returns:
        str: Empty, existing safe hash, or short SHA-256 reference.
    """
    text = str(value or "")
    if not text or text.startswith("device-sha256:"):
        return text
    return "device-sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def sanitize_export(
    value: Any,
    *,
    path: tuple[str | int, ...] = (),
    diagnostics: list[ExportDiagnostic] | None = None,
) -> tuple[Any, tuple[ExportDiagnostic, ...]]:
    """Recursively convert a runtime value into safe JSON-compatible data.

    Args:
        value (Any): Value to sanitize.
        path (tuple[str | int, ...]): Logical field path.
        diagnostics (list[ExportDiagnostic] | None): Shared action collector.

    Raises:
        None.

    Returns:
        tuple[Any, tuple[ExportDiagnostic, ...]]: Safe value and diagnostics.
    """
    collected = diagnostics if diagnostics is not None else []
    if value is None or isinstance(value, (bool, int, float)):
        return value, tuple(collected)
    if isinstance(value, str):
        safe = _CREDENTIAL_URL.sub(r"\g<scheme><redacted>@", value)
        safe = _ABSOLUTE_PATH.sub("<host-path>", safe)
        safe = _ADB_COMMAND.sub("<adb-command>", safe)
        if _EMULATOR_SERIAL.search(safe):
            safe = _EMULATOR_SERIAL.sub("<device-id>", safe)
            collected.append(
                ExportDiagnostic(
                    code="benchmark.export.device_id_redacted",
                    path=path,
                    action="redacted",
                )
            )
        if safe != value and not any(item.path == path for item in collected):
            collected.append(
                ExportDiagnostic(
                    code="benchmark.export.text_redacted",
                    path=path,
                    action="redacted",
                )
            )
        return safe[:4000], tuple(collected)
    if isinstance(value, Path):
        collected.append(
            ExportDiagnostic(
                code="benchmark.export.host_path_redacted",
                path=path,
                action="redacted",
            )
        )
        return "<host-path>", tuple(collected)
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            safe_key = str(key)[:128]
            child_path = (*path, safe_key)
            if _is_secret_key(safe_key):
                result[safe_key] = "<redacted>"
                collected.append(
                    ExportDiagnostic(
                        code="benchmark.export.secret_redacted",
                        path=child_path,
                        action="redacted",
                    )
                )
                continue
            if safe_key.lower() in _PRIVATE_AUTHORITY_KEYS:
                result[safe_key] = "<redacted>"
                collected.append(
                    ExportDiagnostic(
                        code="benchmark.export.private_authority_redacted",
                        path=child_path,
                        action="redacted",
                    )
                )
                continue
            if safe_key.lower() in _DEVICE_KEYS:
                result[safe_key] = _safe_device_id(item)
                if item:
                    collected.append(
                        ExportDiagnostic(
                            code="benchmark.export.device_id_hashed",
                            path=child_path,
                            action="hashed",
                        )
                    )
                continue
            result[safe_key], _ = sanitize_export(
                item,
                path=child_path,
                diagnostics=collected,
            )
        return result, tuple(collected)
    if isinstance(value, (list, tuple, set, frozenset)):
        result_list = []
        for index, item in enumerate(value):
            safe_item, _ = sanitize_export(
                item,
                path=(*path, index),
                diagnostics=collected,
            )
            result_list.append(safe_item)
        return result_list, tuple(collected)
    to_safe_dict = getattr(value, "to_safe_dict", None)
    if callable(to_safe_dict):
        return sanitize_export(
            to_safe_dict(),
            path=path,
            diagnostics=collected,
        )
    collected.append(
        ExportDiagnostic(
            code="benchmark.export.live_object_rejected",
            path=path,
            action="rejected",
        )
    )
    return f"<{type(value).__name__}>", tuple(collected)


def safe_export(value: Any) -> Any:
    """Return only the sanitized value for ordinary writers.

    Args:
        value (Any): Runtime value.

    Raises:
        None.

    Returns:
        Any: JSON-compatible safe value.
    """
    return sanitize_export(value)[0]


__all__ = ["ExportDiagnostic", "safe_export", "sanitize_export"]
