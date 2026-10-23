"""Pydantic models for canonical BenchmarkTask and BenchmarkSuite JSON."""

from __future__ import annotations

import math
from typing import Annotated, Any, Dict, Literal, Union

from pydantic import Field, RootModel, StrictBool, StrictInt, field_validator, model_validator

from .common import PluginReference, StrictContractModel, ensure_json_compatible


class EnvironmentPluginCall(PluginReference):
    """One ordered Benchmark environment operation."""

    namespace: str | None = None
    category: str | None = None
    phase: Literal["reset", "setup"] | None = None
    meta: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("namespace", "category")
    @classmethod
    def _optional_non_blank(cls, value: str | None) -> str | None:
        """Reject blank optional routing values.

        Args:
            value (str | None): Optional namespace or category.

        Raises:
            ValueError: Value is blank.

        Returns:
            str | None: Validated value.
        """
        if value is not None and not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("meta")
    @classmethod
    def _json_meta(cls, value: Dict[str, Any]) -> Dict[str, Any]:
        """Validate operation metadata as JSON-compatible data.

        Args:
            value (Dict[str, Any]): Metadata mapping.

        Raises:
            ValueError: Metadata contains unsupported values.

        Returns:
            Dict[str, Any]: Validated metadata.
        """
        ensure_json_compatible(value)
        return value


class LeafEvaluatorParams(StrictContractModel):
    model_config = StrictContractModel.model_config | {"extra": "allow"}
    method: str = Field(min_length=1)

    @field_validator("method")
    @classmethod
    def _method_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("method must not be blank")
        return value


class LeafEvaluator(StrictContractModel):
    name: str = Field(min_length=1)
    params: LeafEvaluatorParams

    @field_validator("name")
    @classmethod
    def _leaf_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name must not be blank")
        if value in {"composite", "eval_composite"}:
            raise ValueError("leaf evaluator name cannot be composite or eval_composite")
        return value


class CompositeEvaluatorParams(StrictContractModel):
    logic: Literal["AND", "OR", "SEQUENCE", "THRESHOLD", "WEIGHTED"]
    rules: list["EvaluatorNode"] = Field(min_length=1)
    min_passed: StrictInt | None = Field(default=None, gt=0)
    min_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    pass_threshold: float | None = Field(default=None, ge=0.0, le=1.0)
    weights: list[float] | None = None

    @model_validator(mode="after")
    def _logic_parameters(self) -> "CompositeEvaluatorParams":
        """Validate logic-specific threshold and weight parameters.

        Raises:
            ValueError: Parameters are missing, conflicting, or non-finite.

        Returns:
            CompositeEvaluatorParams: Validated composite parameters.
        """
        threshold_fields = (self.min_passed, self.min_ratio)
        if self.logic == "THRESHOLD":
            if sum(value is not None for value in threshold_fields) != 1:
                raise ValueError(
                    "THRESHOLD requires exactly one of min_passed or min_ratio"
                )
            if self.pass_threshold is not None or self.weights is not None:
                raise ValueError("THRESHOLD does not accept weighted parameters")
            if self.min_passed is not None and self.min_passed > len(self.rules):
                raise ValueError("min_passed cannot exceed the number of rules")
        elif self.logic == "WEIGHTED":
            if self.pass_threshold is None or self.weights is None:
                raise ValueError(
                    "WEIGHTED requires pass_threshold and one weight per rule"
                )
            if len(self.weights) != len(self.rules):
                raise ValueError("WEIGHTED requires one weight per rule")
            if any(
                not math.isfinite(value) or value <= 0 for value in self.weights
            ):
                raise ValueError("WEIGHTED weights must be positive and finite")
            if threshold_fields != (None, None):
                raise ValueError("WEIGHTED does not accept threshold count fields")
        elif any(
            value is not None
            for value in (
                self.min_passed,
                self.min_ratio,
                self.pass_threshold,
                self.weights,
            )
        ):
            raise ValueError(f"{self.logic} does not accept threshold parameters")
        return self


class CompositeEvaluator(StrictContractModel):
    name: Literal["composite"]
    params: CompositeEvaluatorParams


EvaluatorNode = Annotated[
    Union[CompositeEvaluator, LeafEvaluator], Field(union_mode="left_to_right")
]
CompositeEvaluatorParams.model_rebuild()


class BenchmarkTask(StrictContractModel):
    """Canonical task definition independent of a concrete Agent."""

    id: str = Field(min_length=1)
    instruction: str = Field(min_length=1)
    app: str | None = None
    type: Literal["static", "dynamic"]
    task_initializer: Dict[str, PluginReference]
    environment_initializer: list[EnvironmentPluginCall]
    cleanup_initializer: list[EnvironmentPluginCall] = Field(default_factory=list)
    evaluator: EvaluatorNode
    requires_login: StrictBool | None = None
    max_steps: StrictInt | None = Field(default=None, gt=0)

    @field_validator("id", "instruction")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        """Reject blank task identity or instruction.

        Args:
            value (str): Field value.

        Raises:
            ValueError: Value is blank.

        Returns:
            str: Validated value.
        """
        if not value.strip():
            raise ValueError("value must not be blank")
        return value

    @field_validator("app")
    @classmethod
    def _app_not_blank(cls, value: str | None) -> str | None:
        """Reject a blank optional App identifier.

        Args:
            value (str | None): Optional App identifier.

        Raises:
            ValueError: Value is blank.

        Returns:
            str | None: Validated App identifier.
        """
        if value is not None and not value.strip():
            raise ValueError("app must not be blank")
        return value

    @model_validator(mode="after")
    def _dynamic_initializer(self) -> "BenchmarkTask":
        """Require materializers for dynamic tasks.

        Args:
            None.

        Raises:
            ValueError: A dynamic task has no initializer.

        Returns:
            BenchmarkTask: Validated task.
        """
        if self.type == "dynamic" and not self.task_initializer:
            raise ValueError("dynamic task requires at least one task_initializer")
        return self

    def canonical_dict(self) -> dict[str, Any]:
        """Return the complete JSON-compatible task semantics.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: Canonical task mapping.
        """
        value = self.model_dump(mode="json", exclude_none=True)
        if not value.get("cleanup_initializer"):
            value.pop("cleanup_initializer", None)
        return value


class BenchmarkSuite(RootModel[list[BenchmarkTask]]):
    root: list[BenchmarkTask] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_ids(self) -> "BenchmarkSuite":
        seen: dict[str, int] = {}
        duplicates: list[str] = []
        for index, task in enumerate(self.root):
            if task.id in seen:
                duplicates.append(f"{task.id!r} at indexes {seen[task.id]} and {index}")
            else:
                seen[task.id] = index
        if duplicates:
            raise ValueError("duplicate task ids: " + ", ".join(duplicates))
        return self

    def canonical_list(self) -> list[dict[str, Any]]:
        return [task.canonical_dict() for task in self.root]
