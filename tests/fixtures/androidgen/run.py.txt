import os
import sys
import re
import getpass
import json
from tqdm import tqdm
from recorder import Recorder
from model.agent import Agent
from environment import get_env

def get_code_snippet(content):
    code = re.search(r'```.*?\n([\s\S]+?)\n```', content)
    if code is None:
        raise RuntimeError()
    code = code.group(1)
    return code

def run(instruction) -> None:
    config = json.load(open('config.json'))
    Env = get_env(config['environment'])
    
    instruction = input("What would you like to do? >>> ") if instruction is None else instruction
    env = Env()
    recorder = Recorder(instruction=instruction, trace_dir=config["TRACE_DIR"])
    
    architecture_config = config["architecture"]
    agent = Agent(
        llm=config["llm"],
        architecture_config=architecture_config, 
        instruction=instruction, 
        environment=config['environment'], 
        init_state=env.init_state
    )

    while recorder.turn_number <= 30:
        
        state, record = env.get_current_state()
        
        output = agent(state, history=recorder.format_history())

        code = get_code_snippet(output['response'])

        exe_res = env.interact(code)

        agent.update(exe_res)
        
        recorder.update(record, output, exe_res)
        
        if exe_res['operation'] == 'exit':
            break
            
    recorder.save()
    env.close()

if __name__ == '__main__':
    instruction = sys.argv[1] if len(sys.argv) > 1 else input("What would you like to do? >>> ")
    run(instruction)