import random
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseParamInitializerGenerator
from zhixing.core.benchmark.protocol import ParamInitializerPluginType

class TemplateListTaskInitializer(BaseParamInitializerGenerator):
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
        
        # 1. 提取核心配置
        count = param_config.get("count", 1)  # 生成条目数量
        template = param_config.get("template", "")  # 单条目标模板
        separator = param_config.get("separator", ", ")  # 条目分隔符
        variables = param_config.get("variables", {})  # 模板中的变量配置

        if not template:
            raise ValueError("template_list类型必须提供template字段")
        if count <= 0:
            raise ValueError("template_list的count必须大于0")

        # 2. 为每个条目生成变量值
        items = []
        for _ in range(count):
            # 生成当前条目的所有变量值
            item_vars = {}
            for var_name, var_config in variables.items():
                # 嵌套调用参数生成器工厂，处理变量的类型（如random_choice/random_int）
                var_type = var_config.get("type")
                var_initializer = TaskInitializerFactory.get_initializer(var_type)
                item_vars[var_name] = var_initializer.generate(var_config)
            
            # 填充模板生成单条目
            item = template.format(**item_vars)
            items.append(item)

        # 3. 拼接所有条目为最终字符串
        final_str = separator.join(items)
        return final_str
    
