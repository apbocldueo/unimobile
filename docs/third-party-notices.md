# Third-party source in the core profile

The framework's Apache-2.0 license does not replace licenses or copyright
notices belonging to upstream source. Model weights, apps and datasets are
separate dependencies and are not distributed here.

| Retained source | Pinned origin | License record |
| --- | --- | --- |
| M3A selected algorithms and reference fixtures | google-research/android_world, `f8e78c0ab0bb8b5daa681afd0296ed0193a98f1f` | `zhixing/plugins/agent/m3a/LICENSE`, original source headers and `source-origin.json` |
| AndroidGen selected algorithms and fixtures | THUDM/AndroidGen, `3f511cff18a842e6583ac7e7d9cabd217c5d3b1b` | `zhixing/plugins/agent/androidgen/LICENSE` and `source-origin.json` |
| EcoAgent selected algorithms and fixtures | Yi-Biao/EcoAgent, `d9b16afb4ccaf3beb59664984dab2aa258b3cccf` | Adjacent MIT `LICENSE`, `NOTICE`, and `source-origin.json` |
| GUI-explorer selected algorithms and fixtures | iLearn-Lab/ACL25-GUI-explorer, `01338e8ccc1c21d9897642ba197c6ac177e90118` | Adjacent MIT `LICENSE`, `NOTICE`, and `source-origin.json` |
| Aguvis protocol constants and reference CLI | xlang-ai/aguvis, `178c4187069d8aa028aaf00f209139824c00a76f` | `tests/fixtures/aguvis/upstream-pyproject.toml` preserves the upstream MIT declaration; `zhixing/prompts/AGUVIS-LICENSE` contains the MIT terms and attribution |
| SeeClick protocol/reference material | njucckevin/SeeClick, `0ef37ac4d7aaf37ba7b990e3e3c3ca77e1fb8f93` | `zhixing/prompts/SEECLICK-LICENSE` preserves the pinned Apache-2.0 license |

Selected definitions and documented adaptations remain identifiable through
their provenance records. Reference fixture code is inert test input rather
than newly authored framework code.

## Deliberately withheld integrations

The user selected a core-only release while redistribution terms remain
unverified for the following pinned ports:

| Integration | Pinned upstream |
| --- | --- |
| Agent-SAMA | pockyitachi/Agent-SAMA, `714a304843d2deb3403815a683071cb6e85ddd3d` |
| AndroidArena | AndroidArenaAgent/AndroidArena, `c06a141557ef310a9f3a3aeef9e7535ba0747087` |
| V-Droid | V-Droid-Agent/V-Droid, `8d549027634abe65a5721fe6bc3b5e84475db2f6` |
| MobA | OpenDFM/MobA, `05cd237d80fcd23ad0dd6096cdb144117ecb3471` |

No root license file was found in the inspected Git trees at these commits.
That observation is not a determination of the authors' ownership or permission
to grant a license. These implementations, their copied test fixtures and their
online examples are omitted until a suitable redistribution basis is recorded.

VisionTasker (`AkimotoAyako/VisionTasker`,
`d31b50e98bde28c0d1cfbc7d7ee2528d10b3fbb0`) carries GPL-3.0 and is not bundled
in this Apache core profile. This profile does not relicense that source.

See `release/public-manifest.json` for exact omissions. Upstream Benchmark media
and generated result corpora remain outside the core source boundary.
