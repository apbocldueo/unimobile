"""Compiler, Catalog, CLI, and first-party Package acceptance tests."""

from __future__ import annotations

import io
import json
from pathlib import Path, PurePosixPath

import pytest
import yaml

from zhixing.benchmark import (
    BenchmarkCatalog,
    BenchmarkDefinitionError,
    BenchmarkValidationLevel,
    compile_benchmark_package,
    discover_benchmark_candidates,
    enumerate_installed_benchmarks,
)
from zhixing.cli import main

from .helpers import task, write_package

ROOT = Path(__file__).resolve().parents[2]
BUILTIN_ROOT = ROOT / "benchmarks"
requires_upstream_packages = pytest.mark.skipif(
    not (BUILTIN_ROOT / "android_world/benchmark.yaml").is_file(),
    reason="Upstream Benchmark assets are omitted from the public release pending redistribution review",
)


class _FakeDistribution:
    """Distribution metadata fixture that never imports a module."""

    def __init__(self, package_root: Path) -> None:
        """Initialize resource metadata.

        Args:
            package_root (Path): Directory containing benchmark.yaml.

        Raises:
            None.

        Returns:
            None.
        """
        self._root = package_root.parent.parent
        self.files = (
            PurePosixPath("fixture_benchmark/package/benchmark.yaml"),
        )
        self.metadata = {"Name": "fixture-benchmark"}
        self.version = "1.0.0"

    def locate_file(self, path: PurePosixPath) -> Path:
        """Resolve one distribution-owned file.

        Args:
            path (PurePosixPath): Distribution-relative resource path.

        Raises:
            None.

        Returns:
            Path: Fixture resource path.
        """
        del path
        return self._root / "fixture_benchmark/package/benchmark.yaml"


class _FakeEntryPoint:
    """Entry Point fixture whose load method must never be called."""

    value = "fixture_benchmark.package"

    def __init__(self, distribution: _FakeDistribution) -> None:
        """Attach distribution metadata.

        Args:
            distribution (_FakeDistribution): Fixture distribution.

        Raises:
            None.

        Returns:
            None.
        """
        self.dist = distribution
        self.loaded = False

    def load(self) -> None:
        """Fail if metadata-only discovery executes third-party code.

        Raises:
            AssertionError: Always; load is forbidden.

        Returns:
            None.
        """
        self.loaded = True
        raise AssertionError("EntryPoint.load must not be called")


def test_compile_dynamic_package_does_not_materialize_or_import(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keep generators, evaluators, devices, and models outside compilation."""
    dynamic = task()
    dynamic["type"] = "dynamic"
    dynamic["instruction"] = "Open ${target}"
    dynamic["task_initializer"] = {
        "target": {"name": "would_execute", "params": {}}
    }
    package = write_package(tmp_path / "package", tasks=[dynamic])
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["plugins"].append({"id": "would_execute", "optional": False})
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    imported: list[str] = []
    original_import = __import__

    def guarded_import(name: str, *args, **kwargs):
        """Record forbidden implementation imports during compilation.

        Args:
            name (str): Module name.
            *args: Import positional arguments.
            **kwargs: Import keyword arguments.

        Raises:
            AssertionError: A runtime implementation module is imported.

        Returns:
            object: Imported non-runtime module.
        """
        if name.startswith(("zhixing.devices", "zhixing.plugins", "openai")):
            imported.append(name)
            raise AssertionError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    result = compile_benchmark_package(package)
    assert result.is_success
    assert result.plan is not None
    assert result.plan.tasks[0].task_initializer["target"].name == "would_execute"
    assert imported == []


def test_full_validation_aggregates_resource_and_protocol_failures(
    tmp_path: Path,
) -> None:
    """Return multiple independently detectable definition errors."""
    package = write_package(tmp_path / "package")
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["resources"][0]["sha256"] = "sha256:" + "0" * 64
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    protocol_path = package / "protocols" / "default.yaml"
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    protocol["budget"]["max_interactions"] = 0
    protocol_path.write_text(yaml.safe_dump(protocol, sort_keys=False), encoding="utf-8")
    result = compile_benchmark_package(
        package,
        validation_level=BenchmarkValidationLevel.FULL,
    )
    codes = {item.code for item in result.diagnostics}
    assert "benchmark.resource.digest_mismatch" in codes
    assert "benchmark.protocol.invalid" in codes
    assert result.plan is None


def test_package_rejects_cwd_dependent_local_path(tmp_path: Path) -> None:
    """Require asset URI use for Package host-resource fields."""
    package = write_package(
        tmp_path / "package",
        tasks=[task(local_path="data/private/fixture.txt")],
    )
    result = compile_benchmark_package(package)
    assert not result.is_success
    assert any(
        item.code == "benchmark.resource.cwd_reference"
        for item in result.diagnostics
    )


def test_catalog_discovers_only_explicit_local_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Avoid recursive or implicit current-working-directory discovery."""
    catalog_root = tmp_path / "catalog"
    package = write_package(catalog_root / "fixture")
    unrelated = write_package(tmp_path / "unrelated")
    monkeypatch.chdir(tmp_path)
    candidates = discover_benchmark_candidates(
        catalog_roots=[catalog_root],
        include_installed=False,
    )
    assert [item.root for item in candidates] == [package.resolve()]
    assert unrelated.resolve() not in {item.root for item in candidates}


def test_installed_discovery_uses_distribution_files_without_loading(
    tmp_path: Path,
) -> None:
    """Locate installed resource metadata without EntryPoint.load or import."""
    resource_root = tmp_path / "fixture_benchmark" / "package"
    write_package(resource_root)
    entry_point = _FakeEntryPoint(_FakeDistribution(resource_root))
    candidates = enumerate_installed_benchmarks([entry_point])
    assert len(candidates) == 1
    assert candidates[0].source_kind == "installed"
    assert candidates[0].distribution == "fixture-benchmark"
    assert entry_point.loaded is False


def test_local_and_installed_sources_share_semantic_identity(
    tmp_path: Path,
) -> None:
    """Keep discovery provenance outside Package and Plan identity."""
    resource_root = tmp_path / "fixture_benchmark" / "package"
    write_package(resource_root)
    entry_point = _FakeEntryPoint(_FakeDistribution(resource_root))
    candidates = discover_benchmark_candidates(
        package_dirs=[resource_root],
        installed_entry_points=[entry_point],
    )
    assert {item.source_kind for item in candidates} == {"local", "installed"}
    catalog = BenchmarkCatalog(candidates)
    resolved = catalog.resolve("tests/fixture@1.0.0")
    selected = compile_benchmark_package(resolved.root)
    direct = compile_benchmark_package(resource_root)
    assert selected.plan is not None and direct.plan is not None
    assert selected.plan.canonical_hash() == direct.plan.canonical_hash()
    assert entry_point.loaded is False


def test_catalog_detects_same_version_content_drift(tmp_path: Path) -> None:
    """Reject readable identity collisions when semantic content differs."""
    first = write_package(tmp_path / "first")
    second = write_package(tmp_path / "second", tasks=[task("changed")])
    candidates = discover_benchmark_candidates(
        package_dirs=[first, second],
        include_installed=False,
    )
    catalog = BenchmarkCatalog(candidates)
    with pytest.raises(BenchmarkDefinitionError) as caught:
        catalog.resolve("tests/fixture@1.0.0")
    assert "benchmark.catalog.identity_ambiguous" in {
        item.code for item in caught.value.diagnostics
    }


@requires_upstream_packages
def test_cli_list_info_validate_are_definition_only() -> None:
    """Expose stable metadata and validation commands for first-party Packages."""
    for argv, expected in (
        (
            [
                "benchmark",
                "list",
                "--catalog-root",
                str(BUILTIN_ROOT),
                "--no-installed",
                "--json",
            ],
            "zhixing/android-world@1.0.0",
        ),
        (
            [
                "benchmark",
                "info",
                "zhixing/appagent@1.0.0",
                "--catalog-root",
                str(BUILTIN_ROOT),
                "--no-installed",
                "--json",
            ],
            '"test": 45',
        ),
        (
            [
                "benchmark",
                "validate",
                "zhixing/android-world@1.0.0",
                "--catalog-root",
                str(BUILTIN_ROOT),
                "--no-installed",
            ],
            "definition-layer validation only",
        ),
    ):
        output = io.StringIO()
        error = io.StringIO()
        code = main(argv, stdout=output, stderr=error, stdin=io.StringIO())
        assert code == 0, error.getvalue()
        assert expected in output.getvalue()
        assert "emulator-5554" not in output.getvalue()


def test_cli_reports_safe_invalid_digest(tmp_path: Path) -> None:
    """Return a nonzero code and stable JSON without source absolute paths."""
    package = write_package(tmp_path / "package")
    manifest_path = package / "benchmark.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    manifest["resources"][0]["sha256"] = "sha256:" + "0" * 64
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    output = io.StringIO()
    error = io.StringIO()
    code = main(
        ["benchmark", "validate", str(package), "--no-installed", "--json"],
        stdout=output,
        stderr=error,
        stdin=io.StringIO(),
    )
    assert code == 2
    payload = json.loads(output.getvalue())
    assert payload["ok"] is False
    assert str(tmp_path) not in output.getvalue()


@requires_upstream_packages
def test_first_party_packages_and_migration_reports() -> None:
    """Verify task counts, resource closure, and auditable source differences."""
    expectations = {
        "android_world": (81, 82, "AndroidWorld_72"),
        "appagent": (45, 45, None),
    }
    for package_name, (task_count, legacy_count, duplicate_id) in expectations.items():
        root = BUILTIN_ROOT / package_name
        result = compile_benchmark_package(
            root,
            validation_level=BenchmarkValidationLevel.RESOURCES,
        )
        assert result.is_success, [item.to_safe_dict() for item in result.diagnostics]
        assert result.plan is not None
        assert len(result.plan.tasks) == task_count
        report = json.loads(
            (root / "migration-report.json").read_text(encoding="utf-8")
        )
        assert report["baseline"]["entries"] == task_count
        assert report["legacy"]["entries"] == legacy_count
        assert report["removed_non_duplicate_task_ids"] == []
        assert report["execution_verified"] is False
        duplicate_ids = {
            item["task_id"] for item in report["legacy"]["duplicates"]
        }
        if duplicate_id is None:
            assert duplicate_ids == set()
        else:
            assert duplicate_ids == {duplicate_id}
