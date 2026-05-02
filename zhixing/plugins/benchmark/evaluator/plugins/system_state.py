import logging
from typing import Dict, Any

from unimobile.devices.base import BaseDevice
from benchmarks.core.interface import EvalResult
from benchmarks.core.protocol import BaseEvaluator
from benchmarks.evaluator import register_evaluator
from benchmarks.evaluator.system_actions import SYSTEM_ACTION_REGISTRY

logger = logging.getLogger(__name__)

# ==========================================
# 主插件
# ==========================================

@register_evaluator("system_state")
class SystemStatePlugin(BaseEvaluator):
    def __init__(self, params: Dict[str, Any], device: BaseDevice) -> None:
        super().__init__(params, device)

        method = self.params.get("method")
        logger.info(f"[Evaluator]: evaluator type is: {method} --SystemStatePlugin")

        if not method or method not in SYSTEM_ACTION_REGISTRY:
            raise ValueError(f"缺少或未注册的方法: '{method}'。已注册方法: {list(SYSTEM_ACTION_REGISTRY.keys())}")

        action_class = SYSTEM_ACTION_REGISTRY[method]

        self.action_instance = action_class(self.params, self.device)

    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        self.action_instance.pre_execute(context)
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        return self.action_instance.execute(context)

