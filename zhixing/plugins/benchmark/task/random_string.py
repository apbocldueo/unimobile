import random
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType


# 定义常用字符集别名，方便配置
CHARSET_ALIASES = {
    "digits": "0123456789",                # 纯数字
    "letters_lower": "abcdefghijklmnopqrstuvwxyz",  # 小写字母
    "letters_upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",  # 大写字母
    "letters": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",  # 所有字母
    "alphanumeric": "abcdefghijklmnopqrstuvwxyz0123456789",  # 字母+数字（默认）
    "hex": "0123456789abcdef",             # 十六进制
}

class RandomStringTaskGenerator(BaseParamInitializerGenerator):
    """
    Task parameter initializer that generates a random string.

    This initializer corresponds to the `random_string` parameter type.
    It supports customizable string length, prefix, and character sets.

    Character sets can be specified either by:
        - predefined aliases (e.g., "digits", "letters", "alphanumeric")
        - a custom character string provided by the user.
    """
    gen_type = ParamInitializerPluginType.RANDOM_STRING
    def generate(self, params: Dict[str, Any]) -> str:
        """
        Generate a random string according to the given configuration.

        Args:
            params (Dict[str, Any]):
                Configuration dictionary containing:
                - length (int, optional): Length of the generated random part.
                  Default is 8.
                - prefix (str | int, optional): Prefix string added before the
                  random characters. Default is an empty string.
                - charset (str, optional): Character set used for generating
                  random characters. This can be:
                    - a predefined alias (e.g., "digits", "letters")
                    - a custom string containing allowed characters

        Returns:
            str: The generated random string with the specified prefix.

        Raises:
            ValueError: If the character set is empty.
        """
        
        # 1. 提取基础配置
        length = params.get("length", 8)
        prefix = params.get("prefix", "") # 前缀
        suffix = params.get("suffix", "") # 后缀
        charset = params.get("charset", "alphanumeric")  # 默认字母+数字

        
        # 2. 处理字符集：先解析别名，再用自定义字符集
        if charset in CHARSET_ALIASES:
            # 如果是别名，替换为实际字符集
            charset = CHARSET_ALIASES[charset]
        # 若不是别名，直接使用用户配置的字符集（兼容自定义场景）
        
        # 3. 处理prefix类型（如配置的是数字139，转为字符串）
        prefix = str(prefix)
        suffix = str(suffix)
        length = int(length)
        
        # 4. 生成随机字符串（仅从指定字符集中选择）
        if not charset:
            raise ValueError("charset cannot be empty. Please configure a valid character set or alias（digits/letters）")
        random_str = ''.join(random.choice(charset) for _ in range(length))
        
        # 5. 拼接前缀并返回
        return f"{prefix}{random_str}{suffix}"
    

if __name__ == "__main__":
    # import sys
    # import os
    # sys.dont_write_bytecode = True
    # sys.path.append(os.getcwd())
    # LIBS_PATH = os.path.join(os.getcwd(), "plugins")
    # if LIBS_PATH not in sys.path:
    #     sys.path.append(LIBS_PATH)
    random_string = RandomStringTaskGenerator()
    number = {
        "type": "random_string",
        "length": 8,
        "prefix": 139,
        "charset": "digits"
    }
    result = random_string.generate(number)
    print(result)