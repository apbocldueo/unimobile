import os
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


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
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            self.logger.debug("started")
            full_path = params.get("phone_file_path")
            folder_path = params.get("folder_path")
            file_name = params.get("file_name")

            if not full_path and (not folder_path or not file_name):
                self.logger.error("need phone_file_path or both folder_path and file_name")
                return False

            android_file_path = full_path if full_path else os.path.join(folder_path, file_name)
            android_file_path = os.path.normpath(android_file_path).replace("\\", "/")
            file_content = params.get("content", "")

            if not file_content:
                cmd = f'touch "{android_file_path}"'
            else:
                safe_content = str(file_content).replace('"', '\\"')
                cmd = f'echo "{safe_content}" > "{android_file_path}"'

            self.logger.debug("shell: %s", cmd)
            result = device.shell(cmd)
            if result.exit_code != 0:
                self.logger.error(
                    "write failed path=%r exit_code=%s stderr=%s",
                    android_file_path,
                    result.exit_code,
                    result.error,
                )
                return False

            check_cmd = f'ls "{android_file_path}"'
            check_result = device.shell(check_cmd)
            if check_result.exit_code != 0:
                self.logger.error("file missing after write path=%r", android_file_path)
                return False

            self.logger.info("file created path=%s", android_file_path)
            return True
        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
