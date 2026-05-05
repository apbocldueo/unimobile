from typing import Dict, Any, Optional
from zhixing.utils.utils import get_plugin_logger
from zhixing.core.runner import AgentRunner
from zhixing.core.factory import PluginRegistry
from zhixing.engine.benchmark.eval_factory import EvaluatorFactory
from zhixing.core.benchmark.param_handler import ParamHandler

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

        This method orchestrates data generation, environment resetting, 
        evaluator initialization, agent execution, and final grading.

        Args:
            benchmark_config (Dict[str, Any]): The configuration definition for the specific benchmark task.
            agent (Any): The agent instance to be evaluated.
            context (Dict[str, Any]): The runtime context dictionary shared across the pipeline.

        Returns:
            Optional[Any]: The final evaluation result object containing the pass/fail status and reasoning,
                or None if no evaluator is configured.
        """
        task_id = benchmark_config.get('id', 'Unknown')
        self.logger.info(f"\n========== Start Benchmark: [{task_id}] ==========")

        # --- Step 1: Task Initialization (Generate Data) ---
        if "task_initializer" in benchmark_config:
            rendered_params = self._generate_task_params(benchmark_config["task_initializer"])
            context.setdefault("task_params", {}).update(rendered_params)
            
            # Render the instruction string with dynamic parameters
            raw_instruction = benchmark_config.get("instruction", "")
            rendered_instruction = ParamHandler.render_placeholders(raw_instruction, rendered_params)
            context["task_params"]["instruction"] = rendered_instruction
            
            self.logger.info(f"Final Instruction: {rendered_instruction}")

        # --- Step 2: Environment Setup (Clean state) ---
        if "environment_initializer" in benchmark_config:
            self._setup_environment(benchmark_config["environment_initializer"])

        # --- Step 3: Evaluator Initialization (Build grading logic) ---
        evaluator_tree = None
        if "evaluator" in benchmark_config:
            evaluator_tree = EvaluatorFactory.build(benchmark_config["evaluator"], self.device)
            evaluator_tree.pre_evaluate(context)

        # --- Step 4: Agent Execution (Run the task) ---
        max_steps = context.get("global_config", {}).get("max_steps", 15)
        context["trajectory"] = self.agent_runner.run(agent, context, max_steps)

        # --- Step 5: Final Evaluation (Grading) ---
        if evaluator_tree:
            self.logger.info("Entering Final Evaluation Phase...")
            final_result = evaluator_tree.evaluate(context)
            
            status_emoji = "✅ PASS" if final_result.is_pass else "❌ FAIL"
            self.logger.info(f"FINAL RESULT: {status_emoji} | Reason: {final_result.reason}")
            return final_result

        return None
    

    def _generate_task_params(self, initializer_config: Dict[str, Any]) -> Dict[str, Any]:
        """Parses and executes task initializer plugins to generate variables.

        Args:
            initializer_config (Dict[str, Any]): Configuration dict mapping variable 
                names to their respective generator plugin settings.

        Returns:
            Dict[str, Any]: A dictionary containing the dynamically generated parameters.
            
        Raises:
            ValueError: If a specified generator plugin is not found in the registry.
            RuntimeError: If a generator plugin fails to execute.
        """
        generated_params = {}
        for var_name, gen_config in initializer_config.items():
            gen_name = gen_config.get("name")
            try:
                GeneratorClass = PluginRegistry.get_plugin(namespace="benchmark.task", name=gen_name)
                if not GeneratorClass:
                    raise ValueError(f"Generator plugin '{gen_name}' not found.")
                
                generated_params[var_name] = GeneratorClass().generate(gen_config.get("params", {}))
            except Exception as e:
                self.logger.error(f"Failed to generate parameter '{var_name}': {e}", exc_info=True)
                # Fail fast: Stop initialization if critical params cannot be generated
                raise RuntimeError(f"Task parameter generation failed for '{var_name}'") from e
                
        return generated_params
    

    def _setup_environment(self, env_configs: list) -> None:
        """Parses and executes environment reset plugins.

        Args:
            env_configs (list): A list of environment configuration dictionaries.
            
        Raises:
            ValueError: If a specified environment plugin is not found.
            RuntimeError: If environment setup fails, ensuring the benchmark 
                does not run in a dirty state.
        """
        for env_conf in env_configs:
            env_name = env_conf.get("name")
            try:
                EnvPlugin = PluginRegistry.resolve_benchmark_env_plugin(env_conf)
                meta = dict(env_conf.get("meta") or {})
                params = dict(env_conf.get("params") or {})
                if "device" not in meta:
                    meta["device"] = self.device
                ok = EnvPlugin().execute(meta=meta, params=params)
                if not ok:
                    raise RuntimeError(f"Environment plugin '{env_name}' reported failure (returned False)")
                self.logger.info(f"Environment setup executed successfully: {env_name}")
            except Exception as e:
                self.logger.error(f"Failed to setup environment [{env_name}]: {e}", exc_info=True)
                # Fail fast: A dirty environment invalidates the benchmark
                raise RuntimeError(f"Environment setup aborted due to failure in '{env_name}'") from e