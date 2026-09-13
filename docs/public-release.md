# Public source release

The public repository is built from a reviewed, committed snapshot. Do not copy
the development working directory and do not mirror-push its Git history.

## Boundary

`release/public-manifest.json` is the source-of-truth allowlist. It includes the
backend, Studio, tests, examples, public documentation, accepted OpenSpec specs,
CI, and release tooling. Explicit denies remove generated dependencies, local
device configuration, duplicate examples, internal paper/interview material,
and Benchmark assets whose redistribution provenance has not been closed.

The exporter considers only Git-tracked files. An untracked file below an
included directory is never copied. The public `.gitignore` comes from
`release/public.gitignore`, rather than the development repository's selection
rules.

## Preconditions

1. Rotate any credential that has previously entered development Git history.
2. Commit the reviewed release state and require a clean worktree.
3. Pass backend, frontend, packaging, OpenSpec, and secret/path checks.
4. Review third-party notices before adding Benchmark assets to the allowlist.
5. Use a new empty output directory outside the development repository.

## Validate and build

Validation only:

```bash
python scripts/build_public_release.py
```

Materialize the public source tree:

```bash
python scripts/build_public_release.py \
  --destination ../unimobile-public
```

`RELEASE-MANIFEST.json` records the source commit, output/source paths, sizes,
and SHA-256 values. `dirtyPreview=false` is required for a release candidate.
`--allow-dirty` is only for local inspection and must not be used for publication.
When reviewing new files before committing, explicitly add `--include-untracked`.
This mode still applies the allowlist and all content checks, and always records
`dirtyPreview=true` and `includesUntracked=true`. It does not stage or commit any
development files. Review every inventory row before promoting a snapshot.

The public ignore template is retained alongside its `.gitignore` copy so the
exporter also works inside a fresh clone of the public repository.

## Validate the exported tree

Initialize a new Git repository inside the exported directory, then run:

```bash
python -m pip install -e ".[dev]"
python -m pytest tests -q \
  -m "not real_android_acceptance" \
  --ignore=tests/packaging
python -m pytest tests/packaging -q
python -m build
python -m twine check dist/*

cd studio
npm ci
npm test
npm run typecheck
npm run lint
npm run build
```

## Publish without overwriting the legacy branch

Push the clean repository first as `release-v2`. After CI and a clean-clone
review pass, rename the old public `main` to `legacy-v1`, rename `release-v2` to
`main`, set it as the default branch, and reapply branch protection. This keeps
the old implementation recoverable without mixing it into the new source history.

Never use `git push --mirror` to perform the public replacement.

## Known limitation

The default manifest currently excludes `benchmarks/` media and generated
packages. Adding them requires a separately reviewed source, license,
redistribution, attribution, integrity, and size record for every included member.
Five tests that specifically require those upstream Packages report explicit
skips when the Packages are absent. CLI orchestration tests use generated local
fixtures and still run. These skips are not evidence of upstream task success.
The legacy optional `experiment.human_review_output` integration is not bundled;
its explicit opt-in export is unavailable in the public tree. Core execution and
native managed report/Replay paths do not require that local helper.

Credential pattern checks detect known shapes, not every possible secret.
The exact synthetic reporting canary is exempt; real credentials must be rotated
at the provider if they entered development history. Exporting a fresh source
history cannot revoke credentials already disclosed elsewhere.
