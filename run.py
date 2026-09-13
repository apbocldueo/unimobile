import argparse
import logging
import os
import time
import yaml

from zhixing.utils.utils import get_core_logger
from zhixing.core.factory import PluginRegistry
from zhixing.engine.agent.agent_factory import AgentFactory
from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.utils.utils import setup_logging
from zhixing.config.contracts import (
    ContractValidationError,
    load_agent_yaml,
    load_benchmark_json,
)
from zhixing.config.contracts.diagnostics import raise_for_errors
from zhixing.config.contracts.registry_validation import (
    validate_agent_registry,
    validate_benchmark_registry,
)

def bootstrap_plugins():
    """
    ✨ 使用自发现机制
    """
    # 1. 扫描核心引擎层 (如 modular_agent, eval_composite 等)
    reports = [PluginRegistry.autodiscover("zhixing.engine")]
    
    # 2. 扫描业务插件层 (perception, reasoning, system_state 等)
    reports.append(PluginRegistry.autodiscover("zhixing.plugins"))

    # 3. 扫描物理设备层 (android, harmony 等)
    reports.append(PluginRegistry.autodiscover("zhixing.devices"))
    return tuple(reports)

def main():

    parser = argparse.ArgumentParser(description="ZhiXing Multi-Modal Agent Framework")
    # 🌟 将单一的 --config 拆分为大脑和试卷两个输入
    parser.add_argument("--agent", type=str, required=True, help="Path to Agent config (YAML)")
    parser.add_argument("--task", type=str, required=False, help="Path to Task/Benchmark config (JSON/YAML)")
    parser.add_argument("--secrets", type=str, default="secrets.yaml", help="Android Device Serial")
    parser.add_argument("--serial", type=str, default=None, help="Android Device Serial (optional)")
    parser.add_argument(
        "--max_steps",
        type=int,
        default=None,
        help="Agent step limit for Benchmark/interactive mode when a task JSON has no max_steps. "
        "Priority per task: task JSON max_steps > this flag > 15.",
    )
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
    # 1. Load and validate the two independent contracts before side effects
    # ==========================================
    logger = get_core_logger(phase="🚀 System", module_name="Main")
    logger.info("Initializing ZhiXing Framework...")

    agent_model = None
    try:
        agent_model = load_agent_yaml(args.agent)
        config = agent_model.canonical_dict()
    except Exception as e:
        logger.error(f"❌ Failed to load Agent config [{args.agent}]: {e}")
        return

    benchmark_model = None
    task_configs = []
    if args.task:
        try:
            benchmark_model = load_benchmark_json(args.task)
            task_configs = benchmark_model.canonical_list()
        except Exception as e:
            logger.error(f"❌ Failed to load Task config [{args.task}]: {e}")
            return

    # ==========================================
    # 2. Discover plugins and validate configured names without instantiation
    # ==========================================
    discovery_reports = bootstrap_plugins()
    try:
        raise_for_errors(
            validate_agent_registry(agent_model, discovery_reports=discovery_reports)
        )
        if benchmark_model is not None:
            raise_for_errors(
                validate_benchmark_registry(
                    benchmark_model, discovery_reports=discovery_reports
                )
            )
    except ContractValidationError as e:
        logger.error("❌ Registry validation failed: %s", e)
        return

    # ==========================================
    # 3. Resolve secrets only after both contracts and plugin references are valid
    # ==========================================
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
    # 4. 组装大脑 (Build Agent)
    # ==========================================
    logger.info("🧠 Building Agent Brain...")
    try:
        agent = AgentFactory.build(config, device, context)
    except Exception as e:
        logger.error(f"❌ Agent Assembly Failed: {e}")
        return

    # ==========================================
    # 5. 启动模式：--task 为评测流水线；不传 --task 为 AgentRunner 纯执行（交互输入任务）
    # ==========================================

    if args.task:
        context["global_config"] = dict(config.get("global_config") or {})
        if args.max_steps is not None:
            context["cli_max_steps"] = args.max_steps
        # 完整流程：BenchmarkPipeline（任务初始化、环境初始化、评测与打分）
        cli_hint = (
            str(args.max_steps)
            if args.max_steps is not None
            else "not set (per-task JSON max_steps, else default 15)"
        )
        logger.info(
            f"⚖️ Benchmark Mode: Found {len(task_configs)} tasks in the suite. "
            f"CLI max_steps={cli_hint}"
        )
        from zhixing.engine.benchmark.pipeline import BenchmarkPipeline

        finalize_human_review_session = None
        init_human_review_session = None
        build_experiment_run_config = None
        try:
            from experiment.human_review_output import (
                build_experiment_run_config,
                finalize_human_review_session,
                init_human_review_session,
            )
        except ImportError:
            logger.warning(
                "未找到 experiment/human_review_output.py（本地实验目录，默认不纳入 Git）。"
                "将跳过 human_review 文件导出；截图标注亦不可用，直至在仓库根目录添加该模块。"
            )

        pipeline = BenchmarkPipeline(device)

        human_review_dir = None
        experiment_run_config = None
        if finalize_human_review_session is not None:
            human_review_dir = os.path.join(os.getcwd(), "temp", "human_review", f"session_{task_id}")
            os.makedirs(human_review_dir, exist_ok=True)
            logger.info("📂 Human review pack (per session): %s", os.path.abspath(human_review_dir))

            if build_experiment_run_config is not None:
                experiment_run_config = build_experiment_run_config(
                    config,
                    agent_config_path=os.path.abspath(args.agent),
                    task_config_path=os.path.abspath(args.task) if args.task else None,
                    benchmark_session_id=str(task_id),
                    cli_args={
                        "agent": os.path.abspath(args.agent),
                        "task": os.path.abspath(args.task) if args.task else None,
                        "max_steps": args.max_steps,
                        "log_level": args.log_level,
                        "secrets": os.path.abspath(args.secrets) if args.secrets else None,
                        "serial": args.serial,
                    },
                )
            if init_human_review_session is not None:
                log_hint = os.path.abspath(os.path.join(log_dir, f"session_{task_id}.log"))
                init_human_review_session(
                    human_review_dir,
                    str(task_id),
                    agent_config_path=os.path.abspath(args.agent),
                    effective_config=config,
                    experiment_run_config=experiment_run_config,
                    log_file_hint=log_hint,
                )
                logger.info("📋 Human review header written: %s", os.path.join(human_review_dir, "HUMAN_REVIEW.md"))

        for i, task_data in enumerate(task_configs):
            current_task_id = task_data.get("id", f"task_{i}")

            logger.info("")
            logger.info("=" * 62)
            logger.info(
                "          >>     DATASET ITEM   %d / %d     <<          [ %s ]",
                i + 1,
                len(task_configs),
                current_task_id,
            )
            logger.info("=" * 62)
            logger.info("")

            # Inherit session-level keys (max_steps, global_config, evaluator_llm, …) from parent context.
            task_context = dict(context)
            task_context["task_params"] = task_data.copy()
            task_context["screenshot_session_id"] = str(task_id)
            if human_review_dir is not None:
                task_context["human_review_dir"] = human_review_dir
                task_context["benchmark_session_id"] = str(task_id)
                if experiment_run_config is not None:
                    task_context["experiment_run_config"] = experiment_run_config

            try:
                final_result = pipeline.evaluate_task(task_data, agent, task_context)

                if final_result:
                    is_pass = getattr(final_result, "is_pass", True)
                    status_emoji = "🏆 PASS" if is_pass else "💥 FAIL"
                    logger.info(f"{status_emoji} Task [{current_task_id}] Completed.")
            except Exception as e:
                logger.error(f"❌ Task [{current_task_id}] Pipeline Crashed: {e}", exc_info=True)

        logger.info(f"\n🎉 All {len(task_configs)} Benchmark Tasks Finished!")
        if finalize_human_review_session is not None and human_review_dir:
            review_paths = finalize_human_review_session(
                human_review_dir,
                str(task_id),
                os.path.abspath(os.path.join(log_dir, f"session_{task_id}.log")),
                experiment_run_config=experiment_run_config,
            )
            logger.info("📋 Human review index (Markdown): %s", review_paths["markdown"])
            logger.info("📋 Human review manifest (JSON): %s", review_paths["manifest_summary"])

    else:
        # AgentRunner 纯执行：不跑考卷、不做环境初始化与评测，仅按用户输入的任务描述循环执行
        logger.info(
            "🏃 AgentRunner interactive mode (no --task): reading task description from stdin."
        )
        try:
            user_instruction = input("输入你想要实现的任务：\n").strip()
        except EOFError:
            logger.error("❌ No task input received (EOF).")
            return
        if not user_instruction:
            logger.error("❌ Task description cannot be empty.")
            return

        context["task_params"] = {"instruction": user_instruction}
        context["screenshot_session_id"] = str(task_id)

        max_steps = args.max_steps if args.max_steps is not None else 15
        from zhixing.core.runner import AgentRunner

        runner = AgentRunner(device)

        try:
            trajectory = runner.run(agent, context, max_steps)
            logger.info(f"🏁 Agent Execution Finished. Total Steps: {len(trajectory)}")
        except Exception as e:
            logger.error(f"❌ Agent Runner Crashed: {e}", exc_info=True)

if __name__ == "__main__":
    main()
