from android_world.agents.base_agent import EnvironmentInteractingAgent
from android_world.agents import base_agent

import sys
import json
import re
from pathlib import Path

sys.path.append("../..")

from model.agent import Agent
from recorder import Recorder
from environment import get_env
import subprocess

ROOT_DIR = Path(__file__).parent.parent.parent

def get_code_snippet(content):
    code = re.search(r'```.*?\n([\s\S]+?)\n```', content)
    if code is None:
        raise RuntimeError()
    code = code.group(1)
    return code

class AndroidGen(EnvironmentInteractingAgent):
    def __init__(self, env, name="AndroidGen"):
        super().__init__(env, name)
        self.interface = get_env('android')(env=env)
        
        self.config = json.load(open(ROOT_DIR / 'config.json'))
        
        self.agent = None
        self.recorder = None
        self.to_be_reset = False
    
    def reset(self, go_home: bool = False) -> None:
        super().reset(go_home)
        self.to_be_reset = True

    def step(self, instruction):
        if self.to_be_reset:
            self.agent = Agent(llm=self.config["llm"], architecture_config=self.config["architecture"], instruction=instruction, environment='android')
            if self.recorder is not None:
                self.recorder.save()
            self.recorder = Recorder(instruction=instruction, trace_dir=self.config["TRACE_DIR"])
            self.to_be_reset = False
        
        state, record = self.interface.get_current_state()
        
        output = self.agent(state, history=self.recorder.format_history())
        
        exe_res = self.interface.interact(get_code_snippet(output['response']))
        
        self.agent.update(exe_res)
        
        self.recorder.update(record, output, exe_res)
        
        if exe_res['operation'] == 'exit':
            done=True
            subprocess.run(['python', '-m', 'model.judge.judge', '-d', './evaluate/androidworld/episodes'], cwd='../..')
        else:
            done=False
        
        return base_agent.AgentInteractionResult(
            done=done,
            data=record,
        )
