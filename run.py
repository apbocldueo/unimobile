import os
import argparse
import yaml

from zhixing.utils.utils import get_plugin_logger
from zhixing.core.factory import PluginRegistry
from zhixing.engine.agent.agent_factory import AgentFactory
from zhixing.core.runner import AgentRunner

def bootstrap_plugins():
    """
    ✨ 使用自发现机制
    """
    # 1. 扫描核心引擎层 (如 modular_agent, eval_composite 等)
    PluginRegistry.autodiscover("zhixing.engine")
    
    # 2. 扫描业务插件层 (perception, reasoning, system_state 等)
    PluginRegistry.autodiscover("zhixing.plugins")

    PluginRegistry.autodiscover("zhixing.devices")

def main():
    parser = argparse.ArgumentParser(description="ZhiXing Multi-Modal Agent Framework")
    parser.add_argument("--config", type=str, required=True, help="Path to task config (YAML/JSON)")
    parser.add_argument("--serial", type=str, default=None, help="Android Device Serial (optional)")
    args = parser.parse_args()

    # ==========================================
    # 1. 框架初始化与魔法装载
    # ==========================================
    logger = get_plugin_logger(phase="🚀 System", namespace="core", plugin_name="Main")
    logger.info("Initializing ZhiXing Framework...")
    
    bootstrap_plugins()
    
    # ==========================================
    # 2. 读取配置与准备上下文
    # ==========================================
    try:
        with open(args.config, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"❌ Failed to load config file {args.config}: {e}")
        return

    device_config = config.get("device", {})
    device_name = device_config.get("name", "android_device") 
    device_params = device_config.get("params", {}).copy()

    # 命令行优先级最高，覆盖 YAML 配置
    if args.serial:
        device_params["serial"] = args.serial

    logger.info(f"📱 Connecting to physical environment: [{device_name}]...")
    try:
        DeviceClass = PluginRegistry.get_plugin(namespace="device", name=device_name)
        device = DeviceClass(**device_params)
        logger.info(f"✅ Device connected.")
    except Exception as e:
        logger.error(f"❌ Device Connection Failed: {e}")
        return
    
    context = {
        "task_params": config.get("task", {})
    }
