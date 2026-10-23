"""Pydantic models for the canonical Agent YAML contract."""

from __future__ import annotations

from typing import Any, Dict, Literal

from pydantic import Field, StrictBool, field_validator

from .common import (
    ComponentReference,
    DeviceReference,
    GlobalConfig,
    StrictContractModel,
    ensure_json_compatible,
)


class ModularStrategy(StrictContractModel):
    pass


class ReflectionStrategy(StrictContractModel):
    use_experience_cache: StrictBool = False


class MultiAgentStrategy(ReflectionStrategy):
    manager_each_step: StrictBool = True


class UGroundStrategy(StrictContractModel):
    summarize_steps: StrictBool = True
    summary_prompt_file: str = "summary_seeact_uground.md"
    hide_automation_ui_on_reset: StrictBool = True


class AgentComponents(StrictContractModel):
    perception: ComponentReference | list[ComponentReference]
    reasoning: ComponentReference
    memory: ComponentReference
    planner: ComponentReference | None = None
    verifier: ComponentReference | None = None
    grounder: ComponentReference | None = None

    @field_validator("perception")
    @classmethod
    def _non_empty_perception(
        cls, value: ComponentReference | list[ComponentReference]
    ) -> ComponentReference | list[ComponentReference]:
        if isinstance(value, list) and not value:
            raise ValueError("perception fallback list must not be empty")
        return value

    def iter_slots(self):
        for role in ("perception", "reasoning", "memory", "planner", "verifier", "grounder"):
            value = getattr(self, role)
            if value is None:
                continue
            if isinstance(value, list):
                for index, component in enumerate(value):
                    yield role, index, component
            else:
                yield role, None, value


class AgentDefinition(StrictContractModel):
    strategy: Dict[str, Any] = Field(default_factory=dict)
    components: AgentComponents

    @field_validator("strategy")
    @classmethod
    def _json_strategy(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        ensure_json_compatible(value)
        return value


class AgentConfig(StrictContractModel):
    schema_version: Literal[1]
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    agent_type: str = Field(min_length=1)
    device: DeviceReference
    agent: AgentDefinition

    @field_validator("agent_type")
    @classmethod
    def _agent_type_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent_type must not be blank")
        return value

    def canonical_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)
