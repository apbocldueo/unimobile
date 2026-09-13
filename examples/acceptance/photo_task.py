"""Example acceptance for a photo AgentGraph using independent device evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Sequence

import yaml

from zhixing.components import RunStatus
from zhixing.devices.android import AndroidDevice
from zhixing.sdk import AgentRunConfig, load_agent

from zhixing.devices.probes import AndroidContentProbe


def build_parser() -> argparse.ArgumentParser:
    """Build the explicit real-device acceptance parser.

    Args:
        None.

    Raises:
        None.

    Returns:
        argparse.ArgumentParser: Photo acceptance command parser.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Run a graph-native Mobile Agent on Android and require a new "
            "MediaStore image as independent success evidence."
        )
    )
    parser.add_argument("--agent", required=True, type=Path)
    parser.add_argument("--serial", required=True)
    parser.add_argument("--secrets", required=True, type=Path)
    parser.add_argument("--artifact-root", required=True, type=Path)
    parser.add_argument(
        "--instruction",
        default=(
            "打开相机，只点击一次白色快门按钮拍摄一张照片；"
            "执行一次拍照动作后，下一步必须输出 DONE，禁止重复拍照"
        ),
    )
    parser.add_argument("--max-steps", type=int, default=10)
    return parser


def _read_secrets(path: Path) -> dict[str, Any]:
    """Read runtime secrets without including values in diagnostics.

    Args:
        path (Path): Secret YAML mapping.

    Raises:
        ValueError: File is unreadable or not a string-keyed mapping.

    Returns:
        dict[str, Any]: Runtime SecretRef provider.
    """
    try:
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(f"cannot read secrets ({type(error).__name__})") from error
    if not isinstance(value, dict) or not all(
        isinstance(key, str) for key in value
    ):
        raise ValueError("secrets must be a string-keyed YAML mapping")
    return dict(value)


def run_acceptance(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    """Run the real photo task and compare pre/post MediaStore state.

    Args:
        args (argparse.Namespace): Agent, device, secret, task, and artifact inputs.

    Raises:
        None: Preconditions and runtime failures become safe result payloads.

    Returns:
        tuple[int, dict[str, Any]]: Exit code and auditable acceptance summary.
    """
    try:
        secrets = _read_secrets(args.secrets)
        device = AndroidDevice(serial=args.serial)
        device.go_home()
        device.wait(1.0)
        probe = AndroidContentProbe()
        before = probe.snapshot(device)
        agent = load_agent(args.agent, secrets=secrets)
    except Exception as error:
        return 2, {
            "accepted": False,
            "phase": "preflight",
            "error_type": type(error).__name__,
        }
    result = agent.run(
        args.instruction,
        AgentRunConfig(
            serial=args.serial,
            artifact_root=args.artifact_root,
            max_steps=args.max_steps,
            include_ui_tree=False,
            metadata={
                "acceptance": "android_photo",
                "android_content_baselines": {
                    "target_content": sorted(before.ids),
                },
            },
        ),
        device=device,
    )
    try:
        after = probe.snapshot(device)
        delta = probe.diff(before, after)
        after_count: int | None = after.raw_row_count
        probe_error = ""
    except Exception as error:
        delta = None
        after_count = None
        probe_error = type(error).__name__
    accepted = bool(
        result.status is RunStatus.SUCCESS
        and delta is not None
        and delta.has_additions
    )
    payload: dict[str, Any] = {
        "accepted": accepted,
        "phase": "complete",
        "canonical_hash": agent.canonical_hash,
        "run": result.to_safe_dict(),
        "media_before_count": before.raw_row_count,
        "media_after_count": after_count,
        "added_media_ids": list(delta.added_ids) if delta is not None else [],
        "media_probe_error": probe_error,
    }
    if result.artifact_namespace:
        evidence = (
            args.artifact_root
            / result.artifact_namespace
            / "photo-acceptance.json"
        )
        try:
            evidence.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            payload["acceptance_evidence"] = str(evidence)
        except OSError:
            payload["acceptance_evidence"] = ""
    return (0 if accepted else 1), payload


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the real Android photo acceptance command.

    Args:
        argv (Sequence[str] | None): Optional test argument vector.

    Raises:
        None.

    Returns:
        int: Zero only when both Agent success and new media are proven.
    """
    code, payload = run_acceptance(build_parser().parse_args(argv))
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
