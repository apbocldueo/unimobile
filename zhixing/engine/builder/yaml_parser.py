import os
import yaml
from typing import Dict

from zhixing.core.agent.interfaces import BaseAgent
from zhixing.devices.base import BaseDevice






class YamlParser:
    def __init__(self, config_path: str, secrets_path: str = "secrets.yaml") -> None:
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
