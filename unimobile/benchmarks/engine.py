import json
import logging
from unimobile.core.runner import Runner
from unimobile.benchmarks.task_generator import TaskGenerator
from unimobile.benchmarks.env_manager import EnvironmentManager

logger = logging.getLogger(__name__)

class BenchmarkEngine:
    def __init__(self, agent, device, eval_llm, config_path="configs/app_mapping.yaml"):
        self.runner = Runner(agent, device)
        
        self.task_gen = TaskGenerator(mapping_path=config_path)
        self.env_mgr = EnvironmentManager(device)

    def run_benchmark(self, dataset_path: str):
        """
        Runing Dataset
        """
        with open(dataset_path, "r", encoding="utf-8") as f:
            raw_tasks = json.load(f)
            
        report = []
        total = len(raw_tasks)

        for i, raw_task in enumerate(raw_tasks):
            
            task_inst = self.task_gen.generate(raw_task, self.env_mgr.device)
            
            self.env_mgr.setup(task_inst)
            
            runner_input = {
                "instruction": task_inst.instruction,
                "app": task_inst.app
            }
            try:
                trajectory = self.runner.run(runner_input)
            except Exception as e:
                logger.error(f"Execution Failed: {e}")
                trajectory = []

            result = self.eval_mgr.evaluate(task_inst, trajectory)
            
            status = "✅ PASS" if result.is_success else "❌ FAIL"
            print(f"{status} | score: {result.score} | Reason: {result.reason}")
            
            report.append({
                "id": task_inst.id,
                "success": result.is_success,
                "score": result.score,
                "reason": result.reason
            })
            
            self.env_mgr.teardown(task_inst)

        return report