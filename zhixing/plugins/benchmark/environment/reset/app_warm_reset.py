from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_app_warm_reset")
class ADBAppWarmResetOperator(BaseEnvironmentInitializerOperation):
    """
    Lightweight app reset: force-stop only (no pm clear).
    Keeps app data; use before a run so the next cold start lands on a clean task stack.
    """
    op_type = EnvironmentInitializerPluginType.ADB_APP_WARM_RESET

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            app_name = params.get("app")
            if not app_name:
                self.logger.error("missing params.app (logical app key)")
                return False
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            names = getattr(device, "app_package_names", None)
            key = app_name.lower() if isinstance(app_name, str) else app_name
            if not names or key not in names:
                self.logger.error(
                    "unknown app key %r; available keys: %s",
                    app_name,
                    sorted(names.keys()) if names else [],
                )
                return False

            package_name = names[key]
            self.logger.info("force-stop package=%s (app=%r)", package_name, app_name)

            stop_cmd = f"am force-stop {package_name}"
            stop_result = device.shell(stop_cmd)
            if stop_result.exit_code != 0:
                self.logger.error(
                    "force-stop failed exit_code=%s stderr=%s",
                    stop_result.exit_code,
                    stop_result.error,
                )
                return False

            self.logger.info("warm reset OK for %s", package_name)
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
