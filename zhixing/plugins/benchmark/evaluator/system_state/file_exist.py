from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.system_state", name="file_exist")
class FileExistAction(BaseSystemAction):
    """File existence validator.

    Checks whether a specified file or directory exists on the Android device.

    - **file_path** (required): Path on device (supports ``${...}`` via task_params).
    - **expect_absent** (optional, default ``false``): If ``true``, pass when the path
      does **not** exist (use after delete-file tasks). If ``false`` (default), pass
      when the path exists.
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
        expect_absent = self.get_param("expect_absent", context, default=False, expected_type=bool)

        self.logger.info("file_exist: path=%r expect_absent=%s", file_path, expect_absent)

        # Execute the 'ls' command
        output = self._run_device_shell(f"ls {file_path}")

        missing = (
            "No such file" in output
            or "No such file or directory" in output
            or "ERROR" in output
            or not output.strip()
        )

        if expect_absent:
            if missing:
                return EvalResult(is_pass=True, reason=f"Path absent as expected: {file_path}")
            return EvalResult(is_pass=False, reason=f"Path still exists (expected deleted): {file_path}")

        if missing:
            return EvalResult(is_pass=False, reason=f"Target file does not exist: {file_path}")

        return EvalResult(is_pass=True, reason=f"Target file exists: {file_path}")