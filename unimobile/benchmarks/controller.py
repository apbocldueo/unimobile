import logging
from typing import Dict, Any

from unimobile.benchmarks.task_generator import TaskGenerator, TaskInstance
from unimobile.benchmarks.env_manager import EnvironmentManager
from unimobile.devices.base import BaseDevice

logger = logging.getLogger(__name__)

class BenchmarkController:
    def __init__(self, device: BaseDevice, eval_llm: Any, app_mapping_path: str = "configs/app_mapping.yaml"):
        self.device = device
        
        self.task_gen = TaskGenerator(mapping_path=app_mapping_path)
        self.env_mgr = EnvironmentManager(device)

    def generate_task(self, raw_task_json: Dict, global_seed: int = 42) -> TaskInstance:
        try:
            return self.task_gen.generate(raw_task_json, self.device, global_seed)
        except Exception as e:
            logger.error(f"Task generation failed: {e}")
            raise e

    def setup_task_env(self, task_instance: TaskInstance):
        self.env_mgr.setup(task_instance)