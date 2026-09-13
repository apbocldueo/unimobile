"""Side-effect-free compilation from Benchmark JSON or Package to BenchmarkPlan."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable

from pydantic import ValidationError

from zhixing.config.contracts import (
    BenchmarkSuite,
    ContractValidationError,
    load_benchmark_json,
)

from ..diagnostics import (
    BenchmarkDefinitionError,
    BenchmarkDiagnostic,
    BenchmarkDiagnosticSeverity,
    sorted_diagnostics,
)
from ..loaders import load_manifest, load_package_suites, load_protocol
from ..models import (
    BenchmarkPackage,
    BenchmarkPlan,
    ExperimentProtocol,
    GroundTruthBinding,
    ResourceRef,
)
from ..resources import (
    collect_logical_uris,
    resolve_package_path,
    validate_host_resource_fields,
    validate_logical_references,
    validate_resources,
)
from .references import collect_task_plugin_ids


class BenchmarkValidationLevel(str, Enum):
    """Definition-layer validation depth."""

    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    RESOURCES = "resources"
    FULL = "full"


@dataclass(frozen=True)
class BenchmarkCompilationResult:
    """Plan, optional Protocol, and all safe compilation diagnostics."""

    plan: BenchmarkPlan | None
    diagnostics: tuple[BenchmarkDiagnostic, ...] = ()
    protocol: ExperimentProtocol | None = None

    @property
    def is_success(self) -> bool:
        """Report whether compilation produced a Plan without errors.

        Returns:
            bool: Compilation success state.
        """
        return self.plan is not None and not any(
            item.severity is BenchmarkDiagnosticSeverity.ERROR
            for item in self.diagnostics
        )

    def to_safe_dict(self) -> dict[str, Any]:
        """Serialize a bounded compilation result.

        Returns:
            dict[str, Any]: JSON-compatible result without source paths.
        """
        return {
            "is_success": self.is_success,
            "plan": (
                self.plan.model_dump(mode="json", exclude_none=True)
                if self.plan is not None
                else None
            ),
            "plan_identity": (
                self.plan.canonical_hash() if self.plan is not None else None
            ),
            "protocol": (
                self.protocol.model_dump(mode="json", exclude_none=True)
                if self.protocol is not None
                else None
            ),
            "protocol_identity": (
                self.protocol.canonical_hash()
                if self.protocol is not None
                else None
            ),
            "diagnostics": [item.to_safe_dict() for item in self.diagnostics],
        }


def _contract_error_diagnostics(
    error: Exception,
    *,
    source: str,
) -> tuple[BenchmarkDiagnostic, ...]:
    """Convert known contract failures into safe Benchmark diagnostics.

    Args:
        error (Exception): Existing config or Package validation failure.
        source (str): Safe source label.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Sanitized diagnostics.
    """
    if isinstance(error, BenchmarkDefinitionError):
        return error.diagnostics
    if isinstance(error, ContractValidationError):
        return sorted_diagnostics(
            [
                BenchmarkDiagnostic(
                    code=str(issue.code),
                    message=str(issue.message)[:300],
                    source=source,
                    path=tuple(issue.path),
                )
                for issue in error.issues
            ]
        )
    if isinstance(error, ValidationError):
        return sorted_diagnostics(
            [
                BenchmarkDiagnostic(
                    code="benchmark.plan.invalid",
                    message=str(item["msg"])[:300],
                    source=source,
                    path=tuple(item["loc"]),
                )
                for item in error.errors(include_url=False, include_input=False)
            ]
        )
    return (
        BenchmarkDiagnostic(
            code="benchmark.definition.invalid",
            message="Benchmark definition could not be compiled.",
            source=source,
            path=(type(error).__name__,),
        ),
    )


def compile_benchmark_suite(
    suite_or_path: BenchmarkSuite | str | Path,
) -> BenchmarkCompilationResult:
    """Compile existing standalone V1 JSON into a pure BenchmarkPlan.

    Args:
        suite_or_path (BenchmarkSuite | str | Path): Parsed suite or JSON path.

    Raises:
        None: Definition failures are returned as diagnostics.

    Returns:
        BenchmarkCompilationResult: Side-effect-free compilation result.
    """
    try:
        suite = (
            suite_or_path
            if isinstance(suite_or_path, BenchmarkSuite)
            else load_benchmark_json(Path(suite_or_path))
        )
        plan = BenchmarkPlan(
            split="default",
            tasks=tuple(sorted(suite.root, key=lambda item: item.id)),
        )
    except Exception as error:
        return BenchmarkCompilationResult(
            plan=None,
            diagnostics=_contract_error_diagnostics(error, source="standalone-json"),
        )
    return BenchmarkCompilationResult(plan=plan)


def _ground_truth_diagnostics(
    package: BenchmarkPackage,
) -> tuple[BenchmarkDiagnostic, ...]:
    """Validate task-scoped ground truth keys and logical references.

    Args:
        package (BenchmarkPackage): Loaded semantic Package.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Missing task or resource references.
    """
    all_task_ids = {
        task.id for suite in package.suites.values() for task in suite.root
    }
    resources = {
        resource.id: resource for resource in package.manifest.resources
    }
    diagnostics: list[BenchmarkDiagnostic] = []
    for task_id, binding in package.manifest.ground_truth.items():
        if task_id not in all_task_ids:
            diagnostics.append(
                BenchmarkDiagnostic(
                    code="benchmark.ground_truth.task_missing",
                    message="Ground truth is bound to an unknown task ID.",
                    path=("ground_truth", task_id),
                    task_id=task_id,
                )
            )
        if binding.ref is not None:
            logical_id = binding.ref.removeprefix("groundtruth://")
            resource = resources.get(logical_id)
            if resource is None:
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.ground_truth.reference_missing",
                        message="Ground truth references an undeclared resource.",
                        path=("ground_truth", task_id, "ref"),
                        task_id=task_id,
                    )
                )
            elif resource.kind.value != "ground_truth":
                diagnostics.append(
                    BenchmarkDiagnostic(
                        code="benchmark.ground_truth.kind_mismatch",
                        message="Ground truth URI must reference a ground_truth resource.",
                        path=("ground_truth", task_id, "ref"),
                        task_id=task_id,
                    )
                )
    return tuple(diagnostics)


def _declared_plugin_diagnostics(
    tasks: Iterable[dict[str, Any]],
    declared_plugins: set[str],
    *,
    known_plugins: set[str] | None,
) -> tuple[BenchmarkDiagnostic, ...]:
    """Check declared Package plugin references without importing code.

    Args:
        tasks (Iterable[dict[str, Any]]): Canonical task mappings.
        declared_plugins (set[str]): Manifest plugin logical IDs.
        known_plugins (set[str] | None): Optional metadata-only available IDs.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Non-executing reference diagnostics.
    """
    diagnostics: list[BenchmarkDiagnostic] = []
    referenced_plugins = collect_task_plugin_ids(tasks)
    for plugin_id in sorted(referenced_plugins - declared_plugins):
        diagnostics.append(
            BenchmarkDiagnostic(
                code="benchmark.plugin.undeclared",
                message="Task references a plugin absent from the Package manifest.",
                path=("plugins", plugin_id),
            )
        )
    if known_plugins is None:
        return tuple(diagnostics)
    for plugin_id in sorted(declared_plugins - known_plugins):
        diagnostics.append(
            BenchmarkDiagnostic(
                code="benchmark.plugin.unavailable",
                message="Declared Benchmark plugin is not present in the supplied metadata catalog.",
                path=("plugins", plugin_id),
            )
        )
    return tuple(diagnostics)


def _app_reference_diagnostics(
    tasks: Iterable[dict[str, Any]],
    declared_apps: set[str],
) -> tuple[BenchmarkDiagnostic, ...]:
    """Check task App IDs against the Package manifest.

    Args:
        tasks (Iterable[dict[str, Any]]): Canonical task mappings.
        declared_apps (set[str]): Manifest App logical IDs.

    Raises:
        None.

    Returns:
        tuple[BenchmarkDiagnostic, ...]: Undeclared App references.
    """
    diagnostics: list[BenchmarkDiagnostic] = []
    for index, task in enumerate(tasks):
        app = task.get("app")
        if isinstance(app, str) and app not in declared_apps:
            diagnostics.append(
                BenchmarkDiagnostic(
                    code="benchmark.app.undeclared",
                    message="Task references an App absent from the Package manifest.",
                    path=("tasks", index, "app"),
                    task_id=str(task.get("id", "")) or None,
                )
            )
    return tuple(diagnostics)


def _selected_resource_closure(
    tasks: tuple[dict[str, Any], ...],
    ground_truth: dict[str, GroundTruthBinding],
    resources: tuple[ResourceRef, ...],
) -> tuple[ResourceRef, ...]:
    """Select only resources referenced by one compiled split.

    Args:
        tasks (tuple[dict[str, Any], ...]): Selected task mappings.
        ground_truth (dict[str, GroundTruthBinding]): Package ground truth.
        resources (tuple[ResourceRef, ...]): All declared resources.

    Raises:
        None.

    Returns:
        tuple[ResourceRef, ...]: Stable referenced resource closure.
    """
    used: set[str] = set()
    for task in tasks:
        used.update(logical_id for _, logical_id, _ in collect_logical_uris(task))
        binding = ground_truth.get(str(task["id"]))
        if binding is not None and binding.ref is not None:
            used.add(binding.ref.removeprefix("groundtruth://"))
    return tuple(sorted((item for item in resources if item.id in used), key=lambda item: item.id))


def compile_benchmark_package(
    package_root: str | Path,
    *,
    split: str | None = None,
    validation_level: BenchmarkValidationLevel = BenchmarkValidationLevel.SEMANTIC,
    known_plugins: set[str] | None = None,
) -> BenchmarkCompilationResult:
    """Compile one explicit Benchmark Package without executing task logic.

    Args:
        package_root (str | Path): Directory containing ``benchmark.yaml``.
        split (str | None): Selected split or the first stable split.
        validation_level (BenchmarkValidationLevel): Requested validation depth.
        known_plugins (set[str] | None): Optional metadata-only plugin IDs.

    Raises:
        None: All definition failures become structured diagnostics.

    Returns:
        BenchmarkCompilationResult: Pure Plan and optional default Protocol.
    """
    root = Path(package_root)
    try:
        manifest = load_manifest(root)
        suites = load_package_suites(root, manifest)
        package = BenchmarkPackage(manifest=manifest, suites=suites)
    except Exception as error:
        return BenchmarkCompilationResult(
            plan=None,
            diagnostics=_contract_error_diagnostics(error, source="benchmark-package"),
        )

    selected_split = split or sorted(package.suites)[0]
    diagnostics: list[BenchmarkDiagnostic] = list(_ground_truth_diagnostics(package))
    if selected_split not in package.suites:
        diagnostics.append(
            BenchmarkDiagnostic(
                code="benchmark.split.not_found",
                message="Requested Benchmark split does not exist.",
                path=("split",),
            )
        )
        return BenchmarkCompilationResult(
            plan=None,
            diagnostics=sorted_diagnostics(diagnostics),
        )

    suite = package.suites[selected_split]
    task_mappings = tuple(task.canonical_dict() for task in suite.root)
    diagnostics.extend(
        validate_logical_references(
            list(task_mappings),
            package.manifest.resources,
        )
    )
    diagnostics.extend(validate_host_resource_fields(list(task_mappings)))
    diagnostics.extend(
        _app_reference_diagnostics(
            task_mappings,
            {item.id for item in package.manifest.apps},
        )
    )
    diagnostics.extend(
        _declared_plugin_diagnostics(
            task_mappings,
            {item.id for item in package.manifest.plugins},
            known_plugins=(
                known_plugins
                if validation_level is BenchmarkValidationLevel.FULL
                else None
            ),
        )
    )
    selected_ground_truth = {
        task.id: package.manifest.ground_truth[task.id]
        for task in suite.root
        if task.id in package.manifest.ground_truth
    }
    selected_resources = _selected_resource_closure(
        task_mappings,
        selected_ground_truth,
        package.manifest.resources,
    )
    if validation_level in {
        BenchmarkValidationLevel.RESOURCES,
        BenchmarkValidationLevel.FULL,
    }:
        diagnostics.extend(
            validate_resources(
                root,
                package.manifest.resources,
                verify_digests=True,
            )
        )
    protocol: ExperimentProtocol | None = None
    if package.manifest.default_protocol is not None:
        try:
            protocol_path = resolve_package_path(
                root,
                package.manifest.default_protocol,
            )
            protocol = load_protocol(protocol_path)
        except Exception as error:
            diagnostics.extend(
                _contract_error_diagnostics(error, source="default-protocol")
            )

    if any(
        item.severity is BenchmarkDiagnosticSeverity.ERROR for item in diagnostics
    ):
        return BenchmarkCompilationResult(
            plan=None,
            diagnostics=sorted_diagnostics(diagnostics),
            protocol=protocol,
        )

    try:
        plan = BenchmarkPlan(
            package_identity=package.manifest.identity.identifier,
            package_content_identity=package.content_identity,
            split=selected_split,
            tasks=tuple(sorted(suite.root, key=lambda item: item.id)),
            resources=selected_resources,
            ground_truth=selected_ground_truth,
            apps=package.manifest.apps,
            plugins=package.manifest.plugins,
        )
    except ValidationError as error:
        return BenchmarkCompilationResult(
            plan=None,
            diagnostics=_contract_error_diagnostics(error, source="benchmark-plan"),
            protocol=protocol,
        )
    return BenchmarkCompilationResult(
        plan=plan,
        diagnostics=sorted_diagnostics(diagnostics),
        protocol=protocol,
    )
