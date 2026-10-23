"""Parse literal Aguvis calls; Android gesture rules are explicit adaptations."""

from __future__ import annotations

import ast
import math
import re

from zhixing.components import Action, ActionType
from zhixing.plugins.agent.aguvis_types import AguvisCommand, AguvisDecision
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


def _number(value, minimum: float, maximum: float) -> float:
    """Validate a finite non-boolean number in an explicit unit range.

    Args:
        value: Literal numeric argument.
        minimum: Inclusive lower bound.
        maximum: Inclusive upper bound.
    Raises:
        ValueError: Argument is not a finite in-range number.
    Returns:
        float: Validated value without guessed units.
    """
    if type(value) not in (int, float) or not minimum <= value <= maximum or not math.isfinite(value):
        raise ValueError("invalid numeric argument")
    return float(value)


def _text(value) -> str:
    """Validate bounded literal text without stringifying other types.

    Args:
        value: Expected text argument.
    Raises:
        ValueError: Argument is not bounded text.
    Returns:
        str: Original text, including spaces and escapes.
    """
    if not isinstance(value, str) or len(value) > 8192:
        raise ValueError("invalid text argument")
    return value


def _arguments(call: ast.Call, names: tuple[str, ...], defaults=None) -> dict:
    """Bind only literal positional/named arguments to a fixed signature.

    Args:
        call: Parsed call expression, never executed.
        names: Complete ordered accepted parameter names.
        defaults: Optional literal defaults for omitted arguments.
    Raises:
        ValueError: Unknown, repeated, missing or nonliteral arguments occur.
    Returns:
        dict: Fully bound arguments.
    """
    if len(call.args) > len(names):
        raise ValueError("too many arguments")
    values = dict(defaults or {})
    supplied = set()
    for name, node in zip(names, call.args):
        values[name], supplied = ast.literal_eval(node), supplied | {name}
    for item in call.keywords:
        if item.arg not in names or item.arg in supplied:
            raise ValueError("unknown or repeated argument")
        values[item.arg], supplied = ast.literal_eval(item.value), supplied | {item.arg}
    if set(values) != set(names):
        raise ValueError("missing argument")
    return values


class AguvisActionParser:
    """Map the mobile subset to shared actions; reject unsupported desktop APIs."""

    def __init__(self, max_commands: int = 16, gesture_duration_ms: int = 400,
                 long_press_ms: int = 1000, scroll_pixels_per_click: float | None = None):
        """Set bounded adapter rules absent from the upstream execution code.

        Args:
            max_commands: Maximum commands per model decision.
            gesture_duration_ms: Explicit Android swipe duration.
            long_press_ms: Explicit Android long-press duration.
            scroll_pixels_per_click: Optional desktop-wheel conversion; None rejects clicks units.
        Raises:
            ValueError: A configuration value is invalid.
        Returns:
            None.
        """
        if (type(max_commands) is not int or not 1 <= max_commands <= 32
                or type(gesture_duration_ms) is not int or not 1 <= gesture_duration_ms <= 5000
                or type(long_press_ms) is not int or not 1 <= long_press_ms <= 5000):
            raise ValueError("invalid Aguvis parser configuration")
        if scroll_pixels_per_click is not None:
            _number(scroll_pixels_per_click, 0.001, 1000)
        self.max_commands, self.gesture_duration_ms = max_commands, gesture_duration_ms
        self.long_press_ms, self.scroll_pixels_per_click = long_press_ms, scroll_pixels_per_click

    def parse(self, response: str, metadata: dict, *, step: int = 1,
              low_level_instruction: str | None = None) -> AguvisDecision:
        """Parse one continuation atomically before any command can execute.

        Args:
            response: Decoded continuation, possibly containing monologue/role labels.
            metadata: Positive original screenshot width and height.
            step: One-based model decision number for external history.
            low_level_instruction: Instruction already present in the assistant prefill.
        Raises:
            ActionParseError: Any command, argument or response shape is unsupported.
        Returns:
            AguvisDecision: Ordered typed commands and explicit history description.
        """
        try:
            if not isinstance(response, str) or not 1 <= len(response) <= 32768:
                raise ValueError("invalid response length")
            width, height = metadata["width"], metadata["height"]
            if any(type(value) is not int or not 1 <= value <= 100000 for value in (width, height)):
                raise ValueError("invalid screenshot dimensions")
            cleaned = re.sub(r"(?m)^\s*```(?:python)?\s*$", "", response).strip()
            start = re.search(r"(?m)^\s*(?=(?:pyautogui\.|mobile\.|terminate\s*\(|answer\s*\())", cleaned)
            if start is None:
                raise ValueError("no command block")
            preamble, block = cleaned[:start.start()], cleaned[start.start():]
            if re.search(r"(?m)^\s*[A-Za-z_][A-Za-z0-9_.]*\s*\(", preamble):
                raise ValueError("unexpected call before command block")
            tree = ast.parse(block.strip(), mode="exec")
            if not 1 <= len(tree.body) <= self.max_commands or sum(1 for _ in ast.walk(tree)) > 1024:
                raise ValueError("command bound exceeded")
            commands = []
            for statement in tree.body:
                if not isinstance(statement, ast.Expr) or not isinstance(statement.value, ast.Call):
                    raise ValueError("only literal calls are supported")
                command = self._command(statement.value, width, height)
                if commands and commands[-1].action is not None and commands[-1].action.type in (ActionType.DONE, ActionType.FAIL):
                    raise ValueError("terminal command must be last")
                commands.append(command)
            descriptions = re.findall(r"(?m)^Action:\s*([^\n]+)", preamble)
            description = low_level_instruction or (descriptions[-1].strip() if descriptions else block.strip())
            return AguvisDecision(tuple(commands), description, step)
        except (ValueError, TypeError, KeyError, SyntaxError, RecursionError, OverflowError):
            raise ActionParseError("invalid Aguvis response or unsupported mobile command") from None

    def _command(self, call: ast.Call, width: int, height: int) -> AguvisCommand:
        """Translate a single allowlisted call without executing model code.

        Args:
            call: Literal call AST.
            width: Original screenshot width.
            height: Original screenshot height.
        Raises:
            ValueError: Command or its exact signature is unsupported.
        Returns:
            AguvisCommand: Existing Action or an inert answer.
        """
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name):
            name = call.func.value.id + "." + call.func.attr
        elif isinstance(call.func, ast.Name):
            name = call.func.id
        else:
            raise ValueError("invalid call target")
        action = None
        if name in ("pyautogui.click", "mobile.long_press"):
            values = _arguments(call, ("x", "y"))
            x, y = self._point([values["x"], values["y"]], width, height)
            action = Action(ActionType.TAP if name.endswith("click") else ActionType.LONG_PRESS,
                {"x": x, "y": y, **({"duration_ms": self.long_press_ms} if name == "mobile.long_press" else {})})
        elif name == "mobile.swipe":
            values = _arguments(call, ("from_coord", "to_coord"))
            start, end = (self._point(values[key], width, height) for key in ("from_coord", "to_coord"))
            action = self._swipe(start, end)
        elif name in ("pyautogui.scroll", "pyautogui.hscroll"):
            # Source mobile data uses page fractions. This explicit screen-fraction
            # gesture is our adapter policy, not an unavailable official executor.
            page_form = not call.args and any(item.arg == "page" for item in call.keywords)
            key = "page" if page_form else "clicks"
            values = _arguments(call, (key,))
            amount = _number(values[key], -1e6, 1e6)
            if not amount:
                raise ValueError("zero scroll is not a gesture")
            extent = height if name.endswith(".scroll") else width
            if page_form:
                fraction = _number(amount, -0.8, 0.8)
            elif self.scroll_pixels_per_click is not None:
                fraction = _number(amount * self.scroll_pixels_per_click / extent, -0.8, 0.8)
            else:
                raise ValueError("wheel units require explicit conversion")
            delta = int(fraction * extent)
            if not delta:
                raise ValueError("scroll is smaller than one pixel")
            center_x, center_y = width // 2, height // 2
            if name.endswith(".scroll"):
                start, end = (center_x, center_y - delta // 2), (center_x, center_y + delta - delta // 2)
            else:
                # Positive horizontal wheel scroll reveals the right: finger moves left.
                start, end = (center_x + delta // 2, center_y), (center_x - delta + delta // 2, center_y)
            start = (max(0, min(start[0], width - 1)), max(0, min(start[1], height - 1)))
            end = (max(0, min(end[0], width - 1)), max(0, min(end[1], height - 1)))
            action = self._swipe(start, end)
        elif name == "pyautogui.write":
            key = "text" if any(item.arg == "text" for item in call.keywords) else "message"
            action = Action(ActionType.TEXT, {"text": _text(_arguments(call, (key,))[key])})
        elif name == "pyautogui.press":
            key = _text(_arguments(call, ("keys",))["keys"])
            mapping = {"enter": "enter", "home": "home", "back": "back", "backspace": "KEYCODE_DEL"}
            if key not in mapping:
                raise ValueError("unsupported Android key")
            action = Action(ActionType.KEY, {"code": mapping[key]})
        elif name in ("mobile.home", "mobile.back"):
            _arguments(call, ())
            action = Action(ActionType.KEY, {"code": name.split(".")[1]})
        elif name == "mobile.wait":
            seconds = _number(_arguments(call, ("seconds",))["seconds"], 0.5, 30)
            action = Action(ActionType.WAIT, {"seconds": seconds})
        elif name == "mobile.open_app":
            app = _text(_arguments(call, ("app_name",))["app_name"])
            if not app.strip():
                raise ValueError("empty application name")
            action = Action(ActionType.START_APP, {"app": app})
        elif name in ("terminate", "mobile.terminate"):
            status = _text(_arguments(call, ("status",), {"status": "success"})["status"])
            if status not in ("success", "complete", "failure", "failed", "infeasible", "impossible"):
                raise ValueError("unknown terminal status")
            action = Action(ActionType.DONE if status in ("success", "complete") else ActionType.FAIL,
                            thought=status)
        elif name in ("answer", "mobile.answer"):
            key = "text" if any(item.arg == "text" for item in call.keywords) else "answer"
            return AguvisCommand(answer=_text(_arguments(call, (key,))[key]))
        else:
            raise ValueError("unsupported command")
        return AguvisCommand(action=action)

    @staticmethod
    def _point(value, width: int, height: int) -> tuple[int, int]:
        """Convert explicit normalized coordinates to bounded original pixels.

        Args:
            value: Exactly two finite values in [0, 1].
            width: Positive original width.
            height: Positive original height.
        Raises:
            ValueError: Point shape or coordinate range is invalid.
        Returns:
            tuple[int, int]: Pixels with inclusive 1 mapped to the last pixel.
        """
        if not isinstance(value, (list, tuple)) or len(value) != 2:
            raise ValueError("invalid point")
        return min(int(_number(value[0], 0, 1) * width), width - 1), min(int(_number(value[1], 0, 1) * height), height - 1)

    def _swipe(self, start: tuple[int, int], end: tuple[int, int]) -> Action:
        """Build a precise shared swipe without device effects.

        Args:
            start: Validated start pixel.
            end: Validated end pixel.
        Returns:
            Action: Explicit coordinates and configured duration.
        """
        return Action(ActionType.SWIPE, {"start_x": start[0], "start_y": start[1],
            "end_x": end[0], "end_y": end[1], "duration_ms": self.gesture_duration_ms})
