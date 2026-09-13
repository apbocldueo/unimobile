# 外部插件闭环人工验收

以下步骤用于从开发者视角验证一个独立 Python 插件能够被安装、发现、诊断，
并通过 YAML 与 Python SDK 执行同一个 AgentGraph。本验收使用 fake Runtime，
不主动连接 Android、模型或网络。

为避免当前仓库通过 `sys.path[0]` 污染导入结果，只有构建命令指向源码仓库；
安装后的发现、CLI、测试和执行均在仓库外的工作目录运行，并禁用
`PYTHONPATH`/user site。开始前在仓库根目录记录绝对路径：

```bash
export ZHIXING_REPO_ROOT="$(pwd -P)"
export ZHIXING_ACCEPTANCE_ROOT="$(mktemp -d)"
mkdir -p \
  "$ZHIXING_ACCEPTANCE_ROOT/core-dist" \
  "$ZHIXING_ACCEPTANCE_ROOT/plugin-dist" \
  "$ZHIXING_ACCEPTANCE_ROOT/work"
```

## 1. 创建干净虚拟环境

```bash
python -m venv "$ZHIXING_ACCEPTANCE_ROOT/venv"
source "$ZHIXING_ACCEPTANCE_ROOT/venv/bin/activate"
python -m pip install --upgrade pip build
unset PYTHONPATH
export PYTHONNOUSERSITE=1
```

预期：命令提示符进入新环境，后续 `python` 和 `pip` 均来自
`$ZHIXING_ACCEPTANCE_ROOT/venv`。

## 2. 构建并安装 ZhiXing

```bash
python -m build --wheel \
  --outdir "$ZHIXING_ACCEPTANCE_ROOT/core-dist" \
  "$ZHIXING_REPO_ROOT"
cd "$ZHIXING_ACCEPTANCE_ROOT/work"
python -m pip install "$ZHIXING_ACCEPTANCE_ROOT"/core-dist/zhixing-*.whl
python -c \
  'import pathlib, sys, zhixing; assert pathlib.Path(zhixing.__file__).resolve().is_relative_to(pathlib.Path(sys.prefix).resolve()); print(zhixing.__file__)'
```

预期：wheel 构建和安装成功，打印路径位于当前虚拟环境而不是源码仓库；此时尚未
安装示例插件。

## 3. 确认未安装组件会在执行前失败

```bash
zhixing components inspect example.external:run_labeler@1.0.0
```

预期：命令非零退出并报告组件未找到，不会尝试连接设备或启动 Graph Kernel。

## 4. 安装独立插件并运行 Contract 测试

```bash
python -m pip install -e \
  "$ZHIXING_REPO_ROOT/examples/external_component_plugin[test]"
python -m pytest -q \
  "$ZHIXING_REPO_ROOT/examples/external_component_plugin/tests"
```

预期：插件以 editable distribution 安装，三个 Contract Test Kit 用例通过，
包括成功调用、Bundle 聚合和失败诊断脱敏。

## 5. 验证 metadata、解析和健康检查

```bash
zhixing components list --json
zhixing components inspect example.external:run_labeler@1.0.0 --json
zhixing components doctor --plugin-provider zhixing-example --json
```

预期：

- `list` 能看到 provider `zhixing-example`；
- `inspect` 返回身份 `example.external:run_labeler@1.0.0`、完整公开
  NodeContract 和安全配置 schema；
- `doctor` 退出码为 0，discovery、Catalog 与已执行的 Bundle Contract 检查
  健康；该示例在没有 invocation fixture 的 CLI doctor 中可显示
  `structural-only`，并明确列出 `invocation:fixture_required` 等跳过原因；
- 输出不包含 factory、组件实例、原始本地安装 URL、secret 或 traceback。

`doctor` 的成功不等同于 invocation 或算法正确。上一步插件仓库自己的 pytest
通过显式 fake input 与 `RuntimeContext` 验证 invocation。

## 6. 验证 YAML/SDK 等价与节点执行

```bash
python "$ZHIXING_REPO_ROOT/examples/external_component_plugin/sdk_example.py"
```

预期输出包含：

- YAML 和 Python SDK 的 canonical hash 相同；
- 两条 AgentGraph 都完成真实 Catalog 绑定与 fake Graph Runtime 执行；
- 两条路径的节点结果均为 `demo:hello:external-plugin-example`；
- 两条路径的外部节点均产生 `start` 和 `complete` RunEvent；
- 两条运行状态均成功。

这证明已安装组件通过真实 discovery 与 Catalog 进入通用 Graph Runtime；它不
证明真实 Android 行为或组件算法质量。

## 7. 验证 wheel 与固定 Git commit 来源

```bash
python -m build --wheel \
  --outdir "$ZHIXING_ACCEPTANCE_ROOT/plugin-dist" \
  "$ZHIXING_REPO_ROOT/examples/external_component_plugin"
python -m pip uninstall -y zhixing-example-components
python -m pip install \
  "$ZHIXING_ACCEPTANCE_ROOT"/plugin-dist/zhixing_example_components-*.whl
zhixing components list --json
zhixing components inspect example.external:run_labeler@1.0.0 --json
zhixing components doctor --plugin-provider zhixing-example
```

预期：wheel 安装后同一 provider 和组件身份仍然健康。Git 安装应在插件自己的
仓库固定 commit：

```bash
python -m pip install \
  'zhixing-example-components @ git+https://github.com/you/plugin.git@<commit>'
```

ZhiXing 不会自动下载 Git URL。安装第三方 Python 包表示信任其在当前 Python
进程执行代码，包括模块导入和组件构造；`doctor` 是默认安全的结构/兼容性诊断，
不是安全沙箱，也不证明未执行的 invocation 或算法质量。
