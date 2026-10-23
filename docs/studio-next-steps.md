# Find your next step in Studio

[完整中文](studio-next-steps.zh-CN.md)

Start with an official example, change one capability, validate it, and save a
revision. Configure a model and an Android target only when you intend to run it.
Creating and validating a definition does not require a connected phone or a key.

## Open a working example

Run the backend from the repository root in the `unimobile` environment:

```bash
conda run -n unimobile --no-capture-output python -m zhixing.studio serve
```

In another terminal:

```bash
cd studio
npm ci
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Open `http://127.0.0.1:5173/`. Keep both processes running. Use the expected
frontend origin; an arbitrary port can fail the backend's origin check. If the
port is occupied, inspect the existing service rather than stopping it blindly.

Choose **从示例开始** (Start from an example), enter an Agent name and create it
from the official template. **创建空白 Agent** remains available for building
from scratch. Returning users can open their latest Agent; a historical revision
may be read-only under current policy and is never silently migrated.

The left palette lists available capabilities; the center shows this Agent's
actual instances. Click a capability to add it in the visible canvas, or drag it
to your chosen position. Select a node to inspect its exact implementation and
dependencies on the right. The system Input/Output boundaries are not ordinary
deletable capabilities.

## Resolve an editing or validation problem

Click **Validate**. Read the problem and proposed next step; expand **Technical
details** for the compiler code and severity. **Show object** appears only when
the location is trustworthy. Some errors are document-level: do not infer that
Studio has identified a field when the UI says it has not.

For a missing LLM dependency, inspect that capability's dependency configuration.
The LLM is a dependency, not another canvas node. Use the selected Catalog
implementation's contract for the exact provider/version, model and SecretRef
fields. Do not repair this by adding hidden runtime/control nodes.

Malformed JSON stays in its editor. Correct brackets, quotes and commas before
Validate, Save or Export; these actions must not silently use the previous value.
Navigation protection retains unfinished input. Viewing an error does not save
or modify the graph. After editing, validate again: the previous result does not
describe your new draft.

Save with **Save revision** and wait for acknowledgement. A saved incomplete graph
can still be invalid. If saving conflicts with another tab, preserve your local
work and explicitly reload or Save As; do not assume the remote revision was
overwritten. Refresh only after saving or accepting the unsaved-work warning.

## Configure the server, not the graph, with credentials

The graph contains identities such as `{"secret_ref":"api_key"}` and
`{"secret_ref":"base_url"}`. The server operator stores the corresponding
values in a private YAML scalar mapping outside Git:

```yaml
api_key: replace-with-your-local-value
base_url: https://your-openai-compatible-endpoint/v1
```

These are placeholders, not usable credentials. Restrict the file's permissions
to its owner. Never paste real values into graph JSON/YAML, screenshots, issues,
URLs or browser storage. Provider packages must be installed in the environment
running Studio; viewing Help does not install anything.

## Prepare an explicit device profile

Start your intended emulator or authorize a test device, then use `adb devices`
as the server operator to identify the exact target. Do not select a random device
when several are connected. A private server JSON file has this shape:

```json
{
  "schemaVersion": 1,
  "profiles": [{
    "deviceProfileId": "research-android",
    "label": "Research Android",
    "platform": "android",
    "target": {"kind": "adb_serial", "serial": "replace-with-exact-target"}
  }]
}
```

Stop your own development backend before restarting it with the intended files;
do not interrupt active experiments. Substitute private paths in this command:

```bash
conda run -n unimobile --no-capture-output python -m zhixing.studio serve \
  --host 127.0.0.1 --port 8765 \
  --secrets /absolute/private/path/secrets.yaml \
  --device-profile-config /absolute/private/path/device-profiles.json
```

Open **Settings → 运行环境** and refresh. The page is read-only: it shows provider
availability, SecretRef identities and safe profile IDs, never their credential
values or raw ADB serials. An empty list, a failed query and a check still running
are different states. Use the checklist's instructions and retry the query after
fixing configuration. Full service details: [Run readiness](studio-agent-run-readiness.md).

## Run, or benchmark, deliberately

For an ordinary **Run**, save a valid current-policy revision, choose the safe
profile and enter your task. **Recheck configuration only** does not create a Run.
Only an explicit run action can submit it through the existing authoritative
checks. Ordinary Run does **not** require a Benchmark Package.

For a **Benchmark Experiment**, choose an available Catalog Package, saved Agent
revision and supported profile/protocol in the existing Composer. Inspect its
preview before creating the Experiment. If there are no matches, clear filters;
if the query failed, retry. If the Catalog really is empty, create/import a draft
through Benchmark authoring and follow validation, freeze and explicit publication.
A draft is not a published Catalog entry. The Studio worker remains limited to
one Agent × one Task × one repeat; this is separate from Core multi-cardinality support.

| Observation | What it proves |
| --- | --- |
| Graph valid | The definition passed compilation checks. |
| Revision saved | That document snapshot was persisted. |
| Provider/profile configured | Static configuration exists, not live connectivity. |
| Exact revision ready | That revision's static prerequisites passed at check time. |
| Run accepted | A durable request was accepted, not that the task succeeded. |
| Terminal outcome with evidence | The recorded execution result, within its actual scope. |

Device disconnection, target contention, model access and task failures can still
happen after readiness passes. Inspect the real Run/Experiment status and evidence;
Replay describes recorded evidence, not current device state.

## Help and publication scope

Open **Help** or a contextual preparation link. English is the default; switching
to 简体中文 retains the topic and gives the complete translated instructions.
External links point to verified published articles with their actual scope noted.
For example, the secrets article covers CLI binding while these local instructions
explain Studio server configuration. Existing website screenshots may show an
earlier version. This guide and the frontend change have not published new Pages content.
