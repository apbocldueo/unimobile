"""Runtime-only Benchmark component resolution boundary."""

from __future__ import annotations

import random
import threading
from random import Random
from typing import Any, Mapping, Protocol

from zhixing.config.contracts.common import PluginReference
from zhixing.core.factory import PluginRegistry

_LEGACY_RANDOM_LOCK = threading.RLock()


class BenchmarkComponentResolver(Protocol):
    """Explicit runtime boundary for Benchmark infrastructure components."""

    def generate_task_value(
        self,
        reference: PluginReference,
        params: Mapping[str, Any],
        *,
        rng: Random,
    ) -> tuple[Any, tuple[str, ...]]:
        """Generate one task parameter."""
        ...

    def resolve_environment(self, call: Mapping[str, Any]) -> type[Any]:
        """Resolve one environment operation class."""
        ...

    def resolve_evaluator(self, config: Mapping[str, Any]) -> type[Any]:
        """Resolve one leaf evaluator class."""
        ...


class RegistryBenchmarkComponentResolver:
    """Default compatibility resolver backed by the existing PluginRegistry."""

    def __init__(self, *, autodiscover: bool = True) -> None:
        """Create the resolver and optionally load built-in Benchmark plugins.

        Args:
            autodiscover (bool): Whether to import built-in plugin modules.

        Raises:
            RuntimeError: Built-in discovery reports import failures.

        Returns:
            None.
        """
        if autodiscover:
            # Discovery remains best-effort for optional plugin dependencies;
            # exact logical resolution below is still fail-fast.
            PluginRegistry.autodiscover("zhixing.plugins")

    def generate_task_value(
        self,
        reference: PluginReference,
        params: Mapping[str, Any],
        *,
        rng: Random,
    ) -> tuple[Any, tuple[str, ...]]:
        """Invoke one initializer with deterministic legacy random isolation.

        Args:
            reference (PluginReference): Logical initializer reference.
            params (Mapping[str, Any]): Rendered plugin parameters.
            rng (Random): Run-local deterministic generator.

        Raises:
            ValueError: The initializer cannot be resolved.
            RuntimeError: The initializer fails.

        Returns:
            tuple[Any, tuple[str, ...]]: Generated value and reproducibility notes.
        """
        namespace = str(getattr(reference, "namespace", "") or "benchmark.task")
        plugin_class = PluginRegistry.get_plugin(namespace, reference.name)
        plugin = plugin_class()
        generate_with_rng = getattr(plugin, "generate_with_rng", None)
        if callable(generate_with_rng):
            return generate_with_rng(dict(params), rng), ()
        invoke = getattr(plugin, "invoke", None)
        if callable(invoke):
            value = invoke(dict(params), {"rng": rng})
            return value, ()
        generate = getattr(plugin, "generate", None)
        if not callable(generate):
            raise TypeError(
                f"Benchmark task plugin {namespace}:{reference.name} has no generator"
            )
        # Legacy generators mutate the module-global RNG. Isolate that state
        # under a lock so parallel or unrelated calls cannot observe it.
        with _LEGACY_RANDOM_LOCK:
            previous = random.getstate()
            random.setstate(rng.getstate())
            try:
                value = generate(dict(params))
                rng.setstate(random.getstate())
            finally:
                random.setstate(previous)
        notes = ["benchmark.materialization.legacy_random_adapter"]
        if reference.name in {"date_relative", "calendar_timestamp"}:
            notes.append("benchmark.materialization.wall_clock_dependency")
        return value, tuple(notes)

    def resolve_environment(self, call: Mapping[str, Any]) -> type[Any]:
        """Resolve an environment class with exact legacy routing semantics.

        Args:
            call (Mapping[str, Any]): Canonical environment call.

        Raises:
            ValueError: Plugin is absent or routing is ambiguous.

        Returns:
            type[Any]: Environment operation class.
        """
        return PluginRegistry.resolve_benchmark_env_plugin(dict(call))

    def resolve_evaluator(self, config: Mapping[str, Any]) -> type[Any]:
        """Resolve one leaf evaluator by explicit namespace and method.

        Args:
            config (Mapping[str, Any]): Canonical leaf evaluator definition.

        Raises:
            ValueError: Definition or plugin is invalid.

        Returns:
            type[Any]: Evaluator class.
        """
        name = str(config.get("name", "")).strip()
        params = config.get("params")
        if not name or not isinstance(params, Mapping):
            raise ValueError("leaf evaluator requires name and params")
        method = str(params.get("method", "")).strip()
        if not method:
            raise ValueError("leaf evaluator requires params.method")
        return PluginRegistry.get_plugin(f"evaluator.{name}", method)


__all__ = ["BenchmarkComponentResolver", "RegistryBenchmarkComponentResolver"]
