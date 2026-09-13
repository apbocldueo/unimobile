"""Benchmark-owned CLI parsers and side-effect-free authoring commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Mapping, TextIO

from .authoring import (
    TEMPLATE_NAMES,
    declaration_fixture_set,
    dry_run_benchmark,
    run_benchmark_contract_tests,
    scaffold_benchmark_package,
)
from .compiler import BenchmarkValidationLevel, compile_benchmark_package
from .reporting import (
    load_experiment_report,
    load_run_report,
    safe_export,
    verify_trajectory_bundle,
)
from .reporting.writer import load_json_document

AUTHORING_COMMANDS = frozenset(
    {"init", "dry-run", "contract-test", "report", "trajectory"}
)


def add_authoring_subcommands(
    subcommands: argparse._SubParsersAction[argparse.ArgumentParser],
) -> None:
    """Attach Benchmark authoring and artifact-inspection parsers.

    Args:
        subcommands (argparse._SubParsersAction[argparse.ArgumentParser]):
            Existing ``zhixing benchmark`` parser collection.

    Raises:
        None.

    Returns:
        None: Mutates the supplied parser collection.
    """
    init = subcommands.add_parser(
        "init",
        help="create a small valid Benchmark Package scaffold",
    )
    init.add_argument("destination", type=Path)
    init.add_argument("--name", required=True)
    init.add_argument("--publisher", default="local")
    init.add_argument("--version", default="0.1.0")
    init.add_argument("--template", choices=TEMPLATE_NAMES, default="minimal")
    init.add_argument("--force", action="store_true")
    init.add_argument("--json", action="store_true")

    dry_run = subcommands.add_parser(
        "dry-run",
        help="compile definitions and print a deterministic schedule only",
    )
    dry_run.add_argument("target", type=Path)
    dry_run.add_argument("--split")
    dry_run.add_argument("--task", action="append", dest="task_ids", default=[])
    dry_run.add_argument(
        "--agent",
        action="append",
        dest="authoring_agents",
        default=[],
        metavar="NAME=PATH",
    )
    dry_run.add_argument("--json", action="store_true")

    contract_test = subcommands.add_parser(
        "contract-test",
        help="run explicit fake-fixture Package contract checks",
    )
    contract_test.add_argument("target", type=Path)
    contract_test.add_argument("--split")
    contract_test.add_argument("--seed", type=int, default=0)
    contract_test.add_argument("--json", action="store_true")

    report = subcommands.add_parser(
        "report",
        help="inspect a versioned Benchmark report without runtime access",
    )
    report.add_argument("path", type=Path)
    report.add_argument("--json", action="store_true")

    trajectory = subcommands.add_parser(
        "trajectory",
        help="inspect a JSONL trajectory or verify a trajectory bundle",
    )
    trajectory.add_argument("path", type=Path)
    trajectory.add_argument("--json", action="store_true")


def _parse_named_paths(values: list[str]) -> dict[str, Path]:
    """Parse unique ``NAME=PATH`` definition selections.

    Args:
        values (list[str]): Raw repeated CLI values.

    Raises:
        ValueError: A value is malformed or a name is duplicated.

    Returns:
        dict[str, Path]: Stable named local paths.
    """
    result: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise ValueError("--agent must use NAME=PATH")
        name, raw_path = (item.strip() for item in value.split("=", 1))
        if not name or not raw_path or name in result:
            raise ValueError("Agent names and paths must be non-blank and unique")
        result[name] = Path(raw_path)
    return result


def _read_trajectory(path: Path) -> dict[str, Any]:
    """Read and summarize a safe JSONL Benchmark trajectory.

    Args:
        path (Path): JSONL trajectory path.

    Raises:
        ValueError: A line is not a JSON object or uses an unsupported schema.
        OSError: The file cannot be read.

    Returns:
        dict[str, Any]: Safe phase and record summary.
    """
    records: list[Mapping[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, Mapping):
            raise ValueError("trajectory records must be JSON objects")
        if value.get("schema_version") != "1.0":
            raise ValueError("unsupported Benchmark trajectory schema")
        records.append(value)
    return safe_export(
        {
            "ok": True,
            "kind": "benchmark_trajectory",
            "record_count": len(records),
            "phases": [str(item.get("phase", "")) for item in records],
            "task_run_ids": sorted(
                {
                    str(item.get("task_run_id", ""))
                    for item in records
                    if item.get("task_run_id")
                }
            ),
        }
    )


def _load_report(path: Path) -> dict[str, Any]:
    """Load one supported report through its typed clean-process loader.

    Args:
        path (Path): Versioned report path.

    Raises:
        ValueError: The report kind or version is unsupported.
        OSError: The file cannot be read.

    Returns:
        dict[str, Any]: Safe report mapping.
    """
    document = load_json_document(path)
    kind = document.get("kind")
    if kind == "benchmark_run_report":
        return load_run_report(path).to_safe_dict()
    if kind == "benchmark_experiment_report":
        return load_experiment_report(path).to_safe_dict()
    raise ValueError("document is not a supported Benchmark report")


def _write_payload(
    payload: Mapping[str, Any],
    *,
    as_json: bool,
    stdout: TextIO,
) -> None:
    """Write stable JSON or compact key/value Benchmark output.

    Args:
        payload (Mapping[str, Any]): Safe output mapping.
        as_json (bool): Whether JSON output was selected.
        stdout (TextIO): Destination stream.

    Raises:
        None.

    Returns:
        None.
    """
    safe = safe_export(payload)
    if as_json:
        print(
            json.dumps(safe, ensure_ascii=False, indent=2, sort_keys=True),
            file=stdout,
        )
        return
    for key, value in safe.items():
        rendered = (
            json.dumps(value, ensure_ascii=False, sort_keys=True)
            if isinstance(value, (dict, list))
            else value
        )
        print(f"{key}: {rendered}", file=stdout)


def handle_authoring_command(
    args: argparse.Namespace,
    *,
    stdout: TextIO,
    stderr: TextIO,
) -> int:
    """Execute one Benchmark authoring or artifact-inspection command.

    Args:
        args (argparse.Namespace): Parsed Benchmark command.
        stdout (TextIO): Safe result stream.
        stderr (TextIO): Human-readable error stream.

    Raises:
        None: Input and validation failures become exit code two.

    Returns:
        int: Zero on success, two on definition/input failure, or three when a
        contract test completes with failed checks.
    """
    try:
        if args.benchmark_command == "init":
            scaffold_benchmark_package(
                args.destination,
                name=args.name,
                publisher=args.publisher,
                version=args.version,
                template=args.template,
                force=args.force,
            )
            payload: Mapping[str, Any] = {
                "ok": True,
                "template": args.template,
                "package": f"{args.publisher}/{args.name}@{args.version}",
                "device_accessed": False,
            }
        elif args.benchmark_command == "dry-run":
            report = dry_run_benchmark(
                args.target,
                agent_paths=_parse_named_paths(args.authoring_agents),
                split=args.split,
                task_ids=tuple(args.task_ids),
            )
            payload = report.to_safe_dict()
            if not report.ok:
                _write_payload(payload, as_json=args.json, stdout=stdout)
                return 2
        elif args.benchmark_command == "contract-test":
            compiled = compile_benchmark_package(
                args.target,
                split=args.split,
                validation_level=BenchmarkValidationLevel.RESOURCES,
            )
            if compiled.plan is None:
                payload = {
                    "ok": False,
                    "diagnostics": [
                        item.to_safe_dict() for item in compiled.diagnostics
                    ],
                }
                _write_payload(payload, as_json=args.json, stdout=stdout)
                return 2
            report = run_benchmark_contract_tests(
                compiled.plan,
                declaration_fixture_set(compiled.plan),
                seed=args.seed,
            )
            payload = report.to_safe_dict()
            if not report.is_success:
                _write_payload(payload, as_json=args.json, stdout=stdout)
                return 3
        elif args.benchmark_command == "report":
            payload = _load_report(args.path)
        else:
            if args.path.suffix.lower() == ".zip":
                payload = {
                    "ok": verify_trajectory_bundle(args.path),
                    "kind": "benchmark_trajectory_bundle",
                }
                if not payload["ok"]:
                    _write_payload(payload, as_json=args.json, stdout=stdout)
                    return 2
            else:
                payload = _read_trajectory(args.path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        payload = {
            "ok": False,
            "error": {
                "code": "benchmark.authoring.invalid",
                "message": (
                    "Benchmark authoring or inspection input is invalid "
                    f"({type(error).__name__})."
                ),
            },
        }
        _write_payload(payload, as_json=args.json, stdout=stdout)
        if not args.json:
            print("zhixing: benchmark.authoring.invalid", file=stderr)
        return 2
    _write_payload(payload, as_json=args.json, stdout=stdout)
    return 0


__all__ = [
    "AUTHORING_COMMANDS",
    "add_authoring_subcommands",
    "handle_authoring_command",
]
