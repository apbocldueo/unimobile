"""Canonical JSON and semantic identities for Benchmark definitions."""

from __future__ import annotations

import hashlib
import json
import math
import re
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from .constants import BENCHMARK_CANONICALIZATION_VERSION

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "credential",
    "credentials",
    "device_handle",
    "device_serial",
    "password",
    "secret",
    "token",
}
_RUNTIME_PATH_KEYS = {
    "artifact_root",
    "cwd",
    "output_dir",
    "output_path",
}
_RUNTIME_IDENTITY_KEYS = {"device_handle", "device_serial"}
_SECRET_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


def _is_safe_secret_ref(value: Any) -> bool:
    """Recognize the only credential-shaped value allowed in semantic data.

    Args:
        value: Candidate value stored below a sensitive key.

    Raises:
        None.

    Returns:
        bool: True only for one strict stable SecretRef mapping.
    """
    return bool(
        isinstance(value, Mapping)
        and set(value) == {"secret_ref"}
        and isinstance(value.get("secret_ref"), str)
        and _SECRET_REF.fullmatch(str(value["secret_ref"]))
    )


def canonical_primitive(value: Any, *, path: tuple[str | int, ...] = ()) -> Any:
    """Convert supported values into deterministic JSON primitives.

    Args:
        value (Any): Value to normalize.
        path (tuple[str | int, ...]): Diagnostic path used in failures.

    Raises:
        ValueError: Value is non-JSON, non-finite, or contains forbidden keys.

    Returns:
        Any: Canonical JSON-compatible value.
    """
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float at {path or ('<root>',)}")
        return 0.0 if value == 0 else value
    if isinstance(value, Enum):
        return canonical_primitive(value.value, path=path)
    if isinstance(value, Path):
        raise ValueError(f"filesystem path is not semantic data at {path or ('<root>',)}")
    if isinstance(value, (list, tuple)):
        return [
            canonical_primitive(item, path=path + (index,))
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise ValueError(f"non-string key at {path + (str(key),)}")
            normalized_key = key.strip().lower().replace("-", "_")
            if (
                normalized_key in _RUNTIME_PATH_KEYS
                or normalized_key in _RUNTIME_IDENTITY_KEYS
                or (
                    normalized_key in _SENSITIVE_KEYS
                    and not _is_safe_secret_ref(value[key])
                )
            ):
                raise ValueError(f"forbidden runtime or secret field at {path + (key,)}")
            normalized[key] = canonical_primitive(value[key], path=path + (key,))
        return normalized
    if hasattr(value, "model_dump"):
        return canonical_primitive(
            value.model_dump(mode="python", exclude_none=True),
            path=path,
        )
    raise ValueError(
        f"canonical JSON cannot represent {type(value).__name__} "
        f"at {path or ('<root>',)}"
    )


def canonical_json(value: Any) -> str:
    """Serialize one value as stable compact canonical JSON.

    Args:
        value (Any): Supported semantic value.

    Raises:
        ValueError: Canonical projection fails.

    Returns:
        str: Stable UTF-8 JSON text.
    """
    envelope = {
        "canonicalization_version": BENCHMARK_CANONICALIZATION_VERSION,
        "value": canonical_primitive(value),
    }
    return json.dumps(
        envelope,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def canonical_hash(value: Any) -> str:
    """Compute a SHA-256 identity for semantic Benchmark data.

    Args:
        value (Any): Supported semantic value.

    Raises:
        ValueError: Canonical projection fails.

    Returns:
        str: ``sha256:``-prefixed content identity.
    """
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
