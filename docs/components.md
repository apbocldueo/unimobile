# ZhiXing component programming model

`zhixing.components` is the side-effect-free Python extension boundary for
Mobile Agent components. Version 1 uses one synchronous call shape:

```python
output = component.invoke(input, runtime)
```

Explicit local SDK objects may still use structural typing without inheriting a
ZhiXing class. Reusable formal components use either a role-specific
`BaseComponent` subclass or the `@component` decorator together with an
immutable `ComponentSpec`; see [external component authoring](external-components.md).
Importing this namespace does not discover plugins, connect to a Device, read
secrets, create runtime directories, or import OpenAI, Torch, Transformers,
OpenCV, Harmony, or Benchmark-only integrations. It also does not change the
deliberately small `zhixing` root exports.

Installed external distributions declare the fixed
`zhixing.components` Entry Point group and export a versioned `ComponentBundle`.
Use `zhixing components list` for metadata-only inspection, or see
[external component distribution and discovery](external-components.md) for
wheel, editable, Git, allowlist/denylist, Catalog, and SDK examples.

## Studio Catalog placement

Component Catalog availability and Studio canvas placement are different facts. Safe Catalog
descriptors now carry a framework-validated placement:

- `agent_capability` may appear only through one of the six core capability families or an
  approved Grounder/Tool extension;
- `dependency_only` supplies an implementation dependency such as an LLM provider and is edited
  in Inspector, not as a canvas node;
- `runtime_internal` supplies generated observation, action, parsing, and control glue;
- `benchmark_only` remains owned by Benchmark initialization/evaluation.

An unknown external contract defaults to non-authorable placement. A provider cannot obtain a
generic Studio card merely by publishing safe metadata: its requested family must match the exact
role, NodeContract ports, category, side-effect boundary, and structured termination policy.
These Studio placement rules do not change the component's Python identifier or prevent direct
use through the supported Python/YAML AgentGraph contracts.

External providers are trusted Python code loaded in the host process. ZhiXing
does not sandbox provider imports or component construction. The default
`components doctor` path avoids proactively injecting or invoking real Device,
LLM, ADB, or network capabilities, and reports unexecuted invocation checks as
`skipped`/`structural-only`; it cannot prevent arbitrary provider-side effects
and does not establish algorithmic correctness.

## Role signatures

| Role | Input | Output | Legacy entry point |
| --- | --- | --- | --- |
| `Perception` | `DeviceObservation` | `PerceptionResult` | `perceive(PerceptionInput)` |
| `Planner` | `PlanInput` | `PlanResult` | `make_plan(PlanInput)` |
| `Reasoning` | `ReasoningInput` | `Action` | `think(...)` |
| `Memory` | `MemoryInput` | `MemoryResult` | `add`, `get_working_context`, `clear`, optional retrieval methods |
| `Verifier` | `VerifierInput` | `VerifierResult` | `verify(VerifierInput)` |
| `Grounder` | `GroundingInput` | `GroundingResult` | `ground(path, description, width, height)` |
| `LLM` | `LLMInput` | `LLMResult` | `generate(prompt, images)` |
| `Device` | `DeviceRequest` | `DeviceResult` | Device primitive methods |
| `ActionExecutor` | `ActionExecutionInput` | `ActionResult` | current Runner action mapping |
| `BenchmarkInitializer` | `BenchmarkInitInput` | `BenchmarkInitResult` | `generate(params)` or `execute(meta, params)` |
| `Evaluator` | `EvaluationInput` | `EvalResult` | `evaluate(context)` |

This V1 component contract is synchronous. Async invocation, stream-returning
components, and remote components are not supported.

## Implementing a component

```python
from zhixing.components import (
    Action,
    ActionType,
    ReasoningInput,
    RuntimeContext,
)


class StopWhenAsked:
    def invoke(
        self,
        input: ReasoningInput,
        runtime: RuntimeContext,
    ) -> Action:
        runtime.emit(
            phase="decision",
            role="reasoning",
            component=type(self).__name__,
            kind="complete",
            payload={"instruction_length": len(input.task.instruction)},
        )
        return Action(ActionType.DONE, thought="Example completed")
```

The common objects are `TaskInput`, `DeviceObservation`, `PerceptionResult`,
`PlanResult`, `ReasoningInput`, `Action`, `ActionResult`, `RunEvent`,
`RunResult`, `RuntimeContext`, and `AgentState`. Role-specific request/result
objects cover Memory, grounding, LLMs, Devices, Action execution, Benchmark
initialization, and evaluation.

Existing `Action`, perception, plan, memory-fragment, and verification classes
are re-exported rather than copied, so current built-ins and new components
exchange the same Python object identities.

## RuntimeContext boundary

`RuntimeContext` is run-scoped and holds:

- run id and current step;
- isolated `AgentState`;
- optional Device, event sink, cancellation, and artifact services;
- namespaced extension metadata.

Task instructions, plans, perception values, memory contents, actions, and
evaluator inputs belong to the role input objects, not runtime metadata.
Credentials are not RuntimeContext fields. Safe context/event/result views
redact secret-like metadata keys and represent live services only as presence
flags.

## Tagged operations

Stateful or multi-operation roles use explicit enums rather than guessing from
dictionaries:

- `MemoryOperation`: `APPEND`, `READ`, `RESET`, `LOAD_KNOWLEDGE`,
  `RETRIEVE_EXPERIENCE`.
- `DeviceOperation`: `OBSERVE`, `TAP`, `LONG_PRESS`, `SWIPE`, `TEXT`, `KEY`,
  `START_APP`, `WAIT`, `SHELL`.
- `BenchmarkInitKind`: `TASK_PARAMETER` or `ENVIRONMENT`.

Passing a task initializer input to an environment initializer, omitting an
append fragment, or supplying an unsupported Device request raises a typed,
deterministic input error before an unrelated legacy method can run.

## Legacy compatibility

Use `adapt_component` on an already-instantiated object:

```python
from zhixing.components import adapt_component

perception = adapt_component("perception", existing_perception)
result = perception.invoke(observation, runtime)

legacy_view = adapt_component("perception", new_perception, "legacy")
result = legacy_view.perceive(old_perception_input)
```

The first direction wraps `perceive`, `make_plan`, `think`, Memory lifecycle,
`verify`, `ground`, `generate`, Device primitives, initializer operations, and
`evaluate` as canonical invocations. The reverse direction presents current
engine method names around an invocation-native component. An already
conforming instance is returned unchanged.

Current Reasoning implementations may return either `Action` or
`(Action, raw_response)`. Canonical invocation always returns `Action`; the
adapter stores raw text under
`zhixing.legacy.raw_response` in `Action.metadata`. The reverse adapter uses
that key to reconstruct the tuple expected by the current Agent engine.

`PluginRegistry.adapt_instance(role, instance, target=...)` exposes the same
adaptation after registry lookup/instantiation. It does not change registration,
lookup precedence, or plugin discovery.

## Device and ActionExecutor

Reasoning produces a platform-neutral `Action`. `ActionExecutor` maps that
action to Device primitives and returns a typed `ActionResult`; Reasoning never
receives the Device handle. `LegacyActionExecutor` mirrors the current Runner
mapping for tap, long press, text, swipe, key, start-app, wait, done, and fail.
The existing Runner still owns physical execution in this release; delegating
Runner execution to the new component is follow-up work after parity testing.

## Configuration compatibility

The component programming model is additive. Agent YAML still builds
`AgentConfig`; Benchmark JSON still builds `BenchmarkSuite`. Neither format is
converted into the other, and neither is removed by future Python composition.
From a source checkout, run the no-device protocol/adapter example with
`python -m examples.python_components`. When using an installed wheel, copy the
example into your project and run it normally.
