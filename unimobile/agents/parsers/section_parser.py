import logging
from typing import Dict, Any

from unimobile.core.interfaces import BasePlannerParser
from unimobile.core.protocol import PlanResult
from unimobile.utils.registry import register_parser

logger = logging.getLogger(__name__)

@register_parser("section_planner_parser")
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
                logger.info(f"Parser successful: {plan[:]}...")
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