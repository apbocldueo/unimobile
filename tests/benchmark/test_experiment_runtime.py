"""Contract and fake-device integration tests for Benchmark Experiment Runtime."""

from __future__ import annotations

from pathlib import Path
from random import Random
import random
import subprocess
import sys
from typing import Any, Mapping

import pytest

from zhixing.benchmark import (
    BenchmarkLifecycleEvent,
    BenchmarkExperimentRuntime,
    BenchmarkOutcome,
    BenchmarkPlan,
    BenchmarkPublicationPolicy,
    BenchmarkRunConfig,
    BenchmarkStageResult,
    BenchmarkTaskResult,
    BenchmarkStageStatus,
    EmptyBenchmarkResourceProvider,
    ExperimentProtocol,
    PackageBenchmarkResourceProvider,
    RegistryBenchmarkComponentResolver,
    build_schedule,
    compile_benchmark_suite,
    load_experiment_report,
    materialize_task,
    verify_trajectory_bundle,
)
from zhixing.benchmark.runtime import TaskInstancePool
from zhixing.benchmark.runtime.evaluator import (
    evaluate_tree,
    prepare_evaluator_tree,
    run_evaluator_pre_hooks,
)
from zhixing.benchmark.runtime.adapters import (
    execute_environment_calls,
    infer_environment_phase,
)
from zhixing.components import Action, ActionType, RunStatus, RuntimeContext
from zhixing.config.contracts import BenchmarkSuite
from zhixing.config.contracts.common import PluginReference
from zhixing.config.contracts.semantic import validate_benchmark_semantics
from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.factory import PluginRegistry
from zhixing.runtime.android import build_android_smoke_graph
from zhixing.runtime import SimpleCancellationSignal
from zhixing.sdk import ExecutableAgent
from tests.benchmark.helpers import write_package
from zhixing.benchmark import compile_benchmark_package
from zhixing.sdk import AgentRunConfig


class FakeShellResult:
    """Small shell result compatible with legacy Benchmark leaves."""

    def __init__(self, output: str = "", exit_code: int = 0) -> None:
        """Create one successful response.

        Args:
            output (str): Shell standard output.
            exit_code (int): Process exit code.

        Raises:
            None.

        Returns:
            None.
        """
        self.output = output
        self.exit_code = exit_code
        self.error = ""


class FakeBenchmarkDevice:
    """Android-compatible fake shared by infrastructure and Graph Runtime."""

    serial = "fake-benchmark"
    platform = "android"
    locale = "en-US"
    orientation = "portrait"
    w = 100
    h = 200
    app_package_names = {"files": "com.android.documentsui"}

    def __init__(self) -> None:
        """Create empty device call evidence.

        Returns:
            None.
        """
        self.calls: list[tuple[Any, ...]] = []

    def screenshot(self, path: str) -> str:
        """Write a minimal screenshot artifact.

        Args:
            path (str): Host destination.

        Raises:
            OSError: Artifact cannot be written.

        Returns:
            str: Destination path.
        """
        Path(path).write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 64)
        self.calls.append(("screenshot",))
        return path

    def go_home(self) -> None:
        """Record one HOME action.

        Returns:
            None.
        """
        self.calls.append(("home",))

    def go_back(self) -> None:
        """Record one BACK action.

        Returns:
            None.
        """
        self.calls.append(("back",))

    def wait(self, seconds: float) -> None:
        """Record a device wait.

        Args:
            seconds (float): Requested duration.

        Raises:
            None.

        Returns:
            None.
        """
        self.calls.append(("wait", seconds))

    def shell(self, command: str, error_raise: bool = False) -> FakeShellResult:
        """Record an infrastructure shell command.

        Args:
            command (str): Shell command.
            error_raise (bool): Legacy compatibility flag.

        Raises:
            None.

        Returns:
            FakeShellResult: Successful response.
        """
        del error_raise
        self.calls.append(("shell", command))
        return FakeShellResult("ok")


class FakeEnvironmentOperation:
    """Environment plugin that records phase parameters on the shared device."""

    __plugin_namespace__ = "benchmark.environment.setup"

    def execute(self, meta: Mapping[str, Any], params: Mapping[str, Any]) -> bool:
        """Record one environment operation.

        Args:
            meta (Mapping[str, Any]): Runtime metadata containing device.
            params (Mapping[str, Any]): Rendered parameters.

        Raises:
            None.

        Returns:
            bool: True unless explicitly configured to fail.
        """
        device = meta["device"]
        device.calls.append(("environment", params.get("label")))
        return not bool(params.get("fail"))


class FakeResetOperation(FakeEnvironmentOperation):
    """Reset plugin with an unambiguous namespace."""

    __plugin_namespace__ = "benchmark.environment.reset"


class FakeEvaluator:
    """Legacy-shaped leaf that records pre/evaluate instance reuse."""

    def __init__(self, params: Mapping[str, Any], device: Any) -> None:
        """Bind parameters and shared device.

        Args:
            params (Mapping[str, Any]): Evaluator configuration.
            device (Any): Shared fake Android device.

        Raises:
            None.

        Returns:
            None.
        """
        self.params = dict(params)
        self.device = device
        self.prepared = False

    def pre_evaluate(self, context: Mapping[str, Any]) -> None:
        """Record baseline preparation.

        Args:
            context (Mapping[str, Any]): Legacy-compatible view.

        Raises:
            None.

        Returns:
            None.
        """
        self.prepared = True
        self.device.calls.append(("evaluator_pre", context["task_params"]["id"]))

    def evaluate(self, context: Mapping[str, Any]) -> EvalResult:
        """Return configured pass/fail evidence.

        Args:
            context (Mapping[str, Any]): View containing typed RunResult.

        Raises:
            AssertionError: Pre-hook or Graph result is absent.

        Returns:
            EvalResult: Configured result.
        """
        assert self.prepared
        assert context["run_result"] is not None
        if self.params.get("raise"):
            raise RuntimeError("controlled fake evaluator infrastructure failure")
        self.device.calls.append(("evaluate", context["task_params"]["id"]))
        return EvalResult(
            is_pass=bool(self.params.get("pass", True)),
            reason="configured fake evaluator",
            token=float(self.params.get("token", 1.0)),
        )


class FakeBenchmarkResolver:
    """Resolver that exposes deterministic task, environment, and evaluator fakes."""

    def __init__(self) -> None:
        """Create generation counters.

        Returns:
            None.
        """
        self.generated = 0

    def generate_task_value(
        self,
        reference: Any,
        params: Mapping[str, Any],
        *,
        rng: Random,
    ) -> tuple[Any, tuple[str, ...]]:
        """Generate one deterministic integer.

        Args:
            reference (Any): Logical plugin reference.
            params (Mapping[str, Any]): Generator parameters.
            rng (Random): Run-local RNG.

        Raises:
            None.

        Returns:
            tuple[Any, tuple[str, ...]]: Generated integer and no warnings.
        """
        del reference
        self.generated += 1
        return rng.randint(int(params.get("min", 1)), int(params.get("max", 9))), ()

    def resolve_environment(self, call: Mapping[str, Any]) -> type[Any]:
        """Resolve reset or setup by explicit fake name.

        Args:
            call (Mapping[str, Any]): Environment definition.

        Raises:
            ValueError: Fake name is unknown.

        Returns:
            type[Any]: Fake operation class.
        """
        name = call.get("name")
        if name == "reset":
            return FakeResetOperation
        if name in {"setup", "cleanup"}:
            return FakeEnvironmentOperation
        raise ValueError("unknown fake environment plugin")

    def resolve_evaluator(self, config: Mapping[str, Any]) -> type[Any]:
        """Resolve every fake leaf to FakeEvaluator.

        Args:
            config (Mapping[str, Any]): Leaf definition.

        Raises:
            None.

        Returns:
            type[Any]: Fake evaluator.
        """
        del config
        return FakeEvaluator


def _task(task_id: str, *, evaluator_pass: bool = True) -> dict[str, Any]:
    """Build a dynamic task with explicit lifecycle phases.

    Args:
        task_id (str): Stable task identity.
        evaluator_pass (bool): Fake evaluator outcome.

    Raises:
        None.

    Returns:
        dict[str, Any]: Canonical task mapping.
    """
    return {
        "id": task_id,
        "instruction": "Use value ${value}",
        "app": "files",
        "type": "dynamic",
        "task_initializer": {
            "value": {"name": "number", "params": {"min": 1, "max": 20}}
        },
        "environment_initializer": [
            {
                "name": "reset",
                "phase": "reset",
                "params": {"label": f"{task_id}-reset"},
            },
            {
                "name": "setup",
                "phase": "setup",
                "params": {"label": f"{task_id}-setup-${{value}}"},
            },
        ],
        "evaluator": {
            "name": "fake",
            "params": {"method": "configured", "pass": evaluator_pass},
        },
        "cleanup_initializer": [
            {
                "name": "cleanup",
                "params": {"label": f"{task_id}-cleanup"},
            }
        ],
        "max_steps": 3,
    }


def _plan() -> BenchmarkPlan:
    """Compile two fake tasks into a source-neutral Plan.

    Returns:
        BenchmarkPlan: Valid test Plan.
    """
    result = compile_benchmark_suite(
        BenchmarkSuite.model_validate([_task("one"), _task("two", evaluator_pass=False)])
    )
    assert result.plan is not None
    return result.plan


def _mixed_evaluation_plan() -> BenchmarkPlan:
    """Compile dynamic PASS, FAIL, and INVALID fake-device tasks.

    Raises:
        None.

    Returns:
        BenchmarkPlan: Plan containing threshold, weighted, and error branches.
    """
    passing = _task("pass")
    passing["evaluator"] = {
        "name": "composite",
        "params": {
            "logic": "THRESHOLD",
            "min_passed": 1,
            "rules": [
                {"name": "fake", "params": {"method": "a", "pass": True}},
                {"name": "fake", "params": {"method": "b", "pass": False}},
            ],
        },
    }
    failing = _task("fail")
    failing["evaluator"] = {
        "name": "composite",
        "params": {
            "logic": "WEIGHTED",
            "pass_threshold": 0.75,
            "weights": [1.0, 1.0],
            "rules": [
                {"name": "fake", "params": {"method": "a", "pass": True}},
                {"name": "fake", "params": {"method": "b", "pass": False}},
            ],
        },
    }
    invalid = _task("invalid")
    invalid["evaluator"] = {
        "name": "fake",
        "params": {"method": "error", "raise": True},
    }
    result = compile_benchmark_suite(
        BenchmarkSuite.model_validate([passing, failing, invalid])
    )
    assert result.plan is not None
    return result.plan


def _agent(action: Action) -> ExecutableAgent:
    """Create a graph-native deterministic smoke Agent.

    Args:
        action (Action): Physical action distinguishing candidate graphs.

    Raises:
        ValueError: Smoke graph is invalid.

    Returns:
        ExecutableAgent: Agent with fresh explicit component mappings.
    """
    graph, components = build_android_smoke_graph(action)
    return ExecutableAgent(graph=graph, resolver_factory=lambda: dict(components))


def test_cleanup_phase_changes_plan_identity_and_round_trips() -> None:
    """Include explicit lifecycle semantics in Plan canonical identity."""
    plan = _plan()
    changed = plan.tasks[0].model_copy(update={"cleanup_initializer": []})
    changed_plan = plan.model_copy(update={"tasks": (changed, plan.tasks[1])})
    assert changed_plan.canonical_hash() != plan.canonical_hash()
    restored = BenchmarkPlan.model_validate(
        plan.model_dump(mode="json", exclude_none=True)
    )
    assert restored.canonical_hash() == plan.canonical_hash()


def test_cleanup_placeholder_is_validated_at_its_exact_path() -> None:
    """Reject unresolved cleanup values before any runtime side effect."""
    mapping = _task("one")
    mapping["cleanup_initializer"][0]["params"]["label"] = "${missing}"
    suite = BenchmarkSuite.model_validate([mapping])
    issues = validate_benchmark_semantics(suite)
    issue = next(
        item for item in issues if item.code == "benchmark.placeholder.unresolved"
    )
    assert issue.path[:3] == (0, "cleanup_initializer", 0)


def test_schedule_and_materialization_are_deterministic_and_share_instances() -> None:
    """Build a pure matrix and invoke one generator for paired Agents."""
    plan = _plan()
    protocol = ExperimentProtocol(repeats=2)
    schedule = build_schedule(plan, protocol, ["b", "a"])
    assert len(schedule) == 8
    assert schedule[0].agent_id == "a"
    assert schedule[0].seed == schedule[1].seed
    resolver = FakeBenchmarkResolver()
    pool = TaskInstancePool()
    first_entry, second_entry = schedule[0], schedule[1]
    task = next(item for item in plan.tasks if item.id == first_entry.task_id)
    first = pool.get_or_materialize(
        first_entry.shared_instance_key,
        lambda: materialize_task(
            plan,
            task,
            repeat=first_entry.repeat,
            seed=first_entry.seed,
            resolver=resolver,
            resource_provider=EmptyBenchmarkResourceProvider(),
        ),
    )
    second = pool.get_or_materialize(
        second_entry.shared_instance_key,
        lambda: pytest.fail("paired instance was generated twice"),
    )
    assert first is second
    assert resolver.generated == 1
    assert "${" not in first.instruction
    assert first.canonical_hash() == second.canonical_hash()


def test_schedule_seed_is_stable_in_a_fresh_process() -> None:
    """Keep deterministic scheduling independent of Python hash randomization."""
    plan = _plan()
    protocol = ExperimentProtocol.model_validate(
        {"seed": 17, "task_order": {"strategy": "seeded"}}
    )
    script = (
        "import json;"
        "from zhixing.benchmark import BenchmarkPlan,ExperimentProtocol,build_schedule;"
        f"p=BenchmarkPlan.model_validate(json.loads({plan.model_dump_json()!r}));"
        f"x=ExperimentProtocol.model_validate(json.loads({protocol.model_dump_json()!r}));"
        "print([(e.task_id,e.agent_id,e.seed) for e in build_schedule(p,x,['b','a'])])"
    )
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": str(Path.cwd())},
    )
    assert completed.returncode == 0, completed.stderr
    expected = [
        (item.task_id, item.agent_id, item.seed)
        for item in build_schedule(plan, protocol, ["b", "a"])
    ]
    assert completed.stdout.strip() == repr(expected)


def test_package_resource_provider_verifies_and_binds_logical_uri(
    tmp_path: Path,
) -> None:
    """Resolve assets only through the explicit Package runtime boundary."""
    package = write_package(tmp_path / "package")
    compiled = compile_benchmark_package(package)
    assert compiled.plan is not None
    provider = PackageBenchmarkResourceProvider(package, compiled.plan)
    bound = provider.bind({"source": "asset://fixture"})
    assert Path(bound["source"]).read_text(encoding="utf-8") == "fixture\n"
    assert str(package) not in compiled.plan.canonical_hash()
    with pytest.raises(ValueError, match="undeclared"):
        provider.resolve("asset://missing")


def test_registry_random_generator_uses_run_local_rng_without_global_drift() -> None:
    """Prefer built-in run-local RNG support over the legacy global adapter."""
    resolver = RegistryBenchmarkComponentResolver()
    reference = PluginReference(
        name="random_int",
        params={"min": 1, "max": 100},
    )
    before = random.getstate()
    first, notes = resolver.generate_task_value(
        reference,
        reference.params,
        rng=Random(99),
    )
    second, _ = resolver.generate_task_value(
        reference,
        reference.params,
        rng=Random(99),
    )
    assert first == second
    assert notes == ()
    assert random.getstate() == before


def test_legacy_generator_adapter_restores_global_random_and_marks_limits() -> None:
    """Isolate legacy global-random plugins and disclose wall-clock limits."""

    @PluginRegistry.register(namespace="benchmark.task", name="test_legacy_random")
    class LegacyRandom:
        """Legacy plugin that only exposes generate(params)."""

        def generate(self, params: Mapping[str, Any]) -> int:
            """Generate through module-global random.

            Args:
                params (Mapping[str, Any]): Unused legacy parameters.

            Raises:
                None.

            Returns:
                int: Pseudorandom value.
            """
            del params
            return random.randint(1, 1000)

    resolver = RegistryBenchmarkComponentResolver(autodiscover=False)
    reference = PluginReference(name="test_legacy_random", params={})
    before = random.getstate()
    first, notes = resolver.generate_task_value(
        reference,
        {},
        rng=Random(42),
    )
    second, _ = resolver.generate_task_value(
        reference,
        {},
        rng=Random(42),
    )
    assert first == second
    assert notes == ("benchmark.materialization.legacy_random_adapter",)
    assert random.getstate() == before

    clock_value, clock_notes = RegistryBenchmarkComponentResolver().generate_task_value(
        PluginReference(
            name="date_relative",
            params={"offset_days": 0, "format": "%Y-%m-%d"},
        ),
        {"offset_days": 0, "format": "%Y-%m-%d"},
        rng=Random(42),
    )
    assert isinstance(clock_value, str)
    assert "benchmark.materialization.wall_clock_dependency" in clock_notes


def test_registry_resolution_error_contains_only_logical_identity() -> None:
    """Keep missing-plugin diagnostics useful without resolver object repr."""
    resolver = RegistryBenchmarkComponentResolver(autodiscover=False)
    with pytest.raises(ValueError) as caught:
        resolver.generate_task_value(
            PluginReference(name="missing_component", params={}),
            {"api_key": "must-not-leak"},
            rng=Random(1),
        )
    message = str(caught.value)
    assert "benchmark.task" in message
    assert "missing_component" in message
    assert "must-not-leak" not in message


def test_legacy_phase_inference_is_auditable_and_preflighted() -> None:
    """Infer only from a uniquely resolved namespace and fail before execute."""
    phase, warning = infer_environment_phase(
        {"name": "reset"},
        FakeResetOperation,
    )
    assert (phase, warning) == (
        "reset",
        "benchmark.environment.phase_inferred",
    )

    class AmbiguousOperation(FakeEnvironmentOperation):
        """Plugin outside the Benchmark environment namespace."""

        __plugin_namespace__ = "external.unknown"

    class AmbiguousResolver(FakeBenchmarkResolver):
        """Resolver returning a class whose phase is unknowable."""

        def resolve_environment(self, call: Mapping[str, Any]) -> type[Any]:
            """Return the intentionally ambiguous class.

            Args:
                call (Mapping[str, Any]): Ignored logical call.

            Raises:
                None.

            Returns:
                type[Any]: Ambiguous operation.
            """
            del call
            return AmbiguousOperation

    device = FakeBenchmarkDevice()
    with pytest.raises(ValueError, match="does not identify"):
        execute_environment_calls(
            ({"name": "unknown", "params": {}},),
            requested_phase="setup",
            resolver=AmbiguousResolver(),
            resource_provider=EmptyBenchmarkResourceProvider(),
            device=device,
        )
    assert device.calls == []


def test_evaluator_tree_preserves_leaf_results_and_short_circuit() -> None:
    """Retain executed and skipped branches instead of one boolean."""
    resolver = FakeBenchmarkResolver()
    device = FakeBenchmarkDevice()
    tree = prepare_evaluator_tree(
        {
            "name": "composite",
            "params": {
                "logic": "OR",
                "rules": [
                    {"name": "fake", "params": {"method": "a", "pass": True}},
                    {"name": "fake", "params": {"method": "b", "pass": False}},
                ],
            },
        },
        resolver=resolver,
        device=device,
    )
    context = {
        "task_params": {"id": "one"},
        "run_result": object(),
    }
    pre = run_evaluator_pre_hooks(tree, context)
    result = evaluate_tree(tree, context)
    assert len(pre) == 2
    assert result.is_pass is True
    assert result.children[0].status is BenchmarkStageStatus.SUCCESS
    assert result.children[1].status is BenchmarkStageStatus.SKIPPED
    assert result.short_circuited is True


def test_nested_and_sequence_tree_retains_all_executed_leaf_evidence() -> None:
    """Evaluate nested composite logic with stable paths and token totals."""
    resolver = FakeBenchmarkResolver()
    device = FakeBenchmarkDevice()
    tree = prepare_evaluator_tree(
        {
            "name": "composite",
            "params": {
                "logic": "AND",
                "rules": [
                    {"name": "fake", "params": {"method": "a", "pass": True}},
                    {
                        "name": "composite",
                        "params": {
                            "logic": "SEQUENCE",
                            "rules": [
                                {
                                    "name": "fake",
                                    "params": {"method": "b", "pass": True},
                                },
                                {
                                    "name": "fake",
                                    "params": {"method": "c", "pass": False},
                                },
                            ],
                        },
                    },
                ],
            },
        },
        resolver=resolver,
        device=device,
    )
    context = {"task_params": {"id": "one"}, "run_result": object()}
    run_evaluator_pre_hooks(tree, context)
    result = evaluate_tree(tree, context)
    assert result.is_pass is False
    assert result.children[1].name == "SEQUENCE"
    assert [item.path for item in result.children[1].children] == [
        "root/1/0",
        "root/1/1",
    ]
    assert result.token == 3.0


def test_executable_agent_reuses_caller_context_and_activation_budget(tmp_path: Path) -> None:
    """Keep caller run identity while applying a run-local activation override."""
    device = FakeBenchmarkDevice()
    runtime = RuntimeContext(
        run_id="caller-owned",
        max_steps=3,
        max_activations=1,
    )
    result = _agent(Action(ActionType.KEY, {"code": "home"})).run(
        "finish",
        device=device,
        runtime=runtime,
        run_config=AgentRunConfig(artifact_root=tmp_path),
    )
    assert result.run_id == "caller-owned"
    assert result.status is not RunStatus.SUCCESS
    assert result.kernel_status == "budget_exhausted"


def test_caller_event_sink_and_context_are_isolated_between_runs(
    tmp_path: Path,
) -> None:
    """Forward Graph events while preserving independent run state."""
    device = FakeBenchmarkDevice()
    agent = _agent(Action(ActionType.KEY, {"code": "home"}))
    captured: list[Any] = []
    first_context = RuntimeContext(
        run_id="first-context",
        max_steps=3,
        max_activations=30,
        event_sink=captured.append,
    )
    first = agent.run(
        "first",
        AgentRunConfig(artifact_root=tmp_path),
        device=device,
        runtime=first_context,
    )
    second = agent.run(
        "second",
        AgentRunConfig(artifact_root=tmp_path),
        device=device,
        runtime=RuntimeContext(
            run_id="second-context",
            max_steps=3,
            max_activations=30,
        ),
    )
    assert first.status is RunStatus.SUCCESS
    assert second.status is RunStatus.SUCCESS
    assert first.run_id != second.run_id
    assert captured
    assert {event.run_id for event in captured} == {"first-context"}


@pytest.mark.fake_device_integration
def test_suite_runs_two_agents_repeats_and_evaluation_failure(tmp_path: Path) -> None:
    """Execute the complete lifecycle without importing or calling AgentRunner."""
    plan = _plan()
    protocol = ExperimentProtocol.model_validate(
        {
            "repeats": 2,
            "budget": {
                "max_interactions": 3,
                "max_activations": 30,
                "timeout_seconds": 30,
            },
        }
    )
    resolver = FakeBenchmarkResolver()
    device = FakeBenchmarkDevice()
    result = BenchmarkExperimentRuntime().run(
        plan,
        protocol,
        {
            "home": _agent(Action(ActionType.KEY, {"code": "home"})),
            "back": _agent(Action(ActionType.KEY, {"code": "back"})),
        },
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=resolver,
        device=device,
    )
    assert len(result.results) == 8
    assert result.counts == {
        "pass": 4,
        "fail": 4,
        "invalid": 0,
        "skipped": 0,
    }
    assert resolver.generated == 4
    assert all(item.agent_result is not None for item in result.results)
    assert all(
        item.agent_result.status is RunStatus.SUCCESS
        for item in result.results
        if item.agent_result is not None
    )
    assert all(
        item.task_instance_identity
        == next(
            other.task_instance_identity
            for other in result.results
            if other.task_id == item.task_id
            and other.repeat == item.repeat
        )
        for item in result.results
    )
    assert {event.kind for event in result.lifecycle_events} >= {
        "start",
        "complete",
    }
    assert all(
        (tmp_path / item.task_run_id / "benchmark-result.json").is_file()
        for item in result.results
    )
    assert [call[1] for call in device.calls if call[0] == "environment"].count(
        "one-reset"
    ) == 4


@pytest.mark.fake_device_integration
def test_complete_fake_experiment_reports_comparable_mixed_outcomes(
    tmp_path: Path,
) -> None:
    """Close dynamic two-Agent reporting with PASS/FAIL/INVALID evidence."""
    plan = _mixed_evaluation_plan()
    protocol = ExperimentProtocol.model_validate(
        {
            "seed": 19,
            "repeats": 2,
            "budget": {
                "max_interactions": 3,
                "max_activations": 30,
                "timeout_seconds": 30,
            },
        }
    )
    agents = {
        "home": _agent(Action(ActionType.KEY, {"code": "home"})),
        "back": _agent(Action(ActionType.KEY, {"code": "back"})),
    }
    expected_schedule = build_schedule(plan, protocol, list(agents))
    assert expected_schedule == build_schedule(plan, protocol, list(agents))
    resolver = FakeBenchmarkResolver()
    result = BenchmarkExperimentRuntime().run(
        plan,
        protocol,
        agents,
        run_config=BenchmarkRunConfig(
            artifact_root=tmp_path,
            experiment_id="fake-complete-loop",
        ),
        resolver=resolver,
        device=FakeBenchmarkDevice(),
    )
    assert result.counts == {
        "pass": 4,
        "fail": 4,
        "invalid": 4,
        "skipped": 0,
    }
    assert resolver.generated == 6
    assert len({item.task_run_id for item in result.results}) == len(
        result.results
    )
    assert all(
        item.agent_result is not None
        and item.agent_result.run_id == item.task_run_id
        and all(
            event.run_id == item.task_run_id
            for event in item.agent_result.events
        )
        for item in result.results
    )
    assert all(
        item.task_instance_identity
        == next(
            other.task_instance_identity
            for other in result.results
            if other.task_id == item.task_id
            and other.repeat == item.repeat
            and other.agent_id != item.agent_id
        )
        for item in result.results
    )
    experiment_root = tmp_path / result.experiment_id
    report = load_experiment_report(
        experiment_root / "experiment-report.json"
    )
    assert {item.agent_id for item in report.agent_metrics} == {"home", "back"}
    assert report.comparisons[0].paired is True
    assert report.comparisons[0].matched_count == 4
    assert report.comparisons[0].significance_claimed is False
    assert verify_trajectory_bundle(
        experiment_root / "trajectory-bundle.zip"
    )


def test_preflight_invalidates_without_agent_or_environment_side_effects(
    tmp_path: Path,
) -> None:
    """Reject an unverified device before reset, Agent, or evaluator calls."""
    device = FakeBenchmarkDevice()
    device.locale = ""
    result = BenchmarkExperimentRuntime().run(
        _plan(),
        ExperimentProtocol(repeats=1),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
    )
    assert result.counts["invalid"] == 2
    assert device.calls == [("shell", "getprop persist.sys.locale")]


def test_preflight_falls_back_to_product_locale(
    tmp_path: Path,
) -> None:
    """Use the immutable product locale when the persistent override is empty."""

    class ProductLocaleDevice(FakeBenchmarkDevice):
        """Fake Android device exposing locale only through ro.product.locale."""

        locale = ""

        def shell(
            self,
            command: str,
            error_raise: bool = False,
        ) -> FakeShellResult:
            """Return command-specific locale evidence.

            Args:
                command (str): Read-only Android shell command.
                error_raise (bool): Legacy compatibility flag.

            Raises:
                None.

            Returns:
                FakeShellResult: Product locale or generic success output.
            """
            del error_raise
            self.calls.append(("shell", command))
            if command == "getprop persist.sys.locale":
                return FakeShellResult("")
            if command == "getprop ro.product.locale":
                return FakeShellResult("en-US")
            return FakeShellResult("ok")

    device = ProductLocaleDevice()
    result = BenchmarkExperimentRuntime().run(
        BenchmarkPlan.model_copy(
            _plan(),
            update={"tasks": (_plan().tasks[0],)},
        ),
        ExperimentProtocol(repeats=1),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
    )
    assert result.results[0].outcome is BenchmarkOutcome.PASS
    assert device.calls[:2] == [
        ("shell", "getprop persist.sys.locale"),
        ("shell", "getprop ro.product.locale"),
    ]


def test_before_each_task_warns_and_resets_once_per_agent_batch(
    tmp_path: Path,
) -> None:
    """Make shared device state explicit when comparing multiple Agents."""
    protocol = ExperimentProtocol.model_validate(
        {
            "isolation": {
                "reset": "before_each_task",
                "cleanup": "after_each_run",
                "require_verified_reset": True,
            }
        }
    )
    device = FakeBenchmarkDevice()
    result = BenchmarkExperimentRuntime().run(
        _plan(),
        protocol,
        {
            "a": _agent(Action(ActionType.KEY, {"code": "home"})),
            "b": _agent(Action(ActionType.KEY, {"code": "back"})),
        },
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
    )
    assert "benchmark.protocol.shared_device_state_across_agents" in (
        result.fairness_warnings
    )
    reset_labels = [
        call[1]
        for call in device.calls
        if call[0] == "environment" and str(call[1]).endswith("-reset")
    ]
    assert reset_labels.count("one-reset") == 1
    assert reset_labels.count("two-reset") == 1


def test_after_each_task_cleanup_evidence_is_shared_by_all_agents(
    tmp_path: Path,
) -> None:
    """Attach one task-batch cleanup result to every affected Agent result."""
    protocol = ExperimentProtocol.model_validate(
        {
            "isolation": {
                "reset": "before_each_agent",
                "cleanup": "after_each_task",
                "require_verified_reset": True,
            }
        }
    )
    device = FakeBenchmarkDevice()
    result = BenchmarkExperimentRuntime().run(
        _plan(),
        protocol,
        {
            "a": _agent(Action(ActionType.KEY, {"code": "home"})),
            "b": _agent(Action(ActionType.KEY, {"code": "back"})),
        },
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
    )

    cleanup_labels = [
        call[1]
        for call in device.calls
        if call[0] == "environment" and str(call[1]).endswith("-cleanup")
    ]
    assert cleanup_labels.count("one-cleanup") == 1
    assert cleanup_labels.count("two-cleanup") == 1
    for task_id in ("one", "two"):
        task_results = [item for item in result.results if item.task_id == task_id]
        references = {
            next(
                stage.artifact_refs[0]
                for stage in item.stages
                if stage.phase == "cleanup_shared"
            )
            for item in task_results
        }
        assert len(references) == 1
        assert all(
            any(event.phase == "cleanup_shared" for event in item.lifecycle_events)
            for item in task_results
        )


def test_once_boundaries_share_reset_and_cleanup_evidence(
    tmp_path: Path,
) -> None:
    """Execute suite reset/cleanup at unique boundaries with shared references."""
    protocol = ExperimentProtocol.model_validate(
        {
            "isolation": {
                "reset": "once",
                "cleanup": "once",
                "require_verified_reset": True,
            }
        }
    )
    device = FakeBenchmarkDevice()
    result = BenchmarkExperimentRuntime().run(
        _plan(),
        protocol,
        {
            "a": _agent(Action(ActionType.KEY, {"code": "home"})),
            "b": _agent(Action(ActionType.KEY, {"code": "back"})),
        },
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
    )

    assert [
        event.kind
        for event in result.lifecycle_events
        if event.phase == "reset_shared"
    ] == ["start", "complete"]
    assert [
        event.kind
        for event in result.lifecycle_events
        if event.phase == "cleanup_shared"
    ] == ["start", "complete"]
    reset_refs = {
        next(
            stage.artifact_refs[0]
            for stage in item.stages
            if stage.phase == "reset_shared"
        )
        for item in result.results
    }
    cleanup_refs = {
        next(
            stage.artifact_refs[0]
            for stage in item.stages
            if stage.phase == "cleanup_shared"
        )
        for item in result.results
    }
    assert len(reset_refs) == 1
    assert len(cleanup_refs) == 1
    assert all(
        any(
            stage.phase == "reset"
            and next(iter(reset_refs)) in stage.artifact_refs
            for stage in item.stages
        )
        for item in result.results
    )
    assert all(
        any(
            stage.phase == "cleanup"
            and next(iter(cleanup_refs)) in stage.artifact_refs
            for stage in item.stages
        )
        for item in result.results
    )


def test_strict_fairness_rejects_shared_state_before_side_effects(
    tmp_path: Path,
) -> None:
    """Reject an unsafe comparison before reset or Graph execution."""
    protocol = ExperimentProtocol.model_validate(
        {
            "task_materialization": {
                "reuse_across_agents": True,
                "strict_fairness": True,
            },
            "isolation": {
                "reset": "before_each_task",
                "cleanup": "after_each_run",
                "require_verified_reset": True,
            },
        }
    )
    device = FakeBenchmarkDevice()
    with pytest.raises(ValueError, match="strict fairness"):
        BenchmarkExperimentRuntime().run(
            _plan(),
            protocol,
            {
                "a": _agent(Action(ActionType.KEY, {"code": "home"})),
                "b": _agent(Action(ActionType.KEY, {"code": "back"})),
            },
            run_config=BenchmarkRunConfig(artifact_root=tmp_path),
            resolver=FakeBenchmarkResolver(),
            device=device,
        )
    assert device.calls == []


def test_cleanup_failure_can_stop_suite_and_marks_remaining_skipped(
    tmp_path: Path,
) -> None:
    """Apply cleanup failure policy without erasing evaluator evidence."""
    first = _task("one")
    first["cleanup_initializer"][0]["params"]["fail"] = True
    suite = BenchmarkSuite.model_validate([first, _task("two")])
    compiled = compile_benchmark_suite(suite)
    assert compiled.plan is not None
    protocol = ExperimentProtocol.model_validate(
        {
            "failure": {
                "initializer": {
                    "outcome": "invalidate",
                    "continue_suite": True,
                    "preserve_evidence": True,
                },
                "agent": {
                    "outcome": "evaluate_if_possible",
                    "continue_suite": True,
                    "preserve_evidence": True,
                },
                "evaluator": {
                    "outcome": "invalidate",
                    "continue_suite": True,
                    "preserve_evidence": True,
                },
                "cleanup": {
                    "outcome": "invalidate",
                    "continue_suite": False,
                    "preserve_evidence": True,
                },
            }
        }
    )
    result = BenchmarkExperimentRuntime().run(
        compiled.plan,
        protocol,
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert [item.outcome for item in result.results] == [
        BenchmarkOutcome.INVALID,
        BenchmarkOutcome.SKIPPED,
    ]
    assert result.results[0].evaluation is not None
    assert result.results[0].evaluation.is_pass is True


def test_new_runtime_does_not_construct_legacy_agent_runner(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Prove the graph-native path succeeds when AgentRunner is forbidden."""

    def forbidden(*args: Any, **kwargs: Any) -> None:
        """Fail on any legacy runner construction.

        Args:
            *args (Any): Ignored positional arguments.
            **kwargs (Any): Ignored keyword arguments.

        Raises:
            AssertionError: Always.

        Returns:
            None.
        """
        del args, kwargs
        raise AssertionError("AgentRunner must not be used")

    monkeypatch.setattr("zhixing.core.runner.AgentRunner", forbidden)
    one_task = _plan().model_copy(update={"tasks": (_plan().tasks[0],)})
    result = BenchmarkExperimentRuntime().run(
        one_task,
        ExperimentProtocol(),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert result.results[0].outcome is BenchmarkOutcome.PASS


def test_protocol_activation_budget_and_cooperative_timeout_are_enforced(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """Apply Protocol budgets without changing AgentGraph identity."""
    plan = _plan().model_copy(update={"tasks": (_plan().tasks[0],)})
    agent = _agent(Action(ActionType.KEY, {"code": "home"}))
    graph_identity = agent.canonical_hash
    budgeted = ExperimentProtocol.model_validate(
        {
            "budget": {
                "max_interactions": 1,
                "max_activations": 1,
                "timeout_seconds": 30,
            }
        }
    )
    exhausted = BenchmarkExperimentRuntime().run(
        plan,
        budgeted,
        {"agent": agent},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path / "budget"),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert exhausted.results[0].agent_result is not None
    assert exhausted.results[0].agent_result.kernel_status == "budget_exhausted"
    assert agent.canonical_hash == graph_identity

    class AlreadyCancelled:
        """Signal returned by the patched deadline factory."""

        def is_cancelled(self) -> bool:
            """Report immediate cooperative cancellation.

            Returns:
                bool: Always true.
            """
            return True

    monkeypatch.setattr(
        "zhixing.benchmark.runtime.engine.DeadlineCancellation.after",
        lambda seconds: AlreadyCancelled(),
    )
    cancelled = BenchmarkExperimentRuntime().run(
        plan,
        ExperimentProtocol(),
        {"agent": agent},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path / "cancel"),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert cancelled.results[0].agent_result is not None
    assert cancelled.results[0].agent_result.kernel_status == "cancelled"


def test_runtime_external_cancellation_before_device_has_no_side_effects(
    tmp_path: Path,
) -> None:
    """Skip scheduled work without touching the device or publishing artifacts."""
    plan = _plan().model_copy(update={"tasks": (_plan().tasks[0],)})
    device = FakeBenchmarkDevice()
    signal = SimpleCancellationSignal(cancelled=True)

    result = BenchmarkExperimentRuntime().run(
        plan,
        ExperimentProtocol(),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(
            artifact_root=tmp_path,
            experiment_id="cancelled-before-device",
        ),
        resolver=FakeBenchmarkResolver(),
        device=device,
        cancellation=signal,
    )

    assert result.results[0].outcome is BenchmarkOutcome.SKIPPED
    assert device.calls == []
    assert (tmp_path / "cancelled-before-device" / "experiment-report.json").is_file()


def test_runtime_active_agent_cancellation_preserves_cleanup(
    tmp_path: Path,
) -> None:
    """Propagate caller cancellation into Agent Runtime and still run cleanup."""
    signal = SimpleCancellationSignal()

    class CancellingDevice(FakeBenchmarkDevice):
        """Fake device that requests cancellation during the Agent action."""

        def go_home(self) -> None:
            """Record HOME and request cooperative cancellation.

            Returns:
                None.
            """
            super().go_home()
            signal.cancel()

    plan = _plan().model_copy(update={"tasks": (_plan().tasks[0],)})
    device = CancellingDevice()
    result = BenchmarkExperimentRuntime().run(
        plan,
        ExperimentProtocol(),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
        cancellation=signal,
    )

    assert result.results[0].agent_result is not None
    assert result.results[0].agent_result.kernel_status == "cancelled"
    assert result.results[0].outcome is BenchmarkOutcome.SKIPPED
    assert next(
        stage
        for stage in result.results[0].stages
        if stage.phase == "evaluation"
    ).status is BenchmarkStageStatus.SKIPPED
    assert ("environment", "one-cleanup") in device.calls


def test_runtime_evaluation_cancellation_retains_evidence_and_cleanup(
    tmp_path: Path,
) -> None:
    """Keep completed Evaluation facts when cancellation arrives in that phase."""
    signal = SimpleCancellationSignal()

    class CancellingEvaluator(FakeEvaluator):
        """Evaluator that requests cancellation after producing its result."""

        def evaluate(self, context: Mapping[str, Any]) -> EvalResult:
            """Evaluate normally, then request cancellation.

            Args:
                context (Mapping[str, Any]): Legacy-compatible evaluation view.

            Raises:
                AssertionError: Evaluation preconditions are absent.

            Returns:
                EvalResult: Configured fake evaluation result.
            """
            result = super().evaluate(context)
            signal.cancel()
            return result

    class CancellingResolver(FakeBenchmarkResolver):
        """Resolver selecting the cancellation-aware evaluator."""

        def resolve_evaluator(self, config: Mapping[str, Any]) -> type[Any]:
            """Resolve every leaf to the cancellation-aware evaluator.

            Args:
                config (Mapping[str, Any]): Leaf definition.

            Raises:
                None.

            Returns:
                type[Any]: Cancellation-aware evaluator class.
            """
            del config
            return CancellingEvaluator

    plan = _plan().model_copy(update={"tasks": (_plan().tasks[0],)})
    device = FakeBenchmarkDevice()
    result = BenchmarkExperimentRuntime().run(
        plan,
        ExperimentProtocol(),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=CancellingResolver(),
        device=device,
        cancellation=signal,
    )

    assert result.results[0].evaluation is not None
    assert result.results[0].evaluation.is_pass is True
    assert result.results[0].outcome is BenchmarkOutcome.PASS
    assert ("environment", "one-cleanup") in device.calls


def test_runtime_deferred_publication_returns_facts_without_files(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Return complete suite facts without invoking the reporting finalizer."""
    finalized = False

    def forbidden_finalizer(*args: Any, **kwargs: Any) -> None:
        """Record and reject any unexpected publication attempt.

        Args:
            *args (Any): Ignored positional arguments.
            **kwargs (Any): Ignored keyword arguments.

        Raises:
            AssertionError: Always, because defer must bypass publication.

        Returns:
            None.
        """
        nonlocal finalized
        del args, kwargs
        finalized = True
        raise AssertionError("deferred execution must not publish artifacts")

    monkeypatch.setattr(
        "zhixing.benchmark.runtime.suite.finalize_suite_result",
        forbidden_finalizer,
    )
    plan = _plan().model_copy(update={"tasks": (_plan().tasks[0],)})
    result = BenchmarkExperimentRuntime().run(
        plan,
        ExperimentProtocol(),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(
            artifact_root=tmp_path,
            publication_policy=BenchmarkPublicationPolicy.DEFER,
        ),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )

    assert result.results[0].outcome is BenchmarkOutcome.PASS
    assert result.results[0].evaluation is not None
    assert finalized is False
    assert not (tmp_path / result.experiment_id / "experiment-report.json").exists()
    assert not (tmp_path / result.experiment_id / "trajectory-bundle.zip").exists()
    assert not (
        tmp_path
        / result.results[0].task_run_id
        / "benchmark-result.json"
    ).exists()


def test_strict_unobservable_token_budget_invalidates_result(
    tmp_path: Path,
) -> None:
    """Do not treat absent model usage as zero tokens."""
    protocol = ExperimentProtocol.model_validate(
        {
            "budget": {
                "max_interactions": 3,
                "max_activations": 30,
                "timeout_seconds": 30,
                "token_limit": 50,
                "require_observable_tokens": True,
            }
        }
    )
    result = BenchmarkExperimentRuntime().run(
        BenchmarkPlan.model_copy(_plan(), update={"tasks": (_plan().tasks[0],)}),
        protocol,
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=FakeBenchmarkDevice(),
    )
    assert result.results[0].outcome is BenchmarkOutcome.INVALID
    token_stage = next(
        stage
        for stage in result.results[0].stages
        if stage.phase == "token_budget"
    )
    assert token_stage.status is BenchmarkStageStatus.UNVERIFIED


def test_safe_suite_serialization_redacts_runtime_only_values(tmp_path: Path) -> None:
    """Keep host artifact roots and live device repr outside result JSON."""
    device = FakeBenchmarkDevice()
    result = BenchmarkExperimentRuntime().run(
        _plan(),
        ExperimentProtocol(repeats=1),
        {"agent": _agent(Action(ActionType.KEY, {"code": "home"}))},
        run_config=BenchmarkRunConfig(artifact_root=tmp_path),
        resolver=FakeBenchmarkResolver(),
        device=device,
    )
    text = str(result.to_safe_dict())
    assert str(tmp_path) not in text
    assert "FakeBenchmarkDevice object" not in text


def test_runtime_dtos_redact_secrets_paths_and_live_repr() -> None:
    """Bound result serialization even when a caller supplies unsafe payloads."""
    event = BenchmarkLifecycleEvent(
        experiment_id="experiment",
        sequence=1,
        phase="setup",
        kind="fail",
        payload={
            "api_key": "secret-value",
            "path": "/Users/example/private/file.txt",
            "device": FakeBenchmarkDevice(),
        },
    )
    safe = str(event.to_safe_dict())
    assert "secret-value" not in safe
    assert "/Users/example" not in safe
    assert "FakeBenchmarkDevice object" not in safe
