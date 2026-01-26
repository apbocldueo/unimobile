import sys
import os
import time
import logging
import argparse

sys.dont_write_bytecode = True
sys.path.append(os.getcwd())
LIBS_PATH = os.path.join(os.getcwd(), "plugins")
if LIBS_PATH not in sys.path:
    sys.path.append(LIBS_PATH)

from unimobile.utils.config_loader import ConfigLoader
from unimobile.core.runner import Runner
from unimobile.config.loggerFile import setup_logging

logger = logging.getLogger(__name__)

def init_session(config_path):
    """
    Step 1: Initialize the system (Load Config, Device, Agent)
    This runs ONLY ONCE.
    """
    print("\n🔥 Initializing Agent System...")
    task_id = int(time.time())
    
    log_dir = "temp/log"
    os.makedirs(log_dir, exist_ok=True)
    setup_logging(f"{log_dir}/session_{task_id}.log")

    if not os.path.exists(config_path):
        print(f"❌ Error：The configuration file cannot be found: {config_path}")
        return None, None

    # loading components
    loader = ConfigLoader(config_path)

    try:
        logger.info("========== Loading Component... ==========")
        
        # Connecting the device
        print("📱 Connecting the device...")
        device = loader.load_device()
        print(f"✅ Device connected: {device.__class__.__name__} (ID: {device.serial})")
        
        # Load Agent
        print("🤖 Initializing Agent (this may take some time)...")
        agent = loader.load_agent()
        print(f"✅ Agent initialized successfully")
        
        return agent, device

    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ Initialization failed: {e}")
        return None, None

def run_single_task(agent, device, instruction, max_steps=15):
    """
    Step 2: Execute a specific task using the initialized agent.
    This can be called multiple times.
    """
    try:
        print("\n" + "="*40)
        print(f"🚀 Start carrying out the task")
        print(f"📝 Instruction: {instruction}")
        print("="*40 + "\n")

        # Initialize Runner (Runner is usually lightweight and can be re-instantiated or reset)
        runner = Runner(agent, device)

        runner_input = {
            "instruction": instruction,
            "app": None # App name is usually inferred or handled by planner
        }

        logger.info(f"Runner Input: {runner_input}")
        
        # Run
        start_time = time.time()
        trajectory = runner.run(runner_input, max_steps=max_steps)
        end_time = time.time()

        duration = end_time - start_time
        print("\n" + "-"*40)
        print("✅ Current task completed.")
        print(f"⏱️ Time Consuming: {duration:.2f} seconds")
        print(f"👣 Step number: {len(trajectory) if trajectory else 0}")
        print("-"*40)
        
        logger.info(f"Trajectory: {trajectory}")

    except KeyboardInterrupt:
        print("\n🛑 Task manually interrupted by user.")
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ An error occurred during this task: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Zhi Xing System - Interactive Mode")

    # Required parameter
    parser.add_argument("--config", type=str, required=True, help="The path of the YAML configuration file")
    
    # Optional: User can still provide a first task via CLI if they want
    parser.add_argument("--task", type=str, default=None, help="Optional: First task to run immediately")
    parser.add_argument("--max_steps", type=int, default=30, help="Max steps per task")

    args = parser.parse_args()

    # 1. Initialize once
    agent, device = init_session(args.config)

    if agent and device:
        # 2. Run the first task if provided via CLI
        if args.task:
            run_single_task(agent, device, args.task, args.max_steps)

        # 3. Enter Interactive Loop
        print("\n✨ System Ready. Enter your next task below (or type 'exit'/'q' to quit).")
        
        while True:
            try:
                # Get input from user
                user_input = input("\n👤 User Task >>> ").strip()
                
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("👋 Exiting Zhi Xing System. Bye!")
                    break
                
                if not user_input:
                    continue
                
                # Execute the new task
                run_single_task(agent, device, user_input, args.max_steps)
                
            except KeyboardInterrupt:
                print("\n👋 Exiting...")
                break