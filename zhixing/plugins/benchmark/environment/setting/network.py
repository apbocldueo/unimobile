import logging
from typing import Dict, Any
from benchmarks.environment.initializers.base.android import AndroidEnvironmentSetup
from benchmarks.core.interface import BaseEnvOp
from benchmarks.core.protocol import EnvironmentInitializerType

logger = logging.getLogger(__name__)

class ADBCheckNetworkOperator(BaseEnvOp):
    """
    Check if the Android device has network connectivity.
    - If network is available: do nothing.
    - If network is unavailable: try to enable Wi-Fi & Mobile Data automatically.
    - If reconnection fails: only log a WARNING, DO NOT stop execution.

    This operator ensures the benchmark can run without network interruption.
    No mandatory params required.
    """
    op_type = EnvironmentInitializerType.ADB_CHECK_NETWORK

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        try:
            logger.info("[CheckNetwork] 开始执行网络检测操作")
            # 1. 获取设备实例
            device = meta.get("device")
            if not device:
                logger.warning("[CheckNetwork] 未获取到设备，跳过网络检测（不中断执行）")
                return True
            # 2. 检测网络是否通畅（ping 谷歌DNS，通用可靠）
            ping_cmd = "ping -c 1 8.8.8.8"
            ping_result = device.device.shell(ping_cmd)

            if ping_result.exit_code == 0:
                logger.info("[CheckNetwork] 设备网络正常，无需操作")
                return True
            
            # 3. 无网络 → 尝试自动开启 Wi-Fi + 移动数据
            logger.warning("[CheckNetwork] 设备无网络，尝试自动开启网络...")
            # 开启Wi-Fi
            device.device.shell("svc wifi enable")
            # 开启移动数据（需要ROOT权限，模拟器默认支持）
            device.device.shell("svc data enable")
            # 等待1秒让网络生效
            import time
            time.sleep(3)
            # 4. 再次检测网络
            recheck_result = device.device.shell(ping_cmd)
            if recheck_result.exit_code == 0:
                logger.info("[CheckNetwork] 网络开启成功！")
            else:
                # ✅ 关键：连接失败只警告，不中断执行
                logger.warning("[CheckNetwork] 自动开启网络失败，请手动检查网络连接！")

            logger.info("[CheckNetwork] 网络检测操作完成")
            return True
        except Exception as e:
            # ✅ 异常只打日志，不中断程序
            logger.error(f"[CheckNetwork] 网络检测出现异常：{str(e)}（不中断执行）", exc_info=False)
            return True 