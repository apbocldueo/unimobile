from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.system_state", name="file_exist")
class FileExistAction(BaseSystemAction):
    """File existence validator.
    
    Checks whether a specified file or directory exists on the Android device.
    """
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates the existence of the specified file.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        # Fetch the path dynamically using the base class proxy
        file_path = self.get_param("file_path", context, expected_type=str)

        self.logger.info(f"Checking existence of file: {file_path}")

        # Execute the 'ls' command
        output = self._run_device_shell(f"ls {file_path}")

        # Architect Note: Added .strip() to ensure spaces/newlines aren't treated as valid output
        if "No such file" in output or "No such file or directory" in output or "ERROR" in output or not output.strip():
            return EvalResult(is_pass=False, reason=f"Target file does not exist: {file_path}")
        
        return EvalResult(is_pass=True, reason=f"Target file exists: {file_path}")