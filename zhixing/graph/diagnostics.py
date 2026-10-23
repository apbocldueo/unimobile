"""Safe diagnostics and compilation results for AgentGraph tooling."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from .enums import DiagnosticSeverity
from .models import AgentGraph, GraphModel


class GraphDiagnostic(GraphModel):
    code: str
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    path: tuple[str | int, ...] = ()
    node_id: str | None = None
    edge_index: int | None = None
    port_id: str | None = None
    source_id: str | None = None

    def sort_key(self) -> tuple[Any, ...]:
        return (
            self.severity.value,
            self.code,
            tuple(str(item) for item in self.path),
            self.node_id or "",
            self.edge_index if self.edge_index is not None else -1,
            self.port_id or "",
            self.source_id or "",
            self.message,
        )

    def to_safe_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class GraphValidationResult(GraphModel):
    diagnostics: tuple[GraphDiagnostic, ...] = ()

    @property
    def errors(self) -> tuple[GraphDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == DiagnosticSeverity.ERROR)

    @property
    def warnings(self) -> tuple[GraphDiagnostic, ...]:
        return tuple(item for item in self.diagnostics if item.severity == DiagnosticSeverity.WARNING)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "errors": [item.to_safe_dict() for item in self.errors],
            "warnings": [item.to_safe_dict() for item in self.warnings],
        }


class SourceMapEntry(GraphModel):
    """Map one authoring source location to a compiled graph object."""

    source_id: str
    graph_kind: str
    graph_id: str
    document_id: str | None = None
    canvas_path: tuple[str, ...] = ()
    canvas_node_id: str | None = None
    canvas_edge_id: str | None = None
    logical_node_path: tuple[str, ...] = ()
    contract_port_id: str | None = None
    property_path: tuple[str | int, ...] = ()


class CompilationResult(GraphModel):
    graph: AgentGraph | None = None
    diagnostics: tuple[GraphDiagnostic, ...] = ()
    source_map: tuple[SourceMapEntry, ...] = ()

    @property
    def is_success(self) -> bool:
        return self.graph is not None and not any(
            item.severity == DiagnosticSeverity.ERROR for item in self.diagnostics
        )

    def to_safe_dict(self) -> dict[str, Any]:
        return {
            "is_success": self.is_success,
            "graph": self.graph.model_dump(mode="json", exclude_none=True) if self.graph else None,
            "diagnostics": [item.to_safe_dict() for item in self.diagnostics],
            "source_map": [item.model_dump(mode="json") for item in self.source_map],
        }


def sorted_diagnostics(items: list[GraphDiagnostic]) -> tuple[GraphDiagnostic, ...]:
    return tuple(sorted(items, key=lambda item: item.sort_key()))
