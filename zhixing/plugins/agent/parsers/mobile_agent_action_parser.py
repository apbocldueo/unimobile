import re

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


@PluginRegistry.register(namespace="agent.parser", name="mobile_agent_action_parser")
class MobileAgentActionParser(BaseActionParser):
    """Parse MobileAgent-style sectioned outputs."""

    def parse(self, response: str, metadata: dict) -> Action:
        thought = self._section(response, "Thought")
        action_text = self._section(response, "Action")
        operation = self._section(response, "Operation")
        if not action_text:
            raise ActionParseError("missing ### Action ### section")

        compact = " ".join(action_text.replace("\n", " ").split())
        lower = compact.lower()

        if lower.startswith("open app"):
            app = self._first_parenthesized(compact)
            action = Action(type=ActionType.START_APP, params={"app": app})
        elif lower.startswith("tap"):
            x, y = self._parse_xy(self._first_parenthesized(compact))
            action = Action(type=ActionType.TAP, params={"x": x, "y": y})
        elif lower.startswith("swipe"):
            match = re.search(r"Swipe\s*\(([^)]*)\)\s*,\s*\(([^)]*)\)", compact, re.IGNORECASE)
            if not match:
                raise ActionParseError(f"invalid Swipe action: {compact}")
            x1, y1 = self._parse_xy(match.group(1))
            x2, y2 = self._parse_xy(match.group(2))
            action = Action(
                type=ActionType.SWIPE,
                params={"start_x": x1, "start_y": y1, "end_x": x2, "end_y": y2},
            )
        elif lower.startswith("type"):
            text = self._first_parenthesized(compact)
            action = Action(type=ActionType.TEXT, params={"text": text})
        elif lower.startswith("back"):
            action = Action(type=ActionType.KEY, params={"code": "back"})
        elif lower.startswith("home"):
            action = Action(type=ActionType.KEY, params={"code": "home"})
        elif lower.startswith("stop"):
            action = Action(type=ActionType.DONE)
        else:
            raise ActionParseError(f"unknown MobileAgent action: {compact}")

        action.thought = thought
        action.metadata = {
            "raw_response": response,
            "operation": operation,
            "mobile_agent_action": compact,
        }
        return action

    @staticmethod
    def _section(text: str, name: str) -> str:
        pattern = rf"###\s*{re.escape(name)}\s*###\s*(.*?)(?=\n###\s*[A-Za-z ]+\s*###|\Z)"
        match = re.search(pattern, text or "", re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return " ".join(match.group(1).strip().split())

    @staticmethod
    def _first_parenthesized(text: str) -> str:
        match = re.search(r"\((.*)\)", text)
        if not match:
            return ""
        value = match.group(1).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    @staticmethod
    def _parse_xy(value: str) -> tuple[int, int]:
        parts = [p.strip() for p in value.split(",")]
        if len(parts) < 2:
            raise ActionParseError(f"invalid coordinate pair: {value}")
        return int(float(parts[0])), int(float(parts[1]))
