# Copyright 2026 The android_world Authors.
# Licensed under the Apache License, Version 2.0 (see the distribution LICENSE).
# Derived from google-research/android_world, commit f8e78c0ab0bb8b5daa681afd0296ed0193a98f1f.
# See source-origin.json for selected definitions and the original file hashes.
"""Pinned M3A algorithms, without an Agent loop or device/model imports.

Only docstrings, the second JSON extractor name, and lazy OpenCV imports differ.
"""
from __future__ import annotations
import ast
import dataclasses
import json
import math
import re
from types import SimpleNamespace
from typing import Any, Optional

@dataclasses.dataclass
class BoundingBox:
    """Class for representing a bounding box."""
    x_min: float | int
    x_max: float | int
    y_min: float | int
    y_max: float | int

    @property
    def center(self) -> tuple[float, float]:
        """Gets center of bounding box.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        return ((self.x_min + self.x_max) / 2.0, (self.y_min + self.y_max) / 2.0)

    @property
    def width(self) -> float | int:
        """Gets width of bounding box.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        return self.x_max - self.x_min

    @property
    def height(self) -> float | int:
        """Gets height of bounding box.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        return self.y_max - self.y_min

    @property
    def area(self) -> float | int:
        """area follows the pinned AndroidWorld algorithm.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        return self.width * self.height

@dataclasses.dataclass
class UIElement:
    """Represents a UI element."""
    text: Optional[str] = None
    content_description: Optional[str] = None
    class_name: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    bbox_pixels: Optional[BoundingBox] = None
    hint_text: Optional[str] = None
    is_checked: Optional[bool] = None
    is_checkable: Optional[bool] = None
    is_clickable: Optional[bool] = None
    is_editable: Optional[bool] = None
    is_enabled: Optional[bool] = None
    is_focused: Optional[bool] = None
    is_focusable: Optional[bool] = None
    is_long_clickable: Optional[bool] = None
    is_scrollable: Optional[bool] = None
    is_selected: Optional[bool] = None
    is_visible: Optional[bool] = None
    package_name: Optional[str] = None
    resource_name: Optional[str] = None
    tooltip: Optional[str] = None
    resource_id: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None

_JSON_SEPARATORS = (',', ':')

ANSWER = 'answer'

CLICK = 'click'

DOUBLE_TAP = 'double_tap'

INPUT_TEXT = 'input_text'

KEYBOARD_ENTER = 'keyboard_enter'

LONG_PRESS = 'long_press'

NAVIGATE_BACK = 'navigate_back'

NAVIGATE_HOME = 'navigate_home'

OPEN_APP = 'open_app'

SCROLL = 'scroll'

STATUS = 'status'

SWIPE = 'swipe'

UNKNOWN = 'unknown'

WAIT = 'wait'

_ACTION_TYPES = (CLICK, DOUBLE_TAP, SCROLL, SWIPE, INPUT_TEXT, NAVIGATE_HOME, NAVIGATE_BACK, KEYBOARD_ENTER, OPEN_APP, STATUS, WAIT, LONG_PRESS, ANSWER, UNKNOWN)

_SCROLL_DIRECTIONS = ('left', 'right', 'down', 'up')

@dataclasses.dataclass()
class JSONAction:
    """Represents a parsed JSON action.

  # Example
  result_json = {'action_type': 'click', 'x': %d, 'y': %d}
  action = JSONAction(**result_json)

  Attributes:
    action_type: The action type.
    index: The index to click, if action is a click. Either an index or a <x, y>
      should be provided. See x, y attributes below.
    x: The x position to click, if the action is a click.
    y: The y position to click, if the action is a click.
    text: The text to type, if action is type.
    direction: The direction to scroll, if action is scroll.
    goal_status: If the status is a 'status' type, indicates the status of the
      goal.
    app_name: The app name to launch, if the action type is 'open_app'.
    keycode: Keycode actions are necessary for an agent to interact with complex
      UI elements (like large textareas) that can't be accessed or controlled by
      simply taping, ensuring precise control over navigation and selection in
      the interface.
    clear_text: Whether to clear the text field before typing.
  """
    action_type: Optional[str] = None
    index: Optional[str | int] = None
    x: Optional[int] = None
    y: Optional[int] = None
    text: Optional[str] = None
    direction: Optional[str] = None
    goal_status: Optional[str] = None
    app_name: Optional[str] = None
    keycode: Optional[str] = None
    clear_text: Optional[bool] = None

    def __post_init__(self):
        """__post_init__ follows the pinned AndroidWorld algorithm.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        if self.action_type not in _ACTION_TYPES:
            raise ValueError(f'Invalid action type: {self.action_type}')
        if self.index is not None:
            self.index = int(self.index)
            if self.x is not None or self.y is not None:
                raise ValueError('Either an index or a <x, y> should be provided.')
        if self.direction and self.direction not in _SCROLL_DIRECTIONS:
            raise ValueError(f'Invalid scroll direction: {self.direction}')
        if self.text is not None and (not isinstance(self.text, str)):
            self.text = str(self.text)
        if self.keycode is not None and (not self.keycode.startswith('KEYCODE_')):
            raise ValueError(f'Invalid keycode: {self.keycode}')

    def __repr__(self) -> str:
        """__repr__ follows the pinned AndroidWorld algorithm.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        properties = []
        for (key, value) in self.as_dict(skip_none=True).items():
            if isinstance(value, float):
                value = f'{value:.3f}'
            properties.append(f'{key}={value!r}')
        return f"JSONAction({', '.join(properties)})"

    def __eq__(self, other):
        """__eq__ follows the pinned AndroidWorld algorithm.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        if isinstance(other, JSONAction):
            return _compare_actions(self, other)
        return False

    def __ne__(self, other):
        """__ne__ follows the pinned AndroidWorld algorithm.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        return not self.__eq__(other)

    def as_dict(self, skip_none: bool=True) -> dict[str, Any]:
        """Returns a dict representation of the action.

Args:
  skip_none: Whether to skip none values.

Returns:
  A dict representation of the action.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
        non_null = {}
        for (key, value) in self.__dict__.items():
            if value is not None:
                if skip_none and value is None:
                    continue
                non_null[key] = value
        return non_null

    def json_str(self) -> str:
        """json_str follows the pinned AndroidWorld algorithm.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
        non_null = self.as_dict(skip_none=True)
        return json.dumps(non_null, separators=_JSON_SEPARATORS)

def _compare_actions(a: JSONAction, b: JSONAction) -> bool:
    """Compares two JSONActions.

Args:
  a: The first action.
  b: The second action.

Returns:
  If the actions are equal.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    if a.app_name is not None and b.app_name is not None:
        app_name_match = a.app_name.lower() == b.app_name.lower()
    else:
        app_name_match = a.app_name == b.app_name
    if a.text is not None and b.text is not None:
        text_match = a.text.lower() == b.text.lower()
    else:
        text_match = a.text == b.text
    return app_name_match and text_match and (a.action_type == b.action_type) and (a.index == b.index) and (a.x == b.x) and (a.y == b.y) and (a.keycode == b.keycode) and (a.direction == b.direction) and (a.goal_status == b.goal_status)

TRIGGER_SAFETY_CLASSIFIER = 'Triggered LLM safety classifier.'

def _logical_to_physical(logical_coordinates: tuple[int, int], logical_screen_size: tuple[int, int], physical_frame_boundary: tuple[int, int, int, int], orientation: int) -> tuple[int, int]:
    """Convert logical coordinates to physical coordinates.

Args:
  logical_coordinates: The logical coordinates for the point.
  logical_screen_size: The logical screen size.
  physical_frame_boundary: The physical coordinates in portrait orientation
    for the upper left and lower right corner for the frame.
  orientation: The current screen orientation.

Returns:
  The physical coordinate for the point in portrait orientation.

Raises:
  ValueError: If the orientation is not valid.

"""
    (x, y) = logical_coordinates
    (px0, py0, px1, py1) = physical_frame_boundary
    (px, py) = (px1 - px0, py1 - py0)
    (lx, ly) = logical_screen_size
    if orientation == 0:
        return (int(x * px / lx) + px0, int(y * py / ly) + py0)
    if orientation == 1:
        return (px - int(y * px / ly) + px0, int(x * py / lx) + py0)
    if orientation == 2:
        return (px - int(x * px / lx) + px0, py - int(y * py / ly) + py0)
    if orientation == 3:
        return (int(y * px / ly) + px0, py - int(x * py / lx) + py0)
    print('Invalid orientation.')
    raise ValueError('Unsupported orientation.')

def _ui_element_logical_corner(ui_element: representation_utils.UIElement, orientation: int) -> list[tuple[int, int]]:
    """Get logical coordinates for corners of a given UI element.

Args:
  ui_element: The corresponding UI element.
  orientation: The current orientation.

Returns:
  Logical coordinates for upper left and lower right corner for the UI
  element.

Raises:
  ValueError: If bounding box is missing.
  ValueError: If orientation is not valid.

"""
    if ui_element.bbox_pixels is None:
        raise ValueError('UI element does not have bounding box.')
    if orientation == 0:
        return [(int(ui_element.bbox_pixels.x_min), int(ui_element.bbox_pixels.y_min)), (int(ui_element.bbox_pixels.x_max), int(ui_element.bbox_pixels.y_max))]
    if orientation == 1:
        return [(int(ui_element.bbox_pixels.x_min), int(ui_element.bbox_pixels.y_max)), (int(ui_element.bbox_pixels.x_max), int(ui_element.bbox_pixels.y_min))]
    if orientation == 2:
        return [(int(ui_element.bbox_pixels.x_max), int(ui_element.bbox_pixels.y_max)), (int(ui_element.bbox_pixels.x_min), int(ui_element.bbox_pixels.y_min))]
    if orientation == 3:
        return [(int(ui_element.bbox_pixels.x_max), int(ui_element.bbox_pixels.y_min)), (int(ui_element.bbox_pixels.x_min), int(ui_element.bbox_pixels.y_max))]
    raise ValueError('Unsupported orientation.')

def get_ui_element_bbox_pixels(ui_element: representation_utils.UIElement, logical_screen_size: tuple[int, int], physical_frame_boundary: tuple[int, int, int, int], orientation: int) -> representation_utils.BoundingBox | None:
    """Get bounding box in physical coordinates for a given UI element.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
    if ui_element.bbox_pixels:
        (upper_left_logical, lower_right_logical) = _ui_element_logical_corner(ui_element, orientation)
        upper_left_physical = _logical_to_physical(upper_left_logical, logical_screen_size, physical_frame_boundary, orientation)
        lower_right_physical = _logical_to_physical(lower_right_logical, logical_screen_size, physical_frame_boundary, orientation)
        return representation_utils.BoundingBox(x_min=upper_left_physical[0], y_min=upper_left_physical[1], x_max=lower_right_physical[0], y_max=lower_right_physical[1])
    else:
        return None

def add_ui_element_mark(screenshot: np.ndarray, ui_element: representation_utils.UIElement, index: int | str, logical_screen_size: tuple[int, int], physical_frame_boundary: tuple[int, int, int, int], orientation: int):
    """Add mark (a bounding box plus index) for a UI element in the screenshot.

Args:
  screenshot: The screenshot as a numpy ndarray.
  ui_element: The UI element to be marked.
  index: The index for the UI element.
  logical_screen_size: The logical screen size.
  physical_frame_boundary: The physical coordinates in portrait orientation
    for the upper left and lower right corner for the frame.
  orientation: The current screen orientation.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
    import cv2
    if ui_element.bbox_pixels:
        (upper_left_logical, lower_right_logical) = _ui_element_logical_corner(ui_element, orientation)
        upper_left_physical = _logical_to_physical(upper_left_logical, logical_screen_size, physical_frame_boundary, orientation)
        lower_right_physical = _logical_to_physical(lower_right_logical, logical_screen_size, physical_frame_boundary, orientation)
        x_scale = screenshot.shape[1] / physical_frame_boundary[2]
        y_scale = screenshot.shape[0] / physical_frame_boundary[3]
        iso_scale = math.sqrt(x_scale * x_scale + y_scale * y_scale)
        upper_left_physical = (int(upper_left_physical[0] * x_scale), int(upper_left_physical[1] * y_scale))
        lower_right_physical = (int(lower_right_physical[0] * x_scale), int(lower_right_physical[1] * y_scale))
        cv2.rectangle(screenshot, upper_left_physical, lower_right_physical, color=(0, 255, 0), thickness=int(2 * iso_scale))
        screenshot[upper_left_physical[1] + int(1 * y_scale):upper_left_physical[1] + int(25 * y_scale), upper_left_physical[0] + int(1 * x_scale):upper_left_physical[0] + int(35 * x_scale), :] = (255, 255, 255)
        cv2.putText(screenshot, str(index), (upper_left_physical[0] + int(1 * x_scale), upper_left_physical[1] + int(20 * y_scale)), cv2.FONT_HERSHEY_SIMPLEX, 0.7 * iso_scale, (0, 0, 0), thickness=int(2 * iso_scale))

def add_screenshot_label(screenshot: np.ndarray, label: str):
    """Add a text label to the right bottom of the screenshot.

Args:
  screenshot: The screenshot as a numpy ndarray.
  label: The text label to add, just a single word.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
    import cv2
    (height, width, _) = screenshot.shape
    screenshot[height - 30:height, width - 150:width, :] = (255, 255, 255)
    cv2.putText(screenshot, label, (width - 120, height - 5), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 0), thickness=2)

def parse_reason_action_output(raw_reason_action_output: str) -> tuple[Optional[str], Optional[str]]:
    """Parses llm action reason output.

Args:
  raw_reason_action_output: Raw string output that supposes to have the format
    'Reason: xxx\\nAction:xxx'.

Returns:
  If parsing successfully, returns reason and action.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    reason_result = re.search('Reason:(.*)Action:', raw_reason_action_output, flags=re.DOTALL)
    reason = reason_result.group(1).strip() if reason_result else None
    action_result = re.search('Action:(.*)', raw_reason_action_output, flags=re.DOTALL)
    action = action_result.group(1).strip() if action_result else None
    if action:
        extracted = extract_json(action)
        if extracted is not None:
            action = json.dumps(extracted)
    return (reason, action)

def extract_json(s: str) -> Optional[dict[str, Any]]:
    """Extracts JSON from string.

Args:
  s: A string with a JSON in it. E.g., "{'hello': 'world'}" or from CoT:
    "let's think step-by-step, ..., {'hello': 'world'}".

Returns:
  JSON object.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    pattern = '\\{.*?\\}'
    match = re.search(pattern, s, re.DOTALL)
    if match:
        try:
            return ast.literal_eval(match.group())
        except (SyntaxError, ValueError) as error:
            print(f'Cannot extract JSON, skipping due to error {error}')
            return None
    else:
        print(f'No JSON match in {s}')
        return None

def validate_ui_element(ui_element: representation_utils.UIElement, screen_width_height_px: tuple[int, int]) -> bool:
    """Used to filter out invalid UI element.

Args:
    Parameters: See the annotated signature and class attributes.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable.

Returns:
    The source-defined result, or None for in-place operations."""
    (screen_width, screen_height) = screen_width_height_px
    if not ui_element.is_visible:
        return False
    if ui_element.bbox_pixels:
        x_min = ui_element.bbox_pixels.x_min
        x_max = ui_element.bbox_pixels.x_max
        y_min = ui_element.bbox_pixels.y_min
        y_max = ui_element.bbox_pixels.y_max
        if x_min >= x_max or x_min >= screen_width or x_max <= 0 or (y_min >= y_max) or (y_min >= screen_height) or (y_max <= 0):
            return False
    return True

def extract_action_json(s: str) -> dict[str, Any] | None:
    """Extracts JSON from string.

Tries conversion with ast and json modules.

Args:
  s: A string with a JSON in it. E.g., "{'hello': 'world'}" or from CoT:
    "let's think step-by-step, ..., {'hello': 'world'}".

Returns:
  JSON object.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    pattern = '\\{.*?\\}'
    match = re.search(pattern, s)
    if match:
        try:
            return ast.literal_eval(match.group())
        except (SyntaxError, ValueError) as error:
            try:
                return json.loads(match.group())
            except (SyntaxError, ValueError) as error2:
                print('Cannot extract JSON, skipping due to errors %s and %s', error, error2)
                return None
    else:
        return None

PROMPT_PREFIX = 'You are an agent who can operate an Android phone on behalf of a user. Based on user\'s goal/request, you may\n- Answer back if the request/goal is a question (or a chat message), like user asks "What is my schedule for today?".\n- Complete some tasks described in the requests/goals by performing actions (step by step) on the phone.\n\nWhen given a user request, you will try to complete it step by step. At each step, you will be given the current screenshot (including the original screenshot and the same screenshot with bounding boxes and numeric indexes added to some UI elements) and a history of what you have done (in text). Based on these pieces of information and the goal, you must choose to perform one of the action in the following list (action description followed by the JSON format) by outputing the action in the correct JSON format.\n- If you think the task has been completed, finish the task by using the status action with complete as goal_status: `{{"action_type": "status", "goal_status": "complete"}}`\n- If you think the task is not feasible (including cases like you don\'t have enough information or can not perform some necessary actions), finish by using the `status` action with infeasible as goal_status: `{{"action_type": "status", "goal_status": "infeasible"}}`\n- Answer user\'s question: `{{"action_type": "answer", "text": "<answer_text>"}}`\n- Click/tap on an element on the screen. We have added marks (bounding boxes with numeric indexes on their TOP LEFT corner) to most of the UI elements in the screenshot, use the numeric index to indicate which element you want to click: `{{"action_type": "click", "index": <target_index>}}`.\n- Long press on an element on the screen, similar with the click action above, use the numeric label on the bounding box to indicate which element you want to long press: `{{"action_type": "long_press", "index": <target_index>}}`.\n- Type text into a text field (this action contains clicking the text field, typing in the text and pressing the enter, so no need to click on the target field to start), use the numeric label on the bounding box to indicate the target text field: `{{"action_type": "input_text", "text": <text_input>, "index": <target_index>}}`\n- Press the Enter key: `{{"action_type": "keyboard_enter"}}`\n- Navigate to the home screen: `{{"action_type": "navigate_home"}}`\n- Navigate back: `{{"action_type": "navigate_back"}}`\n- Scroll the screen or a scrollable UI element in one of the four directions, use the same numeric index as above if you want to scroll a specific UI element, leave it empty when scroll the whole screen: `{{"action_type": "scroll", "direction": <up, down, left, right>, "index": <optional_target_index>}}`\n- Open an app (nothing will happen if the app is not installed): `{{"action_type": "open_app", "app_name": <name>}}`\n- Wait for the screen to update: `{{"action_type": "wait"}}`\n'

GUIDANCE = 'Here are some useful guidelines you need to follow:\nGeneral:\n- Usually there will be multiple ways to complete a task, pick the easiest one. Also when something does not work as expected (due to various reasons), sometimes a simple retry can solve the problem, but if it doesn\'t (you can see that from the history), SWITCH to other solutions.\n- Sometimes you may need to navigate the phone to gather information needed to complete the task, for example if user asks "what is my schedule tomorrow", then you may want to open the calendar app (using the `open_app` action), look up information there, answer user\'s question (using the `answer` action) and finish (using the `status` action with complete as goal_status).\n- For requests that are questions (or chat messages), remember to use the `answer` action to reply to user explicitly before finish! Merely displaying the answer on the screen is NOT sufficient (unless the goal is something like "show me ...").\n- If the desired state is already achieved (e.g., enabling Wi-Fi when it\'s already on), you can just complete the task.\nAction Related:\n- Use the `open_app` action whenever you want to open an app (nothing will happen if the app is not installed), do not use the app drawer to open an app unless all other ways have failed.\n- Use the `input_text` action whenever you want to type something (including password) instead of clicking characters on the keyboard one by one. Sometimes there is some default text in the text field you want to type in, remember to delete them before typing.\n- For `click`, `long_press` and `input_text`, the index parameter you pick must be VISIBLE in the screenshot and also in the UI element list given to you (some elements in the list may NOT be visible on the screen so you can not interact with them).\n- Consider exploring the screen by using the `scroll` action with different directions to reveal additional content.\n- The direction parameter for the `scroll` action can be confusing sometimes as it\'s opposite to swipe, for example, to view content at the bottom, the `scroll` direction should be set to "down". It has been observed that you have difficulties in choosing the correct direction, so if one does not work, try the opposite as well.\nText Related Operations:\n- Normally to select certain text on the screen: <i> Enter text selection mode by long pressing the area where the text is, then some of the words near the long press point will be selected (highlighted with two pointers indicating the range) and usually a text selection bar will also appear with options like `copy`, `paste`, `select all`, etc. <ii> Select the exact text you need. Usually the text selected from the previous step is NOT the one you want, you need to adjust the range by dragging the two pointers. If you want to select all text in the text field, simply click the `select all` button in the bar.\n- At this point, you don\'t have the ability to drag something around the screen, so in general you can not select arbitrary text.\n- To delete some text: the most traditional way is to place the cursor at the right place and use the backspace button in the keyboard to delete the characters one by one (can long press the backspace to accelerate if there are many to delete). Another approach is to first select the text you want to delete, then click the backspace button in the keyboard.\n- To copy some text: first select the exact text you want to copy, which usually also brings up the text selection bar, then click the `copy` button in bar.\n- To paste text into a text box, first long press the text box, then usually the text selection bar will appear with a `paste` button in it.\n- When typing into a text field, sometimes an auto-complete dropdown list will appear. This usually indicating this is a enum field and you should try to select the best match by clicking the corresponding one in the list.\n'

ACTION_SELECTION_PROMPT_TEMPLATE = PROMPT_PREFIX + '\nThe current user goal/request is: {goal}\n\nHere is a history of what you have done so far:\n{history}\n\nThe current screenshot and the same screenshot with bounding boxes and labels added are also given to you.\nHere is a list of detailed information for some of the UI elements (notice that some elements in this list may not be visible in the current screen and so you can not interact with it, can try to scroll the screen to reveal it first), the numeric indexes are consistent with the ones in the labeled screenshot:\n{ui_elements}\n' + GUIDANCE + '{additional_guidelines}' + '\nNow output an action from the above list in the correct JSON format, following the reason why you do that. Your answer should look like:\nReason: ...\nAction: {{"action_type":...}}\n\nYour Answer:\n'

SUMMARY_PROMPT_TEMPLATE = PROMPT_PREFIX + '\nThe (overall) user goal/request is: {goal}\nNow I want you to summerize the latest step.\nYou will be given the screenshot before you performed the action (which has a text label "before" on the bottom right), the action you chose (together with the reason) and the screenshot after the action was performed (which has a text label "after" on the bottom right).\nAlso here is the list of detailed information for some UI elements in the before screenshot:\n{before_elements}\nHere is the list for the after screenshot:\n{after_elements}\nThis is the action you picked: {action}\nBased on the reason: {reason}\n\nBy comparing the two screenshots (plus the UI element lists) and the action performed, give a brief summary of this step. This summary will be added to action history and used in future action selection, so try to include essential information you think that will be most useful for future action selections like what you intended to do, why, if it worked as expected, if not what might be the reason (be critical, the action/reason might be wrong), what should/should not be done next and so on. Some more rules/tips you should follow:\n- Keep it short (better less than 50 words) and in a single line\n- Some actions (like `answer`, `wait`) don\'t involve screen change, you can just assume they work as expected.\n- Given this summary will be added into action history, it can be used as memory to include information that needs to be remembered, or shared between different apps.\n\nSummary of this step: '

def _generate_ui_element_description(ui_element: representation_utils.UIElement, index: int) -> str:
    """Generate a description for a given UI element with important information.

Args:
  ui_element: UI elements for the current screen.
  index: The numeric index for the UI element.

Returns:
  The description for the UI element.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    element_description = f'UI element {index}: {{"index": {index}, '
    if ui_element.text:
        element_description += f'"text": "{ui_element.text}", '
    if ui_element.content_description:
        element_description += f'"content_description": "{ui_element.content_description}", '
    if ui_element.hint_text:
        element_description += f'"hint_text": "{ui_element.hint_text}", '
    if ui_element.tooltip:
        element_description += f'"tooltip": "{ui_element.tooltip}", '
    element_description += f""""is_clickable": {('True' if ui_element.is_clickable else 'False')}, """
    element_description += f""""is_long_clickable": {('True' if ui_element.is_long_clickable else 'False')}, """
    element_description += f""""is_editable": {('True' if ui_element.is_editable else 'False')}, """
    if ui_element.is_scrollable:
        element_description += '"is_scrollable": True, '
    if ui_element.is_focusable:
        element_description += '"is_focusable": True, '
    element_description += f""""is_selected": {('True' if ui_element.is_selected else 'False')}, """
    element_description += f""""is_checked": {('True' if ui_element.is_checked else 'False')}, """
    return element_description[:-2] + '}'

def _generate_ui_elements_description_list(ui_elements: list[representation_utils.UIElement], screen_width_height_px: tuple[int, int]) -> str:
    """Generate concise information for a list of UIElement.

Args:
  ui_elements: UI elements for the current screen.
  screen_width_height_px: The height and width of the screen in pixels.

Returns:
  Concise information for each UIElement.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    tree_info = ''
    for (index, ui_element) in enumerate(ui_elements):
        if m3a_utils.validate_ui_element(ui_element, screen_width_height_px):
            tree_info += _generate_ui_element_description(ui_element, index) + '\n'
    return tree_info

def _action_selection_prompt(goal: str, history: list[str], ui_elements: str, additional_guidelines: list[str] | None=None) -> str:
    """Generate the prompt for the action selection.

Args:
  goal: The current goal.
  history: Summaries for previous steps.
  ui_elements: A list of descriptions for the UI elements.
  additional_guidelines: Task specific guidelines.

Returns:
  The text prompt for action selection that will be sent to gpt4v.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    if history:
        history = '\n'.join(history)
    else:
        history = 'You just started, no action has been performed yet.'
    extra_guidelines = ''
    if additional_guidelines:
        extra_guidelines = 'For The Current Task:\n'
        for guideline in additional_guidelines:
            extra_guidelines += f'- {guideline}\n'
    return ACTION_SELECTION_PROMPT_TEMPLATE.format(goal=goal, history=history, ui_elements=ui_elements if ui_elements else 'Not available', additional_guidelines=extra_guidelines)

def _summarize_prompt(action: str, reason: str, goal: str, before_elements: str, after_elements: str) -> str:
    """Generate the prompt for the summarization step.

Args:
  action: Action picked.
  reason: The reason to pick the action.
  goal: The overall goal.
  before_elements: Information for UI elements on the before screenshot.
  after_elements: Information for UI elements on the after screenshot.

Returns:
  The text prompt for summarization that will be sent to gpt4v.

Raises:
    Exception: Invalid source input or a required drawing dependency is unavailable."""
    return SUMMARY_PROMPT_TEMPLATE.format(goal=goal, before_elements=before_elements, after_elements=after_elements, action=action, reason=reason)

representation_utils = SimpleNamespace(BoundingBox=BoundingBox, UIElement=UIElement)
m3a_utils = SimpleNamespace(validate_ui_element=validate_ui_element)
