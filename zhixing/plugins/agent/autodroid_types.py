"""Implementation-owned AutoDroid data; no new public component contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AutoDroidModel(BaseModel):
    """Reject unknown fields and freeze algorithm data at component boundaries."""

    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Target(AutoDroidModel):
    """A semantic UI target or logical scroll operation, never stale pixels."""

    key: str = ""
    description: str = ""
    state_id: str = ""
    operation: Literal["tap", "input", "scroll", "back"] = "tap"
    text: str = ""
    direction: Literal["up", "down", "left", "right"] = "down"

    @model_validator(mode="after")
    def validate_locator(self) -> "Target":
        """Require a locator for UI operations.

        Raises:
            ValueError: A UI target lacks a locator or a scroll lacks a region key.
        Returns:
            Target: The validated immutable target.
        """
        if self.operation in {"tap", "input"} and not (self.key or self.description):
            raise ValueError("UI target requires key or description")
        if self.operation == "scroll" and not self.key:
            raise ValueError("scroll target requires a region key")
        return self


class Candidate(AutoDroidModel):
    """One prompt choice and the identity used to resolve it on a live frame."""

    choice_id: int = Field(ge=0)
    key: str
    tag: Literal["button", "input", "checkbox", "p"]
    text: str = ""
    label: str = ""
    checked: bool = False
    bounds: tuple[int, int, int, int]
    region_key: str = ""
    interactive: bool = True
    description: str
    prefix: tuple[Target, ...] = ()


class ScrollRegion(AutoDroidModel):
    """A scroll container identified independently of its current contents."""

    key: str
    bounds: tuple[int, int, int, int]


class UIState(AutoDroidModel):
    """Portable current-frame UI data returned by Perception."""

    state_id: str
    app_id: str
    candidates: tuple[Candidate, ...]
    regions: tuple[ScrollRegion, ...] = ()


class MemoryEntry(AutoDroidModel):
    """One simulated task, its navigation path and cached semantic embedding."""

    id: str
    task: str = Field(min_length=1)
    function: str = ""
    path: tuple[Target, ...] = ()
    embedding: tuple[float, ...] = ()

    @field_validator("embedding", mode="before")
    @classmethod
    def validate_embedding_values(cls, value: object) -> object:
        """Reject boolean vectors before floating-point coercion.

        Args:
            value: Caller-owned cached vector.
        Raises:
            ValueError: A cached vector uses booleans instead of numbers.
        Returns:
            object: Original value for ordinary shape and finite-value validation.
        """
        if isinstance(value, (tuple, list)) and any(isinstance(item, bool) for item in value):
            raise ValueError("embedding values cannot be boolean")
        return value


class AppMemory(AutoDroidModel):
    """Versioned input to the online agent; no offline task synthesis is implied."""

    schema_version: Literal[1] = 1
    app_id: str = Field(min_length=1)
    embedding_model: str = "hkunlp/instructor-xl"
    embedding_instruction: str = "Represent the task for retrieval: "
    entries: tuple[MemoryEntry, ...]
    equivalent_groups: dict[str, tuple[tuple[str, ...], ...]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_entries(self) -> "AppMemory":
        """Check entry identities and cached embedding dimensions.

        Raises:
            ValueError: Entries are empty, duplicated or dimensionally inconsistent.
        Returns:
            AppMemory: The validated snapshot.
        """
        if not self.entries or len({entry.id for entry in self.entries}) != len(self.entries):
            raise ValueError("App Memory requires nonempty unique entry ids")
        dimensions = {len(entry.embedding) for entry in self.entries if entry.embedding}
        if len(dimensions) > 1:
            raise ValueError("inconsistent cached embedding dimensions")
        return self


class GuideHit(AutoDroidModel):
    """A retrieved entry and its cosine similarity."""

    entry: MemoryEntry
    score: float = Field(ge=-1.000001, le=1.000001)


class Guide(AutoDroidModel):
    """Structured knowledge delivered through existing MemoryFragment values."""

    app_id: str
    hits: tuple[GuideHit, ...] = ()
    equivalent_groups: dict[str, tuple[tuple[str, ...], ...]] = Field(default_factory=dict)


class Choice(AutoDroidModel):
    """Validated model selection before conversion into canonical Action."""

    choice_id: int = Field(ge=-1)
    operation: Literal["tap", "input"] = "tap"
    text: str = ""
    thought: str = ""


@dataclass
class ScanState:
    """Task-local bounded collection of independent scroll regions."""

    regions: tuple[ScrollRegion, ...]
    index: int = 0
    phase: str = "top"
    previous_signature: str | None = None
    waiting: str = ""
    attempts: int = 0
    offset: int = 0
    top_signature: str = ""
    candidates: list[Candidate] = field(default_factory=list)


@dataclass
class PolicyState:
    """Reasoning state owned by one RuntimeContext, not by a shared instance."""

    shortcut_attempted: bool = False
    pending: list[Target] = field(default_factory=list)
    pending_kind: str = ""
    scan: ScanState | None = None
    scanned: tuple[Candidate, ...] | None = None


def stable_id(value: object) -> str:
    """Hash JSON-compatible UI identity deterministically.

    Args:
        value: Stable structural UI values, excluding device handles.
    Returns:
        str: A SHA-256 hex digest.
    """
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def normalize_description(value: str) -> str:
    """Normalize upstream HTML descriptions without discarding element text.

    Args:
        value: UI HTML with an optional transient numerical id.
    Returns:
        str: A comparison-only description, never executable HTML.
    """
    value = re.sub(r"\s+id=(?:['\"]\d+['\"]|\d+)", "", value)
    return " ".join(value.replace('"', "'").split())
