"""Validate M3A without side effects, or execute it against explicit AndroidWorld."""

import argparse
import json
from pathlib import Path

from zhixing.m3a import build_m3a_graph


def main() -> int:
    """Compile or execute the complete M3A online composition.

    Raises:
        SystemExit: Arguments are invalid or a real run lacks a task.
        Exception: Original environment/model setup fails.
    Returns:
        int: Zero for dry run or normal Agent/environment completion, otherwise one.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task", default="")
    parser.add_argument("--max-rounds", type=int, default=30)
    parser.add_argument("--model", help="Override the pinned source model explicitly")
    parser.add_argument("--console-port", type=int, default=5554)
    parser.add_argument("--grpc-port", type=int, default=8554)
    parser.add_argument("--adb-path", default="adb")
    parser.add_argument("--start-on-home-screen", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=Path("temp/m3a-runs"))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    graph = build_m3a_graph(max_rounds=args.max_rounds, start_on_home_screen=args.start_on_home_screen,
                           model_params={"model": args.model} if args.model else None)
    if args.dry_run:
        print(json.dumps({"graph_hash": graph.canonical_hash(), "execution_evidence": False}))
        return 0
    if not args.task.strip():
        parser.error("--task is required for execution")
    from android_world.env import env_launcher
    from zhixing.components import RunStatus
    from zhixing.plugins.agent.m3a.environment import M3AEnvironment
    from zhixing.sdk import AgentRunConfig, compile_agent

    env = env_launcher.load_and_setup_env(console_port=args.console_port, grpc_port=args.grpc_port,
        adb_path=args.adb_path, emulator_setup=False, freeze_datetime=False)
    try:
        result = compile_agent(graph).run(args.task,
            AgentRunConfig(artifact_root=args.artifact_root, max_steps=args.max_rounds + 1, include_ui_tree=False),
            device=M3AEnvironment(env))
        print(json.dumps({"run_id": result.run_id, "status": result.status.value,
                          "benchmark_evaluated": False}, ensure_ascii=False))
        return 0 if result.status is RunStatus.SUCCESS else 1
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(main())
