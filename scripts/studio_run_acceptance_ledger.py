"""Strict bounded evidence ledger for ordinary Run experience acceptance."""

from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SCENARIOS = tuple([f"R{index:02d}" for index in range(1, 12)] + ["B01", "A01"])
Text = Annotated[str, Field(min_length=1, max_length=1000)]


class StrictEvidence(BaseModel):
    """Reject undeclared evidence fields and coercions."""

    model_config = ConfigDict(extra="forbid", strict=True)


class CommandEvidence(StrictEvidence):
    """Reproducible bounded command with its observed exit code."""

    command: Text
    exit_code: int


class ScenarioEvidence(StrictEvidence):
    """Separate test evidence, browser observations, and absent authorization."""

    scenario_id: str
    environment: Literal["fake", "android"]
    status: Literal["passed", "failed", "blocked", "not-run"]
    sources: list[Literal["contract-test", "route-test", "actual-backend-browser", "android-browser"]] = Field(max_length=4)
    expected: Text
    observed: Text
    commands: list[CommandEvidence] = Field(max_length=20)
    evidence_paths: list[str] = Field(max_length=20)
    agent_id: str | None = None
    revision_id: str | None = None
    run_id: str | None = None
    canonical_hash: str | None = None
    experiment_id: str | None = None
    task_run_id: str | None = None
    cursor: int | None = Field(default=None, ge=0)
    high_water_mark: int | None = Field(default=None, ge=0)

    @field_validator("evidence_paths")
    @classmethod
    def relative_paths(cls, paths: list[str]) -> list[str]:
        """Allow only bounded repository-relative evidence references.

        Args:
            paths: Retained evidence file names, never runtime absolute paths.
        Raises:
            ValueError: A reference escapes the repository or has an unsafe shape.
        Returns:
            Unchanged validated paths.
        """
        for value in paths:
            path = PurePosixPath(value)
            if not value or len(value) > 300 or path.is_absolute() or ".." in path.parts or ":" in value or "\\" in value:
                raise ValueError("evidence references must be bounded relative paths")
        return paths

    @model_validator(mode="after")
    def closure(self) -> "ScenarioEvidence":
        """Reject unsupported scenarios, identity leakage and unsupported pass claims.

        Raises:
            ValueError: Identity, status, cursor, or source closure is incomplete.
        Returns:
            Validated scenario without promoting skipped work into proof.
        """
        if self.scenario_id not in SCENARIOS:
            raise ValueError("unknown acceptance scenario")
        if (self.scenario_id == "A01") != (self.environment == "android"):
            raise ValueError("fake and Android evidence must remain separate")
        for value in (self.agent_id, self.revision_id, self.run_id, self.experiment_id, self.task_run_id, self.canonical_hash):
            if value is not None and (not value or len(value) > 150 or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_:" for c in value)):
                raise ValueError("identity must be an opaque bounded token")
        if self.cursor is not None and (self.high_water_mark is None or self.cursor > self.high_water_mark):
            raise ValueError("cursor must belong to the observed high-water prefix")
        if self.status == "passed":
            if not self.sources or not self.evidence_paths or not self.commands or any(c.exit_code != 0 for c in self.commands):
                raise ValueError("pass requires successful commands and retained evidence")
            if "actual-backend-browser" in self.sources and not all((self.agent_id, self.revision_id, self.run_id or self.experiment_id)):
                raise ValueError("browser pass requires exact resource identities")
            if self.scenario_id == "A01" and ("android-browser" not in self.sources or not self.run_id):
                raise ValueError("Android pass requires fresh Android browser evidence")
        return self


class RunAcceptanceLedger(StrictEvidence):
    """Complete scenario inventory; partial acceptance remains an explicit outcome."""

    schema_version: Literal[1]
    code_revision: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    dirty_baseline: Text
    scenarios: list[ScenarioEvidence] = Field(min_length=13, max_length=13)
    forbidden_effects: dict[Literal["real-device", "external-network", "real-secret"], int | None]

    @model_validator(mode="after")
    def inventory(self) -> "RunAcceptanceLedger":
        """Require a complete matrix and honest unmeasured safety counters.

        Raises:
            ValueError: Scenarios/canaries are missing, duplicated or negative.
        Returns:
            Ledger retaining failed, blocked and unexecuted scenarios.
        """
        if tuple(s.scenario_id for s in self.scenarios) != SCENARIOS:
            raise ValueError("ledger must contain the exact ordered scenario inventory")
        if set(self.forbidden_effects) != {"real-device", "external-network", "real-secret"}:
            raise ValueError("all forbidden-effect counters must be present")
        if any(n is not None and n < 0 for n in self.forbidden_effects.values()):
            raise ValueError("negative effect count")
        return self
