import os
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="benchmark.environment.injection", name="android_injection_create_folder")
class ADBInjectionCreateFolderOperator(BaseEnvironmentInitializerOperation):

    op_type = EnvironmentInitializerPluginType.ADB_CREATE_FOLDER

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False
            self.logger.debug("started")

            # 解析参数
            full_folder_path = params.get("phone_folder_path")
            folder_path = params.get("folder_path") # 基础路径
            folder_name = params.get("folder_name") # 文件夹名
            # 检验合法性
            if not full_folder_path and (not folder_path or not folder_name):
                self.logger.error("need phone_folder_path or both folder_path and folder_name")
                return False
            
            # 拼接路径
            if not full_folder_path:
                full_folder_path = os.path.join(folder_path, folder_name)
            # 标准化路径
            full_folder_path = os.path.normpath(full_folder_path).replace("\\", "/")
            self.logger.debug("target path=%s", full_folder_path)

            # 构建 ADB 命令
            adb_cmd = f'mkdir -p "{full_folder_path}"'
            self.logger.debug("shell: %s", adb_cmd)

            result = device.shell(adb_cmd)

            # 检验结果
            if result.exit_code != 0:
                self.logger.error(
                    "mkdir failed path=%r exit_code=%s stderr=%s",
                    full_folder_path,
                    result.exit_code,
                    result.error,
                )
                return False
            
            # 验证文件夹是否真的创建成功
            check_cmd = f'ls -d "{full_folder_path}"'
            check_result = device.shell(check_cmd)
            if check_result.exit_code != 0:
                self.logger.warning("mkdir exited 0 but ls verify failed path=%r", full_folder_path)
                # 这里可选择返回False或True（根据业务需求），建议返回False确保可靠性
                return False
            self.logger.info("folder created and verified: %s", full_folder_path)
            return True
            
        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
