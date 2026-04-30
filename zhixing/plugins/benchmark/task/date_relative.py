import random
from typing import Dict, Any
from datetime import datetime, timedelta

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="benchmark.task", name="date_relative")
class DateRelativeTaskGenerator(BaseParamInitializerGenerator):
    """
    Task parameter initializer that generates a date relative to the current date.

    This initializer is used for parameters with type `date_relative`. It computes
    a target date by adding an offset (in days) to the current system date and
    returns the formatted date string.

    Typical usage examples:
        - offset_days = 0   -> today's date
        - offset_days = 1   -> tomorrow
        - offset_days = -1  -> yesterday

    The output format can be customized using the `format` field.
    """
    gen_type = ParamInitializerPluginType.DATE_RELATIVE

    def generate(self, params: Dict[str, Any]) -> str:
        """
        Generate a date string based on the current date and an offset.

        Args:
            params (Dict[str, Any]):
                Configuration dictionary containing:
                - offset_days (int, optional): Number of days to offset from
                  the current date. Positive values indicate future dates,
                  negative values indicate past dates. Default is 0.
                - format (str, optional): Output date format compatible with
                  `datetime.strftime`. Default is "%Y-%m-%d".

        Returns:
            str: The formatted date string after applying the offset.
        """
        # 1. 提取核心配置
        offset_days = params.get("offset_days", 0)  # 日期偏移天数
        date_format = params.get("format", "%Y-%m-%d")  # 日期输出格式
        
        # 2. 计算目标日期
        current_date = datetime.now()
        target_date = current_date + timedelta(days=offset_days)
        
        # 3. 格式化输出（如：2026-03-12）
        formatted_date = target_date.strftime(date_format)
        return formatted_date
    