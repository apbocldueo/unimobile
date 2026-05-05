from abc import abstractmethod
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEvaluator
from zhixing.core.benchmark.protocol import EvalResult
from zhixing.devices.base import BaseDevice

class BaseSystemAction(BaseEvaluator):
    
    def __init__(self, params: Dict[str, Any], device: BaseDevice) -> None:
        self.params = params
        self.device = device
        super().__init__(params, device)

    def _run_device_shell(self, command: str) -> str:
        self.logger.debug("device shell: %s", command)
        try:
            result = self.device.shell(command, error_raise=True)
            output = result.output.strip() if result and result.output else ""
            if result.exit_code != 0:
                self.logger.error(
                    "shell non-zero exit_code=%s cmd=%r stderr=%s",
                    result.exit_code,
                    command,
                    result.error,
                )
            return output
        except Exception as e:
            self.logger.error("shell raised for cmd=%r: %s", command, e, exc_info=True)
            return f"ERROR:{e}"
        
    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        """Pre-assessment hook.
        Triggered before the Agent actually starts running the task. Used to save the initial state

        Args:
            context (Dict[str, Any]): _description_
        """
        pass

    @abstractmethod
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Core assessment logic.
        Triggered after the Agent finishes the task. Used for comparing the status and returning the final result.
        Args:
            context (Dict[str, Any]): _description_

        Returns:
            EvalResult: _description_
        """
        
        pass