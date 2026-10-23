# Studio Builder editing reliability

Implemented in the development checkout by OpenSpec change
`harden-studio-builder-edit-session`. This is **not** a release-v2 publication
claim, runtime acceptance, or a claim that Studio has no remaining bugs.

2026-09-17 follow-up: [UX phase 1](studio-builder-editing-phase1.md) adds bounded undo/redo and makes camera movement temporary. The historical Fit View observation below describes the earlier implementation, not current behavior.

## What changed

The Inspector and toolbar now share one in-memory editing session. Malformed
configuration text is unsaved work, survives node selection, and cannot be
silently replaced with the previous parsed value during Validate, Save, Save As,
Export, or Save & Run. Structurally valid but compile-invalid graphs remain
saveable drafts.

Previously, Inspector JSON lived in component-local state and only successful
blur parsing updated the document. Toolbar commands could validate the older
document; route unmount cleared unsaved work; successful save responses hydrated
the editor without accounting for subsequent edits.

Now the flow is:

```text
Raw input + parsed graph → atomic current snapshot → existing API
          │                         │                    │
          └─ unsaved/field errors    └─ session/generation └─ acknowledgement
                                                              │
                               advance saved baseline, retain newer edits
```

The backend revision, optimistic concurrency, configuration schemas, canonical
graph identities, AgentGraph/Benchmark independence, and runtime are unchanged.

## Editing and leaving

- `{` or unsafe credential input immediately invalidates current feedback. Fixed
  diagnostics never quote raw source; correction stays in the original field.
- Returning input to its saved value clears dirty state. Equivalent object key
  order/formatting is not a semantic edit. Presentation edits still require saving
  but do not redefine canonical execution identity.
- The raw-field owner includes node, candidate slot, implementation identity, and
  property. Removing/replacing an owner with outstanding input requires explicit
  confirmation. Node selection alone never authorizes discarding input.
- In-app departure offers **继续编辑 / 放弃修改并离开 / 保存并离开**. Invalid input
  or a known revision conflict disables save-before-leave. Saving an incomplete
  graph may succeed as an invalid draft; that does not authorize execution.
- Saving is serialized across normal save, Save As, Save & Run and leave-dialog
  save. Normal editing may continue during a request. Acknowledgement of A can
  update the saved baseline without replacing newer B. A subsequent save uses
  the acknowledged base revision.
- Compile callbacks require the originating session, generation and validation
  request identity. Old-session responses cannot alter the new editor. Save As
  and Save & Run cannot navigate over newer edits; Run handoff also checks the
  current cached readiness state after saving.
- Import is parsed and credential-checked before replacement; file reads,
  revision loads and reloads are generation-owned. Failed reloads do not hydrate
  retained Query cache data as if it were a fresh server response.
- Refresh/close uses native `beforeunload`, not asynchronous save-on-close.
  Raw drafts are **not** stored in localStorage or server DTOs.

## Verified browser evidence (2026-09-14)

Automated checks: **122 test files / 546 tests passed**, plus lint, typecheck,
production build and strict OpenSpec validation. The detailed ledger distinguishes
old-baseline reproduction, deterministic tests, browser observations and manual checks.

Actual development frontend on `127.0.0.1:4173`, actual backend on
`127.0.0.1:8877`, isolated database
`/private/tmp/zhixing-edit-session-IpvTDk/studio.sqlite3`.
No device/profile/secret configuration or installed Benchmark discovery was used.
No Run, model call, or Experiment execution was requested.

| Journey | Observed result |
| --- | --- |
| Blank Agent → add Memory → Settings readiness button | One leave dialog; Continue retained the node and dirty state. |
| Save before leaving with incomplete graph | Backend saved invalid revision 2, then navigated to Settings. Returning showed Memory and `acceptance_marker: 7`. |
| Save presentation → refresh | Saved Memory configuration reloaded through the real service. Fit View is itself a presentation edit, not a lost-save defect. |
| Valid recommended example → Reasoning config `{` → Validate | Input-error state, Save disabled, no false compile success; Output/Reasoning selection retained `{`. |
| Dirty browser Back and Forward | Both reached the in-app leave dialog; cancellation retained the draft. |
| Stop only the isolated backend → Save / Save before leaving | HTTP 502; draft and current page retained; leave dialog explained unconfirmed save. |
| Restart service → retry → refresh | Reasoning `parse_max_retries: 3` persisted in valid revision 2, independently confirmed by GET API. |
| Home / Library / Run / Catalog / Composer / Benchmark editor | Routes loaded; Run remained disabled without a Device Profile. Composer showed its missing prerequisites. |
| Missing Replay deep link | Rendered `Replay 不存在`, not a routing crash. Existing valid Replay route tests also passed. |

Test objects are retained only in the isolated database:

- Blank Agent: `agent-532981f3bdd642ccb565cd5b1700ad02`.
- Example Agent: `agent-c74b87a738ae4995a352f2ac2dbef2b2`.
- Saved example revision: `revision-6df12d24711a4a5ea7dc452955748d8a`;
  ordinal 2, compile status `valid`, `parse_max_retries: 3`.
- Benchmark routing fixture: `benchmark-draft-5281ffb9770a46e4a1c1c4b76a00508d`;
  template-only, unvalidated. No Benchmark publication or execution.

Unsaved navigation is protected (image not bundled in the core source)

Invalid input no longer reports the old graph as current success (image not bundled in the core source)

Failed save leaves the editor and its work intact (image not bundled in the core source)

Additional captures: saved refresh (not bundled in the core source)
and successful retry (not bundled in the core source).
The final raw-input leave dialog (not bundled in the core source)
also shows why save-before-leave is disabled until the field is corrected.
The earlier public-release defect captures remain in the
[original UX review](studio-ux-review-20260914.md).

## Reproduce locally

Run from the repository root, with the existing `unimobile` environment:

```sh
env -u ZHIXING_STUDIO_SECRETS -u ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG \
  -u ZHIXING_STUDIO_BENCHMARK_PACKAGES -u ZHIXING_STUDIO_BENCHMARK_CATALOG_ROOTS \
  conda run -n unimobile --no-capture-output python -m zhixing.studio serve \
  --host 127.0.0.1 --port 8877 \
  --workspace /private/tmp/zhixing-edit-session-IpvTDk \
  --database /private/tmp/zhixing-edit-session-IpvTDk/studio.sqlite3 \
  --no-installed-benchmarks
```

In another terminal, from `studio/`:

```sh
ZHIXING_STUDIO_PROXY_TARGET=http://127.0.0.1:8877 npm run dev -- --host 127.0.0.1 --port 4173 --strictPort
npm run test
npm run lint
npm run typecheck
npm run build -- --outDir /private/tmp/zhixing-edit-session-IpvTDk/dist-final
```

If ports are occupied, stop only the matching test processes or choose ports
compatible with the existing service origin policy. Do not reuse a production
database. Build output was placed outside tracked `studio/dist` to preserve
unrelated user work.

## Evidence limits and manual checks

- Native unload/close dialogs: the in-app browser did not expose a native dialog
  handle. A dirty reload attempt retained `{`, but this is **not** proof of the
  physical Chrome close dialog. Unit tests verify `beforeunload` registration,
  raw dirty cancellation, clean behavior and cleanup. Manually type `{`, press
  refresh/close in ordinary Chrome, cancel, and verify exact text remains; then
  repair/save and verify clean refresh needs no confirmation.
- Explicit in-app Discard is covered by routed tests, including POP. It was not
  action-time-confirmed and clicked in the live browser; no live discard proof is
  claimed. To check manually, use only a disposable draft, choose Discard, return,
  and expect the saved baseline. This intentionally discards unsaved work.
- The Benchmark editor's native confirm could not be reliably inspected through
  the automation interface (click timed out, subsequent page was Library).
  Its actual editor route loaded without a Builder dialog; existing Benchmark
  route/editor tests passed. Manual native-confirm cancellation and duplicate-
  prompt inspection remain a check, not an asserted browser result.
- Test-environment dialog and AbortController shims are not browser focus/inert
  or close-dialog evidence. StrictMode and Agent-to-Agent component reuse are
  covered by lifecycle tests.
- Memory-only drafts do not survive deliberate discard, confirmed unload,
  process crash, or development hot-module replacement. Save As has no new server
  idempotency protocol; an uncertain create may already exist in the Agent list.
  Revision saves retain existing CAS and do not automatically merge conflicts.
- No broad Android/model quality, security sandbox, mobile-layout or full
  usability-study claims. Offscreen new nodes, onboarding, config UX hierarchy
  and other UX-review items remain separate work.

For implementation check output and baseline distinctions, see
`openspec/changes/harden-studio-builder-edit-session/verification.md`.
