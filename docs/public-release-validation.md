# 开源发布验证记录（2026-09-05）

本次从研发工作区构造独立的公开源码副本，验证白名单是否包含运行、安装、测试及
文档所需内容。研发工作区已有的未提交功能改动保留；独立验证仓库的提交由自动化
创建，仅用于固定审阅快照，不代表项目版本已发布。

## 已验证事实

- 研发工作区无设备后端：947 项通过。
- 公开副本无设备后端：940 项通过，5 项明确跳过。与研发工作区相比另少两个重复
  YAML 示例产生的参数化用例；没有把测试失败静默当作通过。
- Studio：117 个测试文件、505 项测试通过；typecheck、lint、production build 通过。
  依赖通过公开副本自己的 `npm ci` 安装，没有复制研发目录的 node_modules。
- wheel 和 sdist 构建成功，`twine check` 均通过。
- 初次完整安装回归中 29 项通过；最后一项发现旧 schema-2 fixture 以及 fake Catalog
  未传入执行组合的问题。更新为 schema 3 并传递同一份 Catalog 后，该项独立安装、
  Experiment、报告、Replay、GET/HEAD 完整链路通过，六个禁止副作用计数均为零。
- 两个 README 无设备示例成功运行。
- 公开目录 Markdown 本地链接和清单成员大小/SHA-256 检查通过。
- 发布工具的 13 项合同测试及 OpenSpec strict 校验通过。

## 修复的边界

发布器默认只读取 Git 已跟踪文件；未提交新文件需显式选择预览模式，且清单始终
标为预览。正常发行只接受干净快照。目录白名单与排除规则存放于
`release/public-manifest.json`，导出后的逐文件清单为 `RELEASE-MANIFEST.json`。
公开 `.gitignore` 和它的源模板同时保留，使正式仓库可以继续使用同一发布工具。

发布器拒绝不安全路径、私密文件名、父目录符号链接、输出冲突、超限文件和常见
密钥形状，并核对复制后的字节摘要。对固定的测试用假密钥只做精确值豁免；扫描
不能证明任意格式的秘密都已被发现。

Run HTTP 测试原先把 terminal/replay 可见误当成最终事件已提交。现在等待正式
`run.terminal` 事件后再检查取消幂等性，未修改生产运行时和取消合同。

## 发行限制

五项跳过检查涉及未随公开源码分发的 AndroidWorld/AppAgent Package 素材；通用
Benchmark CLI 测试使用测试内生成的小型 Package，仍然执行。上游素材授权记录
未完成，不能把历史任务数量或验证文档解释为发行包已经附带这些数据。

仍被使用的 `zhixing/engine` 和 Studio 兼容代码继续保留。可选本地
`experiment.human_review_output` 不随发行，原生报告和 Replay 不依赖它。本次没有
新增真实 Android 执行证明，没有扩大 Studio Worker 的 1 Agent × 1 Task × 1 repeat
边界，也没有执行远程推送、切换默认分支或撤销账户凭据。

## 复验

按 [发布指南](public-release.md) 构造副本，在副本根目录安装 `.[dev]`，执行无设备
后端和独立 packaging 套件，再于 Studio 运行 test/typecheck/lint/build。公开快照的
验收应同时记录通过数、跳过数、源提交和逐文件摘要；凭据若进入过旧历史，仍需
由持有人在服务商处撤销或轮换。
