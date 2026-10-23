"""Loopback-only ordinary Run acceptance server; never real Android evidence."""

from __future__ import annotations

import argparse
import json
import sys
import threading
from pathlib import Path


def main() -> None:
    """Serve a fresh fake workspace with explicit stdin hold/release controls.

    Raises:
        ValueError: The workspace is not empty or production readiness fails.
        OSError: Local storage or loopback binding fails.
    Returns:
        None; EOF or the stop command releases holds and closes owned resources.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--browser-origin", default="http://127.0.0.1:4191")
    parser.add_argument("--hold", action="store_true")
    parser.add_argument("--fail-at", type=int, choices=(1, 2))
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tests.studio.run_experience_fixtures import forbid_real_effects

    with forbid_real_effects() as counters:
        _serve(args, counters)


def _serve(args: argparse.Namespace, counters: dict[str, int]) -> None:
    """Run the owned HTTP server inside the acceptance effect tripwires.

    Args:
        args: Parsed fresh-workspace and fake-scenario options.
        counters: Guard-owned attempted-effect counts, not execution counts.
    Raises:
        ValueError: Compilation/readiness or workspace isolation fails.
        OSError: Loopback socket or storage setup fails.
    Returns:
        None after stdin stop/EOF, with all held calls released.
    """
    from tests.studio.run_experience_fixtures import RunControl, build_run_experience_harness
    from zhixing.studio.httpd import create_http_server

    harness = build_run_experience_harness(
        args.workspace, control=RunControl(hold=args.hold, fail_at=args.fail_at, timeout=600),
    )
    server = create_http_server(
        "127.0.0.1", args.port, application_service=harness.authoring,
        run_composition=harness.composition,
        allowed_origins=frozenset({args.browser_origin}),
        sse_heartbeat_seconds=0.5,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(json.dumps({
        "kind": "FAKE / NO REAL DEVICE", "agentId": harness.agent_id,
        "revisionId": harness.revision_id,
        "designPath": f"/agents/{harness.agent_id}/design",
        "commands": ["release", "stats", "stop"],
    }), flush=True)
    try:
        for line in sys.stdin:
            command = line.strip()
            if command == "stop":
                break
            if command == "release":
                harness.control.release.set()
            print(json.dumps({
                "executions": harness.control.executions,
                "modelCalls": harness.control.model_calls,
                "heldCallEntered": harness.control.started.is_set(),
                "deviceCalls": [call[0] for call in harness.device.calls],
                "forbiddenEffects": {**counters, "real-secret": harness.control.secret_attempts},
            }), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        harness.control.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        harness.close()


if __name__ == "__main__":
    main()
