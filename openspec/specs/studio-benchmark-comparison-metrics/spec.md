# studio-benchmark-comparison-metrics Specification

## Purpose
TBD - created by archiving change implement-studio-benchmark-comparison-metrics-5-4c. Update Purpose after archive.
## Requirements
### Requirement: Experiment outcome 与 eligible denominator 必须保持正式口径
Studio Report SHALL 从已通过严格解析和 Experiment identity 校验的正式
`benchmark_experiment_report` 展示 PASS、FAIL、INVALID 和 SKIPPED 原始 counts。
每个 Agent 的 eligible denominator SHALL 只使用报告提供的 `eligibleCount`，并与
该 Agent 的 PASS/FAIL 并列展示；客户端 MUST NOT 把 INVALID/SKIPPED 加入分母、
从顶层 counts 构造未发布的 Experiment denominator，或重新计算成功率。

#### Scenario: 四类 outcome 同时存在
- **WHEN**正式报告同时包含 PASS、FAIL、INVALID 和 SKIPPED
- **THEN**页面分别展示四类 count，并只把后端给出的 per-Agent eligible denominator 标识为成功率样本

#### Scenario: 没有 eligible outcome
- **WHEN**一个 Agent 只有 INVALID 或 SKIPPED，且报告给出 `eligibleCount=0` 和 null rates
- **THEN**页面展示原始 INVALID/SKIPPED counts、零 eligible 样本和 unavailable rate，不把结果显示为 0% success

#### Scenario: 零值不是缺失
- **WHEN**报告明确给出零 PASS、非零 FAIL、`eligibleCount>0` 和 rate `0`
- **THEN**页面把 rate 展示为合法的 0%，而不是 unavailable、空白或解析错误

### Requirement: Per-Agent metrics 必须保留定义、单位与不确定性
Studio SHALL 按正式报告顺序展示每个 Agent 的 micro/macro success rate、
duration mean、median、sample variance、95% Wilson interval 和
`usageAvailableRuns`。schema `1.0` 的读者说明 SHALL 明确 micro 是 eligible
TaskRun 的总体比例、macro 是 per-Task rate 的平均、duration 仅聚合 eligible
TaskRun 的可观察阶段耗时、sample variance 使用 `ms²`、Wilson interval 适用于
eligible PASS/FAIL。UI MAY 做确定性舍入和单位格式化，但 MUST NOT 重算、补零、
clamp 或替换任一正式数值。

#### Scenario: 单个 eligible 样本
- **WHEN**一个 Agent 只有一个 eligible TaskRun，后端给出 rate、Wilson interval 和 null sample variance
- **THEN**页面展示后端 rate、interval 与样本数，并将 variance 显示为 unavailable 而不是零

#### Scenario: 合法零 duration 或 variance
- **WHEN**报告明确给出 duration 或 sample variance 为有限零值
- **THEN**页面按对应 `ms` 或 `ms²` 单位展示零，不把它与 null 合并

#### Scenario: usage 只覆盖部分样本
- **WHEN**`usageAvailableRuns` 小于 `eligibleCount`
- **THEN**页面以已提供样本数对 eligible 样本数展示 usage coverage，不外推缺失 usage

#### Scenario: metric 字段为 null
- **WHEN**任一可空 rate、duration、variance 或 interval 在合法报告中为 null
- **THEN**对应单元独立显示 unavailable，并保留同一 Agent 的其他可用正式指标

### Requirement: Pairwise comparison 必须保持 matched scope 且不得生成排名
Studio SHALL 按正式报告顺序展示每个 Agent pair 的 `paired`、matched count、
unmatched eligible count、left/right wins 和 ties。`paired=true` SHALL 只表示至少
存在一个 matched TaskInstance；当 unmatched count 非零时，UI MUST 明确这是部分可配对
证据。页面 MUST NOT 根据 wins、rates、interval overlap 或 Agent 顺序生成 winner、
leaderboard、优越性文案或隐含排名。

#### Scenario: 完全 matched comparison
- **WHEN**一个 pair 的 `paired=true`、matched count 非零且 unmatched eligible count 为零
- **THEN**页面展示 matched 样本和 wins/ties，并标识全部 eligible 比较样本已配对但不宣布 winner

#### Scenario: 部分 matched comparison
- **WHEN**一个 pair 同时具有非零 matched count 和 unmatched eligible count
- **THEN**页面同时展示两者，并将其描述为部分可配对而不是完整 paired experiment

#### Scenario: 没有 matched pair
- **WHEN**一个 comparison 的 `paired=false`、matched count 为零且只有 unmatched eligible samples
- **THEN**页面明确没有可直接配对的 TaskInstance，不把原始 Agent success rate 当作 pair wins

#### Scenario: 当前单 Agent 产品切片
- **WHEN**正式 Studio Experiment report 只有一个 Agent 且 comparisons 为空
- **THEN**页面展示没有 Agent pair 可比较的事实，不将空 comparison 解释为查询或发布失败

### Requirement: Fairness 与 significance boundary 必须始终可见且安全
Studio SHALL 展示报告中的 bounded fairness warning codes，并为已知 schema `1.0`
codes 提供不改变语义的读者说明；未知 code SHALL 以安全 code 文本保留，不猜测原因、
严重性或修复。Experiment 和每个 comparison 的 `significanceClaimed=false` SHALL
被明确展示为 descriptive-only boundary，且 MUST NOT 被颜色、图形、排序或自然语言
暗示为统计显著。

#### Scenario: 未配对 materialization warning
- **WHEN**报告包含 `benchmark.protocol.unpaired_materialization`
- **THEN**页面说明 Agent 未复用同一 TaskInstance materialization，并保留原 warning code

#### Scenario: 多 Agent 共享设备状态 warning
- **WHEN**报告包含 `benchmark.protocol.shared_device_state_across_agents`
- **THEN**页面说明 Agent 间可能共享设备状态，并保留原 warning code

#### Scenario: 未知 fairness warning
- **WHEN**报告包含客户端尚未映射但通过 bounded parser 的 warning code
- **THEN**页面安全展示原 code 并标记说明不可用，不丢弃或发明解释

#### Scenario: Agent wins 更多但无显著性声明
- **WHEN**一个 Agent 的 wins 高于另一个且 `significanceClaimed=false`
- **THEN**页面仍明确显示 no statistical significance claimed，不生成“更好”“领先”或推荐结论

### Requirement: Metric 与 comparison 大集合必须有界挂载并保留后端顺序
Studio SHALL 对合法但较大的 Agent metric 和 comparison collections 使用有界的本地
分页或等价的 bounded mounting，每页最多挂载 50 个数据行，并保留正式报告中的稳定
顺序。分页状态 SHALL 是非持久的视图状态；客户端 MUST NOT 为排名而排序、把 collection
写入 localStorage、丢弃未挂载记录或突破既有 report parser limits。

#### Scenario: 大型合法 metrics collection
- **WHEN**正式报告包含超过一页但未超过 parser 上限的 Agent metrics
- **THEN**页面只挂载当前有界页，显示总数和稳定翻页动作，并可访问后续全部记录

#### Scenario: 大型合法 comparison collection
- **WHEN**正式报告包含接近既有上限的 pairwise comparisons
- **THEN**页面不会一次挂载全部 rows，翻页后仍保持后端顺序和每条 comparison 原始事实

#### Scenario: 页面刷新
- **WHEN**用户刷新 Report route
- **THEN**metrics/comparison 从正式 report 重建并将本地页码安全恢复为默认页，不依赖持久浏览器副本

### Requirement: 5.4C 验收证据必须区分 synthetic UI 与真实执行
Studio SHALL 通过当前 single-Agent no-device report 和明确 synthetic 的 multi-Agent
report fixture 验证 metrics/comparison UI。Synthetic fixture SHALL 保持可见的
fixture Package/source identity，并覆盖 paired、partially paired、unpaired、
fairness warning、zero eligible、null、zero 和小样本状态。文档与交接 MUST NOT
把 fixture 渲染描述为当前 Studio Worker 的 multi-Agent execution、真实 Android
evidence 或统计显著性证据。

#### Scenario: Synthetic multi-Agent browser journey
- **WHEN**浏览器从明确 fixture identity 的 Experiment Report 加载两个或多个 Agent metrics 和 comparisons
- **THEN**UI 完整展示合同事实，验收记录明确这是 synthetic no-device presentation evidence

#### Scenario: 当前真实 cardinality boundary
- **WHEN**5.4C 完成时当前 Studio Experiment resource 仍声明 single Agent、single Task 和 single repeat 限制
- **THEN**产品文档继续保留该限制，不因 multi-Agent fixture 页面可渲染而宣称执行能力已扩展

