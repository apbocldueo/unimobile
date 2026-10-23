"""Deterministic command-line acceptance test for the Android Graph Runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from zhixing.components import (
    Action,
    ActionType,
    ObservationRequest,
    RunStatus,
    RuntimeContext,
)

from zhixing.runtime.android import AndroidGraphRuntime, build_android_smoke_plan


_MISSING_PACKAGE = "com.zhixing.smoke.missing"


def build_parser() -> argparse.ArgumentParser:
    """Build the Android smoke-test command parser.

    Args:
        None.

    Raises:
        None.

    Returns:
        argparse.ArgumentParser: Parser for repeatable real-device acceptance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic AgentGraph against one Android device without "
            "LLM/VLM credentials."
        )
    )
    parser.add_argument("--serial", required=True, help="Exact adb serial to bind")
    parser.add_argument(
        "--artifact-root",
        type=Path,
        required=True,
        help="Directory under which a unique run namespace is created",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional stable run ID; omit it to generate a UUID-backed ID",
    )
    parser.add_argument(
        "--mode",
        choices=("success", "device-failure"),
        default="success",
        help=(
            "success sends HOME and reaches DONE; device-failure attempts to "
            "resolve and start a known-missing Android package"
        ),
    )
    return parser


def _action_for_mode(mode: str) -> Action:
    """Select the deterministic action for one acceptance mode.

    Args:
        mode (str): ``success`` or ``device-failure``.

    Raises:
        ValueError: The mode is not supported.

    Returns:
        Action: Safe HOME action or controlled missing-component action.
    """
    if mode == "success":
        return Action(ActionType.KEY, {"code": "home"})
    if mode == "device-failure":
        # This package identifier is syntactically valid but intentionally
        # absent, so Android reports a real failure without changing app data.
        return Action(ActionType.START_APP, {"app": _MISSING_PACKAGE})
    raise ValueError(f"Unsupported Android smoke mode: {mode}")


def run_smoke(args: argparse.Namespace) -> tuple[int, dict[str, object]]:
    """Execute one smoke graph and normalize its command exit status.

    Args:
        args (argparse.Namespace): Parsed serial, artifact root, run ID, and mode.

    Raises:
        None: Runtime failures are returned as structured RunResult payloads.

    Returns:
        tuple[int, dict[str, object]]: Process code and safe serialized result.
    """
    runtime = RuntimeContext(run_id=args.run_id) if args.run_id else RuntimeContext()
    result = AndroidGraphRuntime().run(
        build_android_smoke_plan(_action_for_mode(args.mode)),
        {"value": ObservationRequest()},
        artifact_root=args.artifact_root,
        serial=args.serial,
        runtime=runtime,
    )
    payload = result.to_safe_dict()
    expected = (
        RunStatus.SUCCESS
        if args.mode == "success"
        else RunStatus.DEVICE_FAILURE
    )
    return (0 if result.status is expected else 1), payload


def main(argv: Sequence[str] | None = None) -> int:
    """Run the Android acceptance command and print its JSON evidence.

    Args:
        argv (Sequence[str] | None): Optional argument vector for tests.

    Raises:
        None.

    Returns:
        int: Zero only when the selected mode reaches its expected outcome.
    """
    args = build_parser().parse_args(argv)
    exit_code, payload = run_smoke(args)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
