import sys
import os
import time
import logging
import argparse

sys.dont_write_bytecode = True
sys.path.append(os.getcwd())
LIBS_PATH = os.path.join(os.getcwd(), "libs", "AppAgent")
if LIBS_PATH not in sys.path:
    sys.path.append(LIBS_PATH)

from unimobile.utils.config_loader import ConfigLoader
from unimobile.utils.utils import load_yaml
from unimobile.core.runner import Runner
from unimobile.config.loggerFile import setup_logging

logger = logging.getLogger(__name__)

def run_agent(config_path, instruction, app_name=None, max_steps=15):
    """_summary_

    Args:
        config_path (_type_): _description_
        instruction (_type_): _description_
        app_name (_type_, optional): _description_. Defaults to None.
        max_steps (int, optional): _description_. Defaults to 15.
    """
    print("🔥 Initial Agent system...")
    task_id = int(time.time())
    
    log_dir = "temp/log"
    os.makedirs(log_dir, exist_ok=True)
    configs = load_yaml(config_path)
    if configs.get("global_config").get("verbose", False):
        setup_logging(f"{log_dir}/run_{task_id}.log")

    if not os.path.exists(config_path):
        print(f"❌ Error：The configuration file cannot be found: {config_path}")
        return

    # loading components
    loader = ConfigLoader(config_path)

    try:
        logger.info("========== Loading Component... ==========")
        
        # Connecting the device
        print("📱 Connecting the device...")
        device = loader.load_device()
        print(f"✅ The device connection was successful.: {device.__class__.__name__} (ID: {device.serial})")
        
        # 加载 Agent
        print("🤖 Being Initialized Agent (this may take some time)...")
        agent = loader.load_agent()
        print(f"✅ Agent has been successfully initialized")

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Initialization failed: {e}")
        return
    
    # Start Runner
    try:
        print("\n" + "="*40)
        print(f"🚀 Start carrying out the task")
        print(f"📝 Instruction: {instruction}")
        print("="*40 + "\n")

        # Initialize Runner
        runner = Runner(agent, device)

        runner_input = {
            "instruction": instruction,
            "app": app_name
        }

        logger.info(f"Runner Input: {runner_input}")
        
        # Run
        start_time = time.time()
        trajectory = runner.run(runner_input, max_steps=max_steps)
        end_time = time.time()

        duration = end_time - start_time
        print("\n" + "="*40)
        print("✅ The task execution is completed.")
        print(f"⏱️ Time Consuming: {duration:.2f} seconds")
        print(f"👣 Step number: {len(trajectory) if trajectory else 0}")
        print("="*40)
        
        logger.info(f"Trajectory: {trajectory}")

    except KeyboardInterrupt:
        print("\n🛑 The task was manually terminated")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ An error occurred during the task execution: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zhi Xing System")

    # Required parameter
    parser.add_argument("--config", type=str, required=True, help="The path of the YAML configuration file")
    parser.add_argument("--task", type=str, required=True, help="需要 Agent 执行的自然语言指令 (例如: '打开设置并调节亮度')")

    # Optional parameter
    parser.add_argument("--max_steps", type=int, default=15, help="Agent 执行的最大步数限制 (默认: 15)")

    args = parser.parse_args()

    run_agent(
        config_path=args.config,
        instruction=args.task,
        max_steps=args.max_steps
    )