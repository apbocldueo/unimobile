"""Guard the user-selected core release boundary independently of Git ignores."""

from pathlib import Path

from scripts.build_public_release import load_manifest, select_paths


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "release/paper-core-manifest.json"


def test_core_profile_withholds_upstream_ports_and_their_copied_fixtures() -> None:
    """Deny copied integrations even when their files are already Git-tracked.

    Raises:
        AssertionError: A withheld implementation, fixture or example is selected.
    Returns:
        None.
    """
    paths = (
        "zhixing/runtime/kernel.py",
        "zhixing/graph/agent_sama_contracts.py",
        "zhixing/plugins/agent/sama_official/source.py",
        "zhixing/plugins/agent/androidarena/source.py",
        "zhixing/plugins/agent/vdroid/_source_ui.py",
        "zhixing/plugins/agent/moba/source.py",
        "zhixing/plugins/agent/visiontasker/upstream/new_file.py.txt",
        "tests/fixtures/agent_sama/official_backend.py",
        "tests/fixtures/androidarena/new_file.py.txt",
        "tests/fixtures/vdroid/selection_source.py",
        "examples/graphs/agent_sama_online_no_mentor.yaml",
        "examples/graphs/androidarena_online.yaml",
        "examples/graphs/vdroid_selection.yaml",
    )
    assert set(select_paths(paths, load_manifest(MANIFEST))) == {
        "zhixing/runtime/kernel.py",
        "zhixing/graph/agent_sama_contracts.py",
    }


def test_core_profile_keeps_independent_benchmark_and_runnable_framework_inputs() -> None:
    """Retain both contracts, full task-definition inputs, and test helper tools.

    Raises:
        AssertionError: Required public source inputs are silently omitted.
    Returns:
        None.
    """
    paths = (
        "zhixing/config/contracts/agent.py",
        "zhixing/config/contracts/benchmark.py",
        "zhixing/benchmark/compiler/loader.py",
        "examples/benchmark_v1/android_world.json",
        "examples/benchmark_v1/android_world_missing.json",
        "examples/agent_mobileagent.yaml",
        "scripts/export_legacy_workflow_yaml.py",
        "scripts/simplify_workflow_yaml.py",
        "zhixing/plugins/agent/m3a/LICENSE",
    )
    assert set(select_paths(paths, load_manifest(MANIFEST))) == set(paths)


def test_core_profile_denies_private_plans_generated_dependencies_and_logs() -> None:
    """Keep private learning state and generated artifacts out of tracked exports.

    Raises:
        AssertionError: A local-only or generated path crosses the source boundary.
    Returns:
        None.
    """
    paths = (
        ".local/interview-plan.md",
        "docs/interview/agent-graph-ir.md",
        "paper/main.tex",
        "studio/node_modules/anything/index.js",
        "studio/dist/index.html",
        "studio/device-profiles.json",
        "zhixing/temp/log/zhixing_studio.log",
        "zhixing/local.sqlite",
        "secrets.local copy.yaml",
    )
    assert select_paths(paths, load_manifest(MANIFEST)) == ()
