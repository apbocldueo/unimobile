
import logging
import pyperclip
from typing import Any, Dict

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType

logger = logging.getLogger(__name__)

class ADBSetClipboardGenerator(BaseEnvironmentInitializerOperation):

    op_type = EnvironmentInitializerPluginType.ADB_SET_CLIPBOARD

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        """_summary_

        Args:
            meta (Dict[str, Any]): _description_
            params (Dict[str, Any]): 
            {
                "clipboard_content": "content"
            }

        Returns:
            bool: _description_
        """
        clipboard_content = params.get("clipboard_content").strip()

        if not clipboard_content:
            logger.error("❌ 必传参数 clipboard_content 为空！")
            return False 
           
        # 2. 设置电脑剪切板
        try:
            pyperclip.copy(clipboard_content)

            # 验证
            pasted_content = pyperclip.paste()
            if pasted_content == clipboard_content:
                logger.info(f"✅ 剪贴板内容设置成功：{clipboard_content[:20]}...")
                return True
            else:
                logger.error("❌ 剪贴板内容设置失败（粘贴内容不匹配）")
                return False
        except Exception as e:
            logger.error(f"❌ 设置剪贴板异常：{str(e)}", exc_info=True)
            return False

