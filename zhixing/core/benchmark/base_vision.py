from typing import Dict, Any
from zhixing.core.benchmark.interface import BaseEvaluator


class BaseVLMAction(BaseEvaluator):
    """The basic toolbox for VLM actions

    Args:
        BaseEvaluator (_type_): _description_
    """
    
    def __init__(self, params: Dict[str, Any], device: Any) -> None:
        super().__init__(params, device)
        
        self.custom_model = self.params.get("model")
        self._local_llm = None

        if self.custom_model or self.params.get("api_key"):
            self.logger.info(f"A locally customized LLM has been detected: {self.custom_model}")
            from zhixing.plugins.agent.llm.openai_llm import OpenAILLM
            self._local_llm = OpenAILLM(
                api_key=self.params.get("api_key"),
                model=self.custom_model or "gpt-4o",
                base_url=self.params.get("base_url")
            )

    def get_llm(self, context: Dict[str, Any]):
        active_llm = self._local_llm or context.get("evaluator_llm")
        if not active_llm:
            raise ValueError("No available LLM instances were found!")
        return active_llm