import os
from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_vision import BaseVLMAction
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="evaluator.vision_mllm", name="single_image_qa")
class SingleImageEvaluatorAction(BaseVLMAction):
    """
    Single Image Visual Validator.
    Captures a screenshot after the agent task and sends it to the VLM for final judgment.
    
    Usage Examples in JSON/YAML:
    {
        "type": "vision_mllm",
        "params": {
            "method": "single_image_qa",
            "prompt": "Check if 'ZhiXing' App is opened and no error popups appear."
        }
    }
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates the screen state using a Vision-Language Model.

        Args:
            context (Dict[str, Any]): The execution context containing LLM instances and variables.

        Returns:
            EvalResult: Evaluation result parsed from VLM response.
        """
        # 1. Retrieve the optimal LLM instance from base class proxy
        llm = self.get_llm(context)

        # 2. Render the dynamic prompt
        user_prompt = self.get_param("prompt", context, expected_type=str)
        system_prompt = (
            "Please act as a strict automated testing judge. "
            "Your response MUST start with 'PASS:' or 'FAIL:', followed by a short comment."
        )
        final_prompt = f"{system_prompt}\n\n[Verification Rule]:\n{user_prompt}"

        # 3. Capture current screen state
        screenshot_dir = os.path.join(os.getcwd(), "temp", "eval_screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        screenshot_path = os.path.join(screenshot_dir, "vlm_final_check.png")

        try:
            # self.device is injected into the base class during initialization
            self.device.screenshot(path=screenshot_path)
            self.logger.info(f"Screenshot captured successfully: {screenshot_path}")
        except Exception as e:
            return EvalResult(is_pass=False, reason=f"Failed to capture screenshot: {e}")
        
        # 4. Request VLM Inference
        try:
            self.logger.info(f"Sending request to VLM ({llm.model})...")
            response = llm.generate(prompt=final_prompt, images=[screenshot_path])
        except Exception as e:
            return EvalResult(is_pass=False, reason=f"LLM request crashed: {e}")
        
        # 5. Parse and Format Result
        result_text = response.strip()
        if result_text.upper().startswith("PASS"):
            # Strip prefixes like 'PASS:', 'PASS：' and leading/trailing whitespaces
            return EvalResult(is_pass=True, reason=result_text[4:].strip(":： \n"))
        elif result_text.upper().startswith("FAIL"):
            return EvalResult(is_pass=False, reason=result_text[4:].strip(":： \n"))
        else:
            self.logger.warning(f"Unexpected LLM response format: {result_text}")
            return EvalResult(is_pass=False, reason=f"Invalid VLM response format: {result_text[:100]}")