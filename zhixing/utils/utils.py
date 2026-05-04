import os
import logging
from typing import Any, MutableMapping

################################## Logger ##################################
# set logger
def setup_logging(log_file="app.log", log_level=logging.INFO):
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    formatter = logging.Formatter("%(message)s - %(asctime)s - %(name)s - %(levelname)s")
    
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    logger.addHandler(file_handler)

    return logger

################################## Logger Adapter ##################################

class ZhiXingLoggerAdapter(logging.LoggerAdapter):
    """Low-level formatting: 
    Responsible for arranging strings as neatly as a table

    Args:
        logging (_type_): _description_
    """
    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        phase = self.extra.get('phase', '⚙️ System')
        scope = self.extra.get('scope', 'unknown')

        # Uniform format: 
        # [stage] [scope] ➜ information
        return f"[{phase.ljust(14)}] [{scope}] ➜ {msg}", kwargs
    
import os
import logging


# set logger
def setup_logging(log_file="app.log", log_level=logging.INFO):
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    # formatter = logging.Formatter("%(message)s - %(asctime)s - %(name)s - %(levelname)s")
    
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-7s] [%(name)s] ➜ %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.setLevel(log_level)
    if not logger.handlers:
        logger.addHandler(file_handler)

    return logger

def get_plugin_logger(phase: str, namespace: str, plugin_name: str) -> logging.LoggerAdapter:
    """Tailor-made for "plugins"!
    The parameters clearly require the namespace and name.

    Automatically spell "namespace" and "name" into the format [namespace::name] for you.

    Args:
        phase (str): _description_
        namespace (str): _description_
        plugin_name (str): _description_

    Returns:
        logging.LoggerAdapter: _description_
    """
    
    base_logger =  logging.getLogger("ZhiXing.Plugin")
    scope = f"{namespace}::{plugin_name}"

    return ZhiXingLoggerAdapter(base_logger, {"phase": phase, "scope": scope})


def get_core_logger(phase: str, module_name: str) -> logging.LoggerAdapter:
    """Tailor-made for "core processes/engines"! 
    The parameter only requires passing module_name

    Adapt to non-plugin infrastructure code such as: run.py, pipeline.py, factory.py, etc.

    Args:
        phase (str): _description_
        module_name (str): _description_

    Returns:
        logging.LoggerAdapter: _description_
    """
    base_logger = logging.getLogger("ZhiXing.Core")

    return ZhiXingLoggerAdapter(base_logger, {"phase": phase, "scope": module_name})
