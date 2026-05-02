import logging
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType


logger = logging.getLogger(__name__)


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
            logger.info("[ResetAppData] 开始执行APP数据重置操作")
            device = meta.get("device")
            package_name = params.get("package")
            app_name = params.get("app")

            if not package_name and not app_name:
                logger.error("[ResetAppData] params必须包含package 或 app参数")
                return False
            
            # 解析包名
            resolved_package = None
            if package_name:
                resolved_package = package_name
                logger.info(f"[ResetAppData] 使用显式包名：{resolved_package}")
            elif app_name:
                app_name_lower = app_name.lower()
                if not hasattr(device.device, "app_package_names"):
                    logger.error("[ResetAppData] Device实例未暴露'app_package_names'属性")
                    return False
                # 检验应用名是否存在
                if app_name_lower not in device.device.app_package_names:
                    logger.error(f"[ResetAppData] 未知应用'{app_name}'，可用应用：{list(device.device.app_package_names.keys())}")
                    return False
                resolved_package = device.device.app_package_names[app_name_lower]
                logger.info(f"[ResetAppData] 解析应用名'{app_name}' → 包名'{resolved_package}'")

            if not resolved_package:
                logger.error("[ResetAppData] 包名解析失败")
                return False
        
            # ====================== 3. 强制停止应用 ======================
            logger.info(f"[ResetAppData] 强制停止应用：{resolved_package}")
            stop_cmd = f"am force-stop {resolved_package}"
            stop_result = device.device.shell(stop_cmd)

            if stop_result.exit_code != 0:
                logger.warning(
                    f"[ResetAppData] 强制停止应用返回非零退出码：{stop_result.exit_code}，错误：{stop_result.error}"
                )
            
            # ====================== 4. 清空APP数据 ======================
            logger.info(f"[ResetAppData] 清空APP数据：{resolved_package}")
            clear_cmd = f"pm clear {resolved_package}"
            result = device.device.shell(clear_cmd)

            logger.info(
                f"[ResetAppData] pm clear输出：output={result.output}, error={result.error}, exit_code={result.exit_code}"
            )

            # ====================== 5. 校验执行结果 ======================
            if result.exit_code != 0:
                logger.error(
                    f"[ResetAppData] 清空APP数据失败：包名={resolved_package}，exit_code={result.exit_code}，error={result.error}"
                )
                return False
            if "Success" not in result.output:
                logger.warning(
                    f"[ResetAppData] pm clear返回非预期输出：{result.output}"
                )

            logger.info(f"[ResetAppData] 成功重置APP数据：{resolved_package}")
            return True
        except Exception as e:
            logger.error(f"[ResetAppData] 执行异常：{str(e)}", exc_info=True)
            return False
