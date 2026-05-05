import json
import re
import logging
from zhixing.core.agent.interfaces import BasePlannerParser
from zhixing.core.agent.protocol import PlanResult
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

# @register_parser("mobimind_planner_parser")
@PluginRegistry.register(namespace="agent.parser", name="mobimind_planner_parser")
class MobimindParser(BasePlannerParser):

    def __init__(self, **kwargs) -> None:
        super().__init__()

    def parse(self, response: str, **kwargs) -> PlanResult:
        task = kwargs.get("task", "unknown_task")
        pattern = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL)
        match = pattern.search(response)
        json_str = match.group(1) if match else response.strip()

        try:
            data = json.loads(json_str)
            
            app_name = data.get("app_name")
            package_name = data.get("package_name")
            final_desc = data.get("final_task_description", task)
            
            return PlanResult(
                content=final_desc,
                data={
                    "app_name": app_name,
                    "package_name": package_name,
                    "raw_json": data
                }
            )
        except json.JSONDecodeError as e:
            raw_preview = (json_str or "")[:240]
            self.logger.error(
                "planner JSON decode error at pos %s: %s; raw excerpt=%r",
                getattr(e, "pos", None),
                e,
                raw_preview,
            )
            return PlanResult(content=task, data={"error": "json_parse_error"})
        