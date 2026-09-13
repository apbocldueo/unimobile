"""Bounded trusted SecretRef configuration for the local Studio process."""

from __future__ import annotations

import math
import os
import re
import stat
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import yaml


STUDIO_SECRETS_ENV = "ZHIXING_STUDIO_SECRETS"
MAX_STUDIO_SECRETS_BYTES = 64 * 1024
MAX_STUDIO_SECRET_COUNT = 256
MAX_STUDIO_SECRET_VALUE_CHARACTERS = 8192
_SECRET_REF = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,127}$")


class StudioSecretsConfigurationError(ValueError):
    """Report one safe startup configuration failure without source details."""

    def __init__(self, code: str, message: str) -> None:
        """Create a bounded path- and value-free error.

        Args:
            code: Stable machine-readable configuration code.
            message: Safe operator-facing explanation.

        Raises:
            None.

        Returns:
            None.
        """
        safe_message = str(message).replace("\r", " ").replace("\n", " ")[:500]
        super().__init__(safe_message)
        self.code = str(code)[:160]
        self.message = safe_message


def resolve_studio_secrets_path(
    cli_path: str | Path | None,
    *,
    environment: Mapping[str, str] | None = None,
) -> Path | None:
    """Resolve CLI-over-environment trusted secret configuration authority.

    Args:
        cli_path: Explicit command-line path, if supplied.
        environment: Optional environment mapping used by deterministic tests.

    Raises:
        None.

    Returns:
        Path | None: Selected unexpanded path, or no configured authority.
    """
    if cli_path is not None:
        return Path(cli_path)
    source = os.environ if environment is None else environment
    value = source.get(STUDIO_SECRETS_ENV, "").strip()
    return Path(value) if value else None


def _valid_scalar(value: Any) -> bool:
    """Return whether a YAML value is an allowed bounded runtime scalar.

    Args:
        value: Parsed YAML value.

    Raises:
        None.

    Returns:
        bool: True for supported finite scalar values.
    """
    if isinstance(value, str):
        return 0 < len(value) <= MAX_STUDIO_SECRET_VALUE_CHARACTERS
    if isinstance(value, bool) or isinstance(value, int):
        return True
    return isinstance(value, float) and math.isfinite(value)


def load_studio_secrets(
    path: str | Path | None,
) -> Mapping[str, str | bool | int | float]:
    """Load one bounded regular YAML mapping without persisting its values.

    Args:
        path: Trusted local YAML file selected by startup configuration.

    Raises:
        StudioSecretsConfigurationError: The file authority, size, YAML shape,
            identity, or scalar value is unsafe.

    Returns:
        Mapping[str, str | bool | int | float]: Immutable process-scoped values.
    """
    if path is None:
        return MappingProxyType({})
    candidate = Path(path).expanduser()
    try:
        file_stat = candidate.stat()
    except OSError as error:
        raise StudioSecretsConfigurationError(
            "studio.secrets.file_unavailable",
            "Studio secret configuration file is unavailable",
        ) from error
    if candidate.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
        raise StudioSecretsConfigurationError(
            "studio.secrets.file_invalid",
            "Studio secret configuration must be a regular file",
        )
    if file_stat.st_size > MAX_STUDIO_SECRETS_BYTES:
        raise StudioSecretsConfigurationError(
            "studio.secrets.file_too_large",
            "Studio secret configuration exceeds the size limit",
        )
    try:
        raw_bytes = candidate.read_bytes()
    except OSError as error:
        raise StudioSecretsConfigurationError(
            "studio.secrets.file_unavailable",
            "Studio secret configuration file cannot be read",
        ) from error
    if len(raw_bytes) > MAX_STUDIO_SECRETS_BYTES:
        raise StudioSecretsConfigurationError(
            "studio.secrets.file_too_large",
            "Studio secret configuration exceeds the size limit",
        )
    try:
        payload = yaml.safe_load(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, yaml.YAMLError) as error:
        raise StudioSecretsConfigurationError(
            "studio.secrets.content_invalid",
            "Studio secret configuration is not valid UTF-8 YAML",
        ) from error
    if payload is None:
        payload = {}
    if not isinstance(payload, Mapping) or len(payload) > MAX_STUDIO_SECRET_COUNT:
        raise StudioSecretsConfigurationError(
            "studio.secrets.mapping_invalid",
            "Studio secret configuration must be a bounded mapping",
        )
    values: dict[str, str | bool | int | float] = {}
    for key, value in payload.items():
        if not isinstance(key, str) or _SECRET_REF.fullmatch(key) is None:
            raise StudioSecretsConfigurationError(
                "studio.secrets.identity_invalid",
                "Studio secret configuration contains an invalid SecretRef identity",
            )
        if not _valid_scalar(value):
            raise StudioSecretsConfigurationError(
                "studio.secrets.value_invalid",
                "Studio secret configuration contains an unsupported scalar value",
            )
        values[key] = value
    return MappingProxyType(values)


__all__ = [
    "MAX_STUDIO_SECRET_COUNT",
    "MAX_STUDIO_SECRETS_BYTES",
    "STUDIO_SECRETS_ENV",
    "StudioSecretsConfigurationError",
    "load_studio_secrets",
    "resolve_studio_secrets_path",
]
