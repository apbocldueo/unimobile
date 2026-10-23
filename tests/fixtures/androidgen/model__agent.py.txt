from .llms import llm_provider
from .planning import Plan
from .example_retrieval import ExampleRetriever
from .prompt import prompt_provider
import sys
import select

class Agent:
    def __init__(self, llm, architecture_config, instruction, environment, init_state=None):
        self.instruction = instruction
        self.environment = environment
        self.llm = llm
        self.engine = llm_provider(self.llm["model_name"])
        self.input_type = self.llm["model_type"]
        self.architecture_config = architecture_config
        if self.architecture_config["reflectplan"]:
            self.plan = Plan(
                instruction, 
                self.architecture_config["reflectplan"], 
                self.environment
            )
        if self.architecture_config["expsearch"]:
            example_retrieval = self.architecture_config["expsearch"]
            self.example_retriever = ExampleRetriever(
                database_path=example_retrieval["database_path"],
                retriever_ckpt_path=example_retrieval["retriever_ckpt_path"]
            )
            best_example = self.example_retriever.retrieve_example(instruction, self.environment, init_state)
        else:
            best_example = None
            
        self.system_prompt = prompt_provider(self.environment, best_example)
        
        self.pre_exe_res = None
        
    def format_input_prompt(self, plan, current_state, error_feedback):
        prompt = ''
        if current_state:
            state = current_state[self.llm["model_type"]]['text']
            prompt += f'# Current State: {state}'
        
        if plan:
            prompt += f'\n\n# Plan: {plan}'
            
        if error_feedback:
            prompt += f'\n\n# Last Round Error: {error_feedback}'
            
        if self.llm["model_type"] == "image":
            prompt = {
                "text": prompt,
                "image_url": current_state[self.llm["model_type"]]['image_url']
            }
        
        return prompt
    
    def __call__(self, current_state, history):
        ret = {}
        
        if self.architecture_config["reflectplan"]:
            self.plan.planning(current_state, history.copy())
            formated_plan = self.plan.format_plan()
            ret['plan'] = formated_plan
        else:
            formated_plan = None
        
        error_feedback = None
        if self.architecture_config["autocheck"] and self.pre_exe_res is not None:
            if self.pre_exe_res['operation'] == 'fail':
                error_feedback = self.pre_exe_res['kwargs']['message']
                ret['error_feedback'] = error_feedback
        
        history = [
            {"role": "user", "content": {"text": f'# User Instruction: {self.instruction}'}},
            {"role": "assistant", "content": {"text": "** Task Start **"}}
        ] + history[-20:]
        
        prompt = self.format_input_prompt(
            formated_plan,
            current_state,
            error_feedback
        )
        
        model_output = self.engine.generate(
            prompt=prompt,
            system_prompt=self.system_prompt,
            history=history
        )
        ret['response'] = model_output

        return ret
    
    def update(self, exe_res):
        self.pre_exe_res = exe_res
        