import os
from dataclasses import dataclass

@dataclass
class ActionTimingConfig:
    """Time configuration for action interaction"""
    keyboard_switch_delay: float = 1.0
    text_clear_delay: float = 1.0
    text_input_delay: float = 1.0
    keyboard_restore_delay: float = 1.0

    def __post_init__(self):
        self.text_input_delay = float(os.getenv("PHONE_AGENT_TEXT_INPUT_DELAY", self.text_input_delay))

@dataclass
class DeviceTimingConfig:
    """Time configuration"""
    default_tap_delay: float = 1.0
    default_double_tap_delay: float = 1.0
    double_tap_interval: float = 0.1
    default_long_press_delay: float = 1.0
    default_swipe_delay: float = 1.5
    default_back_delay: float = 1.0
    default_home_delay: float = 1.0
    default_launch_delay: float = 3.0

@dataclass
class ConnectionTimingConfig:
    """Connect the relevant time configuration"""
    adb_restart_delay: float = 2.0
    server_restart_delay: float = 1.0

@dataclass
class TimingConfig:
    """Total configuration"""
    action: ActionTimingConfig
    device: DeviceTimingConfig
    connection: ConnectionTimingConfig

    def __init__(self):
        self.action = ActionTimingConfig()
        self.device = DeviceTimingConfig()
        self.connection = ConnectionTimingConfig()

TIMING_CONFIG = TimingConfig()