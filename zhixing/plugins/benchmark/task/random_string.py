import random
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType
from zhixing.core.factory import PluginRegistry


CHARSET_ALIASES = {
    "digits": "0123456789",                # number
    "letters_lower": "abcdefghijklmnopqrstuvwxyz",  # lowercase
    "letters_upper": "ABCDEFGHIJKLMNOPQRSTUVWXYZ",  # capital
    "letters": "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ",  # All letters
    "alphanumeric": "abcdefghijklmnopqrstuvwxyz0123456789",  # letter and number (defult)
    "hex": "0123456789abcdef",             # 0x
}

@PluginRegistry.register(namespace="benchmark.task", name="random_string")
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
        
        length = params.get("length", 8)
        prefix = params.get("prefix", "") # prefix
        suffix = params.get("suffix", "") # suffix
        charset = params.get("charset", "alphanumeric") 

        if charset in CHARSET_ALIASES:
            charset = CHARSET_ALIASES[charset]
        
        prefix = str(prefix)
        suffix = str(suffix)
        length = int(length)
        
        if not charset:
            raise ValueError("charset cannot be empty. Please configure a valid character set or alias（digits/letters）")
        random_str = ''.join(random.choice(charset) for _ in range(length))
        
        return f"{prefix}{random_str}{suffix}"
