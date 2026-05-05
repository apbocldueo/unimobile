import logging
from typing import Dict, Any

from zhixing.core.agent.interfaces import BasePlannerParser
from zhixing.core.agent.protocol import PlanResult
# from zhixing.utils.registry import register_parser
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

# @register_parser("section_planner_parser")
@PluginRegistry.register(namespace="agent.parser", name="section_planner_parser")
class SectionParser(BasePlannerParser):
    """
    Parse text formats
    """
    def parse(self, response: str, **kwargs) -> PlanResult:
        task = kwargs.get("task", "unknown_task")
        
        try:
            if "### Plan ###" in response:
                plan = response.split("### Plan ###")[-1].replace("\n", " ").replace("  ", " ").strip()
                # thought = response.split("### Thought ###")[-1].split("### Plan ###")[0].strip()
                logger.debug("Parsed plan text: %s", plan)
                logger.info("Planner output parsed OK (%d chars)", len(plan))
                return PlanResult(
                    content=plan,
                    data={} 
                )
            else:
                logger.warning("Not Found '### Plan ###'")
                return PlanResult(content=response, data={})
                
        except Exception as e:
            logger.error(f"{e}")
            return PlanResult(content=f"Execute task: {task}", data={"error": str(e)})