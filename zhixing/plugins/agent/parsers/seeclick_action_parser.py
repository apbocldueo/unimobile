"""Map SeeClick-AITW numeric decisions to existing portable actions."""

from __future__ import annotations

import ast
import math

from zhixing.core.agent.protocol import Action, ActionType
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


HISTORY_KEY = "seeclick.history"
MAX_RESPONSE_CHARS = 32768

# These are (x, y) vectors from upstream pred_2_format, before its scorer-only
# conversion to (y, x). Avoid backend-dependent scroll direction names.
_SWIPES = {
    0: ((0.5, 0.8), (0.5, 0.2)),
    1: ((0.5, 0.2), (0.5, 0.8)),
    8: ((0.2, 0.5), (0.8, 0.5)),
    9: ((0.8, 0.5), (0.2, 0.5)),
}


def _point(point: object, width: int, height: int) -> tuple[int, int]:
    """Convert an explicit normalized point without guessing its coordinate scale.

    Args:
        point: Two finite coordinates in [0, 1], in x/y order.
        width: Positive screenshot width.
        height: Positive screenshot height.
    Raises:
        ValueError: Coordinates or screenshot dimensions are invalid.
    Returns:
        tuple[int, int]: Pixel coordinates clipped only at the inclusive 1 edge.
    """
    if any(type(size) is not int or size <= 0 for size in (width, height)):
        raise ValueError("positive integer screenshot dimensions required")
    if not isinstance(point, (tuple, list)) or len(point) != 2:
        raise ValueError("click_point requires exactly two coordinates")
    if any(type(value) not in (int, float) or not math.isfinite(value)
           or not 0 <= value <= 1 for value in point):
        raise ValueError("coordinates must be finite numbers in [0, 1]")
    return min(width - 1, round(point[0] * width)), min(height - 1, round(point[1] * height))


@PluginRegistry.register(namespace="agent.parser", name="seeclick_action_parser")
class SeeClickActionParser:
    """Accept the upstream Python-literal dictionary protocol, including tuples."""

    def parse(self, response: str, metadata: dict) -> Action:
        """Validate a mobile decision and preserve its exact history representation.

        Args:
            response: One original model response; no executable expressions.
            metadata: Current screenshot width and height for spatial actions.
        Raises:
            ActionParseError: A response is malformed, oversized or unsupported.
        Returns:
            Action: Existing TAP/TEXT/SWIPE/KEY/DONE/FAIL with source metadata.
        """
        try:
            if not isinstance(response, str) or not 0 < len(response) <= MAX_RESPONSE_CHARS:
                raise ValueError("response size")
            data = ast.literal_eval(response.strip())
            if not isinstance(data, dict) or type(data.get("action_type")) is not int:
                raise ValueError("integer action_type required")
            identifier = data["action_type"]
            if identifier == 4:
                x, y = _point(data.get("click_point"), metadata.get("width"), metadata.get("height"))
                action = Action(ActionType.TAP, {"x": x, "y": y})
            elif identifier == 3:
                text = data.get("typed_text")
                if not isinstance(text, str) or len(text) > 4096 or "\x00" in text:
                    raise ValueError("bounded typed_text required")
                # AITW TYPE neither focuses a field nor submits it. Lowercasing
                # in upstream pred_2_format belongs only to offline scoring.
                action = Action(ActionType.TEXT, {"text": text})
            elif identifier in _SWIPES:
                start, end = _SWIPES[identifier]
                width, height = metadata.get("width"), metadata.get("height")
                x1, y1 = _point(start, width, height)
                x2, y2 = _point(end, width, height)
                action = Action(ActionType.SWIPE, {"start_x": x1, "start_y": y1,
                                "end_x": x2, "end_y": y2, "duration_ms": 400})
            elif identifier in (5, 6, 7):
                action = Action(ActionType.KEY, {"code": {5: "back", 6: "home", 7: "enter"}[identifier]})
            elif identifier in (10, 11):
                action = Action(ActionType.DONE if identifier == 10 else ActionType.FAIL)
            else:
                # 2 is a web SELECT operation, not an Android action.
                raise ValueError("unsupported mobile action_type")
            action.thought = f"SeeClick action_type={identifier}"
            action.metadata = {HISTORY_KEY: response, "raw_response": response,
                               "seeclick.action_type": identifier}
            return action
        except (ValueError, TypeError, SyntaxError, RecursionError, OverflowError) as error:
            # Never echo model text into failure diagnostics or turn it into DONE.
            raise ActionParseError("invalid SeeClick-AITW decision") from error
