"""Benchmark environment lifecycle ownership boundary."""

from __future__ import annotations

from typing import Any, Mapping

from .resolver import BenchmarkComponentResolver
from .resources import BenchmarkResourceProvider


def infer_environment_phase(
    call: Mapping[str, Any],
    plugin_class: type[Any],
) -> tuple[str, str | None]:
    """Resolve reset/setup phase without fuzzy plugin-name guessing.

    Args:
        call (Mapping[str, Any]): Canonical call.
        plugin_class (type[Any]): Uniquely resolved plugin implementation.

    Raises:
        ValueError: Resolved namespace cannot establish a unique phase.

    Returns:
        tuple[str, str | None]: Phase and optional compatibility warning.
    """
    explicit = call.get("phase")
    if explicit in {"reset", "setup"}:
        return str(explicit), None
    namespace = str(getattr(plugin_class, "__plugin_namespace__", ""))
    if namespace == "benchmark.environment.reset" or namespace.startswith(
        "benchmark.environment.reset."
    ):
        return "reset", "benchmark.environment.phase_inferred"
    if namespace == "benchmark.environment" or namespace.startswith(
        "benchmark.environment."
    ):
        return "setup", "benchmark.environment.phase_inferred"
    raise ValueError("resolved environment namespace does not identify reset or setup")


def execute_environment_calls(
    calls: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    *,
    requested_phase: str,
    resolver: BenchmarkComponentResolver,
    resource_provider: BenchmarkResourceProvider,
    device: Any,
) -> tuple[dict[str, Any], ...]:
    """Execute all calls for one phase after resolving every class first.

    Args:
        calls: Ordered canonical environment calls.
        requested_phase (str): Reset, setup, or cleanup.
        resolver (BenchmarkComponentResolver): Component resolution boundary.
        resource_provider (BenchmarkResourceProvider): Logical resource provider.
        device (Any): Shared explicit device session.

    Raises:
        ValueError: Routing is ambiguous.
        RuntimeError: A plugin reports failure.

    Returns:
        tuple[dict[str, Any], ...]: Safe per-call evidence.
    """
    resolved: list[tuple[Mapping[str, Any], type[Any], str, str | None]] = []
    for call in calls:
        plugin_class = resolver.resolve_environment(call)
        if requested_phase == "cleanup":
            phase, warning = "cleanup", None
        else:
            phase, warning = infer_environment_phase(call, plugin_class)
        resolved.append((call, plugin_class, phase, warning))
    evidence: list[dict[str, Any]] = []
    for call, plugin_class, phase, warning in resolved:
        if phase != requested_phase:
            continue
        params = resource_provider.bind(dict(call.get("params") or {}))
        meta = dict(call.get("meta") or {})
        meta["device"] = device
        ok = plugin_class().execute(meta=meta, params=params)
        if not ok:
            raise RuntimeError(
                f"Benchmark environment plugin {call.get('name', '')!r} failed"
            )
        item = {
            "plugin_id": str(call.get("name", "")),
            "namespace": str(
                getattr(plugin_class, "__plugin_namespace__", "")
            ),
            "phase": phase,
            "verified": bool(ok),
        }
        if warning:
            item["warning"] = warning
        evidence.append(item)
    return tuple(evidence)


__all__ = ["execute_environment_calls", "infer_environment_phase"]
