# studio-benchmark-export Specification

## Purpose
定义 Studio Benchmark 正式材料导出的闭合 inventory、严格 manifest、准备与浏览器交接、安全性及真实状态边界。

## Requirements

### Requirement: Export 候选必须来自完整闭合的权威 inventory
Studio SHALL 从当前 Experiment 已完整、有界闭合的 artifact inventory 构造 Export
候选，并 SHALL 保留每个 descriptor 的 exact Experiment/TaskRun scope、kind、
availability、content type、size、SHA-256、causal identity 与后端返回的 content
capability。投影 MUST 对 Experiment report、Experiment bundle 和 publication
manifest singleton 做唯一性校验，并按 TaskRun scope 区分 report、trajectory 与其他
可读 evidence。系统 MUST NOT 从文件名、kind、artifact id、Core reference、宿主路径
或 bundle member path 构造下载 URL。

#### Scenario: 完整 inventory 中的合法 publication
- **WHEN**闭合 inventory 对 report、bundle、publication manifest 和两个 TaskRun trajectories 各提供唯一且 scope 一致的 descriptor
- **THEN**Export drawer 将它们作为相互独立的候选，并只保留 descriptor 已给出的 exact content capability

#### Scenario: singleton 冲突
- **WHEN**同一 Experiment 出现两个可见 Experiment bundle 或两个 publication manifest singleton
- **THEN**Export projection 以 integrity conflict 失败关闭且不选择任意一个，Report 其余已验证事实保持可用

#### Scenario: inventory 无法闭合
- **WHEN**inventory 超过成员上限、cursor 不前进、页面 scope 冲突或无法取得全部 metadata
- **THEN**Export 整体不进入可准备状态且不从当前页、缓存候选或推断路径降级导出

### Requirement: Publication manifest 必须严格有界解析
Studio SHALL 只在 manifest descriptor 可读、scope 一致、content type 为允许的 JSON
且 size 不超过 2 MiB 时显式读取 `studio_benchmark_publication_manifest` schema 1。
Parser MUST 校验 exact kind/version/Experiment/TaskRun identities、安全相对 member
reference、唯一 member、已知 kind/content type、非负 size、canonical SHA-256、
scope、availability 与有界 `excludedEvidence`；member 总数 MUST 不超过 2000。
浏览器 MUST NOT 解压、扫描或从 ZIP 反推 manifest。

#### Scenario: 合法 manifest
- **WHEN**用户显式展开 scope 一致且不超过边界的 publication manifest
- **THEN**页面展示 bundle identity、member 数量、总声明大小、member kind/size/hash 摘要和排除原因，并明确这些是已发布 manifest facts

#### Scenario: manifest identity 或 member 冲突
- **WHEN**manifest 的 Experiment/TaskRun scope 与 descriptor 冲突，或 member reference 重复、非安全相对路径、digest 非法
- **THEN**manifest 审阅局部失败关闭且不把其内容用于启用任何下载

#### Scenario: standalone inventory 与 bundle manifest 差异
- **WHEN**manifest 声明一个 bundle member，但 Experiment inventory 没有对应的独立可读 artifact
- **THEN**页面保留“bundle 内已声明成员”和“独立 artifact availability”两类事实，不把前者伪造成新的 content capability

### Requirement: Export 必须先刷新并准备再交给浏览器
每次 Export SHALL 由两个显式用户动作组成。`Prepare export` MUST 重新获取当前
Experiment、TaskRuns 与完整 artifact inventory，重新执行 exact scoped projection，
并对目标 content capability 发起 HEAD 准备检查；只有响应 status、normalized
content type、canonical content length、content disposition 与 descriptor 合同一致时，
该目标才 SHALL 进入 `ready-for-handoff`。随后 `Hand off to browser` SHALL 使用同一
exact capability 的普通浏览器导航或下载动作，而不是把大文件读入 JavaScript。

#### Scenario: 准备一个大 bundle
- **WHEN**用户准备一个 descriptor size 在后端 policy 内但不适合前端内存读取的 bundle
- **THEN**客户端只刷新 metadata 并执行无 body HEAD，随后以普通 exact link 交给浏览器，不 fetch、缓存、解压或重打包 bundle bytes

#### Scenario: metadata 在准备前已变化
- **WHEN**旧页面显示 available，但权威刷新后 descriptor 已变为 missing 或 corrupt
- **THEN**目标不执行 HEAD 或浏览器交接，并显示刷新后的持久 availability

#### Scenario: HEAD 合同不匹配
- **WHEN**HEAD 的 content type、length 或 disposition 与刷新后的 descriptor/下载策略冲突
- **THEN**目标进入局部 header-conflict 状态且 handoff 被禁用

### Requirement: Prepare 控制器必须 single-flight 且可销毁
Export prepare state SHALL 由 Report workbench 的短生命周期本地控制器拥有，按
Experiment、TaskRun、artifact identity、digest、size 与 capability 组成稳定 target key。
同一 target 的重复点击 MUST 合并为一个进行中的 metadata refresh/HEAD；scope 改变、
目标改变、drawer 关闭或组件卸载 MUST 取消旧请求并忽略迟到结果。该状态 MUST NOT
写入 SQLite、Zustand、URL、localStorage、Monitor event session 或长期 Query byte cache。

#### Scenario: 双击 Prepare
- **WHEN**用户在第一个 HEAD 未完成前再次点击同一 target 的 Prepare
- **THEN**客户端至多保留一个该 target 的准备请求且两个动作不能产生并发下载或第二个 export identity

#### Scenario: 准备期间切换 TaskRun
- **WHEN**TaskRun-scoped trajectory 正在准备时用户切换到另一个 TaskRun
- **THEN**旧请求被取消，迟到结果不能为新 scope 启用 handoff

#### Scenario: descriptor 变化
- **WHEN**刷新返回相同 artifact identity 但新的 digest、size 或 capability
- **THEN**旧 ready state 失效，新 target 必须重新准备

### Requirement: Export 失败必须局部、可刷新且不伪造完成
Missing、corrupt、failed、excluded、hidden、scope conflict、manifest invalid、
network failure、HEAD failure 和 header conflict SHALL 保持可区分。一次可重试失败
MUST 释放对应 single-flight，并 SHALL 允许用户重新刷新权威 inventory 后准备；
一个 artifact 的失败 MUST NOT 禁用其他已验证候选，MUST NOT 重跑 Experiment、
重新发布 artifact 或改写后端 availability。

#### Scenario: trajectory corrupt、report available
- **WHEN**trajectory 的 HEAD 触发 corrupt closure，但 Experiment report 仍可用
- **THEN**trajectory 显示 corrupt 且可刷新，report 仍可独立准备和交接

#### Scenario: retryable transport failure
- **WHEN**HEAD 因网络失败而没有得到权威响应
- **THEN**客户端释放进行中状态，显示局部 retryable failure，并在 Retry 时先重新获取 metadata

#### Scenario: hidden evidence
- **WHEN**inventory 只声明匿名 `hiddenCount`
- **THEN**Export 只显示聚合排除提示，不创建 hidden identity、content link 或下载 action

### Requirement: Export 必须保持安全和真实措辞
Export SHALL 只消费既有 managed publication 与 scoped capabilities，并 MUST NOT
生成新 report/bundle、在前端打包、扫描 ZIP、读取 storage reference/宿主路径、暴露
Prompt/secret/raw serial、重算正式统计、连接设备、启动 Worker、实例化 plugin/model
或进入 SSE session。浏览器动作后 UI SHALL 只声明 `handed off to browser`，不得声明
下载完成、文件落盘、客户端 digest 验证完成、bundle verifier 通过或自动失败诊断。

#### Scenario: 浏览器接管下载
- **WHEN**用户从 ready target 点击 `Hand off to browser`
- **THEN**UI 记录本地 handed-off 状态并提示浏览器将处理响应，不显示 completed、verified 或 saved

#### Scenario: HEAD 与 GET 之间内容变化
- **WHEN**HEAD 成功后 artifact 在 GET 前变为缺失或损坏
- **THEN**GET 仍由 managed resolver 再次验证并安全失败，UI 不把先前 HEAD 解释为下载或完整性完成证明

#### Scenario: no-device export
- **WHEN**terminal Experiment 的 managed publication 已存在且当前环境没有设备、Worker、plugin 或 model
- **THEN**用户仍可从 History 进入 Report、审阅 manifest、准备并交接允许的 artifact，且没有运行副作用
