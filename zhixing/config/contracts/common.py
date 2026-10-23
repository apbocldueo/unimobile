"""Common strict models and JSON-compatible parameter validation."""

from __future__ import annotations

import math
from typing import Any, Dict

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator


class StrictContractModel(BaseModel):
    """Strict envelope model: extension is allowed only inside params mappings."""

    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


def ensure_json_compatible(value: Any, path: tuple[Any, ...] = ()) -> Any:
    """Reject non-JSON values while preserving insertion order and original values."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"non-finite float at {path or ('<root>',)}")
        return value
    if isinstance(value, list):
        for index, item in enumerate(value):
            ensure_json_compatible(item, path + (index,))
        return value
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"non-string mapping key at {path + (key,)}")
            ensure_json_compatible(item, path + (key,))
        return value
    raise ValueError(f"non-JSON value {type(value).__name__} at {path or ('<root>',)}")


class PluginReference(StrictContractModel):
    name: str = Field(min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def _non_blank_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        return value

    @field_validator("params")
    @classmethod
    def _json_params(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        ensure_json_compatible(value)
        return value


class LLMReference(PluginReference):
    pass


class ComponentReference(PluginReference):
    llm: LLMReference | None = None


class DeviceReference(PluginReference):
    pass


class GlobalConfig(StrictContractModel):
    verbose: StrictBool = True
    default_llm: LLMReference | None = None
