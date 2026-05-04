import logging
from typing import Dict, Any, Optional

from zhixing.utils.utils import get_plugin_logger
from zhixing.core.runner import AgentRunner
from zhixing.core.factory import PluginRegistry

# 假设你的引擎里有这两个工厂（对应你目录里的文件）
from zhixing.engine.benchmark.eval_factory import EvaluatorFactory
from zhixing.core.benchmark.param_hander import ParamHandler

class BenchmarkPipeline:
    """Coordinates the entire benchmark execution lifecycle.

    This pipeline acts as the chief examiner. It is responsible for setting up 
    the evaluation environment, rendering dynamic task parameters, orchestrating 
    the agent's execution via the AgentRunner, and finally grading the trajectory 
    using the constructed EvaluatorTree.

    Attributes:
        device (Any): The physical or simulated device interface (e.g., AndroidDevice).
        logger (logging.Logger): The logger instance for the benchmark phase.
        agent_runner (AgentRunner): The runner responsible for the agent's interaction loop.
    """

    _pipeline_phase = "⚖️ Benchmark"

    def __init__(self, device: Any) -> None:
        """Initializes the BenchmarkPipeline with the target device.

        Args:
            device (Any): The ADB device wrapper instance.
        """
        self.logger = get_plugin_logger(
            phase=self._pipeline_phase, 
            namespace="engine.benchmark", 
            plugin_name=self.__class__.__name__
        )
        self.device = device
        self.agent_runner = AgentRunner(device)
    
    def evaluate_task(self, benchmark_config: Dict[str, Any], agent: Any, context: Dict[str, Any]) -> Optional[Any]:
        """Executes a single benchmark task from start to finish.

        Args:
            benchmark_config (Dict[str, Any]): The benchmark configuration block 
                (usually parsed from a JSON/YAML file) containing initializers and evaluators.
            agent (Any): The instantiated Agent object ready to perform the task.
            context (Dict[str, Any]): The global execution context that will be updated 
                and shared across components.

        Returns:
            Optional[Any]: The final evaluation result object if an evaluator exists, 
                otherwise None.
        """
        task_id = benchmark_config.get('id', 'Unknown')
        self.logger.info(f"========== Start Benchmark: {task_id} ==========")

        # ==========================================
        # Step 1: Dynamic Parameter Generation & Rendering
        # ==========================================
        initializer_config = benchmark_config.get("task_initializer", {})
        if initializer_config:
            self.logger.info("🎲 Generating dynamic task parameters...")
            
            # Generate actual values (e.g., hours=5) using ParamHandler
            rendered_params = ParamHandler.generate(initializer_config)
            context.setdefault("task_params", {}).update(rendered_params)
            
            # Inject rendered parameters into the instruction string
            raw_instruction = benchmark_config.get("instruction", "")
            rendered_instruction = ParamHandler.render_string(raw_instruction, rendered_params)
            context["task_params"]["instruction"] = rendered_instruction
            
            self.logger.info(f"📝 Rendered Instruction: {rendered_instruction}")
        
        # ==========================================
        # Step 2: Environment Setup
        # ==========================================
        env_configs = benchmark_config.get("environment_initializer", [])
        for env_conf in env_configs:
            env_name = env_conf.get("name")
            env_params = env_conf.get("params", {})
            try:
                # Dynamically load and execute environment manipulation scripts
                EnvPlugin = PluginRegistry.get_plugin(namespace="benchmark.environment", name=env_name)
                env_tool = EnvPlugin(device=self.device)
                env_tool.execute(**env_params)
                self.logger.info(f"🧹 Environment setup executed successfully: {env_name}")
            except Exception as e:
                self.logger.error(f"❌ Failed to setup environment [{env_name}]: {e}")

        # ==========================================
        # Step 3: Evaluator Tree Construction & Pre-Evaluation
        # ==========================================
        evaluator_config = benchmark_config.get("evaluator")
        evaluator_tree = None
        if evaluator_config:
            self.logger.info("🌲 Building Evaluator Tree...")
            evaluator_tree = EvaluatorFactory.build(evaluator_config, self.device)
            
            # Capture baseline states (e.g., initial screenshots) if required
            evaluator_tree.pre_evaluate(context)

        # ==========================================
        # Step 4: Agent Execution
        # ==========================================
        max_steps = context.get("global_config", {}).get("max_steps", 15)
        
        # Delegate the actual execution loop to the AgentRunner
        trajectory = self.agent_runner.run(agent, context, max_steps)
        
        # Store the execution trajectory into the context for the evaluator
        context["trajectory"] = trajectory

        # ==========================================
        # Step 5: Final Evaluation
        # ==========================================
        if evaluator_tree:
            self.logger.info("\n⚖️ Entering Final Evaluation Phase...")
            
            # Grade the agent's performance based on the defined rules
            final_result = evaluator_tree.evaluate(context)
            
            status = "✅ PASS" if final_result.is_pass else "❌ FAIL"
            self.logger.info("=" * 50)
            self.logger.info(f"FINAL RESULT: {status}")
            self.logger.info(f"REASON: {final_result.reason}")
            self.logger.info("=" * 50)
            
            return final_result

        return None