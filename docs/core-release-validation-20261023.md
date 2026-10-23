# Core source verification — 2026-10-23

This record describes checks run by the Coding Agent on an isolated curated
source copy. It does not describe a new Android/model experiment or external
artifact acceptance. The source profile follows the user's choice to publish
the core and withhold upstream ports whose redistribution terms remain unverified.

## Current checks

| Check | Observed result |
| --- | --- |
| No-device backend suite from the public copy | 1,524 passed, 8 skipped |
| Studio tests after the copy's own offline `npm ci` | 145 files, 681 tests passed |
| Studio typecheck, lint and production build | Passed; build retained its bundle-size advisory |
| Full installed-package suite | 38 passed |
| Additional wheel license/resource check after adding distribution NOTICE | 1 passed |
| Wheel and sdist build / metadata check | Passed |
| Deterministic Runtime examples | Ordinary loop and generalized ReAct / Planner-and-Execute examples succeeded with fake services |
| Self-contained minimal Benchmark Package | Validated without device/model execution |
| Both retained AndroidWorld JSON suites | Loaded through the production contract loader; 81 + 35 unique IDs, 116 distinct overall |

The initial sandboxed backend run could not bind loopback ports or inspect its
own test child processes. The complete no-device suite was rerun with those
test capabilities available and produced the result above. No failing test was
reclassified as a skip. The eight existing skips are retained; omitted upstream
Packages and opt-in checks are not evidence of real task success.

## Reproduce

From a clean source checkout with Python 3.10+ and Node.js 22.12+:

```bash
python -m pip install -e ".[dev,openai,harmony,m3a,androidgen,guiexplorer]"
# CPU tensor tests do not load model checkpoints.
if [ "$(uname -s)" = "Linux" ]; then
  python -m pip install 'torch>=2.1,<3' --index-url https://download.pytorch.org/whl/cpu
else
  python -m pip install 'torch>=2.1,<3'
fi
python -m pip install -e ".[androidgen-retrieval]"
python -m pytest tests -q -m "not real_android_acceptance" --ignore=tests/packaging
python -m pytest tests/packaging -q
python -m build
python -m twine check dist/*
npm --prefix studio ci
npm --prefix studio test
npm --prefix studio run typecheck
npm --prefix studio run lint
npm --prefix studio run build
```

Package checks use disposable environments; some download public dependencies.
Local HTTP/SSE tests need loopback sockets and process-lifecycle tests need
permission to inspect their own children. No phone or model credential is needed.

The first remote CI run exposed undeclared test-environment assumptions: the
integration tests import optional vision/Harmony libraries, fixture preparation
uses the OpenAI component metadata, and Python 3.12+ disposable environments do
not supply the external fixture's setuptools builder. CI now installs the named
lightweight integration extras explicitly. The external fixture wheel is built
with declared developer build tools and only then installed into the isolated
base runtime. These are test/build dependencies, not new base runtime requirements.
The tensor checks explicitly install PyTorch without checkpoints. A macOS-only
Worker fixture path now uses the platform temporary directory, and wheel/sdist
metadata is fixed at version 2.4 so the current validator can read it.

## Source and evidence boundary

The README follow-up replaces the former four-stage overview in both languages
with the supplied paper workflow figure and descriptions of Agent construction,
Graph Runtime, task construction, and Benchmark Runtime. The new image is an
unchanged copy of the author's supplied PNG (SHA-256
`56041b56a6deefaf82ee51169cf55466655697de9f9de2ba0c3f3255cbfd6c6e`).
All 38 local links in each README resolve in the public tree. The documented
no-device graph example returned `success`, the minimal Package validation
returned `is_success: true`, and the 17 release-boundary tests passed. The wheel
and sdist were rebuilt and passed metadata validation after the README changes.
No Runtime or device behavior changed in this follow-up.

- Public selection is controlled by `release/public-manifest.json`; the
  development version is `release/paper-core-manifest.json`.
- The source export omits private learning notes, paper drafts, local secrets,
  device profiles, generated dependencies, databases, logs and experiment output.
- Source licenses and the distribution NOTICE are retained. Agent-SAMA,
  AndroidArena, V-Droid, MobA and VisionTasker implementations, copied fixtures
  and online examples are outside this profile.
- Public documentation marks unbundled historical screenshots and experiment
  files explicitly instead of linking to absent private files.
- Framework-authored contract metadata is retained to avoid changing graph
  identities. Reserved component names do not imply an installed implementation.
- The final `RELEASE-MANIFEST.json` binds selected bytes to a reviewed source
  commit. The development checkout's unrelated changes are not committed or
  uploaded by this process.

No real Android run, model-quality comparison, broad compatibility claim,
statistical-significance claim or reproduction of paper metrics is added by
these checks. Full benchmark media and frozen experiment result ledgers remain
outside the source release. See [the paper artifact guide](paper-artifact.md).
