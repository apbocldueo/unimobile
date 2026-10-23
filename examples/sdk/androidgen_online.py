"""Compile AndroidGen without effects, or run its standalone online flow explicitly."""

import argparse
import json
from pathlib import Path

from zhixing.androidgen import build_androidgen_graph


def main() -> int:
    """Compile or run the six-family AndroidGen graph against caller-owned AndroidWorld.

    Raises:
        SystemExit: Execution lacks a task/database/checkpoint or arguments are invalid.
        Exception: Original environment/model/retrieval initialization or cleanup fails.
    Returns:
        int: Zero for dry-run or source exit; one for non-exit runtime outcomes.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--task', default='')
    parser.add_argument('--max-rounds', type=int, default=31)
    parser.add_argument('--max-plan-attempts', type=int, default=3)
    parser.add_argument('--model', default='gpt-4o-2024-08-06')
    parser.add_argument('--planner-model', default='gpt-4o-2024-08-06')
    parser.add_argument('--model-type', choices=('text','image'), default='text')
    parser.add_argument('--planner-model-type', choices=('text','image'), default='text')
    parser.add_argument('--database', type=Path)
    parser.add_argument('--checkpoint')
    parser.add_argument('--no-expsearch', action='store_true')
    parser.add_argument('--console-port', type=int, default=5554)
    parser.add_argument('--grpc-port', type=int, default=8554)
    parser.add_argument('--adb-path', default='adb')
    parser.add_argument('--serial', default='')
    parser.add_argument('--artifact-root', type=Path, default=Path('temp/androidgen-runs'))
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    examples = {}
    if args.database:
        examples['database_path'] = str(args.database)
    if args.checkpoint:
        examples['retriever_ckpt_path'] = args.checkpoint
    graph = build_androidgen_graph(max_rounds=args.max_rounds, max_plan_attempts=args.max_plan_attempts,
        model_type=args.model_type, planner_model_type=args.planner_model_type, expsearch=not args.no_expsearch,
        model_params={} if args.model == 'gpt-4o-2024-08-06' else {'model':args.model},
        planner_model_params={} if args.planner_model == 'gpt-4o-2024-08-06' else {'model':args.planner_model},
        example_params=examples)
    if args.dry_run:
        print(json.dumps({'graph_hash':graph.canonical_hash(), 'execution_evidence':False}))
        return 0
    if not args.task.strip():
        parser.error('--task is required for execution')
    if not args.no_expsearch and (args.database is None or args.checkpoint is None):
        parser.error('ExpSearch requires --database and --checkpoint')
    from android_world.env import env_launcher
    from zhixing.components import RunStatus
    from zhixing.plugins.agent.androidgen.environment import AndroidGenAdb, AndroidGenEnvironment
    from zhixing.sdk import AgentRunConfig, compile_agent

    env = env_launcher.load_and_setup_env(console_port=args.console_port, grpc_port=args.grpc_port,
        adb_path=args.adb_path, emulator_setup=False, freeze_datetime=False)
    try:
        env_launcher.verify_api_level(env)
        result = compile_agent(graph).run(args.task,
            AgentRunConfig(artifact_root=args.artifact_root, max_steps=args.max_rounds + 1, include_ui_tree=False),
            device=AndroidGenEnvironment(env, adb=AndroidGenAdb(args.adb_path, args.serial), reset_on_setup=True))
        print(json.dumps({'run_id':result.run_id, 'status':result.status.value,
            'benchmark_evaluated':False}, ensure_ascii=False))
        return 0 if result.status is RunStatus.SUCCESS else 1
    finally:
        # Caller ownership guarantees cleanup even for original fatal parsing paths.
        env.close()


if __name__ == '__main__':
    raise SystemExit(main())
