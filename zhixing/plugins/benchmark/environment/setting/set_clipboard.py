import pyperclip
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.setting", name="android_setting_set_clipboard")
class ADBSetClipboardGenerator(BaseEnvironmentInitializerOperation):

    op_type = EnvironmentInitializerPluginType.ADB_SET_CLIPBOARD

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        raw = params.get("clipboard_content")
        if raw is None or not str(raw).strip():
            self.logger.error("execute: 'clipboard_content' is missing or empty")
            return False

        clipboard_content = str(raw).strip()

        try:
            pyperclip.copy(clipboard_content)
            pasted = pyperclip.paste()
            if pasted == clipboard_content:
                preview = clipboard_content[:40] + ("…" if len(clipboard_content) > 40 else "")
                self.logger.info("host clipboard set OK (%d chars): %s", len(clipboard_content), preview)
                return True
            self.logger.error("clipboard verify mismatch after copy (len local=%d len read=%d)", len(clipboard_content), len(pasted or ""))
            return False
        except Exception as e:
            self.logger.error("clipboard operation failed: %s", e, exc_info=True)
            return False
