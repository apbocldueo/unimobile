import re
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

        self.logger.info("adb_shell_match: pattern=%r", expected_pattern)
        self.logger.debug("adb_shell_match: command=%r", command)

        output = self._run_device_shell(command)

        if re.search(expected_pattern, output):
            return EvalResult(is_pass=True, reason=f"output matched pattern {expected_pattern!r}")

        preview = (output or "")[:200]
        return EvalResult(
            is_pass=False,
            reason=f"output did not match {expected_pattern!r}; first 200 chars: {preview!r}",
        )
