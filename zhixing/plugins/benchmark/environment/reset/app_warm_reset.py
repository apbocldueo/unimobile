import logging
import time
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


logger = logging.getLogger(__name__)

@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_app_warm_reset")
class ADBAppWarmResetOperator(BaseEnvironmentInitializerOperation):
    """
    Lightweight application state resetter。
    Used to make sure to enter the main interface next time you open it
    
    Note:
    Never clear local data (SQLite/ cache), 
    and retain the login status and authorized permissions.
    """
    op_type = EnvironmentInitializerPluginType.ADB_APP_WARM_RESET
    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            app_name = params.get("app")
            if not app_name:
                logger.error("[AppWarmReset] Missing 'app' in params; cannot warm-reset.")
                return False
            if not device:
                logger.error("[AppWarmReset] Missing device instance in meta.")
                return False
            package_name = device.device.app_package_names[app_name]
            logger.info("[AppWarmReset] Stopping %s and clearing task stack…", package_name)

            stop_cmd = f"am force-stop {package_name}"
            stop_result = device.device.shell(stop_cmd)
            if stop_result.exit_code != 0:
                logger.error("[AppWarmReset] force-stop failed: %s", stop_result.error)
                return False

            logger.info("[AppWarmReset] force-stop OK for %s", package_name)

            return True
        
        except Exception as e:
            logger.error("[AppWarmReset] execute failed: %s", e, exc_info=True)
            return False