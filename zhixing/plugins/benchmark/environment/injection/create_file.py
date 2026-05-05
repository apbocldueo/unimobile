import os
import logging
from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

@PluginRegistry.register(namespace="benchmark.environment.injection", name="android_injection_create_file")
class ADBInjectionCreateFileOperator(BaseEnvironmentInitializerOperation):
    """
    Create files on the Android device.

    This initializer supports both static and parametric file creation.

    The plugin parses a declarative DSL describing how files should
    be generated.

    ------------------------------------------------------------
    Supported setup_config formats
    ------------------------------------------------------------

    Static mode (direct file definitions):

    {
        "type": "android_injection_create_file",
        "phone_file_path": "/storage/emulated/0/Documents",
        "files": [
            {
                "file_name": "test1.txt",
                "content": "hello"
            },
            {
                "file_name": "test2.txt",
                "content": "world"
            }
        ]
    }

    ------------------------------------------------------------

    Parametric mode (files generated from params):

    {
        "type": "android_injection_create_file",
        "phone_file_path": "/storage/emulated/0/Documents",

        "files": {
            "source": "$params.file_names",
            "template": {
                "file_name": "{item}",
                "content": "test content"
            }
        }
    }

    ------------------------------------------------------------
    DSL fields
    ------------------------------------------------------------

    phone_file_path : str
        Base directory where files will be created.

    files : list OR dict

        list:
            Static file definitions.

        dict:
            Parametric definition with:

                source:
                    Reference to parameter list
                    e.g. "$params.file_names"

                template:
                    Template used to generate each file definition.

    params : dict
        Generated parameters injected by task initialization.

    ------------------------------------------------------------
    """

    op_type = EnvironmentInitializerPluginType.ADB_CREATE_FILE

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]) -> bool:
        """_summary_

        Args:
            device (AndroidEnvironmentSetup): _description_
            meta (Dict[str, Any]): _description_
            params (Dict[str, Any]): 
            {
                "phone_file_path": phone_file_path
                or
                "folder_path": folder_path, // 可以是 dynamic
                "file_name": file_name // 可以是 dynamic
                "content": content
            }

        Returns:
            bool: _description_
        """
        try:
            device = meta.get("device")
                
            logger.info("CreateFileOperator started")
            # --------------------------------------------------
            # Step 1: Validate base path
            # --------------------------------------------------
            full_path = params.get("phone_file_path")
            folder_path = params.get("folder_path")
            file_name = params.get("file_name")
            
            # 校验路径参数
            if not full_path and (not folder_path or not file_name):
                logger.error("[CreateFile] params必须包含phone_file_path 或 (folder_path + file_name)")
                return False
            
            # 拼接最终文件路径（适配两种格式）
            android_file_path = full_path if full_path else os.path.join(folder_path, file_name)
            # 标准化路径（兼容Windows/Linux分隔符）
            android_file_path = os.path.normpath(android_file_path).replace("\\", "/")
            file_content = params.get("content", "")
            
            if not file_content:
                cmd = f'touch "{android_file_path}"'
            else:
                # Step 1: 转义内容（避免shell命令注入，和你原代码一致）
                safe_content = str(file_content).replace('"', '\\"')
                # Step 2: 构建手机端shell命令（和你原代码逻辑一致）
                cmd = f'echo "{safe_content}" > "{android_file_path}"'
                
            logger.info(f"[CreateFile] 执行手机命令：{cmd}")
            result = device.device.shell(cmd)
            # Step 4: 校验执行结果（和你原代码一致）
            if result.exit_code != 0:
                logger.error(f"[CreateFile] 文件创建失败：{result.error} | 路径：{android_file_path}")
                return False
            # Step 5: 验证文件是否存在（可选，增强可靠性）
            check_cmd = f'ls "{android_file_path}"'
            check_result = device.device.shell(check_cmd)
            if check_result.exit_code != 0:
                logger.error(f"[CreateFile] 文件验证失败：{android_file_path}")
                return False

            logger.info(f"[CreateFile] 操作成功：{android_file_path}")
            return True
        except Exception as e:
            logger.error(f"[CreateFile] 执行异常：{str(e)}", exc_info=True)
            return False
