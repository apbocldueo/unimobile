# 第三方组件：作者 API、分发与自动发现

ZhiXing 提供一套不依赖全局注册副作用的正式组件作者 API，以及基于 Python
Entry Point 的显式发现流程。第三方项目可以作为 editable 项目、wheel、PyPI
包或 Git URL 安装；安装完成后都通过相同的 distribution metadata 进入目录，
不需要修改 ZhiXing 的核心注册表。

当前边界如下：

```text
作者实现
  ├─ 正式类：BasePerception / BasePlanner / ... / BaseVerifier
  └─ 轻量函数或类：@component(...)
             │
             ▼
       immutable ComponentSpec
             │
       versioned ComponentBundle
             │
  zhixing.components Entry Point
             │（仅在显式 discover/load 时）
             ▼
       immutable ComponentCatalog
             │
       definition/config/type preflight
             │
             ▼
        CatalogComponentResolver
             │
             ▼
        AgentGraph Runtime
```

`import zhixing` 和 `import zhixing.components` 不会枚举或加载 Entry Point。
metadata-only 列表也不会导入 provider；只有 SDK/CLI 的高层运行入口或用户显式
调用 `discover_components()` 时，才会加载被策略选中的 provider。

外部 provider 是运行在宿主 Python 进程中的可信代码。加载 provider 会执行其
模块导入代码，Contract 检查还可能构造组件；ZhiXing 不为这些过程提供进程沙箱、
网络隔离或设备权限隔离。因此，只应安装和选择可信 provider，并在独立虚拟环境
中固定依赖版本。下文所说的“默认安全”只描述 ZhiXing 自身不会主动注入或调用
Device、LLM、网络等能力，不代表框架能够约束第三方 Python 代码的任意副作用。

## 1. 正式 ABC 组件

六类核心 AgentGraph 角色是 Perception、Planner、Reasoning、Memory、
ActionExecutor 和 Verifier。正式可复用组件建议继承对应基类：

```python
from zhixing.components import (
    BaseVerifier,
    RuntimeContext,
    VerifierInput,
    VerifierResult,
)


class TaskVerifier(BaseVerifier):
    """Verify one task without hidden runtime dependencies."""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Return a typed verification result.

        Args:
            input (VerifierInput): Current task and execution evidence.
            runtime (RuntimeContext): Run-scoped services and state.

        Raises:
            None.

        Returns:
            VerifierResult: Verification decision.
        """
        return VerifierResult(
            is_success=bool(input.screenshot_after),
            metadata={"run_id": runtime.run_id},
        )
```

然后用准确的内置 Contract 创建不可变定义。`ComponentSpec` 的安全视图不会
输出 implementation、factory、secret 或 live service：

```python
from zhixing.components import (
    ComponentCategory,
    ComponentRole,
    ComponentSpec,
)
from zhixing.graph import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    GraphRole,
    contract_ref_for_role,
)

contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(
    contract_ref_for_role(GraphRole.VERIFIER)
)
assert contract is not None

TASK_VERIFIER = ComponentSpec(
    namespace="acme",
    name="task_verifier",
    version="1.0.0",
    contract=contract,
    implementation=TaskVerifier,
    category=ComponentCategory.CORE_AGENT,
    role=ComponentRole.VERIFIER,
    zhixing_compatibility=">=0.1,<0.2",
)
```

## 2. 轻量 decorated callable

不需要构造类时，可以使用 `@component`。装饰器保留原函数可调用性，只附加
同一种 `ComponentSpec`，不会调用旧 `PluginRegistry.register()`：

```python
from zhixing.components import (
    ComponentRole,
    RuntimeContext,
    VerifierInput,
    VerifierResult,
    component,
)


@component(
    namespace="acme",
    name="always_pass",
    version="1.0.0",
    role=ComponentRole.VERIFIER,
)
def always_pass(
    input: VerifierInput,
    runtime: RuntimeContext,
) -> VerifierResult:
    """Return a deterministic typed result for demonstration."""
    del input, runtime
    return VerifierResult(is_success=True)


ALWAYS_PASS = always_pass.__zhixing_component_spec__
```

正式 V1 组件必须使用同步且完整标注的
`invoke(input, runtime) -> output`；async、generator、缺少类型或错误角色
会在构造设备和执行任务之前失败。没有 `ComponentSpec` 的 typed object 仍可
作为本地 SDK 对象显式注入，但它属于兼容的 structural-local 路径，不具备正式
组件的严格作者保证。

## 3. 配置模型和显式依赖

组件参数使用 Pydantic 模型校验。只有验证后的普通字段会作为构造参数；LLM、
Device、secret 和其他 live dependency 应由 resolver 独立注入，不能写入
`safe_metadata()`：

```python
from pydantic import BaseModel, ConfigDict


class VerifierConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    threshold: float = 0.8
```

将 `VerifierConfig` 传给 `ComponentSpec(config_model=VerifierConfig)` 后，
未知字段或类型错误会在实现构造函数运行前产生
`component.config_invalid`。

## 4. 自定义 NodeContract 与运行时类型

Tool 等扩展节点不应扩张六类核心角色枚举。它们使用显式 NodeContract；所有
非内置且非 `any` 的逻辑类型必须绑定到确定的 Python DTO：

```python
from dataclasses import dataclass

from zhixing.components import RuntimeContext, component
from zhixing.graph import (
    ContractPort,
    InvocationAdapterKind,
    NodeContract,
    NodeContractRef,
    PortDirection,
)


@dataclass(frozen=True)
class SearchQuery:
    text: str


contract = NodeContract(
    ref=NodeContractRef(id="acme.search", version="1.0"),
    ports=(
        ContractPort(
            id="input",
            direction=PortDirection.INPUT,
            data_types=("acme.search_query",),
            required=True,
        ),
        ContractPort(
            id="result",
            direction=PortDirection.OUTPUT,
            data_types=("text",),
        ),
    ),
    adapter=InvocationAdapterKind.TYPED_INVOKE,
)


@component(
    namespace="acme",
    name="search",
    contract=contract,
    input_type=SearchQuery,
    output_type=str,
    runtime_types={"acme.search_query": SearchQuery},
)
def search(input: SearchQuery, runtime: RuntimeContext) -> str:
    """Return a local fixture result."""
    del runtime
    return input.text
```

相同 logical type ID 绑定到不同 Python 类型会确定性失败。类型绑定只影响当前
进程的调用边界，不进入 AgentGraph canonical hash。

## 5. Contract Test Kit

第三方仓库可以在自己的 pytest 中直接运行公共检查：

```python
from zhixing.components import assert_component_contract


def test_component_contract() -> None:
    result = assert_component_contract(TASK_VERIFIER)
    assert "definition" in result.checks
    assert "invocation" in result.checks
```

`check_component_contract()` 返回结构化结果而不抛断言，适合输出诊断；其检查
阶段包括 definition、construction、invocation 和 instance isolation。六类
核心角色有最小 DTO 与 fake `RuntimeContext` fixture。

默认安全策略不会由 Test Kit 主动调用 ActionExecutor、Device、LLM 等敏感角色，
也不会主动向组件提供真实网络、模型或 ADB 能力。相应 invocation 会以
`invocation:side_effect_not_authorized` 等原因记录在 `skipped` 中，而不是伪装
成已经验证。测试这些边界时必须显式设置 `allow_side_effects=True`，并提供受控
input、fake dependency 和 fake `RuntimeContext`。该授权只控制 Test Kit 是否
发起调用，不会替作者判断 fake 是否真实无副作用，也不能阻止第三方模块导入或
构造函数自行访问外部资源。

插件仓库应同时检查完整 Bundle，避免一个失败组件遮蔽同一 provider 中的其他
组件：

```python
from zhixing.components import assert_component_bundle


def test_bundle_contracts() -> None:
    result = assert_component_bundle(bundle, provider_id="acme-mobile")
    assert result.passed
    assert len(result.components) == len(bundle.components)
```

`check_component_bundle()` 按稳定组件身份检查所有成员，不会在第一个失败处提前
终止。需要受控副作用 fixture 时，可以用完整组件身份建立 mapping；未命中的
fixture 会作为安全诊断返回，而不会把 factory、实例、secret 或 traceback 写入
结果。

## 6. 声明 ComponentBundle

一个 provider 的 Entry Point 必须直接导出不可变 `ComponentBundle`，不能导出
注册函数、组件实例或任意字典：

```python
from zhixing.components import ComponentBundle

bundle = ComponentBundle(
    components=(TASK_VERIFIER, ALWAYS_PASS),
    schema_version="1",
)
```

Bundle 必须非空，成员必须是通过正式作者模型校验的 `ComponentSpec`，同一
Bundle 内不得重复 `namespace:name@version`。加载 Bundle 不会构造组件，也不会
向 provider 注入 RuntimeContext、Device、LLM、Secret 或 Benchmark runtime。

## 7. 建立独立 distribution

推荐的最小结构如下。组件仓库与 ZhiXing 仓库相互独立：

```text
acme-zhixing-components/
├── pyproject.toml
├── src/
│   └── acme_zhixing_components/
│       └── __init__.py       # 导出 bundle
└── tests/
    └── test_contracts.py     # Contract Test Kit
```

`pyproject.toml` 声明固定 group 和稳定 provider ID：

```toml
[build-system]
requires = ["hatchling>=1.26,<2"]
build-backend = "hatchling.build"

[project]
name = "acme-zhixing-components"
version = "1.2.0"
requires-python = ">=3.10"
dependencies = ["zhixing>=0.1,<0.2"]

[project.entry-points."zhixing.components"]
acme-mobile = "acme_zhixing_components:bundle"
```

provider ID（例：`acme-mobile`）标识一个已安装 provider；组件的运行身份仍然是
`namespace:name@version`。provider ID 重复、组件身份冲突、外部组件遮蔽内置
身份都会在绑定设备之前确定性失败。

## 8. 安装方式

以下方式最终都安装为标准 Python distribution，因此发现协议相同：

```bash
# 本地开发；修改源码后立即生效
python -m pip install -e ../acme-zhixing-components

# 本地或 CI 中固定 wheel
python -m pip install dist/acme_zhixing_components-1.2.0-py3-none-any.whl

# PyPI / 私有 index
python -m pip install 'acme-zhixing-components==1.2.0'

# Git 仓库；研究复现应固定 commit，而不是浮动分支
python -m pip install \
  'acme-zhixing-components @ git+https://github.com/acme/components.git@<commit>'
```

ZhiXing 只读取 distribution 名称、版本和清理后的 `direct_url.json` 类别。公开
provenance 不包含本地路径、原始 URL 或 URL 凭据；Git 来源可报告 VCS 类型、
requested revision 和 commit ID。wheel/editable/Git 来源差异不会进入 AgentGraph
canonical hash。

## 9. 发现、查看与加载

CLI 默认只看 metadata，不调用 `EntryPoint.load()`：

```bash
zhixing components list
zhixing components list --json

# 明确加载 Bundle，显示安全组件 metadata 和逐 provider 失败
zhixing components list --load --json

# 解析一个精确组件并显示完整的公开 NodeContract 与安全 metadata
zhixing components inspect acme.mobile:task_verifier@1.2.0

# 加载所选 provider、构建 Catalog 并运行默认安全的 Bundle Contract 检查
zhixing components doctor --plugin-provider acme-mobile
zhixing components doctor --plugin-provider acme-mobile --json
```

`inspect` 只接受 `namespace:name[@version]`，不会把路径、Git URL 或包名当成
安装请求；省略版本仅在 Catalog 中只有一个候选版本时成功。公开 metadata 包含
NodeContract 的端口、adapter、副作用和执行特性声明，但不包含 executable
factory 或 live component。

`doctor` 是默认安全的结构与兼容性健康检查，不是组件算法验收。provider 的健康
状态分为：

- `verified`：默认检查中没有失败或跳过项；
- `structural-only`：definition、construction 等检查通过，但 invocation 因缺少
  fixture 或未授权敏感副作用而跳过；
- `contract-failed`：至少一个 Contract 检查失败。

文本和 JSON 输出都会给出 `skipped` 原因与 `skipped_count`。退出码 `0` 表示
discovery/catalog 没有失败且已执行的 Contract 检查通过，即使状态可能是
`structural-only`；`2` 表示 provider/discovery/catalog 失败，`3` 表示成功发现
但已执行的 Contract 检查失败。两条命令都只输出有界、安全的 metadata 和诊断，
不输出原始 traceback、凭据 URL、factory 或 live component。

Python 中可以将枚举与加载拆开：

```python
from zhixing.catalog import (
    enumerate_component_plugins,
    load_component_plugins,
)

candidates = enumerate_component_plugins()  # metadata-only
environment = load_component_plugins(
    candidates,
    allowlist=("acme-mobile",),
    denylist=("untrusted-provider",),
)
print(environment.report.to_safe_dict())
print(environment.catalog.to_safe_dict())
```

denylist 优先于 allowlist，未选 provider 不会被导入。选中 provider 独立加载；
某个 provider 的 ImportError、缺失可选依赖、错误返回类型或非法 Bundle 会进入
`DiscoveryReport.failures`，不会遮蔽成功 provider。成功 Bundle 之间的全局身份、
Contract 或 logical runtime type 冲突则会拒绝建立 Catalog，避免结果随安装顺序
变化。

## 10. SDK、YAML 与显式绑定

高层 YAML 入口在用户真正调用时显式发现已安装 provider：

```python
from zhixing import load_agent

agent = load_agent(
    "agent.yaml",
    plugin_allowlist=("acme-mobile",),
    plugin_denylist=("disabled-provider",),
)
result = agent.run("拍一张照片")
```

完全禁用 installed discovery：

```python
agent = load_agent("agent.yaml", discover_external=False)
```

CLI 提供同一控制：

```bash
zhixing run --agent agent.yaml --instruction '拍一张照片' \
  --plugin-provider acme-mobile \
  --disable-plugin-provider disabled-provider

zhixing run --agent agent.yaml --instruction '只使用内置组件' \
  --no-external-plugins
```

低层 `compile_agent(graph)` 不扫描安装环境。需要 Python SDK 使用外部组件时，
先显式传入 discovery environment：

```python
from zhixing import compile_agent
from zhixing.catalog import discover_components

environment = discover_components(allowlist=("acme-mobile",))
agent = compile_agent(graph, component_environment=environment)
```

`ExecutableAgent` 保存不可变 Catalog/Contract catalog 和 resolver factory；每次
run 都创建新 resolver 并重新构造组件实例。Graph 中的 `params` 先经 Pydantic
校验，`SecretRef` 与 live dependency 由运行期 provider 解析，不写入图、事件、
轨迹或 provenance。

原有显式 mapping 仍然可用：

正式定义目前可以显式交给 Runtime：

```python
plan = bind_execution_plan(
    graph,
    {
        "task_verifier": TASK_VERIFIER,
        "search": search,
    },
    contract_catalog=custom_contract_catalog,
)
```

绑定顺序是：定义预检 → 参数校验 → run-scoped 构造 → Runtime 调用 → 实际
输出端口与 Python 类型检查。正式定义失败后不会降级到 duck typing 或 Legacy
Adapter；旧组件和没有 ComponentSpec 的显式本地对象仍保留各自兼容路径。

## 11. 版本、冲突和信任边界

- 指定 `namespace:name@version` 时必须精确存在。
- 省略 version 仅在目录中只有一个可用版本时允许；多版本会要求显式固定。
- provider ID、组件 identity、NodeContract 或 logical runtime type 冲突不会按
  “后安装覆盖先安装”处理。
- 安装 Python 插件等同于允许其在当前 Python 进程执行代码。allowlist/denylist
  是选择机制，不是沙箱；只安装和加载可信包，并在独立虚拟环境中固定版本。
- `components doctor` 不创建权限边界。它只保证 ZhiXing 不主动向默认检查注入
  真实 Device、LLM 或网络服务；provider 的 import 和组件构造仍属于可信代码执行。
- discovery 只负责声明和目录，不替用户安装/卸载包，也不提供 marketplace。

## 已知限制

- Test Kit 能验证接口、已执行 fixture 的行为和实例隔离，不能证明算法在真实
  任务上正确；`skipped` 的 invocation 也不能算作行为验证。
- `allow_side_effects=True` 必须由作者配合真正的 fake service 使用。
- 当前只支持同步单次调用，不支持 async 或 streaming component。
- provider 在当前 Python 进程中加载；本阶段没有进程沙箱、签名验证或权限隔离。
- Git URL 是 pip 的安装来源，不是 ZhiXing 自己实现的 Git 下载器。
- Studio 的组件面板与 marketplace 不在本阶段范围内。

## 可运行的正式样例

[`examples/external_component_plugin`](../examples/external_component_plugin/)
是唯一受支持的独立插件样例，可直接复制到单独 Git 仓库。它包含：

- 独立 `pyproject.toml`、`src` 布局和固定 `zhixing.components` Entry Point；
- 使用配置模型和 `RuntimeContext` 的 `RunLabeler` 组件；
- 单组件与 Bundle Contract Test Kit；
- canonical hash 相同的 YAML 与 Python SDK AgentGraph；
- 两种定义分别通过真实 installed metadata 发现、Catalog 绑定，并在 fake
  Runtime 中执行，比较结果与节点事件。

完整的干净环境人工验收命令和预期观察见
[`docs/external-plugin-acceptance.md`](external-plugin-acceptance.md)。
