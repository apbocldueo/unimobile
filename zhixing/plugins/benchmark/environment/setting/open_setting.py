from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_open_system_setting")
class ADBOpenSystemSetting(BaseEnvironmentInitializerOperation):

    op_type = EnvironmentInitializerPluginType.ADB_OPEN_SYSTEM_SETTING

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.warning("no device in meta; cannot open system settings")
                return False

            setting_action = params.get("setting_action")
            delay = params.get("delay", 1.0)
            if not setting_action:
                self.logger.error("execute: missing required param 'setting_action'")
                return False

            result = device.open_system_setting(setting_action, delay)
            if result.exit_code == 0:
                self.logger.info("opened system setting %r (exit 0)", setting_action)
                return True

            self.logger.error(
                "open_system_setting failed action=%r exit_code=%s stderr=%s",
                setting_action,
                result.exit_code,
                result.error,
            )
            return False
        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
