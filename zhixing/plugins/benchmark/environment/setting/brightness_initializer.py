import logging
from typing import Dict, Any

from benchmarks.core.interface import BaseEnvOp
from benchmarks.core.protocol import EnvironmentInitializerType

logger = logging.getLogger(__name__)


class AndroidBrightnessEnvInitializer(BaseEnvOp):

    # 注册专属插件类型
    op_type = EnvironmentInitializerType.ADB_SET_BRIGHTNESS_INITIALIZE

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            # 1. 获取设备对象（和你现有插件一致）
            device = meta.get("device")
            if not device:
                logger.error("[AndroidBrightness] meta中缺少device对象")
                return False

            logger.info("[AndroidBrightness] 开始执行亮度环境初始化")

            # 2. 解析核心参数：对齐 max_or_min（统一判断标准）
            target_mode = params.get("max_or_min")
            if target_mode not in ["max", "min"]:
                logger.error(f"[AndroidBrightness] 参数错误，仅支持 max/min，当前：{target_mode}")
                return False

            # 3. 核心逻辑：根据目标，反向设置初始亮度
            if target_mode == "max":
                # 任务要求调最大 → 初始设为最小亮度
                brightness_cmd = "settings put system screen_brightness 1"
                logger.info("[AndroidBrightness] 目标：max → 初始化亮度为最小值(1)")
            else:
                # 任务要求调最小 → 初始设为最大亮度
                brightness_cmd = "settings put system screen_brightness 255"
                logger.info("[AndroidBrightness] 目标：min → 初始化亮度为最大值(255)")

            # 4. 执行ADB命令（复用你现有插件的调用方式）
            result = device.device.shell(brightness_cmd)
            if result.exit_code != 0:
                logger.error(f"[AndroidBrightness] 设置亮度失败：{result.error}")
                return False

            logger.info("[AndroidBrightness] 亮度环境初始化执行成功")
            return True

        except Exception as e:
            logger.error(f"[AndroidBrightness] 初始化异常：{str(e)}", exc_info=True)
            return False