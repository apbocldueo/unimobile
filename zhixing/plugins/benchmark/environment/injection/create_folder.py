import os
import logging
from typing import Dict, Any

from benchmarks.core.interface import BaseEnvOp
from benchmarks.core.protocol import EnvironmentInitializerType
from benchmarks.environment.initializers.base.android import AndroidEnvironmentSetup
logger = logging.getLogger(__name__)

class ADBInjectionCreateFolderOperator(BaseEnvOp):

    op_type = EnvironmentInitializerType.ADB_CREATE_FOLDER

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        
        try:
            device = meta.get("device")
            if not device:
                logger.error("[CreateFolder] meta中缺少有效的device实例")
                return False
            logger.info("[CreateFolder] 文件夹创建操作开始")

            # 解析参数
            full_folder_path = params.get("phone_folder_path")
            folder_path = params.get("folder_path") # 基础路径
            folder_name = params.get("folder_name") # 文件夹名
            # 检验合法性
            if not full_folder_path and (not folder_path or not folder_name):
                logger.error("[CreateFolder] params必须包含phone_folder_path 或 (folder_path + folder_name)")
                return False
            
            # 拼接路径
            if not full_folder_path:
                full_folder_path = os.path.join(folder_path, folder_name)
            # 标准化路径
            full_folder_path = os.path.normpath(full_folder_path).replace("\\", "/")
            logger.info(f"[CreateFolder] 目标文件夹路径：{full_folder_path}")

            # 构建 ADB 命令
            adb_cmd = f'mkdir -p "{full_folder_path}"'
            logger.info(f"[CreateFolder] 执行手机命令：{adb_cmd}")

            result = device.device.shell(adb_cmd)

            # 检验结果
            if result.exit_code != 0:
                logger.error(f"[CreateFolder] 文件夹创建失败 | 路径：{full_folder_path} | 错误：{result.error}")
                return False
            
            # 验证文件夹是否真的创建成功
            check_cmd = f'ls -d "{full_folder_path}"'
            check_result = device.device.shell(check_cmd)
            if check_result.exit_code != 0:
                logger.warning(f"[CreateFolder] 命令执行成功，但文件夹验证失败 | 路径：{full_folder_path}")
                # 这里可选择返回False或True（根据业务需求），建议返回False确保可靠性
                return False
            logger.info(f"[CreateFolder] 文件夹创建成功：{full_folder_path}")
            return True
            
        except Exception as e:
            logger.error(f"[CreateFolder] 执行异常：{str(e)}", exc_info=True)
            return False
