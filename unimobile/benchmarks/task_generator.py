import logging
import random
import hashlib
from typing import Dict
from dataclasses import dataclass

from unimobile.devices.base import BaseDevice
from unimobile.utils.app_resolver import AppResolver
from unimobile.utils.generators import generate_params

logger = logging.getLogger(__name__)

@dataclass
class TaskInstance:
    id: str
    instruction: str
    ground_truth: str
    app: str
    original_params: Dict
    raw_config: Dict

class TaskGenerator:
    def __init__(self, mapping_path="configs/app_mapping.yaml"):
        AppResolver.load_mapping(mapping_path)

    def generate(self, task_json: Dict, device: BaseDevice, global_seed: int = 42) -> TaskInstance:
        task_id = task_json.get("id", "unknown")

        seed_str = f"{global_seed}_{task_id}"
        local_seed = int(hashlib.sha256(seed_str.encode()).hexdigest(), 16) % (2**32)
        random.seed(local_seed)

        raw_app_alias = task_json.get("app", "")
        real_app_name = AppResolver.resolve(
            alias=raw_app_alias, 
            platform=getattr(device, 'platform', 'android'),
            language=getattr(device, 'language', 'cn')
        )

        params = {}
        if "params_config" in task_json:
            params = generate_params(task_json["params_config"], device=device)
        
        if "app" not in params: params["app"] = real_app_name
        if "app_name" not in params: params["app_name"] = real_app_name

        if "task_template" in task_json:
            final_instruction = task_json["task_template"].format(**params)
            final_gt = task_json.get("ground_truth_template", "").format(**params)
        else:
            final_instruction = task_json.get("task", "")
            final_gt = task_json.get("ground_truth", "")

        return TaskInstance(
            id=task_id,
            instruction=final_instruction,
            ground_truth=final_gt,
            app=real_app_name,
            original_params=params,
            raw_config=task_json
        )