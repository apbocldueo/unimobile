"""Validate or execute the Aguvis-7B CLI protocol through an Android graph."""

import argparse
import json
from pathlib import Path

from zhixing.aguvis import build_aguvis_graph
from zhixing.components import RunStatus
from zhixing.sdk import AgentRunConfig, compile_agent


def main() -> int:
    """Build a graph and optionally run a cached checkpoint on explicit Android.

    Raises:
        SystemExit: Arguments are malformed or execution lacks a task.
        ValueError: Graph/model configuration is invalid.
    Returns:
        int: Zero for static validation or Agent-declared completion, else one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-path", default="xlangai/Aguvis-7B-720P")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--mode", choices=("self-plan", "force-plan", "grounding"), default="self-plan")
    parser.add_argument("--low-level-instruction")
    parser.add_argument("--serial")
    parser.add_argument("--task", default="")
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--max-decisions", type=int, default=30)
    parser.add_argument("--artifact-root", type=Path, default=Path("temp/aguvis-runs"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    graph = build_aguvis_graph(max_steps=args.max_steps, max_decisions=args.max_decisions,
        mode=args.mode, low_level_instruction=args.low_level_instruction,
        model_params={"model_path": args.model_path, "device": args.device})
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
