# package-resource-resolution Specification

## Purpose
TBD - created by archiving change package-zhixing-python-core. Update Purpose after archive.
## Requirements
### Requirement: Central package resource service
The system SHALL provide one internal resource service for resolving and reading ZhiXing-owned text assets. Built-in Agent components MUST use this service instead of constructing repository-relative paths from the process working directory.

#### Scenario: Read a built-in prompt after wheel installation
- **WHEN** an installed component requests a known built-in prompt while the process runs outside the repository
- **THEN** the resource service reads the prompt from the installed `zhixing` distribution

#### Scenario: Change working directory
- **WHEN** the same prompt is requested from two different working directories
- **THEN** both calls return identical built-in content and neither call requires a local `zhixing/prompts` directory

### Requirement: Explicit external prompt override
Prompt-consuming components SHALL continue to accept an explicit existing user file as an override. An existing explicit file MUST take precedence over a packaged prompt with the same basename, while a non-path prompt name MUST resolve only inside the packaged prompt collection.

#### Scenario: Existing user override
- **WHEN** a caller supplies a path to an existing readable prompt file
- **THEN** the exact external file content is returned instead of the built-in prompt

#### Scenario: Built-in prompt name
- **WHEN** a caller supplies `reasoning_general.md` and no explicit file exists at that input
- **THEN** the packaged prompt named `reasoning_general.md` is returned

#### Scenario: Missing prompt
- **WHEN** neither an explicit readable file nor a packaged prompt matches the input
- **THEN** resolution fails with a deterministic error that identifies the requested prompt without exposing secrets

### Requirement: Resource API independent of physical installation layout
The resource service SHALL use Python package-resource APIs and MUST NOT assume that resources are ordinary files adjacent to the current checkout. Callers that need text MUST consume text directly; callers that genuinely require a filesystem path MUST use a managed materialization context.

#### Scenario: Non-directory package resource
- **WHEN** Python exposes a package resource through a traversable or temporary materialization rather than a permanent source path
- **THEN** the resource service can still read it and cleans up any temporary materialization according to its context lifetime

### Requirement: Complete retained package metadata
Any package-owned metadata used by a shipped `zhixing` module SHALL be version controlled and included in build artifacts. The retained Studio flow-template metadata SHALL no longer be silently omitted by the repository-wide dataset ignore rule.

#### Scenario: Installed Studio metadata lookup
- **WHEN** the shipped Studio template loader runs from an installed wheel
- **THEN** it can list and read the retained manifest, skeleton, and baseline template without accessing the source repository

#### Scenario: Build from a clean clone
- **WHEN** artifacts are built from a clean version-control checkout rather than the developer's existing workspace
- **THEN** all declared package metadata is present because it is tracked source input

