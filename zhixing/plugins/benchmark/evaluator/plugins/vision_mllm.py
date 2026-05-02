import os
import base64
import logging
from typing import Dict, Any

from benchmarks.core.interface import EvalResult
from benchmarks.core.param_handler import ParamHander
from benchmarks.core.protocol import BaseEvaluator
from benchmarks.evaluator import register_evaluator
from unimobile.devices.base import BaseDevice
from benchmarks.evaluator.vlm_actions import VLM_ACTION_REGISTRY

logger = logging.getLogger(__name__)

@register_evaluator("vision_vllm")
class VisionVLLMPlugin(BaseEvaluator):
    """
    视觉大模型评估路由器 (一级评估器 / 包工头)
    负责初始化大模型环境，并路由到具体的 VLM 动作 (单图/多图/对比等)。

    Args:
        BaseEvaluator (_type_): _description_
    """
    def __init__(self, params: Dict[str, Any], device: BaseDevice) -> None:
        super().__init__(params, device)
        
        # 1. 路由检查
        method = self.params.get("method")
        if not method or method not in VLM_ACTION_REGISTRY:
            raise ValueError(f"[VisionMLLM] 缺少或未注册的 method: '{method}'。已注册: {list(VLM_ACTION_REGISTRY.keys())}")
        
        # 将解析好的 params 和 device 传给底层的具体 Action
        action_class = VLM_ACTION_REGISTRY[method]
        self.action_instance = action_class(self.params, self.device)
    
    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        if hasattr(self.action_instance, 'pre_execute'):
            self.action_instance.pre_execute(context)
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        logger.info(f"[VisionMLLM] 将评估任务分发给 VLM Action: {self.params.get('method')}")
        # 传递 context，让小弟去里面捞 default_llm 等资源
        return self.action_instance.execute(context)