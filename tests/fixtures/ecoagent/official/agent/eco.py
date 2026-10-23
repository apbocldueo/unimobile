import base64
import json
import subprocess
import time
import re
from utils import ui_tars_utils, showui_utils, os_atlas_utils, qwen_utils
import infer
import requests
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import ThreadPoolExecutor
from config import load_config
from prompt import PLANNING_PROMPT, ACTION_PROMPT_UITARS, DESCRIPTION_PROMPT, SUMARRY_PROMPT, REPLANNING_PROMPT, ACTION_PROMPT_SHOWUI, ACTION_PROMPT_QWEN3, ACTION_PROMPT_OS_ATLAS



def capture_and_encode(device_image_path="/data/local/tmp/screen.jpeg", local_image_path="screen.jpeg"):
    # 1. Take screenshot using adb
    # Use screencap to capture a screenshot on Android, then pull it to local
    subprocess.run(f"adb shell screencap -p {device_image_path}", shell=True, check=True)

    # 2. Pull screenshot from device to local
    subprocess.run(f"adb pull {device_image_path} {local_image_path}", shell=True, check=True)

    # 3. Delete temporary file on device
    subprocess.run(f"adb shell rm {device_image_path}", shell=True, check=True)

    # 4. Convert image to base64 Data URL
    with open(local_image_path, "rb") as f:
        encoded_bytes = base64.b64encode(f.read())
        encoded_str = encoded_bytes.decode("utf-8")
        data_url = f"data:image/jpeg;base64,{encoded_str}"

    return data_url



class ECO():
    def __init__(
            self,
            llm: infer.Gpt4Wrapper,
            slm: infer.SLMWrapper,
            name='Eco',
            wait_after_action_seconds: float = 2.0,
            config_loader = None,
        ):
        """Initializes a ecoagent.
        
        Args:
            env: The environment.
            llm: The multimodal LLM wrapper.
            slm: The small language model wrapper.
            name: The name of the agent.
            wait_after_action_seconds: The number of seconds to wait after an action
            config_loader: Configuration loader instance.
        """
        if config_loader is None:
            config_loader = load_config()
        
        self.llm = llm
        self.slm = slm
        self.name = name
        self.history = []
        self.additional_guidelines = None
        self.wait_after_action_seconds = wait_after_action_seconds
        self.vision_config = config_loader.get_vision_config()
    # 📌 Provide utility methods to avoid code duplication
    def _needs_ui_tars(self, step_str: str) -> bool:
        # If step is text input, delete or press, no need UI-TARS
        if step_str.startswith(("INPUT", "DELETE TEXT", "PRESS_BACK", "PRESS_HOME")):
            return False
        return True

    def _execute_action(self, step_str, image):
        match_1 = re.match(r'INPUT \[(.*)\]', step_str)
        if step_str.startswith('DELETE TEXT'):
            # send DEL key multiple times to clear text (use KEYCODE_DEL = 67)
            cmd = ["adb", "shell", "input", "keyevent", "67"]
            for _ in range(10):
                subprocess.run(cmd, check=True)
        elif match_1:
            input_text = match_1.group(1)
            # adb input text requires spaces encoded as %s or properly escaped adb shell am broadcast -a ADB_INPUT_TEXT --es msg 'mobile simulation test'            
            cmd = ["adb", "shell", "am", "broadcast", "-a", "ADB_INPUT_TEXT", "--es", "msg", input_text]
            subprocess.run(cmd, check=True)
        elif step_str == 'PRESS_BACK':
            subprocess.run(["adb", "shell", "input", "keyevent", "KEYCODE_BACK"], check=True)
        elif step_str == 'PRESS_HOME':
            subprocess.run(["adb", "shell", "input", "keyevent", "KEYCODE_HOME"], check=True)
        else:
            if self.name == 'eco_ui-tars':
                action_output, is_safe, raw_response = self.slm.predict_mm(
                    ACTION_PROMPT_UITARS.format(goal=step_str),
                    image,
                )
                ui_tars_utils.run_from_response(action_output)
            elif self.name == 'eco_showui':
                action_output, is_safe, raw_response = self.slm.predict_mm(
                    ACTION_PROMPT_SHOWUI.format(goal=step_str),
                    image,
                )
                showui_utils.run_from_response(action_output)
            elif self.name == 'eco_qwen3':
                action_output, is_safe, raw_response = self.slm.predict_mm(
                    ACTION_PROMPT_QWEN3.format(goal=step_str),
                    image,
                )
                qwen_utils.run_from_response(action_output)
            elif self.name == 'eco_os-atlas':
                action_output, is_safe, raw_response = self.slm.predict_mm(
                    ACTION_PROMPT_OS_ATLAS.format(goal=step_str),
                    image,
                )
                os_atlas_utils.run_from_response(action_output)


    def _infer_description(self, image):
        vision_config = self.vision_config
        url = vision_config.get('description_api_url')
        model_name = vision_config.get('description_model_name')
        
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": DESCRIPTION_PROMPT},
                        {"type": "image_url", "image_url": {"url": image}},
                    ],
                }
            ],
            "max_tokens": vision_config.get('max_tokens', 256),
            "temperature": vision_config.get('temperature', 0),
        }
        result = requests.post(url, json=payload).json()
        return result['choices'][0]['message']['content']

    def _infer_summary(self, before_image, after_image, expectation):
        vision_config = self.vision_config
        summary_prompt = SUMARRY_PROMPT.format(expectation=expectation)
        url = vision_config.get('summary_api_url')
        model_name = vision_config.get('summary_model_name')
        
        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": summary_prompt},
                        {"type": "image_url", "image_url": {"url": before_image}},
                        {"type": "image_url", "image_url": {"url": after_image}}
                    ],
                }
            ],
            "max_tokens": vision_config.get('max_tokens', 256),
            "temperature": vision_config.get('temperature', 0),
        }
        result = requests.post(url, json=payload).json()
        return result['choices'][0]['message']['content']

    def _infer_next_action(self, image, goal_step):
        action_output, is_safe, raw_response = self.slm.predict_mm(
            ACTION_PROMPT_UITARS.format(goal=goal_step),
            image,
        )
        return action_output
    def step(self, goal: str, step_n: int, steps: list, expectations: list, descriptions: list, total_tokens: int, llm_calls: int) -> tuple:
        print(f"----------step {step_n + 1}")

        # ============ Step 1: Screenshot + Planning + Execution ============
        if step_n == 0:
            # Capture image + Planning
            image = capture_and_encode()
            planning_prompt = PLANNING_PROMPT.format(instruction=goal)
            planning_output, is_safe, raw_response, tokens = self.llm.predict_mm(
                planning_prompt,
                image,
            )
            total_tokens += tokens
            llm_calls += 1
            print(planning_output)

            # ✅ Consistent with original logic: Parse JSON plan
            json_start = planning_output.find('```json')
            if json_start == -1:
                json_start = planning_output.find('```')
            json_end = planning_output.find('```', json_start + 3) if json_start != -1 else -1
            if json_start == -1 or json_end == -1:
                print("No JSON plan found in response")
                return steps, expectations, descriptions, total_tokens, llm_calls, False

            json_content = planning_output[json_start + 3:json_end].strip().lstrip('JSON')
            json_content = json_content.replace('\n', '').replace('\r', '').replace('\t', '').strip()
            try:
                plan_dict = json.loads(json_content)
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON plan: {e}")
                return steps, expectations, descriptions, total_tokens, llm_calls, False

            steps = [v.get('step') for v in plan_dict.values() if isinstance(v, dict) and v.get('step')]
            expectations = [v.get('expectation') for v in plan_dict.values() if isinstance(v, dict) and v.get('expectation')]

            if not steps:
                print("No executable steps found in plan")
                return steps, expectations, descriptions, total_tokens, llm_calls, False

            # ✅ Execute step 0 action
            print(f'Executing step: {steps[0]}')
            self._execute_action(steps[0], image)

            # Wait after execution & capture again: Enter concurrent logic
            time.sleep(self.wait_after_action_seconds)
            after_image = capture_and_encode()
            before_image = image

        else:
            # ✅ after_image passed from previous round
            before_image = self.before_image
            after_image = self.after_image

        # ============ Image ready → Concurrent summary + description + next step prediction ============

        curr_expectation = expectations[step_n]
        next_step = steps[step_n + 1] if step_n + 1 < len(steps) else None

        with ThreadPoolExecutor() as executor:
            # Description & summary concurrent execution
            future_desc = executor.submit(self._infer_description, after_image)
            future_summary = executor.submit(self._infer_summary, before_image, after_image, curr_expectation)

            # If next step exists, predict UI-TARS action in parallel
            future_action = None
            if next_step and self._needs_ui_tars(next_step):
                future_action = executor.submit(self._infer_next_action, after_image, next_step)

            # Must wait for summary judgment first
            summary_output = future_summary.result()
            is_success = not bool(re.search(r'\bnot\b', summary_output.lower()))

            # Description output
            description_output = future_desc.result()
            print("Description:\n", description_output)
            descriptions.append(description_output)
            print("Summary:\n", summary_output)

        # ============ Success / Failure judgment ============
        if is_success:
            print("✅ Summary success.")

            # If next step exists: execute
            if next_step:
                if future_action:
                    action_output = future_action.result()
                    print("Action:\n", action_output)
                    ui_tars_utils.run_from_response(action_output)
                else:
                    print(f'Executing step: {next_step}')
                    self._execute_action(next_step, after_image)

                # Run action → take new screenshot → for next round
                time.sleep(self.wait_after_action_seconds)
                self.before_image = after_image
                self.after_image = capture_and_encode()
            else:
                print("No further steps. Goal completed.")
                return steps, expectations, descriptions, total_tokens, llm_calls, True

            # Return to continue next loop
            return steps, expectations, descriptions, total_tokens, llm_calls, False

        else:
            # ❌ Current step failed to meet expectation → failure → no action execution → enter Replan
            print("Summary failed. Replan needed.")

            replanning_prompt = REPLANNING_PROMPT.format(
                goal=goal,
                original_plan=json.dumps({"steps": steps, "expectations": expectations}),
                descriptions=descriptions,
                summary=summary_output,
                description=description_output,
            )
            replanning_output, is_safe, raw_response, tokens = self.llm.predict_mm(
                replanning_prompt,
                after_image
            )
            total_tokens += tokens
            llm_calls += 1
            print('Replanning output:\n', replanning_output)
            if replanning_output == "No need to replan." and step_n == len(steps) - 1:
                return steps, expectations, descriptions, total_tokens, llm_calls, True
                        # If next step exists: execute
            if replanning_output == "No need to replan.":
                if next_step:
                    if future_action:
                        action_output = future_action.result()
                        print("Action:\n", action_output)
                        ui_tars_utils.run_from_response(action_output)
                    else:
                        print(f'Executing step: {next_step}')
                        self._execute_action(next_step, after_image)

                    # Run action → take new screenshot → for next round
                    time.sleep(self.wait_after_action_seconds)
                    self.before_image = after_image
                    self.after_image = capture_and_encode()
                else:
                    print("No further steps. Goal completed.")
                    return steps, expectations, descriptions, total_tokens, llm_calls, True

                # Return to continue next loop
                return steps, expectations, descriptions, total_tokens, llm_calls, False

            # ✅ Keep original replanning JSON parsing logic
            json_start = replanning_output.find('```json')
            if json_start == -1:
                json_start = replanning_output.find('```')
            json_end = replanning_output.find('```', json_start + 3) if json_start != -1 else -1
            if json_start == -1 or json_end == -1:
                print("No JSON plan found in response")
                return steps, expectations, descriptions, total_tokens, llm_calls, False

            json_content = replanning_output[json_start + 3:json_end].strip().lstrip('JSON')
            json_content = json_content.replace('\n', '').replace('\r', '').replace('\t', '').strip()
            try:
                plan_dict = json.loads(json_content)
            except json.JSONDecodeError as e:
                print(f"Failed to parse JSON plan: {e}")
                return steps, expectations, descriptions, total_tokens, llm_calls, False

            # Update steps, expectations
            steps = steps[:step_n + 1] + [v.get('step') for v in plan_dict.values() if isinstance(v, dict) and v.get('step')]
            expectations = expectations[:step_n + 1] + [v.get('expectation') for v in plan_dict.values() if isinstance(v, dict) and v.get('expectation')]

            new_step = steps[step_n + 1]   # After replanning, steps[:step_n+1] are preserved, next step is the first step of new plan
            print(f"Executing replanned step: {new_step}")
            self._execute_action(new_step, after_image)

            # Take screenshot and enter next round
            time.sleep(self.wait_after_action_seconds)
            self.before_image = after_image
            self.after_image = capture_and_encode()
            return steps, expectations, descriptions, total_tokens, llm_calls, False
