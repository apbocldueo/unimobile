import logging
from typing import Dict, Any

from zhixing.devices.base import BaseDevice
from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.interface import BaseEvaluator
from zhixing.engine.benchmark.eval_factory import EvaluatorFactory

logger = logging.getLogger(__name__)

class AndEvaluator(BaseEvaluator):
    """复合节点：逻辑与

    Args:
        BaseEvaluator (_type_): _description_
    """
    def __init__(self, params: Dict[str, Any], device: BaseDevice) -> None:
        super().__init__(params, device)
        # 递归解析 params 里的 rules 列表
        self.children = [EvaluatorFactory.build(rule, device) for rule in params.get("rules", [])]
    
    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        for child in self.children:
            child.pre_evaluate(context)

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        total_token = 0.0
        for child in self.children:
            result = child.evaluate(context)
            total_token += result.token

            if not result.is_pass:
                return EvalResult(
                    is_pass=False,
                    reason=f"Fail: {result.reason}",
                    token=total_token
                )
        
        return EvalResult(
            is_pass=True,
            reason="所有 AND 规则均通过",
            token=total_token
        )

class OrEvaluator(BaseEvaluator):
    """复合节点

    Args:
        BaseEvaluator (_type_): _description_
    """
    def __init__(self, params: Dict[str, Any], device: BaseDevice) -> None:
        super().__init__(params)
        self.children = [EvaluatorFactory.build(rule, device) for rule in params.get("rules", [])]

    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        for child in self.children:
            child.pre_evaluate(context)
    
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        total_token = 0.0
        reasons = []

        for child in self.children:
            result = child.evaluate(context)
            total_token += result.token

            if result.is_pass:
                return EvalResult(
                    is_pass=True,
                    reason=f"Pass: {result.reason}",
                    token=total_token
                )
            reasons.append(result.reason)
        
        return EvalResult(
            is_pass=False,
            reason=f"所有 Or 规则全失败: {reasons}",
            token=total_token
        )

class SequenceEvaluator(BaseEvaluator):
    """严格顺序递进逻辑：

    按顺序执行子评估器，一旦某一步失败，立即阻断并返回详细的步骤拦截信息

    Args:
        BaseEvaluator (_type_): _description_
    """
    def __init__(self, params: Dict[str, Any], device: BaseDevice) -> None:
        super().__init__(params, device)
        self.children = [EvaluatorFactory.build(rule, device) for rule in params.get("rules", [])] # 

    def pre_evaluate(self, context: Dict[str, Any]) -> None:
        for child in self.children:
            child.pre_evaluate(context)
        
    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        total_token = 0.0

        for step_idx, child in enumerate(self.children):
            # 获取插件名, 用于打印
            child_name = child.__class__.__name__
            logger.info(f"▶️ [Sequence] 正在执行步骤 {step_idx + 1}/{len(self.children)}: {child_name}")

            result = child.evaluate(context)

            total_token += getattr(result, "token", 0.0)

            if not result.is_pass:
                abort_reason = f"Sequence aborted at Step {step_idx + 1} ({child_name}): {result.reason}"
                logger.warning(f"⏸️ [Sequence] 流程中断！{abort_reason}")

                return EvalResult(
                    is_pass=False,
                    reason=abort_reason,
                    token=total_token
                )
            
        return EvalResult(
            is_pass=True,
            reason="所有 Sequence 递进规则均顺利通过！",
            token=total_token
        )
        