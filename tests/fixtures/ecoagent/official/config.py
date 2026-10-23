"""Configuration loader for EcoAgent.

This module provides utilities to load and manage configuration from config.yaml file.
"""

import os
import yaml
from typing import Any, Dict, Optional


class ConfigLoader:
    """Loads and manages configuration from config.yaml."""

    def __init__(self, config_path: str = "config.yaml"):
        """Initialize config loader.
        
        Args:
            config_path: Path to the config.yaml file. Defaults to "config.yaml" in current directory.
        
        Raises:
            FileNotFoundError: If config file is not found.
            yaml.YAMLError: If config file is not valid YAML.
        """
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        if self.config is None:
            raise ValueError(f"Config file is empty: {config_path}")

    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM (Large Language Model) configuration."""
        return self.config.get('llm', {})

    def get_slm_config(self) -> Dict[str, Any]:
        """Get SLM (Small Language Model / UI-TARS) configuration."""
        return self.config.get('slm', {})

    def get_vision_config(self) -> Dict[str, Any]:
        """Get vision model configuration."""
        return self.config.get('vision', {})

    def get_m3a_config(self) -> Dict[str, Any]:
        """Get M3A model configuration."""
        return self.config.get('m3a', {})

    def get_api_key(self, env_var_name: str) -> str:
        """Get API key from environment variable.
        
        Args:
            env_var_name: Name of the environment variable to read from.
        
        Returns:
            The API key value.
        
        Raises:
            RuntimeError: If environment variable is not set.
        """
        api_key = os.environ.get(env_var_name)
        if not api_key:
            raise RuntimeError(f"Environment variable '{env_var_name}' is not set. Please set it before running the agent.")
        return api_key

    def get_llm_api_key(self) -> str:
        """Get LLM API key from environment variable."""
        llm_config = self.get_llm_config()
        env_var = llm_config.get('api_key_env_var', 'OPENAI_API_KEY')
        return self.get_api_key(env_var)

    def get_m3a_api_key(self) -> str:
        """Get M3A API key from environment variable."""
        m3a_config = self.get_m3a_config()
        env_var = m3a_config.get('api_key_env_var', 'MODELSCOPE_TOKEN')
        return self.get_api_key(env_var)


def load_config(config_path: str = "config.yaml") -> ConfigLoader:
    """Load configuration from config.yaml.
    
    Args:
        config_path: Path to the config.yaml file.
    
    Returns:
        ConfigLoader instance.
    """
    return ConfigLoader(config_path)
