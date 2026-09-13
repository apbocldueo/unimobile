import logging
import os
from typing import Any, MutableMapping

import yaml


def load_yaml(path: str) -> Any:
    """Load a YAML file (UTF-8). Used by config loaders."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(
    log_file: str = "app.log",
    *,
    log_level: int = logging.INFO,
) -> logging.Logger:
    """Configure root logging: one UTF-8 file handler, consistent format, noisy HTTP libs capped."""
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-5s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(log_level)

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(log_level)
    root.addHandler(file_handler)

    for noisy in ("httpx", "httpcore", "urllib3", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    return root


class ZhiXingLoggerAdapter(logging.LoggerAdapter):
    """Prefix messages with phase and scope for readable multi-module logs."""

    def process(self, msg: Any, kwargs: MutableMapping[str, Any]) -> tuple[Any, MutableMapping[str, Any]]:
        phase = self.extra.get("phase", "System")
        scope = self.extra.get("scope", "unknown")
        return f"[{phase.ljust(14)}] [{scope}] {msg}", kwargs


def get_plugin_logger(phase: str, namespace: str, plugin_name: str) -> logging.LoggerAdapter:
    """Logger for plugins: scope is ``namespace::plugin_name``."""
    base_logger = logging.getLogger("ZhiXing.Plugin")
    scope = f"{namespace}::{plugin_name}"
    return ZhiXingLoggerAdapter(base_logger, {"phase": phase, "scope": scope})


def get_core_logger(phase: str, module_name: str) -> logging.LoggerAdapter:
    """Logger for core / engine entrypoints (run, pipeline, factory, etc.)."""
    base_logger = logging.getLogger("ZhiXing.Core")
    return ZhiXingLoggerAdapter(base_logger, {"phase": phase, "scope": module_name})
