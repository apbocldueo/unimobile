"""Pure reference traversal shared by Benchmark compilation and migration."""

from __future__ import annotations

from typing import Any, Iterable, Mapping


def collect_task_plugin_ids(tasks: Iterable[Mapping[str, Any]]) -> set[str]:
    """Collect explicit initializer, lifecycle, and evaluator plugin IDs.

    Args:
        tasks: Parsed BenchmarkTask-like mappings in source order.

    Raises:
        None.

    Returns:
        The distinct logical plugin IDs explicitly referenced by the tasks.
    """
    found: set[str] = set()

    def visit_evaluator(node: Mapping[str, Any]) -> None:
        """Visit one evaluator node without resolving its implementation.

        Args:
            node: Parsed evaluator mapping.

        Raises:
            None.

        Returns:
            None.
        """
        if node.get("name") == "composite":
            params = node.get("params")
            rules = params.get("rules", ()) if isinstance(params, Mapping) else ()
            if isinstance(rules, (list, tuple)):
                for rule in rules:
                    if isinstance(rule, Mapping):
                        visit_evaluator(rule)
            return
        params = node.get("params")
        method = params.get("method") if isinstance(params, Mapping) else None
        if isinstance(method, str):
            found.add(method)

    for task in tasks:
        initializers = task.get("task_initializer")
        if isinstance(initializers, Mapping):
            for reference in initializers.values():
                name = (
                    reference.get("name")
                    if isinstance(reference, Mapping)
                    else None
                )
                if isinstance(name, str):
                    found.add(name)
        for field_name in ("environment_initializer", "cleanup_initializer"):
            references = task.get(field_name)
            if not isinstance(references, (list, tuple)):
                continue
            for reference in references:
                name = (
                    reference.get("name")
                    if isinstance(reference, Mapping)
                    else None
                )
                if isinstance(name, str):
                    found.add(name)
        evaluator = task.get("evaluator")
        if isinstance(evaluator, Mapping):
            visit_evaluator(evaluator)
    return found


__all__ = ["collect_task_plugin_ids"]
