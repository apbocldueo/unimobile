"""Frozen compatibility evidence for the Benchmark package migration."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest


requires_upstream_packages = pytest.mark.skipif(
    not (Path(__file__).resolve().parents[2] / "benchmarks/android_world/benchmark.yaml").is_file(),
    reason="Upstream Benchmark assets are omitted from the public release pending redistribution review",
)

from zhixing.benchmark import (
    BenchmarkCatalog,
    BenchmarkExperimentRuntime,
    BenchmarkPlan,
    BenchmarkTaskResult,
    BenchmarkValidationLevel,
    compile_benchmark_package,
)
from zhixing.cli import main
from zhixing.components import EvalResult, EvaluationResult, EvaluationResultV2
from zhixing.components.protocols import ComponentRole, ROLE_DESCRIPTORS


_PACKAGE_IDENTITIES = {
    "android_world": {
        "content": "sha256:4e70bd49163ada95536ada3ef679cb37ee0dc667d8c8dcb03fe77b0f0859431d",
        "plan": "sha256:fe8b170a866a2b91afb501bd0d6b195b05783d908a8debca5f430d4cf2b257df",
        "protocol": "sha256:21f1c9fde5b9f8da2bffc52a82fb055dc0fb7367a39ba6f78e3ccc6db49f0b24",
    },
    "appagent": {
        "content": "sha256:870a6618b985591f79caf95de356f9df8092e2d00d66837b7fb835b2b9055ec1",
        "plan": "sha256:54050a5c4b3324a22a0534b68460fdb12e1e7003013f743b7772e2a319fe147b",
        "protocol": "sha256:21f1c9fde5b9f8da2bffc52a82fb055dc0fb7367a39ba6f78e3ccc6db49f0b24",
    },
}


def test_documented_benchmark_import_surface_is_stable() -> None:
    """Freeze representative definition and runtime imports before migration."""
    assert BenchmarkCatalog.__name__ == "BenchmarkCatalog"
    assert BenchmarkPlan.__name__ == "BenchmarkPlan"
    assert BenchmarkExperimentRuntime.__name__ == "BenchmarkExperimentRuntime"
    assert BenchmarkTaskResult.__name__ == "BenchmarkTaskResult"


def test_evaluator_descriptor_moves_to_v2_without_removing_legacy_alias() -> None:
    """Protect the explicit V2 boundary and legacy import compatibility."""
    descriptor = ROLE_DESCRIPTORS[ComponentRole.EVALUATOR]
    assert descriptor.output_type is EvaluationResultV2
    assert EvaluationResult is EvalResult


@requires_upstream_packages
def test_builtin_package_and_plan_identities_are_frozen() -> None:
    """Protect existing package, plan, and protocol identities during migration."""
    for package_name, expected in _PACKAGE_IDENTITIES.items():
        compiled = compile_benchmark_package(
            f"benchmarks/{package_name}",
            validation_level=BenchmarkValidationLevel.RESOURCES,
        )
        assert compiled.plan is not None
        assert compiled.protocol is not None
        assert compiled.plan.package_content_identity == expected["content"]
        assert compiled.plan.canonical_hash() == expected["plan"]
        assert compiled.protocol.canonical_hash() == expected["protocol"]


@requires_upstream_packages
def test_benchmark_cli_validation_exit_and_text_contract_is_stable() -> None:
    """Freeze the installed validation command's success summary and exit code."""
    stdout = StringIO()
    stderr = StringIO()
    exit_code = main(
        [
            "benchmark",
            "validate",
            "benchmarks/android_world",
            "--no-installed",
        ],
        stdout=stdout,
        stderr=stderr,
    )
    assert exit_code == 0
    assert stderr.getvalue() == ""
    lines = stdout.getvalue().splitlines()
    assert lines[0] == "valid: true"
    assert lines[1] == f"plan_identity: {_PACKAGE_IDENTITIES['android_world']['plan']}"
    assert lines[2] == (
        "protocol_identity: "
        f"{_PACKAGE_IDENTITIES['android_world']['protocol']}"
    )
    assert lines[3] == (
        "note: definition-layer validation only; no task was executed"
    )
