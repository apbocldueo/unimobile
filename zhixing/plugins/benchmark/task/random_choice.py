import random
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="benchmark.task", name="random_choice")
class RandomChoiceTaskGenerator(BaseParamInitializerGenerator):
    """
    Task parameter initializer that randomly selects one value from a list of options.

    This initializer corresponds to the `random_choice` parameter type and is
    commonly used when a parameter should be randomly chosen from a predefined
    set of candidates.
    """
    gen_type = ParamInitializerPluginType.RANDOM_CHOICE

    def generate(self, params: Dict[str, Any]) -> Any:
        """
        Randomly select a value from the provided options list.

        Args:
            params (Dict[str, Any]):
                Configuration dictionary containing:
                - options (List[Any]): A list of candidate values to choose from.

        Returns:
            Any: A randomly selected value from the options list.

        Raises:
            ValueError: If the options list is missing or empty.
        """
        
        options = params.get("options", [])
        if not options:
            raise ValueError("random_choice类型参数必须提供options列表")
        return random.choice(options)

