"""CLI tests for the graph-native Benchmark Experiment Runtime entry point."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

from zhixing.benchmark import (
    BenchmarkOutcome,
    BenchmarkStageResult,
    BenchmarkStageStatus,
    BenchmarkSuiteResult,
    BenchmarkTaskResult,
)
from zhixing.cli import main
from tests.benchmark.helpers import task, write_package


ROOT = Path(__file__).resolve().parents[2]


def _suite_result(plan: Any, protocol: Any, agents: dict[str, Any], config: Any) -> BenchmarkSuiteResult:
    """Create one safe PASS result for a CLI facade test.

    Args:
        plan (Any): Compiled BenchmarkPlan.
        protocol (Any): Loaded ExperimentProtocol.
        agents (dict[str, Any]): Named ExecutableAgents.
        config (Any): Runtime-only configuration.

    Raises:
        None.

    Returns:
        BenchmarkSuiteResult: Single-result passing suite.
    """
    agent_id = sorted(agents)[0]
    agent = agents[agent_id]
    task_id = config.task_ids[0]
    task = BenchmarkTaskResult(
        experiment_id=config.experiment_id,
        task_run_id="run-cli",
        task_id=task_id,
        repeat=0,
        agent_id=agent_id,
        agent_graph_identity=agent.canonical_hash,
        benchmark_plan_identity=plan.canonical_hash(),
        experiment_protocol_identity=protocol.canonical_hash(),
        task_instance_identity="sha256:" + "1" * 64,
        outcome=BenchmarkOutcome.PASS,
        stages=(
            BenchmarkStageResult(
                phase="evaluation",
                status=BenchmarkStageStatus.SUCCESS,
            ),
        ),
        artifact_namespace="run-cli",
    )
    return BenchmarkSuiteResult(
        experiment_id=config.experiment_id,
        benchmark_plan_identity=plan.canonical_hash(),
        experiment_protocol_identity=protocol.canonical_hash(),
        results=(task,),
    )


def test_benchmark_run_cli_delegates_to_public_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Load definitions and Agents before invoking the public runtime once."""
    calls: list[tuple[Any, ...]] = []

    class FakeRuntime:
        """Runtime replacement that proves CLI orchestration only."""

        def run(self, plan, protocol, agents, **kwargs):
            """Record the public call and return one result.

            Args:
                plan: Compiled BenchmarkPlan.
                protocol: ExperimentProtocol.
                agents: Named ExecutableAgents.
                **kwargs: Runtime-only bindings.

            Raises:
                None.

            Returns:
                BenchmarkSuiteResult: Passing fake suite.
            """
            calls.append((plan, protocol, agents, kwargs))
            return _suite_result(plan, protocol, agents, kwargs["run_config"])

    monkeypatch.setattr("zhixing.cli.BenchmarkExperimentRuntime", FakeRuntime)
    output = io.StringIO()
    error = io.StringIO()
    code = main(
        [
            "benchmark",
            "run",
            str(write_package(tmp_path / "package", tasks=[task("AndroidWorld_6")])),
            "--split",
            "test",
            "--task",
            "AndroidWorld_6",
            "--agent",
            f"candidate={ROOT / 'examples/graphs/builtin_android_agent.yaml'}",
            "--artifact-root",
            str(tmp_path),
            "--no-installed",
            "--json",
        ],
        stdout=output,
        stderr=error,
        stdin=io.StringIO(),
    )
    assert code == 0, error.getvalue()
    assert len(calls) == 1
    payload = json.loads(output.getvalue())
    assert payload["ok"] is True
    assert payload["suite"]["counts"]["pass"] == 1
    assert str(tmp_path) not in output.getvalue()


def test_benchmark_run_cli_rejects_agent_syntax_before_runtime(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Return a definition exit code without entering runtime or ADB."""
    called = False

    class ForbiddenRuntime:
        """Runtime whose construction proves a preflight ordering regression."""

        def __init__(self) -> None:
            """Fail if the CLI reaches runtime.

            Raises:
                AssertionError: Always.

            Returns:
                None.
            """
            nonlocal called
            called = True
            raise AssertionError("runtime must not start")

    monkeypatch.setattr("zhixing.cli.BenchmarkExperimentRuntime", ForbiddenRuntime)
    output = io.StringIO()
    error = io.StringIO()
    code = main(
        [
            "benchmark",
            "run",
            str(write_package(tmp_path / "package", tasks=[task("AndroidWorld_6")])),
            "--task",
            "AndroidWorld_6",
            "--agent",
            "missing-equals",
            "--no-installed",
            "--json",
        ],
        stdout=output,
        stderr=error,
        stdin=io.StringIO(),
    )
    assert code == 2
    assert called is False
    assert json.loads(output.getvalue())["ok"] is False


def test_benchmark_run_cli_supports_multiple_agents_and_text_output(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Forward multiple named Agents and render the stable text summary."""
    seen_agents: tuple[str, ...] = ()

    class FakeRuntime:
        """Runtime replacement used to inspect named Agent forwarding."""

        def run(self, plan, protocol, agents, **kwargs):
            """Record Agents and return a passing suite.

            Args:
                plan: Compiled BenchmarkPlan.
                protocol: ExperimentProtocol.
                agents: Named ExecutableAgents.
                **kwargs: Runtime-only bindings.

            Raises:
                None.

            Returns:
                BenchmarkSuiteResult: Passing fake suite.
            """
            nonlocal seen_agents
            seen_agents = tuple(sorted(agents))
            return _suite_result(plan, protocol, agents, kwargs["run_config"])

    monkeypatch.setattr("zhixing.cli.BenchmarkExperimentRuntime", FakeRuntime)
    graph = ROOT / "examples/graphs/builtin_android_agent.yaml"
    output = io.StringIO()
    error = io.StringIO()
    code = main(
        [
            "benchmark",
            "run",
            str(write_package(tmp_path / "package", tasks=[task("AndroidWorld_6")])),
            "--split",
            "test",
            "--task",
            "AndroidWorld_6",
            "--agent",
            f"candidate-a={graph}",
            "--agent",
            f"candidate-b={graph}",
            "--artifact-root",
            str(tmp_path),
            "--no-installed",
        ],
        stdout=output,
        stderr=error,
        stdin=io.StringIO(),
    )
    assert code == 0, error.getvalue()
    assert seen_agents == ("candidate-a", "candidate-b")
    assert "outcomes:" in output.getvalue()
    assert "AndroidWorld_6 agent=candidate-a" in output.getvalue()
    assert str(tmp_path) not in output.getvalue()


def test_benchmark_run_cli_returns_nonpass_exit_code(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Return exit code three for a completed evaluator failure."""

    class FakeRuntime:
        """Runtime replacement that returns one completed failing task."""

        def run(self, plan, protocol, agents, **kwargs):
            """Build a completed non-passing suite.

            Args:
                plan: Compiled BenchmarkPlan.
                protocol: ExperimentProtocol.
                agents: Named ExecutableAgents.
                **kwargs: Runtime-only bindings.

            Raises:
                None.

            Returns:
                BenchmarkSuiteResult: Completed failing suite.
            """
            passing = _suite_result(
                plan,
                protocol,
                agents,
                kwargs["run_config"],
            )
            failed = BenchmarkTaskResult(
                **{
                    **passing.results[0].__dict__,
                    "outcome": BenchmarkOutcome.FAIL,
                }
            )
            return BenchmarkSuiteResult(
                experiment_id=passing.experiment_id,
                benchmark_plan_identity=passing.benchmark_plan_identity,
                experiment_protocol_identity=(
                    passing.experiment_protocol_identity
                ),
                results=(failed,),
            )

    monkeypatch.setattr("zhixing.cli.BenchmarkExperimentRuntime", FakeRuntime)
    output = io.StringIO()
    error = io.StringIO()
    code = main(
        [
            "benchmark",
            "run",
            str(write_package(tmp_path / "package", tasks=[task("AndroidWorld_6")])),
            "--split",
            "test",
            "--task",
            "AndroidWorld_6",
            "--agent",
            (
                "candidate="
                f"{ROOT / 'examples/graphs/builtin_android_agent.yaml'}"
            ),
            "--artifact-root",
            str(tmp_path),
            "--no-installed",
            "--json",
        ],
        stdout=output,
        stderr=error,
        stdin=io.StringIO(),
    )
    assert code == 3, error.getvalue()
    assert json.loads(output.getvalue())["suite"]["counts"]["fail"] == 1
