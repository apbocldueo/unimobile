import os
from typing import Dict, Any, Optional

from zhixing.utils.utils import get_plugin_logger
from zhixing.core.llm.usage import get_task_usage_dict, reset_task_usage
from zhixing.core.runner import AgentRunner
from zhixing.core.factory import PluginRegistry
from zhixing.engine.benchmark.eval_factory import EvaluatorFactory
from zhixing.core.benchmark.param_handler import ParamHandler


def resolve_max_steps(
    benchmark_config: Optional[Dict[str, Any]] = None,
    context: Optional[Dict[str, Any]] = None,
    *,
    default: int = 15,
) -> int:
    """Resolve agent step limit: task JSON > CLI > default (15).

    Args:
        benchmark_config: Per-task benchmark dict; may include top-level ``max_steps``.
        context: Runtime context; may include ``cli_max_steps`` from ``run.py --max_steps``.
        default: Fallback when neither source provides a value.

    Returns:
        int: Maximum agent steps for this task run.
    """
    if benchmark_config is not None:
        task_limit = benchmark_config.get("max_steps")
        if task_limit is not None:
            return int(task_limit)
    if context is not None:
        cli_limit = context.get("cli_max_steps")
        if cli_limit is not None:
            return int(cli_limit)
    return int(default)


def _default_llm_from_agent(agent: Any):
    """Reuse the agent's already-instantiated default LLM for evaluators without a local ``llm`` block."""
    if agent is None:
        return None
    for role in ("reasoning", "planner", "memory"):
        comp = getattr(agent, role, None)
        if comp is None:
            continue
        llm = getattr(comp, "llm", None)
        if llm is not None:
            return llm
    return None


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

    def _go_home_after_task(self, task_id: str) -> None:
        """Return to launcher after a task so the next run starts from a clean desktop."""
        try:
            self.device.go_home()
            self.logger.info("Returned to home screen after task %r.", task_id)
        except Exception as e:
            self.logger.warning("go_home after task %r failed: %s", task_id, e)
    
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
        reset_task_usage()
        self.logger.info("benchmark task_id=%r — phases: task_params -> env_init -> eval_build -> agent_run -> grade", task_id)

        try:
            return self._evaluate_task_body(benchmark_config, agent, context, task_id)
        finally:
            self._go_home_after_task(task_id)

    def _evaluate_task_body(
        self,
        benchmark_config: Dict[str, Any],
        agent: Any,
        context: Dict[str, Any],
        task_id: str,
    ) -> Optional[Any]:
        # Vision / VLM evaluators with no per-evaluator ``llm`` use the agent's global default (same instances as modular_agent).
        if not context.get("evaluator_llm"):
            fallback_llm = _default_llm_from_agent(agent)
            if fallback_llm is not None:
                context["evaluator_llm"] = fallback_llm
                self.logger.debug("evaluator_llm set from agent default LLM")

        # --- Step 1: Task Initialization (Generate Data) ---
        if "task_initializer" in benchmark_config:
            rendered_params = self._generate_task_params(benchmark_config["task_initializer"])
            context.setdefault("task_params", {}).update(rendered_params)
            
            # Render the instruction string with dynamic parameters
            raw_instruction = benchmark_config.get("instruction", "")
            rendered_instruction = ParamHandler.render_placeholders(raw_instruction, rendered_params)
            context["task_params"]["instruction"] = rendered_instruction

            print("Instruction: ", rendered_instruction)
            
            self.logger.info("instruction after placeholder render (%d chars)", len(rendered_instruction or ""))
            self.logger.debug("instruction text: %s", rendered_instruction)

        # --- Step 2: Environment Setup (Clean state) ---
        if "environment_initializer" in benchmark_config:
            self._setup_environment(benchmark_config["environment_initializer"], context)

        # --- Step 3: Evaluator Initialization (Build grading logic) ---
        evaluator_tree = None
        if "evaluator" in benchmark_config:
            evaluator_tree = EvaluatorFactory.build(benchmark_config["evaluator"], self.device)
            evaluator_tree.pre_evaluate(context)

        # --- Step 4: Agent Execution (Run the task) ---
        max_steps = resolve_max_steps(benchmark_config, context)
        self.logger.info(
            "agent_run max_steps=%d (source=%s)",
            max_steps,
            "task_json"
            if benchmark_config.get("max_steps") is not None
            else ("cli" if context.get("cli_max_steps") is not None else "default"),
        )
        context["trajectory"] = self.agent_runner.run(agent, context, max_steps)

        # --- Step 5: Final Evaluation (Grading) ---
        final_result = None
        if evaluator_tree:
            self.logger.info("running evaluator tree on trajectory")
            final_result = evaluator_tree.evaluate(context)

            self.logger.info(
                "FINAL %s reason=%s",
                "PASS" if final_result.is_pass else "FAIL",
                final_result.reason,
            )

        llm_usage = get_task_usage_dict()
        context["llm_usage"] = llm_usage
        if llm_usage.get("total_tokens"):
            self.logger.info(
                "llm_usage total=%d prompt=%d completion=%d calls=%d",
                llm_usage["total_tokens"],
                llm_usage["prompt_tokens"],
                llm_usage["completion_tokens"],
                llm_usage["call_count"],
            )

        human_review_dir = context.get("human_review_dir")
        if human_review_dir and isinstance(human_review_dir, str):
            try:
                from experiment.human_review_output import (
                    append_manifest_entry,
                    write_task_human_review_record,
                )
            except ImportError:
                self.logger.warning(
                    "human_review_dir is set but ``experiment.human_review_output`` is not importable "
                    "(add repo-root ``experiment/human_review_output.py`` locally). Skipping human review export."
                )
            else:
                os.makedirs(human_review_dir, exist_ok=True)
                tid = str(benchmark_config.get("id", "Unknown"))
                task_params = dict(context.get("task_params") or {})
                traj = context.get("trajectory") or []
                detail_path = write_task_human_review_record(
                    human_review_dir,
                    tid,
                    task_params,
                    traj,
                    final_result,
                    benchmark_session_id=context.get("benchmark_session_id"),
                    benchmark_config=benchmark_config,
                    pipeline_error=None,
                    llm_usage=context.get("llm_usage"),
                    experiment_run_config=context.get("experiment_run_config"),
                )
                automated = None
                if final_result is not None:
                    token_total = float((context.get("llm_usage") or {}).get("total_tokens", 0) or 0)
                    automated = {
                        "is_pass": bool(getattr(final_result, "is_pass", False)),
                        "reason": str(getattr(final_result, "reason", "") or ""),
                        "token": token_total,
                    }
                manifest_path = os.path.join(human_review_dir, "manifest.jsonl")
                append_manifest_entry(
                    manifest_path,
                    {
                        "dataset_task_id": tid,
                        "instruction": task_params.get("instruction"),
                        "automated_eval": automated,
                        "detail_json": detail_path,
                        "num_steps": len(traj),
                    },
                )
                self.logger.info("human_review task_json=%s", detail_path)

        return final_result

    

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

                raw_params = gen_config.get("params", {})
                params = ParamHandler.render_placeholders(raw_params, generated_params)
                generated_params[var_name] = GeneratorClass().generate(params)
            except Exception as e:
                self.logger.error(f"Failed to generate parameter '{var_name}': {e}", exc_info=True)
                # Fail fast: Stop initialization if critical params cannot be generated
                raise RuntimeError(f"Task parameter generation failed for '{var_name}'") from e
                
        return generated_params
    

    def _setup_environment(self, env_configs: list, context: Dict[str, Any]) -> None:
        """Parses and executes environment reset plugins.

        Args:
            env_configs (list): A list of environment configuration dictionaries.
            context (Dict[str, Any]): Run context; ``task_params`` is used to render
                ``${...}`` placeholders inside each plugin's ``params`` (recursive).

        Raises:
            ValueError: If a specified environment plugin is not found.
            RuntimeError: If environment setup fails, ensuring the benchmark
                does not run in a dirty state.
        """
        task_params = context.get("task_params") or {}
        for env_conf in env_configs:
            env_name = env_conf.get("name")
            try:
                EnvPlugin = PluginRegistry.resolve_benchmark_env_plugin(env_conf)
                meta = dict(env_conf.get("meta") or {})
                params = dict(env_conf.get("params") or {})
                params = ParamHandler.render_placeholders(params, task_params)
                if "device" not in meta:
                    meta["device"] = self.device
                ok = EnvPlugin().execute(meta=meta, params=params)
                if not ok:
                    raise RuntimeError(f"Environment plugin '{env_name}' reported failure (returned False)")
                self.logger.info("environment_initializer OK plugin_name=%r", env_name)
            except Exception as e:
                self.logger.error(f"Failed to setup environment [{env_name}]: {e}", exc_info=True)
                # Fail fast: A dirty environment invalidates the benchmark
                raise RuntimeError(f"Environment setup aborted due to failure in '{env_name}'") from e