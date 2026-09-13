# Studio Benchmark Android Profile 与证据来源（Stage 5.6A）

## 状态与范围

Stage 5.6A `implement-studio-benchmark-android-profile-5-6a` 已实现并通过自动化
验证。它解决的是 Studio Run 与 Benchmark Experiment 在连接 Android 前的**显式
设备权限**问题：浏览器和公开 DTO 只选择安全的 `deviceProfileId`，服务端通过受信任
的本地配置解析唯一私有目标，并在任何 initializer、Agent 或 evaluator 动作前完成
固定绑定、漂移检查和独占租约。

本阶段没有运行真实 Android Benchmark，也没有产生新的真机成功证据。它只建立
authority、fail-closed 行为和可追溯的 evidence-origin 合同。真实 Studio service 与
浏览器真机验收仍分别属于 5.6C-1 和 5.6C-2。

## 已实现合同

### 受信任配置与安全目录

Studio server 接受一个有界、严格、版本化的 JSON 文件：

```bash
python -m zhixing.studio serve \
  --device-profile-config examples/device-profiles.example.json
```

也可使用 `ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG`。命令行参数优先；两者都未提供时，
resolver 为空，Catalog、History、authoring、reporting 与 Replay 等无设备资源仍可用，
但新的 Run/Experiment 不能隐式选择设备。

配置 schema 1 只允许 `android` + `adb_serial`，并限制文件为 64 KiB、最多 64 个
profile。未知字段、重复 profile ID、重复目标、不合法 serial、Harmony 或隐式目标均
在 composition 建立前拒绝。加载过程不调用 ADB、模型、secret provider 或网络。
公开 profile DTO 只包含 ID、label、platform 和 configured 状态；serial、配置路径、
私有 fingerprint、target key 和 live device 永不进入公开模型。

### 私有绑定与 SQLite schema 11

首次接受 Experiment 时，服务将以下事实原子提交：

```text
Experiment + TaskRuns + accepted event + private device binding
```

schema 11 新增一对一私有 binding 表，只保存 `profile_id`、私有 binding fingerprint、
候选 environment 和创建时间，不保存 raw serial 或配置路径。公开 Experiment、History、
Report、event 和 definition fingerprint 不 join 该表。幂等 create 重试先返回原命令
结果，即使当前配置后来漂移或移除，也不会静默重绑定。

旧 terminal Experiment 仍可读取；旧 nonterminal Experiment 若没有私有 binding，
会在副作用前以稳定的 unbound authority 失败，服务不会从当前同名 profile 猜测目标。

### 精确目标与跨产品租约

默认 Run 与 Benchmark composition 共用一个进程级 `DeviceLeaseRegistry`，租约键是
私有目标而不是公开 profile ID。因此两个 alias 即使在测试 composition 中指向同一
目标，也不能让 Run/Run 或 Run/Benchmark 并发操作该设备。生产路径从不再向 Core
传递 `serial=None`，也不回退到“唯一在线设备”。

Benchmark 执行顺序现在是：

```text
pure definition/component/storage preflight
  -> read pinned private binding
  -> compare current binding fingerprint
  -> acquire private target lease
  -> verify/construct exact target session
  -> cancellation check
  -> Core platform/locale/orientation/App preflight
  -> initializer -> Agent -> evaluator -> cleanup/publication
```

unknown、unbound、drifted、missing、offline、unauthorized、busy 和 invalid target 都
有固定、有界、不会泄漏 serial 的错误码。platform、locale、orientation、required App、
Protocol 和最终 `INVALID` 语义仍由 Core Benchmark Runtime 拥有，Studio 不复制判断。

### 两轴 evidence origin

TaskResult 和 Replay 现在保留版本化的两轴来源事实：

- acquisition：`fresh_execution`、`replay_projection`、`imported_excerpt`、
  `contract_fixture`；
- environment：`real_android`、`fake_device`、`unverified`。

配置了真实 serial 只代表 authority candidate，不授予 `realDeviceEvidence=true`。
该布尔值只可由实际 source execution facts 推导。本阶段自动化 fake profile 产生
`contract_fixture/fake_device`；旧数据缺少来源事实时保守映射为 `unverified`；native
Replay projection 改变 acquisition，但保留已知 source environment。原 Replay
`provenance` 字符串继续兼容，前端严格 parser 会保留新字段，但 5.6A 不增加最终真机
证据 UI。

## 安全与失败边界

- raw serial、ADB command、配置路径、private fingerprint、target key、device handle、
  secret 和宿主绝对路径不得进入公开 SQLite JSON、HTTP、SSE、日志、diagnostics、
  TaskResult、report、trajectory、Replay、artifact metadata 或 bundle；
- exact target 的 readiness 与 session 构造都发生在租约内；失败后释放租约；
- process-local lease 只协调一个 Studio 进程，不是跨进程或分布式硬件锁；
- 配置漂移、旧数据缺少 binding、离线/未授权/缺失目标都在 Agent 动作前 fail closed；
- injected fake device 只用于测试/programmatic composition，生产 JSON 不能构造 live
  Python object。

## 可复现验证

在仓库根目录运行：

```bash
UV_CACHE_DIR=/tmp/zhixing-uv-cache uv run pytest -q -o pythonpath=tests
cd studio && npm run typecheck -- --pretty false
cd studio && npm run lint
cd studio && npm test
UV_CACHE_DIR=/tmp/zhixing-uv-cache uv run pytest -q \
  tests/packaging/test_studio_android_profile_install.py
```

本次实际证据为：包含 schema-11/profile clean-wheel acceptance 的完整后端
`828 passed`；该 clean-wheel 用例也曾独立运行并得到 `1 passed`；5.6A focused
backend 集合 `149 passed`；完整前端
`88 files / 391 tests passed`，typecheck 与 lint 通过。clean-wheel 测试分别启动空
resolver 和 bounded fake resolver，并确认 device/model/network/secret canary 均为
零。所有结果都是 no-device/fake/contract evidence，不是 fresh real Android evidence。

## 部署、停用与回滚

部署前备份 Studio SQLite 数据库，创建权限受控的 profile JSON，并通过 CLI 或环境
变量重启服务。示例文件中的 `emulator-5554` 必须替换为用户明确选择的 exact ADB
serial；不要把含真实 serial 的本地配置提交到版本库。

安全停用只需移除配置参数/环境变量并重启：profile directory 变为空，新的设备执行
fail closed，已有公开历史和证据仍可读取。应用二进制若回滚到不理解 schema 11 的
旧版本，应恢复升级前数据库备份或使用新 workspace；不要手工删除 binding 表。受管
evidence 文件不因 schema 11 迁移而改变。

## 已知限制与后续

- 没有跨进程、跨主机或分布式设备 ownership；
- 没有 broad Android/Harmony compatibility、任意 App/任务或模型质量证明；
- 没有 real Android Studio service/browser acceptance；
- Studio Worker 仍明确限制为 1 Agent × 1 Task × 1 repeat；
- provenance parser compatibility 已完成，但最终用户可见的 fresh/fake/historical
  presentation 留给 5.6C-2；
- 下一项固定工作是 5.6B
  `validate-studio-benchmark-layered-acceptance-5-6b`，用 no-device/fake 证据闭合
  lifecycle、repository、events/recovery、browser、clean-wheel、external Package 和
  Core fairness/Studio cardinality rejection 矩阵。
