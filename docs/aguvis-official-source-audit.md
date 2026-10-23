# Aguvis 官方在线代码来源复核与本轮排除决定

核查日期：2026-10-22。用户要求统计官方公开、可运行的完整 Agent 核心流程，不能
把 ZhiXing 补写的在线循环当作官方代码。Coding Agent 沿论文、项目页、全部公开
分支、发布记录、Issue 和相关官方仓库进行只读来源核查；未运行模型、设备或远端
模型服务。本页使用 academic-research-suite 的 fact-check 流程，由 Coding Agent
在当前会话执行，没有委托其他 Agent 或联系作者。

## 决定

**Aguvis 暂不计入本轮 Mobile Agent 的有效样本数或官方核心 LOC 对比。**

这不等于“作者没有公开任何完整在线流程”：本轮找到作者在 OSWorld 中发布的
**桌面**在线实现，纠正了此前只检查 Aguvis 主仓库后作出的过宽判断。但目前未找到
官方 Android 在线执行器，现有 63 行 ZhiXing YAML 也不是 OSWorld 这套逻辑的复现。
不以桌面源码替代手机原流程，不把两条路径拼成一个声称等价的统计。

- **163 行**：已提取的官方 CLI 单步推理相关材料，不能称完整在线 Agent。
- **388 行**：163 行官方材料加 225 行我们补写的解析/循环/装配，只保留为历史实验
  基线，不能计作官方原始核心。
- **63 行 YAML**：现有 ZhiXing Android 在线适配声明，不与 163 或新发现的 OSWorld
  源码形成有效的官方完整流程 LOC 配对。
- 本轮官方完整手机流程 LOC 记为 **N/A，而不是 0**。既有实现与冻结证据保留，不删除。

机器可读决定见
eligibility.json (not bundled in the core source)。

## 核查路径与结果

| 来源 | 本轮检查内容 | 结果 |
| --- | --- | --- |
| [正式论文页面](https://proceedings.mlr.press/v267/xu25ae.html)、[论文 HTML](https://arxiv.org/html/2412.04454v2)、[项目页](https://aguvis-project.github.io/) | Software/Code 链接与在线实验说明 | 正式论文 Software 与项目页 Code 均指向 xlang-ai/aguvis；论文实验和视频不等于执行器已在该仓库发布 |
| [Aguvis 全部分支](https://github.com/xlang-ai/aguvis/branches/all) | Git 远端引用、API 分支清单、两个完整 tracked tree | 只有 main 和 inference；均为 18 个条目，serve/cli.py 均为单次预测后打印，无设备执行循环 |
| [Releases](https://github.com/xlang-ai/aguvis/releases)、Tags、PR、Issue | API 全状态清单及相关讨论 | 0 个 release、0 个 tag；2 个 PR 均已合并，涉及训练修复与单步 serve；未找到另一个 Android runner 下载入口 |
| [官方 7B 模型文件](https://huggingface.co/xlangai/Aguvis-7B-720P/tree/main) | Files 页面与模型卡 | 页面无模型卡，文件为权重、tokenizer、processor/config 等，没有在线执行脚本；未下载权重 |
| [xlang-ai/OSWorld](https://github.com/xlang-ai/OSWorld) | Aguvis agent、运行入口、共享循环与设备边界、提交历史 | **存在作者发布的桌面闭环源码**，详见下文；未验证实际运行 |
| [xlang-ai/OpenCUA](https://github.com/xlang-ai/OpenCUA)、[AndroidWorld](https://github.com/google-research/android_world) | 当前完整目录 API；读取 OpenCUA 中 Aguvis 文件 | OpenCUA 的 evaluation/agentnetbench/agent/aguvis.py 读取已有 trajectory/step 做离线预测；AndroidWorld 目录未发现 Aguvis 专用路径，未找到论文指向的另一份官方 Android 实现 |

Git `ls-remote --heads --tags` 与 API 分支清单一致：

- main：`178c4187069d8aa028aaf00f209139824c00a76f`。
- inference：`00d338480a31d0d3c75f2ae6eca354e145812207`。

分支名称 inference 不代表在线执行；其脚本仍以静态 IMAGE_PATH 调用 CLI。
本轮还检查了 [Evaluation code #4](https://github.com/xlang-ai/aguvis/issues/4)、
[#17](https://github.com/xlang-ai/aguvis/issues/17)、
[AndroidWorld #32](https://github.com/xlang-ai/aguvis/issues/32) 以及相关回复。
#4 唯一回复来自其他提问者，不能冒称作者承认未发布；#17 和 #32 当前 API 均为
0 条评论，也不能将未回复本身视为代码不存在的证明。

## 找到的官方桌面执行链

来源不只是第三方复现。OSWorld 文件历史显示论文作者 Tianbao Xie 于 2024-11-11
提交初始 Aguvis 评测，Junli Wang 于 2024-11-24 提交 “Finish Aguvis eval on OSWorld”。
作者版本固定为 `1503eb39947b7c234c7f8a164d4f868b30439981`：

1. [run_multienv_aguvis.py](https://github.com/xlang-ai/OSWorld/blob/1503eb39947b7c234c7f8a164d4f868b30439981/run_multienv_aguvis.py)
   创建 AguvisAgent 和 `DesktopEnv(os_type="Ubuntu")`，交给共享运行函数。
2. [lib_run_single.py](https://github.com/xlang-ai/OSWorld/blob/1503eb39947b7c234c7f8a164d4f868b30439981/lib_run_single.py)
   reset Agent/环境，获取观察，在 done 或 max_steps 前循环 predict → env.step，
   并接收执行后的新观察。末尾 evaluator 属于评测，不能把整个文件都当 Agent 核心计数。
3. [mm_agents/aguvis_agent.py](https://github.com/xlang-ai/OSWorld/blob/1503eb39947b7c234c7f8a164d4f868b30439981/mm_agents/aguvis_agent.py)
   包含自主预测及 GPT 规划/Aguvis 定位两条路径、提示与历史、响应解析、桌面坐标
   转换和模型服务调用。它不是此次提取的 163 行 CLI。
4. 当前环境源码可追至 `DesktopEnv.step`，执行 PyAutoGUI 命令并再次截图；WAIT、
   DONE、FAIL 控制执行或结束。其设备平台、终止协议、提示与 parser 与现有 Android
   适配不同，因此不能沿用已有 15 个自补基线场景作为这套官方源码的对照证据。

本轮另固定 OSWorld 当前 head `90a245c0c29ffd417513ea421d84afc2b33df87b`。
当前 `scripts/python/run_multienv_aguvis.py` 仍调用共享 `run_single_example`，但该
共享函数向 `reset` 传 `vm_ip`，当前 AguvisAgent.reset 只接受 `_logger=None`，两次
reset 调用均不兼容。Aguvis 模型客户端也硬编码了外部服务地址。**闭环源码存在**
与**当前版本可直接运行**必须分开；本轮没有修复这些问题或探测远端地址。

若未来另开桌面范围的统计，必须固定匹配版本，确认模型服务可取得，实际执行官方
闭环，再按调用路径抽取核心和独立统计；不能直接把整份 agent、批量调度或评测文件
相加当作已验证 LOC。该工作尚未开展。

## 证据与限制

证据目录：`output/research/aguvis-official-online-20261022/`。

- `branches.json`、`tags.json`、`releases.json`、`issues.json`、`pull_requests.json`
  与相关 `comments_*.json` 保存公开 API 返回；Issue 清单含 PR，阅读时已分开识别。
- `official-aguvis/main/`、`official-aguvis/inference/` 保存两套完整 tracked 文件；
  `official-manifest.json` 记录 commit 与逐文件 SHA256。
- `osworld-author-release/` 保存上述作者版本的入口、agent 和共享循环；`osworld/`
  保存当前版本的对应源码、环境边界和提示。只解析源码，没有 import 或执行它们。
- `osworld_aguvis_history.json` 保存作者贡献链；三个相关仓库的 tree API 均返回
  `truncated=false`。完整目录读取不等于对另外两个大型仓库逐文件审计。
- 搜索还覆盖了 Aguvis + AndroidWorld + 作者用户名等组合。未发现不能证明任何
  私有仓库、未索引页面或未来版本不存在，因此结论写为“在已检查的官方公开路径中
  未找到可配对的 Android 完整流程”。这是当前排除的依据，不是绝对未公开断言。
- Hugging Face API 直连失败，但浏览工具成功读取模型 Files 页面；OpenReview
  forum 返回 429，未作为已读材料。论文来源使用正式 PMLR 页面及 arXiv HTML。
- 没有运行权重、桌面虚拟机、Android、Benchmark 或重新统计桌面 LOC；本轮不新增
  运行通过声明。生产代码和 YAML 未修改，历史冻结结果未改写。

复核远端引用可运行：

```bash
git ls-remote --heads --tags https://github.com/xlang-ai/aguvis.git
```

本轮预期仅上述两个 head、无 tag；完整来源可由 manifest 和固定提交链接复查。
