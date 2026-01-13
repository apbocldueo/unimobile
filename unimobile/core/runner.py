import time
import os
import tempfile
import logging
from typing import Optional, Union, Dict
from PIL import Image

from unimobile.core.interfaces import BaseAgent
from unimobile.devices.base import BaseDevice, SwipeDirection
from unimobile.core.protocol import ActionType

logger = logging.getLogger(__name__)

class Runner:
    def __init__(self, agent: BaseAgent, device: BaseDevice):
        logger.info("========== Initialize Runner ==========")
        self.agent = agent
        self.device = device
        
        # TODO
        self.save_dir = os.path.join(os.getcwd(), "temp", "screenshots")
        
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
            print(f"📁 [Runner] The screenshot directory has been created: {self.save_dir}")
        else:
            print(f"📁 [Runner] The screenshot will be saved to: {self.save_dir}")
        
        logger.info("========== The initialization of Runner is complete ==========")
        logger.info("\n")

    def run(self, task_input: Union[str, Dict], max_steps: int = 15):
        if isinstance(task_input, dict):
            instruction = task_input.get("instruction", "")
            self.agent.reset(instruction)
        else:
            instruction = task_input
            self.agent.reset(instruction)
            
        print(f"\n🚀 [Runner] Starting Task: {instruction}")
        
        task_id = int(time.time())
        trajectory = []
        
        step = 0
        while step < max_steps:
            step += 1
            logger.info(f"--- Step {step}/{max_steps} ---")
            print(f"\n--- Step {step}/{max_steps} ---")
            
            timestamp = int(time.time() * 1000)
            filename = f"task_{task_id}_step_{step}.png"
            screenshot_path = os.path.join(self.save_dir, filename)
            
            if step > 1:
                print("[Runner] ⏳ Wait for the screen to stabilize...")
                time.sleep(1.5)

            try:
                self.device.screenshot(path=screenshot_path)
                img = Image.open(screenshot_path)
                width = img.width
                height = img.height
                print(f"📸 [Device] The screenshot has been saved.: {screenshot_path}")
            except Exception as e:
                logger.error(f"Screenshot Failed: {e}")
                break
            
            try:
                action = self.agent.step(screenshot_path, width, height)
                print(f"🧠 [Agent] action is: {action}")
            except Exception as e:
                logger.error(f"Agent Execute Failed: {e}")
                break

            print(f"🧠 [Agent]: {action.type.value} -> params: {action.params}")
            
            step_record = {
                "step": step,
                "screenshot_path": screenshot_path,
                "action": action,
                "thought": action.thought
            }
            trajectory.append(step_record)

            if action.type == ActionType.DONE:
                print("✅ [Runner] The Agent believes that the task has been completed！")
                break
            elif action.type == ActionType.FAIL:
                print("❌ [Runner] Agent give up task (Fail)。")
                break
            elif action.type == ActionType.WAIT:
                print("⏳ [Runner] Agent request to wait...")
                time.sleep(2)
                continue

            self._execute_on_device(action)
            time.sleep(0.5)
            
        print("\n🎉 [Runner] Task Finish！")
        return trajectory

    def _execute_on_device(self, action):
        try:
            if action.type == ActionType.TAP:
                # {"x": 100, "y": 200}
                # tap(x, y)
                x = int(action.params.get('x', 0))
                y = int(action.params.get('y', 0))
                self.device.tap(x, y)

            elif action.type == ActionType.TEXT:
                # {"text": "hello"}
                # input_text(text)
                text = action.params.get('text', "")
                self.device.input_text(text)

            elif action.type == ActionType.SWIPE:
                # {"direction": "left", "dist": "medium"}
                # swipe(direction, scale)
                direction_str = action.params.get('direction', 'left').lower()
                dist_str = action.params.get('dist', 'medium').lower()
                
                scale_map = {
                    "short": 0.4,
                    "medium": 0.6,
                    "long": 0.8
                }
                scale = scale_map.get(dist_str, 0.6)
                
                self.device.swipe(direction=direction_str, scale=scale)

            elif action.type == ActionType.KEY:
                code = action.params.get('code', '').lower()
                
                if code == 'home':
                    self.device.go_home()
                elif code == 'back':
                    self.device.go_back()
                elif code == 'enter':
                    self.device.enter()
                elif code in ['del', 'clear']:
                    self.device.clear_text()
                else:
                    logger.warning(f"Unknown key code: {code}")

            print(f"👆 [Device] Instructions {action.type.value} Finish")

        except Exception as e:
            logger.error(f"Failed to execute the device instruction: {e}")
            print(f"❌ [Device] Executing Error: {e}")