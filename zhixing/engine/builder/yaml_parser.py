import os
import re
import yaml
from typing import Dict, Any

from zhixing.core.agent.interfaces import BaseAgent
from zhixing.devices.base import BaseDevice
from zhixing.utils.utils import get_plugin_logger

logger = get_plugin_logger(phase="🔍 YamlParser", namespace="engine.builder", plugin_name="YamlParser")

class YamlParser:
    def __init__(self, config_path: str, secrets_path: str = "secrets.yaml") -> None:
        """YamlParser: Be responsible for parsing YAML and pulling up the Agent

        Args:
            config_path (str): yaml path
        """
        self.config_path = config_path

        self.raw_config = self._load_yaml(config_path)
        self.secrets = self._load_secrets(secrets_path)
        self.config = self._inject_secrets(self.raw_config, self.secrets)

    def load_agent(self) -> tuple[BaseDevice, BaseAgent]:
        """loading Agent and Device

        Returns:
            tuple[BaseDevice, BaseAgent]: Device and Agent
        """
        device = None
        agent = None
        return device, agent

    @staticmethod
    def _load_yaml(path: str) -> Dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Config file not found: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    @staticmethod
    def _load_secrets(secrets_path):
        
        if os.path.exists(secrets_path):
            logger.info("secrets file found: %s", secrets_path)
            return YamlParser._load_yaml(secrets_path)
        else:
            logger.warning("no secrets.yaml in configs/; ${KEY} placeholders may fail")
            return {}
        
    def _inject_secrets(self, data, secrets) -> Any:
        """Recursively replace the placeholder variable ${key} in the data structure

        Replacement rule:
        1. look for values from the incoming "secrets" dictionary
        2. If you can't find it, look for it in the system environment variables again
        3. Replace the corresponding part of the data after finding it

        Args:
            data (Any): Any data (str/dict/list)
            secrets (dict): The key/variable dictionary in the configuration file

        Returns:
            same data: The new data after the replacement is completed
        """
        if isinstance(data, dict):
            return {k: self._inject_secrets(v, secrets) for k, v in data.items()}
        elif isinstance(data, list):
            return [self._inject_secrets(i, secrets) for i in data]
        elif isinstance(data, str):
            pattern = re.compile(r'\$\{(\w+)\}')
            matches = pattern.findall(data)
            
            new_val = data
            for key in matches:
                secret_val = secrets.get(key, os.getenv(key))
                
                if secret_val:
                    new_val = new_val.replace(f"${{{key}}}", str(secret_val))
                else:
                    logger.warning("no value for placeholder ${%s} in secrets or env", key)
            return new_val
        else:
            return data