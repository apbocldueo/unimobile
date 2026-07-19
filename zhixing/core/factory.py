# Global Plugin registration center
import importlib
import pkgutil
import logging
from typing import Tuple, Any, Dict, Type
from zhixing.utils.utils import get_plugin_logger

logger = get_plugin_logger(
            phase="⚙️ Plugin Registry"
            , namespace="plugin"
            , plugin_name="registry"
        )

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
            logger.debug(f"Registered plugin {namespace} -> {name} ({plugin_class.__name__})")

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
    def get_plugin_under_prefix(cls, prefix: str, name: str) -> Type[Any]:
        """Look up *name* in *prefix* or in any registered sub-namespace ``prefix.<anything>``."""
        if prefix in cls._registry and name in cls._registry[prefix]:
            return cls._registry[prefix][name]
        dotted = prefix + "."
        hits = [
            ns
            for ns in sorted(cls._registry.keys())
            if ns.startswith(dotted) and name in cls._registry[ns]
        ]
        if not hits:
            error_msg = (
                f"❌ [Plugin Not Found] Cannot find plugin '{name}' under namespace prefix '{prefix}' "
                f"(exact or any '{prefix}.*'). Set 'namespace' or 'category' in config, or register the plugin."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        if len(hits) > 1:
            error_msg = (
                f"❌ [Ambiguous Plugin] '{name}' exists under multiple namespaces: {hits}. "
                f"Disambiguate with a full 'namespace' or a 'category' field (e.g. 'reset' -> '{prefix}.reset')."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        return cls._registry[hits[0]][name]

    @classmethod
    def resolve_benchmark_env_plugin(cls, env_conf: Dict[str, Any]) -> Type[Any]:
        """Resolve a benchmark ``environment_initializer`` plugin class.

        Resolution order:
        1. ``env_conf['namespace']`` if set — exact ``get_plugin(namespace, name)``.
        2. ``env_conf['category']`` if set — ``benchmark.environment.{category}``.
        3. Otherwise — *name* under ``benchmark.environment`` or any ``benchmark.environment.*`` (unique match).
        """
        name = env_conf.get("name")
        if not name:
            raise ValueError("environment_initializer entry is missing required field 'name'")
        if env_conf.get("namespace"):
            return cls.get_plugin(env_conf["namespace"], name)
        if env_conf.get("category"):
            return cls.get_plugin(f"benchmark.environment.{env_conf['category']}", name)
        return cls.get_plugin_under_prefix("benchmark.environment", name)

    @classmethod
    def autodiscover(cls, package_name: str = "zhixing.plugins"):
        logger.info("PluginAutoDiscover: scanning package %r", package_name)
        try:
            package = importlib.import_module(package_name)
        except ImportError as e:
            logger.error("PluginAutoDiscover: cannot import package %r: %s", package_name, e)
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
        logger.info("PluginAutoDiscover: finished package %r (%d modules imported)", package_name, count)
        
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
        