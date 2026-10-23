# Canonical Benchmark V1 suites

These JSON arrays are the version-controlled Benchmark contract fixtures:

- `android_world.json` — retained from `data/AndroidWorld/AndroidWorld_end.json`
- `android_world_missing.json` — retained from `data/AndroidWorld/AndroidWorld_missing.json`
- `app_agent.json` — retained from `data/AppAgent/AppAgent_end.json`

The V1 contract deliberately rejects the old `task`, `params_config`,
`setup_config`, `eval_type`, and plugin-level `type` shapes. The following
legacy local configuration files were removed after the retained suites passed
contract validation:

- `data/AndroidWorld/AndroidWorld.json`
- `data/AppAgent/AppAgent.json`
- `data/MobilEval/MobileEval.json`
- `data/SPA_Bench/cross_app_CHN.json`
- `data/SPA_Bench/cross_app_ENG.json`
- `data/SPA_Bench/single_app_CHN.json`
- `data/SPA_Bench/single_app_ENG.json`
- `data/myData.json`
- `data/test.json`

Canonical-shape development chunks under `data/**/chunkData` and `run*.json`
are not part of this fixture set, but they were not deleted because they do not
use the rejected legacy contract and may still be useful for local experiments.
