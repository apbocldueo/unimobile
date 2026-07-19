import pyperclip
from typing import Dict, Any

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_system import BaseSystemAction
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="evaluator.system_state", name="host_clipboard_match")
class HostClipboardMatchAction(BaseSystemAction):
    """Compare host OS clipboard text via pyperclip.

    Use with ``android_setting_set_clipboard`` when the benchmark bridges clipboard
    through the desktop (same mechanism as the env initializer).
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        expected = self.get_param("expected", context, expected_type=str)
        match = self.get_param("match", context, default="exact", expected_type=str).lower()

        try:
            actual = pyperclip.paste()
        except Exception as e:
            return EvalResult(is_pass=False, reason=f"Failed to read host clipboard: {e}")

        if match == "exact":
            if actual == expected:
                return EvalResult(is_pass=True, reason="Host clipboard equals expected text.")
            preview = (actual or "")[:40]
            return EvalResult(
                is_pass=False,
                reason=(
                    f"Clipboard mismatch (len actual={len(actual or '')} "
                    f"expected={len(expected)}). Actual preview: {preview!r}"
                ),
            )

        if expected in (actual or ""):
            return EvalResult(is_pass=True, reason="Host clipboard contains expected text.")
        return EvalResult(is_pass=False, reason="Expected substring not found in host clipboard.")
