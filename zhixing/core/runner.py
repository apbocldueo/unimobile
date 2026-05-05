import time
import os
from typing import Dict, Any, List
from PIL import Image

from zhixing.core.agent.protocol import ActionType
from zhixing.utils.utils import get_plugin_logger

class AgentRunner:
    """Pure Agent Execution Engine.
    
    Responsible solely for managing the environment loop: capturing screenshots, 
    querying the agent for decisions, and executing physical actions via ADB.
    """
    _pipeline_phase = "🏃 Runner"

    def __init__(self, device: Any):
        """Initializes the runner and prepares the environment."""
        self.logger = get_plugin_logger(
            phase=self._pipeline_phase, 
            namespace="core", 
            plugin_name=self.__class__.__name__
        )

        self.device = device
        self.save_dir = os.path.join(os.getcwd(), "temp", "screenshots")
        os.makedirs(self.save_dir, exist_ok=True)
        self.logger.info("AgentRunner init screenshot_root=%s", self.save_dir)

    def run(self, agent: Any, context: Dict[str, Any], max_steps: int = 15) -> List[Dict]:
        """Executes the main interaction loop between the Agent and the Device.

        Args:
            agent (Any): The initialized Agent instance (e.g., ModularAgent).
            context (Dict[str, Any]): Global execution context containing task instructions.
            max_steps (int): Maximum allowed steps before forceful termination.

        Returns:
            List[Dict]: The trajectory of the execution containing states and actions.
        """
        task_instruction = context.get("task_params", {}).get("instruction", "Unknown Task")
        app_name = context.get("task_params", {}).get("app")
        
        # 1. Prepare Environment
        if app_name:
            self.device.start_app(app_name)

        task_id = int(time.time())
        self.logger.info("task start task_id=%s instruction=%r", task_id, task_instruction)
        agent.reset({"instruction": task_instruction, "app": app_name})
        trajectory = []
        step = 0
        
        # 2. Main Execution Loop
        while step < max_steps:
            step += 1
            self.logger.info("step %d/%d task_id=%s", step, max_steps, task_id)
            
            # A. Environmental Perception (Screenshot)
            filename = f"task_{task_id}_step_{step}.png"
            target_dir = os.path.join(self.save_dir, f"task_{task_id}")
            os.makedirs(target_dir, exist_ok=True)
            screenshot_path = os.path.join(target_dir, filename)
            
            if step > 1:
                self.logger.debug("stabilize delay before screenshot")
                time.sleep(1.5)

            try:
                self.device.screenshot(path=screenshot_path)
                img = Image.open(screenshot_path)
                width, height = img.width, img.height
                self.logger.info("screenshot path=%s", screenshot_path)
            except Exception as e:
                self.logger.error("screenshot failed step=%d: %s", step, e, exc_info=True)
                break
            
            # B. Agent Decision Making (Brain)
            try:
                action = agent.step(screenshot_path, width, height)
            except Exception as e:
                self.logger.error("agent.step failed step=%d: %s", step, e, exc_info=True)
                break

            self.logger.info("decision action=%s params=%s", action.type.value, action.params)
            
            # Record Trajectory
            trajectory.append({
                "step": step,
                "screenshot_path": screenshot_path,
                "action": action,
                "thought": getattr(action, "thought", "")
            })

            # C. Check Termination Conditions
            if action.type == ActionType.DONE:
                self.logger.info("agent returned DONE")
                break
            elif action.type == ActionType.FAIL:
                self.logger.warning("agent returned FAIL")
                break
            elif action.type == ActionType.WAIT:
                self.logger.info("agent returned WAIT; sleeping 2s")
                time.sleep(2)
                continue

            # D. Physical Execution (Body)
            self._execute_on_device(action)
            time.sleep(0.5)

        self.logger.info("run loop finished steps=%d task_id=%s", step, task_id)
        return trajectory

    def _execute_on_device(self, action: Any) -> None:
        """Translates Agent Actions into physical device ADB commands."""
        try:
            if action.type == ActionType.TAP:
                x, y = int(action.params.get('x', 0)), int(action.params.get('y', 0))
                self.device.tap(x, y)
                
            elif action.type == ActionType.TEXT:
                self.device.input_text(action.params.get('text', ""))
                
            elif action.type == ActionType.SWIPE:
                direction = action.params.get('direction', 'left').lower()
                dist_str = action.params.get('dist', 'medium').lower()
                scale = {"short": 0.4, "medium": 0.6, "long": 0.8}.get(dist_str, 0.6)
                self.device.swipe(direction=direction, scale=scale)
                
            elif action.type == ActionType.KEY:
                code = action.params.get('code', '').lower()
                if code == 'home': self.device.go_home()
                elif code == 'back': self.device.go_back()
                elif code == 'enter': self.device.enter()
                elif code in ['del', 'clear']: self.device.clear_text()
                else: self.logger.warning(f"Unknown key code: {code}")
                
            self.logger.info("device action OK type=%s", action.type.value)
            
        except Exception as e:
            self.logger.error("device execution error action=%s: %s", action.type.value, e, exc_info=True)