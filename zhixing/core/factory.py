# Global Plugin registration center
import importlib
import pkgutil
import logging
from typing import Tuple, Any, Dict


logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    ZhiXing framework the global plugin registry.
    Two-dimensional dictionary storage based on namespaces, implemented to achieve decoupling and dynamic dependency injection
    """
    @classmethod
    def register(cls, namespace: str, name: str):
        pass

    @classmethod
    def get_plugin(cls, namespace: str, name: str) -> Tuple[Any]:
        pass

    @classmethod
    def autodiscover(cls, package_name: str = "zhixing.plugins"):
        pass

    @classmethod
    def get_all_registered(cls) -> Dict[str, list]:
        pass