# 在 Studio 找到下一步

[English](studio-next-steps.md)

先从正式示例创建 Agent，修改一项能力，校验并保存 revision。准备执行时再配置模型与
Android 目标。仅创建、校验定义不需要手机或密钥。

## 打开一个可用示例

在仓库根目录使用 `unimobile` 环境启动后端：

```bash
conda run -n unimobile --no-capture-output python -m zhixing.studio serve
```

在另一个终端启动前端：

```bash
cd studio
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

打开 `http://127.0.0.1:5173/`，保持两个进程运行。使用预期的前端来源；任意更换端口
可能无法通过后端 origin 检查。端口被占用时，先确认已有服务，不要盲目停止。

点击 **从示例开始**，填写 Agent 名称并从正式模板创建。**创建空白 Agent** 保留为
自行搭建的入口。返回用户可以打开最近 Agent；历史 revision 可能因当前策略只能读取，
系统不会静默迁移。

左侧能力库表示可添加的能力，中间画布才是当前 Agent 实际使用的实例。点击添加时节点
放在可见画布，也可以拖动到指定位置。选择节点后，在右侧检查精确实现与依赖。
系统 Input/Output 边界不是可随意删除的普通能力。

## 处理编辑和校验问题

点击 **Validate**，先读问题和下一步建议，需要时展开 **Technical details** 查看代码与
严重程度。只有位置可信才显示 **Show object**。有些错误只有文档级位置，界面说明没有
字段精度时，不要认为已经定位到具体字段。

缺少 LLM 依赖时，检查该能力的依赖配置。LLM 是依赖，不是额外画布节点。Provider/version、
model 和 SecretRef 的精确字段应遵循当前 Catalog 实现的合同，不要通过添加隐藏运行时或
流程控制节点来修复。

格式错误的 JSON 留在编辑器中。先修正括号、引号和逗号，再 Validate、Save 或 Export；
这些操作不能静默使用旧值。导航保护保留未完成输入。查看错误不会保存或修改图。
修改后需重新校验，旧结果不能代表新草稿。

点击 **Save revision** 后等待确认。保存成功的未完成图仍可能无效。如果与其他标签页
发生保存冲突，保留本地工作，再显式重新加载或 Save As，不要假设远端已被覆盖。
保存后再刷新，或明确接受未保存修改提示。

## 将凭证配置在服务端，不放进图

图中只包含 `{"secret_ref":"api_key"}`、`{"secret_ref":"base_url"}` 等标识。
服务端操作者在 Git 外的私有 YAML 标量映射中保存对应值：

```yaml
api_key: replace-with-your-local-value
base_url: https://your-openai-compatible-endpoint/v1
```

这里是占位内容，不是可用凭证。限制文件权限，只允许所属用户读取。真实值不得进入
图 JSON/YAML、截图、issue、URL 或浏览器存储。Provider 所需包必须安装在运行 Studio 的
环境中；查看 Help 不会自动安装任何内容。

## 准备明确的设备 Profile

启动预期模拟器或授权测试设备，由服务端操作者使用 `adb devices` 确认精确目标。
多设备环境不要随机选择。私有服务端 JSON 文件格式如下：

```json
{
  "schemaVersion": 1,
  "profiles": [{
    "deviceProfileId": "research-android",
    "label": "Research Android",
    "platform": "android",
    "target": {"kind": "adb_serial", "serial": "replace-with-exact-target"}
  }]
}
```

重启前先停止属于自己的开发后端，不要中断正在执行的实验。将下列占位路径替换为
预期的私有文件：

```bash
conda run -n unimobile --no-capture-output python -m zhixing.studio serve \
  --host 127.0.0.1 --port 8765 \
  --secrets /absolute/private/path/secrets.yaml \
  --device-profile-config /absolute/private/path/device-profiles.json
```

打开 **Settings → 运行环境** 并刷新。页面只读，显示 Provider 可用性、SecretRef 标识和
安全 Profile ID，不显示凭证值或原始 ADB serial。列表为空、请求失败、检查进行中是不同
状态。按照准备清单处理配置后重试查询。服务端完整合同见[运行准备](studio-agent-run-readiness.md)。

## 明确选择普通运行或 Benchmark

普通 **Run**：先保存符合当前策略的有效 revision，再选择安全 Profile、填写任务。
**Recheck configuration only** 不创建 Run；只有显式运行动作才会经过既有权威检查提交。
普通 Run **不需要** Benchmark Package。

**Benchmark Experiment**：在已有 Composer 选择可用 Catalog Package、已保存 Agent
revision 和受支持 Profile/Protocol。创建前检查预览。无匹配时清除筛选，查询失败时重试。
确实为空时，通过 Benchmark authoring 创建或导入草稿，完成校验、冻结并显式发布。
草稿不是已发布的 Catalog 条目。Studio Worker 仍限制为一个 Agent × 一个 Task × 一次
repeat；这与 Core 多基数能力是不同边界。

| 观察到的状态 | 实际能证明什么 |
| --- | --- |
| Graph valid | 定义通过编译检查。 |
| Revision saved | 对应文档快照已持久化。 |
| Provider/profile configured | 静态配置存在，不是在线连接证据。 |
| Exact revision ready | 检查当时，该 revision 的静态前提通过。 |
| Run accepted | 持久请求被接受，不代表任务成功。 |
| 终态结果与证据 | 实际范围内记录下来的执行结果。 |

Readiness 通过后仍可能发生设备断连、目标竞争、模型访问失败或任务失败。检查真实
Run/Experiment 状态及证据；Replay 解释历史记录，不代表设备当前状态。

## 帮助与发布边界

打开 **Help** 或上下文准备链接。默认英文，切换到简体中文后保留主题并提供完整翻译。
外链指向经过核验的已发布文章，并标明其真实范围。例如密钥专题介绍 CLI 绑定，本地说明
补充 Studio 服务端配置。站点现有截图可能来自较早版本。本指南和前端修改没有发布新的
GitHub Pages 内容。
