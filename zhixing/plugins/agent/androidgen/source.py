# Derived from THUDM/AndroidGen, commit 3f511cff18a842e6583ac7e7d9cabd217c5d3b1b.
# Apache-2.0; see LICENSE and source-origin.json for provenance and compatibility changes.
"""Pinned UI/action algorithms; no Agent loop, optional imports or implicit ADB."""
import inspect
import re
from functools import partial
from types import SimpleNamespace

from zhixing.plugins.agent.m3a.source import JSONAction

json_action = SimpleNamespace(JSONAction=JSONAction)

class Env:
    """Source function protocol, with services held only at the execution boundary."""

    def __init__(self, env, adb, observe):
        """Bind services without invoking them.

        Args:
            env: Explicit execute_action/close boundary.
            adb: Explicit system/popen/activity-resolution boundary.
            observe: Scoped observation callback for source code using get_current_state.
        Returns:
            None.
        """
        self.env, self.adb, self.observe = env, adb, observe
        self.current_return = None
        self.init_state = None

    def get_current_state(self):
        """Delegate source observation through the explicit boundary.

        Raises:
            Exception: Capturing or encoding fails.
        Returns:
            tuple: Source state and record.
        """
        return self.observe()

    def close(self):
        """Delegate explicit source close to the environment owner.

        Raises:
            Exception: Environment cleanup fails.
        Returns:
            None.
        """
        self.env.close()

    def _validate_ui_element(self, ui_element, screen_width_height_px: tuple[int, int]) -> bool:
        """Pinned AndroidGen _validate_ui_element operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
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

    def _format_element(self, ui_element, index):
        """Pinned AndroidGen _format_element operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        if ui_element.class_name:
            _class = f''' class="{ui_element.class_name.split('.')[-1]}"'''
        else:
            _class = ''
        text = ui_element.text
        if text is None:
            text = ui_element.content_description
        if text is None:
            text = ''
        if ui_element.tooltip:
            tooltip = f' tooltip="{ui_element.tooltip}"'
        else:
            tooltip = ''
        if ui_element.resource_name:
            if 'inputmethod' in ui_element.resource_name:
                return None
            resource_name = f' resource-name="{ui_element.resource_name}"'
        else:
            resource_name = ''
        attribute = ''
        if ui_element.is_clickable:
            attribute += ' clickable'
        if ui_element.is_checkable:
            attribute += ' checkable'
            if ui_element.is_checked:
                attribute += ' status="on"'
            else:
                attribute += ' status="off"'
        if ui_element.is_editable:
            attribute += ' editable'
        return f'<element id="{index}"{_class}{tooltip}{resource_name}{attribute}> {text} </element>'

    def _generate_ui_elements_description_list_full(self, ui_elements, screen_width_height_px: tuple[int, int]) -> str:
        """Pinned AndroidGen _generate_ui_elements_description_list_full operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        tree_info = ''
        for (index, ui_element) in enumerate(ui_elements):
            if self._validate_ui_element(ui_element, screen_width_height_px):
                formated_element = self._format_element(ui_element, index)
                if formated_element:
                    tree_info += formated_element + '\n'
        return tree_info.strip()

    def get_current_app(self):
        """Pinned AndroidGen get_current_app operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        cmd = "adb shell dumpsys window | grep mCurrentFocus | awk -F '/' '{print $1}' | awk '{print $NF}'"
        activity = self.adb.popen(cmd).read().strip()
        if activity == 'com.google.android.apps.nexuslauncher':
            return 'Home'
        for (app_name, pattern) in self.adb.patterns.items():
            if type(pattern) == list:
                pattern = pattern[0]
            if activity.lower() in pattern.lower():
                return app_name.split('|')[0]
        return activity

    def _get_class_methods(self, include_dunder=False, exclude_inherited=True):
        """Pinned AndroidGen _get_class_methods operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        methods_dict = {}
        cls = self.__class__
        for (name, method) in inspect.getmembers(cls, predicate=inspect.isfunction):
            if exclude_inherited and method.__qualname__.split('.')[0] != cls.__name__:
                continue
            if not include_dunder and name.startswith('__'):
                continue
            methods_dict[name] = partial(method, self)
        return methods_dict

    def interact(self, code_snippet):
        """Pinned AndroidGen interact operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        self.current_return = None
        local_context = self._get_class_methods()
        local_context.update(**{'self': self})
        try:
            exec(code_snippet, {}, local_context)
        except Exception as e:
            self.current_return = {'operation': 'fail', 'kwargs': {'message': 'Some error happened in previous action.'}}
        return self.current_return

    def open_app(self, app_name):
        """Pinned AndroidGen open_app operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        activity = self.adb.get_adb_activity(app_name)
        if activity is None:
            message = f'App name "{app_name}" can not be found.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        converted_action = json_action.JSONAction(action_type='open_app', app_name=app_name.strip())
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'open_app', 'kwargs': {'app_name': app_name}}

    def do(self, action=None, element_id=None, text=None, direction=None):
        """Pinned AndroidGen do operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        if element_id is not None:
            try:
                tmp = int(element_id)
            except:
                message = f'Element id "{element_id}" is not a number. Please check the element id and try again.'
                self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
                return
        if action == 'Click':
            self.click(element_id)
        elif action == 'Long Press':
            self.long_press(element_id)
        elif action == 'Input Text':
            self.input_text(text, element_id)
        elif action == 'Press Enter':
            self.press_enter()
        elif action == 'Navigate Home':
            self.navigate_home()
        elif action == 'Navigate Back':
            self.navigate_back()
        elif action == 'Scroll':
            self.scroll(direction, element_id)
        elif action == 'Swipe':
            self.swipe(direction, element_id)
        elif action == 'Wait':
            self.wait()
        else:
            raise NotImplementedError()

    def quote(self, content):
        """Pinned AndroidGen quote operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        if content == '':
            message = f'The content to quote can not be empty. Please input some content and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        self.current_return = {'operation': 'quote', 'kwargs': {'content': content}}

    def exit(self, message=None):
        """Pinned AndroidGen exit operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        if message is not None:
            converted_action = json_action.JSONAction(action_type='answer', text=message)
            self.env.execute_action(converted_action)
        self.current_return = {'operation': 'exit', 'kwargs': {'message': message}}

    def click(self, element_id):
        """Pinned AndroidGen click operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='click', index=element_id)
        try:
            self.env.execute_action(converted_action)
        except:
            message = f'Element id "{element_id}" not found in the current page. Read the current page carefully and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        self.current_return = {'operation': 'do', 'action': 'Click', 'kwargs': {'element_id': element_id}}

    def long_press(self, element_id):
        """Pinned AndroidGen long_press operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='long_press', index=element_id)
        try:
            self.env.execute_action(converted_action)
        except:
            message = f'Element id "{element_id}" not found in the current page. Read the current page carefully and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        self.current_return = {'operation': 'do', 'action': 'Long_press', 'kwargs': {'element_id': element_id}}

    def _adb_input(self, text):
        """Pinned AndroidGen _adb_input operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        for char in text:
            if char == '\n':
                self.adb.system('adb shell input keyevent 66')
            elif char == ' ':
                self.adb.system('adb shell input keyevent 62')
            elif char == "'":
                self.adb.system('adb shell input keyevent 75')
            else:
                if char == '"':
                    char = '\\"'
                elif char == '#':
                    char = '\\#'
                elif char == '?':
                    char = '\\?'
                self.adb.system(f"adb shell input text '{char}'")

    def input_text(self, text, element_id):
        """Pinned AndroidGen input_text operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='click', index=element_id)
        try:
            self.env.execute_action(converted_action)
        except:
            message = f'Element id "{element_id}" not found in the current page. Read the current page carefully and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        if text == '':
            message = f'The text to input can not be empty. Please input some text and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        cmd = f'adb shell input keyevent --press $(for i in {{1..100}}; do echo -n "67 "; done)'
        self.adb.system(cmd)
        cmd = f'adb shell input keyevent --press $(for i in {{1..100}}; do echo -n "112 "; done)'
        self.adb.system(cmd)
        self._adb_input(text)
        self.current_return = {'operation': 'do', 'action': 'Input_text', 'kwargs': {'text': text, 'element_id': element_id}}

    def navigate_home(self):
        """Pinned AndroidGen navigate_home operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='navigate_home')
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'do', 'action': 'Navigate Home'}

    def navigate_back(self):
        """Pinned AndroidGen navigate_back operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='navigate_back')
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'do', 'action': 'Navigate Back'}

    def press_enter(self):
        """Pinned AndroidGen press_enter operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='keyboard_enter')
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'do', 'action': 'Press Enter'}

    def scroll(self, direction, element_id=None):
        """Pinned AndroidGen scroll operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        if direction not in ['up', 'down', 'left', 'right']:
            message = f'Invalid scroll direction "{direction}". Please check the direction and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        converted_action = json_action.JSONAction(action_type='scroll', direction=direction, index=element_id)
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'do', 'action': 'Scroll', 'kwargs': {'direction': direction, 'element_id': element_id}}

    def swipe(self, direction, element_id=None):
        """Pinned AndroidGen swipe operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        if direction not in ['up', 'down', 'left', 'right']:
            message = f'Invalid swipe direction "{direction}". Please check the direction and try again.'
            self.current_return = {'operation': 'fail', 'kwargs': {'message': message}}
            return
        if direction == 'up':
            _dir = 'down'
        elif direction == 'down':
            _dir = 'up'
        elif direction == 'left':
            _dir = 'right'
        elif direction == 'right':
            _dir = 'left'
        converted_action = json_action.JSONAction(action_type='scroll', direction=_dir, index=element_id)
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'do', 'action': 'Swipe', 'kwargs': {'direction': direction, 'element_id': element_id}}

    def wait(self):
        """Pinned AndroidGen wait operation with explicit device I/O.

    Args:
        Parameters: Original signature; self binds the caller's environment and ADB boundary.
    Raises:
        Exception: Source input or I/O fails outside the original recoverable guards.
    Returns:
        Original result, or None for methods setting current_return."""
        converted_action = json_action.JSONAction(action_type='wait')
        self.env.execute_action(converted_action)
        self.current_return = {'operation': 'do', 'action': 'Wait'}

def get_code_snippet(content):
    """Extract the first original fenced code block.

    Args:
        content: Raw model output.
    Raises:
        RuntimeError: No fenced block matches the original expression.
    Returns:
        str: Unmodified first code block.
    """
    code = re.search(r'```.*?\n([\s\S]+?)\n```', content)
    if code is None:
        raise RuntimeError()
    code = code.group(1)
    return code
