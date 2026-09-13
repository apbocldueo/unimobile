#!/usr/bin/env python3
"""Run the actual fake-device Studio composition for browser acceptance.

The launcher deliberately lives outside the product package.  It emits exactly
one safe bootstrap JSON object on stdout, keeps all incidental framework output
on stderr, and tears down the worker and HTTP server on SIGINT or SIGTERM.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import signal
import sys
import threading
from pathlib import Path
from typing import Any


def _parser() -> argparse.ArgumentParser:
    """Build the bounded acceptance-server command parser.

    Returns:
        Configured argument parser.
    """
    parser = argparse.ArgumentParser(
        description="Run the Stage 5.6B actual fake Studio acceptance server."
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    return parser


def _install_signal_handlers(stopped: threading.Event) -> None:
    """Install process-local bounded shutdown handlers.

    Args:
        stopped: Event set when SIGINT or SIGTERM is received.

    Raises:
        ValueError: Signal handlers cannot be installed in this thread.

    Returns:
        None.
    """

    def stop(_signum: int, _frame: Any) -> None:
        """Request graceful server teardown without doing I/O in a signal.

        Args:
            _signum: Received signal number.
            _frame: Interrupted interpreter frame.

        Returns:
            None.
        """
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)


def main(argv: list[str] | None = None) -> int:
    """Start one actual fake Studio server and emit its safe bootstrap.

    Args:
        argv: Optional arguments excluding the executable name.

    Raises:
        OSError: Workspace or loopback server setup fails.
        ValueError: The acceptance fixture cannot be constructed.

    Returns:
        Zero after graceful teardown.
    """
    args = _parser().parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    if not 1 <= args.port <= 65535:
        raise ValueError("acceptance server port must be between 1 and 65535")

    # Imports may initialize optional plugin discovery; keep those diagnostics
    # away from the single machine-readable bootstrap channel.
    repository_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repository_root))
    with contextlib.redirect_stdout(sys.stderr):
        from tests.studio.benchmark_layered_acceptance_fixtures import (
            build_layered_acceptance_harness,
        )

        harness = build_layered_acceptance_harness(workspace)
        server = harness.start_http_server(port=args.port)

    print(json.dumps(server.bootstrap, sort_keys=True), flush=True)
    stopped = threading.Event()
    _install_signal_handlers(stopped)
    try:
        while not stopped.wait(timeout=0.5):
            continue
    finally:
        server.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
