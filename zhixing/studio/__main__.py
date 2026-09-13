"""Run the Studio service or explicit trusted local Replay import command."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Sequence

from zhixing.utils.utils import setup_logging

from zhixing.studio.httpd import run_httpd
from zhixing.studio.device_profiles import (
    load_android_device_profiles,
    resolve_device_profile_config_path,
)
from zhixing.studio.replay_service import build_default_replay_service
from zhixing.studio.repository import default_studio_database_path
from zhixing.studio.secrets import load_studio_secrets, resolve_studio_secrets_path


def _parser() -> argparse.ArgumentParser:
    """Build the local Studio command parser.

    Args:
        None.

    Raises:
        None.

    Returns:
        argparse.ArgumentParser: Configured parser.
    """
    parser = argparse.ArgumentParser(prog="python -m zhixing.studio")
    subcommands = parser.add_subparsers(dest="command")
    serve = subcommands.add_parser("serve", help="run the local Studio HTTP API")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)
    serve.add_argument("--workspace", type=Path, default=None)
    serve.add_argument("--database", type=Path, default=None)
    serve.add_argument(
        "--device-profile-config",
        type=Path,
        default=None,
        help="load one trusted local Android profile JSON file",
    )
    serve.add_argument(
        "--secrets",
        type=Path,
        default=None,
        help="load one trusted local SecretRef YAML mapping",
    )
    serve.add_argument(
        "--benchmark-package",
        type=Path,
        action="append",
        default=[],
        help="add one explicit Benchmark Package directory",
    )
    serve.add_argument(
        "--benchmark-catalog-root",
        type=Path,
        action="append",
        default=[],
        help="add one explicit Benchmark Catalog root",
    )
    serve.add_argument(
        "--no-installed-benchmarks",
        action="store_true",
        help="disable installed Benchmark Package metadata discovery",
    )

    replay = subcommands.add_parser(
        "replay-import",
        help="import one explicit trusted local Replay source",
    )
    source = replay.add_mutually_exclusive_group(required=True)
    source.add_argument("--package", type=Path)
    source.add_argument("--legacy-run", type=Path)
    replay.add_argument("--benchmark-result", type=Path, default=None)
    replay.add_argument("--artifact-root", type=Path, default=None)
    replay.add_argument("--graph-snapshot", type=Path, default=None)
    replay.add_argument(
        "--provenance",
        choices=(
            "legacy_benchmark_import",
            "real_android_excerpt",
            "fake_contract_fixture",
        ),
        default="legacy_benchmark_import",
    )
    replay.add_argument("--workspace", type=Path, default=None)
    replay.add_argument("--database", type=Path, default=None)
    return parser


def _database_path(
    database: Path | None,
    workspace: Path | None,
) -> Path:
    """Resolve an explicit or workspace-isolated Studio database.

    Args:
        database (Path | None): Optional explicit database override.
        workspace (Path | None): Optional workspace identity root.

    Raises:
        OSError: Workspace resolution fails.

    Returns:
        Path: Resolved database path.
    """
    if database is not None:
        return database.expanduser()
    return default_studio_database_path(workspace or Path.cwd())


def _configured_paths(
    cli_values: Sequence[Path],
    environment_name: str,
) -> tuple[Path, ...]:
    """Combine repeated CLI paths with one platform-separated environment list.

    Args:
        cli_values (Sequence[Path]): Explicit repeated command-line paths.
        environment_name (str): Environment variable holding ``os.pathsep``
            separated paths.

    Raises:
        None.

    Returns:
        tuple[Path, ...]: Ordered explicit source paths.
    """
    environment_paths = tuple(
        Path(value)
        for value in os.environ.get(environment_name, "").split(os.pathsep)
        if value.strip()
    )
    return tuple(cli_values) + environment_paths


def _run_replay_import(args: argparse.Namespace) -> None:
    """Execute one explicit local Replay import and print safe JSON identity.

    Args:
        args (argparse.Namespace): Parsed replay-import arguments.

    Raises:
        ReplayImportError: Input is invalid or unsafe.
        ReplayConflictError: Run identity already exists.
        OSError: Input or managed storage cannot be accessed.

    Returns:
        None.
    """
    service = build_default_replay_service(
        _database_path(args.database, args.workspace)
    )
    if args.package is not None:
        envelope = service.import_native_package(args.package)
    else:
        envelope = service.import_legacy_benchmark(
            args.legacy_run,
            benchmark_result=args.benchmark_result,
            artifact_root=args.artifact_root,
            graph_snapshot=args.graph_snapshot,
            provenance=args.provenance,
        )
    print(
        json.dumps(
            {
                "schemaVersion": 1,
                "runId": envelope.run_id,
                "provenance": envelope.provenance,
                "integrityState": envelope.integrity_state,
            },
            ensure_ascii=False,
        )
    )


def main(argv: Sequence[str] | None = None) -> None:
    """Run the selected Studio command while preserving no-argument serving.

    Args:
        argv (Sequence[str] | None): Optional command arguments for tests.

    Raises:
        ValueError: Environment port is not an integer.
        OSError: Logging, storage, or server startup fails.

    Returns:
        None.
    """
    args = _parser().parse_args(argv)
    log_dir = Path("temp/log")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = str(log_dir / "zhixing_studio.log")
    setup_logging(log_path)
    if args.command == "replay-import":
        _run_replay_import(args)
        return

    logging.getLogger(__name__).info("Starting zhixing.studio …")
    host = getattr(args, "host", None) or os.environ.get(
        "ZHIXING_STUDIO_HOST",
        "127.0.0.1",
    )
    port = getattr(args, "port", None) or int(
        os.environ.get("ZHIXING_STUDIO_PORT", "8765")
    )
    profiles = load_android_device_profiles(
        resolve_device_profile_config_path(
            getattr(args, "device_profile_config", None)
        )
    )
    secrets = load_studio_secrets(
        resolve_studio_secrets_path(getattr(args, "secrets", None))
    )
    # Configuration is validated before announcing startup so a rejected file
    # cannot look like a listening service to the operator.
    print(
        f"ZhiXing Studio 正在启动: http://{host}:{port}\n"
        f"进程将一直占用此终端（serve_forever）；按 Ctrl+C 结束。\n"
        f"访问与请求日志见: {log_path}\n"
        f"若在子目录执行 ``python -m zhixing.studio`` 无法找到包，请改为在仓库根目录运行，或: python run_studio.py",
        flush=True,
    )
    run_httpd(
        host=host,
        port=port,
        workspace=getattr(args, "workspace", None),
        database_path=getattr(args, "database", None),
        benchmark_package_dirs=_configured_paths(
            getattr(args, "benchmark_package", ()),
            "ZHIXING_STUDIO_BENCHMARK_PACKAGES",
        ),
        benchmark_catalog_roots=_configured_paths(
            getattr(args, "benchmark_catalog_root", ()),
            "ZHIXING_STUDIO_BENCHMARK_CATALOG_ROOTS",
        ),
        include_installed_benchmarks=not getattr(
            args,
            "no_installed_benchmarks",
            False,
        ),
        device_profiles=profiles,
        secret_provider=secrets,
    )


if __name__ == "__main__":
    main()
