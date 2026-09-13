"""LLM 输出判断（trajectory 文本评测）。

从 AgentRunner 产出的 ``trajectory`` 中读取模型侧输出（如 ``thought``、``metadata.raw_response``），
按 ``match`` 与 ``expected`` 做布尔 / 整数 / 字符串等判定，无需访问设备 Shell。
"""

from . import trajectory_expected_match  # noqa: F401
