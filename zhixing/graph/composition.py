"""Explicit content-addressed catalogs for reusable AgentGraph subgraphs."""

from __future__ import annotations

from types import MappingProxyType
from typing import Iterable

from .models import AgentGraph, SubgraphReference


class GraphCatalog:
    """Immutable explicit graph catalog with semantic-hash verification."""

    def __init__(self, entries: Iterable[tuple[str, str, AgentGraph]] = ()) -> None:
        """Create a catalog without reading paths or scanning packages.

        Args:
            entries (Iterable[tuple[str, str, AgentGraph]]): Graph ID, fixed
                version, and graph triples.

        Raises:
            ValueError: An entry uses ``latest`` or conflicts with another entry.

        Returns:
            None.
        """
        resolved: dict[tuple[str, str], AgentGraph] = {}
        for graph_id, version, graph in entries:
            if not graph_id.strip() or not version.strip() or version.lower() == "latest":
                raise ValueError("graph catalog entries require fixed id and version")
            key = (graph_id, version)
            previous = resolved.get(key)
            if previous is not None and previous.canonical_hash() != graph.canonical_hash():
                raise ValueError(f"conflicting graph catalog entry {graph_id}@{version}")
            resolved[key] = graph
        self._entries = MappingProxyType(resolved)

    def resolve(self, reference: SubgraphReference) -> AgentGraph | None:
        """Resolve and verify one content-addressed reference.

        Args:
            reference (SubgraphReference): Exact graph ID, version, and hash.

        Raises:
            ValueError: The catalog graph does not match the pinned semantic hash.

        Returns:
            AgentGraph | None: Matching graph, when registered.
        """
        graph = self._entries.get((reference.id, reference.version))
        if graph is None:
            return None
        actual = graph.canonical_hash()
        if actual != reference.semantic_hash:
            raise ValueError(
                f"graph catalog hash mismatch for {reference.id}@{reference.version}"
            )
        return graph
