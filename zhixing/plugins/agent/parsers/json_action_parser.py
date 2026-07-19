import json
import re
from typing import Dict, List, Any, Tuple, Union
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.plugins.agent.perception.coordinates import (
    COORDINATE_SCALE_MAX,
    normalized_coordinate_to_pixel,
)
# from zhixing.utils.registry import register_parser
from zhixing.core.factory import PluginRegistry


class ActionParseError(Exception):
    """Model output could not be parsed into a valid action JSON."""


# @register_parser("json_action_parser")
@PluginRegistry.register(namespace="agent.parser", name="json_action_parser")
class JsonActionParser(BaseActionParser):
    """
    General JSON parser
    """

    def __init__(self, **kwargs) -> None:
        super().__init__()

    @staticmethod
    def _wait_seconds_from_args(args: dict, default: float = 2.0) -> float:
        raw = args.get("seconds")
        if raw is None:
            raw = args.get("duration_s")
        if raw is None:
            ms = args.get("duration_ms")
            if ms is not None:
                try:
                    return max(0.5, min(float(ms) / 1000.0, 30.0))
                except (TypeError, ValueError):
                    pass
            return default
        try:
            return max(0.5, min(float(raw), 30.0))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _duration_ms_from_args(args: dict, default: int = 1000) -> int:
        raw = args.get("duration_ms")
        if raw is None:
            raw = args.get("duration")
        if raw is None:
            return default
        try:
            v = int(float(raw))
        except (TypeError, ValueError):
            return default
        return max(300, min(v, 5000))

    def _resolve_tap_xy_to_pixels(
        self,
        x: Any,
        y: Any,
        width: int,
        height: int,
        perception_metadata: dict,
    ) -> Tuple[int, int]:
        """Convert model tap coords to device pixels; denormalize when perception says so."""
        px, py = int(x), int(y)
        if not perception_metadata.get("coordinates_normalized"):
            return px, py
        scale_max = int(perception_metadata.get("coordinate_scale_max", COORDINATE_SCALE_MAX))
        px, py = normalized_coordinate_to_pixel(px, py, width, height, scale_max=scale_max)
        self.logger.debug(
            "Denormalized tap (%s, %s) on 0–%s scale → pixel (%s, %s) for %sx%s",
            x,
            y,
            scale_max,
            px,
            py,
            width,
            height,
        )
        return px, py

    def _resolve_tap_xy(
        self,
        args: dict,
        mode: str,
        width: int,
        height: int,
        perception_metadata: dict,
        perception_elements: list,
        response: str,
        *,
        action_label: str,
    ) -> Union[Tuple[int, int], Action]:
        """Resolve pixel (x, y) for Tap / Long_press from grid, SoM, or raw coordinates."""
        if "grid" in mode:
            area = args.get("area")
            subarea = args.get("subarea", "center")
            rows = perception_metadata.get("rows", 10)
            cols = perception_metadata.get("cols", 5)
            x, y = self.area_to_xy(area, subarea, width, height, rows, cols)
            return (x, y)

        if "set_of_marks" in mode or "som" in mode:
            element_id = self._fuzzy_get(args, ["element_id", "id", "tag", "index"], default=None)
            self.logger.debug(
                "SoM %s: requested element_id=%r type=%s; first indices=%s",
                action_label,
                element_id,
                type(element_id).__name__,
                [e.get("index") for e in perception_elements[:5]],
            )
            if element_id is None:
                return Action(
                    type=ActionType.WAIT,
                    thought=f"Missing 'element_id' for SoM {action_label} action.",
                    metadata={"raw_response": response},
                )
            target = next((e for e in perception_elements if str(e.get("index")) == str(element_id)), None)
            if not target:
                return Action(
                    type=ActionType.WAIT,
                    thought=f"Element ID {element_id} not found in detection results.",
                    metadata={"raw_response": response},
                )
            coords = target.get("coordinates", [0, 0])
            self.logger.debug("SoM id %r -> %s %s", element_id, action_label.lower(), coords)
            return self._resolve_tap_xy_to_pixels(
                coords[0], coords[1], width, height, perception_metadata
            )

        x = args.get("x")
        y = args.get("y")
        try:
            return self._resolve_tap_xy_to_pixels(
                x, y, width, height, perception_metadata
            )
        except (TypeError, ValueError):
            return Action(
                type=ActionType.WAIT,
                thought=f"Missing or invalid x/y for {action_label} in coordinate mode.",
                metadata={"raw_response": response},
            )

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
                self.logger.warning(
                    "no JSON object found in model output (mode=%s); first 120 chars: %r",
                    mode,
                    (response or "")[:120],
                )
                raise ActionParseError("no JSON object found in model output")

            data = json.loads(json_str)

            action_name = self._fuzzy_get(data, ["name", "action", "function", "tool"], default="").lower()
            args = self._fuzzy_get(data, ["arguments", "args", "parameters", "params"], default={})
            thought = self._fuzzy_get(data, ["thought", "thoughts", "reasoning"], default="")

            action_obj = None

            if action_name in ["tap", "click"]:
                xy = self._resolve_tap_xy(
                    args,
                    mode,
                    width,
                    height,
                    perception_metadata,
                    perception_elements,
                    response,
                    action_label="Tap",
                )
                if isinstance(xy, Action):
                    return xy
                x, y = xy
                action_obj = Action(type=ActionType.TAP, params={"x": x, "y": y})

            elif action_name in ["long_press", "longpress"]:
                xy = self._resolve_tap_xy(
                    args,
                    mode,
                    width,
                    height,
                    perception_metadata,
                    perception_elements,
                    response,
                    action_label="Long_press",
                )
                if isinstance(xy, Action):
                    return xy
                x, y = xy
                duration_ms = self._duration_ms_from_args(args)
                action_obj = Action(
                    type=ActionType.LONG_PRESS,
                    params={"x": x, "y": y, "duration_ms": duration_ms},
                )

            elif action_name in ["swipe", "scroll"]:
                action_obj = Action(type=ActionType.SWIPE, params=args)

            elif action_name in ["type", "input"]:
                action_obj = Action(type=ActionType.TEXT, params={"text": args.get("text")})

            elif action_name in ["home", "back", "enter", "clear", "del"]:
                code = "del" if action_name == "clear" else action_name
                action_obj = Action(type=ActionType.KEY, params={"code": code})
            
            elif action_name in ["done", "finish", "complete"]:
                action_obj = Action(type=ActionType.DONE)

            elif action_name in ["wait", "sleep", "pause"]:
                seconds = self._wait_seconds_from_args(args)
                action_obj = Action(type=ActionType.WAIT, params={"seconds": seconds})

            elif action_name in ["start_app", "launch_app", "open_app"]:
                app = self._fuzzy_get(args, ["app", "application", "name"], default="")
                if isinstance(app, str):
                    app = app.strip()
                else:
                    app = str(app).strip() if app is not None else ""
                if not app:
                    action_obj = Action(
                        type=ActionType.WAIT,
                        thought="Missing 'app' in arguments for Start_app.",
                        metadata={"raw_response": response},
                    )
                else:
                    action_obj = Action(type=ActionType.START_APP, params={"app": app})

            else:
                action_obj = Action(type=ActionType.WAIT, thought=f"Unknown action: {action_name}")

            action_obj.thought = thought
            action_obj.metadata = {"raw_response": response}
            return action_obj

        except ActionParseError:
            raise
        except json.JSONDecodeError as e:
            self.logger.error("action parse failed mode=%s: %s", mode, e, exc_info=True)
            raise ActionParseError(str(e)) from e
        except Exception as e:
            self.logger.error("action parse failed mode=%s: %s", mode, e, exc_info=True)
            raise ActionParseError(str(e)) from e
        
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
