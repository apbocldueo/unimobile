from __future__ import annotations

import json
import re
from typing import Any

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


@PluginRegistry.register(namespace="agent.parser", name="os_genesis_action_parser")
class OSGenesisActionParser(BaseActionParser):
    """Parse OS-Genesis low-level thought/action outputs.

    Expected response:
        Low-level thought: ...
        action: {"action_type": "click", "x": 123, "y": 456}
    """

    def parse(self, response: str, metadata: dict) -> Action:
        thought, action_text = self._split_output(response)
        data = self._extract_json(action_text or response)
        action_type = str(data.get("action_type", "")).strip().lower()

        if action_type == "click":
            x, y = self._xy(data)
            action = Action(type=ActionType.TAP, params={"x": x, "y": y}, thought=thought)
        elif action_type == "type":
            x, y = self._xy(data)
            action = Action(
                type=ActionType.TEXT,
                params={"x": x, "y": y, "text": str(data.get("text", "")), "press_enter_after": True},
                thought=thought,
            )
        elif action_type == "long_press":
            x, y = self._xy(data)
            action = Action(type=ActionType.LONG_PRESS, params={"x": x, "y": y}, thought=thought)
        elif action_type == "scroll":
            direction = str(data.get("direction") or "down").strip().lower()
            action = Action(type=ActionType.SWIPE, params={"direction": direction, "dist": "medium"}, thought=thought)
        elif action_type == "navigate_back":
            action = Action(type=ActionType.KEY, params={"code": "back"}, thought=thought)
        elif action_type == "navigate_home":
            action = Action(type=ActionType.KEY, params={"code": "home"}, thought=thought)
        elif action_type == "keyboard_enter":
            action = Action(type=ActionType.KEY, params={"code": "enter"}, thought=thought)
        elif action_type == "wait":
            action = Action(type=ActionType.WAIT, params={"seconds": 2.0}, thought=thought)
        elif action_type == "open_app":
            app = str(data.get("app_name") or data.get("app") or "").strip()
            if not app:
                raise ActionParseError("open_app action missing app_name")
            action = Action(type=ActionType.START_APP, params={"app": app}, thought=thought)
        elif action_type == "status":
            status = str(data.get("goal_status", "")).strip().lower()
            if status in {"successful", "success", "complete", "done"}:
                action = Action(type=ActionType.DONE, thought=thought or status)
            elif status == "infeasible":
                action = Action(type=ActionType.FAIL, thought=thought or status)
            else:
                raise ActionParseError(f"unknown OS-Genesis goal_status: {status}")
        elif action_type == "answer":
            action = Action(type=ActionType.DONE, thought=str(data.get("text") or thought or ""))
        else:
            raise ActionParseError(f"unknown OS-Genesis action_type: {action_type}")

        action.metadata = {"raw_response": response, "os_genesis_action": data}
        return action

    @staticmethod
    def _split_output(response: str) -> tuple[str | None, str | None]:
        text = response or ""
        reason_result = re.search(r"Low-level thought:(.*)action:", text, flags=re.DOTALL | re.IGNORECASE)
        action_result = re.search(r"action:(.*)", text, flags=re.DOTALL | re.IGNORECASE)
        reason = reason_result.group(1).strip() if reason_result else None
        action = action_result.group(1).strip() if action_result else None
        return reason, action

    def _extract_json(self, text: str) -> dict[str, Any]:
        json_str = self._extract_json_object(text)
        if not json_str:
            raise ActionParseError("No JSON action found in OS-Genesis output")
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            raise ActionParseError(f"Invalid OS-Genesis JSON action: {e}") from e
        if not isinstance(data, dict):
            raise ActionParseError("OS-Genesis action JSON is not an object")
        return data

    @staticmethod
    def _extract_json_object(text: str) -> str | None:
        start_idx = (text or "").find("{")
        if start_idx < 0:
            return None
        stack = 0
        for offset, char in enumerate(text[start_idx:]):
            if char == "{":
                stack += 1
            elif char == "}":
                stack -= 1
            if stack == 0:
                return text[start_idx : start_idx + offset + 1]
        return text[start_idx:]

    @staticmethod
    def _xy(data: dict[str, Any]) -> tuple[int, int]:
        try:
            return int(float(data["x"])), int(float(data["y"]))
        except (KeyError, TypeError, ValueError) as e:
            raise ActionParseError(f"OS-Genesis action missing valid x/y: {data}") from e
