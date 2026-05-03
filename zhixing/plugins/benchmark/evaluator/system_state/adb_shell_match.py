import re
import logging
from typing import Dict, Any


from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="evaluator.system_state", name="adb_shell_match")
class AdbShellMatchAction(BaseSystemAction):
    """Android fallback mechanism.
    
    Core logic: Execute arbitrary terminal commands and use regular expressions 
    to match the output results.
    """
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates the system state by executing an ADB shell command and matching the output.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        command = self.get_param("command", context, expected_type=str)
        expected_pattern = self.get_param("expected_result", context, expected_type=str)

        self.logger.info(f"Executing regex match. Command: {command}, Expected pattern: {expected_pattern}")

        output = self._run_device_shell(command)

        if re.search(expected_pattern, output):
            return EvalResult(is_pass=True, reason=f"Regex match successful: {expected_pattern}")
        
        return EvalResult(is_pass=False, reason=f"Regex match failed, actual output: {output[:100]}...")
