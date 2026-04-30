# 清空一个目录

import logging
from typing import Dict, Any
from benchmarks.environment.initializers.base.android import AndroidEnvironmentSetup
from benchmarks.core.interface import BaseEnvOp
from benchmarks.core.protocol import EnvironmentInitializerType


logger = logging.getLogger(__name__)

class ADBResetClearDirectoryGenerator(BaseEnvOp):
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

    op_type = EnvironmentInitializerType.ADB_CLEAR_DIRECTORY

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        try:
            logger.info("[ClearDirectory] 开始执行目录清空操作")
            # ====================== 1. 核心：获取Device实例 ======================
            device = meta.get("device")
            if not device:
                logger.error("[ClearDirectory] meta中缺少device实例！")
                return False
            # ====================== 2. 校验核心参数 ======================
            phone_file_path = params.get("phone_folder_path")
            if not phone_file_path:
                logger.error("[ClearDirectory] params中缺少phone_file_path参数")
                return False
            # 标准化设备路径分隔符（兼容Windows/Linux）
            target_path = phone_file_path.replace("\\", "/")
            logger.info(f"[ClearDirectory] 准备清空目录：{target_path}")

            # 构建ADB shell命令
            clear_cmd = f"rm -rf {target_path}/*"
            logger.info(f"[ClearDirectory] 执行设备命令：{clear_cmd}")

            # 调用Device类执行shell命令
            result = device.device.shell(clear_cmd)
            logger.info(f"[ClearDirectory] ADB命令执行结果：{result}")

            # ====================== 4. 校验执行结果 ======================
            check_cmd = f"ls {target_path}"
            check_result = device.device.shell(check_cmd)
            if check_result.exit_code != 0:
                logger.error(f"[ClearDirectory] 目录操作异常：{check_result.error}")
                return False
            
            logger.info(f"[ClearDirectory] 目录清空成功：{target_path}")
            return True
        
        except Exception as e:
            logger.error(f"[ClearDirectory] 执行异常：{str(e)}", exc_info=True)
            return False