import logging
import time
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


logger = logging.info(__name__)

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
                logger.error("[AppWarmReset] No app parameters are provided, so the application cannot be reset!")
                return False
            if not device:
                logger.error("[AppWarmReset] 无法获取设备实例！")
                return False
            package_name = device.device.app_package_names[app_name]
            logger.info(f"[AppWarmReset] 正在清理 [{package_name}] 的进程与界面栈...")

            stop_cmd = f"am force-stop {package_name}"
            stop_result = device.device.shell(stop_cmd)
            if stop_result.exit_code != 0:
                logger.error(f"[AppWarmReset] 停止应用失败: {stop_result.error}")
                return False

            logger.info(f"[AppWarmReset] [{package_name}] 已被强行停止，UI 状态已清零。")

            return True
        
        except Exception as e:
            logger.error(f"[AppWarmReset] 执行出现致命异常：{str(e)}", exc_info=True)
            return False