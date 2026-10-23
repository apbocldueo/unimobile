"""Registry-backed validation that inspects plugin classes without instantiation."""

from __future__ import annotations

import inspect
from typing import Any, Iterable, Mapping

from zhixing.core.factory import PluginDiscoveryReport, PluginRegistry

from .agent import AgentConfig
from .benchmark import BenchmarkSuite, CompositeEvaluator, LeafEvaluator
from .diagnostics import ValidationIssue


RegistryMap = Mapping[str, Mapping[str, type[Any]]]


def _registry_map(registry: RegistryMap | None) -> RegistryMap:
    return PluginRegistry._registry if registry is None else registry


def _name_locations(registry: RegistryMap, name: str) -> list[str]:
    return sorted(namespace for namespace, plugins in registry.items() if name in plugins)


def _discovery_context(
    reports: Iterable[PluginDiscoveryReport],
    path: tuple[str | int, ...],
) -> list[ValidationIssue]:
    failures = [failure for report in reports for failure in report.failures]
    if not failures:
        return []
    preview = ", ".join(
        f"{item.module} ({item.error_type}: {item.message})" for item in failures[:3]
    )
    return [
        ValidationIssue(
            code="registry.discovery_incomplete",
            path=path,
            message=f"plugin catalog is incomplete because discovery failed: {preview}",
            severity="warning",
        )
    ]


def _resolve_exact(
    registry: RegistryMap,
    namespace: str,
    name: str,
    path: tuple[str | int, ...],
    reports: Iterable[PluginDiscoveryReport],
) -> tuple[type[Any] | None, list[ValidationIssue]]:
    plugin = registry.get(namespace, {}).get(name)
    if plugin is not None:
        return plugin, []
    locations = _name_locations(registry, name)
    if locations:
        message = f"plugin {name!r} is not registered in required namespace {namespace!r}; found in {locations}"
        code = "registry.wrong_namespace"
    else:
        message = f"plugin {name!r} is not registered in namespace {namespace!r}"
        code = "registry.unknown_plugin"
    issues = [ValidationIssue(code=code, path=path, message=message)]
    issues.extend(_discovery_context(reports, path))
    return None, issues


def _requires_llm_client(plugin_class: type[Any]) -> bool:
    signature = inspect.signature(plugin_class.__init__)
    parameter = signature.parameters.get("llm_client")
    return parameter is not None and parameter.default is inspect.Parameter.empty


def validate_agent_registry(
    config: AgentConfig,
    *,
    registry: RegistryMap | None = None,
    discovery_reports: Iterable[PluginDiscoveryReport] = (),
) -> tuple[ValidationIssue, ...]:
    reg = _registry_map(registry)
    reports = tuple(discovery_reports)
    issues: list[ValidationIssue] = []

    _, found = _resolve_exact(reg, "agent.type", config.agent_type, ("agent_type",), reports)
    issues.extend(found)
    _, found = _resolve_exact(reg, "device", config.device.name, ("device", "name"), reports)
    issues.extend(found)

    llm_refs = []
    if config.global_config.default_llm is not None:
        llm_refs.append((("global_config", "default_llm", "name"), config.global_config.default_llm))

    default_llm = config.global_config.default_llm
    for role, index, component in config.agent.components.iter_slots():
        base_path: tuple[str | int, ...] = ("agent", "components", role)
        if index is not None:
            base_path += (index,)
        plugin_class, found = _resolve_exact(
            reg, f"agent.{role}", component.name, base_path + ("name",), reports
        )
        issues.extend(found)
        if component.llm is not None:
            llm_refs.append((base_path + ("llm", "name"), component.llm))
        if plugin_class is not None:
            try:
                llm_required = _requires_llm_client(plugin_class)
            except (TypeError, ValueError) as exc:
                issues.append(
                    ValidationIssue(
                        code="registry.signature.unavailable",
                        path=base_path,
                        message=f"cannot inspect constructor for {component.name!r}: {exc}",
                    )
                )
            else:
                if llm_required and component.llm is None and default_llm is None:
                    issues.append(
                        ValidationIssue(
                            code="agent.llm.required",
                            path=base_path + ("llm",),
                            message=f"component {component.name!r} requires llm_client injection",
                        )
                    )

    seen_llms: set[tuple[str | int, ...]] = set()
    for path, llm in llm_refs:
        if path in seen_llms:
            continue
        seen_llms.add(path)
        _, found = _resolve_exact(reg, "llm", llm.name, path, reports)
        issues.extend(found)
    return tuple(issues)


def _resolve_environment(
    registry: RegistryMap,
    call,
    path: tuple[str | int, ...],
    reports: tuple[PluginDiscoveryReport, ...],
) -> list[ValidationIssue]:
    if call.namespace:
        _, issues = _resolve_exact(registry, call.namespace, call.name, path, reports)
        return issues
    if call.category:
        _, issues = _resolve_exact(
            registry, f"benchmark.environment.{call.category}", call.name, path, reports
        )
        return issues

    prefix = "benchmark.environment"
    matches = sorted(
        namespace
        for namespace, plugins in registry.items()
        if (namespace == prefix or namespace.startswith(prefix + ".")) and call.name in plugins
    )
    if len(matches) == 1:
        return []
    if len(matches) > 1:
        return [
            ValidationIssue(
                code="registry.environment.ambiguous",
                path=path,
                message=f"environment plugin {call.name!r} matches {matches}; set namespace or category",
            )
        ]
    _, issues = _resolve_exact(registry, prefix, call.name, path, reports)
    return issues


def _validate_evaluator_registry(
    node,
    registry: RegistryMap,
    path: tuple[str | int, ...],
    reports: tuple[PluginDiscoveryReport, ...],
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if isinstance(node, CompositeEvaluator):
        _, found = _resolve_exact(
            registry,
            "evaluator.composite",
            node.params.logic,
            path + ("params", "logic"),
            reports,
        )
        issues.extend(found)
        for index, child in enumerate(node.params.rules):
            issues.extend(
                _validate_evaluator_registry(
                    child, registry, path + ("params", "rules", index), reports
                )
            )
    elif isinstance(node, LeafEvaluator):
        _, found = _resolve_exact(
            registry,
            f"evaluator.{node.name}",
            node.params.method,
            path + ("params", "method"),
            reports,
        )
        issues.extend(found)
    return issues


def validate_benchmark_registry(
    suite: BenchmarkSuite,
    *,
    registry: RegistryMap | None = None,
    discovery_reports: Iterable[PluginDiscoveryReport] = (),
) -> tuple[ValidationIssue, ...]:
    reg = _registry_map(registry)
    reports = tuple(discovery_reports)
    issues: list[ValidationIssue] = []

    for task_index, task in enumerate(suite.root):
        for variable, call in task.task_initializer.items():
            _, found = _resolve_exact(
                reg,
                "benchmark.task",
                call.name,
                (task_index, "task_initializer", variable, "name"),
                reports,
            )
            issues.extend(found)
        for env_index, call in enumerate(task.environment_initializer):
            issues.extend(
                _resolve_environment(
                    reg,
                    call,
                    (task_index, "environment_initializer", env_index, "name"),
                    reports,
                )
            )
        issues.extend(
            _validate_evaluator_registry(
                task.evaluator, reg, (task_index, "evaluator"), reports
            )
        )
    return tuple(issues)
