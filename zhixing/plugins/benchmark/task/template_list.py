import random
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="benchmark.task", name="template_list")
class TemplateListTaskGenerator(BaseParamInitializerGenerator):
    """
    Task parameter initializer that generates a list of templated items.

    This initializer corresponds to the `template_list` parameter type.
    It allows generating multiple items using a template string and
    dynamically filling variables inside the template.

    Each variable can itself use another parameter initializer (e.g.,
    `random_choice`, `random_int`), enabling nested parameter generation.

    The generated items are concatenated using a configurable separator.
    """


    gen_type = ParamInitializerPluginType.TEMPLATE_LIST

    def generate(self, param_config: Dict[str, Any]) -> str:
        """
        Generate a formatted string consisting of multiple templated items.

        Args:
            param_config (Dict[str, Any]):
                Configuration dictionary containing:
                - count (int): Number of items to generate.
                - template (str): Template string for a single item.
                - separator (str, optional): Separator used to join generated
                  items. Default is ", ".
                - variables (Dict[str, Dict]): Variable definitions used
                  in the template. Each variable can specify its own
                  parameter generation strategy.

        Returns:
            str: A concatenated string composed of multiple generated items.

        Raises:
            ValueError:
                If the template is missing or if count <= 0.
        """
        
        count = param_config.get("count", 1)
        template = param_config.get("template", "") 
        separator = param_config.get("separator", ", ")
        variables = param_config.get("variables", {})

        if not template:
            raise ValueError("The template list type must provide the template field")
        if count <= 0:
            raise ValueError("The count of the template list must be greater than 0")

        items = []
        for _ in range(count):
            item_vars = {}
            for var_name, var_config in variables.items():
                var_type = var_config.get("type")
                SubInitializerClass = PluginRegistry.get_plugin(
                    namespace="benchmark.task", 
                    name=var_type
                )
                var_initializer = SubInitializerClass()
                item_vars[var_name] = var_initializer.generate(var_config)
            
            item = template.format(**item_vars)
            items.append(item)

        final_str = separator.join(items)
        return final_str
    
