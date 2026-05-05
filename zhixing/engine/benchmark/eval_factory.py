import logging
from typing import Dict, Any

from zhixing.core.benchmark.interface import BaseEvaluator
from zhixing.devices.base import BaseDevice
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)


class EvaluatorFactory:
    """评估插件化工厂
    """
    @classmethod
    def build(cls, config: Dict[str, Any], device: BaseDevice) -> BaseEvaluator:
        """根据 JSON 构建评估树

        Args:
            config (Dict[str, Any]): _description_

        Returns:
            BaseEvaluator: _description_
        """
        node_type = config.get("name")
        logger.debug("Building evaluator node name=%s", node_type)
        if not node_type:
            raise ValueError("evaluator config missing required field 'name'")
        
        # 提取参数
        params = config.get("params", {})

        # 处理复合逻辑节点（与 JSON 里 eval_composite / composite 对齐）
        if node_type in ("composite", "eval_composite"):
            logic = params.get("logic", "AND").upper()
            # 🔥 直接从注册表拿复合逻辑类
            target_class = PluginRegistry.get_plugin(namespace="evaluator.composite", name=logic)
        else:
            # 🔥 之前的普通插件逻辑
            namespace = f"evaluator.{node_type}"
            target_class = PluginRegistry.get_plugin(namespace=namespace, name=params.get("method"))
        
        return target_class(params, device)