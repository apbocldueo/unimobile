"""Bounded, structured diagnostics for Benchmark definition operations."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import ConfigDict, BaseModel


class BenchmarkDiagnosticSeverity(str, Enum):
    """Severity values exposed by Benchmark validation APIs."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class BenchmarkDiagnostic(BaseModel):
    """One safe and machine-readable Benchmark diagnostic."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: str
    message: str
    severity: BenchmarkDiagnosticSeverity = BenchmarkDiagnosticSeverity.ERROR
    source: str = ""
    path: tuple[str | int, ...] = ()
    task_id: str | None = None

    def sort_key(self) -> tuple[Any, ...]:
        """Return the deterministic diagnostic ordering key.

        Args:
            None.

        Raises:
            None.

        Returns:
            tuple[Any, ...]: Stable ordering fields.
        """
        return (
            self.severity.value,
            self.code,
            self.source,
            tuple(str(item) for item in self.path),
            self.task_id or "",
            self.message,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize bounded public diagnostic fields.

        Args:
            None.

        Raises:
            None.

        Returns:
            dict[str, Any]: JSON-compatible diagnostic.
        """
        return self.model_dump(mode="json", exclude_none=True)


class BenchmarkValidationResult(BaseModel):
    """Aggregate all independently detectable Benchmark diagnostics."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    diagnostics: tuple[BenchmarkDiagnostic, ...] = ()

    @property
    def errors(self) -> tuple[BenchmarkDiagnostic, ...]:
        """Return error-level diagnostics.

        Returns:
            tuple[BenchmarkDiagnostic, ...]: Validation errors.
        """
        return tuple(
            item
            for item in self.diagnostics
            if item.severity is BenchmarkDiagnosticSeverity.ERROR
        )

    @property
    def warnings(self) -> tuple[BenchmarkDiagnostic, ...]:
        """Return warning-level diagnostics.

        Returns:
            tuple[BenchmarkDiagnostic, ...]: Validation warnings.
        """
        return tuple(
            item
            for item in self.diagnostics
            if item.severity is BenchmarkDiagnosticSeverity.WARNING
        )

    @property
    def is_valid(self) -> bool:
        """Report whether no error-level diagnostics exist.

        Returns:
            bool: ``True`` when the validated definition is usable.
        """
        return not self.errors

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the validation result without unsafe implementation data.

        Returns:
            dict[str, Any]: Stable validation summary.
        """
        return {
            "is_valid": self.is_valid,
            "errors": [item.to_safe_dict() for item in self.errors],
            "warnings": [item.to_safe_dict() for item in self.warnings],
        }


class BenchmarkDefinitionError(ValueError):
    """A Benchmark definition could not be parsed, resolved, or compiled."""

    def __init__(self, diagnostics: tuple[BenchmarkDiagnostic, ...]) -> None:
        """Create an error from already-sanitized diagnostics.

        Args:
            diagnostics (tuple[BenchmarkDiagnostic, ...]): Safe failures.

        Raises:
            ValueError: Diagnostics is empty.

        Returns:
            None: Initializes the exception.
        """
        if not diagnostics:
            raise ValueError("BenchmarkDefinitionError requires diagnostics")
        ordered = tuple(sorted(diagnostics, key=lambda item: item.sort_key()))
        self.diagnostics = ordered
        preview = "; ".join(
            f"{item.code} at {'.'.join(map(str, item.path)) or '<root>'}"
            for item in ordered[:8]
        )
        super().__init__(preview)

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize the error without arbitrary exception text.

        Returns:
            dict[str, Any]: Stable public error payload.
        """
        return {
            "code": "benchmark.definition_invalid",
            "message": "Benchmark definition validation failed.",
            "diagnostics": [item.to_safe_dict() for item in self.diagnostics],
        }


def sorted_diagnostics(
    diagnostics: list[BenchmarkDiagnostic] | tuple[BenchmarkDiagnostic, ...],
) -> tuple[BenchmarkDiagnostic, ...]:
    """Sort diagnostics deterministically.

    Args:
        diagnostics (list[BenchmarkDiagnostic] | tuple[BenchmarkDiagnostic, ...]):
            Diagnostics to order.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Deterministically ordered diagnostics.
    """
    return tuple(sorted(diagnostics, key=lambda item: item.sort_key()))

