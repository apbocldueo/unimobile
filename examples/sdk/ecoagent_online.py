"""Compile EcoAgent inertly, or explicitly execute its six-family online graph."""

import argparse
import json
import os
from pathlib import Path

from zhixing.ecoagent import build_ecoagent_graph
from zhixing.sdk import compile_agent


def main():
    """Validate public arguments before explicit target/model setup.

    Raises:
        SystemExit: Required task, target or cloud credential is absent.
        Exception: Explicit model/device setup fails.
    Returns:
        int: Zero for dry-run/source success, one otherwise.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--task', default='')
    parser.add_argument('--serial', default='')
    parser.add_argument('--max-rounds', type=int, default=30)
    parser.add_argument('--planner-model', default='gpt-4o')
    parser.add_argument('--executor-model', default='ui-tars')
    parser.add_argument('--observer-model', default='DEVICE_OBSERVER')
    parser.add_argument('--planner-url', default='https://api.openai.com/v1/chat/completions')
    parser.add_argument('--executor-url', default='http://127.0.0.1:8801/v1/chat/completions')
    parser.add_argument('--description-url', default='http://127.0.0.1:8800/v1/chat/completions')
    parser.add_argument('--summary-url', default='http://127.0.0.1:8800/v1/chat/completions')
    parser.add_argument('--artifact-root', type=Path, default=Path('temp/ecoagent-runs'))
    args = parser.parse_args()
    graph = build_ecoagent_graph(max_rounds=args.max_rounds)
    if args.dry_run:
        print(json.dumps({'graph_hash': compile_agent(graph).canonical_hash, 'execution_evidence': False}))
        return 0
    if not args.task.strip() or not args.serial:
        parser.error('Execution requires --task and --serial')
    key = os.environ.get('OPENAI_API_KEY', '')
    if not key:
        parser.error('Execution requires runtime OPENAI_API_KEY')
    from zhixing.components import RunStatus
    from zhixing.devices.android import AndroidDevice
    from zhixing.plugins.agent.ecoagent.environment import EcoEnvironment
    from zhixing.plugins.llm.ecoagent_llm import EcoAgentLLM
    from zhixing.sdk import AgentRunConfig

    dependencies = {'planner_llm': EcoAgentLLM(api_key=key, model=args.planner_model, api_url=args.planner_url),
        'executor_llm': EcoAgentLLM(model=args.executor_model, api_url=args.executor_url),
        'description_llm': EcoAgentLLM(model=args.observer_model, api_url=args.description_url),
        'summary_llm': EcoAgentLLM(model=args.observer_model, api_url=args.summary_url)}
    with EcoEnvironment(AndroidDevice(args.serial)) as boundary:
        result = compile_agent(graph, dependencies=dependencies).run(args.task,
            AgentRunConfig(artifact_root=args.artifact_root, max_steps=graph.policies.max_steps), device=boundary)
    print(json.dumps({'run_id': result.run_id, 'status': result.status.value, 'benchmark_evaluated': False}))
    return 0 if result.status is RunStatus.SUCCESS else 1


if __name__ == '__main__':
    raise SystemExit(main())
