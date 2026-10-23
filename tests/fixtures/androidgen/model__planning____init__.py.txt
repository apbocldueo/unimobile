import re
import sys

sys.path.append("..")
from ..llms import llm_provider
from .prompt import plan_system_prompt, update_plan_system_prompt

class Plan():
    def __init__(self, instruction, config, environment):
        self.plan = []
        self.instruction = instruction
        self.engine = llm_provider(llm=config["model_name"])
        self.model_type = config["model_type"]
        self.environent = environment
    
    def format_plan(self):
        if not self.plan:
            return None
        return '\n'.join([f'{stmt} State: [{"Done" if state else "Todo"}]' for stmt, state in self.plan])
        
    def _generate_plan(self, current_state):
        state = current_state[self.model_type]['text']
        
        prompt = '# Current State: %s\n\n# User Instruction: %s' % (state, self.instruction)
        
        if self.model_type == 'image':
            prompt = {
                "text": prompt,
                "image_url": current_state[self.model_type]['image_url']
            }
        
        output = self.engine.generate(
            prompt=prompt, 
            system_prompt=plan_system_prompt
        ).strip()
        
        for stmt in output.split('\n'):
            if stmt:
                try:
                    stmt, state = re.match(r'(\d+\. *.+) State: \[?(Done|Todo)\]?', stmt).groups()
                    self.plan.append((stmt, state == 'Done'))
                except:
                    continue
                
    def _update_plan(self, current_state, history):
        plan_str = self.format_plan()
        action_history = []
        
        for h in history:
            if h['role'] == 'assistant':
                action_history.append(h['content']['text'])
        
        state = current_state[self.model_type]['text']
                
        prompt = '# Current State: %s\n\n# User Instruction: %s\n\n# Action History: %s\n\n# User Plan: %s' % (state, self.instruction, '\n\n'.join(action_history), plan_str)
        
        if self.model_type == 'image':
            prompt = {
                "text": prompt,
                "image_url": current_state[self.model_type]['image_url']
            }
        
        while True:
            output = self.engine.generate(
                prompt=prompt,
                system_prompt=update_plan_system_prompt
            ).strip()
            
            # Parse the output into plan
            new_plan = []
            for stmt in output.split('\n'):
                if stmt:
                    try:
                        stmt, state = re.match(r'(\d+\. *.+) State: \[?(Done|Todo)\]?', stmt).groups()
                        new_plan.append((stmt, state == 'Done'))
                    except:
                        continue
        
            if len(new_plan) == 0:
                continue
            else:
                self.plan = new_plan
                break

    def planning(self, current_state, history):
        # Generate & Update Plan
        if not self.plan:
            self._generate_plan(current_state)
        else:
            self._update_plan(current_state, history)
        