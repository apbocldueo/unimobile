"""No-device example of invocation-native and legacy ZhiXing components.

This demonstrates the protocol boundary directly. A high-level AgentBuilder or
component graph executor is future work; Agent YAML and Benchmark JSON remain
supported configuration entry points.
"""

from zhixing.components import (
    Action,
    ActionExecutionInput,
    ActionType,
    DeviceObservation,
    LegacyActionExecutor,
    PerceptionResult,
    PlanResult,
    ReasoningInput,
    RuntimeContext,
    TaskInput,
    adapt_component,
)


class LegacyTextPerception:
    """An unchanged plugin with the pre-protocol method name."""

    def perceive(self, input):
        return PerceptionResult(
            mode="recorded",
            original_screenshot_path=input.screenshot_path,
            prompt_representation="A recorded settings screen",
        )


class FinishReasoning:
    """A new structural component: no ZhiXing base-class inheritance."""

    def invoke(self, input: ReasoningInput, runtime: RuntimeContext) -> Action:
        runtime.emit(
            phase="decision",
            role="reasoning",
            component=type(self).__name__,
            kind="complete",
            payload={"task_id": input.task.id},
        )
        return Action(ActionType.DONE, thought="No-device example completed")


def main() -> None:
    events = []
    runtime = RuntimeContext(run_id="component-example", event_sink=events.append)
    observation = DeviceObservation("recorded-screen.png", 1080, 2400)

    perception = adapt_component("perception", LegacyTextPerception()).invoke(
        observation, runtime
    )
    action = FinishReasoning().invoke(
        ReasoningInput(
            task=TaskInput("Explain the current screen", id="example-1"),
            plan=PlanResult("Inspect the recorded observation, then finish"),
            perception=perception,
        ),
        runtime,
    )
    result = LegacyActionExecutor().invoke(ActionExecutionInput(action), runtime)

    print(result.status.value)
    print(events[0].to_safe_dict()["kind"])


if __name__ == "__main__":
    main()
