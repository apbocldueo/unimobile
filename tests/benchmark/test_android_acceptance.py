"""Definition-level tests for real-Android Benchmark acceptance fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

from examples.external_component_plugin.src.zhixing_example_components.provider import (
    bundle,
)
from examples.sdk.android_content_verified_agent import (
    build_android_content_verified_agent,
    build_external_augmented_android_agent,
)
from scripts.run_android_benchmark_acceptance import (
    EXTERNAL_PACKAGE_ROOT,
    SCENARIOS,
    _control_agent,
    _external_yaml_compilation,
    _verified_agent_from_graph,
    _verified_sdk_agent,
    _verified_yaml_agent,
)
from tests.sdk.test_executable_agent import FakeAndroidDevice
from zhixing import AgentRunConfig, compile_agent
from zhixing.benchmark import (
    BenchmarkValidationLevel,
    compile_benchmark_package,
)
from zhixing.catalog import (
    ComponentCatalog,
    DiscoveredComponentEnvironment,
    DiscoveryReport,
    empty_component_environment,
)
from zhixing.components import RunStatus
from zhixing.runtime import GraphBindingError


def _external_environment() -> DiscoveredComponentEnvironment:
    """Build an explicit provider environment without installed discovery.

    Returns:
        DiscoveredComponentEnvironment: Environment containing the example
        task-aware audit component.
    """
    return DiscoveredComponentEnvironment(
        catalog=ComponentCatalog((("zhixing-example", bundle),)),
        report=DiscoveryReport(
            (),
            ("zhixing-example",),
            (),
            ("zhixing-example",),
            (),
        ),
    )


def test_builtin_yaml_sdk_parity_and_control_identity() -> None:
    """Keep authoring parity separate from distinct Agent comparison.

    Raises:
        AssertionError: Equivalent definitions drift or control identity collides.

    Returns:
        None.
    """
    sdk = _verified_sdk_agent(x=540, y=2052)
    yaml_agent = _verified_yaml_agent(x=540, y=2052)
    control = _control_agent()
    assert sdk.canonical_hash == yaml_agent.canonical_hash
    assert control.canonical_hash != sdk.canonical_hash


def test_external_yaml_extension_matches_sdk_graph() -> None:
    """Compile SDK and YAML-composed external graphs to one identity.

    Raises:
        AssertionError: External authoring surfaces have different semantics.

    Returns:
        None.
    """
    environment = _external_environment()
    sdk = compile_agent(
        build_external_augmented_android_agent(max_steps=10),
        component_environment=environment,
        dependencies={"llm": object()},
    )
    yaml_agent = compile_agent(
        _external_yaml_compilation(environment),
        component_environment=environment,
        dependencies={"llm": object()},
    )
    assert sdk.canonical_hash == yaml_agent.canonical_hash


def test_external_graph_fails_preflight_without_provider() -> None:
    """Reject the external component before any device selection.

    Raises:
        AssertionError: Missing provider silently falls back to a built-in.

    Returns:
        None.
    """
    with pytest.raises(GraphBindingError) as caught:
        compile_agent(
            build_external_augmented_android_agent(max_steps=10),
            component_environment=empty_component_environment(),
            dependencies={"llm": object()},
        )
    assert caught.value.info.phase == "validation"


@pytest.mark.fake_device_integration
def test_external_graph_executes_with_run_scoped_context_on_fake_device(
    tmp_path: Path,
) -> None:
    """Execute the installed-contract branch without a real Android device.

    Args:
        tmp_path (Path): Isolated runtime artifact root.

    Raises:
        AssertionError: External events, run identity, or safe output drift.

    Returns:
        None.
    """
    device = FakeAndroidDevice(
        content_outputs=[
            "Row: 0 _id=7",
            "Row: 0 _id=7",
            "Row: 0 _id=7\nRow: 1 _id=8",
        ]
    )
    agent = _verified_agent_from_graph(
        build_external_augmented_android_agent(max_steps=10),
        x=50,
        y=150,
        environment=_external_environment(),
    )
    result = agent.run(
        "create one media item",
        AgentRunConfig(
            artifact_root=tmp_path,
            max_steps=5,
            metadata={
                "android_content_baselines": {
                    "target_content": ["7"],
                }
            },
        ),
        device=device,
    )
    assert result.status is RunStatus.SUCCESS
    external_events = [
        event
        for event in result.events
        if event.node_id == "external_audit"
    ]
    assert [event.kind for event in external_events] == ["start", "complete"]
    assert all(event.run_id == result.run_id for event in external_events)
    assert external_events[-1].payload == {
        "outputs": {
            "keys": ["result"],
            "type": "dict",
        }
    }


def test_external_photo_package_compiles_from_explicit_directory() -> None:
    """Validate the resource-only external Package without a device.

    Raises:
        AssertionError: Package, task, or Protocol compilation fails.

    Returns:
        None.
    """
    result = compile_benchmark_package(
        EXTERNAL_PACKAGE_ROOT,
        split="test",
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    assert result.plan is not None
    assert result.protocol is not None
    assert result.plan.tasks[0].id == "PhotoSmoke_1"


def test_acceptance_scenarios_and_paths_are_backend_only() -> None:
    """Keep the declared matrix explicit and outside Studio.

    Raises:
        AssertionError: A required scenario or Package resource is absent.

    Returns:
        None.
    """
    assert set(SCENARIOS) == {
        "builtin-sdk-pass",
        "builtin-yaml-pass",
        "controlled-fail",
        "paired-comparison",
        "external-component",
        "external-package",
    }
    assert Path(EXTERNAL_PACKAGE_ROOT, "benchmark.yaml").is_file()
    assert build_android_content_verified_agent(max_steps=10).profile == "mobile_agent"
