"""Deterministic built-in component catalog shared by SDK, YAML, and Studio."""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from zhixing.components.authoring import ComponentCategory, ComponentDependencySlot
from zhixing.core.factory import PluginRegistry
from zhixing.graph import GraphComponentRef, GraphRole

from zhixing.runtime.binding import RegistryComponentResolver


_LLM_DEPENDENCY_SLOT = ComponentDependencySlot(
    name="llm",
    required=True,
    accepted_namespaces=("llm",),
    accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
    config_schema={
        "type": "object",
        "required": ["name", "params"],
        "properties": {
            "namespace": {"type": "string", "const": "llm"},
            "name": {"type": "string", "minLength": 1},
            "version": {"type": ["string", "null"]},
            "params": {"type": "object"},
        },
        "additionalProperties": False,
    },
)


@dataclass(frozen=True)
class BuiltInComponentSpec:
    """Describe one framework-owned component without importing its module."""

    namespace: str
    name: str
    module: str
    version: str = "1"
    extra: str = ""
    required_modules: tuple[str, ...] = ()
    dependency_slots: tuple[ComponentDependencySlot, ...] = ()

    def __post_init__(self) -> None:
        """Validate and freeze built-in dependency authoring metadata.

        Args:
            None.

        Raises:
            ValueError: A declaration has too many, malformed, or duplicate
                dependency slots.

        Returns:
            None.
        """
        slots = tuple(self.dependency_slots)
        if len(slots) > 32 or any(
            not isinstance(item, ComponentDependencySlot) for item in slots
        ):
            raise ValueError("built-in dependency slots are invalid")
        names = [item.name for item in slots]
        if len(names) != len(set(names)):
            raise ValueError("built-in dependency slot names must be unique")
        object.__setattr__(self, "dependency_slots", slots)

    @property
    def identifier(self) -> str:
        """Return the stable namespace/name identifier.

        Args:
            None.

        Raises:
            None.

        Returns:
            str: Stable component identifier.
        """
        return f"{self.namespace}:{self.name}"


@dataclass(frozen=True)
class BuiltInAvailability:
    """Report whether one catalog entry can be imported in this environment."""

    identifier: str
    available: bool
    extra: str = ""
    error_type: str = ""


class BuiltInComponentUnavailableError(LookupError):
    """Signal a selected built-in component or optional dependency is unavailable."""


_SPECS = (
    BuiltInComponentSpec(
        "agent.perception",
        "screenshot_perception",
        "zhixing.plugins.agent.perception.screenshot",
    ),
    BuiltInComponentSpec(
        "agent.perception",
        "coordinate_perception",
        "zhixing.plugins.agent.perception.coordinate",
    ),
    BuiltInComponentSpec(
        "agent.reasoning",
        "universal_reasoning",
        "zhixing.plugins.agent.reasoning.universal_reasoning",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.memory",
        "sliding_window_memory",
        "zhixing.plugins.agent.memory.sliding_window",
    ),
    BuiltInComponentSpec(
        "agent.memory",
        "summary_memory",
        "zhixing.plugins.agent.memory.summary_memory",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.planner",
        "universal_planner",
        "zhixing.plugins.agent.planner.universal_planner",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.verifier",
        "screen_diff_verifier",
        "zhixing.plugins.agent.verifier.screen_diff",
        extra="vision",
        required_modules=("cv2", "numpy"),
    ),
    BuiltInComponentSpec(
        "agent.verifier",
        "llm_reflect_verifier",
        "zhixing.plugins.agent.verifier.llm_reflect",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.verifier",
        "android_content_delta_verifier",
        "zhixing.plugins.agent.verifier.android_content_delta",
    ),
    BuiltInComponentSpec(
        "agent.action_executor",
        "legacy_action_executor",
        "zhixing.engine.agent.legacy_action_executor",
    ),
    BuiltInComponentSpec(
        "agent.grounder",
        "uground_grounder",
        "zhixing.plugins.agent.grounder.uground",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "llm",
        "openai_llm",
        "zhixing.plugins.llm.openai_llm",
        extra="openai",
        required_modules=("openai",),
    ),
    BuiltInComponentSpec(
        "zhixing.control",
        "action_request",
        "zhixing.runtime.transforms",
    ),
    BuiltInComponentSpec(
        "zhixing.control",
        "verification_terminal_action",
        "zhixing.runtime.transforms",
    ),
    BuiltInComponentSpec(
        "zhixing.runtime",
        "device_observe",
        "zhixing.runtime.transforms",
    ),
    BuiltInComponentSpec(
        "zhixing.runtime",
        "action_executor",
        "zhixing.runtime.transforms",
    ),
)

_PARSER_MODULES = (
    "zhixing.plugins.agent.parsers.appagent_action_parser",
    "zhixing.plugins.agent.parsers.gui_schema_action_parser",
    "zhixing.plugins.agent.parsers.guicourse_action_parser",
    "zhixing.plugins.agent.parsers.json_action_parser",
    "zhixing.plugins.agent.parsers.mobile_agent_action_parser",
    "zhixing.plugins.agent.parsers.mobile_use_tool_parser",
    "zhixing.plugins.agent.parsers.mobimind_parser",
    "zhixing.plugins.agent.parsers.os_genesis_action_parser",
    "zhixing.plugins.agent.parsers.section_parser",
    "zhixing.plugins.agent.parsers.seeact_uground_action_parser",
    "zhixing.plugins.agent.parsers.showui_action_parser",
)


class BuiltInComponentCatalog:
    """Resolve only framework-owned, explicitly listed component modules."""

    def __init__(
        self,
        specs: tuple[BuiltInComponentSpec, ...] = _SPECS,
    ) -> None:
        """Create a deterministic catalog without importing component modules.

        Args:
            specs (tuple[BuiltInComponentSpec, ...]): Explicit supported entries.

        Raises:
            ValueError: Duplicate namespace/name declarations are present.

        Returns:
            None: Initializes an immutable lookup table.
        """
        entries: dict[tuple[str, str], BuiltInComponentSpec] = {}
        for spec in specs:
            key = (spec.namespace, spec.name)
            if key in entries and entries[key] != spec:
                raise ValueError(f"conflicting built-in component {spec.identifier}")
            entries[key] = spec
        self._entries = MappingProxyType(entries)

    def get(self, namespace: str, name: str) -> BuiltInComponentSpec | None:
        """Return one declaration without importing its module.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Raises:
            None.

        Returns:
            BuiltInComponentSpec | None: Matching declaration.
        """
        return self._entries.get((namespace, name))

    def entries(self) -> tuple[BuiltInComponentSpec, ...]:
        """Return supported entries in deterministic order.

        Args:
            None.

        Raises:
            None.

        Returns:
            tuple[BuiltInComponentSpec, ...]: Sorted catalog entries.
        """
        return tuple(self._entries[key] for key in sorted(self._entries))

    def ensure(self, namespace: str, name: str) -> type[Any]:
        """Import and return one selected built-in plugin class.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Raises:
            LookupError: The component is not framework-owned.
            BuiltInComponentUnavailableError: An optional dependency or import fails.

        Returns:
            type[Any]: Registered component class.
        """
        spec = self.get(namespace, name)
        if spec is None:
            raise LookupError(f"unknown built-in component {namespace}:{name}")
        missing = tuple(
            module
            for module in spec.required_modules
            if importlib.util.find_spec(module) is None
        )
        if missing:
            hint = f"; install zhixing[{spec.extra}]" if spec.extra else ""
            raise BuiltInComponentUnavailableError(
                f"built-in component {spec.identifier} requires {', '.join(missing)}{hint}"
            )
        try:
            if namespace in {"agent.reasoning", "agent.planner"}:
                for module in _PARSER_MODULES:
                    importlib.import_module(module)
            importlib.import_module(spec.module)
            return PluginRegistry.get_plugin(namespace, name)
        except BuiltInComponentUnavailableError:
            raise
        except Exception as error:
            hint = f"; install zhixing[{spec.extra}]" if spec.extra else ""
            raise BuiltInComponentUnavailableError(
                f"built-in component {spec.identifier} is unavailable "
                f"({type(error).__name__}){hint}"
            ) from error

    def availability(self, namespace: str, name: str) -> BuiltInAvailability:
        """Inspect one selected catalog entry without leaking import messages.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Raises:
            None: Unavailable entries are returned as data.

        Returns:
            BuiltInAvailability: Structured availability result.
        """
        spec = self.get(namespace, name)
        identifier = f"{namespace}:{name}"
        if spec is None:
            return BuiltInAvailability(identifier, False, error_type="unknown_component")
        try:
            self.ensure(namespace, name)
        except Exception as error:
            return BuiltInAvailability(
                identifier,
                False,
                extra=spec.extra,
                error_type=type(error).__name__,
            )
        return BuiltInAvailability(identifier, True, extra=spec.extra)


BUILTIN_COMPONENT_CATALOG = BuiltInComponentCatalog()


class BuiltInComponentResolver(RegistryComponentResolver):
    """Instantiate selected built-ins with explicit secrets and dependencies."""

    def __init__(
        self,
        *,
        catalog: BuiltInComponentCatalog = BUILTIN_COMPONENT_CATALOG,
        secret_provider: Mapping[str, Any] | Callable[[str], Any] | None = None,
        dependency_provider: Mapping[str, Any] | None = None,
        constructor_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Configure production binding without scanning installed packages.

        Args:
            catalog (BuiltInComponentCatalog): Explicit framework catalog.
            secret_provider (Mapping[str, Any] | Callable[[str], Any] | None):
                Runtime-only SecretRef provider.
            dependency_provider (Mapping[str, Any] | None): Prebuilt dependencies.
            constructor_kwargs (Mapping[str, Any] | None): Explicit constructor defaults.

        Raises:
            None.

        Returns:
            None: Initializes the resolver.
        """
        super().__init__(
            secret_provider=secret_provider,
            dependency_provider=dependency_provider,
            constructor_kwargs=constructor_kwargs,
        )
        self.catalog = catalog

    def _dependency(self, name: str, specification: Any) -> Any:
        """Resolve nested built-in dependencies after deterministic import.

        Args:
            name (str): Constructor dependency name.
            specification (Any): Literal or nested component reference.

        Raises:
            LookupError: A nested built-in is unavailable.

        Returns:
            Any: Resolved dependency instance or literal value.
        """
        if name in self.dependency_provider:
            return super()._dependency(name, specification)
        if isinstance(specification, Mapping) and specification.get("name"):
            namespace = str(
                specification.get("namespace")
                or ("llm" if name == "llm" else f"agent.{name}")
            )
            self.catalog.ensure(namespace, str(specification["name"]))
        return super()._dependency(name, specification)

    def resolve(
        self,
        reference: GraphComponentRef,
        role: GraphRole | None = None,
    ) -> Any:
        """Instantiate one selected built-in component.

        Args:
            reference (GraphComponentRef): Declarative component reference.
            role (GraphRole | None): Expected core role, used by adapters later.

        Raises:
            LookupError: Component or dependency is unavailable.
            TypeError: Constructor parameters are incompatible.

        Returns:
            Any: New component instance.
        """
        spec = self.catalog.get(reference.namespace, reference.name)
        if spec is None:
            raise LookupError(
                f"unknown built-in component {reference.namespace}:{reference.name}"
            )
        if reference.version is not None and reference.version != spec.version:
            raise LookupError(
                f"built-in component {spec.identifier} does not provide "
                f"version {reference.version!r}"
            )
        self.catalog.ensure(reference.namespace, reference.name)
        return super().resolve(reference, role)  # type: ignore[arg-type]


def create_builtin_resolver(
    *,
    secrets: Mapping[str, Any] | Callable[[str], Any] | None = None,
    dependencies: Mapping[str, Any] | None = None,
) -> BuiltInComponentResolver:
    """Create the default framework-owned component resolver.

    Args:
        secrets (Mapping[str, Any] | Callable[[str], Any] | None): Secret provider.
        dependencies (Mapping[str, Any] | None): Prebuilt named dependencies.

    Raises:
        None.

    Returns:
        BuiltInComponentResolver: Fresh deterministic resolver.
    """
    return BuiltInComponentResolver(
        secret_provider=secrets,
        dependency_provider=dependencies,
    )


__all__ = [
    "BUILTIN_COMPONENT_CATALOG",
    "BuiltInAvailability",
    "BuiltInComponentCatalog",
    "BuiltInComponentResolver",
    "BuiltInComponentSpec",
    "BuiltInComponentUnavailableError",
    "create_builtin_resolver",
]
