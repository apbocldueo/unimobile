"""Tests for bounded process-scoped Studio SecretRef configuration."""

from __future__ import annotations

from pathlib import Path

import pytest

from zhixing.studio.secrets import (
    MAX_STUDIO_SECRETS_BYTES,
    STUDIO_SECRETS_ENV,
    StudioSecretsConfigurationError,
    load_studio_secrets,
    resolve_studio_secrets_path,
)


def test_secret_path_uses_cli_over_environment(tmp_path: Path) -> None:
    """Give the explicit CLI file precedence over the environment fallback."""
    cli = tmp_path / "cli.yaml"
    environment = tmp_path / "environment.yaml"
    assert resolve_studio_secrets_path(
        cli,
        environment={STUDIO_SECRETS_ENV: str(environment)},
    ) == cli
    assert resolve_studio_secrets_path(
        None,
        environment={STUDIO_SECRETS_ENV: str(environment)},
    ) == environment


def test_secret_loader_accepts_only_bounded_scalar_mapping(tmp_path: Path) -> None:
    """Load stable identities while keeping the result immutable."""
    source = tmp_path / "secrets.yaml"
    source.write_text("openai_api_key: fixture-value\nretry_budget: 2\n", encoding="utf-8")
    values = load_studio_secrets(source)
    assert values == {"openai_api_key": "fixture-value", "retry_budget": 2}
    with pytest.raises(TypeError):
        values["openai_api_key"] = "replacement"  # type: ignore[index]


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ("- list-entry\n", "studio.secrets.mapping_invalid"),
        ("bad identity: value\n", "studio.secrets.identity_invalid"),
        ("secret: [nested]\n", "studio.secrets.value_invalid"),
        ("secret: null\n", "studio.secrets.value_invalid"),
        ("unterminated: [\n", "studio.secrets.content_invalid"),
    ],
)
def test_secret_loader_returns_safe_errors(
    tmp_path: Path,
    content: str,
    code: str,
) -> None:
    """Reject malformed input without echoing source values or host paths."""
    source = tmp_path / "private-value.yaml"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(StudioSecretsConfigurationError) as captured:
        load_studio_secrets(source)
    assert captured.value.code == code
    assert str(source) not in str(captured.value)
    assert "nested" not in str(captured.value)


def test_secret_loader_rejects_missing_and_oversized_files(tmp_path: Path) -> None:
    """Fail closed before parsing absent or oversized configuration."""
    with pytest.raises(StudioSecretsConfigurationError) as captured:
        load_studio_secrets(tmp_path / "missing.yaml")
    assert captured.value.code == "studio.secrets.file_unavailable"
    oversized = tmp_path / "oversized.yaml"
    oversized.write_bytes(b"x" * (MAX_STUDIO_SECRETS_BYTES + 1))
    with pytest.raises(StudioSecretsConfigurationError) as captured:
        load_studio_secrets(oversized)
    assert captured.value.code == "studio.secrets.file_too_large"
