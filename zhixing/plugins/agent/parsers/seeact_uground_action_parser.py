from __future__ import annotations

import ast
import json
import re
from typing import Any

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


@PluginRegistry.register(namespace="agent.parser", name="seeact_uground_action_parser")
class SeeActUGroundActionParser(BaseActionParser):
    """Parse SeeAct-V / UGround outputs.

    Expected response:
        Reason: ...
        Action: {"action_type": "click", "element": "..."}

    Element-targeted actions intentionally remain unresolved here. The
    ``uground_agent`` strategy invokes a grounder component after parsing.
    """

    def parse(self, response: str, metadata: dict) -> Action:
        reason, action_text = self._split_reason_action(response)
        data = self._extract_action_json(action_text or response)
        action_type = str(data.get("action_type", "")).strip().lower()

        if action_type == "status":
            status = str(data.get("goal_status", "")).strip().lower()
            if status in {"complete", "done", "success"}:
                return Action(type=ActionType.DONE, thought=reason or "Agent thinks the request has been completed.", metadata={"raw_response": response, "seeact_action": data})
            return Action(type=ActionType.FAIL, thought=reason or status or "Task infeasible", metadata={"raw_response": response, "seeact_action": data})

        if action_type == "answer":
            answer = str(data.get("text", ""))
            return Action(type=ActionType.DONE, thought=answer or reason, metadata={"raw_response": response, "seeact_action": data})

        if action_type in {"click", "double_tap", "long_press"}:
            params, meta = self._target_params(data)
            mapped = ActionType.LONG_PRESS if action_type == "long_press" else ActionType.TAP
            action = Action(type=mapped, params=params, thought=reason, metadata={"raw_response": response, "seeact_action": data, **meta})
            if action_type == "double_tap":
                action.metadata["repeat_tap"] = 2
            return action

        if action_type == "input_text":
            params, meta = self._target_params(data)
            params["text"] = str(data.get("text", ""))
            params["press_enter_after"] = True
            return Action(type=ActionType.TEXT, params=params, thought=reason, metadata={"raw_response": response, "seeact_action": data, **meta})

        if action_type == "keyboard_enter":
            return Action(type=ActionType.KEY, params={"code": "enter"}, thought=reason, metadata={"raw_response": response, "seeact_action": data})

        if action_type == "navigate_home":
            return Action(type=ActionType.KEY, params={"code": "home"}, thought=reason, metadata={"raw_response": response, "seeact_action": data})

        if action_type == "navigate_back":
            return Action(type=ActionType.KEY, params={"code": "back"}, thought=reason, metadata={"raw_response": response, "seeact_action": data})

        if action_type == "open_app":
            app = str(data.get("app_name") or data.get("app") or "").strip()
            if not app:
                raise ActionParseError("open_app action missing app_name")
            return Action(type=ActionType.START_APP, params={"app": app}, thought=reason, metadata={"raw_response": response, "seeact_action": data})

        if action_type == "wait":
            return Action(type=ActionType.WAIT, params={"seconds": 1.0}, thought=reason, metadata={"raw_response": response, "seeact_action": data})

        if action_type in {"scroll", "swipe"}:
            direction = str(data.get("direction") or "down").strip().lower()
            params, meta = self._target_params(data)
            params.update({"direction": direction, "dist": "medium"})
            return Action(type=ActionType.SWIPE, params=params, thought=reason, metadata={"raw_response": response, "seeact_action": data, **meta})

        raise ActionParseError(f"Unknown SeeAct/UGround action_type: {action_type}")

    @staticmethod
    def _split_reason_action(response: str) -> tuple[str | None, str | None]:
        text = response or ""
        reason_result = re.search(r"Reason:(.*)Action:", text, flags=re.DOTALL | re.IGNORECASE)
        action_result = re.search(r"Action:(.*)", text, flags=re.DOTALL | re.IGNORECASE)
        reason = reason_result.group(1).strip() if reason_result else None
        action = action_result.group(1).strip() if action_result else None
        return reason, action

    def _extract_action_json(self, text: str) -> dict[str, Any]:
        json_str = self._extract_json_object(text)
        if not json_str:
            raise ActionParseError("No JSON action found in SeeAct/UGround output")
        try:
            data = ast.literal_eval(json_str)
        except Exception:
            try:
                data = json.loads(json_str)
            except Exception as e:
                raise ActionParseError(f"Invalid SeeAct/UGround JSON action: {e}") from e
        if not isinstance(data, dict):
            raise ActionParseError("SeeAct/UGround action JSON is not an object")
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
    def _target_params(data: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        params: dict[str, Any] = {}
        meta: dict[str, Any] = {}
        if data.get("x") is not None and data.get("y") is not None:
            params["x"] = int(float(data["x"]))
            params["y"] = int(float(data["y"]))
            return params, meta
        element = data.get("element")
        if element:
            meta["needs_grounding"] = True
            meta["grounding_description"] = str(element)
        return params, meta
