import argparse
import logging
import os
import time
import yaml

from zhixing.utils.utils import get_core_logger
from zhixing.core.factory import PluginRegistry
from zhixing.engine.agent.agent_factory import AgentFactory
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.core.runner import AgentRunner
from zhixing.utils.utils import setup_logging

def bootstrap_plugins():
    """
    ✨ 使用自发现机制
    """
    # 1. 扫描核心引擎层 (如 modular_agent, eval_composite 等)
    PluginRegistry.autodiscover("zhixing.engine")
    
    # 2. 扫描业务插件层 (perception, reasoning, system_state 等)
    PluginRegistry.autodiscover("zhixing.plugins")

    # 3. 扫描物理设备层 (android, harmony 等)
    PluginRegistry.autodiscover("zhixing.devices")

def main():

    parser = argparse.ArgumentParser(description="ZhiXing Multi-Modal Agent Framework")
    # 🌟 将单一的 --config 拆分为大脑和试卷两个输入
    parser.add_argument("--agent", type=str, required=True, help="Path to Agent config (YAML)")
    parser.add_argument("--task", type=str, required=False, help="Path to Task/Benchmark config (JSON/YAML)")
    parser.add_argument("--secrets", type=str, default="secrets.yaml", help="Android Device Serial")
    parser.add_argument("--serial", type=str, default=None, help="Android Device Serial (optional)")
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="File log level. DEBUG enables full LLM prompts, plugin registration lines, and grid internals.",
    )
    args = parser.parse_args()

    task_id = int(time.time())
    
    log_dir = "temp/log"
    os.makedirs(log_dir, exist_ok=True)
    setup_logging(
        f"{log_dir}/session_{task_id}.log",
        log_level=getattr(logging, args.log_level),
    )

    # ==========================================
    # 1. 框架初始化与魔法装载
    # ==========================================
    logger = get_core_logger(phase="🚀 System", module_name="Main")
    logger.info("Initializing ZhiXing Framework...")
    
    bootstrap_plugins()
    
    # ==========================================
    # 2. 读取双配置并进行融合 (Merge Context)
    # ==========================================
    config = {}
    
    # 2.1 加载大脑配置 (Agent YAML)
    try:
        with open(args.agent, 'r', encoding='utf-8') as f:
            agent_config = yaml.safe_load(f)
            config.update(agent_config)
    except Exception as e:
        logger.error(f"❌ Failed to load Agent config [{args.agent}]: {e}")
        return

    # 2.2 加载考卷配置 (Task JSON) -> 统一处理为列表
    task_configs = [] 
    if args.task:
        try:
            with open(args.task, 'r', encoding='utf-8') as f:
                loaded_tasks = yaml.safe_load(f)
                # 如果传入的是个列表 [{}, {}] (比如你的 data_android.json)
                if isinstance(loaded_tasks, list):
                    task_configs = loaded_tasks
                # 如果传入的是单个字典 {} 
                elif isinstance(loaded_tasks, dict):
                    task_configs = [loaded_tasks]
        except Exception as e:
            logger.error(f"❌ Failed to load Task config [{args.task}]: {e}")
            return
        
    # 2.3 加载 Secrets 并复用 ParamHandler 注入全局变量
    secrets = {}
    if os.path.exists(args.secrets):
        try:
            with open(args.secrets, 'r', encoding='utf-8') as f:
                secrets = yaml.safe_load(f) or {}
            logger.info(f"🔐 Loaded secrets from {args.secrets}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load secrets file: {e}")
    
    # ✨ 魔法时刻：直接用你的工具类，把 config 里所有的 ${api_key} 替换成 secrets 里的真实值
    config = ParamHandler.render_placeholders(config, secrets)

    # print("\n\n")
    # print("task_configs: ", task_configs)
    
    device_config = config.get("device", {})
    device_name = device_config.get("name", "android") 
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
    
    context = { # 公文包
        "task_params": {}
    }
    # print(context)

    # ==========================================
    # 3. 组装大脑 (Build Agent)
    # ==========================================
    logger.info("🧠 Building Agent Brain...")
    try:
        agent = AgentFactory.build(config, device, context)
    except Exception as e:
        logger.error(f"❌ Agent Assembly Failed: {e}")
        return

    # ==========================================
    # 4. 🚀 智能双擎路由 (Smart Dual-Engine Routing)
    # ==========================================
    
    # 🌟 终极判断条件：只要 task_configs 里有东西，就是批量评测模式！
    if task_configs:
        logger.info(f"⚖️ Benchmark Mode: Found {len(task_configs)} tasks in the suite.")
        from zhixing.engine.benchmark.pipeline import BenchmarkPipeline
        
        pipeline = BenchmarkPipeline(device)
        
        for i, task_data in enumerate(task_configs):
            current_task_id = task_data.get("id", f"task_{i}")
            
            logger.info(f"\n" + "="*50)
            logger.info(f"▶️ RUNNING TASK {i+1}/{len(task_configs)}: [{current_task_id}]")
            logger.info("="*50)
            
            # 每次循环，给当前考题塞进独立的公文包
            task_context = {"task_params": task_data.copy()}
            
            try:
                final_result = pipeline.evaluate_task(task_data, agent, task_context)
                
                if final_result:
                    is_pass = getattr(final_result, 'is_pass', True)
                    status_emoji = "🏆 PASS" if is_pass else "💥 FAIL"
                    logger.info(f"{status_emoji} Task [{current_task_id}] Completed.")
            except Exception as e:
                logger.error(f"❌ Task [{current_task_id}] Pipeline Crashed: {e}", exc_info=True)
                
        logger.info(f"\n🎉 All {len(task_configs)} Benchmark Tasks Finished!")
            
    else:
        # 如果没有考卷，那就是瞎逛打工模式
        logger.info("🏃 Pure task mode detected (No Task Configs). Entering Agent Runner Mode.")
        
        max_steps = config.get("global_config", {}).get("max_steps", 15)
        runner = AgentRunner(device)
        
        try:
            trajectory = runner.run(agent, context, max_steps)
            logger.info(f"🏁 Agent Execution Finished. Total Steps: {len(trajectory)}")
        except Exception as e:
            logger.error(f"❌ Agent Runner Crashed: {e}", exc_info=True)

if __name__ == "__main__":
    main()