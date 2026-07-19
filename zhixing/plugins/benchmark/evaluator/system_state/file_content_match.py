# zhixing/plugins/benchmark/evaluator/system_state/file_content_match.py
from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry

def _normalize_text(s: str) -> str:
    """Normalize newlines and surrounding whitespace for stable comparisons."""
    return s.replace("\r\n", "\n").replace("\r", "\n").strip()


@PluginRegistry.register(namespace="evaluator.system_state", name="file_content_match")
class FileContentMatchAction(BaseSystemAction):
    """File content matcher.

    Reads the content of a specified file on the device and checks it against
    the expected text. Use ``match`` to require a full-file replacement
    (``exact``) or the default substring check (``contains``).
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        """Evaluates whether the specified file contains the expected content.

        Args:
            context (Dict[str, Any]): The execution context containing dynamic variables.

        Returns:
            EvalResult: The evaluation result, including pass/fail status and the reason.
        """
        file_path = self.get_param("file_path", context, expected_type=str)
        content = self.get_param("content", context, expected_type=str)
        match = self.get_param("match", context, default="contains", expected_type=str).lower()

        self.logger.info("Checking content of file: %s (match=%s)", file_path, match)

        output = self._run_device_shell(f"cat {file_path}")

        if "No such file" in output or "No such file or directory" in output:
            return EvalResult(is_pass=False, reason=f"File not found: {file_path}")

        if match == "exact":
            if _normalize_text(output) == _normalize_text(content):
                return EvalResult(is_pass=True, reason="File content equals expected text (exact match).")
            snippet = output.replace("\n", "\\n")[:120]
            return EvalResult(
                is_pass=False,
                reason=f"Exact content mismatch. Actual begins: {snippet!r}...",
            )

        if content in output:
            return EvalResult(is_pass=True, reason="File content matches perfectly.")
        return EvalResult(
            is_pass=False,
            reason=f"Content mismatch. Actual output snippet: {output[:50]}...",
        )