# python-package-distribution Specification

## Purpose
TBD - created by archiving change package-zhixing-python-core. Update Purpose after archive.
## Requirements
### Requirement: Canonical Python distribution identity
The project SHALL build a Python distribution named `zhixing` whose import package is also `zhixing`. The distribution MUST declare version `0.1.0`, Apache-2.0 licensing, and a minimum supported Python version of 3.10 through standard project metadata.

#### Scenario: Inspect installed metadata
- **WHEN** an installer or metadata reader inspects a built ZhiXing artifact
- **THEN** it reports distribution name `zhixing`, version `0.1.0`, Apache-2.0 licensing, and `Requires-Python >=3.10`

#### Scenario: Unsupported Python version
- **WHEN** pip resolves the distribution under Python 3.9 or earlier
- **THEN** installation is rejected by distribution metadata before importing ZhiXing code

### Requirement: Stable root import surface
The installed `zhixing` root package SHALL expose `__version__`, `AgentConfig`, `BenchmarkTask`, `BenchmarkSuite`, and `ValidationIssue`. Importing the root package MUST NOT perform plugin discovery, connect to a device, read secrets, create runtime output directories, or import optional model/device stacks.

#### Scenario: Import from a clean process
- **WHEN** a process with only base dependencies executes `import zhixing`
- **THEN** import succeeds, `zhixing.__version__` matches installed distribution metadata, and no device, network, model, or filesystem-output side effect occurs

#### Scenario: Import stable contract types
- **WHEN** a caller imports the documented contract types from `zhixing`
- **THEN** the values resolve to the existing canonical Agent and Benchmark contract classes

### Requirement: Standard wheel and source artifacts
The project SHALL produce a platform-independent wheel and a standards-compliant source distribution from `pyproject.toml`. A wheel rebuilt from the source distribution MUST provide the same documented root imports and package resources as the directly built wheel.

#### Scenario: Build release artifacts
- **WHEN** the documented build command runs from a clean source checkout
- **THEN** it produces `zhixing-0.1.0-py3-none-any.whl` and `zhixing-0.1.0.tar.gz` artifacts that pass distribution metadata checks

#### Scenario: Rebuild from source distribution
- **WHEN** the source distribution is unpacked and used as the only build input
- **THEN** a valid ZhiXing wheel can be built and passes the same isolated import and resource checks

### Requirement: Deliberate artifact contents
The wheel SHALL contain the ZhiXing Python packages, built-in prompts, and retained package-owned metadata required by shipped modules. It MUST NOT contain secrets, `.env` files, local datasets, examples, tests, OpenSpec artifacts, frontend `node_modules`, screenshots, logs, caches, or other generated runtime outputs.

#### Scenario: Inspect wheel manifest
- **WHEN** the wheel file list is inspected
- **THEN** all declared Python modules and package resources are present and every prohibited repository/runtime path is absent

#### Scenario: Secret-like repository files exist locally
- **WHEN** a developer builds artifacts in a checkout containing `secrets.yaml` or `.env` files
- **THEN** those files are absent from both the wheel and source distribution

### Requirement: Installed configuration contract support
An installed base distribution SHALL load and validate canonical Agent YAML and Benchmark JSON using the existing V1 contracts from an arbitrary working directory. Packaging MUST NOT merge, replace, or weaken the two format-specific contracts.

#### Scenario: Load Agent YAML outside the repository
- **WHEN** a clean environment installs the wheel, changes to a directory outside the source checkout, and loads a valid Agent YAML file
- **THEN** `load_agent_yaml` returns the canonical `AgentConfig` without relying on repository paths or device access

#### Scenario: Load Benchmark JSON outside the repository
- **WHEN** the same environment loads a valid Benchmark JSON suite
- **THEN** `load_benchmark_json` returns the canonical `BenchmarkSuite` without treating JSON as Agent YAML or accessing benchmark/device runtime services

### Requirement: Isolated installation verification
Release verification SHALL install the built wheel into a fresh environment outside the repository with repository import paths removed. Verification MUST prove that imports originate from the installed artifact and MUST run metadata, contract-loader, package-resource, and dependency-consistency checks.

#### Scenario: Repository shadowing is unavailable
- **WHEN** isolated verification changes to a temporary empty directory and clears repository path injection
- **THEN** `zhixing.__file__` resolves inside the test environment's installed packages and all acceptance checks still pass

#### Scenario: Dependency consistency
- **WHEN** the base wheel and its declared dependencies are installed
- **THEN** the environment's package consistency check reports no missing or conflicting required dependency

