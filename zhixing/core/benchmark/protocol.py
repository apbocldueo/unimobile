from enum import Enum
from dataclasses import dataclass



################################### Type ###################################

class TaskType(str, Enum):
    """Task Initializer Type"""
    STATIC = "static"
    DYNAMIC = "dynamic"

class ParamInitializerPluginType(str, Enum):
    """Task Parameter initialization plugin type"""
    RANDOM_CHOICE = "random_choice"
    DATE_RELATIVE = "date_relative"
    RANDOM_INT = "random_int"
    RANDOM_STRING = "random_string"

class EnvironmentInitializerPluginType(str, Enum):
    """Environment initialization plugin type"""
    ADB_RESET_APP_DATA = "android_reset_reset_app_data"
    ADB_CLEAR_DIRECTORY = "android_reset_clear_directory"
    ADB_CLEAR_SQLITE_TABLE = "android_reset_clear_sqlite_rows"
    ADB_APP_WARM_RESET = "android_app_warm_reset"

    ADB_CREATE_FILE  = "android_injection_create_file"
    ADB_INSERT_SALITE = "android_injection_insert_sqlite_rows"
    ADB_PUSH_FILE = "android_injection_push_file"
    ADB_CREATE_FOLDER = "android_injection_create_folder"
    ADB_SHELL_EXECUTE = "android_shell_execute"

    ADB_SET_CLIPBOARD = "android_setting_set_clipboard"
    ADB_CHECK_NETWORK = "android_network_check_network"
    ADB_OPEN_SYSTEM_SETTING = "android_open_system_setting"

    ADB_CONDITIONAL_ADB_OPERATOR = "android_conditional_adb_operator"

    ADB_SET_BRIGHTNESS_INITIALIZE = "android_setting_brightness_initializer"

    UI_JUDEG_UI = "ui_judge_ui"


class ToolInitializerPluginType(str, Enum):
    """Tool initializer plugin type"""
    CALENDAR_EVENT = "calendar_event_tool",
    WEEKDAY_EVENT = "weekday_event_tool"

class EvaluatorInitializerPluginType(str, Enum):
    """Evaluator initializer plugin type"""
    

################################### Result ###################################
@dataclass
class EvalResult:
    """
    A unified evaluation result return class
    """
    is_pass: bool
    reason: str   
    token: float = 0.0