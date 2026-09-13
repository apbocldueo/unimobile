"""Run reproducible real-Android Benchmark acceptance scenarios."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
from typing import Any, Mapping

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    # Direct ``python scripts/...`` execution otherwise exposes only scripts/.
    sys.path.insert(0, str(ROOT))

from examples.sdk.android_content_verified_agent import (
    build_android_content_verified_agent,
    build_external_augmented_android_agent,
)
from zhixing import ExecutableAgent, compile_agent, load_agent
from zhixing.benchmark import (
    BenchmarkCatalog,
    BenchmarkExperimentRuntime,
    BenchmarkOutcome,
    BenchmarkRunConfig,
    BenchmarkValidationLevel,
    PackageBenchmarkResourceProvider,
    compile_benchmark_package,
    enumerate_installed_benchmarks,
    load_experiment_report,
    load_run_report,
    verify_trajectory_bundle,
)
from zhixing.catalog import (
    DiscoveredComponentEnvironment,
    create_component_resolver,
    discover_components,
    empty_component_environment,
)
from zhixing.components import Action, ActionType, RunStatus
from zhixing.devices.manager import DeviceManager
from zhixing.devices.probes import AndroidContentProbe
from zhixing.graph import compile_graph_yaml_data
from zhixing.runtime.android import build_android_smoke_graph


BUILTIN_PACKAGE_ROOT = ROOT / "benchmarks" / "android_world"
EXTERNAL_PACKAGE_ROOT = (
    ROOT
    / "examples"
    / "external_benchmark_plugin"
    / "src"
    / "zhixing_photo_smoke_benchmark"
    / "package"
)
EXTERNAL_PACKAGE_ID = "example/photo-smoke@1.0.0"
BUILTIN_YAML = ROOT / "examples" / "graphs" / "android_content_verified_agent.yaml"
EXTERNAL_YAML = (
    ROOT
    / "examples"
    / "graphs"
    / "android_content_verified_external_extension.yaml"
)
SCENARIOS = (
    "builtin-sdk-pass",
    "builtin-yaml-pass",
    "controlled-fail",
    "paired-comparison",
    "external-component",
    "external-package",
)


def _installed_external_package_root() -> Path:
    """Resolve the external fixture through installed Benchmark metadata.

    Raises:
        AssertionError: Installed and explicit Package identities differ.
        BenchmarkDefinitionError: The installed readable identity is missing
            or ambiguous.
        RuntimeError: Discovery resolves a non-installed source.

    Returns:
        Path: Installed package-resource root selected by the Catalog.
    """
    candidate = BenchmarkCatalog(enumerate_installed_benchmarks()).resolve(
        EXTERNAL_PACKAGE_ID
    )
    if candidate.source_kind != "installed":
        raise RuntimeError("external acceptance requires an installed Package")
    installed = compile_benchmark_package(
        candidate.root,
        split="test",
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    explicit = compile_benchmark_package(
        EXTERNAL_PACKAGE_ROOT,
        split="test",
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    assert installed.plan is not None
    assert explicit.plan is not None
    assert (
        installed.plan.package_content_identity
        == explicit.plan.package_content_identity
    )
    assert installed.plan.canonical_hash() == explicit.plan.canonical_hash()
    return candidate.root


class ScriptedCameraLLM:
    """Emit deterministic camera actions with an explicit startup wait."""

    def __init__(self, *, x: int, y: int) -> None:
        """Create a run-scoped scripted model dependency.

        Args:
            x (int): Shutter horizontal coordinate.
            y (int): Shutter vertical coordinate.

        Raises:
            ValueError: A coordinate is negative.

        Returns:
            None.
        """
        if x < 0 or y < 0:
            raise ValueError("camera coordinates must be non-negative")
        self.x = x
        self.y = y
        self.index = 0

    def generate(
        self,
        prompt: str,
        images: list[str] | None = None,
    ) -> str:
        """Return START_APP, WAIT, then TAP in parser-compatible JSON.

        Args:
            prompt (str): Rendered reasoning prompt.
            images (list[str] | None): Current screenshot references.

        Raises:
            RuntimeError: The verifier asks for an unexpected fourth decision.

        Returns:
            str: One deterministic Mobile Agent action.
        """
        del prompt, images
        self.index += 1
        if self.index == 1:
            return (
                '{"action":"start_app","arguments":{"app":"camera"},'
                '"thought":"open the camera"}'
            )
        if self.index == 2:
            return (
                '{"action":"wait","arguments":{"seconds":3},'
                '"thought":"wait for the camera preview"}'
            )
        if self.index == 3:
            return (
                '{"action":"tap","arguments":'
                f'{{"x":{self.x},"y":{self.y}}},'
                '"thought":"press the shutter"}'
            )
        raise RuntimeError(
            "content Verifier did not terminate after the shutter action"
        )


def _verified_agent_from_graph(
    graph: Any,
    *,
    x: int,
    y: int,
    environment: DiscoveredComponentEnvironment,
) -> ExecutableAgent:
    """Compile and preflight one graph with fresh scripted dependencies per run.

    Args:
        graph (Any): AgentGraph or successful graph compilation.
        x (int): Shutter horizontal coordinate.
        y (int): Shutter vertical coordinate.
        environment (DiscoveredComponentEnvironment): Explicit plugin environment.

    Raises:
        GraphBindingError: Graph or component preflight fails.

    Returns:
        ExecutableAgent: Reusable run recipe with isolated model cursors.
    """
    preflight = compile_agent(
        graph,
        dependencies={"llm": ScriptedCameraLLM(x=x, y=y)},
        component_environment=environment,
    )

    def resolver_factory() -> Any:
        """Create fresh built-in/external components and one scripted LLM.

        Returns:
            Any: Composite run-scoped component resolver.
        """
        return create_component_resolver(
            environment,
            dependencies={"llm": ScriptedCameraLLM(x=x, y=y)},
        )

    return replace(preflight, resolver_factory=resolver_factory)


def _verified_sdk_agent(
    *,
    x: int,
    y: int,
    external: bool = False,
) -> ExecutableAgent:
    """Build a verified SDK Agent with optional installed external audit node.

    Args:
        x (int): Shutter horizontal coordinate.
        y (int): Shutter vertical coordinate.
        external (bool): Whether to discover and require the example provider.

    Raises:
        GraphBindingError: Compilation or component discovery preflight fails.

    Returns:
        ExecutableAgent: SDK-defined camera Agent.
    """
    environment = (
        discover_components(allowlist=("zhixing-example",))
        if external
        else empty_component_environment()
    )
    graph = (
        build_external_augmented_android_agent(max_steps=10)
        if external
        else build_android_content_verified_agent(max_steps=10)
    )
    return _verified_agent_from_graph(
        graph,
        x=x,
        y=y,
        environment=environment,
    )


def _verified_yaml_agent(
    *,
    x: int,
    y: int,
    external: bool = False,
) -> ExecutableAgent:
    """Load a verified YAML Agent and replace its scripted dependency factory.

    Args:
        x (int): Shutter horizontal coordinate.
        y (int): Shutter vertical coordinate.
        external (bool): Whether the YAML requires the example provider.

    Raises:
        GraphBindingError: YAML or component preflight fails.

    Returns:
        ExecutableAgent: YAML-defined camera Agent.
    """
    environment = (
        discover_components(allowlist=("zhixing-example",))
        if external
        else empty_component_environment()
    )
    if external:
        compilation = _external_yaml_compilation(environment)
        preflight = compile_agent(
            compilation,
            dependencies={"llm": ScriptedCameraLLM(x=x, y=y)},
            component_environment=environment,
        )
    else:
        preflight = load_agent(
            BUILTIN_YAML,
            component_environment=environment,
            dependencies={"llm": ScriptedCameraLLM(x=x, y=y)},
        )
    return _verified_agent_from_graph(
        preflight.graph,
        x=x,
        y=y,
        environment=environment,
    )


def _external_yaml_compilation(
    environment: DiscoveredComponentEnvironment,
) -> Any:
    """Compile the base YAML plus its declarative external extension.

    Args:
        environment (DiscoveredComponentEnvironment): Contract source for the
            installed task labeler.

    Raises:
        ValueError: YAML documents are malformed.

    Returns:
        Any: Public graph compilation result consumed by ``compile_agent``.
    """
    base_data = yaml.safe_load(BUILTIN_YAML.read_text(encoding="utf-8"))
    extension = yaml.safe_load(EXTERNAL_YAML.read_text(encoding="utf-8"))
    base_data["nodes"].extend(extension["nodes"])
    base_data["edges"].extend(extension["edges"])
    return compile_graph_yaml_data(
        base_data,
        contract_catalog=environment.contract_catalog,
    )


def _control_agent() -> ExecutableAgent:
    """Build a successful Agent that deliberately does not take a photo.

    Returns:
        ExecutableAgent: HOME then DONE graph with a distinct canonical hash.
    """
    graph, components = build_android_smoke_graph(
        Action(ActionType.KEY, {"code": "home"})
    )
    return ExecutableAgent(
        graph=graph,
        resolver_factory=lambda: dict(components),
    )


def _artifact_summary(
    artifact_root: Path,
    experiment_id: str,
    *,
    raw_serial: str,
) -> dict[str, Any]:
    """Reload reports, trajectories, and bundle while checking safe exports.

    Args:
        artifact_root (Path): Scenario-specific writer root.
        experiment_id (str): Completed experiment identity.
        raw_serial (str): Raw serial forbidden from durable Benchmark outputs.

    Raises:
        AssertionError: A required artifact, schema, hash, or safety check fails.

    Returns:
        dict[str, Any]: Safe relative artifact evidence.
    """
    experiment_root = artifact_root / experiment_id
    report_path = experiment_root / "experiment-report.json"
    report = load_experiment_report(report_path)
    assert report.experiment_id == experiment_id
    bundle_path = experiment_root / "trajectory-bundle.zip"
    assert verify_trajectory_bundle(bundle_path)
    run_refs: list[str] = []
    for run_dir in sorted((experiment_root / "runs").iterdir()):
        load_run_report(run_dir / "run-report.json")
        records = [
            json.loads(line)
            for line in (run_dir / "trajectory.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert records
        assert {record["phase"] for record in records} >= {
            "reset",
            "setup",
            "evaluator_pre",
            "agent",
            "evaluation",
            "cleanup",
        }
        run_refs.append(
            str((run_dir / "run-report.json").relative_to(experiment_root))
        )
    for path in experiment_root.rglob("*"):
        if path.is_file() and path.suffix in {".json", ".jsonl"}:
            content = path.read_text(encoding="utf-8")
            assert raw_serial not in content
            assert "sk-live-acceptance-canary" not in content
    return {
        "experiment_root": experiment_id,
        "experiment_report": "experiment-report.json",
        "trajectory_bundle": "trajectory-bundle.zip",
        "run_reports": run_refs,
        "bundle_verified": True,
    }


def _expected_agents(
    scenario: str,
    *,
    x: int,
    y: int,
) -> tuple[dict[str, ExecutableAgent], Mapping[str, BenchmarkOutcome]]:
    """Build scenario Agents and their expected Benchmark outcomes.

    Args:
        scenario (str): Selected acceptance scenario.
        x (int): Shutter horizontal coordinate.
        y (int): Shutter vertical coordinate.

    Raises:
        ValueError: The scenario is unknown.

    Returns:
        tuple[dict[str, ExecutableAgent], Mapping[str, BenchmarkOutcome]]:
            Named run recipes and expected outcome per Agent.
    """
    if scenario == "builtin-sdk-pass":
        return {"verified-sdk": _verified_sdk_agent(x=x, y=y)}, {
            "verified-sdk": BenchmarkOutcome.PASS
        }
    if scenario == "builtin-yaml-pass":
        sdk = _verified_sdk_agent(x=x, y=y)
        yaml_agent = _verified_yaml_agent(x=x, y=y)
        assert sdk.canonical_hash == yaml_agent.canonical_hash
        return {"verified-yaml": yaml_agent}, {
            "verified-yaml": BenchmarkOutcome.PASS
        }
    if scenario == "controlled-fail":
        return {"early-finish-control": _control_agent()}, {
            "early-finish-control": BenchmarkOutcome.FAIL
        }
    if scenario == "paired-comparison":
        return {
            "verified-camera": _verified_sdk_agent(x=x, y=y),
            "early-finish-control": _control_agent(),
        }, {
            "verified-camera": BenchmarkOutcome.PASS,
            "early-finish-control": BenchmarkOutcome.FAIL,
        }
    if scenario == "external-component":
        sdk = _verified_sdk_agent(x=x, y=y, external=True)
        yaml_agent = _verified_yaml_agent(x=x, y=y, external=True)
        assert sdk.canonical_hash == yaml_agent.canonical_hash
        return {"external-augmented-camera": sdk}, {
            "external-augmented-camera": BenchmarkOutcome.PASS
        }
    if scenario == "external-package":
        return {"verified-camera": _verified_sdk_agent(x=x, y=y)}, {
            "verified-camera": BenchmarkOutcome.PASS
        }
    raise ValueError(f"unknown acceptance scenario {scenario!r}")


def run_acceptance(
    scenario: str,
    *,
    serial: str,
    x: int,
    y: int,
    repeats: int,
    artifact_root: Path,
) -> dict[str, Any]:
    """Execute and validate one real-Android Benchmark acceptance scenario.

    Args:
        scenario (str): One value from :data:`SCENARIOS`.
        serial (str): Exact online Android serial.
        x (int): Shutter horizontal coordinate.
        y (int): Shutter vertical coordinate.
        repeats (int): Requested repeats; comparison requires exactly two.
        artifact_root (Path): Parent for scenario-isolated artifacts.

    Raises:
        AssertionError: Runtime results do not match the scenario contract.
        RuntimeError: Package compilation lacks a Plan or Protocol.
        ValueError: Input values are invalid.

    Returns:
        dict[str, Any]: Safe acceptance summary without raw serial or media IDs.
    """
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS!r}")
    if repeats < 1:
        raise ValueError("repeats must be positive")
    selected_repeats = 2 if scenario == "paired-comparison" else repeats
    package_root = (
        _installed_external_package_root()
        if scenario == "external-package"
        else BUILTIN_PACKAGE_ROOT
    )
    task_id = "PhotoSmoke_1" if scenario == "external-package" else "AndroidWorld_6"
    compiled = compile_benchmark_package(
        package_root,
        split="test",
        validation_level=BenchmarkValidationLevel.RESOURCES,
    )
    if compiled.plan is None or compiled.protocol is None:
        raise RuntimeError("Benchmark Package lacks a valid Plan or default Protocol")
    protocol = compiled.protocol.model_copy(
        update={"repeats": selected_repeats}
    )
    agents, expectations = _expected_agents(scenario, x=x, y=y)
    device = DeviceManager.get_android_device(serial)
    probe = AndroidContentProbe()
    before = probe.snapshot(device)
    scenario_root = artifact_root / scenario
    suite = BenchmarkExperimentRuntime().run(
        compiled.plan,
        protocol,
        agents,
        run_config=BenchmarkRunConfig(
            artifact_root=scenario_root,
            serial=serial,
            task_ids=(task_id,),
        ),
        resource_provider=PackageBenchmarkResourceProvider(
            package_root,
            compiled.plan,
        ),
        device=device,
    )
    after = probe.snapshot(device)
    media_delta = probe.diff(before, after)
    assert suite.reporting_error_code == ""
    expected_per_agent = selected_repeats
    for agent_id, expected in expectations.items():
        selected = [item for item in suite.results if item.agent_id == agent_id]
        assert len(selected) == expected_per_agent
        assert all(item.outcome is expected for item in selected)
        assert all(
            item.agent_result is not None
            and item.agent_result.status is RunStatus.SUCCESS
            for item in selected
        )
        assert all(
            item.evaluation is not None
            and item.evaluation.is_pass is (expected is BenchmarkOutcome.PASS)
            for item in selected
        )
    pass_count = sum(
        count
        for agent_id, count in (
            (agent_id, selected_repeats)
            for agent_id, expected in expectations.items()
            if expected is BenchmarkOutcome.PASS
        )
    )
    assert len(media_delta.added_ids) >= pass_count
    if not pass_count:
        assert not media_delta.has_additions
        assert suite.counts["invalid"] == 0
    artifacts = _artifact_summary(
        scenario_root,
        suite.experiment_id,
        raw_serial=serial,
    )
    report = load_experiment_report(
        scenario_root / suite.experiment_id / "experiment-report.json"
    )
    comparison_summary: list[Mapping[str, Any]] = []
    if scenario == "paired-comparison":
        comparison = next(
            item
            for item in report.comparisons
            if {
                item.left_agent_id,
                item.right_agent_id,
            }
            == {"verified-camera", "early-finish-control"}
        )
        assert comparison.paired
        assert comparison.matched_count == 2
        assert (
            comparison.left_wins
            if comparison.left_agent_id == "verified-camera"
            else comparison.right_wins
        ) == 2
        comparison_summary.append(comparison.to_safe_dict())
    if scenario == "external-component":
        result = suite.results[0].agent_result
        assert result is not None
        external_events = [
            event.kind
            for event in result.events
            if event.node_id == "external_audit"
        ]
        assert external_events == ["start", "complete"]
        complete = next(
            event
            for event in result.events
            if event.node_id == "external_audit" and event.kind == "complete"
        )
        assert complete.role == "example.external.task_run_labeler"
        assert complete.run_id == result.run_id
        assert complete.run_id == suite.results[0].task_run_id
        assert complete.payload == {
            "outputs": {
                "keys": ["result"],
                "type": "dict",
            }
        }
    summary = {
        "scenario": scenario,
        "counts": suite.counts,
        "is_expected": True,
        "identities": {
            "benchmark_plan": suite.benchmark_plan_identity,
            "experiment_protocol": suite.experiment_protocol_identity,
            "agents": {
                name: agent.canonical_hash for name, agent in agents.items()
            },
        },
        "media_store": {"added_count": len(media_delta.added_ids)},
        "artifacts": artifacts,
        "comparisons": comparison_summary,
    }
    summary_path = scenario_root / suite.experiment_id / "acceptance-summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _parser() -> argparse.ArgumentParser:
    """Build the acceptance command parser.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(
        description="Run one explicit real-Android Benchmark acceptance scenario."
    )
    parser.add_argument("--scenario", choices=SCENARIOS, required=True)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--x", type=int, default=540)
    parser.add_argument("--y", type=int, default=2052)
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=ROOT / "temp" / "benchmark-runs" / "android-acceptance",
    )
    return parser


def main() -> int:
    """Run the selected scenario and print its safe acceptance summary.

    Returns:
        int: Zero only when the scenario-specific contract is satisfied.
    """
    args = _parser().parse_args()
    summary = run_acceptance(
        args.scenario,
        serial=args.serial,
        x=args.x,
        y=args.y,
        repeats=args.repeats,
        artifact_root=args.artifact_root,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
