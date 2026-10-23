"""Strict safe two-axis execution-evidence provenance models."""

from __future__ import annotations

import re
from typing import Any, Literal, Mapping

from pydantic import Field, field_validator, model_validator

from .models import StudioModel


EvidenceAcquisition = Literal[
    "fresh_execution",
    "replay_projection",
    "imported_excerpt",
    "contract_fixture",
]
EvidenceEnvironment = Literal["real_android", "fake_device", "unverified"]
_STABLE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")


class StudioDeviceContextCheckV1(StudioModel):
    """One bounded safe Core device-context check without target identity."""

    name: Literal["platform", "locale", "orientation", "apps"]
    passed: bool
    observed: str = Field(default="", max_length=160)

    @field_validator("observed")
    @classmethod
    def _safe_observed(cls, value: str) -> str:
        """Reject path/control-shaped observed context text.

        Args:
            value: Candidate Core-observed safe context value.

        Raises:
            ValueError: Value is path-like or contains line breaks.

        Returns:
            Bounded one-line observed value.
        """
        if "\n" in value or "\r" in value or value.startswith(("/", "\\")):
            raise ValueError("device context observation is unsafe")
        return value[:160]


class StudioExecutionEvidenceOriginV1(StudioModel):
    """Independent acquisition/environment evidence facts for public use."""

    schema_version: Literal[1] = 1
    acquisition: EvidenceAcquisition = "fresh_execution"
    environment: EvidenceEnvironment = "unverified"
    device_profile_id: str | None = Field(default=None, max_length=160)
    device_checks: tuple[StudioDeviceContextCheckV1, ...] = Field(
        default=(),
        max_length=4,
    )
    real_device_evidence: bool = False

    @field_validator("device_profile_id")
    @classmethod
    def _safe_profile(cls, value: str | None) -> str | None:
        """Validate an optional safe profile identity.

        Args:
            value: Candidate browser-safe profile identity.

        Raises:
            ValueError: Identity is unstable.

        Returns:
            Validated optional identity.
        """
        if value is not None and _STABLE_ID.fullmatch(value) is None:
            raise ValueError("invalid evidence profile identity")
        return value

    @model_validator(mode="after")
    def _derived_real_evidence(self) -> "StudioExecutionEvidenceOriginV1":
        """Require real-device evidence to follow exact source facts only.

        Args:
            None.

        Raises:
            ValueError: Boolean claims disagree with the two typed axes.

        Returns:
            Validated origin.
        """
        expected = (
            self.acquisition == "fresh_execution"
            and self.environment == "real_android"
        )
        if self.real_device_evidence != expected:
            raise ValueError("real-device evidence disagrees with source facts")
        if len({item.name for item in self.device_checks}) != len(
            self.device_checks
        ):
            raise ValueError("device context checks must be unique")
        return self

    @classmethod
    def from_runtime(
        cls,
        *,
        acquisition: EvidenceAcquisition,
        environment: EvidenceEnvironment,
        device_profile_id: str | None,
        device_provenance: Mapping[str, Any],
    ) -> "StudioExecutionEvidenceOriginV1":
        """Project safe Core check outcomes while dropping target references.

        Args:
            acquisition: How the evidence was acquired.
            environment: Verified or unverified source execution environment.
            device_profile_id: Optional safe Studio profile identity.
            device_provenance: Core-owned context preflight facts.

        Raises:
            ValueError: Projected safe facts violate the strict DTO.

        Returns:
            Strict two-axis provenance with at most four safe checks.
        """
        raw_checks = device_provenance.get("checks")
        checks = raw_checks if isinstance(raw_checks, Mapping) else {}
        observed_values = {
            "platform": device_provenance.get("platform"),
            "locale": device_provenance.get("locale"),
            "orientation": device_provenance.get("orientation"),
            "apps": (
                "verified"
                if bool(device_provenance.get("apps_verifiable"))
                else "unverified"
            ),
        }
        projected = tuple(
            StudioDeviceContextCheckV1(
                name=name,  # type: ignore[arg-type]
                passed=bool(checks.get(name, False)),
                observed=str(observed_values.get(name) or "unverified")[:160],
            )
            for name in ("platform", "locale", "orientation", "apps")
            if name in checks
        )
        return cls(
            acquisition=acquisition,
            environment=environment,
            device_profile_id=device_profile_id,
            device_checks=projected,
            real_device_evidence=(
                acquisition == "fresh_execution"
                and environment == "real_android"
            ),
        )

    def with_acquisition(
        self,
        acquisition: EvidenceAcquisition,
    ) -> "StudioExecutionEvidenceOriginV1":
        """Change transport acquisition while preserving source environment.

        Args:
            acquisition: New truthful acquisition axis.

        Raises:
            ValueError: Resulting typed facts are inconsistent.

        Returns:
            New immutable origin.
        """
        return self.model_copy(
            update={
                "acquisition": acquisition,
                "real_device_evidence": (
                    acquisition == "fresh_execution"
                    and self.environment == "real_android"
                ),
            }
        )


def replay_import_origin(
    provenance: str,
) -> StudioExecutionEvidenceOriginV1:
    """Map only explicit legacy provenance facts to safe typed origin.

    Args:
        provenance: Backward-compatible Replay provenance label.

    Raises:
        None.

    Returns:
        Truthful import/fixture origin; absent facts stay unverified.
    """
    if provenance == "real_android_excerpt":
        return StudioExecutionEvidenceOriginV1(
            acquisition="imported_excerpt",
            environment="real_android",
            real_device_evidence=False,
        )
    if provenance == "fake_contract_fixture":
        return StudioExecutionEvidenceOriginV1(
            acquisition="contract_fixture",
            environment="fake_device",
            real_device_evidence=False,
        )
    return StudioExecutionEvidenceOriginV1(
        acquisition="imported_excerpt",
        environment="unverified",
        real_device_evidence=False,
    )


def legacy_replay_origin(
    provenance: str,
) -> StudioExecutionEvidenceOriginV1:
    """Derive backward-readable typed origin from one legacy Replay label.

    Args:
        provenance: Stored legacy adapter/transport provenance.

    Raises:
        None.

    Returns:
        Conservative acquisition with unverified environment when absent.
    """
    if provenance in {"native_benchmark_task_run", "native_studio_run"}:
        return StudioExecutionEvidenceOriginV1(
            acquisition="replay_projection",
            environment="unverified",
        )
    return replay_import_origin(provenance)


__all__ = [
    "EvidenceAcquisition",
    "EvidenceEnvironment",
    "StudioDeviceContextCheckV1",
    "StudioExecutionEvidenceOriginV1",
    "replay_import_origin",
    "legacy_replay_origin",
]
