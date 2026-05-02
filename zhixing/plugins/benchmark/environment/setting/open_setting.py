import logging
from typing import Dict, Any
from benchmarks.environment.initializers.base.android import AndroidEnvironmentSetup
from benchmarks.core.interface import BaseEnvOp
from benchmarks.core.protocol import EnvironmentInitializerType

logger = logging.getLogger(__name__)

class ADBOpenSystemSetting(BaseEnvOp):
   
    op_type = EnvironmentInitializerType.ADB_OPEN_SYSTEM_SETTING

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            logger.info("[OpenSystemSetting] 开始执行打开系统设置操作")
            # 1. 获取设备
            device = meta.get("device")
            if not device:
                logger.warning("[OpenSystemSetting] 未获取到设备，跳过操作")
                return False
            # 2. 解析传入参数
            setting_action = params.get("setting_action")
            delay = params.get("delay", 1.0)
            if not setting_action:
                logger.warning("[OpenSystemSetting] 缺少必填参数 setting_action，跳过操作")
                return False
            # 3. 调用设备已封装的方法打开系统设置
            result = device.device.open_system_setting(setting_action, delay)
            if result.exit_code == 0:
                logger.info(f"[OpenSystemSetting] 成功跳转到系统设置页面：{setting_action}")
                logger.info("[OpenSystemSetting] 打开系统设置操作完成")
                return True
            return False
        except Exception as e:
            # 异常仅打日志，不中断程序执行（和原类保持一致）
            logger.error(f"[OpenSystemSetting] 打开系统设置出现异常：{str(e)}", exc_info=False)
            return False