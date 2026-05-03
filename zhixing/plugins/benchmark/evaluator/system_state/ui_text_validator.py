from typing import Dict, Any, List

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.system_state", name="ui_text_validator")
class UITextValidatorAction(BaseSystemAction):
    """Lightweight UI text validator based on screen XML dump.
    
    Example JSON parameter:
    {
        "method": "ui_text_validator",
        "metric": "contains_all",
        "expected_text": ["${hours}", "${minutes}", "${seconds}"]
    }
    """
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates whether the expected texts exist in the current screen's XML layout.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        # 1. Fetch dynamic parameters gracefully
        # Architect Note: We explicitly enforce 'expected_text' to be a list in the new architecture
        # to ensure type safety.
        expected_text_data = self.get_param("expected_text", context, expected_type=list)
        metric = self.get_param("metric", context, default="contains_all", expected_type=str)

        if not expected_text_data:
            return EvalResult(is_pass=False, reason="No valid 'expected_text' provided.")
            
        expected_texts = [str(item) for item in expected_text_data]
        
        # 2. Interact with device shell securely
        self.logger.info("Dumping screen XML layout via uiautomator...")

        # Step 1: Dump XML to device storage
        dump_output = self._run_device_shell("uiautomator dump /sdcard/window_dump.xml")

        # Step 2: Read the content
        xml_content = self._run_device_shell("cat /sdcard/window_dump.xml")

        # Architect Note: Covering multiple standard Android shell error outputs
        if not xml_content or "No such file" in xml_content or "No such file or directory" in xml_content:
            return EvalResult(is_pass=False, reason=f"Failed to pull XML tree. Dump output: {dump_output}")
        
        xml_content_lower = xml_content.lower()

        # 3. Validation Logic
        if metric == "contains_all":
            missing_texts = []
            for text in expected_texts:
                if str(text).lower() not in xml_content_lower:
                    missing_texts.append(str(text))
            
            if missing_texts:
                return EvalResult(is_pass=False, reason=f"The following texts are missing in XML: {missing_texts}")
            
            return EvalResult(is_pass=True, reason="All expected texts were successfully found in the XML!")
        
        elif metric == "contains_any":
            for text in expected_texts:
                if str(text).lower() in xml_content_lower:
                    return EvalResult(is_pass=True, reason=f"Successfully matched expected text in XML: {text}")
                
            return EvalResult(is_pass=False, reason=f"None of the expected texts were found in the XML: {expected_texts}")
        
        else:
            return EvalResult(is_pass=False, reason=f"Unsupported metric type: {metric}")