# Builder layout and configuration

Status: frontend implementation and automated checks completed; final acceptance
is pending the real Chrome 200% zoom check. Not archived or published.

## Baseline (2026-09-15)

The existing no-device acceptance page at localhost:5173 uses the isolated
`/private/tmp/zhixing-guidance-LrNG1d` workspace. No execution is requested in
this change. Baseline frontend: `cd studio && npm test -- --reporter=dot`:
129 files / 595 tests passed. The current Settings expose light/dark and
sm/md/lg font presets (root sizes 13/14/15px), but no global UI-language switch.
Builder currently mixes Chinese instructions and English technical/action names.

Before (image not bundled in the core source)

## Schema audit (source inspection, not runtime parity evidence)

| Source | Verified declaration | Limit |
| --- | --- | --- |
| `zhixing/studio/catalog.py` built-in map | Sliding Window Memory declares window_size, include_thought, include_raw with defaults and a bounded window | `zhixing/plugins/agent/memory/sliding_window.py` accepts these constructor arguments but also knowledge_source and kwargs; matching defaults do not prove validation parity |
| Same built-in map | Universal Reasoning declares nullable preset/prompt_file/parser_name/input_mode and parse_max_retries | A field declaration is not an enum of supported presets or proof every runtime combination is valid |
| `zhixing/components/authoring.py` safe_metadata | External ComponentSpec derives config_schema from its Pydantic config model, through redaction | References/unions and redaction mean a future form renderer needs explicit supported-subset and round-trip tests |
| `zhixing/studio/catalog.py` fallback | Unmapped built-ins receive a closed object schema with no declared properties | Do not describe a closed-empty schema as missing or assume it matches every constructor |
| `studio/.../catalog.schema.ts` | Frontend preserves configSchema JSON metadata, defaulting missing metadata to an empty object | An unrestricted empty schema does not mean no parameters exist |

JSON remains the configuration editor. No form fields, defaults, credentials or
constraints are inferred from examples or legacy UI definitions. No backend
repair or schema/runtime parity claim is included in this audit.

## Scoped terminology

Keep existing English technical action names and Chinese instructional prose;
the following glossary establishes consistent meaning, not a new language switch.

| English | 中文 |
| --- | --- |
| Capability | 能力 |
| Implementation | 实现 |
| Parameters | 参数 |
| Dependencies | 依赖 |
| Advanced settings | 高级设置 |
| Technical identity | 技术身份 |
| Validate / Validation | 校验 / 校验结果 |
| Save revision | 保存版本 |
| Save As | 另存为新 Agent |
| Runtime readiness | 运行环境准备状态 |
| Expand editor / Close | 展开编辑 / 关闭（编辑保留在草稿中） |
| Reset layout | 重置布局（不重置图文档） |

Capability-purpose descriptions explain approved family roles only, based on
the Stage 0 product decisions and the current capability-only graph model.
They do not promise behavior of arbitrary selected external implementations.

## Implementation and state boundaries

The Inspector now presents family purpose and exact implementation/version before
configuration, then Advanced settings and Technical identity disclosures. Missing
required dependencies remain next to their editor; active fallback order remains
visible independently of its policy disclosure. Repeated heading explanations
were removed, not the separate saved/valid/readiness facts.

Expanded JSON editing shares the existing raw-field registry. Closing does not
discard edits; Save revision uses the same snapshot-bound save command as the
toolbar. Native dialog behavior alone let reverse Tab escape to browser chrome
during testing; an explicit Tab boundary and close-before-focus restoration were
added and verified in the browser. No new server-side or credential path exists.

Pane sizes belong to `zx-builder-panes-v1` display preferences, not the Agent
document. Finite values are bounded and fitted to measured workspace space;
storage failure is nonfatal. Pointer movement, keyboard arrows and Reset layout
do not move nodes or modify the draft. The existing Expand canvas mode hides the
side panes and separators together. Existing root font presets now affect the
configuration chrome; XYFlow zoomed node geometry was not redesigned.

## Reproducible verification

From the repository, run:

```bash
cd studio
npm test -- --reporter=dot
npm run typecheck
npm run lint
npm run build
```

Observed final result: **131 files / 605 tests passed**, typecheck and lint exit
0, production build completed. For this run, build output was isolated with
`npm run build -- --outDir /private/tmp/zhixing-layout-baseline-w9eQuT/final-build`
to preserve existing `studio/dist`. The pre-existing React Router future-flag
warning remains informational, not a failed test.

From the repository root:

```bash
conda run -n unimobile python -m pytest tests/studio/test_capability_authoring.py -k 'hash_and_round_trip or lowering_is_deterministic' -q
```

Observed: **2 passed / 9 deselected**. These tests verify presentation exclusion
and deterministic lowering, not real Android execution. Frontend state invariance
tests establish that the new presentation operations do not alter the document.
The isolated SQLite workspace had **0 ordinary Runs and 0 Experiments** after the
browser journey. No production workspace or model/device execution was requested.

## Browser evidence (Coding Agent observed)

The final in-app browser matrix covers **24 combinations**: 900/1024/1280/1440px
width, 800px height, light/dark, and sm/md/lg. Each preserved an Inspector right
edge within the viewport and no page-level horizontal overflow. Computed JSON
editor font sizes were 13/14/15px. Screenshots are retained in
`docs/assets/studio-builder-layout/{light,dark}-{sm,md,lg}-{width}.png`.

The sampled 38 enabled Inspector/palette/toolbar text controls in each theme had
minimum computed foreground/background contrast 6.68:1 dark and 6.26:1 light.
This bounded DOM sampling is not a whole-application accessibility certification;
disabled controls, canvas zoomed content and unrelated routes are not included.

Verified journeys:

- Malformed `{` in expanded editing cannot save; closing/reopening retains it.
- Corrected focused input saves through the real service: test Agent
  `agent-c62e04d591d7427d8c9d24a36a34cd17`, revision ordinal 3, `parse_max_retries: 3`.
  It remains compile-invalid because its required LLM dependency is deliberately
  absent; saving does not claim runnable success.
- A 2,499-character JSON configuration remained editable and survived closing
  plus cancelling a Settings departure. The extra recording-only field was
  removed without saving it. It is not a supported parameter example.
- Reverse/forward Tab stays inside expanded editing; Escape restores focus to
  the exact Expand trigger.
- Keyboard resizing changed Inspector width from 360 to 380px; pointer resizing
  changed it to 437px; Reset layout restored the preference. Saved state remained.
- Expand canvas hides both side panes and both separators, then Restore panels
  restores them.

Final light layout (image not bundled in the core source)
Expanded long JSON (image not bundled in the core source)

## Remaining acceptance and limits

- Real Chrome 200% zoom: **not yet verified**. The in-app browser zoom shortcut
  did not change its viewport/DPR, so it is not counted as zoom evidence. A
  separate real Chrome local test tab was opened. On 2026-09-15, after user
  approval, the native Chrome address-bar accessibility control explicitly
  reported `缩放比例：200%` following menu-based zoom changes. However, interaction
  was interrupted again when opening the Inspector. The complete 200% editing
  journey and a matching visual capture remain unverified. The test tab was
  last observed at 200%; restoration was not confirmed. Do not mark OpenSpec
  task 5.4 complete on the zoom indicator or viewport emulation alone.
- Final interview note and full-acceptance handoff remain pending that check
  (task 5.5). No user report has been substituted for agent-observed evidence.
- JSON is retained intentionally; schema-generated forms, arbitrary external
  schema support, global bilingual UI and mobile editing parity are not added.
- Narrow windows may show only part of a graph at its existing zoom. Pan or
  Expand canvas to inspect it; resizing does not silently rearrange the graph.
- This change does not prove Android execution, model quality or Benchmark
  success, and does not change their runtime/preflight contracts.
