"""Validate or execute the SeeClick-AITW graph with explicit model/device inputs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from zhixing.components import RunStatus
from zhixing.sdk import AgentRunConfig, compile_agent
from zhixing.seeclick import build_seeclick_graph


def main() -> int:
    """Build the graph and optionally run against cached models and Android.

    Args:
        None: Configuration is supplied through command-line arguments.
    Raises:
        ValueError: A graph parameter is invalid.
        SystemExit: Command-line arguments are malformed or execution lacks a task.
    Returns:
        int: Zero for static validation or Agent DONE; one for execution failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default="cckevinn/SeeClick-aitw")
    parser.add_argument("--qwen-path", default="Qwen/Qwen-VL-Chat")
    parser.add_argument("--checkpoint-format", choices=("full", "lora"), default="full")
    parser.add_argument("--device-map", default="cuda")
    parser.add_argument("--task", default="")
    parser.add_argument("--serial")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-decisions", type=int, default=30)
    parser.add_argument("--artifact-root", type=Path, default=Path("temp/seeclick-runs"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    graph = build_seeclick_graph(model_path=args.model_path, qwen_path=args.qwen_path,
        checkpoint_format=args.checkpoint_format, max_steps=args.max_steps,
        max_decisions=args.max_decisions,
        model_params={"device_map": args.device_map} if args.device_map != "cuda" else None)
    if args.dry_run:
        print(json.dumps({"graph_hash": graph.canonical_hash(), "execution_evidence": False}))
        return 0
    if not args.task.strip():
        parser.error("--task is required for execution")
    result = compile_agent(graph).run(args.task, AgentRunConfig(serial=args.serial,
        artifact_root=args.artifact_root, max_steps=args.max_steps, include_ui_tree=False))
    print(json.dumps({"run_id": result.run_id, "status": result.status.value,
                      "interactions": result.interaction_count}, ensure_ascii=False))
    return 0 if result.status is RunStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
