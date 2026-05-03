from typing import Dict, Any
from zhixing.core.benchmark.interface import BaseEvaluator
from zhixing.core.factory import PluginRegistry

class BaseVLMAction(BaseEvaluator):
    """The basic toolbox for VLM actions

    Args:
        BaseEvaluator (_type_): _description_
    """

    _llm_instance_cache = {}
    
    def __init__(self, config: Dict[str, Any], device: Any) -> None:
        super().__init__(config.get("params", {}), device)

        # 1. Independently extract the llm infrastructure configuration
        llm_config = config.get("llm") 
        self._local_llm = None

        if llm_config:
            # 2. Extract configuration items
            llm_name = llm_config.get("name", "openai_llm") # 默认找 openai_llm
            llm_params = llm_config.get("params", {})
            
            # 3. Generate Hash Key
            custom_model = llm_params.get("model", "unknown")
            custom_api_key = llm_params.get("api_key", "no_key")
            cache_key = f"{llm_name}_{custom_model}_{custom_api_key}"
            
            # 4. Check the cache: Instantiate only if it is not available
            if cache_key not in self.__class__._llm_instance_cache:
                self.logger.info(f"Instantiate and customize the LLM engine: {llm_name} ({custom_model})")
                
                LLMClass = PluginRegistry.get_plugin(namespace="llm", name=llm_name)
                
                # Instantiate and store in the cache
                new_llm_instance = LLMClass(**llm_params) 
                self.__class__._llm_instance_cache[cache_key] = new_llm_instance
            else:
                self.logger.debug(f"Hit the cache! Reuse the LLM engine directly: {custom_model}")
                
            # 5. Bind instance
            self._local_llm = self.__class__._llm_instance_cache[cache_key]
        

    def get_llm(self, context: Dict[str, Any]):
        active_llm = self._local_llm or context.get("evaluator_llm")
        if not active_llm:
            raise ValueError("No available LLM instances were found!")
        return active_llm