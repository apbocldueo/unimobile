import json
import re
import logging
from unimobile.core.interfaces import BasePlannerParser
from unimobile.core.protocol import PlanResult
from unimobile.utils.registry import register_parser

logger = logging.getLogger(__name__)

@register_parser("mobimind_planner_parser")
class MobimindParser(BasePlannerParser):
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
            logger.error(f"JSON 解析失败: {e} \nRaw: {json_str[:100]}...")
            return PlanResult(content=task, data={"error": "json_parse_error"})
        