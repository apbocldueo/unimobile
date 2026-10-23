# benchmark-package-contract Specification

## Purpose
TBD - created by archiving change define-benchmark-package-and-experiment-protocol. Update Purpose after archive.
## Requirements
### Requirement: Benchmark Package manifest
系统 SHALL 定义带版本的 `BenchmarkPackage` manifest，至少包含 schema version、`publisher/name@semver` 包身份、标题、支持平台、任务 split 入口、资源与 ground truth 清单、App 与插件要求，以及可选默认 ExperimentProtocol 引用。

#### Scenario: 有效 Package manifest
- **WHEN** 一个 manifest 提供合法包身份、至少一个非空 task split 且所有入口均满足合同
- **THEN** 系统返回规范化的 `BenchmarkPackage` 元数据，且不加载设备或执行任务

#### Scenario: 非法包身份或版本
- **WHEN** manifest 的 publisher、name 或语义版本为空或不合法
- **THEN** 验证失败并定位到对应 identity 字段

### Requirement: Existing BenchmarkTask remains the task contract
Package 中的任务文件 MUST 继续使用现有 `BenchmarkTask` V1 与 `BenchmarkSuite` 合同；Package 层不得引入另一套不兼容的任务字段，也不得静默转换被现有合同拒绝的 legacy 字段。

#### Scenario: Package contains canonical V1 tasks
- **WHEN** split 指向包含唯一 task ID 的有效 `BenchmarkSuite`
- **THEN** Package 任务验证成功并保留每个 `BenchmarkTask` 的规范语义

#### Scenario: Package contains legacy task fields
- **WHEN** Package 任务使用 `task`、`params_config`、`setup_config` 或其他现有合同拒绝的 legacy 字段
- **THEN** Package 验证返回原 `BenchmarkTask` 合同诊断，不进行隐式转换

### Requirement: Package-relative resources
系统 SHALL 通过逻辑 `ResourceRef` 管理 asset 与 ground truth。每个引用 MUST 包含稳定逻辑 ID、Package 内相对路径、media type、SHA-256 与 size；绝对路径、`..` 越界和解析后逃逸 Package 根目录的路径 MUST 被拒绝。

#### Scenario: Valid asset reference
- **WHEN** `asset://camera-seed` 对应的 manifest 条目指向 Package 根内文件且摘要与大小一致
- **THEN** 引用验证成功并解析为逻辑资源描述，不把绝对路径写入语义模型

#### Scenario: Path traversal attempt
- **WHEN** 资源条目包含绝对路径、`..` 或通过符号链接逃逸 Package 根目录
- **THEN** 验证失败且不得读取 Package 根目录之外的目标内容

#### Scenario: Resource digest mismatch
- **WHEN** 资源文件存在但其 SHA-256 或 size 与 manifest 不一致
- **THEN** 完整验证失败并报告资源逻辑 ID、期望摘要和实际摘要

### Requirement: Ground truth representation
系统 SHALL 允许小型 ground truth 以内联 JSON-compatible 值表示，并允许共享或大型 ground truth 通过 `groundtruth://<id>` 引用；系统 MUST NOT 自动猜测或生成缺失的 ground truth。

#### Scenario: Inline ground truth
- **WHEN** 任务声明一个 JSON-compatible 的内联 ground truth
- **THEN** 该值进入任务语义并可参与后续 TaskInstance identity

#### Scenario: Referenced ground truth
- **WHEN** 任务引用 manifest 中存在且摘要有效的 `groundtruth://expected-state`
- **THEN** 验证成功并保留逻辑引用与内容摘要

#### Scenario: Missing ground truth reference
- **WHEN** 任务引用未在 Package 清单中声明的 ground truth ID
- **THEN** 验证失败并定位到该任务的引用路径

### Requirement: Package dependency and application declarations
Package SHALL 声明完成任务所需的逻辑 App、平台约束和插件引用；声明 MAY 包含 Android package ID、登录要求与版本约束，但 MUST NOT 包含设备 serial、凭据、live handle 或解析后的插件实例。

#### Scenario: Declarative App requirements
- **WHEN** Package 声明逻辑 App 及其 Android package ID 和版本约束
- **THEN** manifest 验证成功并保留为后续 ExperimentProtocol 检查所需的声明

#### Scenario: Secret embedded in manifest
- **WHEN** manifest 在 App 或插件要求中包含 API key、password、token 或设备句柄字段
- **THEN** 验证失败或安全诊断拒绝把该值纳入 Package 输出

### Requirement: Source-neutral package semantics
同一 Benchmark Package 在不同合法文件系统位置加载时 SHALL 产生相同的规范化 Package 内容；Package 语义 MUST NOT 依赖当前工作目录。

#### Scenario: Package copied to another directory
- **WHEN** 两个目录包含字节与 manifest 语义相同的 Package
- **THEN** 两者产生相同 Package identity 与资源摘要集合

#### Scenario: CWD-dependent task resource
- **WHEN** 任务仍引用 `data/...` 等未声明的当前工作目录相对资源
- **THEN** Package 验证失败并要求使用已声明的逻辑资源 URI

