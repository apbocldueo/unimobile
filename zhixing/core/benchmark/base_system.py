from typing import Dict, Any
from zhixing.core.benchmark.interface import BaseEvaluator

class BaseSystemAction(BaseEvaluator):
    
    def _run_device_shell(self, command: str) -> str:
        self.logger.info(f"Running command on device: {command}")
        try:
            result = self.device.shell(command, error_raise=True)
            output = result.output.strip() if result and result.output else ""
            if result.exit_code != 0:
                self.logger.error(f"Command failed with exit code {result.exit_code}: {result.error}")
            return output
        except Exception as e:
            self.logger.error(f"Failed to run command on device: {e}")
            return f"ERROR :{str(e)}"