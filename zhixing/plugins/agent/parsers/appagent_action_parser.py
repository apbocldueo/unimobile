import re
from typing import Any

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError, JsonActionParser


@PluginRegistry.register(namespace="agent.parser", name="appagent_action_parser")
class AppAgentActionParser(BaseActionParser):
    """Parse AppAgent-style two-line action outputs.

    Expected format:
        Action: tap(3)
        Summary: tapped the search box

    In grid mode:
        Action: tap(12, "center")
        Action: swipe(12, "center", 18, "center")
    """

    def parse(self, response: str, metadata: dict) -> Action:
        mode = metadata.get("mode", "")
        width = int(metadata.get("width", 0) or 0)
        height = int(metadata.get("height", 0) or 0)
        perception_metadata = metadata.get("perception_metadata", {})
        elements = metadata.get("elements", [])

        action_text = self._extract_line(response, "Action")
        summary = self._extract_line(response, "Summary") or ""
        if not action_text:
            raise ActionParseError("missing Action line")

        action_text = action_text.strip()
        if "FINISH" in action_text.upper():
            return self._with_common_metadata(Action(type=ActionType.DONE, thought=summary), response, summary)

        action_name = action_text.split("(", 1)[0].strip().lower()

        if action_name == "grid":
            return self._with_common_metadata(
                Action(
                    type=ActionType.WAIT,
                    params={"seconds": 0.5},
                    thought=summary or "Switch to grid perception for precise targeting.",
                ),
                response,
                summary,
                next_perception_name="grid_perception",
            )

        if "grid" in mode:
            action = self._parse_grid_action(action_name, action_text, width, height, perception_metadata, summary)
        else:
            action = self._parse_labeled_action(action_name, action_text, elements, summary)

        return self._with_common_metadata(action, response, summary)

    def _parse_labeled_action(
        self,
        action_name: str,
        action_text: str,
        elements: list[dict[str, Any]],
        summary: str,
    ) -> Action:
        if action_name == "tap":
            area = self._single_int_arg(action_text)
            x, y = self._element_center(elements, area)
            return Action(type=ActionType.TAP, params={"x": x, "y": y}, thought=summary)

        if action_name == "long_press":
            area = self._single_int_arg(action_text)
            x, y = self._element_center(elements, area)
            return Action(type=ActionType.LONG_PRESS, params={"x": x, "y": y}, thought=summary)

        if action_name == "text":
            text = self._single_string_arg(action_text)
            return Action(type=ActionType.TEXT, params={"text": text}, thought=summary)

        if action_name == "swipe":
            params = self._split_args(action_text)
            if len(params) < 3:
                raise ActionParseError("swipe requires area, direction, dist")
            area = int(params[0])
            direction = self._strip_quotes(params[1]).lower()
            dist = self._strip_quotes(params[2]).lower()
            x, y = self._element_center(elements, area)
            return Action(
                type=ActionType.SWIPE,
                params={"x": x, "y": y, "direction": direction, "dist": dist},
                thought=summary,
            )

        raise ActionParseError(f"unknown AppAgent action: {action_name}")

    def _parse_grid_action(
        self,
        action_name: str,
        action_text: str,
        width: int,
        height: int,
        perception_metadata: dict,
        summary: str,
    ) -> Action:
        rows = int(perception_metadata.get("rows", 10) or 10)
        cols = int(perception_metadata.get("cols", 5) or 5)
        params = self._split_args(action_text)

        if action_name == "tap":
            area = int(params[0])
            subarea = self._strip_quotes(params[1]) if len(params) > 1 else "center"
            x, y = JsonActionParser.area_to_xy(area, subarea, width, height, rows, cols)
            return Action(
                type=ActionType.TAP,
                params={"x": x, "y": y},
                thought=summary,
                metadata={"next_perception_index": 0},
            )

        if action_name == "long_press":
            area = int(params[0])
            subarea = self._strip_quotes(params[1]) if len(params) > 1 else "center"
            x, y = JsonActionParser.area_to_xy(area, subarea, width, height, rows, cols)
            return Action(
                type=ActionType.LONG_PRESS,
                params={"x": x, "y": y},
                thought=summary,
                metadata={"next_perception_index": 0},
            )

        if action_name == "swipe":
            if len(params) < 4:
                raise ActionParseError("grid swipe requires start_area, start_subarea, end_area, end_subarea")
            start_x, start_y = JsonActionParser.area_to_xy(
                int(params[0]), self._strip_quotes(params[1]), width, height, rows, cols
            )
            end_x, end_y = JsonActionParser.area_to_xy(
                int(params[2]), self._strip_quotes(params[3]), width, height, rows, cols
            )
            return Action(
                type=ActionType.SWIPE,
                params={"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                thought=summary,
                metadata={"next_perception_index": 0},
            )

        if action_name == "grid":
            return Action(type=ActionType.WAIT, params={"seconds": 0.5}, thought=summary)

        raise ActionParseError(f"unknown grid action: {action_name}")

    def _with_common_metadata(
        self,
        action: Action,
        response: str,
        summary: str,
        **metadata: Any,
    ) -> Action:
        existing = dict(action.metadata or {})
        existing.update({"raw_response": response, "summary": summary})
        existing.update(metadata)
        action.metadata = existing
        return action

    @staticmethod
    def _extract_line(response: str, key: str) -> str:
        match = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", response or "", re.MULTILINE)
        return match.group(1) if match else ""

    @staticmethod
    def _split_args(action_text: str) -> list[str]:
        match = re.search(r"\((.*)\)", action_text)
        if not match:
            return []
        raw = match.group(1)
        parts = []
        buf = ""
        quote = None
        for char in raw:
            if char in {"'", '"'}:
                quote = None if quote == char else char
                buf += char
            elif char == "," and quote is None:
                parts.append(buf.strip())
                buf = ""
            else:
                buf += char
        if buf.strip():
            parts.append(buf.strip())
        return parts

    def _single_int_arg(self, action_text: str) -> int:
        params = self._split_args(action_text)
        if not params:
            raise ActionParseError(f"missing numeric argument in {action_text}")
        return int(params[0])

    def _single_string_arg(self, action_text: str) -> str:
        params = self._split_args(action_text)
        if not params:
            raise ActionParseError(f"missing string argument in {action_text}")
        return self._strip_quotes(params[0])

    @staticmethod
    def _strip_quotes(value: str) -> str:
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            return value[1:-1]
        return value

    @staticmethod
    def _element_center(elements: list[dict[str, Any]], area: int) -> tuple[int, int]:
        target = next((elem for elem in elements if int(elem.get("index", -1)) == area), None)
        if not target:
            raise ActionParseError(f"element tag {area} not found")
        coords = target.get("coordinates") or [0, 0]
        return int(coords[0]), int(coords[1])
