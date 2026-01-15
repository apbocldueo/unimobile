import yaml
import os
import logging
from typing import Dict, Any, Union

from unimobile.core.interfaces import BaseAgent
from unimobile.devices.base import BaseDevice
from unimobile.utils.utils import load_yaml
from unimobile.utils.registry import (
    get_perception_class, get_reasoning_class, get_memory_class, 
    get_planner_class, get_strategy_class, get_device_class,
    get_verifier_class, get_llm_class
)

try:
    import unimobile.devices.harmony
    import unimobile.devices.android

    import unimobile.agents.components.perception.omniparser
    import unimobile.agents.components.perception.grid
    import unimobile.agents.components.perception.som

    import unimobile.agents.components.llm.openai_llm

    import unimobile.agents.components.memory.sliding_window
    import unimobile.agents.components.memory.summary_memory

    import unimobile.agents.components.reasoning.universal_reasoning

    import unimobile.agents.strategies.modular

    import unimobile.agents.components.verifier.screen_diff

    import unimobile.agents.parsers.jsona_action_parser
    import unimobile.agents.parsers.section_parser
    import unimobile.agents.parsers.mobimind_parser
except ImportError as e:
    print(f"[ConfigLoader] Components import failed: {e}")

logger = logging.getLogger(__name__)

class ConfigLoader:
    def __init__(self, config_path: str):
        self.config = load_yaml(config_path)

    def _create_instance(self, config_item: Union[str, Dict], getter_func, **extra_kwargs):
        if not config_item:
            return None
            
        if isinstance(config_item, str):
            name = config_item
            params = {}
        else:
            name = config_item.get("name")
            params = config_item.get("params", {})

        cls = getter_func(name)
        final_params = {**params, **extra_kwargs}
        
        try:
            return cls(**final_params)
        except TypeError as e:
            logger.error(f"Instantiation {name} Failed: {e}")
            raise

    def _load_llm(self, llm_config: Union[Dict, Any]) -> Any:
        if not llm_config:
            return None
            
        if "name" in llm_config:
            return self._create_instance(llm_config, get_llm_class)
        else:
            llm_group = {}
            for key, sub_config in llm_config.items():
                print(f"[Config] Loading sub-LLM: {key}")
                llm_group[key] = self._create_instance(sub_config, get_llm_class)
            return llm_group

    def load_device(self) -> BaseDevice:
        components_cfg = self.config.get("agent", {}).get("components", {})
        action_cfg = components_cfg.get("action")
        
        if not action_cfg:
            raise ValueError("Config missing 'agent.components.action' section.")
            
        logger.info(f"[Config] Loading Device/Action: {action_cfg.get('name')}")
        
        return self._create_instance(action_cfg, get_device_class)

    def load_agent(self) -> BaseAgent:
        global_config = self.config.get("global_config", {})
        verbose = global_config.get("verbose", True)
        
        strategy_name = self.config.get("agent_type", "modular_agent")
        logger.info(f"[Config] Agent Strategy: {strategy_name}")

        init_kwargs = global_config.copy()
        
        components_cfg = self.config.get("agent", {}).get("components", {})
        
        components_map = {
            "perception": get_perception_class,
            "reasoning": get_reasoning_class,
            "memory": get_memory_class,
            "planner": get_planner_class,
            "verifier": get_verifier_class,
        }

        key_alias = { }

        for comp_key, comp_cfg in components_cfg.items():
            if comp_key == "action": 
                continue 
                
            if not comp_cfg: continue

            getter = components_map.get(comp_key)
            if not getter:
                logger.warning(f"Unknown component type: {comp_key}, skipping")
                continue

            extra_args = {}
            
            if isinstance(comp_cfg, dict) and "llm" in comp_cfg:
                specific_llm = self._load_llm(comp_cfg.get("llm"))
                extra_args["llm_client"] = specific_llm
            
            if isinstance(comp_cfg, list):
                instance = [self._create_instance(c, getter, **extra_args) for c in comp_cfg]
                names = [c.get("name") for c in comp_cfg]
                logger.info(f"Loading {comp_key} (List): {names}")
            else:
                instance = self._create_instance(comp_cfg, getter, **extra_args)
                logger.info(f"Loading {comp_key}: {comp_cfg.get('name')}")

            arg_name = key_alias.get(comp_key, comp_key)
            init_kwargs[arg_name] = instance

        AgentClass = get_strategy_class(strategy_name)
        logger.info(f"[Config] Instantiating Agent: {AgentClass.__name__}")

        try:
            return AgentClass(**init_kwargs)
        except TypeError as e:
            logger.error(f"Agent init failed: {e}")
            raise