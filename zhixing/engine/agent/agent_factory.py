from typing import Dict, Any

from zhixing.core.factory import PluginRegistry
from zhixing.utils.utils import get_plugin_logger

class AgentFactory:
    """Agent Factory.
    
    Responsible for dynamically instantiating the correct overarching Agent architecture 
    (e.g., modular_agent, react_agent) based on the global configuration.
    """

    @classmethod
    def build(cls, config: Dict[str, Any], device: Any, context: Dict[str, Any] = None) -> Any:
        """Builds the Agent instance based on the YAML/JSON configuration.

        Args:
            config (Dict[str, Any]): The full parsed YAML/JSON configuration.
            device (Any): The ADB device wrapper instance.
            context (Dict[str, Any], optional): Execution context. Defaults to None.

        Returns:
            Any: An instantiated Agent orchestrator (e.g., ModularAgent).
            
        Raises:
            ValueError: If 'agent_type' is missing or not registered.
        """
        # 使用统一的高级日志，标识为 🏗️ Factory 阶段
        logger = get_plugin_logger(phase="🏗️ Agent Factory", namespace="engine.agent", plugin_name="AgentFactory")
        
        agent_type = config.get("agent_type")
        if not agent_type:
            logger.error("Missing 'agent_type' in configuration.")
            raise ValueError("Missing 'agent_type' in configuration (e.g., 'modular_agent').")
        
        logger.info(f"Building Agent Architecture: [{agent_type}]")

        # 提取专属于 Agent 内部的配置块 (对应 YAML 里的 agent: {...})
        # Keep top-level global_config visible to component builders so YAML can
        # define shared defaults such as default_llm outside the agent block.
        agent_config = dict(config.get("agent", {}) or {})
        if "global_config" not in agent_config and config.get("global_config") is not None:
            agent_config["global_config"] = config.get("global_config")
        
        # 从大一统注册表中拉取对应的 Agent 编排类 (比如找回我们写的 ModularAgent)
        try:
            # 注意：这里的 namespace 必须和 ModularAgent 顶部的注册 namespace 一致
            AgentClass = PluginRegistry.get_plugin(namespace="agent.type", name=agent_type)
        except ValueError:
            logger.error(f"Unregistered agent type: {agent_type}. Did you forget to import/register it?")
            raise ValueError(f"Unregistered agent type: {agent_type}. Please check your plugins.")
        
        # 实例化包工头，并把权利交给他 (它会在 __init__ 里去组装自己的 6 大组件)
        return AgentClass(config=agent_config, device=device, context=context)
