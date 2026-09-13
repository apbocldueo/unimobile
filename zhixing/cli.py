"""Installed command-line entry point for graph-native ZhiXing agents."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence, TextIO

import yaml

from zhixing.components import (
    ComponentBundle,
    RunStatus,
    check_component_bundle,
)
from zhixing.catalog import (
    ComponentCatalogError,
    ComponentDiscoveryError,
    ExternalComponentError,
    enumerate_component_plugins,
    load_component_plugins,
)
from zhixing.graph import GraphComponentRef
from zhixing.runtime.errors import GraphRuntimeError
from zhixing.sdk import AgentRunConfig, load_agent
from zhixing.benchmark import (
    BenchmarkCatalog,
    BenchmarkExperimentRuntime,
    BenchmarkDefinitionError,
    BenchmarkDiagnostic,
    BenchmarkRunConfig,
    BenchmarkValidationLevel,
    PackageBenchmarkResourceProvider,
    compile_benchmark_package,
    discover_benchmark_candidates,
    load_protocol,
    safe_export,
)
from zhixing.benchmark.cli import (
    AUTHORING_COMMANDS,
    add_authoring_subcommands,
    handle_authoring_command,
)


def build_parser() -> argparse.ArgumentParser:
    """Create the stable installed command parser.

    Args:
        None.

    Raises:
        None.

    Returns:
        argparse.ArgumentParser: Parser containing the graph-native run command.
    """
    parser = argparse.ArgumentParser(
        prog="zhixing",
        description="Build and run graph-native ZhiXing Mobile Agents.",
    )
    subcommands = parser.add_subparsers(dest="command", required=True)
    run = subcommands.add_parser("run", help="run one graph-native Android agent")
    run.add_argument("--agent", required=True, type=Path, help="AgentGraph YAML path")
    run.add_argument("--instruction", help="task text; omit to read one task from stdin")
    run.add_argument("--serial", help="exact adb serial; required when multiple devices exist")
    run.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("temp/runs"),
        help="host directory for isolated run artifacts",
    )
    run.add_argument("--max-steps", type=int, default=15)
    run.add_argument(
        "--secrets",
        type=Path,
        help="YAML mapping from SecretRef names to runtime values",
    )
    run.add_argument(
        "--include-ui-tree",
        action="store_true",
        help="capture UI hierarchy with every screenshot",
    )
    run.add_argument("--json", action="store_true", help="print the full safe RunResult")
    run.add_argument(
        "--no-external-plugins",
        action="store_true",
        help="disable installed external component discovery",
    )
    run.add_argument(
        "--plugin-provider",
        action="append",
        dest="plugin_allowlist",
        help="allow only this external provider ID; repeat as needed",
    )
    run.add_argument(
        "--disable-plugin-provider",
        action="append",
        dest="plugin_denylist",
        default=[],
        help="skip this external provider ID; repeat as needed",
    )
    components = subcommands.add_parser(
        "components",
        help="inspect installed external component providers",
    )
    component_commands = components.add_subparsers(
        dest="components_command",
        required=True,
    )
    component_list = component_commands.add_parser(
        "list",
        help="list provider metadata without loading by default",
    )
    component_list.add_argument(
        "--load",
        action="store_true",
        help="load selected providers and include safe component metadata",
    )
    component_list.add_argument("--json", action="store_true", help="print safe JSON")
    component_list.add_argument(
        "--plugin-provider",
        action="append",
        dest="plugin_allowlist",
        help="allow only this provider ID; repeat as needed",
    )
    component_list.add_argument(
        "--disable-plugin-provider",
        action="append",
        dest="plugin_denylist",
        default=[],
        help="skip this provider ID; repeat as needed",
    )
    component_inspect = component_commands.add_parser(
        "inspect",
        help="load providers and inspect one installed component",
    )
    component_inspect.add_argument(
        "component",
        help="component reference in namespace:name[@version] form",
    )
    _add_component_policy_arguments(component_inspect)
    component_doctor = component_commands.add_parser(
        "doctor",
        help="load providers and run safe bundle health checks",
    )
    _add_component_policy_arguments(component_doctor)
    benchmark = subcommands.add_parser(
        "benchmark",
        help="inspect and validate Benchmark Packages without running devices",
    )
    benchmark_commands = benchmark.add_subparsers(
        dest="benchmark_command",
        required=True,
    )
    benchmark_list = benchmark_commands.add_parser(
        "list",
        help="list explicit and installed Benchmark Package metadata",
    )
    _add_benchmark_source_arguments(benchmark_list)
    benchmark_info = benchmark_commands.add_parser(
        "info",
        help="show one Benchmark Package definition summary",
    )
    benchmark_info.add_argument("target", help="Package identity or explicit directory")
    _add_benchmark_source_arguments(benchmark_info)
    benchmark_validate = benchmark_commands.add_parser(
        "validate",
        help="validate one Benchmark Package without running tasks",
    )
    benchmark_validate.add_argument(
        "target",
        help="Package identity or explicit directory",
    )
    benchmark_validate.add_argument("--split", help="specific task split")
    _add_benchmark_source_arguments(benchmark_validate)
    benchmark_run = benchmark_commands.add_parser(
        "run",
        help="execute a BenchmarkPlan with graph-native Agents",
    )
    benchmark_run.add_argument(
        "target",
        help="Package identity or explicit directory",
    )
    benchmark_run.add_argument("--split", help="specific task split")
    benchmark_run.add_argument(
        "--task",
        action="append",
        dest="task_ids",
        default=[],
        help="run only this task ID; repeat as needed",
    )
    benchmark_run.add_argument(
        "--agent",
        action="append",
        required=True,
        dest="benchmark_agents",
        metavar="NAME=PATH",
        help="named AgentGraph YAML in NAME=PATH form; repeat as needed",
    )
    benchmark_run.add_argument(
        "--protocol",
        type=Path,
        help="ExperimentProtocol YAML; defaults to the Package protocol",
    )
    benchmark_run.add_argument("--serial", help="exact Android serial")
    benchmark_run.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("temp/benchmarks"),
        help="host root for isolated Benchmark artifacts",
    )
    benchmark_run.add_argument(
        "--secrets",
        type=Path,
        help="YAML mapping used by all selected AgentGraph definitions",
    )
    _add_benchmark_source_arguments(benchmark_run)
    add_authoring_subcommands(benchmark_commands)
    return parser


def _add_benchmark_source_arguments(parser: argparse.ArgumentParser) -> None:
    """Add explicit, metadata-only Benchmark discovery arguments.

    Args:
        parser (argparse.ArgumentParser): Benchmark subcommand parser.

    Raises:
        None.

    Returns:
        None: Mutates the parser with source and output flags.
    """
    parser.add_argument(
        "--package",
        action="append",
        dest="package_dirs",
        default=[],
        type=Path,
        help="explicit Benchmark Package directory; repeat as needed",
    )
    parser.add_argument(
        "--catalog-root",
        action="append",
        dest="catalog_roots",
        default=[],
        type=Path,
        help="directory whose immediate children are Benchmark Packages",
    )
    parser.add_argument(
        "--no-installed",
        action="store_true",
        help="skip installed zhixing.benchmarks metadata enumeration",
    )
    parser.add_argument("--json", action="store_true", help="print stable safe JSON")


def _add_component_policy_arguments(parser: argparse.ArgumentParser) -> None:
    """Add shared provider selection and output flags to a component command.

    Args:
        parser (argparse.ArgumentParser): Component subcommand parser.

    Raises:
        None.

    Returns:
        None: Mutates the parser with stable public flags.
    """
    parser.add_argument("--json", action="store_true", help="print safe JSON")
    parser.add_argument(
        "--plugin-provider",
        action="append",
        dest="plugin_allowlist",
        help="allow only this provider ID; repeat as needed",
    )
    parser.add_argument(
        "--disable-plugin-provider",
        action="append",
        dest="plugin_denylist",
        default=[],
        help="skip this provider ID; repeat as needed",
    )


def _load_secrets(path: Path | None) -> dict[str, Any]:
    """Load a runtime-only secret mapping without logging values.

    Args:
        path (Path | None): YAML mapping path or None.

    Raises:
        ValueError: The file cannot be read or is not a string-keyed mapping.

    Returns:
        dict[str, Any]: Runtime secret provider.
    """
    if path is None:
        return {}
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"cannot read secrets file ({type(error).__name__})") from error
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError("secrets file must contain a string-keyed YAML mapping")
    return dict(value)


def _read_instruction(value: str | None, stdin: TextIO) -> str:
    """Resolve a non-empty task from an argument or standard input.

    Args:
        value (str | None): Optional non-interactive task.
        stdin (TextIO): Input stream used by interactive mode.

    Raises:
        ValueError: The resolved task is empty.

    Returns:
        str: Trimmed natural-language task.
    """
    instruction = value if value is not None else stdin.readline()
    instruction = instruction.strip()
    if not instruction:
        raise ValueError("instruction must not be empty")
    return instruction


def _safe_summary(
    agent_hash: str,
    result: Any,
    artifact_root: Path,
) -> dict[str, Any]:
    """Build the compact CLI result shared by text and automation users.

    Args:
        agent_hash (str): Canonical AgentGraph identity.
        result (Any): Structured RunResult.
        artifact_root (Path): Host root selected for this run.

    Raises:
        None.

    Returns:
        dict[str, Any]: Stable non-secret execution summary.
    """
    namespace = str(result.artifact_namespace or "")
    manifest = str(artifact_root / namespace / "manifest.json") if namespace else ""
    return {
        "status": result.status.value,
        "canonical_hash": agent_hash,
        "run_id": result.run_id,
        "kernel_status": result.kernel_status,
        "steps": result.step_count,
        "artifact_namespace": namespace,
        "manifest": manifest,
        "error": result.error,
    }


def _run_command(
    args: argparse.Namespace,
    *,
    stdin: TextIO,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Execute one CLI run exclusively through the public SDK.

    Args:
        args (argparse.Namespace): Parsed run arguments.
        stdin (TextIO): Task input stream.
        stdout (TextIO): Result output stream.
        stderr (TextIO): Error stream.

    Raises:
        None: Configuration and runtime failures become stable exit codes.

    Returns:
        int: Zero for success, two for configuration, three for Agent failure,
        or four for device failure.
    """
    try:
        instruction = _read_instruction(args.instruction, stdin)
        secrets = _load_secrets(args.secrets)
        load_options: dict[str, Any] = {"secrets": secrets}
        if args.no_external_plugins:
            load_options["discover_external"] = False
        if args.plugin_allowlist is not None:
            load_options["plugin_allowlist"] = tuple(args.plugin_allowlist)
        if args.plugin_denylist:
            load_options["plugin_denylist"] = tuple(args.plugin_denylist)
        agent = load_agent(args.agent, **load_options)
        result = agent.run(
            instruction,
            AgentRunConfig(
                serial=args.serial,
                artifact_root=args.artifact_root,
                max_steps=args.max_steps,
                include_ui_tree=args.include_ui_tree,
            ),
        )
    except (ValueError, GraphRuntimeError) as error:
        print(f"zhixing: {error}", file=stderr)
        return 2
    if args.json:
        payload = {
            **_safe_summary(agent.canonical_hash, result, args.artifact_root),
            "result": result.to_safe_dict(),
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    else:
        summary = _safe_summary(agent.canonical_hash, result, args.artifact_root)
        for key, value in summary.items():
            print(f"{key}: {value}", file=stdout)
    if result.status is RunStatus.SUCCESS:
        return 0
    if result.status is RunStatus.DEVICE_FAILURE:
        return 4
    return 3


def _components_command(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Inspect provider metadata and optionally load selected bundles.

    Args:
        args (argparse.Namespace): Parsed ``components list`` arguments.
        stdout (TextIO): Safe result output stream.
        stderr (TextIO): Error output stream.

    Returns:
        int: Zero on success or two for discovery/catalog errors.
    """
    try:
        candidates = enumerate_component_plugins()
        if args.load:
            environment = load_component_plugins(
                candidates,
                allowlist=args.plugin_allowlist,
                denylist=args.plugin_denylist,
            )
            payload: dict[str, Any] = environment.to_safe_dict()
        else:
            payload = {
                "mode": "metadata-only",
                "candidates": [item.to_safe_dict() for item in candidates],
            }
    except ValueError as error:
        print(f"zhixing: {error}", file=stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    elif args.load:
        for component in payload["catalog"]["components"]:
            metadata = component["component"]
            print(
                f"{metadata['identifier']} provider={component['provider_id']}",
                file=stdout,
            )
    else:
        for candidate in payload["candidates"]:
            origin = candidate["origin"]
            print(
                f"{candidate['provider_id']} "
                f"distribution={origin['distribution']} version={origin['version']}",
                file=stdout,
            )
    return 0


def _parse_component_reference(value: str) -> GraphComponentRef:
    """Parse one CLI component identity without accepting install sources.

    Args:
        value (str): ``namespace:name`` identity with an optional ``@version``.

    Raises:
        ValueError: The value is a URL, Git source, or malformed identity.

    Returns:
        GraphComponentRef: Safe declarative catalog reference.
    """
    selected = str(value).strip()
    lowered = selected.lower()
    if (
        "://" in selected
        or lowered.startswith(("git+", "http:", "https:", "ssh:"))
        or "/" in selected
    ):
        raise ValueError(
            "component commands inspect installed identities; install the "
            "distribution first"
        )
    identity, separator, version = selected.rpartition("@")
    if not separator:
        identity = selected
        version = ""
    namespace, name_separator, name = identity.partition(":")
    if (
        not name_separator
        or not namespace
        or not name
        or (separator and not version)
    ):
        raise ValueError(
            "component reference must use namespace:name[@version]"
        )
    try:
        return GraphComponentRef(
            namespace=namespace,
            name=name,
            version=version or None,
        )
    except Exception as error:
        raise ValueError(
            "component reference must use namespace:name[@version]"
        ) from error


def _load_selected_component_environment(
    args: argparse.Namespace,
) -> Any:
    """Enumerate and explicitly load providers selected by CLI policy.

    Args:
        args (argparse.Namespace): Parsed inspect or doctor arguments.

    Raises:
        ComponentDiscoveryError: An explicitly requested provider is absent.
        ExternalComponentError: Discovery or Catalog construction fails.

    Returns:
        Any: Immutable ``DiscoveredComponentEnvironment``.
    """
    candidates = enumerate_component_plugins()
    candidate_ids = {candidate.provider_id for candidate in candidates}
    requested = set(args.plugin_allowlist or ())
    missing = sorted(requested - candidate_ids)
    if missing:
        raise ComponentDiscoveryError(
            "plugin.provider_not_installed",
            "One or more selected component providers are not installed.",
            details={"provider_ids": missing},
        )
    return load_component_plugins(
        candidates,
        allowlist=args.plugin_allowlist,
        denylist=args.plugin_denylist,
    )


def _safe_cli_error(error: Exception, *, code: str) -> dict[str, Any]:
    """Convert a CLI failure into bounded machine-readable fields.

    Args:
        error (Exception): Known framework or input error.
        code (str): Fallback stable error code.

    Raises:
        None.

    Returns:
        dict[str, Any]: Safe error payload without arbitrary exception text.
    """
    if isinstance(error, ExternalComponentError):
        return error.to_safe_dict()
    return {
        "code": code,
        "message": "The component command input is invalid.",
        "details": {"error_type": type(error).__name__},
    }


def _write_component_error(
    error: Exception,
    *,
    code: str,
    as_json: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    """Write one safe component-command error in text or JSON form.

    Args:
        error (Exception): Known framework or input error.
        code (str): Fallback stable error code.
        as_json (bool): Whether machine-readable output was requested.
        stdout (TextIO): JSON output stream.
        stderr (TextIO): Human-readable error stream.

    Raises:
        None.

    Returns:
        None: Writes exactly one bounded diagnostic.
    """
    payload = _safe_cli_error(error, code=code)
    if as_json:
        print(
            json.dumps(
                {"ok": False, "error": payload},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=stdout,
        )
        return
    print(
        f"zhixing: {payload['code']}: {payload['message']}",
        file=stderr,
    )


def _components_inspect_command(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Inspect one installed external component through the real Catalog.

    Args:
        args (argparse.Namespace): Parsed ``components inspect`` arguments.
        stdout (TextIO): Safe result output stream.
        stderr (TextIO): Human-readable error stream.

    Raises:
        None: Input, discovery, and resolution failures become exit code two.

    Returns:
        int: Zero on success or two for input/discovery/catalog errors.
    """
    try:
        reference = _parse_component_reference(args.component)
        environment = _load_selected_component_environment(args)
        try:
            entry = environment.catalog.resolve(reference)
        except ComponentCatalogError as error:
            if environment.report.failures:
                raise ComponentDiscoveryError(
                    "plugin.component_provider_failed",
                    "The component is unavailable and selected providers failed.",
                    details={
                        "catalog_error": error.code,
                        "provider_failures": [
                            failure.to_safe_dict()
                            for failure in environment.report.failures
                        ],
                    },
                ) from error
            raise
        payload = {"ok": True, "component": entry.to_safe_dict()}
    except (ValueError, ExternalComponentError) as error:
        _write_component_error(
            error,
            code="component.reference_invalid",
            as_json=args.json,
            stdout=stdout,
            stderr=stderr,
        )
        return 2
    if args.json:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            file=stdout,
        )
        return 0
    component = payload["component"]["component"]
    origin = payload["component"]["origin"] or {}
    print(f"component: {component['identifier']}", file=stdout)
    print(f"provider: {payload['component']['provider_id']}", file=stdout)
    print(f"category: {component['category']}", file=stdout)
    print(f"role: {component['role'] or '-'}", file=stdout)
    print(
        f"contract: {component['contract']['id']}@"
        f"{component['contract']['version']}",
        file=stdout,
    )
    print(
        f"adapter: {component['contract']['adapter']} "
        f"side_effect={component['contract']['side_effect']} "
        f"idempotent={component['contract']['idempotent']}",
        file=stdout,
    )
    for port in component["contract"]["ports"]:
        print(
            f"port {port['direction']} {port['id']}: "
            f"{','.join(port['data_types'])} "
            f"required={port['required']} "
            f"cardinality={port['cardinality']}",
            file=stdout,
        )
    print(
        "config_schema: "
        + json.dumps(
            component["config_schema"],
            ensure_ascii=False,
            sort_keys=True,
        ),
        file=stdout,
    )
    if origin:
        print(
            f"origin: {origin['distribution']}@{origin['version']} "
            f"({origin['source_kind']})",
            file=stdout,
        )
    return 0


def _components_doctor_command(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Diagnose installed providers and run default-safe bundle checks.

    Args:
        args (argparse.Namespace): Parsed ``components doctor`` arguments.
        stdout (TextIO): Safe result output stream.
        stderr (TextIO): Human-readable error stream.

    Raises:
        None: Discovery and Catalog errors become exit code two.

    Returns:
        int: Zero when healthy, two for discovery/catalog failure, or three
        when loaded components fail Contract Test Kit checks.
    """
    try:
        environment = _load_selected_component_environment(args)
    except (ValueError, ExternalComponentError) as error:
        _write_component_error(
            error,
            code="plugin.discovery_failed",
            as_json=args.json,
            stdout=stdout,
            stderr=stderr,
        )
        return 2
    by_provider: dict[str, list[Any]] = {}
    for entry in environment.catalog.entries():
        by_provider.setdefault(entry.provider_id, []).append(
            entry.specification
        )
    bundle_results = tuple(
        check_component_bundle(
            ComponentBundle(
                tuple(
                    sorted(
                        specifications,
                        key=lambda item: item.identifier,
                    )
                )
            ),
            provider_id=provider_id,
        )
        for provider_id, specifications in sorted(by_provider.items())
    )
    discovery_failed = bool(environment.report.failures)
    contract_failed = any(not result.passed for result in bundle_results)
    provider_payloads = []
    for result in bundle_results:
        provider_payload = result.to_safe_dict()
        skipped_count = sum(
            len(component.skipped) for component in result.components
        )
        provider_payload["health"] = (
            "contract-failed"
            if not result.passed
            else "structural-only"
            if skipped_count
            else "verified"
        )
        provider_payload["skipped_count"] = skipped_count
        provider_payloads.append(provider_payload)
    payload = {
        "ok": not discovery_failed and not contract_failed,
        "report": environment.report.to_safe_dict(),
        "providers": provider_payloads,
    }
    if args.json:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            file=stdout,
        )
    else:
        for failure in environment.report.failures:
            print(
                f"provider {failure.provider_id}: failed "
                f"stage={failure.stage} code={failure.code}",
                file=stdout,
            )
        for result in bundle_results:
            skipped_count = sum(
                len(component.skipped) for component in result.components
            )
            state = (
                "contract-failed"
                if not result.passed
                else "structural-only"
                if skipped_count
                else "verified"
            )
            print(
                f"provider {result.provider_id}: {state} "
                f"components={len(result.components)} "
                f"skipped={skipped_count}",
                file=stdout,
            )
            for component in result.components:
                if not component.passed:
                    diagnostic = component.diagnostics[0]
                    print(
                        f"  {component.component_id}: failed "
                        f"phase={diagnostic.phase} code={diagnostic.code}",
                        file=stdout,
                    )
                for skipped in component.skipped:
                    print(
                        f"  {component.component_id}: skipped {skipped}",
                        file=stdout,
                    )
        if not environment.report.candidates:
            print("providers: none installed", file=stdout)
    if discovery_failed:
        return 2
    if contract_failed:
        return 3
    return 0


def _benchmark_catalog_from_args(args: argparse.Namespace) -> BenchmarkCatalog:
    """Build an immutable Catalog from only explicitly selected sources.

    Args:
        args (argparse.Namespace): Parsed Benchmark source arguments.

    Raises:
        BenchmarkDefinitionError: An explicit Package or Catalog root is invalid.

    Returns:
        BenchmarkCatalog: Metadata-only immutable Catalog.
    """
    candidates = discover_benchmark_candidates(
        package_dirs=args.package_dirs,
        catalog_roots=args.catalog_roots,
        include_installed=not args.no_installed,
    )
    return BenchmarkCatalog(candidates)


def _benchmark_target_catalog(
    args: argparse.Namespace,
) -> tuple[BenchmarkCatalog, str]:
    """Resolve a target path into an explicit candidate or keep its identity.

    Args:
        args (argparse.Namespace): Parsed info/validate arguments.

    Raises:
        BenchmarkDefinitionError: Explicit target path is invalid.

    Returns:
        tuple[BenchmarkCatalog, str]: Catalog and readable Package identity.
    """
    target_path = Path(args.target)
    package_dirs = list(args.package_dirs)
    if target_path.is_dir():
        package_dirs.append(target_path)
        candidates = discover_benchmark_candidates(
            package_dirs=package_dirs,
            catalog_roots=args.catalog_roots,
            include_installed=not args.no_installed,
        )
        catalog = BenchmarkCatalog(candidates)
        target_root = target_path.resolve()
        matching = [
            item for item in candidates if item.root.resolve() == target_root
        ]
        if len(matching) != 1:
            raise BenchmarkDefinitionError(
                (
                    # The path is explicit, but public diagnostics still avoid
                    # echoing the host absolute path.
                    BenchmarkDiagnostic(
                        code="benchmark.catalog.target_invalid",
                        message="Explicit Benchmark Package target is invalid.",
                        source="target",
                    ),
                )
            )
        return catalog, matching[0].identity
    return _benchmark_catalog_from_args(args), str(args.target)


def _write_benchmark_error(
    error: Exception,
    *,
    as_json: bool,
    stdout: TextIO,
    stderr: TextIO,
) -> None:
    """Write one sanitized Benchmark CLI error.

    Args:
        error (Exception): Definition or input failure.
        as_json (bool): Whether JSON output was requested.
        stdout (TextIO): Machine-readable output stream.
        stderr (TextIO): Human-readable error stream.

    Raises:
        None.

    Returns:
        None: Writes one bounded diagnostic.
    """
    if isinstance(error, BenchmarkDefinitionError):
        payload = error.to_safe_dict()
    else:
        payload = {
            "code": "benchmark.command.invalid",
            "message": "Benchmark command input is invalid.",
            "diagnostics": [],
        }
    if as_json:
        print(
            json.dumps(
                {"ok": False, "error": payload},
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            file=stdout,
        )
        return
    print(f"zhixing: {payload['code']}: {payload['message']}", file=stderr)


def _benchmark_command(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Execute Benchmark metadata, validation, or graph-native run commands.

    Args:
        args (argparse.Namespace): Parsed Benchmark command.
        stdout (TextIO): Safe output stream.
        stderr (TextIO): Error stream.

    Raises:
        None: Definition failures become exit code two.

    Returns:
        int: Zero on success or two for definition validation failure.
    """
    if args.benchmark_command in AUTHORING_COMMANDS:
        return handle_authoring_command(
            args,
            stdout=stdout,
            stderr=stderr,
        )
    try:
        if args.benchmark_command == "list":
            catalog = _benchmark_catalog_from_args(args)
            payload: dict[str, Any] = {
                "ok": True,
                "mode": "metadata-only",
                "benchmarks": [
                    item.to_safe_dict() for item in catalog.candidates()
                ],
            }
        elif args.benchmark_command in {"info", "validate"}:
            catalog, identity = _benchmark_target_catalog(args)
            if args.benchmark_command == "info":
                payload = {"ok": True, "benchmark": catalog.info(identity)}
            else:
                result = catalog.validate(identity, split=args.split)
                payload = result.to_safe_dict()
                payload["ok"] = result.is_success
                if not result.is_success:
                    if args.json:
                        print(
                            json.dumps(
                                payload,
                                ensure_ascii=False,
                                indent=2,
                                sort_keys=True,
                            ),
                            file=stdout,
                        )
                    else:
                        for diagnostic in result.diagnostics:
                            print(
                                f"{diagnostic.severity.value}: "
                                f"{diagnostic.code}",
                                file=stderr,
                            )
                    return 2
        else:
            return _benchmark_run_command(
                args,
                stdout=stdout,
                stderr=stderr,
            )
    except (BenchmarkDefinitionError, ValueError) as error:
        _write_benchmark_error(
            error,
            as_json=args.json,
            stdout=stdout,
            stderr=stderr,
        )
        return 2
    if args.json:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            file=stdout,
        )
        return 0
    if args.benchmark_command == "list":
        for benchmark in payload["benchmarks"]:
            print(
                f"{benchmark['identity']} "
                f"title={benchmark['title']} "
                f"splits={','.join(benchmark['splits'])} "
                f"source={benchmark['source_kind']}",
                file=stdout,
            )
    elif args.benchmark_command == "info":
        benchmark = payload["benchmark"]
        print(f"benchmark: {benchmark['identity']}", file=stdout)
        print(f"content_identity: {benchmark['content_identity']}", file=stdout)
        print(
            "task_counts: "
            + ",".join(
                f"{name}={count}"
                for name, count in sorted(benchmark["task_counts"].items())
            ),
            file=stdout,
        )
        print(f"resources: {len(benchmark['resources'])}", file=stdout)
    else:
        print("valid: true", file=stdout)
        print(f"plan_identity: {payload['plan_identity']}", file=stdout)
        print(f"protocol_identity: {payload['protocol_identity']}", file=stdout)
        print(
            "note: definition-layer validation only; no task was executed",
            file=stdout,
        )
    return 0


def _parse_named_benchmark_agents(
    values: Sequence[str],
    *,
    secrets: Mapping[str, Any],
) -> dict[str, Any]:
    """Load unique named graph-native Agents before any device connection.

    Args:
        values (Sequence[str]): ``NAME=PATH`` selections.
        secrets (Mapping[str, Any]): Shared runtime-only secret provider.

    Raises:
        ValueError: Syntax, names, or duplicate IDs are invalid.
        GraphRuntimeError: Agent compilation or binding preflight fails.

    Returns:
        dict[str, Any]: Named ExecutableAgent mapping.
    """
    agents: dict[str, Any] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--agent must use NAME=PATH")
        name, raw_path = value.split("=", 1)
        name = name.strip()
        raw_path = raw_path.strip()
        if not name or not raw_path or name in agents:
            raise ValueError("Benchmark Agent names and paths must be non-blank and unique")
        agents[name] = load_agent(Path(raw_path), secrets=secrets)
    return agents


def _benchmark_run_command(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Compile and execute one Package through the public Experiment Runtime.

    Args:
        args (argparse.Namespace): Parsed run arguments.
        stdout (TextIO): Safe result stream.
        stderr (TextIO): Error stream.

    Raises:
        None: Failures become stable exit codes.

    Returns:
        int: Zero when all tasks pass, two for definition/binding failures,
        three for completed non-pass suites, or four for runtime/device failure.
    """
    try:
        catalog, identity = _benchmark_target_catalog(args)
        candidate = catalog.resolve(identity)
        compiled = compile_benchmark_package(
            candidate.root,
            split=args.split,
            validation_level=BenchmarkValidationLevel.RESOURCES,
        )
        if compiled.plan is None:
            raise BenchmarkDefinitionError(compiled.diagnostics)
        protocol = (
            load_protocol(args.protocol)
            if args.protocol is not None
            else compiled.protocol
        )
        if protocol is None:
            raise ValueError(
                "Benchmark run requires --protocol or a Package default_protocol"
            )
        secrets = _load_secrets(args.secrets)
        agents = _parse_named_benchmark_agents(
            args.benchmark_agents,
            secrets=secrets,
        )
        # All definitions and Agent bindings are complete before this call can
        # select a device or execute a Benchmark component.
        result = BenchmarkExperimentRuntime().run(
            compiled.plan,
            protocol,
            agents,
            run_config=BenchmarkRunConfig(
                artifact_root=args.artifact_root,
                serial=args.serial,
                task_ids=tuple(args.task_ids),
            ),
            resource_provider=PackageBenchmarkResourceProvider(
                candidate.root,
                compiled.plan,
            ),
        )
    except (BenchmarkDefinitionError, GraphRuntimeError, ValueError) as error:
        _write_benchmark_error(
            error,
            as_json=args.json,
            stdout=stdout,
            stderr=stderr,
        )
        return 2
    except Exception as error:
        payload = {
            "ok": False,
            "error": {
                "code": "benchmark.runtime.failed",
                "message": f"Benchmark runtime failed ({type(error).__name__}).",
            },
        }
        if args.json:
            print(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                file=stdout,
            )
        else:
            print(
                f"zhixing: benchmark.runtime.failed ({type(error).__name__})",
                file=stderr,
            )
        return 4
    payload = {
        "ok": result.is_success,
        "suite": safe_export(result.to_safe_dict()),
    }
    if args.json:
        print(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            file=stdout,
        )
    else:
        print(f"experiment: {result.experiment_id}", file=stdout)
        print(
            "outcomes: "
            + ",".join(
                f"{name}={count}" for name, count in sorted(result.counts.items())
            ),
            file=stdout,
        )
        for item in result.results:
            print(
                f"{item.task_id} agent={item.agent_id} "
                f"repeat={item.repeat} outcome={item.outcome.value} "
                f"artifact={item.artifact_namespace}",
                file=stdout,
            )
        for warning in result.fairness_warnings:
            print(f"warning: {warning}", file=stdout)
    return 0 if result.is_success else 3


def main(
    argv: Sequence[str] | None = None,
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the installed ZhiXing command.

    Args:
        argv (Sequence[str] | None): Optional test argument vector.
        stdin (TextIO | None): Optional input stream.
        stdout (TextIO | None): Optional output stream.
        stderr (TextIO | None): Optional error stream.

    Raises:
        SystemExit: argparse reports malformed command syntax.

    Returns:
        int: Stable process exit code.
    """
    selected_stdin = stdin or sys.stdin
    selected_stdout = stdout or sys.stdout
    selected_stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    if args.command == "run":
        return _run_command(
            args,
            stdin=selected_stdin,
            stdout=selected_stdout,
            stderr=selected_stderr,
        )
    if args.command == "components" and args.components_command == "list":
        return _components_command(
            args,
            stdout=selected_stdout,
            stderr=selected_stderr,
        )
    if args.command == "components" and args.components_command == "inspect":
        return _components_inspect_command(
            args,
            stdout=selected_stdout,
            stderr=selected_stderr,
        )
    if args.command == "components" and args.components_command == "doctor":
        return _components_doctor_command(
            args,
            stdout=selected_stdout,
            stderr=selected_stderr,
        )
    if args.command == "benchmark":
        return _benchmark_command(
            args,
            stdout=selected_stdout,
            stderr=selected_stderr,
        )
    print(f"zhixing: unsupported command {args.command!r}", file=selected_stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
