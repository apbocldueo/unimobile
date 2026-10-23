# Studio 本地启动

`run_studio.py` 是仓库开发入口，使用当前 Python 环境运行后端，并使用本地 Node/Vite
运行前端。它不安装依赖，不自动选择设备，不调用模型，也不创建或运行 Agent 任务。

## 首次安装与日常使用

项目使用 `unimobile` conda 环境。Python 需要 3.10+，Node.js 需要 22.12+。
在项目根目录运行：

```bash
conda activate unimobile
python -m pip install -e ".[openai,dev]"
npm --prefix studio ci
```

安装只需首次或依赖变化时进行。日常启动：

```bash
conda activate unimobile
python run_studio.py
```

启动器先检查配置、依赖和端口，再启动 API 与前端。两者可访问后，自动打开
`http://127.0.0.1:5173/`。按一次 Ctrl+C 关闭本次启动的两个服务及其子进程。
任何一个服务意外退出，启动器也会关闭另一个并返回失败。

支持从其他目录使用脚本的绝对路径启动；工作区始终固定为脚本所在的项目根目录。
默认数据库沿用该工作区已有身份，不切换成新的 `temp/studio.sqlite3`。
之前若从另一个工作目录启动后端，那个目录对应的数据库不会自动迁移或合并。

## 自动加载与明确覆盖

密钥路径的优先级：

1. `--secrets`；
2. `ZHIXING_STUDIO_SECRETS` 环境变量；
3. 项目根目录 `secrets.local.yaml`，不存在时使用 `secrets.yaml`。

设备路径的优先级：

1. `--device-profile-config`；
2. `ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG` 环境变量；
3. 项目根目录下的 `studio/device-profiles.json`。

相对路径均相对于项目根目录。选择了一个无效文件时直接报错，不悄悄切换到其他文件。
启动器只打印配置是否加载，不打印密钥值或设备 serial，不修改配置文件。

首次配置可参照 `secrets.example.yaml` 与 `examples/device-profiles.example.json`。
密钥文件的项名必须匹配 Agent 引用；设备配置里的 serial 必须对应实际目标设备。
示例内容不能直接当作已经验证的本地设备或模型配置。本地密钥和设备文件不提交 Git。
缺少配置时仍可进入工作台编辑，实际 Run 继续通过已有的 exact revision 检查。

## 可选命令

```bash
# 检查配置、依赖、端口；不启动服务，不打开浏览器，不创建数据库
python run_studio.py --check

# 启动但不自动打开浏览器
python run_studio.py --no-browser

# 使用另一组端口（前端代理会同步指向该后端）
python run_studio.py --backend-port 8876 --frontend-port 5273

# 显式使用独立数据库或其他配置
python run_studio.py --database temp/local-test.sqlite3 \
  --secrets ./secrets.yaml --device-profile-config ./studio/device-profiles.json
```

端口已占用时不会终止或复用旧进程，也不会让 Vite 静默换端口。请先在旧服务终端按
Ctrl+C，或为新实例明确指定另一组端口与独立数据库。同一个数据库不能由两个可执行
后端同时拥有。启动检查与实际监听之间仍有竞态，子进程失败时会统一清理。

启动器只对本次子进程设置 `VITE_STUDIO_API_BASE=/zhixing-studio` 和匹配的代理目标，
避免旧 `.env` 指向其他后端；不修改 `.env` 或父进程环境。端口由启动器参数控制，
不沿用独立后端的 `ZHIXING_STUDIO_PORT/HOST`，监听地址固定为 loopback。

## 页面提示与实际连接

Builder 显示“未加载设备配置”表示后端没有加载 Profile，不代表模拟器没开。
“运行配置已就绪”只表示静态检查通过；Settings 明确显示设备在线状态尚未检查、模型
接口尚未测试。本页刷新只读取配置，不调用模型、不连接设备。实际连接仍在任务执行时
验证；运行前不会因此得到虚假的在线或模型可用保证。

配置文件修改后需要重启服务并刷新页面。页面保持只读，没有新增密钥编辑、设备发现、
连接测试或自动切换设备功能。

## 保留的独立后端方式

```bash
python -m zhixing.studio serve \
  --secrets ./secrets.yaml --device-profile-config ./studio/device-profiles.json
# run_studio.py serve ... 和 run_studio.py replay-import ... 仍转发原后端命令
```

显式后端子命令保留原有参数、工作目录和路径语义，不应用便捷启动器的默认文件查找。
仓库启动器不作为 wheel CLI 的新增合同，也不是生产服务管理器。

## 验证

2026-09-28 在 macOS、`unimobile` Python 环境及 Node.js 24.15.0 验证：

```bash
ZHIXING_TEST_LOCAL_STARTUP=1 conda run -n unimobile python -m pytest \
  tests/studio/test_local_launcher.py \
  tests/studio/test_local_launcher_integration.py \
  tests/studio/test_runtime_readiness.py \
  tests/studio/test_secrets.py tests/studio/test_device_profiles.py -q

cd studio
npm test -- src/entities/runtime-readiness/model/remediation.test.ts \
  src/features/settings/SettingsPage.test.tsx \
  src/features/agent-builder/ui/BuilderToolbar.test.tsx
npm run typecheck
npm run lint
node node_modules/vite/bin/vite.js build --outDir /private/tmp/zhixing-studio-startup-build
```

- 后端与启动器：52 passed。包括配置优先级、私密值不输出、缺依赖提示、旧命令转发、
  固定工作区、部分启动失败、真实进程组及顽固后代清理、无关进程不受影响。
- 实际 API/Vite：使用临时数据库、虚拟设备配置和惰性测试密钥，验证自定义端口、从其他
  目录启动、前端代理覆盖旧环境值、重复启动拒绝、SIGINT/SIGTERM 关闭两端、退出后端口
  可立即重新检查。不连接实际设备或模型，不访问现有数据库。
- 前端：3 个文件 / 11 项测试通过；typecheck、lint 与隔离目录生产构建通过。构建仍报告
  主应用 chunk 超过 700 kB 的提示；本变更未做无关的拆包重构。
- 本机现有配置通过 `--check --backend-port 19876 --frontend-port 15173` 自动加载检查。
- OpenSpec `simplify-studio-local-startup` strict validation 通过。

浏览器打开调用由单元测试覆盖，真实集成使用 `--no-browser`，未做新的桌面浏览器视觉
验收。Windows 清理分支未实测。上述证据不证明设备在线、模型可用或 Agent 任务成功。
