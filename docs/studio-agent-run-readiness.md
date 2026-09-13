# Studio Agent Run Readiness

本文记录普通 Agent 从 Studio Builder 到 Android Run 的配置闭环。它解决两个此前会在
Run 已接受后才暴露的问题：LLM 组件缺少显式 `llm_client` 依赖，以及 Studio 进程没有
SecretRef / Device Profile authority。本文只描述静态就绪度和已验证的本地配置边界；
`ready=true` 不证明设备在线、模型可调用或任务会成功。

## 当前执行流

```text
Builder draft
  → Studio compiler：校验 capability/Catalog placement/dependency 与 SecretRef 形状
  → deterministic lowering + immutable policy/capability/graph/projection closure
  → exact readiness：current policy、组件/依赖、SecretRef、Profile identity
      ├─ blocked：不创建 Run、event、artifact、Replay 或 History 记录
      └─ ready：原子接受 Run
  → Worker 再校验 snapshot/hash、绑定显式依赖与 SecretRef
  → evidence preflight → exact target → lease → AndroidGraphRuntime
```

编译和 eligibility 只检查语义，不读取 SecretRef 值。readiness 只检查受信配置的 presence，不构造组件、
不连接 ADB、不获取 lease、不创建 Run。真正的 provider 构造、设备在线/授权状态和模型调用
仍在 Worker 边界重新检查；接受后的竞态会形成持久、可审计的失败 Run。

## 在 `unimobile` 环境启动

Secret 文件是一个不超过 64 KiB 的 YAML 标量映射。下面的值只是格式占位；实际文件必须
留在版本库外，并设置仅当前用户可读的权限：

```yaml
api_key: replace-with-local-runtime-value
base_url: https://your-openai-compatible-endpoint/v1
```

Device Profile 文件是受信的服务端 JSON。浏览器只能看到 `deviceProfileId`、label 和
platform；`target.serial` 永不进入 HTTP、SQLite Run DTO、event 或 Replay：

```json
{
  "schemaVersion": 1,
  "profiles": [
    {
      "deviceProfileId": "research-android",
      "label": "Research Android",
      "platform": "android",
      "target": {"kind": "adb_serial", "serial": "replace-with-exact-adb-serial"}
    }
  ]
}
```

启动命令：

```bash
conda run -n unimobile python -m zhixing.studio serve \
  --host 127.0.0.1 \
  --port 8765 \
  --database temp/studio.sqlite3 \
  --secrets ./secrets.yaml \
  --device-profile-config ./device-profiles.json
```

Settings 的 process readiness 会列出受信文件实际加载的安全 identity，例如 `api_key` 与
`base_url`，但绝不返回对应值。Exact revision readiness 仍只检查当前 AgentGraph 真正引用的
identity；它不会依赖一个硬编码的 `openai_api_key` 别名。

`--secrets` 优先于 `ZHIXING_STUDIO_SECRETS`；`--device-profile-config` 使用既有的
`ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG` fallback。两种文件都会在服务宣布启动前严格加载。
错误只返回稳定 code 和不含路径/值的说明。Secret mapping 仅驻留当前进程内存，并由普通
Run 与 Benchmark resolver factory 共享；不会写入 SQLite 或浏览器。

React 开发服务仍从另一个终端启动：

```bash
cd studio
npm run dev -- --host 127.0.0.1
```

## Readiness 观察与 API

设置 → 运行环境是只读视图，显示 Provider availability、已知 SecretRef identity 的
configured/missing 状态和安全 Profile 目录。它不提供 credential 或 serial 输入框。

```bash
curl -sS http://127.0.0.1:8765/studio/runtime-readiness

curl -sS \
  'http://127.0.0.1:8765/studio/agents/<agentId>/revisions/<revisionId>/run-readiness?deviceProfileId=research-android'
```

第二个资源绑定 exact immutable revision、authoring/lowering policy、capability hash、
AgentGraph canonical hash、projection map 和安全 Profile identity。
诊断使用稳定 code/category/remediation key，例如：

- `graph.studio.component_dependency_required`：保存新 revision 前补齐组件依赖；
- `studio.readiness.secret_missing`：服务端配置对应 SecretRef 后刷新；
- `studio.device.profile_unknown`：重新选择当前目录中的 Profile；
- `studio.readiness.component_unavailable`：安装/启用所选 provider。

Task Run Bar 从服务端目录选择 Profile：一个自动选择，多个必须显式选择，空目录阻止提交；
只允许把安全 Profile identity 作为非语义偏好保存到 localStorage。task、metadata、SecretRef
状态、serial 和 evidence 不进入 localStorage 或 URL。同一 agent/revision/task/metadata/profile
的不确定网络重试复用 `clientRequestId`；任一语义字段变化会生成新 identity。

## Builder LLM 依赖与历史 revision 重建

正式 `ComponentSpec` 和 built-in Catalog 通过 `dependencySlots` 声明依赖。Planner、
Reasoning、Summary Memory、LLM Reflect Verifier 和 UGround Grounder 的 `llm` slot 是
required。LLM/provider 是 dependency-only，不作为画布节点。Builder Inspector 根据 exact
Catalog 编辑每个 capability implementation 的 provider/version、
model 和 `{secret_ref: "..."}`，也可一次应用到所有兼容 candidate 并单步撤销。这个批量
操作最终仍展开为每个 implementation 的普通 AgentGraph dependency，不引入 Studio-only 全局
LLM，也不改变 YAML/SDK 语义。

历史 immutable schema-1/2 revision 不会被重写；它们继续可读、可导出、可回放，但 current
policy eligibility 为 blocked，不能创建新 Run/Experiment。迁移方式不是在旧低层图上补字段，
而是从当前 schema-3 capability template 明确重建，重新选择 capability implementation、
model、API-key SecretRef 与 Base-URL SecretRef，Validate 后保存一个全新 revision。旧 revision
和引用它的 Run/Replay 保持原样；系统不自动替换 current pointer，也不进行有歧义的静默转换。

## Virtual Phone 事实边界

Virtual Phone 使用一个纯状态选择器区分 not-started、not-configured、preparing、waiting、
current/stale screenshot、early failure、authoritative offline/unauthorized、artifact missing
和 corrupt。缺少截图不再默认显示 `OFFLINE`；只有 Worker 返回明确 offline code 才能显示
设备离线。Replay 只解释持久证据，不查询当前设备状态。

## 安全边界与限制

- readiness DTO 不包含 graph body、secret value、raw serial、target key、host path 或 live client；
- SecretRef mapping 必须是严格单键稳定 identity；raw `api_key` 等值仍在文档、哈希和事件边界被拒绝；
- readiness 是瞬时静态配置结论，不能证明 provider endpoint、账户额度、设备在线或任务质量；
- 目前仍是本地单进程、普通 Run 单 worker；无远程 vault、OS Keychain、credential rotation UI；
- Profile preference 不是 AgentGraph 语义；环境配置变化不会重写 revision 或 canonical hash；
- 未授权目标、offline-after-readiness、lease contention 和模型调用失败仍会成为接受后的真实 Run failure；
- 本次未取得一个用户明确授权的普通 Run 真机 Profile/任务，因此不新增普通 Run 真实 Android 成功声明。

## 本次可复现验证

```bash
# readiness / dependency / secret contracts
/opt/miniconda3/envs/unimobile/bin/python -m pytest -q \
  tests/components/test_authoring.py \
  tests/studio/test_documents_catalog_compiler.py \
  tests/studio/test_secrets.py \
  tests/studio/test_runtime_readiness.py

# YAML / SDK / legacy / external provider / Run / Benchmark compatibility
/opt/miniconda3/envs/unimobile/bin/python -m pytest -q \
  tests/graph/test_compilers.py tests/graph/test_canonical.py \
  tests/studio/test_compiler_parity.py \
  tests/sdk/test_executable_agent.py tests/sdk/test_external_plugin_sdk.py \
  tests/runtime/test_legacy_regression.py \
  tests/runtime/test_formal_component_binding.py \
  tests/runtime/test_external_catalog_binding.py \
  tests/runtime/test_android_graph_runtime.py \
  tests/catalog/test_external_plugins.py \
  examples/external_component_plugin/tests/test_contracts.py \
  tests/studio/test_run_models_repository.py \
  tests/studio/test_run_execution.py tests/studio/test_run_replay_http.py \
  tests/studio/test_benchmark_execution_worker.py \
  tests/benchmark/test_runtime_boundaries.py

# clean-wheel / external Package / explicit fake LLM acceptance
/opt/miniconda3/envs/unimobile/bin/python -m pytest -q \
  tests/packaging/test_external_plugin_distribution.py \
  tests/packaging/test_isolated_install.py \
  tests/packaging/test_studio_benchmark_layered_acceptance_install.py

cd studio
npm run typecheck
npm run lint
npm test -- --reporter=dot
npm run build
```

本次 focused readiness/compiler/secret/identity 回归为 `49 passed`，完整 YAML/SDK/legacy/
external-provider/Run/Replay/Benchmark 兼容矩阵为 `131 passed`。前端完整结果为
`101 files / 434 tests passed`，typecheck、lint 和 production build 通过。Vite 仍提示
主 JS chunk 超过 500 KiB；这是性能优化项，不影响本次运行就绪合同。

packaging 独立结果为基础 clean-install/external-plugin `3 passed`，installed layered
acceptance `1 passed`。后者从 clean wheel 加载显式 LLM dependency，通过 exact fake Catalog
与进程注入的 deterministic fake LLM 完成 fake-device screenshot、terminal action、成功
TaskRun、managed publication 和 native Replay；ADB discovery、真实设备构造、外网、模型
解析、Secret 解析和仓库源码 fallback 六个 canary 均为零。该证据属于 Benchmark 的
contract fixture，不替代普通 Run 真机证据。

无设备浏览器验收先以零 Profile 启动，页面显示“尚未开始运行”和明确的 Profile 缺失，
Run 保持 disabled，没有把缺截图解释成 `OFFLINE`。当前 schema-3 浏览器旅程从正式能力模板
创建 Agent、进入 Builder 并 Validate；缺少运行环境时 Run 仍保持 blocked。Palette、固定
Input/Output、Inspector implementation/dependency 和画布标签均从实际后端合同读取；不再用
旧 schema-2 图或特定历史 Run ID 充当当前准入证据。fake Run/Replay 因果证据与本轮浏览器
结果见 [Studio Mobile Agent 能力组件创作](studio-agent-capability-authoring.md)。
