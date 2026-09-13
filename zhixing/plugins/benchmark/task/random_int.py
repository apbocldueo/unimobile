import random
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="benchmark.task", name="random_int")
class RandomIntTaskGenerator(BaseParamInitializerGenerator):
    """
    Task parameter initializer that generates a random integer within a given range.

    This initializer corresponds to the `random_int` parameter type.
    It is typically used when a task requires a numeric parameter such as
    hours, minutes, counts, or indices.
    """
    gen_type = ParamInitializerPluginType.RANDOM_INT
    def generate(self, params: Dict[str, Any]) -> int:
        """
        Generate a random integer between the specified minimum and maximum values.

        Args:
            params (Dict[str, Any]):
                Configuration dictionary containing:
                - min (int, optional): Minimum value (inclusive). Default is 0.
                - max (int, optional): Maximum value (inclusive). Default is 100.

        Returns:
            int: A randomly generated integer within the specified range.
        """
        
        min_val = params.get("min", 0)
        max_val = params.get("max", 100)
        return random.randint(min_val, max_val)

    def generate_with_rng(self, params: Dict[str, Any], rng: random.Random) -> int:
        """Generate an integer with an explicit run-local RNG.

        Args:
            params (Dict[str, Any]): Optional inclusive min/max values.
            rng (random.Random): Run-local deterministic generator.

        Raises:
            ValueError: The requested range is invalid.

        Returns:
            int: Deterministic integer within the inclusive range.
        """
        return rng.randint(int(params.get("min", 0)), int(params.get("max", 100)))
    
