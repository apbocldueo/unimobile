# Studio Benchmark Publication 与 Replay（Stage 5.2C-2）

本文记录已经实现并验证的 Stage 5.2C-2：把 Benchmark Core 的正式结果、轨迹与
运行证据纳入 Studio 受管边界，并将 terminal TaskRun 提升为可直接打开的 native
Replay。本文是 `AGENTS.md` 链接的长期实现入口；规范性需求仍以主 OpenSpec specs
和 Stage 5 合同为准。

本文只证明 Stage 5.2C-2 publication/Replay；后续 Stage 5.2C-3 startup recovery
现已由独立 Change 完成。本文不代表 Stage 5.3 React Monitor、Stage 5.4 报告统计
界面、多 Task/多 Agent 执行、PostgreSQL、retention/delete 或真实 Android 验收完成。

## 解决的问题

5.2B 已经执行 Benchmark 并持久化 bounded TaskResult，5.2C-1 已经可靠传输 durable
journal，但正式 Core report/trajectory/bundle 仍位于私有文件边界，TaskRun 也没有
显式 Replay identity。浏览器无法通过稳定资源链接复核或导出完整证据，直接暴露
临时路径又会破坏 scope、完整性和 secret 边界。

本 Change 建立以下闭环：

```text
complete BenchmarkSuiteResult
        ↓
server-owned private staging
        ↓
Core report / result / trajectory / manifest
        ↓
policy-filtered managed artifacts + Studio bundle
        ↓
one SQLite metadata transaction
   ├── publication component availability
   ├── Experiment / TaskRun links
   ├── native Benchmark Replay
   └── committed journal events
        ↓ COMMIT 后
Benchmark event waiter notification
```

任务执行事实仍由 Benchmark Runtime 产生；Studio 不重算 outcome、evaluation、
micro/macro、Wilson 或 paired comparison。

## 已实现的合同

### 完整正式准备

- execution adapter 在生成 bounded Studio TaskResult 的同时，保留完整
  `BenchmarkSuiteResult` 给正式 publication preparer；
- preparer 只写入 server-owned、Experiment-scoped 私有 staging，客户端不能提供
  输出路径；
- 复用现有 Benchmark Core reporting writer 生成报告、结果、JSONL trajectory、
  manifest 与 Core bundle；
- 额外保留不可变 definition snapshot，并记录 preparation fingerprint、成员清单和
  有界诊断；
- preparation 失败不删除已经提交的 TaskResult。

### 受管 artifact 与 Studio bundle

- SQLite schema 6 增加 publication、artifact metadata 和显式 TaskRun Replay 映射；
- artifact 使用 Experiment/TaskRun scope、稳定 opaque identity、content type、
  size、SHA-256、availability、provenance 与 causal identity；
- managed store 使用原子不可变写入、文件/Experiment 总量限制和允许的 content
  type，不扫描任意 workspace 或 `temp/`；
- import 只接受 expected private Experiment namespace 下已声明的 JSON/PNG/XML
  成员，拒绝绝对路径、`..`、目录、symlink escape、未知类型和跨 scope identity；
- 每次读取都重新核对 scope、size 和 SHA-256。missing/corrupt 不返回损坏字节，
  并事务化关闭 artifact、publication component、TaskRun/Experiment link 与 Replay
  integrity；
- Studio experiment bundle 包含不可变 definition、正式输出、允许的运行证据、
  publication manifest 与内部 hash manifest；公共 verifier 校验成员路径、size 和
  digest；
- 专用 Prompt 文件不进入受管内容或 bundle；嵌套 Prompt/secret/raw serial/宿主
  路径经统一 sanitizer 清洗。已捕获且清洗后的完整模型响应可以作为允许的独立
  artifact 保留。

### native Benchmark Replay

- terminal TaskRun 使用 publication fingerprint 导出的稳定、服务返回的显式
  Replay identity；客户端不得自行推导；
- Replay provenance 是 `native_benchmark_task_run`，与普通 Studio Run 和显式
  legacy Benchmark import 分离；
- envelope 保留不可变 AgentGraph snapshot、完整 durable journal 前缀、Agent
  status、Benchmark phases/outcome/evaluation、嵌套 Agent moments、诊断和同一组
  managed artifact identities；
- PASS、Agent SUCCESS + Benchmark FAIL、INVALID、device failure、result-level
  cancellation 都保留各自事实；启动前取消且没有 TaskResult 时不创建空 Replay；
- Replay identity/provenance 冲突只使 Replay component 失败，已验证的 report、
  trajectory 和 bundle 仍可用。

### 原子可见性与 HTTP

一个 coordinated SQLite transaction 同时提交 artifact metadata、publication
components、Replay envelope/index、TaskRun 映射、Experiment aggregate availability
与 journal events。waiter 只在 COMMIT 后通知；故障注入回滚后，旧 high-water、
artifact、Replay 和 link 都保持不可见。

默认完整 composition 开放：

```text
GET /studio/benchmark-experiments/{experimentId}/report
GET /studio/benchmark-experiments/{experimentId}/bundle
GET /studio/benchmark-experiments/{experimentId}/artifacts/{artifactId}
GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}/artifacts
GET /studio/benchmark-experiments/{experimentId}/task-runs/{taskRunId}/artifacts/{artifactId}
GET /studio/replays/{replayId}
```

Experiment/TaskRun resource 只在 component 确实可用时返回对应 link/capability。HTTP
下载复用 managed resolver，返回已验证的 content type/length；错误使用 Benchmark
domain code，不泄漏内部路径或相邻 resource metadata。

## 设计选择、权衡与替代方案

- **完整 Core 结果与 bounded API 投影分离。** 这避免 Studio 为了 UI 重算正式报告；
  代价是 execution adapter 需要在 finalization 前短暂保留完整 typed result。
- **私有 staging 与公共 managed root 分离。** 相比直接开放 Core 输出路径，多一次
  验证和复制，但获得不可变 scope、稳定 identity 和 export 策略。
- **metadata 与大文件分离。** SQLite 只保存有界 descriptor/DTO，内容进入本地
  managed store；未来 PostgreSQL adapter 可以保持相同 port，但对象存储尚未实现。
- **一个 metadata transaction，不试图事务化文件系统。** 文件先以内容 hash
  不可变准备，随后原子暴露 metadata。数据库回滚不会暴露半成品；未引用文件的
  回收属于未来 retention/cleanup。
- **component 独立 availability。** bundle verifier 失败不会抹掉 report、
  trajectory 或 Replay；Replay identity 冲突也不损坏其他已验证证据。
- **读取时完整性关闭。** 相比只在写入时校验，多一次 hash 开销，但研究证据损坏后
  不会继续以 available link 对外展示。
- **复用现有 Replay API。** Benchmark 只增加 provenance 与 benchmark projection，
  不建立第二套 Replay HTTP/存储系统。

未采用的方案包括直接暴露 `temp/benchmark-runs`、把大文件写入 SQLite、由前端拼接
artifact/Replay 路径、重新计算报告、把 Prompt 默认导出，以及 publication 失败时
回滚 TaskResult。它们分别会破坏安全 scope、存储边界、身份稳定性、事实唯一性或
失败可审计性。

## 验证证据

本次实现的自动化证据：

- 新 publication/Replay 专项：`23 passed`；
- 完整 Studio + Benchmark：`276 passed`；
- 完整后端：首次非沙箱运行 `565 passed, 1 failed`；唯一失败是 C-1 已记录的普通
  Run terminal cancel/high-water 时序 flake，单独立即复验为 `1 passed`，没有证据
  表明它由 Benchmark publication 引入，也未将其描述为已修复；
- clean wheel 安装后，schema 6 composition、publication services、受管 artifact
  与 Replay publisher 可从已安装包加载；
- clean wheel 外部环境中的代表性 fake-device Experiment 与 publication/native
  Replay 测试通过；
- synthetic canary 扫描覆盖 SQLite、managed files、report、trajectory、嵌套
  bundle、Replay export、HTTP 与 SSE，未发现测试 secret、raw serial、绝对路径、
  Prompt 或 live object 泄漏；
- schema 5 的已填充数据库可升级到 schema 6，TaskRun facts 不丢失；
- rollback、post-commit notify、幂等重试、provenance conflict、missing/corrupt、
  traversal、symlink、scope mismatch、size/hash mismatch 与 bundle tamper 均有测试。

可复验命令：

```bash
env PYTHONPATH=tests uv run --extra dev python -m pytest -q \
  tests/studio/test_benchmark_publication_replay.py

env PYTHONPATH=tests uv run --extra dev python -m pytest -q \
  tests/studio tests/benchmark

python -m compileall -q zhixing/studio tests/studio

/Users/maczhen/.npm/_npx/abab5bd700860149/node_modules/.bin/openspec \
  validate implement-studio-benchmark-publication-replay-5-2c2 --strict
```

clean-wheel 验证必须在仓库外的隔离虚拟环境中导入安装包；只在源码目录中执行不能
证明 wheel 包含新增模块与迁移。

## 已知限制与下一步

- 本 Change 交接时尚无进程重启决策；后续 5.2C-3 现已实现 accepted/starting
  requeue、uncertain in-flight interruption 和 finalizing-only recovery，详见
  [Startup Recovery](studio-benchmark-startup-recovery.md)；
- 当前 Worker 仍限制一个 Agent、一个 Task、一个 repeat；
- React Monitor、reporting UI 与浏览器端 Replay/Report 导航尚未实现；
- SQLite 是唯一实现的 adapter；没有 PostgreSQL、对象存储、quota、delete、
  retention 或 orphan-file cleanup；
- publication 成功不证明 Benchmark task 成功；Replay 明确保留 Agent status 与
  Benchmark outcome 两条独立轴；
- 所有新增执行证据来自 fake-device 与 clean-wheel，未新增真实 Android trajectory，
  不能声明任意设备、Agent 或 Benchmark 已验收；
- 自动失败诊断仍未实现；结构化 Replay 只支持审计和人工定位。

Stage 5.2C-3 现已完成；当前下一步是 Stage 5.3 React Benchmark Monitor。

## 规范与历史来源

- [Stage 5 产品路线](studio-benchmark-experiment-roadmap.md)
- [Stage 5 合同](studio-benchmark-experiment-contracts.md)
- [Stage 5.2B Worker](studio-benchmark-execution-worker.md)
- [Stage 5.2C-1 Event Stream](studio-benchmark-event-stream.md)
- [Stage 5.2C-3 Startup Recovery](studio-benchmark-startup-recovery.md)
- [当前已接受的 OpenSpec 合同](../openspec/specs)（5.2C-2 历史变更不随公开源码发行）
