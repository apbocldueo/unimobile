import re

from zhixing.core.agent.interfaces import BaseActionParser
from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
from zhixing.plugins.agent.perception.coordinates import normalized_coordinate_to_pixel


@PluginRegistry.register(namespace="agent.parser", name="guicourse_action_parser")
class GUICourseActionParser(BaseActionParser):
    """Parse GUICourse task2action CSV-like outputs.

    Expected examples:
        actions:
        tap, <point> 500 500</point>
        click, <box> 100 100 400 160</box>
        swipe, from <point> 500 800</point> to <point> 500 200</point>
        scroll, down 300 right 0
        input, hello
        enter
        answer, task complete

    GUICourse's related_version1 coordinates are on a 0-1000 scale.
    """

    def parse(self, response: str, metadata: dict) -> Action:
        width = int(metadata.get("width", 0) or 0)
        height = int(metadata.get("height", 0) or 0)
        lines = self._action_lines(response)
        if not lines:
            raise ActionParseError("No GUICourse action lines found")

        errors = []
        for line in lines:
            try:
                action = self._parse_line(line, width, height)
                action.metadata = {"raw_response": response, "guicourse_line": line}
                return action
            except Exception as e:
                errors.append(str(e))

        raise ActionParseError("; ".join(errors) or "No executable GUICourse action found")

    def _action_lines(self, response: str) -> list[str]:
        text = (response or "").strip()
        text = text.replace("```", "").strip()
        if "actions:" in text:
            text = text.split("actions:", 1)[-1]
        elif "## Next Actions" in text:
            text = text.split("## Next Actions", 1)[-1]
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _parse_line(self, line: str, width: int, height: int) -> Action:
        lower = line.lower()
        if lower.startswith(("tap,", "click,", "select,", "hover,")):
            x, y = self._target_to_pixel(line, width, height)
            return Action(type=ActionType.TAP, params={"x": x, "y": y}, thought=f"GUICourse action: {line}")

        if lower.startswith("swipe,") or lower.startswith("select_text,"):
            points = self._extract_points(line)
            if len(points) < 2:
                raise ActionParseError(f"Swipe requires two points: {line}")
            start_x, start_y = self._point_to_pixel(points[0], width, height)
            end_x, end_y = self._point_to_pixel(points[1], width, height)
            return Action(
                type=ActionType.SWIPE,
                params={"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                thought=f"GUICourse action: {line}",
            )

        if lower.startswith("scroll,"):
            start_x, start_y, end_x, end_y = self._scroll_to_swipe(line, width, height)
            return Action(
                type=ActionType.SWIPE,
                params={"start_x": start_x, "start_y": start_y, "end_x": end_x, "end_y": end_y},
                thought=f"GUICourse action: {line}",
            )

        if lower.startswith("input,"):
            text = line.split(",", 1)[1].strip()
            return Action(type=ActionType.TEXT, params={"text": text}, thought=f"GUICourse action: {line}")

        if lower.startswith("enter"):
            return Action(type=ActionType.KEY, params={"code": "enter"}, thought=f"GUICourse action: {line}")

        if lower.startswith("answer,"):
            answer = line.split(",", 1)[1].strip()
            if "task complete" in answer.lower() or "complete" in answer.lower():
                return Action(type=ActionType.DONE, thought=answer)
            return Action(type=ActionType.DONE, thought=answer)

        if lower.startswith("copy"):
            return Action(type=ActionType.KEY, params={"code": "KEYCODE_COPY"}, thought=f"GUICourse action: {line}")

        raise ActionParseError(f"Unknown GUICourse action line: {line}")

    def _target_to_pixel(self, text: str, width: int, height: int) -> tuple[int, int]:
        points = self._extract_points(text)
        if points:
            return self._point_to_pixel(points[0], width, height)
        boxes = self._extract_boxes(text)
        if boxes:
            x1, y1, x2, y2 = boxes[0]
            return self._point_to_pixel(((x1 + x2) / 2, (y1 + y2) / 2), width, height)
        raise ActionParseError(f"No <point> or <box> found: {text}")

    @staticmethod
    def _extract_points(text: str) -> list[tuple[float, float]]:
        points = []
        for match in re.finditer(r"<point>\s*([^<]+?)\s*</point>", text, re.IGNORECASE):
            raw = match.group(1).strip()
            parts = [p for p in re.split(r"[\s,]+", raw) if p]
            if len(parts) < 2:
                continue
            points.append((float(parts[0]), float(parts[1])))
        return points

    @staticmethod
    def _extract_boxes(text: str) -> list[tuple[float, float, float, float]]:
        boxes = []
        for match in re.finditer(r"<box>\s*([^<]+?)\s*</box>", text, re.IGNORECASE):
            raw = match.group(1).strip()
            parts = [p for p in re.split(r"[\s,]+", raw) if p]
            if len(parts) < 4:
                continue
            boxes.append((float(parts[0]), float(parts[1]), float(parts[2]), float(parts[3])))
        return boxes

    def _scroll_to_swipe(self, line: str, width: int, height: int) -> tuple[int, int, int, int]:
        match = re.search(r"down\s+(-?\d+(?:\.\d+)?)\s+right\s+(-?\d+(?:\.\d+)?)", line, re.IGNORECASE)
        if not match:
            raise ActionParseError(f"Invalid GUICourse scroll action: {line}")
        down = float(match.group(1))
        right = float(match.group(2))
        if abs(down) <= 1.0 and abs(right) <= 1.0:
            down *= 1000
            right *= 1000
        if width <= 0 or height <= 0:
            width, height = 1000, 1000
        start_x = width // 2
        start_y = height // 2
        dx = int(round(right / 1000 * width))
        dy = int(round(down / 1000 * height))
        end_x = max(0, min(width - 1, start_x + dx))
        end_y = max(0, min(height - 1, start_y + dy))
        return start_x, start_y, end_x, end_y

    @staticmethod
    def _point_to_pixel(point: tuple[float, float], width: int, height: int) -> tuple[int, int]:
        x, y = point
        if x <= 1.0 and y <= 1.0:
            return (
                max(0, min(width - 1, int(round(x * width)))),
                max(0, min(height - 1, int(round(y * height)))),
            )
        return normalized_coordinate_to_pixel(x, y, width, height, scale_max=1000)
