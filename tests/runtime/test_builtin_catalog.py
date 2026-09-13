"""Tests for deterministic built-in component discovery and binding."""

from __future__ import annotations

import pytest

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionType,
    DeviceObservation,
    RuntimeContext,
)
from zhixing.graph import GraphComponentRef, GraphRole
from zhixing.core.factory import PluginRegistry
from zhixing.catalog import (
    BUILTIN_COMPONENT_CATALOG,
    BuiltInComponentCatalog,
    BuiltInComponentResolver,
    BuiltInComponentSpec,
    BuiltInComponentUnavailableError,
)
from zhixing.runtime.transforms import ActionRequestAssembler, RuntimeServiceMarker


class FakeLLM:
    """Provide the legacy generate method expected by UniversalReason."""

    def generate(self, prompt: str, images: list[str] | None = None) -> str:
        """Return a deterministic terminal action.

        Args:
            prompt (str): Rendered reasoning prompt.
            images (list[str] | None): Optional screenshot paths.

        Raises:
            None.

        Returns:
            str: Valid JSON action understood by the built-in parser.
        """
        del prompt, images
        return '{"action": "DONE", "params": {}, "thought": "complete"}'


@PluginRegistry.register(namespace="test.secret", name="echo")
class SecretEcho:
    """Capture a resolved constructor secret for a boundary test."""

    def __init__(self, api_key: str) -> None:
        """Store the received runtime-only value.

        Args:
            api_key (str): Resolved test secret.

        Raises:
            None.

        Returns:
            None.
        """
        self.api_key = api_key


def test_catalog_lists_supported_components_without_global_discovery() -> None:
    """Expose a stable catalog and import only selected entries.

    Args:
        None.

    Raises:
        AssertionError: Required entries or selected classes are absent.

    Returns:
        None.
    """
    identifiers = {entry.identifier for entry in BUILTIN_COMPONENT_CATALOG.entries()}
    assert {
        "agent.perception:screenshot_perception",
        "agent.reasoning:universal_reasoning",
        "agent.memory:sliding_window_memory",
        "zhixing.runtime:device_observe",
        "zhixing.runtime:action_executor",
        "zhixing.control:action_request",
    } <= identifiers
    assert (
        BUILTIN_COMPONENT_CATALOG.ensure(
            "agent.perception",
            "screenshot_perception",
        ).__name__
        == "ScreenshotPerception"
    )


def test_catalog_distinguishes_unknown_and_missing_optional_dependency() -> None:
    """Return actionable and distinct catalog availability failures.

    Args:
        None.

    Raises:
        AssertionError: Unknown and optional-dependency failures are conflated.

    Returns:
        None.
    """
    unknown = BUILTIN_COMPONENT_CATALOG.availability("agent.perception", "missing")
    catalog = BuiltInComponentCatalog(
        (
            BuiltInComponentSpec(
                "agent.perception",
                "optional",
                "zhixing.plugins.agent.perception.screenshot",
                extra="vision",
                required_modules=("package_that_cannot_exist_zhixing",),
            ),
        )
    )
    optional = catalog.availability("agent.perception", "optional")
    assert unknown.error_type == "unknown_component"
    assert optional.error_type == "BuiltInComponentUnavailableError"
    with pytest.raises(BuiltInComponentUnavailableError, match=r"zhixing\[vision\]"):
        catalog.ensure("agent.perception", "optional")


def test_resolver_injects_nested_llm_and_runtime_service_markers() -> None:
    """Instantiate built-ins with a run-time dependency provider.

    Args:
        None.

    Raises:
        AssertionError: Nested dependency or marker resolution fails.

    Returns:
        None.
    """
    resolver = BuiltInComponentResolver(dependency_provider={"llm": FakeLLM()})
    reason = resolver.resolve(
        GraphComponentRef(
            namespace="agent.reasoning",
            name="universal_reasoning",
            params={"preset": "general_vlm_type"},
            dependencies={
                "llm": {
                    "namespace": "llm",
                    "name": "openai_llm",
                    "params": {
                        "api_key": {"secret_ref": "unused_due_to_provider"},
                    },
                }
            },
        ),
        GraphRole.REASONING,
    )
    marker = resolver.resolve(
        GraphComponentRef(
            namespace="zhixing.runtime",
            name="device_observe",
        ),
        None,
    )
    assert reason.llm is not None
    assert isinstance(marker, RuntimeServiceMarker)


def test_resolver_resolves_secret_mapping_without_mutating_reference() -> None:
    """Resolve nested secret mappings only at construction time.

    Args:
        None.

    Raises:
        AssertionError: Secret is lost or written back to graph data.

    Returns:
        None.
    """
    reference = GraphComponentRef(
        namespace="test.secret",
        name="echo",
        params={
            "api_key": {"secret_ref": "openai_api_key"},
        },
    )
    resolver = BuiltInComponentResolver(
        catalog=BuiltInComponentCatalog(
            (
                BuiltInComponentSpec(
                    "test.secret",
                    "echo",
                    "zhixing.runtime.transforms",
                ),
            )
        ),
        secret_provider={"openai_api_key": "runtime-only-value"},
    )
    instance = resolver.resolve(reference, None)
    assert instance.api_key == "runtime-only-value"
    assert reference.params["api_key"] == {"secret_ref": "openai_api_key"}


def test_action_request_assembler_preserves_typed_action_and_observation() -> None:
    """Build the request consumed by the Android action service.

    Args:
        None.

    Raises:
        AssertionError: Typed values are dropped or changed.

    Returns:
        None.
    """
    action = Action(ActionType.KEY, {"code": "home"})
    observation = DeviceObservation("screen.png", 100, 200)
    result = ActionRequestAssembler().invoke(
        {"action": action, "observation": observation},
        RuntimeContext(),
    )
    assert result == ActionExecutionInput(action=action, observation=observation)


@pytest.mark.parametrize(
    ("namespace", "name", "role"),
    [
        ("agent.planner", "universal_planner", GraphRole.PLANNER),
        ("agent.verifier", "llm_reflect_verifier", GraphRole.VERIFIER),
        ("agent.grounder", "uground_grounder", None),
    ],
)
def test_resolver_binds_optional_mobile_agent_roles_with_llm_provider(
    namespace: str,
    name: str,
    role: GraphRole | None,
) -> None:
    """Bind optional built-in roles without choosing an Agent strategy.

    Args:
        namespace (str): Built-in component namespace.
        name (str): Built-in component name.
        role (GraphRole | None): Core graph role when one exists.

    Raises:
        AssertionError: Resolver cannot construct the selected built-in.

    Returns:
        None.
    """
    reference = GraphComponentRef(
        namespace=namespace,
        name=name,
        dependencies={
            "llm": {
                "namespace": "llm",
                "name": "openai_llm",
                "params": {"api_key": {"secret_ref": "provided_at_runtime"}},
            }
        },
    )
    component = BuiltInComponentResolver(
        dependency_provider={"llm": FakeLLM()},
    ).resolve(reference, role)
    assert component is not None
