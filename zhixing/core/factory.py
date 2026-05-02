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
            
            setattr(plugin_class, '__plugin_namespace__', namespace)
            setattr(plugin_class, '__plugin_name__', name)

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
        """Get the registered plugin.

        Args:
            namespace (str): The namespace to which the plugin. 
            name (str): The unique name corresponding to the plugin

        Raises:
            ValueError: If the corresponding plugin cannot be found, throw a definite exception

        Returns:
            Tuple[Any]: Plugin
        """
        if namespace not in cls._registry or name not in cls._registry[namespace]:
            error_msg = (
                f"❌ [Plugin Not Found] Cannot find plugin '{name}' in namespace '{namespace}'. "
                f"Please check your YAML config or ensure the plugin file exists."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        return cls._registry[namespace][name]

    @classmethod
    def autodiscover(cls, package_name: str = "zhixing.plugins"):
        logger.info(f"🔍 [PluginAutoDiscover] Scanning for plugins in package: '{package_name}'...")
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error(f"❌ [PluginAutoDiscover Failed] Cannot find package '{package_name}'. Error: {e}")
            return
        
        # Traverse all the modules under the package path
        count = 0
        for _, module_name, is_pkg in pkgutil.walk_packages(package.__path__, package.__name__ + '.'):
            try:
                # Dynamic import module, used to instantly trigger @PluginRegistry.register in the file
                importlib.import_module(module_name)
                count += 1
            except Exception as e:
                # If a user's custom plugin is written incorrectly
                # Print an error and skip it. Do not let the entire ZhiXing framework crash here
                logger.warning(
                    f"⚠️ [Plugin Import Error] Failed to load module '{module_name}'. "
                    f"It will be skipped. Error details: {e}"
                )
                continue
        logger.info(f"✨ [AutoDiscover Complete] Scanned {count} modules. Registry ready.")
        
    @classmethod
    def get_all_registered(cls) -> Dict[str, list]:
        """Return the list of all currently registered plugins

        Returns:
            Dict[str, list]: _description_
        """
        summary = {}
        for namespace, plugins in cls._registry.items():
            summary[namespace] = list(plugins.keys())
        return summary
        