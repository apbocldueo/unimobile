import json
import re
from typing import Any

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
from zhixing.plugins.agent.perception.coordinates import normalized_coordinate_to_pixel


@PluginRegistry.register(namespace="agent.parser", name="gui_schema_action_parser")
class GuiSchemaActionParser(BaseActionParser):
    """Parse schema-constrained GUI JSON actions with 0-1000 relative coordinates."""

    def parse(self, response: str, metadata: dict) -> Action:
        width = int(metadata.get("width", 0) or 0)
        height = int(metadata.get("height", 0) or 0)
        data = self._parse_json_object(response)

        status = str(data.get("STATUS", "continue")).lower()
        thought = data.get("thought", "")

        if status in {"finish", "satisfied"}:
            return Action(type=ActionType.DONE, thought=thought, metadata={"raw_response": response, "schema_action": data})
        if status in {"impossible", "interrupt", "need_feedback"}:
            return Action(type=ActionType.FAIL, thought=thought or status, metadata={"raw_response": response, "schema_action": data})

        if "PRESS" in data:
            code = str(data["PRESS"]).lower()
            code = {"home": "home", "back": "back", "enter": "enter", "appselect": "home"}.get(code, code)
            return Action(type=ActionType.KEY, params={"code": code}, thought=thought, metadata={"raw_response": response, "schema_action": data})

        if "TYPE" in data:
            action = Action(
                type=ActionType.TEXT,
                params={"text": str(data.get("TYPE", ""))},
                thought=thought,
                metadata={"raw_response": response, "schema_action": data},
            )
            return action

        if "CLEAR" in data:
            return Action(type=ActionType.KEY, params={"code": "del"}, thought=thought, metadata={"raw_response": response, "schema_action": data})

        if "DEEP_LINK" in data:
            return Action(type=ActionType.KEY, params={"code": "home"}, thought=thought or "Open recent app is not supported directly; returning home.", metadata={"raw_response": response, "schema_action": data})

        if "duration" in data and "POINT" not in data and "to" not in data:
            seconds = max(0.5, min(float(data.get("duration", 200)) / 1000.0, 30.0))
            return Action(type=ActionType.WAIT, params={"seconds": seconds}, thought=thought, metadata={"raw_response": response, "schema_action": data})

        if "POINT" in data and "to" in data:
            start_x, start_y = self._point_to_pixel(data["POINT"], width, height)
            target = data.get("to")
            duration_ms = int(data.get("duration", 400) or 400)
            if isinstance(target, str):
                unit = max(80, min(width, height) // 4)
                offsets = {
                    "up": (0, -unit),
                    "down": (0, unit),
                    "left": (-unit, 0),
                    "right": (unit, 0),
                }
                dx, dy = offsets.get(target.lower(), (0, -unit))
                end_x, end_y = start_x + dx, start_y + dy
            else:
                end_x, end_y = self._point_to_pixel(target, width, height)
            return Action(
                type=ActionType.SWIPE,
                params={
                    "start_x": start_x,
                    "start_y": start_y,
                    "end_x": max(0, min(width - 1, end_x)),
                    "end_y": max(0, min(height - 1, end_y)),
                    "duration_ms": duration_ms,
                },
                thought=thought,
                metadata={"raw_response": response, "schema_action": data},
            )

        if "POINT" in data:
            x, y = self._point_to_pixel(data["POINT"], width, height)
            return Action(type=ActionType.TAP, params={"x": x, "y": y}, thought=thought, metadata={"raw_response": response, "schema_action": data})

        raise ActionParseError(f"No executable GUI schema action found: {data}")

    def _parse_json_object(self, response: str) -> dict[str, Any]:
        text = (response or "").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            text = match.group(0)
        try:
            data = json.loads(text)
        except Exception as e:
            raise ActionParseError(f"invalid GUI schema JSON: {e}") from e
        if not isinstance(data, dict):
            raise ActionParseError("GUI schema output is not an object")
        return data

    @staticmethod
    def _point_to_pixel(point: Any, width: int, height: int) -> tuple[int, int]:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ActionParseError(f"invalid POINT: {point}")
        return normalized_coordinate_to_pixel(point[0], point[1], width, height, scale_max=1000)
