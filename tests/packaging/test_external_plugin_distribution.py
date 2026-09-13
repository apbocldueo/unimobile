"""Isolated installation acceptance for the external component protocol."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap
import venv
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples" / "external_component_plugin"
EXAMPLE_YAML = EXAMPLE / "agents" / "run-labeler.yaml"
EXAMPLE_SDK = EXAMPLE / "sdk_example.py"


def _run(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run an isolated packaging command with an assertion-friendly failure.

    Args:
        command (list[str]): Exact subprocess arguments.
        cwd (Path): Unrelated working directory.
        environment (dict[str, str] | None): Optional clean process environment.

    Returns:
        subprocess.CompletedProcess[str]: Successful captured process.
    """
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    return completed


def _metadata_acceptance_script(expected_source: str) -> str:
    """Build the installed provider metadata and Contract acceptance script.

    Args:
        expected_source (str): Expected sanitized origin kind.

    Returns:
        str: Python program executed outside the repository.
    """
    return f"""
from zhixing.catalog import enumerate_component_plugins, load_component_plugins
from zhixing.components import check_component_bundle
from zhixing.graph import GraphComponentRef
candidates = enumerate_component_plugins()
fixture = [item for item in candidates if item.provider_id == 'zhixing-example']
assert len(fixture) == 1, [item.to_safe_dict() for item in candidates]
assert fixture[0].origin.source_kind == {expected_source!r}, fixture[0].origin.to_safe_dict()
environment = load_component_plugins(candidates, allowlist=('zhixing-example',))
assert environment.catalog.providers() == ('zhixing-example',)
assert {{
    item.specification.identifier
    for item in environment.catalog.entries()
}} == {{
    'example.external:run_labeler@1.0.0',
    'example.external:task_run_labeler@1.0.0',
}}
entry = environment.catalog.resolve(GraphComponentRef(
    namespace='example.external',
    name='run_labeler',
    version='1.0.0',
))
from zhixing.components import ComponentBundle
result = check_component_bundle(
    ComponentBundle((entry.specification,)),
    provider_id='zhixing-example',
    fixtures={{
        entry.specification.identifier: {{
            'input_value': 'hello',
        }},
    }},
)
assert result.passed, result.to_safe_dict()
assert not environment.report.failures
print(entry.specification.identifier)
"""


def _missing_plugin_script(yaml_path: Path) -> str:
    """Build a preflight assertion for an environment without the plugin.

    Args:
        yaml_path (Path): External-component AgentGraph YAML path.

    Raises:
        None.

    Returns:
        str: Python program proving failure occurs before runtime startup.
    """
    return f"""
from zhixing import load_agent
from zhixing.runtime import GraphBindingError
try:
    load_agent({str(yaml_path)!r})
except GraphBindingError as error:
    assert error.info.code in {{'sdk.compilation_failed', 'sdk.graph_invalid', 'sdk.component_unknown'}}
    assert error.info.phase in {{'compilation', 'validation', 'preflight'}}
else:
    raise AssertionError('external graph loaded without its provider')
"""


def _prepare_git_source(tmp_path: Path) -> tuple[Path, str]:
    """Copy the example into a standalone local Git repository.

    Args:
        tmp_path (Path): Isolated test root.

    Raises:
        AssertionError: Git initialization or commit creation fails.

    Returns:
        tuple[Path, str]: Repository path and fixed commit ID.
    """
    repository = tmp_path / "git-plugin"
    shutil.copytree(EXAMPLE, repository)
    _run(["git", "init"], cwd=repository)
    _run(["git", "config", "user.email", "fixture@example.test"], cwd=repository)
    _run(["git", "config", "user.name", "ZhiXing Fixture"], cwd=repository)
    _run(["git", "add", "."], cwd=repository)
    _run(["git", "commit", "-m", "external plugin fixture"], cwd=repository)
    commit = _run(["git", "rev-parse", "HEAD"], cwd=repository).stdout.strip()
    return repository, commit


def _build_negative_provider_wheel(tmp_path: Path) -> Path:
    """Build one standalone distribution with three diagnostic providers.

    Args:
        tmp_path (Path): Isolated source and wheel output root.

    Raises:
        AssertionError: Source creation or wheel construction fails.

    Returns:
        Path: Wheel containing load-failure, invalid-Bundle, and
            invocation-failure Entry Points.
    """
    source = tmp_path / "negative-plugin"
    package = source / "src" / "zhixing_acceptance_broken"
    distribution = tmp_path / "negative-dist"
    package.mkdir(parents=True)
    distribution.mkdir()
    (source / "pyproject.toml").write_text(
        textwrap.dedent(
            """
            [build-system]
            requires = ["hatchling>=1.26,<2"]
            build-backend = "hatchling.build"

            [project]
            name = "zhixing-acceptance-broken"
            version = "1.0.0"
            requires-python = ">=3.10"
            dependencies = ["zhixing>=0.1,<0.2"]

            [project.entry-points."zhixing.components"]
            provider-load-failure = "missing_acceptance_provider:bundle"
            invalid-bundle = "zhixing_acceptance_broken:INVALID_BUNDLE"
            contract-failure = "zhixing_acceptance_broken:bundle"

            [tool.hatch.build.targets.wheel]
            packages = ["src/zhixing_acceptance_broken"]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (package / "__init__.py").write_text(
        textwrap.dedent(
            '''
            """Deliberately broken providers used by installed acceptance tests."""

            from zhixing.components import (
                ComponentBundle,
                ComponentRole,
                RuntimeContext,
                VerifierInput,
                VerifierResult,
                component,
                get_component_spec,
            )


            @component(
                namespace="acceptance.broken",
                name="contract_failure",
                role=ComponentRole.VERIFIER,
            )
            def broken_verifier(
                input: VerifierInput,
                runtime: RuntimeContext,
            ) -> VerifierResult:
                """Raise a credential-shaped message to test safe diagnostics.

                Args:
                    input (VerifierInput): Standard side-effect-free fixture.
                    runtime (RuntimeContext): Isolated Contract Test Kit runtime.

                Raises:
                    RuntimeError: Always, with text that must be redacted.

                Returns:
                    VerifierResult: This deliberately broken fixture never returns.
                """
                del input, runtime
                raise RuntimeError(
                    "https://user:fixture-token@example.test/private"
                )


            specification = get_component_spec(broken_verifier)
            assert specification is not None
            bundle = ComponentBundle((specification,))
            INVALID_BUNDLE = "not-a-component-bundle"
            '''
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(distribution),
            str(source),
        ],
        cwd=ROOT,
    )
    return next(distribution.glob("zhixing_acceptance_broken-*.whl"))


def _clean_environment() -> dict[str, str]:
    """Create a process environment without repository import leakage.

    Args:
        None.

    Raises:
        None.

    Returns:
        dict[str, str]: Environment with user site and PYTHONPATH disabled.
    """
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment["PYTHONNOUSERSITE"] = "1"
    return environment


@pytest.mark.packaging_acceptance
def test_external_plugin_install_sources_close_the_graph_runtime_loop(
    wheel_path: Path,
    tmp_path: Path,
) -> None:
    """Install one real plugin through wheel, editable, and fixed Git sources.

    Args:
        wheel_path (Path): Built ZhiXing core wheel fixture.
        tmp_path (Path): Isolated environment and build root.

    Raises:
        AssertionError: Installation, discovery, identity, or execution fails.

    Returns:
        None: All distribution modes pass one installed Entry Point workflow.
    """
    plugin_dist = tmp_path / "plugin-dist"
    plugin_dist.mkdir()
    _run(
        [
            sys.executable,
            "-m",
            "build",
            "--wheel",
            "--no-isolation",
            "--outdir",
            str(plugin_dist),
            str(EXAMPLE),
        ],
        cwd=ROOT,
    )
    plugin_wheel = next(plugin_dist.glob("zhixing_example_components-*.whl"))
    git_repository, git_commit = _prepare_git_source(tmp_path)
    canonical_hashes = []

    for mode in ("wheel", "editable", "git"):
        root = tmp_path / mode
        environment_dir = root / "venv"
        workdir = root / "work"
        workdir.mkdir(parents=True)
        venv.EnvBuilder(with_pip=True, clear=True).create(environment_dir)
        python = environment_dir / (
            "Scripts/python.exe" if os.name == "nt" else "bin/python"
        )
        clean_environment = _clean_environment()
        _run(
            [str(python), "-m", "pip", "install", str(wheel_path)],
            cwd=workdir,
            environment=clean_environment,
        )
        # Provision the declared build backend before disabling all indexes.
        # The acceptance boundary below proves plugin installation itself is
        # local-only; dependency/bootstrap acquisition remains a prerequisite.
        if mode in {"editable", "git"}:
            _run(
                [
                    str(python),
                    "-m",
                    "pip",
                    "install",
                    "hatchling>=1.26,<2",
                    "editables>=0.3",
                ],
                cwd=workdir,
                environment=clean_environment,
            )
        _run(
            [str(python), "-c", _missing_plugin_script(EXAMPLE_YAML)],
            cwd=workdir,
            environment=clean_environment,
        )
        offline_environment = dict(clean_environment)
        offline_environment["PIP_NO_INDEX"] = "1"
        offline_environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
        if mode == "wheel":
            install = [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                str(plugin_wheel),
            ]
            source_kind = "archive"
        elif mode == "editable":
            install = [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--no-build-isolation",
                "-e",
                str(EXAMPLE),
            ]
            source_kind = "local"
        else:
            install = [
                str(python),
                "-m",
                "pip",
                "install",
                "--no-deps",
                "--no-index",
                "--no-build-isolation",
                f"git+file://{git_repository}@{git_commit}",
            ]
            source_kind = "vcs"
        _run(install, cwd=workdir, environment=offline_environment)
        metadata = _run(
            [
                str(python),
                "-m",
                "zhixing.cli",
                "components",
                "list",
                "--json",
            ],
            cwd=workdir,
            environment=clean_environment,
        )
        candidates = json.loads(metadata.stdout)["candidates"]
        candidate = next(
            item
            for item in candidates
            if item["provider_id"] == "zhixing-example"
        )
        assert candidate["origin"]["source_kind"] == source_kind
        _run(
            [str(python), "-c", _metadata_acceptance_script(source_kind)],
            cwd=workdir,
            environment=clean_environment,
        )
        doctor = _run(
            [
                str(python),
                "-m",
                "zhixing.cli",
                "components",
                "doctor",
                "--plugin-provider",
                "zhixing-example",
                "--json",
            ],
            cwd=workdir,
            environment=clean_environment,
        )
        assert json.loads(doctor.stdout)["ok"]
        inspect = _run(
            [
                str(python),
                "-m",
                "zhixing.cli",
                "components",
                "inspect",
                "example.external:run_labeler@1.0.0",
                "--json",
            ],
            cwd=workdir,
            environment=clean_environment,
        )
        assert json.loads(inspect.stdout)["component"]["provider_id"] == (
            "zhixing-example"
        )
        execution = _run(
            [str(python), str(EXAMPLE_SDK)],
            cwd=workdir,
            environment=clean_environment,
        )
        payload = json.loads(execution.stdout)
        assert payload["status"] == "success"
        assert payload["result"] == "demo:hello:external-plugin-example"
        assert payload["events"] == ["start", "complete"]
        assert payload["executions"]["sdk"] == payload["executions"]["yaml"]
        canonical_hashes.append(payload["canonical_hash"])

        if mode == "git":
            assert candidate["origin"]["commit_id"] == git_commit
            assert candidate["origin"]["requested_revision"] == git_commit

    assert len(set(canonical_hashes)) == 1


@pytest.mark.packaging_acceptance
def test_clean_install_reports_provider_bundle_and_contract_failures(
    wheel_path: Path,
    tmp_path: Path,
) -> None:
    """Diagnose three independent third-party failures in a clean install.

    Args:
        wheel_path (Path): Built ZhiXing core wheel fixture.
        tmp_path (Path): Isolated source, wheel, and virtual-environment root.

    Raises:
        AssertionError: Metadata discovery, failure categorization, exit codes,
            or credential redaction differs from the public contract.

    Returns:
        None.
    """
    negative_wheel = _build_negative_provider_wheel(tmp_path)
    environment_dir = tmp_path / "negative-venv"
    workdir = tmp_path / "negative-work"
    workdir.mkdir()
    venv.EnvBuilder(with_pip=True, clear=True).create(environment_dir)
    python = environment_dir / (
        "Scripts/python.exe" if os.name == "nt" else "bin/python"
    )
    clean_environment = _clean_environment()
    _run(
        [str(python), "-m", "pip", "install", str(wheel_path)],
        cwd=workdir,
        environment=clean_environment,
    )
    offline_environment = dict(clean_environment)
    offline_environment["PIP_NO_INDEX"] = "1"
    offline_environment["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    _run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--no-index",
            str(negative_wheel),
        ],
        cwd=workdir,
        environment=offline_environment,
    )
    metadata = _run(
        [
            str(python),
            "-m",
            "zhixing.cli",
            "components",
            "list",
            "--json",
        ],
        cwd=workdir,
        environment=clean_environment,
    )
    provider_ids = {
        candidate["provider_id"]
        for candidate in json.loads(metadata.stdout)["candidates"]
    }
    assert {
        "provider-load-failure",
        "invalid-bundle",
        "contract-failure",
    }.issubset(provider_ids)

    for provider_id, expected_code in (
        ("provider-load-failure", "plugin.provider_load_failed"),
        ("invalid-bundle", "component.bundle_return_invalid"),
    ):
        completed = subprocess.run(
            [
                str(python),
                "-m",
                "zhixing.cli",
                "components",
                "doctor",
                "--plugin-provider",
                provider_id,
                "--json",
            ],
            cwd=workdir,
            env=clean_environment,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 2, completed.stdout + completed.stderr
        payload = json.loads(completed.stdout)
        assert payload["report"]["failures"][0]["code"] == expected_code

    contract = subprocess.run(
        [
            str(python),
            "-m",
            "zhixing.cli",
            "components",
            "doctor",
            "--plugin-provider",
            "contract-failure",
            "--json",
        ],
        cwd=workdir,
        env=clean_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert contract.returncode == 3, contract.stdout + contract.stderr
    payload = json.loads(contract.stdout)
    assert payload["providers"][0]["health"] == "contract-failed"
    diagnostic = payload["providers"][0]["components"][0]["diagnostics"][0]
    assert diagnostic["phase"] == "invocation"
    assert diagnostic["code"] == "component.invocation_failed"
    assert "fixture-token" not in contract.stdout
    assert "example.test" not in contract.stdout
