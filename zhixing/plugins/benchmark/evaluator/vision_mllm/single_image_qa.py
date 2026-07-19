import os
import copy
from typing import Dict, Any, List, Optional, Tuple

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_vision import BaseVLMAction
from zhixing.core.factory import PluginRegistry


def _redact_api_keys(obj: Any) -> Any:
    """Deep-copy dict/list structures and mask string values for keys named api_key."""
    if isinstance(obj, dict):
        return {
            k: ("***" if k == "api_key" and isinstance(v, str) else _redact_api_keys(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact_api_keys(x) for x in obj]
    return obj


def _strip_leading_formatting(s: str) -> str:
    """Remove leading markdown / whitespace so '**PASS:**' is recognized."""
    t = s.strip()
    while True:
        n = t.lstrip("*_` \t\n\r")
        if n == t:
            break
        t = n
    return t


def _split_pass_fail_verdict(t: str) -> Tuple[Optional[bool], str]:
    """Parse VLM line into (is_pass: bool | None, reason_tail).

    Handles markdown like ``**PASS:**`` and avoids treating ``PASSED`` / ``FAILURE`` as verdicts.
    """
    t = _strip_leading_formatting(t)
    if not t:
        return None, ""
    u = t.upper()
    # FAIL before PASS so ``FAIL`` prefix is unambiguous
    for is_pass, word in ((False, "FAIL"), (True, "PASS")):
        lw = len(word)
        if u.startswith(word):
            if len(t) > lw and t[lw].isalpha():
                continue
            rest = t[lw:].lstrip(":：* \t\n\r")
            return is_pass, rest
    return None, t


def _llm_inference_summary(llm: Any, image_paths: List[str]) -> str:
    parts = [
        f"llm_class={type(llm).__name__}",
        f"model={getattr(llm, 'model', '?')}",
        f"temperature={getattr(llm, 'temperature', '?')}",
        f"max_tokens={getattr(llm, 'max_tokens', '?')}",
    ]
    bu = getattr(llm, "base_url", None)
    if bu:
        parts.append(f"base_url={bu!r}")
    parts.append(f"images={image_paths!r}")
    return ", ".join(parts)


@PluginRegistry.register(namespace="evaluator.vision_mllm", name="single_image_qa")
class SingleImageEvaluatorAction(BaseVLMAction):
    """
    Single Image Visual Validator.
    Captures a screenshot after the agent task and sends it to the VLM for final judgment.
    
    Usage Examples in JSON/YAML:
    {
        "name": "vision_mllm",
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
            params_for_log = _redact_api_keys(copy.deepcopy(self.params))
            self.logger.info("single_image_qa evaluator params (api_key redacted): %s", params_for_log)
            self.logger.info("single_image_qa VLM prompt:\n%s", final_prompt)
            self.logger.info("single_image_qa VLM request %s", _llm_inference_summary(llm, [screenshot_path]))
            self.logger.info(f"Sending request to VLM ({llm.model})...")
            response = llm.generate(prompt=final_prompt, images=[screenshot_path])
        except Exception as e:
            return EvalResult(is_pass=False, reason=f"LLM request crashed: {e}")
        
        # 5. Parse and Format Result
        self.logger.info("single_image_qa VLM raw response: %r", response)
        result_text = (response or "").strip()
        verdict, reason = _split_pass_fail_verdict(result_text)
        if verdict is True:
            return EvalResult(is_pass=True, reason=reason)
        if verdict is False:
            return EvalResult(is_pass=False, reason=reason)
        self.logger.warning(f"Unexpected LLM response format: {result_text}")
        return EvalResult(is_pass=False, reason=f"Invalid VLM response format: {result_text[:100]}")