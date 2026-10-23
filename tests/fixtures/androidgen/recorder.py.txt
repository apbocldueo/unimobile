import time
import os
import json
from shutil import copyfile

class Recorder:
    def __init__(self, instruction, trace_dir, task_id=None):
        self.instruction = instruction
        self.id = task_id if task_id else int(time.time())
        self.screenshot_dir = os.path.join(trace_dir, str(self.id), 'screenshots')
        os.makedirs(self.screenshot_dir, exist_ok=True)
        self.file_path = os.path.join(trace_dir, str(self.id), 'record.jsonl')
        self.contents = []
    
    @property
    def turn_number(self):
        return len(self.contents)

    def update(self, record, output, exe_res):
        record['instruction'] = self.instruction
        record['trace_id'] = self.id
        record['index'] = self.turn_number
        record.update(output)
        record['parsed_action'] = exe_res
        
        copyfile(record['image'], os.path.join(self.screenshot_dir, f'{self.turn_number}.png'))
        record['image'] = f'{self.id}/screenshots/{self.turn_number}.png'
        
        copyfile(record['raw'], os.path.join(self.screenshot_dir, f'{self.turn_number}-raw.png'))
        record['raw'] = f'{self.id}/screenshots/{self.turn_number}-raw.png'
        
        self.contents.append(record)
        self.save()
    
    def save(self):
        with open(self.file_path, 'w') as f:
            for turn in self.contents:
                f.write(json.dumps(turn, ensure_ascii=False) + '\n')

    def format_history(self):
        history = []
        for turn in self.contents:
            env_input = '**Environment State (Omitted)**'
            if 'error_feedback' in turn:
                env_input += f'\n# Error Feedback: {turn["error_feedback"]}'
                
            history.append({"role": "user", "content": {"text": env_input}})
            history.append({"role": "assistant", "content": {"text": turn['response']}})
        
        return history
