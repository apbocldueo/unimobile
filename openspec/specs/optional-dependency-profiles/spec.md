# optional-dependency-profiles Specification

## Purpose
TBD - created by archiving change package-zhixing-python-core. Update Purpose after archive.
## Requirements
### Requirement: Lightweight base dependency set
The base `zhixing` distribution SHALL declare only dependencies needed for the stable package import, configuration contracts, package resources, and lightweight core observation/runtime support. It MUST NOT require Torch, Transformers, OpenCV, Harmony drivers, clipboard integration, or other capability-specific heavy stacks for a base installation.

#### Scenario: Install base distribution
- **WHEN** a user installs `zhixing` without extras
- **THEN** root imports, version access, package prompt access, and Agent YAML/Benchmark JSON validation work without installing heavy vision or Harmony dependencies

#### Scenario: Optional modules are absent
- **WHEN** the base environment does not contain an optional provider, vision, Harmony, or Benchmark-only library
- **THEN** importing `zhixing` and using base contract APIs still succeeds

### Requirement: Named optional capability profiles
The distribution SHALL define `openai`, `vision`, `harmony`, `benchmark`, and `all` extras. Each capability-specific third-party dependency MUST appear in its relevant profile, and `all` MUST be the union required to install every shipped optional capability.

#### Scenario: Install provider profile
- **WHEN** a user installs `zhixing[openai]`
- **THEN** the shipped OpenAI-compatible LLM plugin has its declared Python provider dependency available

#### Scenario: Install vision profile
- **WHEN** a user installs `zhixing[vision]`
- **THEN** the shipped components that directly use NumPy, OpenCV, HTTP requests, Torch, or Transformers have their declared Python dependencies available

#### Scenario: Install Harmony profile
- **WHEN** a user installs `zhixing[harmony]`
- **THEN** the shipped Harmony device adapter has its declared driver dependency available

#### Scenario: Install Benchmark profile
- **WHEN** a user installs `zhixing[benchmark]`
- **THEN** shipped Benchmark plugins that use host clipboard integration have their declared dependency available

#### Scenario: Install complete profile
- **WHEN** a user installs `zhixing[all]`
- **THEN** every dependency declared by the other supported runtime extras is included without requiring unused libraries

### Requirement: Dependency declarations reflect direct use
Distribution dependency metadata SHALL include every third-party package directly imported by shipped code in the appropriate base or optional profile. Packages with no direct current use MUST NOT remain mandatory merely because they appeared in the legacy flat requirements file.

#### Scenario: Audit shipped imports
- **WHEN** declared dependencies are compared with third-party imports in shipped modules
- **THEN** `requests` and `pyperclip` are covered by capability profiles and currently unused direct requirements such as DashScope, PyShine, TorchVision, and Ultralytics are not mandatory base dependencies

### Requirement: Optional discovery failure isolation
Missing optional dependencies SHALL affect only the plugins that require them. Plugin discovery MUST return sanitized module-level failures while continuing to register and expose independent available plugins.

#### Scenario: Discover without vision extras
- **WHEN** the base installation discovers built-in plugins and a vision plugin import requires an absent optional dependency
- **THEN** discovery records a sanitized failure for that module, continues scanning other modules, and does not misreport the entire distribution as unimportable

### Requirement: Development dependencies are separate
Test, build, metadata-check, and release-verification tools SHALL be declared separately from runtime dependencies so installing `zhixing` does not install pytest or packaging/release tooling.

#### Scenario: Inspect base environment
- **WHEN** a user installs only the base distribution
- **THEN** pytest, build frontends, and distribution upload/check tools are not installed solely because ZhiXing requires them

