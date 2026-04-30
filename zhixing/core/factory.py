# Global Plugin registration center
import importlib
import pkgutil
import logging
from typing import Tuple, Any, Dict, Type


logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    ZhiXing framework the global plugin registry.
    Two-dimensional dictionary storage based on namespaces, implemented to achieve decoupling and dynamic dependency injection
    """
    # { namespace: { plugin_name: PluginClass } }
    # { "agent.perception": { "omniparser": OmniParserPerception } }
    _registry: Dict[str, Dict[str, Type[Any]]] = {}

    @classmethod
    def register(cls, namespace: str, name: str):
        """Plugin registry decorator.

        Example: 
            @PluginRegistry.register(namespace="agent.perception", naeme="omniparsr")
            class OmniParserPerception:
                ...
        Args:
            namespace (str): The namespace to which the plugin. 
            Such as: agent.perception、environmet_initialization.injection
            
            name (str): The unique name corresponding to the plugin in the YAML configuration file
        """
        def wrapper(plugin_class: Type[Any]) -> Type[Any]:
            # 1. Initialition namespace
            if namespace not in cls._registry:
                cls._registry[namespace] = {}
            
            # 2. duplicate checking
            if name in cls._registry[namespace]:
                logger.warning(
                    f"⚠️ [Plugin Overwritten] Plugin '{name}' in namespace '{namespace}' "
                    f"is being overwritten by {plugin_class.__name__}!"
                )
            
            # 3. Plugin entry library
            cls._registry[namespace][name] = plugin_class
            logger.info(f"✅ [Registered] {namespace} -> {name} ({plugin_class.__name__})")

            return plugin_class
        
        return wrapper

    @classmethod
    def get_plugin(cls, namespace: str, name: str) -> Tuple[Any]:
        pass

    @classmethod
    def autodiscover(cls, package_name: str = "zhixing.plugins"):
        pass

    @classmethod
    def get_all_registered(cls) -> Dict[str, list]:
        pass