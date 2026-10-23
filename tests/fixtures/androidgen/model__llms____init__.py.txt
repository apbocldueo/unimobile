from .gpt import OpenaiEngine
from .vllm import VllmEngine
from .human import Human

def llm_provider(llm, **kwargs):
    if 'gpt' in llm:
        return OpenaiEngine(model=llm, **kwargs)
    
    if llm == 'human':
        return Human()
    
    if llm == 'vllm':
        return VllmEngine(**kwargs)
    
    raise ValueError(f"LLM {llm} not supported.")