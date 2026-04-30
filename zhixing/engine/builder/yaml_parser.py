import os
import yaml
import logging
from typing import Dict

from zhixing.core.agent.interfaces import BaseAgent
from zhixing.devices.base import BaseDevice

logger = logging.getLogger(__name__)

class YamlParser:
    def __init__(self, config_path: str, secret_path: str = "secrets.yaml") -> None:
        """YamlParser: Be responsible for parsing YAML and pulling up the Agent

        Args:
            config_path (str): yaml path
        """
        self.config_path = config_path

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
    def _load_secrets(secret_path):
        
        if os.path.exists(secret_path):
            logger.info(f"🔑 Found secrets file: {secret_path}")
            return YamlParser._load_yaml(secret_path)
        else:
            logger.warning("⚠️ No secrets.yaml found in configs/. placeholders like ${KEY} may fail.")
            return {}