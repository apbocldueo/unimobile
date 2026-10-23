"""Plugin-owned Contract Test Kit checks using only public ZhiXing APIs."""

from __future__ import annotations

import json
from dataclasses import replace

from zhixing.components import (
    RuntimeContext,
    TaskInput,
    assert_component_bundle,
    assert_component_contract,
    check_component_contract,
)
from zhixing_example_components import (
    RUN_LABELER,
    TASK_RUN_LABELER,
    RunLabeler,
    bundle,
)


class _WrongRunLabeler(RunLabeler):
    """Example implementation that violates its declared runtime output type."""

    def invoke(self, input: str, runtime: RuntimeContext) -> str:
        """Return an invalid value while preserving the formal annotation.

        Args:
            input (str): Contract invocation fixture.
            runtime (RuntimeContext): Isolated test runtime.

        Raises:
            None.

        Returns:
            str: Declared type; the fixture intentionally returns an integer.
        """
        del input, runtime
        return 42  # type: ignore[return-value]


def test_component_contract() -> None:
    """Validate the component with explicit safe invocation fixtures.

    Args:
        None.

    Raises:
        AssertionError: The example component violates its public Contract.

    Returns:
        None.
    """
    result = assert_component_contract(
        RUN_LABELER,
        input_value="hello",
        runtime=RuntimeContext(run_id="plugin-component-test"),
    )
    assert "invocation" in result.checks


def test_bundle_contract() -> None:
    """Validate the provider Bundle through the aggregate public API.

    Args:
        None.

    Raises:
        AssertionError: Bundle aggregation or component behavior is invalid.

    Returns:
        None.
    """
    result = assert_component_bundle(
        bundle,
        provider_id="zhixing-example",
        fixtures={
            RUN_LABELER.identifier: {
                "input_value": "hello",
                "runtime": RuntimeContext(run_id="plugin-bundle-test"),
            },
            TASK_RUN_LABELER.identifier: {
                "input_value": TaskInput("Take one photo."),
                "runtime": RuntimeContext(run_id="plugin-bundle-test"),
            },
        },
    )
    assert all(component.passed for component in result.components)


def test_contract_failure_is_structured_and_redacted() -> None:
    """Expose a safe diagnostic when an implementation breaks its declaration.

    Args:
        None.

    Raises:
        AssertionError: The Contract Test Kit misses the output mismatch or
            serializes the invocation fixture.

    Returns:
        None.
    """
    invalid_specification = replace(
        RUN_LABELER,
        implementation=_WrongRunLabeler,
    )
    result = check_component_contract(
        invalid_specification,
        input_value="https://user:fixture-token@example.test/private",
        runtime=RuntimeContext(run_id="plugin-negative-test"),
    )
    encoded = json.dumps(result.to_safe_dict(), sort_keys=True)
    assert not result.passed
    assert result.diagnostics[0].phase == "invocation"
    assert result.diagnostics[0].code == "component.invocation_output_mismatch"
    assert "fixture-token" not in encoded
    assert "example.test" not in encoded
