import json
import re
from typing import Any

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


@PluginRegistry.register(namespace="agent.parser", name="mobile_use_tool_parser")
class MobileUseToolParser(BaseActionParser):
    """Parse MultiAgent-style ``<tool_call>`` mobile_use actions."""

    ACTION_NAME_MAP = {
        "left_click": "click",
        "point": "coordinate",
        "start_point": "coordinate",
        "start_box": "coordinate",
        "end_point": "coordinate2",
        "end_box": "coordinate2",
        "scroll": "swipe",
        "content": "text",
        "open_app": "open",
    }

    def parse(self, response: str, metadata: dict) -> Action:
        thought = self._extract_prefix_field(response, "Thought")
        action_desc = self._extract_prefix_field(response, "Action")
        tool = self._extract_tool_call(response)

        name = tool.get("name", "")
        args = tool.get("arguments") or {}
        if name and name != "mobile_use":
            raise ActionParseError(f"unsupported tool call: {name}")
        if not isinstance(args, dict):
            raise ActionParseError("tool_call.arguments must be an object")

        raw_action_name = str(args.get("action", "")).strip()
        action_name = self._map_name(raw_action_name).lower()
        params = {self._map_name(k): v for k, v in args.items() if k != "action"}

        action = self._to_action(action_name, params, thought)
        action.metadata.update(
            {
                "raw_response": response,
                "mobile_use_tool_call": tool,
                "operation": action_desc,
                "mobile_use_action": raw_action_name,
            }
        )
        return action

    def _to_action(self, action_name: str, params: dict[str, Any], thought: str) -> Action:
        if action_name == "click":
            x, y = self._xy(params.get("coordinate"))
            return Action(type=ActionType.TAP, params={"x": x, "y": y}, thought=thought)

        if action_name == "long_press":
            x, y = self._xy(params.get("coordinate"))
            duration_ms = int(float(params.get("time", 2.0)) * 1000)
            return Action(
                type=ActionType.LONG_PRESS,
                params={"x": x, "y": y, "duration_ms": duration_ms},
                thought=thought,
            )

        if action_name == "swipe":
            x1, y1 = self._xy(params.get("coordinate"))
            x2, y2 = self._xy(params.get("coordinate2"))
            return Action(
                type=ActionType.SWIPE,
                params={"start_x": x1, "start_y": y1, "end_x": x2, "end_y": y2},
                thought=thought,
            )

        if action_name == "type":
            return Action(type=ActionType.TEXT, params={"text": str(params.get("text", ""))}, thought=thought)

        if action_name == "clear_text":
            return Action(type=ActionType.KEY, params={"code": "del"}, thought=thought)

        if action_name == "key":
            return Action(type=ActionType.KEY, params={"code": str(params.get("text", "")).lower()}, thought=thought)

        if action_name == "system_button":
            button = str(params.get("button", "")).lower()
            code = {"back": "back", "home": "home", "enter": "enter", "menu": "menu"}.get(button, button)
            return Action(type=ActionType.KEY, params={"code": code}, thought=thought)

        if action_name == "open":
            return Action(type=ActionType.START_APP, params={"app": str(params.get("text", ""))}, thought=thought)

        if action_name == "wait":
            seconds = float(params.get("time", 2.0))
            return Action(type=ActionType.WAIT, params={"seconds": seconds}, thought=thought)

        if action_name == "take_note":
            note = str(params.get("text", "")).strip()
            return Action(
                type=ActionType.WAIT,
                params={"seconds": 0.5},
                thought=thought or f"Take note: {note}",
                metadata={"take_note": note},
            )

        if action_name == "answer":
            answer = str(params.get("text", "")).strip()
            return Action(type=ActionType.DONE, thought=answer or thought)

        if action_name == "terminate":
            status = str(params.get("status", "success")).lower()
            if status == "success":
                return Action(type=ActionType.DONE, thought=thought or "Task completed")
            return Action(type=ActionType.FAIL, thought=thought or "Task failed")

        raise ActionParseError(f"unknown mobile_use action: {action_name}")

    def _extract_tool_call(self, response: str) -> dict[str, Any]:
        text = response or ""
        match = re.search(r"<tool_call>\s*(.*?)\s*</tool_call>", text, re.DOTALL)
        if match:
            text = match.group(1).strip()
        else:
            match = re.search(r"\{\s*\"name\"\s*:\s*\"mobile_use\".*\}", text, re.DOTALL)
            if match:
                text = match.group(0)
        try:
            data = json.loads(text)
        except Exception as e:
            raise ActionParseError(f"invalid mobile_use tool call JSON: {e}") from e
        if not isinstance(data, dict):
            raise ActionParseError("mobile_use tool call is not an object")
        return data

    @staticmethod
    def _extract_prefix_field(response: str, field: str) -> str:
        match = re.search(rf"{re.escape(field)}:\s*(.*?)(?=\n[A-Z][A-Za-z ]*:|<tool_call>|\Z)", response or "", re.DOTALL)
        return " ".join(match.group(1).strip().split()) if match else ""

    @classmethod
    def _map_name(cls, name: str) -> str:
        return cls.ACTION_NAME_MAP.get(str(name), str(name))

    @staticmethod
    def _xy(value: Any) -> tuple[int, int]:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            raise ActionParseError(f"invalid coordinate: {value}")
        return int(round(float(value[0]))), int(round(float(value[1])))
