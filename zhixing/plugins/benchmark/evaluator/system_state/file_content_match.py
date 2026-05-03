# zhixing/plugins/benchmark/evaluator/system_state/file_content_match.py
from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.system_state", name="file_content_match")
class FileContentMatchAction(BaseSystemAction):
    """File content matcher.
    
    Reads the content of a specified file on the device and checks if it 
    contains the expected text.
    """
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates whether the specified file contains the expected content.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        # 1. Elegantly fetch parameters using the base class proxy
        file_path = self.get_param("file_path", context, expected_type=str)
        content = self.get_param("content", context, expected_type=str)
        
        self.logger.info(f"Checking content of file: {file_path}")
        
        # 2. Run the shell command
        output = self._run_device_shell(f"cat {file_path}")
        
        # 3. Validate results (with English reasons)
        # Note: Added 'No such file or directory' to cover standard Android shell errors
        if "No such file" in output or "No such file or directory" in output:
            return EvalResult(is_pass=False, reason=f"File not found: {file_path}")
            
        if content in output:
            return EvalResult(is_pass=True, reason="File content matches perfectly.")
        else:
            return EvalResult(is_pass=False, reason=f"Content mismatch. Actual output snippet: {output[:50]}...")