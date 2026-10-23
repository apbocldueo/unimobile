"""Validate GUI-explorer without effects, or run against an explicitly selected device."""

import argparse
import json
from pathlib import Path

from zhixing.guiexplorer import build_guiexplorer_graph


def main() -> int:
    """Compile the online graph or connect the explicit official Device for execution.

    Raises:
        SystemExit: Required execution arguments are missing.
        Exception: Optional dependencies or real source service setup fails.
    Returns:
        int: Zero for dry run or Agent-declared completion; otherwise one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="")
    parser.add_argument("--serial")
    parser.add_argument("--max-rounds", type=int, default=30)
    parser.add_argument("--model")
    parser.add_argument("--retrieval-endpoint")
    parser.add_argument("--artifact-root", type=Path, default=Path("temp/guiexplorer-runs"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    graph = build_guiexplorer_graph(max_rounds=args.max_rounds, retrieval_endpoint=args.retrieval_endpoint,
        model_params={"model": args.model} if args.model else None)
    if args.dry_run:
        print(json.dumps({"graph_hash": graph.canonical_hash(), "execution_evidence": False}))
        return 0
    if not args.task.strip() or not args.serial:
        parser.error("execution requires --task and an explicit --serial")
    from zhixing.components import RunStatus
    from zhixing.plugins.agent.guiexplorer.environment import GUIExplorerEnvironment
    from zhixing.plugins.agent.guiexplorer.source import Device
    from zhixing.sdk import AgentRunConfig, compile_agent

    device = Device(args.serial)
    try:
        result = compile_agent(graph).run(args.task,
            AgentRunConfig(artifact_root=args.artifact_root, max_steps=args.max_rounds + 1, include_ui_tree=False),
            device=GUIExplorerEnvironment(device))
        print(json.dumps({"run_id": result.run_id, "status": result.status.value, "benchmark_evaluated": False}))
        return 0 if result.status is RunStatus.SUCCESS else 1
    finally:
        device.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
