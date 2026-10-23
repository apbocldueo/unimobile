"""Run the AutoDroid online template with explicit memory and Android bindings."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from zhixing.autodroid import build_autodroid_graph
from zhixing.sdk import AgentRunConfig, compile_agent
from zhixing.components import RunStatus


def main() -> int:
    """Compile an explicit AutoDroid configuration and optionally run one task.

    Args:
        None: Arguments come from the command line.
    Raises:
        ValueError: The graph configuration is invalid.
    Returns:
        int: Zero for a valid dry run or Agent completion; one for run failure.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory", required=True, help="Normalized JSON or upstream memory directory")
    parser.add_argument("--app-id", required=True, help="Target Android package")
    parser.add_argument("--upstream-app", default="", help="Upstream table key when different from package")
    parser.add_argument("--task", default="")
    parser.add_argument("--serial")
    parser.add_argument("--model", default="gpt-4o")
    parser.add_argument("--max-steps", type=int, default=100)
    parser.add_argument("--artifact-root", type=Path, default=Path("temp/autodroid-runs"))
    parser.add_argument("--dry-run", action="store_true", help="Validate graph only; no memory/model/device access")
    args = parser.parse_args()
    graph = build_autodroid_graph(memory_path=args.memory, app_id=args.app_id,
                                  model=args.model, max_steps=args.max_steps,
                                  memory_params={"upstream_app": args.upstream_app} if args.upstream_app else {})
    if args.dry_run:
        print(json.dumps({"graph_hash": graph.canonical_hash(), "execution_evidence": False}))
        return 0
    if not args.task.strip():
        parser.error("--task is required for execution")
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        parser.error("OPENAI_API_KEY is required for execution")
    agent = compile_agent(graph, secrets={"api_key": api_key,
                                          "base_url": os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")})
    result = agent.run(args.task, AgentRunConfig(serial=args.serial, artifact_root=args.artifact_root,
                                                max_steps=args.max_steps, include_ui_tree=True))
    print(json.dumps({"run_id": result.run_id, "status": result.status.value,
                      "interactions": result.interaction_count}, ensure_ascii=False))
    return 0 if result.status is RunStatus.SUCCESS else 1


if __name__ == "__main__":
    raise SystemExit(main())
