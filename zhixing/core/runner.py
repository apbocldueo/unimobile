import re
import time
import os
from typing import Any, Dict, List, Optional

from PIL import Image

from zhixing.core.agent.protocol import Action, ActionType
from zhixing.utils.utils import get_plugin_logger


def _annotate_screenshot_with_action(screenshot_path: str, action: Action) -> Optional[str]:
    """Optional overlay from local ``experiment/human_review_output.py`` (not in core package)."""
    try:
        from experiment.human_review_output import annotate_screenshot_with_action as _fn

        return _fn(screenshot_path, action)
    except ImportError:
        return None


def _safe_screenshot_dir_fragment(name: str) -> str:
    s = str(name).strip() or "unknown"
    s = re.sub(r"[^0-9A-Za-z_.-]+", "_", s).strip("._-")[:180]
    return s or "unknown"


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
        self.xml_dir = os.path.join(os.getcwd(), "temp", "xmls")
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
        start_app_catalog_text = self.device.format_start_app_catalog_for_prompt()

        # 1. Prepare Environment
        if app_name:
            self.logger.info("sleeping 2s before starting app=%r", app_name)
            time.sleep(2)
            self.device.start_app(app_name)

        # Screenshots: ``temp/screenshots/task_<session>/<dataset_task_id>/step_N.png``
        screenshot_session_id = (
            context.get("screenshot_session_id")
            or context.get("benchmark_session_id")
            or str(int(time.time()))
        )
        task_params = context.get("task_params") or {}
        raw_dataset_id = task_params.get("id")
        if raw_dataset_id is not None and str(raw_dataset_id).strip() != "":
            dataset_dir = _safe_screenshot_dir_fragment(str(raw_dataset_id))
        else:
            dataset_dir = "interactive"
        self.logger.info(
            "task start screenshot_session_id=%s dataset_dir=%s instruction=%r",
            screenshot_session_id,
            dataset_dir,
            task_instruction,
        )
        agent.reset({
            "instruction": task_instruction,
            "app": app_name,
            "start_app_catalog_text": start_app_catalog_text,
        })
        trajectory = []
        step = 0
        
        # 2. Main Execution Loop
        while step < max_steps:
            step += 1
            self.logger.info(" - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")
            self.logger.info(
                "          >>     AGENT STEP   %d / %d     <<          ( session = %s )",
                step,
                max_steps,
                screenshot_session_id,
            )
            self.logger.info(" - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - ")
            
            # A. Environmental Perception (Screenshot)
            filename = f"step_{step}.png"
            target_dir = os.path.join(
                self.save_dir, f"task_{screenshot_session_id}", dataset_dir
            )
            os.makedirs(target_dir, exist_ok=True)
            screenshot_path = os.path.join(target_dir, filename)
            
            if step > 1:
                self.logger.debug("stabilize delay before screenshot")
                time.sleep(1.5)

            try:
                self.device.screenshot(path=screenshot_path)
                xml_path = os.path.join(self.xml_dir, "ui_dump.xml")
                self.device.get_xml(xml_path)
                img = Image.open(screenshot_path)
                width, height = img.width, img.height
                self.logger.info("screenshot path=%s", screenshot_path)
            except Exception as e:
                self.logger.error("screenshot failed step=%d: %s", step, e, exc_info=True)
                break
            
            # B. Agent Decision Making (Brain)
            try:
                action = agent.step(screenshot_path, width, height, xml_path)
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
                seconds = action.params.get("seconds", 2.0)
                try:
                    seconds = float(seconds)
                except (TypeError, ValueError):
                    seconds = 2.0
                seconds = max(0.5, min(seconds, 30.0))
                self.logger.info("agent returned WAIT; sleeping %.1fs", seconds)
                self.device.wait(seconds)
                continue

            # D. Physical Execution (Body)
            self._execute_on_device(action)
            marked_path = _annotate_screenshot_with_action(screenshot_path, action)
            if marked_path:
                trajectory[-1]["action_marked_screenshot_path"] = marked_path
                self.logger.info("action marked screenshot path=%s", marked_path)
            time.sleep(0.5)

        self.logger.info(
            "run loop finished steps=%d screenshot_session_id=%s dataset_dir=%s",
            step,
            screenshot_session_id,
            dataset_dir,
        )
        return trajectory

    def _execute_on_device(self, action: Any) -> None:
        """Translates Agent Actions into physical device ADB commands."""
        try:
            if action.type == ActionType.TAP:
                x, y = int(action.params.get('x', 0)), int(action.params.get('y', 0))
                self.device.tap(x, y)
                if (action.metadata or {}).get("repeat_tap") == 2:
                    time.sleep(0.1)
                    self.device.tap(x, y)

            elif action.type == ActionType.LONG_PRESS:
                x, y = int(action.params.get('x', 0)), int(action.params.get('y', 0))
                duration_ms = int(action.params.get('duration_ms', 1000))
                self.device.long_press(x, y, duration_ms=duration_ms)
                
            elif action.type == ActionType.TEXT:
                if "x" in action.params and "y" in action.params:
                    x, y = int(action.params.get("x", 0)), int(action.params.get("y", 0))
                    self.device.tap(x, y)
                self.device.input_text(action.params.get('text', ""))
                if action.params.get("press_enter_after"):
                    self.device.enter()
                
            elif action.type == ActionType.SWIPE:
                if all(k in action.params for k in ("start_x", "start_y", "end_x", "end_y")):
                    start_x = int(action.params.get("start_x", 0))
                    start_y = int(action.params.get("start_y", 0))
                    end_x = int(action.params.get("end_x", 0))
                    end_y = int(action.params.get("end_y", 0))
                    duration_ms = int(action.params.get("duration_ms", 400))
                    if hasattr(self.device, "shell"):
                        self.device.shell(f"input swipe {start_x} {start_y} {end_x} {end_y} {duration_ms}")
                    else:
                        self.logger.warning("Precise swipe requires a device backend with shell()")
                    self.logger.info("device action OK type=%s", action.type.value)
                    return

                direction = action.params.get('direction', 'left').lower()
                dist_str = action.params.get('dist', 'medium').lower()
                scale = {"short": 0.4, "medium": 0.6, "long": 0.8}.get(dist_str, 0.6)

                if "x" in action.params and "y" in action.params and hasattr(self.device, "shell"):
                    x = int(action.params.get("x", 0))
                    y = int(action.params.get("y", 0))
                    unit_dist = int(getattr(self.device, "w", 1080) / 10)
                    if dist_str == "long":
                        unit_dist *= 3
                    elif dist_str == "medium":
                        unit_dist *= 2
                    offsets = {
                        "up": (0, -2 * unit_dist),
                        "down": (0, 2 * unit_dist),
                        "left": (-unit_dist, 0),
                        "right": (unit_dist, 0),
                    }
                    dx, dy = offsets.get(direction, offsets["left"])
                    self.device.shell(f"input swipe {x} {y} {x + dx} {y + dy} 400")
                    self.logger.info("device action OK type=%s", action.type.value)
                    return

                self.device.swipe(direction=direction, scale=scale)
                
            elif action.type == ActionType.KEY:
                code = action.params.get('code', '').lower()
                if code == 'home': self.device.go_home()
                elif code == 'back': self.device.go_back()
                elif code == 'enter': self.device.enter()
                elif code in ['del', 'clear']: self.device.clear_text()
                elif code in ['menu', 'appselect', 'recent', 'recents']:
                    if hasattr(self.device, "shell"):
                        self.device.shell("input keyevent KEYCODE_APP_SWITCH")
                    else:
                        self.logger.warning(f"Unknown key code: {code}")
                elif code:
                    if hasattr(self.device, "shell"):
                        self.device.shell(f"input keyevent {code.upper()}")
                    else:
                        self.logger.warning(f"Unknown key code: {code}")
                else: self.logger.warning(f"Unknown key code: {code}")

            elif action.type == ActionType.START_APP:
                app = (action.params.get("app") or "").strip()
                if app:
                    self.device.start_app(app)
                else:
                    self.logger.warning("START_APP action missing app param")

            self.logger.info("device action OK type=%s", action.type.value)
            
        except Exception as e:
            self.logger.error("device execution error action=%s: %s", action.type.value, e, exc_info=True)
