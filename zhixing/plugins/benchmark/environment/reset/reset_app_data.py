from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_reset_reset_app_data")
class ADBResetResetAppDataGenerator(BaseEnvironmentInitializerOperation):
    """
    Reset all data for a specific Android application.

    This initializer clears the application's internal storage,
    cache, and databases, effectively restoring it to the state
    it had immediately after installation.

    Internally it executes the Android command:

        pm clear <package_name>

    This is equivalent to:
        Settings → Apps → Storage → Clear Storage

    ------------------------------------------------------------
    Typical use cases
    ------------------------------------------------------------

    - Ensure deterministic environment before benchmark execution
    - Remove data from previous test runs
    - Reset application state for repeatable experiments

    ------------------------------------------------------------
    Configuration example
    ------------------------------------------------------------

    Using logical app name:

    {
        "type": "android_reset_reset_app_data",
        "app": "contacts"
    }

    Using explicit package name:

    {
        "type": "android_reset_reset_app_data",
        "package": "com.google.android.contacts"
    }

    ------------------------------------------------------------
    Required device capabilities
    ------------------------------------------------------------

    device.shell(cmd: str) -> CommandResult

    device.app_package_names: Dict[str, str]

    ------------------------------------------------------------
    """

    op_type = EnvironmentInitializerPluginType.ADB_RESET_APP_DATA

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        try:
            self.logger.info("Starting app data reset (pm clear)")
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False
            package_name = params.get("package")
            app_name = params.get("app")

            if not package_name and not app_name:
                self.logger.error("params must include 'package' or 'app'")
                return False
            
            # 解析包名
            resolved_package = None
            if package_name:
                resolved_package = package_name
                self.logger.info("Using explicit package: %s", resolved_package)
            elif app_name:
                app_name_lower = app_name.lower()
                if not hasattr(device, "app_package_names"):
                    self.logger.error("device has no 'app_package_names' mapping")
                    return False
                # 检验应用名是否存在
                if app_name_lower not in device.app_package_names:
                    self.logger.error(
                        "Unknown app alias %r; known: %s",
                        app_name,
                        list(device.app_package_names.keys()),
                    )
                    return False
                resolved_package = device.app_package_names[app_name_lower]
                self.logger.info("Resolved app %r -> package %s", app_name, resolved_package)

            if not resolved_package:
                self.logger.error("Failed to resolve package name")
                return False
        
            # ====================== 3. 强制停止应用 ======================
            self.logger.info("force-stop %s", resolved_package)
            stop_cmd = f"am force-stop {resolved_package}"
            stop_result = device.shell(stop_cmd)

            if stop_result.exit_code != 0:
                self.logger.warning(
                    "force-stop exit_code=%s stderr=%s",
                    stop_result.exit_code,
                    stop_result.error,
                )
            
            # ====================== 4. 清空APP数据 ======================
            self.logger.info("pm clear %s", resolved_package)
            clear_cmd = f"pm clear {resolved_package}"
            result = device.shell(clear_cmd)

            self.logger.debug(
                "pm clear stdout=%r stderr=%r exit_code=%s",
                result.output,
                result.error,
                result.exit_code,
            )

            # ====================== 5. 校验执行结果 ======================
            if result.exit_code != 0:
                self.logger.error(
                    "pm clear failed package=%s exit_code=%s error=%s",
                    resolved_package,
                    result.exit_code,
                    result.error,
                )
                return False
            if "Success" not in result.output:
                self.logger.warning("pm clear unexpected output: %r", result.output)

            self.logger.info("App data cleared successfully: %s", resolved_package)
            return True
        except Exception as e:
            self.logger.error("Exception: %s", e, exc_info=True)
            return False
