"""Stable structured diagnostics shared by all contract validation levels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Literal


PathPart = str | int
Severity = Literal["error", "warning"]


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    path: tuple[PathPart, ...]
    message: str
    severity: Severity = "error"
    task_id: str | None = None

    @property
    def dotted_path(self) -> str:
        out = ""
        for part in self.path:
            if isinstance(part, int):
                out += f"[{part}]"
            else:
                out += ("." if out else "") + part
        return out or "<root>"

    def as_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "code": self.code,
            "path": list(self.path),
            "message": self.message,
            "severity": self.severity,
        }
        if self.task_id is not None:
            payload["task_id"] = self.task_id
        return payload


class ContractValidationError(ValueError):
    def __init__(self, issues: Iterable[ValidationIssue]):
        self.issues = tuple(issues)
        rendered = "; ".join(
            f"{issue.dotted_path}: {issue.message}" for issue in self.issues
        )
        super().__init__(rendered or "configuration validation failed")


def raise_for_errors(issues: Iterable[ValidationIssue]) -> tuple[ValidationIssue, ...]:
    collected = tuple(issues)
    errors = tuple(issue for issue in collected if issue.severity == "error")
    if errors:
        raise ContractValidationError(errors)
    return collected
