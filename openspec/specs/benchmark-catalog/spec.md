# benchmark-catalog Specification

## Purpose
TBD - created by archiving change define-benchmark-package-and-experiment-protocol. Update Purpose after archive.
## Requirements
### Requirement: Explicit Benchmark Catalog sources
系统 SHALL 建立 Benchmark Catalog，并仅从调用者显式本地目录、配置的本地 Catalog 根和固定 Entry Point group `zhixing.benchmarks` 暴露的已安装独立 Benchmark 分发包发现 Package。已安装候选的 Entry Point 值 SHALL 指向随 distribution 打包且包含 `benchmark.yaml` 的 Python resource package。Catalog MUST NOT 隐式递归扫描任意当前工作目录。

#### Scenario: Add a local package directory
- **WHEN** 用户显式向 Catalog 添加一个合法 Package 目录
- **THEN** Catalog 可按 Package identity 查询该 Package，且不要求它先被构建成 wheel

#### Scenario: Discover installed benchmark distribution
- **WHEN** 一个已安装独立分发包通过约定元数据声明 Benchmark Package
- **THEN** Catalog 通过 Entry Point 与 distribution 文件元数据定位 manifest，而不修改 ZhiXing 核心注册表、不调用 Entry Point load 且不导入目标 module

#### Scenario: Unrelated package under current directory
- **WHEN** 当前工作目录下存在未显式配置的 Benchmark-like 文件
- **THEN** Catalog 不得自动加入该文件

### Requirement: Metadata-only list operation
`benchmark list` SHALL 只读取发现所需的安全元数据，并输出 Package identity、标题、版本、来源类型和可用 split。它 MUST NOT 校验大型资源摘要、导入插件实现、执行第三方代码、连接设备或下载内容。

#### Scenario: List available packages
- **WHEN** Catalog 中存在 AndroidWorld 与 AppAgent Package
- **THEN** `benchmark list` 返回二者的稳定身份和 split 摘要

#### Scenario: Broken optional plugin
- **WHEN** 某 Package 声明的可选插件当前不可导入
- **THEN** list 仍返回 Package 元数据，并可附带非执行性可用性提示

### Requirement: Package information operation
`benchmark info` SHALL 展示所选 Package 的 manifest 摘要、split、任务数量、平台/App/插件要求、资源与 ground truth 摘要以及默认 Protocol，但 MUST 对 secret 和本机绝对路径进行排除或清洗。

#### Scenario: Inspect AndroidWorld package
- **WHEN** 用户按稳定 identity 查询 AndroidWorld
- **THEN** info 返回其 81 个唯一任务的 split 统计、要求和资源摘要，不执行任务

#### Scenario: Ambiguous package identity
- **WHEN** 多个 Catalog 来源提供相同可读 Package identity 但内容 identity 不同
- **THEN** info 返回歧义诊断并要求显式选择来源，不按发现顺序静默覆盖

### Requirement: Layered validate operation
`benchmark validate` SHALL 执行 manifest 结构、现有 BenchmarkTask 合同、跨引用语义、资源路径与摘要、ground truth、split、Catalog identity 和 Protocol 检查，并聚合所有可独立检测的诊断。它 MUST NOT 连接设备、运行插件、调用模型或启动 Benchmark Pipeline。

#### Scenario: Validate complete package
- **WHEN** Package 的任务、资源、ground truth、要求和默认 Protocol 均有效
- **THEN** validate 成功并输出 Package、Plan 与 Protocol identity 摘要

#### Scenario: Validate without device
- **WHEN** 主机没有连接 Android 设备
- **THEN** 完整定义层验证仍可完成，且不把缺少设备报告为错误

#### Scenario: Multiple validation failures
- **WHEN** Package 同时存在重复 task ID、资源摘要错误和非法 Protocol 预算
- **THEN** validate 返回全部可独立检测的结构化诊断

### Requirement: First-party AndroidWorld package
仓库 SHALL 提供首批 AndroidWorld Benchmark Package，使用现有 V1 JSON 作为 81 个唯一任务的迁移基线，并记录旧源 82 个数组项及重复 `AndroidWorld_72` 的差异。Package 中原先依赖 `data/...` 的 asset 引用 MUST 转换为声明式 Package-relative 资源。

#### Scenario: Validate AndroidWorld migration
- **WHEN** 对 AndroidWorld Package 执行 validate
- **THEN** 任务 ID 唯一、任务数为 81、资源引用闭合，并存在可审计的源数据差异报告

#### Scenario: Duplicate silently discarded
- **WHEN** 迁移产物无法说明旧源重复项如何处理
- **THEN** 迁移完整性验证失败，而不是仅凭 81 个任务通过

### Requirement: First-party AppAgent package
仓库 SHALL 提供首批 AppAgent Benchmark Package，以现有 V1 示例和旧源中的 45 个任务为迁移基线，并将当前工作目录资源引用转换为声明式 Package-relative 资源。

#### Scenario: Validate AppAgent migration
- **WHEN** 对 AppAgent Package 执行 validate
- **THEN** 任务 ID 唯一、任务数为 45、资源引用闭合，且源内容核对结果可审计

### Requirement: Core distribution size boundary
首批 Benchmark Package 的大型 assets MUST NOT 被现有 ZhiXing 核心 wheel 隐式打包；本地目录与独立分发包两种来源 SHALL 使用相同 Catalog 与验证语义。

#### Scenario: Build core wheel
- **WHEN** 构建 ZhiXing 核心 wheel
- **THEN** wheel 不包含顶层 AndroidWorld/AppAgent 大型 assets

#### Scenario: Same package from two source types
- **WHEN** 同一 Package 分别从显式本地目录和独立安装来源发现
- **THEN** 其 Package 与 Plan canonical identity 相同

