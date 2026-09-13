from abc import ABC, abstractmethod
from typing import List, Any, Optional, Tuple

from zhixing.core.llm.usage import record_usage
from zhixing.utils.utils import get_plugin_logger

class BaseLLM(ABC):
    """
    LLM Adapter
    Defined the standards for how to interact with the underlying models (OpenAI, DeepSeek, LocalLLM)
    """

    _pipeline_phase = "🧠 LLM" 

    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: Optional[str] = None, 
                 temperature: float = 0.1, max_tokens: int = 4096, **kwargs):
        
        self.api_key = api_key
        self.model = model
        self.base_url = base_url
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        self.extra_kwargs = kwargs

        namespace = getattr(self.__class__, '__plugin_namespace__', 'llm.unknown')
        name = getattr(self.__class__, '__plugin_name__', self.__class__.__name__)
        self.logger = get_plugin_logger(phase=self._pipeline_phase, namespace=namespace, plugin_name=name)

    def generate(self, prompt: str, images: Optional[List[str]] = None) -> str:
        """Call the model and auto-record token usage for the active task scope."""
        text, usage = self._generate_impl(prompt, images=images)
        if usage:
            record_usage(
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            )
        return text

    @abstractmethod
    def _generate_impl(
        self, prompt: str, images: Optional[List[str]] = None
    ) -> Tuple[str, Optional[dict]]:
        """Returns ``(response_text, usage_dict)`` where usage_dict may be None."""

        pass