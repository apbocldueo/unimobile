import json
import re
import logging
from typing import Dict, List, Any
from unimobile.core.protocol import Action, ActionType
from unimobile.core.interfaces import BaseActionParser
from unimobile.utils.registry import register_parser

logger = logging.getLogger(__name__)

@register_parser("json_action_parser")
class JsonActionParser(BaseActionParser):
    """
    General JSON parser
    """
    def parse(self, response: str, metadata: dict) -> Action:
        """parse

        Args:
            response (str): _description_
            metadata (dict): It needs to include information such as mode, width, height, perception_metadata

        Returns:
            Action: _description_
        """
        mode = metadata.get("mode", "unknown")
        width = metadata.get("width", 0)
        height = metadata.get("height", 0)
        perception_metadata = metadata.get("perception_metadata", {})
        perception_elements = metadata.get("elements", [])

        try:
            json_str = self._extract_json(response)
            if not json_str:
                return Action(type=ActionType.WAIT, thought="JSON parse failed", metadata={"raw_response": response})
            
            data = json.loads(json_str)

            action_name = self._fuzzy_get(data, ["name", "action", "function", "tool"], default="").lower()
            args = self._fuzzy_get(data, ["arguments", "args", "parameters", "params"], default={})
            thought = self._fuzzy_get(data, ["thought", "thoughts", "reasoning"], default="")

            action_obj = None

            if action_name in ["tap", "click"]:
                if "grid" in mode:
                    area = args.get("area")
                    subarea = args.get("subarea", "center")
                    rows = perception_metadata.get("rows", 10)
                    cols = perception_metadata.get("cols", 5)
                    x, y = self.area_to_xy(area, subarea, width, height, rows, cols)
                    action_obj = Action(type=ActionType.TAP, params={"x": x, "y": y})
                    
                elif "set_of_marks" in mode or "som" in mode:
                    element_id = self._fuzzy_get(args, ["element_id", "id", "tag", "index"], default=None)
                    logger.info(f"🔍 [SoM Debug] LLM requests ID: {element_id} (类型: {type(element_id)})")
                    logger.info(f"🔍 [SoM Debug] List of available elements (the first 5): {[e.get('index') for e in perception_elements[:5]]}")
                    if element_id is not None:
                        target = next((e for e in perception_elements if str(e.get('index')) == str(element_id)), None)
                        
                        if target:
                            coords = target.get('coordinates', [0, 0])
                            action_obj = Action(type=ActionType.TAP, params={"x": coords[0], "y": coords[1]})
                            logger.info(f"SoM ID {element_id} mapped to coordinates: {coords}")
                        else:
                            return Action(type=ActionType.WAIT, thought=f"Element ID {element_id} not found in detection results.", metadata={"raw_response": response})
                    else:
                        return Action(type=ActionType.WAIT, thought="Missing 'element_id' for SoM Tap action.", metadata={"raw_response": response})
                
                else:
                    action_obj = Action(type=ActionType.TAP, params={"x": args.get("x"), "y": args.get("y")})

            elif action_name in ["swipe", "scroll"]:
                action_obj = Action(type=ActionType.SWIPE, params=args)

            elif action_name in ["type", "input"]:
                action_obj = Action(type=ActionType.TEXT, params={"text": args.get("text")})

            elif action_name in ["home", "back", "enter", "clear", "del"]:
                code = "del" if action_name == "clear" else action_name
                action_obj = Action(type=ActionType.KEY, params={"code": code})
            
            elif action_name in ["done", "finish", "complete"]:
                action_obj = Action(type=ActionType.DONE)

            else:
                action_obj = Action(type=ActionType.WAIT, thought=f"Unknown action: {action_name}")

            action_obj.thought = thought
            action_obj.metadata = {"raw_response": response}
            return action_obj

        except Exception as e:
            logger.error(f"Action parse failed: {e}")
            return Action(type=ActionType.FAIL, thought=str(e))
        
    def _extract_json(self, text: str) -> str:
        """
        Extract the first valid outermost JSON object in the string
        """
        text = text.replace("<|begin_of_box|>", "").replace("<|end_of_box|>", "")
        
        start_idx = text.find("{")
        if start_idx == -1:
            return None
            
        stack = 0
        found_start = False
        
        for i, char in enumerate(text[start_idx:]):
            if char == "{":
                stack += 1
                found_start = True
            elif char == "}":
                stack -= 1
            
            if found_start and stack == 0:
                return text[start_idx : start_idx + i + 1]
                
        return text[start_idx:]

    def _fuzzy_get(self, data: Dict, keys: List[str], default: Any) -> Any:
        for k in keys:
            if k in data:
                return data[k]
        
        data_keys_lower = {k.lower(): k for k in data.keys()}
        for k in keys:
            if k.lower() in data_keys_lower:
                real_key = data_keys_lower[k.lower()]
                return data[real_key]
        return default
    
    @staticmethod
    def area_to_xy(area, subarea, width, height, rows, cols):
        """
        Grid coordinate transformation
        """
        if not area: return width//2, height//2

        area = int(area) - 1
        row, col = area // cols, area % cols
        x_0, y_0 = col * (width // cols), row * (height // rows)
        
        cell_w = width // cols
        cell_h = height // rows

        if subarea == "top-left":
            x, y = x_0 + cell_w // 4, y_0 + cell_h // 4
        elif subarea == "top":
            x, y = x_0 + cell_w // 2, y_0 + cell_h // 4
        elif subarea == "top-right":
            x, y = x_0 + cell_w * 3 // 4, y_0 + cell_h // 4
        elif subarea == "left":
            x, y = x_0 + cell_w // 4, y_0 + cell_h // 2
        elif subarea == "right":
            x, y = x_0 + cell_w * 3 // 4, y_0 + cell_h // 2
        elif subarea == "bottom-left":
            x, y = x_0 + cell_w // 4, y_0 + cell_h * 3 // 4
        elif subarea == "bottom":
            x, y = x_0 + cell_w // 2, y_0 + cell_h * 3 // 4
        elif subarea == "bottom-right":
            x, y = x_0 + cell_w * 3 // 4, y_0 + cell_h * 3 // 4
        else:
            x, y = x_0 + cell_w // 2, y_0 + cell_h // 2
            
        return int(x), int(y)
