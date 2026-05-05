from typing import Dict, Any

from zhixing.core.agent.interfaces import BasePlannerParser
from zhixing.core.agent.protocol import PlanResult
from zhixing.core.factory import PluginRegistry


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
                self.logger.debug("Parsed plan text: %s", plan)
                self.logger.info("Planner output parsed OK (%d chars)", len(plan))
                return PlanResult(
                    content=plan,
                    data={} 
                )
            else:
                self.logger.warning(
                    "planner response has no '### Plan ###' marker; returning raw text (first 160 chars): %r",
                    (response or "")[:160],
                )
                return PlanResult(content=response, data={})
                
        except Exception as e:
            self.logger.error("section_planner parse error for task=%r: %s", kwargs.get("task"), e, exc_info=True)
            return PlanResult(content=f"Execute task: {task}", data={"error": str(e)})