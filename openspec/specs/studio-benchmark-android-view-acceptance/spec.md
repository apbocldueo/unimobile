# studio-benchmark-android-view-acceptance Specification

## Purpose
Define the gated, bounded evidence required to prove that the real Studio browser journey truthfully presents representative fresh Android execution, historical Replay, and fake-fixture provenance without changing runtime semantics or broadening product claims.
## Requirements
### Requirement: Real-browser acceptance must be gated by completed service evidence
Stage 5.6C-2 SHALL require a successfully completed Stage 5.6C-1 campaign covering the exact positive and controlled-negative matrix, managed evidence closure, restart non-replay, and redaction gates before any browser-driven real-Android Experiment begins. An archived change, automated test pass, profile label, historical run, or incomplete acceptance summary MUST NOT satisfy this prerequisite.

#### Scenario: Completed service campaign is supplied
- **WHEN** the operator selects a bounded 5.6C-1 summary whose two scenarios and all required gates are complete and internally consistent
- **THEN** browser acceptance may bind the same safe profile, Package/task, Protocol, repeat, platform context, and immutable Agent revisions for its own isolated journey

#### Scenario: Service evidence is absent or incomplete
- **WHEN** the 5.6C-1 positive run, controlled-negative run, restart proof, managed closure, or security scan is missing or failed
- **THEN** Stage 5.6C-2 stops before browser create, Worker, model, initializer, evaluator, or Android effects and remains incomplete

### Requirement: The browser must create and observe the bounded real-Android matrix through production resources
The accepted journey SHALL use an actual browser connected to the real Studio backend and SHALL traverse Catalog, Composer preview/create, Monitor, Report/Evidence, Replay, and Export through their authoritative routes and links. It MUST create two isolated `1 Agent × 1 Task × 1 repeat` Experiments using the same bounded selections as the accepted service matrix: one representative positive revision and one controlled-negative revision that ends normally without completing the task.

#### Scenario: Positive browser Experiment completes
- **WHEN** the operator selects the approved Package/task, Protocol, positive immutable Agent revision, and safe profile in Composer and confirms the previewed definition
- **THEN** the browser follows the created Experiment to one terminal TaskRun with Agent `SUCCESS`, Benchmark `PASS`, evaluator `PASS`, and fresh real-Android source provenance supplied by authoritative resources

#### Scenario: Controlled-negative browser Experiment completes
- **WHEN** the declared device precondition is restored and the operator creates the approved controlled-negative definition through Composer
- **THEN** the browser follows one normally completed TaskRun with Agent `SUCCESS`, Benchmark `FAIL`, evaluator `FAIL`, `INVALID=0`, and no UI claim that infrastructure failure or missing evidence is an accepted negative

### Requirement: Monitor reconstruction must preserve durable identity and event continuity
Monitor SHALL preserve the authoritative Experiment and TaskRun identities across SSE disconnect, `Last-Event-ID` recovery, terminal drain, route refresh, and page reconstruction. It SHALL expose independent service lifecycle, Agent status, Benchmark outcome, event cursor/high-water facts, publication availability, and source evidence origin; it MUST NOT reconstruct execution from local buffers, duplicate confirmed events, or trigger another source execution.

#### Scenario: SSE disconnects after a committed event
- **WHEN** the browser connection is interrupted and then restored after at least one durable Experiment event
- **THEN** Monitor backfills from the authoritative cursor, reaches the same terminal high-water mark without a semantic gap or duplicate, and retains the same Experiment and TaskRun identities

#### Scenario: Terminal Monitor route is refreshed
- **WHEN** the operator reloads the terminal Monitor route after publication
- **THEN** the page reconstructs the same TaskRun, outcomes, provenance, Replay capability, and publication facts from the backend without rerunning initializer, Agent, evaluator, or Android actions

### Requirement: Report and Evidence must keep independent facts and exact scope
Report SHALL restore the selected TaskRun through URL-owned identity, display service lifecycle, Agent status, and Benchmark outcome as independent axes, render the bounded Evaluation Tree without claiming automatic diagnosis, and open managed evidence only through exact same-Experiment and same-TaskRun capabilities. Missing, corrupt, redacted, hidden, truncated, oversized, download-only, or scope-conflicting evidence MUST remain distinguishable and MUST NOT be replaced with cached or inferred content.

#### Scenario: Positive and controlled-negative reports differ by outcome
- **WHEN** the operator opens each terminal Experiment report and its selected TaskRun
- **THEN** both reports retain normal service/Agent completion while independently presenting PASS versus FAIL evaluator and Benchmark facts plus their exact Evaluation evidence

#### Scenario: Evidence capability is unavailable or cross-scoped
- **WHEN** an Evaluation reference has no readable exact capability or resolves outside the selected Experiment and TaskRun
- **THEN** Evidence Viewer fails closed locally, preserves the remaining verified report facts, and does not construct another URL or claim that the evaluator result was reverified

### Requirement: Every surface must present authoritative provenance without inference
Composer, Monitor, Report/Evidence, Replay, and Export context SHALL preserve the distinction among source acquisition, source environment, and whether the current resource is fresh device evidence. Fresh accepted source results SHALL be labeled `fresh_execution / real_android / realDeviceEvidence=true`; native Replay SHALL be labeled `replay_projection / real_android / realDeviceEvidence=false`; fake acceptance fixtures SHALL remain `contract_fixture / fake_device / realDeviceEvidence=false`. A URL, title, task name, safe profile ID, screenshot, phone rendering, artifact provenance string, or prior page state MUST NOT upgrade these facts.

#### Scenario: Fresh source result is inspected across Monitor and Report
- **WHEN** an accepted real-Android TaskResult is selected
- **THEN** both surfaces present its authoritative fresh acquisition, real environment, and true source-evidence flag without collapsing them into a generic success badge

#### Scenario: Historical Replay of the same real run is opened
- **WHEN** the operator follows the native Replay capability from that TaskRun
- **THEN** Replay explicitly explains that the source environment was real Android while the current view is a historical projection and therefore is not a new fresh-device execution

#### Scenario: Fake fixture is displayed
- **WHEN** the supporting fake/no-device fixture is opened in the same acceptance campaign
- **THEN** every relevant surface retains fake-device and non-real evidence labels and cannot be mistaken for either the fresh real result or its historical Replay

### Requirement: Replay must retain causal source identity and read-only evidence semantics
Native Replay SHALL reload its own persistent envelope through the authoritative Replay route, retain the owning Experiment/TaskRun and source evidence environment, and keep read-only timeline, graph, phone, Inspector, and artifact projection bounded by verified managed evidence. Replay MUST NOT connect to a device, resume the Agent, repeat an action, present itself as live observation, or promote `realDeviceEvidence` to true.

#### Scenario: Native Replay is opened from Report
- **WHEN** the selected TaskRun exposes an available native Replay identity
- **THEN** the browser loads the same causal run envelope, shows `replay_projection / real_android / false`, and projects only its verified evidence prefix

#### Scenario: Replay route is refreshed
- **WHEN** the operator reloads or directly opens the Replay URL
- **THEN** the view reconstructs from the persistent envelope with unchanged identities and no Worker, model, plugin, initializer, evaluator, or device action

### Requirement: Export must preserve browser-owned handoff authority
Export SHALL use the existing closed inventory, strict publication manifest, refresh-plus-HEAD preparation, and exact scoped content capability for the selected real-Android Experiment. The UI SHALL distinguish prepared metadata from browser handoff and MUST NOT claim download completion, local persistence, digest verification after GET, bundle verification, or new execution evidence.

#### Scenario: Managed artifact is prepared and handed off
- **WHEN** the operator prepares an available report, trajectory, manifest, bundle, or evidence member and then chooses browser handoff
- **THEN** current metadata and HEAD facts are verified against the exact capability before ordinary browser navigation, while the UI reports only that control was handed to the browser

#### Scenario: Artifact becomes missing or corrupt
- **WHEN** authoritative refresh or HEAD reveals a missing, corrupt, or header-conflicting target
- **THEN** that target fails locally without enabling handoff, changing other candidates, republishing evidence, or rerunning the Experiment

### Requirement: Browser evidence and diagnostics must not expose private authority
The acceptance campaign SHALL retain only bounded safe route identities, causal resource identities, DOM assertions, screenshots, network metadata, console observations, commands, and claim limits. Raw serials, ADB arguments, trusted configuration paths, private fingerprints, target keys, secrets, live objects, host absolute paths, unsafe artifact bodies, and unredacted exception text MUST NOT enter the browser URL, DOM, storage, console, screenshot, trace, download name, proof ledger, or permanent documentation.

#### Scenario: Browser surfaces and evidence are scanned
- **WHEN** both real journeys, fake-fixture comparison, refresh/reconnect, Replay, Evidence, and Export checks finish
- **THEN** the bounded browser evidence contains only safe profile and provenance facts and no private target or secret material

#### Scenario: Backend error contains a private value
- **WHEN** a request or stream failure includes sensitive internal authority text
- **THEN** the browser renders only the existing structured safe failure and the retained console/trace evidence excludes the private value

### Requirement: Completion evidence must remain narrow and reproducible
Stage 5.6C-2 SHALL produce a versioned machine-readable proof ledger and permanent handoff only after both browser-driven real scenarios, provenance comparison, reconnect/refresh, report/evidence, Replay, Export, security, frontend regression, and actual-browser gates pass. The handoff SHALL bind claims to the selected device, locale/orientation, App versions, Package/task/Protocol, immutable Agent revisions, browser/backend versions, and single-repeat configuration, and MUST NOT claim broad Android compatibility, arbitrary task or Agent success, model quality, statistical significance, automatic diagnosis, or expanded Worker cardinality.

#### Scenario: Automated UI regressions pass without fresh browser evidence
- **WHEN** unit/component tests and fake browser fixtures pass but either real browser scenario or its operator observations are absent
- **THEN** Stage 5.6C-2 remains incomplete and permanent documentation does not mark Stage 5.6 finished

#### Scenario: All bounded browser gates pass
- **WHEN** the complete C-1 prerequisite and every C-2 browser, provenance, integrity, reconstruction, security, and regression gate pass with retained reproducible evidence
- **THEN** the milestone is reported only as bounded real-Android Studio browser acceptance for the selected matrix and Stage 5.6 may be marked complete with the stated limitations

