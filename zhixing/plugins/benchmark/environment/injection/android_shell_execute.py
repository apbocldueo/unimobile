from typing import Dict, Any, List, Union

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="benchmark.environment.injection", name="android_shell_execute")
class ADBInjectionShellExecuteOperator(BaseEnvironmentInitializerOperation):
    """
    Execute shell commands on the Android device.

    This initializer supports executing a single command or a sequence of commands.

    ------------------------------------------------------------
    Supported setup_config formats
    ------------------------------------------------------------

    Single command mode:

    {
        "type": "android_shell_execute",
        "commands": "pm clear com.android.providers.contacts"
    }

    ------------------------------------------------------------

    Multiple commands mode:

    {
        "type": "android_shell_execute",
        "commands": [
            "content insert --uri content://com.android.contacts/raw_contacts --bind account_name:s:null --bind account_type:s:null",
            "content insert --uri content://com.android.contacts/data --bind raw_contact_id:i:1 --bind mimetype:s:vnd.android.cursor.item/name --bind data1:s:'测试老板'"
        ],
        "ignore_errors": false
    }

    ------------------------------------------------------------
    DSL fields
    ------------------------------------------------------------

    commands : str OR list
        The shell command(s) to execute on the device.

    ignore_errors : bool (Optional)
        If True, continues executing subsequent commands even if one fails.
        Defaults to False.

    ------------------------------------------------------------
    """
    
    op_type = EnvironmentInitializerPluginType.ADB_SHELL_EXECUTE

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]) -> bool:
        """_summary_

        Args:
            meta (Dict[str, Any]): _description_
            params (Dict[str, Any]): 
            {
                "commands": "ls -l" // 可以是字符串
                or
                "commands": ["cmd1", "cmd2"] // 也可以是字符串列表
                "ignore_errors": bool // 可选，遇到错误是否继续执行
            }

        Returns:
            bool: _description_
        """
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            self.logger.debug("operator started")
            
            # --------------------------------------------------
            # Step 1: 解析参数
            # --------------------------------------------------
            commands = params.get("commands")
            ignore_errors = params.get("ignore_errors", False)

            if not commands:
                self.logger.error("params must contain 'commands' (str or list)")
                return False

            # 将单条命令统一转为列表，方便后续遍历执行
            if isinstance(commands, str):
                commands = [commands]
            elif not isinstance(commands, list):
                self.logger.error("'commands' must be str or list, got %s", type(commands))
                return False

            # --------------------------------------------------
            # Step 2: 顺序执行命令
            # --------------------------------------------------
            for i, cmd in enumerate(commands):
                self.logger.debug("command %d/%d: %s", i + 1, len(commands), cmd)
                
                result = device.shell(cmd)
                
                # Step 3: 校验单条命令执行结果
                if result.exit_code != 0:
                    error_msg = (
                        "command failed exit_code=%s stderr=%s cmd=%r"
                        % (result.exit_code, result.error, cmd)
                    )
                    if ignore_errors:
                        self.logger.warning("%s (ignore_errors=True, continuing)", error_msg)
                    else:
                        self.logger.error(error_msg)
                        return False
                else:
                    # 打印成功日志（截取部分输出防止日志刷屏）
                    output_preview = result.output.strip() if result.output else "无输出"
                    if len(output_preview) > 100:
                        output_preview = output_preview[:100] + "..."
                    self.logger.debug("command stdout preview: %s", output_preview)

            self.logger.info("all %d shell command(s) succeeded", len(commands))
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False