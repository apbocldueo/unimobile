import os
import logging
from typing import Dict, Union

from zhixing.core.agent.interfaces import BasePlanner
from zhixing.core.agent.protocol import PlanResult, PlanInput
from zhixing.core.context import EnvironmentInfo
# from zhixing.utils.registry import register_planner, get_parser_class
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

# @register_planner("universal_planner")
@PluginRegistry.register(namespace="agent.planner", name="universal_planner")
class UniversalPlanner(BasePlanner):
    """
    General Planner
    """
    
    PRESETS = {
        # Style 1: Manager (Step-by-step)
        "manager_style": {
            "prompt_file": "planner_manager.md",
            "parser_name": "section_planner_parser",
            "use_rag": False
        },
        # Style 2: MobiMind (App + structuring JSON)
        "mobimind_style": {
            "prompt_file": {
                "android": "planner_mobimind_android.md",
                "harmony": "planner_mobimind_harmony.md",
                "default": "planner_mobimind_android.md"
            },
            "parser_name": "mobimind_planner_parser",
            "use_rag": True
        }
    }

    def __init__(
        self, 
        llm_client, 
        knowledge_source=None, 
        env_info: EnvironmentInfo = None,
        preset: str = "manager_style", 
        prompt_file: Union[str, Dict] = None,       
        parser_name: str = None,
        use_rag: bool = None,
        **kwargs
    ):
        super().__init__(llm_client, knowledge_source, env_info)
        
        if preset not in self.PRESETS:
             self.config = {}
             if not prompt_file:
                 raise ValueError(f"UniversalPlanner: no setting '{preset}' and do not provide prompt_file")
        else:
            self.config = self.PRESETS[preset].copy()

        
        if prompt_file: self.config["prompt_file"] = prompt_file
        if parser_name: self.config["parser_name"] = parser_name
        if use_rag is not None: self.config["use_rag"] = use_rag

        raw_prompt_file = self.config.get("prompt_file")
        if isinstance(raw_prompt_file, dict):
            current_platform = self.env.platform.lower() if (self.env and self.env.platform) else "android"
            target_file = raw_prompt_file.get(current_platform)
            if not target_file:
                target_file = raw_prompt_file.get("default")
                logger.warning(f"UniversalPlanner: '{current_platform}' no specific Prompt, use the default:: {target_file}")
            self.target_prompt_file = target_file
        else:
            self.target_prompt_file = raw_prompt_file

        self.prompt_template = self._load_prompt(self.target_prompt_file)
        
        target_parser_name = self.config.get("parser_name")
        # ParserCls = get_parser_class(target_parser_name)
        ParserCls = PluginRegistry.get_plugin(namespace="agent.parser", name=target_parser_name)
        self.parser = ParserCls()
        
        self.use_rag = self.config.get("use_rag", False)
        
        logger.info("Planner ready: preset=%s prompt_file=%s", preset, self.target_prompt_file)

    def make_plan(self, plan_input: PlanInput) -> PlanResult:

        context_str = ""
        if self.use_rag and self.knowledge_source:
            try:
                docs = self.knowledge_source.search_docs(plan_input.task)
                if docs:
                    context_str = "\n".join([str(d) for d in docs])
            except Exception as e:
                logger.warning("planner RAG/knowledge_source search failed (continuing without docs): %s", e)
        
        prompt_vars = {
            "task": plan_input.task,
            "screenshot_path": plan_input.screenshot_path,
            "context": context_str,
            # TODO
        }

        prompt = self.prompt_template
        for key, value in prompt_vars.items():
            if value is not None:
                prompt = prompt.replace(f"{{{key}}}", str(value))

        logger.debug("Planner prompt (%d chars):\n%s", len(prompt), prompt)
        images = [plan_input.screenshot_path] if plan_input.screenshot_path else []
        response = self.llm.generate(prompt=prompt, images=images)
        logger.debug("Planner raw response (%d chars):\n%s", len(response or ""), response)
        logger.info(
            "Planner LLM round-trip done (prompt_chars=%d, response_chars=%d, images=%d)",
            len(prompt),
            len(response or ""),
            len(images),
        )
        
        return self.parser.parse(response, task=plan_input.task)

    def _load_prompt(self, filename: str) -> str:
        if os.path.exists(filename):
            path = filename
        else:
            base_dir = os.path.join(os.getcwd(), "zhixing", "prompts")
            path = os.path.join(base_dir, filename)
            
        if not os.path.exists(path):
             raise FileNotFoundError(f"The Prompt file was not found: {path}")
             
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        
        content = content.replace("````markdown", "").replace("````", "")
        return content.strip()
