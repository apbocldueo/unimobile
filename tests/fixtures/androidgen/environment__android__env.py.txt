from android_world.env import env_launcher
import json
import os
import inspect
import time
import asyncio
from functools import partial
from android_world.env import adb_utils
from android_world.env.adb_utils import _PATTERN_TO_ACTIVITY, get_adb_activity
from android_world.agents import m3a_utils
from android_world.env import json_action
from PIL import Image

class Env:
    def __init__(self, config=None, env=None):
        if env is not None:
            self.env = env
        else:
            current_dir = os.path.dirname(__file__)
            if config is None:
                config = json.load(open(f'{current_dir}/config.json'))
                
            self.env = env_launcher.load_and_setup_env(
                console_port=config["CONSOLE_PORT"],
                emulator_setup=config["EMULATOR_SETUP"],
                adb_path=config["ADB_PATH"]
            )
            env_launcher.verify_api_level(self.env)
            self.env.reset(go_home=True)
            
            if config["APP"]:
                adb_utils.launch_app(config["APP"], self.env.base_env)
        
        # disable virtual keyboard
        os.system("adb shell pm disable-user com.google.android.inputmethod.latin")
        os.system("adb shell pm disable-user com.google.android.tts")
        
        self.init_state = self.get_current_app()
        self.current_return = None
        
    def close(self):
        self.env.close()
    
    def _validate_ui_element(
        self,
        ui_element,
        screen_width_height_px: tuple[int, int],
    ) -> bool:
        screen_width, screen_height = screen_width_height_px

        # Filters out invisible element.
        if not ui_element.is_visible:
            return False

        # Filters out element with invalid bounding box.
        if ui_element.bbox_pixels:
            x_min = ui_element.bbox_pixels.x_min
            x_max = ui_element.bbox_pixels.x_max
            y_min = ui_element.bbox_pixels.y_min
            y_max = ui_element.bbox_pixels.y_max

            if (
                x_min >= x_max
                or x_min >= screen_width
                or x_max <= 0
                or y_min >= y_max
                or y_min >= screen_height
                or y_max <= 0
            ):
                return False

        return True
    
    def _format_element(self, ui_element, index):
        if ui_element.class_name:
            _class = f" class=\"{ui_element.class_name.split('.')[-1]}\""
        else:
            _class = ''
        
        text = ui_element.text
        if text is None:
            text = ui_element.content_description
        if text is None:
            text = ''
        
        if ui_element.tooltip:
            tooltip = f' tooltip="{tooltip}"'
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
    
    def _generate_ui_elements_description_list_full(
        self,
        ui_elements,
        screen_width_height_px: tuple[int, int],
    ) -> str:
        """Generate description for a list of UIElement using full information.

        Args:
            ui_elements: UI elements for the current screen.
            screen_width_height_px: Logical screen size.

        Returns:
            Information for each UIElement.
        """
        tree_info = ''
        for index, ui_element in enumerate(ui_elements):
            if self._validate_ui_element(ui_element, screen_width_height_px):
                formated_element = self._format_element(ui_element, index)
                if formated_element:
                    tree_info += formated_element + '\n'
        
        return tree_info.strip()
    
    def get_current_app(self):
        cmd = "adb shell dumpsys window | grep mCurrentFocus | awk -F '/' '{print $1}' | awk '{print $NF}'"
        activity = os.popen(cmd).read().strip()
        
        if activity == 'com.google.android.apps.nexuslauncher':
            return 'Home'
        
        for app_name, pattern in _PATTERN_TO_ACTIVITY.items():
            if type(pattern) == list:
                pattern = pattern[0]
            if activity.lower() in pattern.lower():
                return app_name.split('|')[0]
            
        return activity
    
    def get_current_state(self):
        current_dir = os.path.dirname(__file__)
        state = self.env.get_state(wait_to_stabilize=True)
        logical_screen_size = self.env.logical_screen_size
        
        ui_elements = state.ui_elements
        element_list = self._generate_ui_elements_description_list_full(
            ui_elements,
            logical_screen_size,
        )
        
        orientation = adb_utils.get_orientation(self.env.base_env)
        physical_frame_boundary = adb_utils.get_physical_frame_boundary(
            self.env.base_env
        )
        
        raw_screenshot = state.pixels
        
        cache_dir = os.path.join(current_dir, "cache")
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        # save raw screenshot
        Image.fromarray(raw_screenshot).save(os.path.join(current_dir, "cache", "screenshot_raw.png"))
        
        marked = raw_screenshot.copy()
        for index, ui_element in enumerate(ui_elements):
            if m3a_utils.validate_ui_element(ui_element, logical_screen_size):
                m3a_utils.add_ui_element_mark(
                    marked,
                    ui_element,
                    index,
                    logical_screen_size,
                    physical_frame_boundary,
                    orientation,
                )
        # save marked screenshot
        Image.fromarray(marked).save(os.path.join(current_dir, "cache", "marked.png"))
        
        record = {
            "env": "android",
            "app": self.get_current_app(),
            "image": f"{current_dir}/cache/marked.png",
            "raw": f"{current_dir}/cache/screenshot_raw.png",
            "state": element_list
        }
        
        image_env = {
            "image_url": record['image'],
            "text": f"App Name: {record['app']}. The image is the current device screenshot."
        }
        
        text_env = {
            "text": f"App Name: {record['app']}\nThe state of the current app: {record['state']}"
        }
        
        enviroment = {
            "image": image_env,
            "text": text_env
        }
            
        return enviroment, record
        
    def _get_class_methods(self, include_dunder=False, exclude_inherited=True):
        """
        Returns a dictionary of {method_name: method_object} for all methods in the given class.

        Parameters:
        - cls: The class object to inspect.
        - include_dunder (bool): Whether to include dunder (double underscore) methods.
        - exclude_inherited (bool): Whether to exclude methods inherited from parent classes.
        """
        methods_dict = {}
        cls = self.__class__
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if exclude_inherited and method.__qualname__.split('.')[0] != cls.__name__:
                continue
            if not include_dunder and name.startswith('__'):
                continue
            methods_dict[name] = partial(method, self)
        return methods_dict
    
    def interact(self, code_snippet):
        self.current_return = None

        local_context = self._get_class_methods()
        local_context.update(**{'self': self})
        try:
            exec(code_snippet, {}, local_context)
        except Exception as e:
            self.current_return = {"operation": "fail", "kwargs": {"message": 'Some error happened in previous action.'}}

        return self.current_return
    
    def open_app(self, app_name):
        activity = get_adb_activity(app_name)
        if activity is None:
            message = f'App name \"{app_name}\" can not be found.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        converted_action = json_action.JSONAction(
            action_type="open_app",
            app_name=app_name.strip()
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "open_app", "kwargs": {"app_name": app_name}}

    def do(self, action=None, element_id=None, text=None, direction=None):
        if element_id is not None:
            try:
                tmp = int(element_id)
            except:
                message = f'Element id \"{element_id}\" is not a number. Please check the element id and try again.'
                self.current_return = {"operation": "fail", "kwargs": {"message": message}}
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
        if content == '':
            message = f'The content to quote can not be empty. Please input some content and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        self.current_return = {"operation": "quote", "kwargs": {"content": content}}

    def exit(self, message=None):
        if message is not None:
            converted_action = json_action.JSONAction(
                action_type="answer",
                text=message
            )
            self.env.execute_action(converted_action)
        
        self.current_return = {"operation": "exit", "kwargs": {"message": message}}
    
    # Implement sub-actions of do
    def click(self, element_id):
        converted_action = json_action.JSONAction(
            action_type="click",
            index=element_id
        )
        try:
            self.env.execute_action(converted_action)
        except:
            message = f'Element id \"{element_id}\" not found in the current page. Read the current page carefully and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        self.current_return = {"operation": "do", "action": 'Click', "kwargs": {"element_id": element_id}}

    def long_press(self, element_id):
        converted_action = json_action.JSONAction(
            action_type="long_press",
            index=element_id
        )
        try:
            self.env.execute_action(converted_action)
        except:
            message = f'Element id \"{element_id}\" not found in the current page. Read the current page carefully and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        self.current_return = {"operation": "do", "action": 'Long_press', "kwargs": {"element_id": element_id}}
        
    def _adb_input(self, text):
        for char in text:
            if char == '\n':
                os.system('adb shell input keyevent 66')
            elif char == ' ':
                os.system('adb shell input keyevent 62')
            elif char == '\'':
                os.system('adb shell input keyevent 75')
            else:
                if char == '"':
                    char = '\\"'
                elif char == '#':
                    char = '\\#'
                elif char == '?':
                    char = '\\?'
                os.system(f"adb shell input text '{char}'")
                
    def input_text(self, text, element_id):
        converted_action = json_action.JSONAction(
            action_type="click",
            index=element_id
        )
        try:
            self.env.execute_action(converted_action)
        except:
            message = f'Element id \"{element_id}\" not found in the current page. Read the current page carefully and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        
        if text == '':
            message = f'The text to input can not be empty. Please input some text and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        
        # delete the previous text
        cmd = f'adb shell input keyevent --press $(for i in {{1..100}}; do echo -n "67 "; done)'
        os.system(cmd)
        
        # delete the after text
        cmd = f'adb shell input keyevent --press $(for i in {{1..100}}; do echo -n "112 "; done)'
        os.system(cmd)
        
        # input text
        self._adb_input(text)
        
        self.current_return = {"operation": "do", "action": 'Input_text', "kwargs": {"text": text, "element_id": element_id}}

    def navigate_home(self):
        converted_action = json_action.JSONAction(
            action_type="navigate_home"
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "do", "action": 'Navigate Home'}
        
    def navigate_back(self):
        converted_action = json_action.JSONAction(
            action_type="navigate_back",
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "do", "action": 'Navigate Back'}

    def press_enter(self):
        converted_action = json_action.JSONAction(
            action_type="keyboard_enter"
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "do", "action": 'Press Enter'}
    
    def scroll(self, direction, element_id=None):
        if direction not in ['up', 'down', 'left', 'right']:
            message = f'Invalid scroll direction \"{direction}\". Please check the direction and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        
        converted_action = json_action.JSONAction(
            action_type="scroll",
            direction=direction,
            index=element_id
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "do", "action": 'Scroll', "kwargs": {"direction": direction, "element_id": element_id}}

    def swipe(self, direction, element_id=None):
        if direction not in ['up', 'down', 'left', 'right']:
            message = f'Invalid swipe direction \"{direction}\". Please check the direction and try again.'
            self.current_return = {"operation": "fail", "kwargs": {"message": message}}
            return
        
        if direction == 'up':
            _dir = 'down'
        elif direction == 'down':
            _dir = 'up'
        elif direction == 'left':
            _dir = 'right'
        elif direction == 'right':
            _dir = 'left'
        
        converted_action = json_action.JSONAction(
            action_type="scroll",
            direction=_dir,
            index=element_id
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "do", "action": 'Swipe', "kwargs": {"direction": direction, "element_id": element_id}}
        
    def wait(self):
        converted_action = json_action.JSONAction(
            action_type="wait"
        )
        self.env.execute_action(converted_action)
        self.current_return = {"operation": "do", "action": 'Wait'}