"""Tests for the installed graph-native command-line facade."""

from __future__ import annotations

import io
import json

from zhixing.catalog import (
    ComponentCatalog,
    DiscoveredComponentEnvironment,
    DiscoveryReport,
    PluginLoadFailure,
)
from zhixing.cli import main
from zhixing.components import (
    AgentState,
    BaseVerifier,
    ComponentBundle,
    ComponentBundleContractResult,
    ComponentCategory,
    ComponentContractResult,
    ComponentRole,
    ComponentSpec,
    RunResult,
    RunStatus,
    RuntimeContext,
    VerifierInput,
    VerifierResult,
)
from zhixing.graph import (
    BUILTIN_NODE_CONTRACT_CATALOG,
    GraphRole,
    contract_ref_for_role,
)


class SpyAgent:
    """Record CLI delegation to the public SDK run method."""

    canonical_hash = "sha256:test"

    def __init__(self) -> None:
        """Initialize captured calls.

        Args:
            None.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls: list[tuple[object, object]] = []

    def run(self, task: str, config: object) -> RunResult:
        """Return a successful structured result.

        Args:
            task (str): Resolved CLI task.
            config (object): Public AgentRunConfig.

        Raises:
            None.

        Returns:
            RunResult: Deterministic success result.
        """
        self.calls.append((task, config))
        return RunResult(
            run_id="cli-run",
            status=RunStatus.SUCCESS,
            state=AgentState(),
            kernel_status="success",
            artifact_namespace="cli-run",
        )


class _HealthyVerifier(BaseVerifier):
    """Small installed-component double for CLI diagnostics."""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Return one deterministic successful Contract Test Kit result.

        Args:
            input (VerifierInput): Standard verifier fixture.
            runtime (RuntimeContext): Fake runtime context.

        Raises:
            None.

        Returns:
            VerifierResult: Success when the fixture contains a task.
        """
        return VerifierResult(
            bool(input.task),
            metadata={"run_id": runtime.run_id},
        )


class _WrongVerifier(_HealthyVerifier):
    """Verifier double that violates its runtime output Contract."""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Return an intentionally invalid value.

        Args:
            input (VerifierInput): Standard verifier fixture.
            runtime (RuntimeContext): Fake runtime context.

        Raises:
            None.

        Returns:
            VerifierResult: Annotation is intentionally violated at runtime.
        """
        del input, runtime
        return "wrong"  # type: ignore[return-value]


class _Candidate:
    """Minimal metadata candidate used by explicit-load CLI tests."""

    provider_id = "cli-provider"


def _cli_spec(
    *,
    version: str = "1.0.0",
    implementation: type[BaseVerifier] = _HealthyVerifier,
) -> ComponentSpec:
    """Build one formal verifier specification for CLI tests.

    Args:
        version (str): Exact component version.
        implementation (type[BaseVerifier]): Runtime implementation class.

    Raises:
        AssertionError: The built-in verifier Contract is unavailable.

    Returns:
        ComponentSpec: Valid formal external component definition.
    """
    contract = BUILTIN_NODE_CONTRACT_CATALOG.resolve(
        contract_ref_for_role(GraphRole.VERIFIER)
    )
    assert contract is not None
    return ComponentSpec(
        namespace="cli.external",
        name="verifier",
        version=version,
        contract=contract,
        implementation=implementation,
        category=ComponentCategory.CORE_AGENT,
        role=ComponentRole.VERIFIER,
    )


def _cli_environment(
    *specifications: ComponentSpec,
    failures: tuple[PluginLoadFailure, ...] = (),
) -> DiscoveredComponentEnvironment:
    """Create one explicit discovery environment for CLI tests.

    Args:
        *specifications (ComponentSpec): Successfully loaded component definitions.
        failures (tuple[PluginLoadFailure, ...]): Provider loading failures.

    Raises:
        ComponentCatalogError: Test component definitions conflict.

    Returns:
        DiscoveredComponentEnvironment: Safe Catalog and report fixture.
    """
    bundles = (
        (("cli-provider", ComponentBundle(tuple(specifications))),)
        if specifications
        else ()
    )
    catalog = ComponentCatalog(bundles)
    loaded = ("cli-provider",) if specifications else ()
    return DiscoveredComponentEnvironment(
        catalog=catalog,
        report=DiscoveryReport(
            candidates=(),
            selected_provider_ids=("cli-provider",),
            skipped_provider_ids=(),
            loaded_provider_ids=loaded,
            failures=failures,
        ),
    )


def test_cli_non_interactive_run_delegates_to_public_sdk(monkeypatch, tmp_path) -> None:
    """Pass graph-native CLI arguments only through load_agent and run.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.
        tmp_path (pathlib.Path): Isolated artifact root.

    Raises:
        AssertionError: CLI duplicates or bypasses the public SDK.

    Returns:
        None.
    """
    spy = SpyAgent()
    loaded: list[tuple[object, object]] = []

    def fake_load(path: object, *, secrets: object) -> SpyAgent:
        """Capture the public SDK load call.

        Args:
            path (object): AgentGraph YAML path.
            secrets (object): Runtime-only secrets mapping.

        Raises:
            None.

        Returns:
            SpyAgent: Shared spy executable.
        """
        loaded.append((path, secrets))
        return spy

    monkeypatch.setattr("zhixing.cli.load_agent", fake_load)
    output = io.StringIO()
    error = io.StringIO()
    code = main(
        [
            "run",
            "--agent",
            "agent.yaml",
            "--instruction",
            "拍一张照片",
            "--serial",
            "emulator-5554",
            "--artifact-root",
            str(tmp_path),
        ],
        stdin=io.StringIO(),
        stdout=output,
        stderr=error,
    )
    assert code == 0
    assert loaded and str(loaded[0][0]).endswith("agent.yaml")
    assert spy.calls[0][0] == "拍一张照片"
    assert spy.calls[0][1].serial == "emulator-5554"
    assert "canonical_hash: sha256:test" in output.getvalue()
    assert "manifest.json" in output.getvalue()
    assert error.getvalue() == ""


def test_cli_reads_one_instruction_from_stdin_and_rejects_empty(monkeypatch) -> None:
    """Support the legacy-style single-task input interaction safely.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.

    Raises:
        AssertionError: Standard-input or empty-task behavior differs.

    Returns:
        None.
    """
    spy = SpyAgent()
    monkeypatch.setattr("zhixing.cli.load_agent", lambda path, secrets: spy)
    output = io.StringIO()
    assert (
        main(
            ["run", "--agent", "agent.yaml"],
            stdin=io.StringIO("打开相机\n"),
            stdout=output,
            stderr=io.StringIO(),
        )
        == 0
    )
    assert spy.calls[0][0] == "打开相机"
    error = io.StringIO()
    assert (
        main(
            ["run", "--agent", "agent.yaml"],
            stdin=io.StringIO("\n"),
            stdout=io.StringIO(),
            stderr=error,
        )
        == 2
    )
    assert "must not be empty" in error.getvalue()


def test_cli_component_list_is_metadata_only_and_json_safe(monkeypatch) -> None:
    """List provider provenance without loading provider code."""

    class Candidate:
        """Metadata-only candidate double for CLI serialization."""

        def to_safe_dict(self) -> dict[str, object]:
            """Return sanitized provider metadata.

            Returns:
                dict[str, object]: Safe provider metadata.
            """
            return {
                "provider_id": "fixture-provider",
                "target": "fixture:bundle",
                "origin": {
                    "distribution": "fixture-components",
                    "version": "1.0.0",
                    "source_kind": "index",
                    "vcs": "",
                    "requested_revision": "",
                    "commit_id": "",
                },
            }

    monkeypatch.setattr(
        "zhixing.cli.enumerate_component_plugins",
        lambda: (Candidate(),),
    )
    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("metadata-only list loaded provider code")
        ),
    )
    output = io.StringIO()
    code = main(
        ["components", "list", "--json"],
        stdout=output,
        stderr=io.StringIO(),
    )
    assert code == 0
    payload = json.loads(output.getvalue())
    assert payload["mode"] == "metadata-only"
    assert payload["candidates"][0]["provider_id"] == "fixture-provider"


def test_cli_run_forwards_external_provider_controls(monkeypatch) -> None:
    """Forward CLI discovery policy to the same public SDK bootstrap."""
    spy = SpyAgent()
    calls: list[dict[str, object]] = []

    def fake_load(path: object, **options: object) -> SpyAgent:
        """Capture SDK discovery controls.

        Args:
            path (object): Agent YAML path.
            **options (object): Public load_agent options.

        Returns:
            SpyAgent: Successful run fixture.
        """
        del path
        calls.append(dict(options))
        return spy

    monkeypatch.setattr("zhixing.cli.load_agent", fake_load)
    code = main(
        [
            "run",
            "--agent",
            "agent.yaml",
            "--instruction",
            "task",
            "--no-external-plugins",
            "--plugin-provider",
            "allowed",
            "--disable-plugin-provider",
            "blocked",
        ],
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert code == 0
    assert calls[0]["discover_external"] is False
    assert calls[0]["plugin_allowlist"] == ("allowed",)
    assert calls[0]["plugin_denylist"] == ("blocked",)


def test_cli_component_inspect_outputs_safe_metadata(monkeypatch) -> None:
    """Resolve one explicit version and serialize no implementation objects.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.

    Raises:
        AssertionError: Inspect bypasses Catalog resolution or leaks objects.

    Returns:
        None.
    """
    monkeypatch.setattr(
        "zhixing.cli.enumerate_component_plugins",
        lambda: (_Candidate(),),
    )
    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: _cli_environment(_cli_spec()),
    )
    output = io.StringIO()
    code = main(
        [
            "components",
            "inspect",
            "cli.external:verifier@1.0.0",
            "--json",
            "--plugin-provider",
            "cli-provider",
        ],
        stdout=output,
        stderr=io.StringIO(),
    )
    payload = json.loads(output.getvalue())
    assert code == 0
    assert payload["component"]["component"]["identifier"] == (
        "cli.external:verifier@1.0.0"
    )
    contract = payload["component"]["component"]["contract"]
    assert contract["adapter"] == "core_role"
    assert contract["ports"]
    assert contract["features"]["fallback"] is True
    assert "implementation" not in output.getvalue()
    assert "factory" not in output.getvalue()

    text_output = io.StringIO()
    assert (
        main(
            [
                "components",
                "inspect",
                "cli.external:verifier@1.0.0",
                "--plugin-provider",
                "cli-provider",
            ],
            stdout=text_output,
            stderr=io.StringIO(),
        )
        == 0
    )
    assert "adapter: core_role" in text_output.getvalue()
    assert "port input task:" in text_output.getvalue()


def test_cli_component_inspect_reports_ambiguity_and_rejects_urls(
    monkeypatch,
) -> None:
    """Return safe non-zero errors for ambiguous identities and Git URLs.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.

    Raises:
        AssertionError: Inspect chooses a version or attempts URL discovery.

    Returns:
        None.
    """
    calls = []
    monkeypatch.setattr(
        "zhixing.cli.enumerate_component_plugins",
        lambda: calls.append("enumerated") or (_Candidate(),),
    )
    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: _cli_environment(
            _cli_spec(version="1.0.0"),
            _cli_spec(version="2.0.0"),
        ),
    )
    ambiguous = io.StringIO()
    assert (
        main(
            ["components", "inspect", "cli.external:verifier", "--json"],
            stdout=ambiguous,
            stderr=io.StringIO(),
        )
        == 2
    )
    assert json.loads(ambiguous.getvalue())["error"]["code"] == (
        "component.catalog_version_ambiguous"
    )

    calls.clear()
    rejected = io.StringIO()
    assert (
        main(
            [
                "components",
                "inspect",
                "git+https://user:token@example.test/plugin.git",
                "--json",
            ],
            stdout=rejected,
            stderr=io.StringIO(),
        )
        == 2
    )
    assert calls == []
    encoded = rejected.getvalue()
    assert "token" not in encoded
    assert "example.test" not in encoded


def test_cli_component_doctor_distinguishes_health_and_contract_failure(
    monkeypatch,
) -> None:
    """Use stable exit codes for healthy and runtime-invalid bundles.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.

    Raises:
        AssertionError: Doctor omits aggregate results or uses one exit code.

    Returns:
        None.
    """
    monkeypatch.setattr(
        "zhixing.cli.enumerate_component_plugins",
        lambda: (_Candidate(),),
    )
    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: _cli_environment(_cli_spec()),
    )
    healthy = io.StringIO()
    assert (
        main(
            ["components", "doctor", "--json"],
            stdout=healthy,
            stderr=io.StringIO(),
        )
        == 0
    )
    assert json.loads(healthy.getvalue())["providers"][0]["passed"]
    assert json.loads(healthy.getvalue())["providers"][0]["health"] == "verified"

    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: _cli_environment(
            _cli_spec(implementation=_WrongVerifier)
        ),
    )
    invalid = io.StringIO()
    assert (
        main(
            ["components", "doctor", "--json"],
            stdout=invalid,
            stderr=io.StringIO(),
        )
        == 3
    )
    payload = json.loads(invalid.getvalue())
    assert not payload["ok"]
    diagnostic = payload["providers"][0]["components"][0]["diagnostics"][0]
    assert diagnostic["phase"] == "invocation"


def test_cli_component_doctor_exposes_structural_only_health(
    monkeypatch,
) -> None:
    """Distinguish skipped invocation from fully verified component behavior.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.

    Raises:
        AssertionError: Doctor hides skipped checks or calls them verified.

    Returns:
        None.
    """
    monkeypatch.setattr(
        "zhixing.cli.enumerate_component_plugins",
        lambda: (_Candidate(),),
    )
    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: _cli_environment(_cli_spec()),
    )
    monkeypatch.setattr(
        "zhixing.cli.check_component_bundle",
        lambda *args, **kwargs: ComponentBundleContractResult(
            schema_version="1.0",
            provider_id="cli-provider",
            components=(
                ComponentContractResult(
                    component_id="cli.external:verifier@1.0.0",
                    contract="zhixing.core.verifier@1.0",
                    checks=("definition", "construction"),
                    skipped=("invocation:fixture_required",),
                ),
            ),
        ),
    )
    output = io.StringIO()
    assert (
        main(
            ["components", "doctor", "--json"],
            stdout=output,
            stderr=io.StringIO(),
        )
        == 0
    )
    provider = json.loads(output.getvalue())["providers"][0]
    assert provider["health"] == "structural-only"
    assert provider["skipped_count"] == 1


def test_cli_component_doctor_reports_provider_load_failure_safely(
    monkeypatch,
) -> None:
    """Preserve provider-stage evidence without leaking exception text.

    Args:
        monkeypatch (pytest.MonkeyPatch): Runtime patch fixture.

    Raises:
        AssertionError: Doctor hides provider failure or exposes a secret.

    Returns:
        None.
    """
    monkeypatch.setattr(
        "zhixing.cli.enumerate_component_plugins",
        lambda: (_Candidate(),),
    )
    failure = PluginLoadFailure(
        provider_id="cli-provider",
        stage="load",
        code="plugin.provider_load_failed",
        error_type="ImportError",
        message="Provider loading failed (ImportError).",
    )
    monkeypatch.setattr(
        "zhixing.cli.load_component_plugins",
        lambda *args, **kwargs: _cli_environment(failures=(failure,)),
    )
    output = io.StringIO()
    assert (
        main(
            ["components", "doctor", "--json"],
            stdout=output,
            stderr=io.StringIO(),
        )
        == 2
    )
    payload = json.loads(output.getvalue())
    assert payload["report"]["failures"][0]["provider_id"] == "cli-provider"
    assert "traceback" not in output.getvalue().lower()
