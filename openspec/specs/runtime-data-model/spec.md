# runtime-data-model Specification

## Purpose
TBD - created by archiving change define-zhixing-component-protocol. Update Purpose after archive.
## Requirements
### Requirement: Stable cross-role runtime objects
The public component API SHALL define stable runtime objects for `TaskInput`, `DeviceObservation`, `PerceptionResult`, the canonical plan value, `ReasoningInput`, `Action`, `ActionResult`, `RunEvent`, `RunResult`, `RuntimeContext`, and `AgentState`. Each object MUST document required fields, defaults, mutability, and extension metadata semantics.

#### Scenario: Build a task without the engine
- **WHEN** a Python user constructs the minimum task, observation, runtime, and Agent state values from documented fields
- **THEN** the values can be passed through the relevant component protocols without an Agent YAML file or untyped context dictionary

#### Scenario: Construct repeated defaults
- **WHEN** two runtime objects are created without optional collection values
- **THEN** mutation of one object's extension metadata or events does not mutate the other object

### Requirement: Device observation is a portable value
`DeviceObservation` SHALL describe the observation timestamp/sequence, screenshot reference, dimensions, optional UI-tree reference, platform information, and extension metadata without requiring the observation object itself to expose a live Device handle.

#### Scenario: Pass an observation to Perception
- **WHEN** Device or an orchestrator captures a screen and optional UI tree
- **THEN** Perception receives all current `PerceptionInput` information through one typed `DeviceObservation`

#### Scenario: Use a recorded observation
- **WHEN** a replay test constructs `DeviceObservation` from recorded artifact references
- **THEN** it can invoke Perception without connecting to a physical Device

### Requirement: Explicit reasoning and execution data flow
`ReasoningInput` SHALL carry task, canonical plan, perception result, memory context, and available capability/application information explicitly. `ActionResult` SHALL distinguish success, failure, skipped, and terminal outcomes and MAY carry sanitized error and platform metadata.

#### Scenario: Reason without RuntimeContext lookup
- **WHEN** Reasoning needs the current task, plan, observation interpretation, memory, or available applications
- **THEN** those values are available from `ReasoningInput` and are not hidden in runtime metadata

#### Scenario: Report device execution failure
- **WHEN** a Device primitive fails while executing an Action
- **THEN** ActionExecutor returns a failed `ActionResult` containing a safe diagnostic and the attempted Action

### Requirement: Bounded RuntimeContext responsibility
`RuntimeContext` SHALL contain run-scoped identity, step position, Agent state, optional runtime services such as Device/event sink/cancellation/artifact access, and an extension metadata mapping. It MUST NOT require business inputs that belong to role input objects, and it MUST NOT define credentials or secrets as public fields.

#### Scenario: Reuse a component in two runs
- **WHEN** the same stateless component is invoked with two RuntimeContext instances
- **THEN** run identifiers, step state, event sinks, and devices remain isolated per run

#### Scenario: Inspect context representation
- **WHEN** a RuntimeContext containing service objects is logged or converted through its documented safe representation
- **THEN** credentials, service internals, and arbitrary object representations are not exposed

### Requirement: Explicit Agent state lifecycle
`AgentState` SHALL represent run-owned mutable orchestration state, including current task/plan, step, last observation/action/result, and extension state needed by strategies. Resetting a run MUST create or clear state deterministically without sharing state between Agent instances.

#### Scenario: Reset between tasks
- **WHEN** an orchestrator starts a second task with an existing Agent composition
- **THEN** the new task does not inherit the prior task's last action, observation, execution result, or strategy state unless an explicit persistent Memory provides it

### Requirement: Structured run events and result
`RunEvent` SHALL identify run, sequence, timestamp, phase/role, component identity, event kind, and a sanitized payload. `RunResult` SHALL report terminal status, final state, trajectory/action results, emitted events or event references, usage summary, and a safe failure when present.

#### Scenario: Observe a component invocation
- **WHEN** an orchestrator emits start, completion, or failure events around a component invocation
- **THEN** consumers can order and attribute events without parsing log strings

#### Scenario: Finish at the step limit
- **WHEN** an Agent run reaches its configured step limit without DONE or FAIL
- **THEN** `RunResult` distinguishes the limit outcome from success, component failure, cancellation, and device failure

### Requirement: Safe extensibility and serialization boundary
Runtime models SHALL permit component-specific metadata without making arbitrary mappings the primary API. Documented serialization and event emission MUST redact common secret fields and MUST NOT blindly traverse live Device, LLM, callback, client, or other service objects.

#### Scenario: Attach plugin metadata
- **WHEN** a plugin adds a namespaced non-secret metadata value to a result
- **THEN** downstream code can preserve the value without changing the stable core fields

#### Scenario: Metadata contains a secret-like key
- **WHEN** metadata supplied to a serializable event contains an API key, token, password, or secret-like key
- **THEN** the emitted/serialized representation redacts the value

### Requirement: No additional mandatory runtime dependency
The runtime data model and protocol package SHALL use the Python standard library and existing base-package types and MUST NOT require an optional model, vision, device, Benchmark, serialization, or validation dependency merely to import or construct public component values.

#### Scenario: Construct models in a base installation
- **WHEN** a user installs `zhixing` without extras and constructs the public runtime models
- **THEN** construction succeeds without OpenAI, Torch, Transformers, OpenCV, Harmony, or Benchmark-only packages

### Requirement: DeviceObservation 记录设备与 artifact 身份
DeviceObservation SHALL 能表达设备平台、安全设备标识、observation sequence、interaction position、采集时间、截图与可选 UI tree 的 artifact 引用和尺寸。该对象 MUST 保持可序列化，且不得持有 live Device、ADB process 或绝对依赖当前工作目录的隐式路径。

#### Scenario: Android observation 序列化
- **WHEN** Android DeviceObserve 返回观察并序列化为 JSON
- **THEN** 结果包含可定位 artifact 的稳定引用和设备安全元数据，不包含设备对象或图像二进制

#### Scenario: 无 UI tree 观察
- **WHEN** 调用方只请求截图
- **THEN** DeviceObservation 以明确空值表达 UI tree 缺省，其他必需身份字段仍完整

### Requirement: ActionResult 表达已确认的设备副作用
ActionResult SHALL 分别表达 execution status、Agent 终止语义、attempted action、是否确认发生物理副作用、effect 类别、安全设备元数据和可选结构化错误。失败或终止结果 MUST NOT 默认声称已执行物理副作用。

#### Scenario: 成功点击结果
- **WHEN** AndroidDevice 确认 TAP 命令成功
- **THEN** ActionResult 为成功并明确 effect_performed 为 true

#### Scenario: 参数校验失败
- **WHEN** ActionExecutor 在调用设备前拒绝非法坐标
- **THEN** ActionResult 为失败且 effect_performed 为 false

#### Scenario: DONE 结果
- **WHEN** Agent 输出 DONE
- **THEN** ActionResult 表达成功终止语义且 effect_performed 为 false

### Requirement: RunResult 区分调度结果与 Agent 终止结果
RunResult SHALL 能同时表达 Kernel 调度状态、Agent outcome/RunStatus、interaction/activation 计数、最终输出、结构化设备失败和 artifact namespace。序列化结果 MUST 使调用方区分“Kernel 正常完成但 Agent 失败”与“Kernel 或设备执行失败”。

#### Scenario: Agent 显式失败
- **WHEN** Kernel 正常调度 ActionExecutor 且该节点返回 FAIL
- **THEN** RunResult 保留成功的 Kernel status 和失败的 Agent outcome

#### Scenario: 设备失败
- **WHEN** Android observation command 失败
- **THEN** RunResult 表达 DEVICE_FAILURE、失败节点和 artifact namespace，而不是普通 Agent FAIL

#### Scenario: 物理交互计数
- **WHEN** 一次运行包含 Tool activations、一次成功 TAP 和 DONE
- **THEN** RunResult 分别报告 activation/decision 信息与一次物理 interaction

### Requirement: RuntimeContext 提供 run-scoped device 与 artifact services
RuntimeContext SHALL 允许调用方注入绑定到本次 run 的 device service、event sink、cancellation 和 artifact store，并通过安全表示暴露其 identity 而非内部对象。反馈和子图执行 MUST 复用同一 services scope。

#### Scenario: 同一 run 的 artifact 分配
- **WHEN** 两个 DeviceObserve activation 在一次运行中请求 artifact 路径
- **THEN** 它们从同一个 run-scoped store 获得不同 sequence 且共享 run namespace

#### Scenario: 安全记录 RuntimeContext
- **WHEN** RuntimeContext 被事件摘要或错误处理序列化
- **THEN** 只记录 run/device/artifact identity，不遍历 device client、进程或 credential

