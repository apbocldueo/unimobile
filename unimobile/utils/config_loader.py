# unimobile/utils/config_loader.py
import yaml
import os
import logging
from typing import Dict, Any, Union

from unimobile.core.interfaces import BaseAgent, BaseBrain, BasePlanner
from unimobile.devices.base import BaseDevice
from unimobile.utils.registry import (
    get_perception_class, get_brain_class, get_memory_class, 
    get_planner_class, get_strategy_class, get_device_class,
    get_verifier_class
)

# === Key: The component library must be imported to trigger the @register decorator ===
# TODO Bach import in __init__
try:
    import unimobile.devices.harmony
    import unimobile.devices.android

    import unimobile.agents.components.perception.omniparser
    import unimobile.agents.components.perception.grid
    import unimobile.agents.components.perception.som
    
    import unimobile.agents.components.llm.openai_llm

    import unimobile.agents.components.memory.sliding_window
    import unimobile.agents.components.memory.summary_memory

    import unimobile.agents.components.brain.decider_brain

    import unimobile.agents.strategies.modular

    import unimobile.agents.components.verifier.screen_diff

    import unimobile.agents.parsers.jsona_action_parser
    import unimobile.agents.parsers.section_parser
    import unimobile.agents.parsers.mobimind_parser
except ImportError as e:
    print(f"[ConfigLoader] Components import failed(some components may not be loaded): {e}")

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_path: str):
        self.config = self._load_yaml(config_path)

    def _load_yaml(self, path: str) -> Dict:
        if not os.path.exists(path):
            raise FileNotFoundError(f"The configuration file was not found: {path}")
        with open(path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _create_instance(self, config_item: Union[str, Dict], getter_func, **extra_kwargs):
        """Instantiation 

        Args:
            config_item (Union[str, Dict]): config
            getter_func (_type_): registry get_xxx_class function

        Returns:
            _type_: _description_
        """
        if not config_item:
            return None
            
        if isinstance(config_item, str):
            name = config_item
            params = {}
        else:
            name = config_item.get("name")
            params = config_item.get("params", {})

        cls = getter_func(name)
        
        # Merge
        final_params = {**params, **extra_kwargs}
        
        try:
            return cls(**final_params)
        except TypeError as e:
            logger.error(f"Instantiation {name} Fail，please check the parameter matching: {e}")
            raise
    
    def _load_llm(self, llm_config: Union[Dict, Any]) -> Dict:
        """Loading LLM

        Args:
            llm_config (Union[Dict, Any]): LLM config

        Returns:
            Dict: LLM
        """
        if not llm_config:
            return None
            
        if "name" in llm_config:
            return self._create_instance(llm_config, get_brain_class)
            
        else:
            llm_group = {}
            for key, sub_config in llm_config.items():
                print(f"[Config] Loading sub model: {key}")
                llm_group[key] = self._create_instance(sub_config, get_brain_class)
            return llm_group
    
    def load_agent(self) -> BaseAgent:
        """Loading agent

        Returns:
            BaseAgent
        """
        agent_cfg = self.config.get("agent", {})

        strategy_name = agent_cfg.get("strategy", "modular_agent")

        logger.info(f"Agent Strategy is: {strategy_name}")

        init_kwargs = agent_cfg.get("params", {}).copy()
        if init_kwargs:
            logger.info(f"Strategy Params: {init_kwargs}")

        components_cfg = agent_cfg.get("components", {})

        components_map = {
            "perception": get_perception_class,
            "brain": get_brain_class,
            "memory": get_memory_class,
            "planner": get_planner_class,
            "verifier": get_verifier_class
        }

        default_llm_cfg = self.config.get("default_llm")
        if default_llm_cfg:
            logger.info(f"Default LLM: {default_llm_cfg.get('name')}")
        default_llm_instance = self._load_llm(default_llm_cfg)

        for comp_key, comp_cfg in components_cfg.items():
            if not comp_cfg: continue

            getter = components_map.get(comp_key)
            if not getter:
                logger.warning(f"Unknown component type: {comp_key}, skipping")
                continue
            
            icon_map = {
                "perception": "perception",
                "brain": "brain",
                "memory": "memory",
                "planner": "planner",
                "verifier": "verifier"
            }
            icon = icon_map.get(comp_key, "agent")

            if isinstance(comp_cfg, list):
                names = [c.get("name") for c in comp_cfg if isinstance(c, dict)]
                logger.info(f"{icon} Loading {comp_key} (List): {names}")
            else:
                name = comp_cfg.get("name")
                logger.info(f"{icon} Loading {comp_key}: {name}")
                
                if comp_cfg.get("llm"):
                     logger.info(f"   ↳ Using specific LLM for {comp_key}: {comp_cfg['llm'].get('name')}")

            extra_args = {}
            if comp_key in ["brain", "planner", "verifier", "memory"]:
                specific_llm = self._load_llm(comp_cfg.get("llm"))
                
                extra_args["llm_client"] = specific_llm if specific_llm else default_llm_instance
            
            if isinstance(comp_cfg, list):
                instance = [self._create_instance(c, getter, **extra_args) for c in comp_cfg]
            else:
                instance = self._create_instance(comp_cfg, getter, **extra_args)
            
            init_kwargs[comp_key] = instance

        AgentClass = get_strategy_class(strategy_name)
        logger.info(f"========== Instantiating Agent Class: {AgentClass.__name__} ==========")
        logger.info("\n")

        try:
            return AgentClass(**init_kwargs)
        except TypeError as e:
            logger.error(f"Agent initialization failed. Parameters do not match: {e}")
            raise

    def load_device(self) -> BaseDevice:
        """Loading device

        Returns:
            BaseDevice
        """
        device_cfg = self.config.get("device")
        logger.info(f"device_cfg is: {device_cfg}")
        if not device_cfg:
            raise ValueError("The device section is missing in the configuration file")
            
        print(f"[Config]  Being initialized device: {device_cfg.get('name')}")
        return self._create_instance(device_cfg, get_device_class)
    
