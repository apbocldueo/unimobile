"""Clear all entries inside a device directory (rm -rf path/*)."""

from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_reset_clear_directory")
class ADBResetClearDirectoryGenerator(BaseEnvironmentInitializerOperation):
    """
    Clear all files in a specified directory on the device.

    This initializer is commonly used to ensure a clean filesystem
    environment before a benchmark task begins.

    Example use cases:
        - Remove leftover files from previous tests
        - Prepare a clean directory for file manipulation tasks
        - Reset application storage directories

    Example setup_config:

    {
        "type": "clear_directory",
        "phone_folder_path": "/storage/emulated/0/Download"
    }
    """

    op_type = EnvironmentInitializerPluginType.ADB_CLEAR_DIRECTORY

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            phone_folder_path = params.get("phone_folder_path")
            if not phone_folder_path:
                self.logger.error("params missing 'phone_folder_path'")
                return False

            target_path = phone_folder_path.replace("\\", "/")
            clear_cmd = f"rm -rf {target_path}/*"
            self.logger.info("clearing directory contents path=%r", target_path)
            self.logger.debug("shell: %s", clear_cmd)

            result = device.shell(clear_cmd)
            self.logger.debug(
                "rm exit_code=%s stderr=%s",
                getattr(result, "exit_code", None),
                getattr(result, "error", None),
            )

            check_cmd = f"ls {target_path}"
            check_result = device.shell(check_cmd)
            if check_result.exit_code != 0:
                self.logger.error(
                    "post-clear ls failed path=%r exit_code=%s stderr=%s",
                    target_path,
                    check_result.exit_code,
                    check_result.error,
                )
                return False

            self.logger.info("directory cleared OK: %s", target_path)
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
