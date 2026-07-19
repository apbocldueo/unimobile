import ast
import json
import re
from typing import Any

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


@PluginRegistry.register(namespace="agent.parser", name="showui_action_parser")
class ShowUIActionParser(BaseActionParser):
    """Parse ShowUI action dictionaries with 0-1 relative coordinates."""

    def parse(self, response: str, metadata: dict) -> Action:
        width = int(metadata.get("width", 0) or 0)
        height = int(metadata.get("height", 0) or 0)
        data = self._parse_dict(response)

        action_name = str(data.get("action", "")).strip().upper()
        value = data.get("value")
        position = data.get("position")

        if action_name in {"TAP", "CLICK", "SELECT", "HOVER"}:
            x, y = self._relative_point_to_pixel(position, width, height)
            action = Action(type=ActionType.TAP, params={"x": x, "y": y})
        elif action_name in {"INPUT", "TYPE"}:
            params = {"text": "" if value is None else str(value)}
            if isinstance(position, list) and len(position) >= 2:
                x, y = self._relative_point_to_pixel(position, width, height)
                params.update({"x": x, "y": y})
            action = Action(type=ActionType.TEXT, params=params)
        elif action_name == "SWIPE":
            if self._is_two_point_position(position):
                start_x, start_y = self._relative_point_to_pixel(position[0], width, height)
                end_x, end_y = self._relative_point_to_pixel(position[1], width, height)
                action = Action(
                    type=ActionType.SWIPE,
                    params={"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                )
            else:
                direction = str(value or "up").lower()
                action = Action(type=ActionType.SWIPE, params={"direction": direction, "dist": "medium"})
        elif action_name.startswith("SCROLL"):
            direction = action_name.replace("SCROLL", "").strip().lower() or str(value or "up").lower()
            action = Action(type=ActionType.SWIPE, params={"direction": direction, "dist": "medium"})
        elif action_name in {"ENTER", "PRESS ENTER"}:
            action = Action(type=ActionType.KEY, params={"code": "enter"})
        elif action_name in {"PRESS BACK", "BACK"}:
            action = Action(type=ActionType.KEY, params={"code": "back"})
        elif action_name in {"PRESS HOME", "HOME"}:
            action = Action(type=ActionType.KEY, params={"code": "home"})
        elif action_name in {"ANSWER", "STATUS TASK COMPLETE"}:
            answer = "" if value is None else str(value)
            action = Action(type=ActionType.DONE, thought=answer)
        elif action_name in {"STATUS TASK IMPOSSIBLE", "IMPOSSIBLE"}:
            answer = "" if value is None else str(value)
            action = Action(type=ActionType.FAIL, thought=answer or "Task impossible")
        else:
            raise ActionParseError(f"unknown ShowUI action: {action_name}")

        if not action.thought:
            action.thought = f"ShowUI action: {action_name}"
        action.metadata = {"raw_response": response, "showui_action": data}
        return action

    def _parse_dict(self, response: str) -> dict[str, Any]:
        text = (response or "").strip()
        text = text.replace("```json", "").replace("```python", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            data = ast.literal_eval(text)
        except Exception:
            try:
                data = json.loads(text)
            except Exception as e:
                raise ActionParseError(f"invalid ShowUI action dictionary: {e}") from e
        if not isinstance(data, dict):
            raise ActionParseError("ShowUI output is not a dictionary")
        return data

    @staticmethod
    def _relative_point_to_pixel(point: Any, width: int, height: int) -> tuple[int, int]:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ActionParseError(f"invalid relative point: {point}")
        x = float(point[0])
        y = float(point[1])
        if x <= 1.0 and y <= 1.0:
            x *= width
            y *= height
        return (
            max(0, min(max(width - 1, 0), int(round(x)))),
            max(0, min(max(height - 1, 0), int(round(y)))),
        )

    @staticmethod
    def _is_two_point_position(position: Any) -> bool:
        return (
            isinstance(position, (list, tuple))
            and len(position) >= 2
            and isinstance(position[0], (list, tuple))
            and isinstance(position[1], (list, tuple))
        )
