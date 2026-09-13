# zhixing/plugins/benchmark/evaluator/system_state/brightness_validator.py
from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.system_state", name="brightness_validator")
class BrightnessValidatorAction(BaseSystemAction):
    """System brightness validator.
    
    Dynamically compares the current system backlight brightness based on 
    the passed target_level ('max' or 'min').
    """
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates the system screen brightness against the target level.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        target_level = self.get_param("target_level", context, expected_type=str)
        
        if target_level not in ["max", "min"]:
            return EvalResult(is_pass=False, reason=f"Unknown brightness target requirements: {target_level}")

        cmd = "settings get system screen_brightness"
        output = self._run_device_shell(cmd).strip()

        try:
            current_brightness = int(output)
            self.logger.info(f"The current true brightness value of the system is: {current_brightness}")
        except ValueError:
            return EvalResult(is_pass=False, reason=f"The system brightness value cannot be parsed: '{output}'")

        # Architect Note: Different manufacturers have different min/max bounds (e.g., Huawei min may be 4, max 250).
        if target_level == "max":
            if current_brightness >= 240: 
                return EvalResult(is_pass=True, reason=f"The brightness has been set to the maximum (current value: {current_brightness})")
            else:
                return EvalResult(is_pass=False, reason=f"The maximum brightness has not been reached. The current value is only: {current_brightness}")
                
        elif target_level == "min":
            if current_brightness <= 15:  
                return EvalResult(is_pass=True, reason=f"The brightness has been set to the minimum (current value: {current_brightness})")
            else:
                return EvalResult(is_pass=False, reason=f"The minimum brightness has not been reached. The current value is as high as: {current_brightness}")