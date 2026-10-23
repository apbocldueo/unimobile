"""Canonical file loaders: Agent is YAML; Benchmark is JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

import yaml
from pydantic import ValidationError

from .agent import AgentConfig
from .benchmark import BenchmarkSuite
from .diagnostics import ContractValidationError, ValidationIssue, raise_for_errors
from .semantic import validate_agent_semantics, validate_benchmark_semantics


def _convert_pydantic_error(exc: ValidationError, code: str) -> ContractValidationError:
    issues = [
        ValidationIssue(
            code=code,
            path=tuple(error["loc"]),
            message=error["msg"],
        )
        for error in exc.errors(include_url=False)
    ]
    return ContractValidationError(issues)


def parse_agent_config(data: Mapping[str, Any]) -> AgentConfig:
    try:
        config = AgentConfig.model_validate(data)
    except ValidationError as exc:
        raise _convert_pydantic_error(exc, "agent.structure.invalid") from exc
    raise_for_errors(validate_agent_semantics(config))
    return config


def parse_benchmark_suite(data: Sequence[Any]) -> BenchmarkSuite:
    try:
        suite = BenchmarkSuite.model_validate(data)
    except ValidationError as exc:
        raise _convert_pydantic_error(exc, "benchmark.structure.invalid") from exc
    raise_for_errors(validate_benchmark_semantics(suite))
    return suite


def load_agent_yaml(path: str | Path) -> AgentConfig:
    source = Path(path)
    if source.suffix.lower() not in {".yaml", ".yml"}:
        raise ContractValidationError(
            [ValidationIssue("agent.format.invalid", (), "Agent configuration must be YAML")]
        )
    with source.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ContractValidationError(
            [ValidationIssue("agent.root.invalid", (), "Agent YAML root must be an object")]
        )
    return parse_agent_config(data)


def load_benchmark_json(path: str | Path) -> BenchmarkSuite:
    source = Path(path)
    if source.suffix.lower() != ".json":
        raise ContractValidationError(
            [ValidationIssue("benchmark.format.invalid", (), "Benchmark configuration must be JSON")]
        )
    with source.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list):
        raise ContractValidationError(
            [ValidationIssue("benchmark.root.invalid", (), "Benchmark JSON root must be an array")]
        )
    return parse_benchmark_suite(data)
