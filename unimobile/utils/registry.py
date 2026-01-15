from typing import Type, Dict

# === 1. Global registry ===
PERCEPTION_REGISTRY: Dict[str, Type] = {}  # perception registry
REASON_REGISTRY: Dict[str, Type] = {}  # reasoning registry
LLM_REGISTRY: Dict[str, Type] = {}
MEMORY_REGISTRY: Dict[str, Type] = {}  # memory registry
PLANNER_REGISTRY: Dict[str, Type] = {} # planner registry
STRATEGY_REGISTRY: Dict[str, Type] = {} # Agent registry
DEVICE_REGISTRY: Dict[str, Type] = {}   # Device registry
EVALUATOR_REGISTRY: Dict[str, Type] = {} # evaluator registry
VERIFIER_REGISTRY: Dict[str, Type] = {} # verifier registry
PARSER_REGISTRY: Dict[str, Type] = {}   # parser registry


def _register(registry: Dict[str, Type], name: str):
    def decorator(cls: Type) -> Type:
        if name in registry:
            print(f"⚠️ Warning: Overwriting registration for '{name}'")
        registry[name] = cls
        return cls
    return decorator

def _get_class(registry: Dict[str, Type], name: str, category: str) -> Type:
    cls = registry.get(name)
    if not cls:
        raise ValueError(f"❌ 未找到 {category}: '{name}'。已注册列表: {list(registry.keys())}")
    return cls

# === 2. Decorators ===
register_perception = lambda name: _register(PERCEPTION_REGISTRY, name)
register_reasoning = lambda name: _register(REASON_REGISTRY, name)
register_llm = lambda name: _register(LLM_REGISTRY, name)
register_memory = lambda name: _register(MEMORY_REGISTRY, name)
register_planner = lambda name: _register(PLANNER_REGISTRY, name)
register_strategy = lambda name: _register(STRATEGY_REGISTRY, name)
register_device = lambda name: _register(DEVICE_REGISTRY, name)
register_evaluator = lambda name: _register(EVALUATOR_REGISTRY, name)
register_verifier = lambda name: _register(VERIFIER_REGISTRY, name)
register_parser = lambda name: _register(PARSER_REGISTRY, name)

# === 3. Getting function ===
get_perception_class = lambda name: _get_class(PERCEPTION_REGISTRY, name, "Perception")
get_reasoning_class = lambda name: _get_class(REASON_REGISTRY, name, "Reasoning")
get_llm_class = lambda name: _get_class(LLM_REGISTRY, name, "LLM")
get_memory_class = lambda name: _get_class(MEMORY_REGISTRY, name, "Memory")
get_planner_class = lambda name: _get_class(PLANNER_REGISTRY, name, "Planner")
get_strategy_class = lambda name: _get_class(STRATEGY_REGISTRY, name, "Strategy")
get_device_class = lambda name: _get_class(DEVICE_REGISTRY, name, "Device")
get_evaluator_class = lambda name: _get_class(EVALUATOR_REGISTRY, name, "Evaluator")
get_verifier_class = lambda name: _get_class(VERIFIER_REGISTRY, name, "Verifier")
get_parser_class = lambda name: _get_class(PARSER_REGISTRY, name, "Parser")
