"""Installed EcoAgent execution with base dependencies and explicit fake services."""

import io
import json
from importlib.resources import files
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from zhixing.components import RunStatus
from zhixing.ecoagent import build_ecoagent_graph
from zhixing.graph import load_graph_yaml
from zhixing.plugins.agent.ecoagent.environment import EcoEnvironment
from zhixing.plugins.agent.ecoagent.types import EcoReply
from zhixing.sdk import AgentRunConfig, compile_agent


class Device:
    """Installed external device fixture, without repository test imports."""
    serial='installed-fixture'
    def __init__(self):
        """Initialize command log. Returns: None."""
        self.commands=[]
    def shell(self,command,error_raise=True):
        """Record effect. Args: command,error_raise: Source operation. Returns: object: Status."""
        self.commands.append(command)
        return SimpleNamespace(exit_code=0)
    def screenshot(self,path):
        """Save screenshot. Args: path: Owned artifact. Returns: str: Path."""
        Image.new('RGB',(20,30)).save(path)
        return path


class Model:
    """Installed external model fixture exercises a discarded failed prediction."""
    def __init__(self):
        """Start observer count. Returns: None."""
        self.summaries=0
    def complete(self,operation,prompt,images):
        """Serve one source request. Args: operation,prompt,images: Request. Raises: RuntimeError: Discarded prediction. Returns: EcoReply: Response."""
        if operation=='action':raise RuntimeError('discard this prediction')
        if operation in ('planning','replanning'):
            steps=['INPUT [hi]','TAP Save'] if operation=='planning' else ['PRESS_HOME']
            return EcoReply('```json\n'+json.dumps({str(i):{'step':s,'expectation':'expected'} for i,s in enumerate(steps)})+'\n```',10)
        if operation=='summary':
            self.summaries+=1
            return EcoReply('not correct' if self.summaries==1 else 'matches')
        return EcoReply('screen description')


def main():
    """Verify wheel resources and default resolver/YAML execution with scoped jobs.

    Raises:
        AssertionError: Installed resources, source protocol, identity or runtime fails.
    Returns:
        None.
    """
    source=files('zhixing.plugins.agent.ecoagent')
    for name in ('source-origin.json','compatibility.json','LICENSE','NOTICE'):
        assert source.joinpath(name).is_file()
    agent_graph=load_graph_yaml('ecoagent_online.yaml')
    assert compile_agent(agent_graph).canonical_hash==build_ecoagent_graph().canonical_hash()
    model=Model();raw=Device()
    with EcoEnvironment(raw,sleep=lambda seconds:None) as boundary:
        jobs=boundary.jobs
        result=compile_agent(agent_graph,dependencies={key+'_llm':model for key in
            ('planner','executor','description','summary')}).run('fixture task',
                AgentRunConfig(artifact_root=Path('artifacts'),max_steps=33),device=boundary)
    assert result.status is RunStatus.SUCCESS,result.error
    assert jobs.closed and not jobs.futures
    payload=result.action_results[-1].metadata['ecoagent']
    assert payload['llm_calls']==2 and payload['benchmark_evaluated'] is False
    assert not any('input tap' in command for command in raw.commands)
    assert 'Future' not in json.dumps(result.to_safe_dict())
    print('ecoagent-installed:'+json.dumps({'status':result.status.value,'cloud_calls':payload['llm_calls']}))


if __name__=='__main__':main()
