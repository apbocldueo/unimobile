import importlib
import logging
import sys
from pathlib import Path
from unimobile.utils.registry import PERCEPTION_REGISTRY, REASON_REGISTRY, MEMORY_REGISTRY, PLANNER_REGISTRY, LLM_REGISTRY, VERIFIER_REGISTRY

logger = logging.getLogger(__name__)

PLUGIN_ROOT = Path("plugins")


def get_registry_by_type(component_type: str):
    return {
        "perception": PERCEPTION_REGISTRY,
        "reasoning": REASON_REGISTRY,
        "memory": MEMORY_REGISTRY,
        "planner": PLANNER_REGISTRY,
        "llm": LLM_REGISTRY,
        "verifier": VERIFIER_REGISTRY
    }[component_type]

def load_user_plugin(component_type: str, target_name: str):
    import os
    plugin_dir = PLUGIN_ROOT / component_type
    logger.info(f"plugin_dir is {plugin_dir}")
    logger.info(f"CWD is {os.getcwd()}")
    logger.info(f"{plugin_dir.exists()}")
    if not plugin_dir.exists():
        return False

    if str(PLUGIN_ROOT.resolve()) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT.resolve()))

    for py_file in plugin_dir.glob("*.py"):
        module_name = py_file.stem
        module_path = f"{component_type}.{module_name}"

        try:
            # import 
            importlib.import_module(module_path)
        except Exception as e:
            logger.warning(f"[PluginLoader] Skip {module_name}: {e}")
            continue

        registry = get_registry_by_type(component_type)
        if target_name in registry:
            logger.info(f"🔌 Loaded plugin '{target_name}' from {py_file.name}")
            return True

    return False
