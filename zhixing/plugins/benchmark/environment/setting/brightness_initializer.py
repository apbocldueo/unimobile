from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_setting_brightness_initializer")
class AndroidBrightnessEnvInitializer(BaseEnvironmentInitializerOperation):

    op_type = EnvironmentInitializerPluginType.ADB_SET_BRIGHTNESS_INITIALIZE

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("execute: meta has no 'device'; cannot set brightness")
                return False

            target_mode = params.get("max_or_min")
            if target_mode not in ("max", "min"):
                self.logger.error(
                    "execute: param 'max_or_min' must be 'max' or 'min', got %r",
                    target_mode,
                )
                return False

            if target_mode == "max":
                brightness_cmd = "settings put system screen_brightness 1"
                self.logger.info(
                    "Setting initial brightness to minimum (1) because benchmark expects later 'max' adjustment"
                )
            else:
                brightness_cmd = "settings put system screen_brightness 255"
                self.logger.info(
                    "Setting initial brightness to maximum (255) because benchmark expects later 'min' adjustment"
                )

            result = device.shell(brightness_cmd)
            if result.exit_code != 0:
                self.logger.error(
                    "brightness shell failed exit_code=%s stderr=%s cmd=%r",
                    result.exit_code,
                    result.error,
                    brightness_cmd,
                )
                return False

            self.logger.info("Brightness precondition applied successfully")
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
