# Ordinary Run experience acceptance — work in progress

This is the execution record for `validate-studio-run-experience`, not a
completion claim. The original baseline below predates the later emulator
journey recorded in the dated section. The separate Builder layout change
remains independently tracked.

## 2026-09-19 actual Android acceptance slice

The user supplied an already-running Android emulator. The existing Studio
backend was running on `127.0.0.1:8765`; the Vite frontend was started on
`127.0.0.1:5173` for this browser journey. The target was the isolated test
Agent `UX 0917 — 模板搭建`, so no production Agent was modified.

The browser journey completed the following path:

```text
Agent design → valid saved revision → Run preparation → ordinary task
→ live execution map / Virtual Phone / Run Inspector
→ Android Settings screenshot and start_app evidence
→ terminal success → native same-Run Replay → Agent run history
```

Observed Run: `run-8970fc018286477e84b762bf033ae919`.

- lifecycle: `terminal`
- Agent result: `success`
- kernel status: `success`
- step count: 4
- activation count: 31
- interaction count: 3
- event high-water mark: 121
- replay availability: `available`
- task: opened the Android Settings homepage and requested immediate termination
- terminal action: `done`, with `effect_kind=none` and `effect_performed=false`

The live page showed the execution path, action evidence and Android Settings
screen. The terminal page retained the final story and exposed “打开完整回放”.
Replay loaded the same Run identity, exposed the 119-event timeline, and moved
to a later observation showing the Settings screen. Agent run history listed the
new `SUCCESS` row and the older controlled `DEVICE_FAILURE` row separately.

This is positive evidence for one real emulator journey through the current
Studio service. It is not a general Android reliability claim: the persisted
Replay envelope still reports `environment=unverified` and
`realDeviceEvidence=false`, so the current product contract does not promote
this run to verified device evidence even though the browser visibly received
an emulator screenshot. That metadata boundary must remain explicit.

## Findings from the same user-oriented pass

1. **Resolved 2026-09-19 — model dependency authoring was JSON-only.** The
   existing “从零搭建” Agent still opens with a missing required `llm` dependency,
   but the Inspector now provides a Catalog-backed form for provider, model ID,
   SecretRef, service address and common parameters. Browser validation removed
   the missing-`llm` diagnostic; the fixture then exposed its independent missing
   input-port and unreachable-Output diagnostics. Advanced dependency JSON remains
   available for extensions.
2. **P2 — automatic layout over-fits the canvas.** At 1280×720, clicking
   “自动整理” correctly creates one undoable presentation edit and leaves
   `Graph 已通过`, but its immediate `Fit View` reduces the graph to tiny,
   hard-to-read cards. The action is semantically safe but visually too small
   for a first-time user.
3. **P2 — the “从零搭建” fixture is not empty.** It opens with a Reasoning
   node and an Input→Reasoning relation, then reports one missing-`llm`
   diagnostic. Either the creation label should describe the starter template,
   or a true blank mode should start with only Input/Output and progressive
   guidance.
4. **P2 — evidence completeness needs explanation.** Run history displays
   `89% · complete native_studio_run` for the successful run. The run is
   terminal and replayable, but the meaning of 89% is not explained beside the
   value, so users may read it as an incomplete execution.

The Builder guide, node add/undo path, live Run, terminal handoff and Replay
were usable in this journey. Feedback-loop authoring and the full blank-agent
from-scratch path remain separate acceptance items; this slice did not claim
that those are solved.

## Tested baseline

On 2026-09-17, HEAD was `0cf5090e5e40341d1549998c5600601fbe908256`.
The working tree already contained extensive tracked and untracked Studio,
schema-3 capability authoring, Benchmark, documentation, paper and release
changes. This is a dirty-worktree test, not evidence for that clean commit.
No existing changes were reset, staged or committed. Exact scenario execution
identities and retained browser evidence are still pending.

## Existing evidence map (coverage, not browser acceptance)

| Scenarios | Existing contracts and test locations |
| --- | --- |
| R01 | `test_runtime_readiness.py`: missing prerequisites, legacy policy, no durable effects; `test_capability_authoring.py`: immutable policy closure |
| R02–R03 | `test_run_models_repository.py`: immutable revisions/idempotency; `AgentRunPage.test.tsx`: stable retry intent; Builder save command tests |
| R04–R07 | `test_run_replay_http.py`: feedback causality/HTTP/SSE; `liveRunSession.test.ts`: continuous backfill, heartbeat, duplicates, gaps, trusted prefix |
| R08–R09 | `test_run_execution.py`: accepted/running cancel, competing terminal paths, binding and later failures |
| R10–R11 | `test_run_artifacts_debug.py`, `test_run_replay_http.py`, `AgentRunPage.test.tsx`: artifact/Replay availability and native same-source projection |
| B01 | `benchmark_layered_acceptance_fixtures.py`: existing actual composition uses the current `modular_baseline` template; report/browser regression still pending |
| A01 | No fresh evidence; requires separately recorded exact target/task/budget authorization after fake gates |

Run lifecycle, Agent result, Benchmark outcome and artifact availability are
separate facts. Ordinary Run does not imply a Benchmark report. Reloading the
browser reconstructs the same Run; it does not resume a device checkpoint.

## Legacy fixture audit

`scripts/studio_live_fake_server.py` constructs a legacy `StudioFlowDocument`
and directly persists a hand-built `CompileSnapshot`. Current eligibility
explicitly rejects legacy revisions for new execution even when the graph is
valid. Its old smoke instructions are therefore not this acceptance's setup.

The newer feedback HTTP fixture compiles `modular_baseline` through the real
authoring service, but explicitly uses `enforce_readiness=False`. Its passing
test proves HTTP/runtime/Replay behavior, not the complete launch prerequisite
gate. The new developer-only fixture keeps `enforce_readiness=True`, evaluates
exact eligibility/readiness, and uses fresh storage and the shipped template.
Production policy, compiler, worker and runtime semantics are unchanged.

## Fresh commands and observations

From the repository in the `unimobile` environment:

```sh
python -m pytest tests/studio/test_run_execution.py tests/studio/test_run_replay_http.py tests/studio/test_runtime_readiness.py tests/studio/test_run_models_repository.py tests/studio/test_run_artifacts_debug.py tests/studio/test_run_event_performance.py -q
```

Observed: **64 passed in 6.12 s**, exit 0. These are automated regression
results only; fake browser and Android gates remain pending.

The new acceptance test's first run recorded 2 passes and 2 failures because
its author incorrectly expected `error` rather than the established Agent
result `failure`. `test_standard_template_preserves_evidence_across_controlled_failures`
confirms the latter contract. Only the new assertion was corrected; this was
a test-authoring mistake, not a product defect or a flaky success retry.

## New fixture boundary

`tests/studio/run_experience_fixtures.py` supplies only a synthetic device and
a per-Run scripted model through explicit dependency injection. Images visibly
say **FAKE / NO REAL DEVICE**. The model does not retain prompts. The server
uses loopback only, refuses a nonempty workspace, and releases held calls on
shutdown. Synthetic SecretRef presence metadata is not a real credential.
The new HTTP tests and the second browser workspace use effect tripwires for
real Android construction/discovery, subprocess execution and non-loopback TCP
connections, plus a rejecting SecretRef provider. The guarded success Run
finished with zero attempted forbidden effects. These tripwires are test
instrumentation, not a third-party plugin sandbox. The first diagnostic browser
workspace predates these tripwires and must not be counted as guarded evidence.

Developer server (fresh empty workspace required):

```sh
python scripts/studio_run_acceptance_server.py --workspace /tmp/zhixing-run-acceptance-UNIQUE --hold
```

Use `stats`, `release`, and `stop` on its standard input. The hold has a bounded
600-second timeout; timeout is a failure outcome, not a successful cancel.
The frontend should proxy `http://127.0.0.1:8891` and use port 4191. This script
and its test imports are developer-only, not installed-package functionality.

## Current outcome: paused at a scope boundary

Four reproduced frontend defects were repaired without changing backend APIs,
execution policy, lowering, device behavior or graph identity:

| Finding | Reproducer and correction |
| --- | --- |
| Live screenshot/steps updated while task bar stayed `accepted` and summary said waiting | `AgentRunPage.test.tsx`: committed lifecycle events now invalidate the exact server-owned Run query; no guessed resource state or per-activation polling |
| Cancelled terminal story was labelled failed | `runStoryPresenter.test.ts`: preserve `cancelled` as a distinct presentation status, retaining the actual error detail |
| Terminal Run retained a disabled `Cancelling…` control | `TaskRunBar.test.tsx`: cancellation control exists only before authoritative terminal |
| Replay's empty initial prefix claimed the whole Run ended before observation | `devicePaneState.test.ts`: distinguish current Replay prefix from whole-Run evidence absence; real early-termination handling remains |

Each new regression failed before its production repair. After changing the
cancelled story's wording, one older route assertion still expected the previous
generic “ended” wording; it was updated to require “cancelled” for that case.
The final full run passed; the initial mismatch was not discarded as a flake.

### Browser facts retained

- Diagnostic/cancel Run: `run-cfaadd2a201143dc922e9282208da2fa`, Agent
  `agent-e9d3ac659c674361832721a9d0fc911e`, revision
  `revision-0e00a72356a746d6b03206fb86e812b2`. Before repair the API was
  `running`, high-water 22, while the UI remained `accepted`. Reload recovered
  the same Run. Cancellation displayed `cancelling` while the model call was
  held; release produced cancelled terminal and explicit same-Run Replay.
  Counts remained one execution, one model call, screenshot/XML only, no tap.
- Guarded success Run: `run-c10f4dcc0f654a5191309d385c0f1b29`, Agent
  `agent-35314308de5a460db3ac1e920709b1a0`, revision
  `revision-dfc2d6d99fe74be5891efa3522a2b8a9`. Without browser reload, the
  repaired UI showed `running`. Locking the first Perception step preserved
  its Inspector evidence while the Phone advanced to observation 44 and the
  Run completed. Journal: 65 events, high-water 65, one terminal event.
  Counts: one execution, two model calls; screenshot/XML/tap/screenshot/XML.
  Explicit Replay showed the last frame at cursor 63 and hid it at cursor 3.
  Counts remained unchanged after Replay navigation; forbidden-effect counters
  remained zero. Both Runs used canonical identity
  `sha256:0a1edd257bb3ea73bc42eb873b85d3c1819bd91ee45ebc3f2280b0387e23fb61`.
- Development interruptions are not acceptance successes: changing hook
  structure caused a Vite hot-reload error, a browser tab became unavailable,
  and the fixture restart caused expected proxy connection errors. The
  repaired path was rechecked in a fresh page/workspace. No process recovery
  or controlled SSE outage claim is made from those interruptions.

Screenshots under `docs/assets/studio-run-experience/` show only synthetic
screens and Studio. The JSON ledger is a partial matrix, not a passed gate.

### Scope decision required: Builder keyboard position changes

In the second isolated workspace, select the Memory node and press Right.
XYFlow announces `Moved selected node right. New position, x: 230, y: 70`, but
the toolbar still reports the revision saved and disables Save revision.
This was reproduced twice. `BuilderCanvas.tsx` currently persists positions
through `onNodeDragStop`, with no corresponding `onNodesChange` position path.
No Builder implementation was changed in this change. This prevents using
that particular edit to validate dirty Save & Run; it does not establish that
every edit/save path is broken. A separate Builder reliability change is the
recommended owner. Do not silently extend this Run change to repair it.

### Final automated checks in this session

- Existing Run/readiness/HTTP/SSE/Replay tests + new ledger/harness tests +
  actual fake Benchmark publication and reporting-resource regressions:
  **85 passed in 12.90 s**. Add
  `tests/studio/test_run_acceptance_ledger.py`,
  `tests/studio/test_run_experience_acceptance.py`,
  `tests/studio/test_benchmark_layered_acceptance.py::test_actual_default_composition_executes_fake_pass_and_publishes`
  and `tests/studio/test_benchmark_reporting_resource.py` to the command above.
- `cd studio && npm test -- --reporter=dot`: **609 passed, 131 files**, 15.79 s.
- `npm run typecheck` and `npm run lint`: exit 0.
- `npx vite build --outDir /private/tmp/zhixing-run-guarded-WeiAsK/frontend-build`:
  exit 0, 621 modules, 5.86 s; existing tracked `studio/dist` not overwritten.
- OpenSpec strict validation and scoped whitespace check: passed.
- No product Python imports, dependencies or packaging configuration changed;
  a new clean-wheel claim is neither required for these edits nor made here.
- Optional `pyperclip` plugin imports warned in this local environment; selected
  fake Run scenarios passed, but clipboard plugin availability is not verified.

### What remains unverified

The full matrix remains open: dirty Save & Run, explicit stream interruption,
all controlled-failure/missing-artifact browser variants, complete safe fixture
variants, and the read-only Benchmark report browser journey. Benchmark
automated publication/resource tests are not a substitute for B01 browser
acceptance. Fresh Android target/task/model/budgets are not approved and no
real device/model actions were performed. Do not archive or publish this as
completed acceptance. Owned acceptance servers were stopped; pre-existing
services and workspaces were left alone, and temporary evidence was retained.

### Engineering explanation of the verified repairs

“The Agent was running correctly, but its live event projection and cached Run
resource could diverge. I reproduced that in an isolated current-policy fake
environment, then made verified lifecycle events trigger an exact resource
refresh rather than inventing frontend status. I also separated cancellation
from failure and a Replay prefix from whole-Run evidence absence. Browser
observations and regression tests verify those repairs; full Run acceptance
and Android claims remain pending.”

- Why not set `running` from an activation? The resource remains authoritative;
  events invalidate the query rather than constructing a second lifecycle.
- Why not poll on every event? Only newer service lifecycle facts trigger this
  repair, avoiding requests for each activation or heartbeat.
- Does a successful fake Run prove Android works? No. It proves only the
  tested service/UI path with explicit fake boundaries and recorded counts.
# 2026-09-19 空白 Agent 真实闭环验收

本次验收从一个真正的空白 Agent 开始，按使用者路径完成了添加能力、配置模型、连线、保存 revision、提交任务和 Android 模拟机运行。过程中发现并修复了四个会迫使用户猜测的断点：

- 空白图的 Output 尚未可达不再作为首屏红色错误，而是显示“先添加能力”，并给出 Perception、Memory、Reasoning、Action Executor 的推荐顺序。
- Reasoning 连接 Output 时会直接说明不能这样结束，并给出 Action Executor 的下一步连线方法。
- 引导明确说明 Perception 与 Action Executor 的设备 observation 由运行时自动注入，不要把 Input observation 手动连到画布；Android Run 所需的下一轮反馈则明确为 Action Executor.result → Memory.write。
- Catalog 表单中的默认值现在会在新建或更换能力实现时写入 Agent 文档。此前只显示默认值但不保存，导致真实运行时拿到空的 Reasoning 配置；该问题已通过模拟机失败复现并修复。

最终验证路径为：Input.task → Reasoning.task；Perception.perception → Reasoning.perception；Input.task → Memory.write；Memory.context → Reasoning.memory；Reasoning.action → Action Executor.action；Action Executor.result → Output；并使用“下一轮反馈”将 Action Executor.result → Memory.write。配置了模型、API SecretRef 和服务地址 SecretRef 后，Graph 校验通过并保存为 Revision 4。

运行任务为“打开 Android 设置首页，看到设置首页后立即结束，不要修改任何设置。”运行页实际收到 Android observation 截图，过程状态依次显示记忆、感知、推理、动作执行和完成检查，最终 Agent 状态为“已完成”，设备最近动作显示 `done · terminal`，完整回放已准备好。

这次证据只覆盖一个只读设置页任务和当前本地 Android 模拟器；它证明了 Builder 到 Run 的闭环可用，不代表任意模型、任意任务或更广泛 Android 兼容性已经验证。
