import logging
import os
from typing import List
from zhixing.core.agent.interfaces import BaseReason
from zhixing.core.agent.protocol import Action, ActionType, PerceptionResult, MemoryFragment, FragmentType
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError
# from zhixing.utils.registry import register_reasoning, get_parser_class
from zhixing.core.factory import PluginRegistry
from zhixing.core.agent.action_space import get_action_space_by_mode

BRAIN_PRESETS = {
    "general_vlm_type": {
        "prompt_file": "reasoning_general.md",
        "parser_name": "json_action_parser",
        "input_mode": "image"
    },
    "appagent_style": {
        "prompt_file": "reasoning_appagent.md",
        "parser_name": "appagent_action_parser",
        "input_mode": "image"
    },
    "mobileagent_style": {
        "prompt_file": "reasoning_mobileagent.md",
        "parser_name": "mobile_agent_action_parser",
        "input_mode": "image"
    },
    "showui_navigation": {
        "prompt_file": "reasoning_showui_navigation.md",
        "parser_name": "showui_action_parser",
        "input_mode": "image"
    },
    "showui_aitw": {
        "prompt_file": "reasoning_showui_aitw.md",
        "parser_name": "showui_action_parser",
        "input_mode": "image"
    },
    "gui_schema_cn": {
        "prompt_file": "reasoning_gui_schema_cn.md",
        "parser_name": "gui_schema_action_parser",
        "input_mode": "image"
    },
    "mobile_use_operator": {
        "prompt_file": "reasoning_mobile_use_operator.md",
        "parser_name": "mobile_use_tool_parser",
        "input_mode": "image"
    },
    "guicourse_task2action": {
        "prompt_file": "reasoning_guicourse_task2action.md",
        "parser_name": "guicourse_action_parser",
        "input_mode": "image"
    },
    "seeact_uground": {
        "prompt_file": "reasoning_seeact_uground.md",
        "parser_name": "seeact_uground_action_parser",
        "input_mode": "image"
    },
    "os_genesis": {
        "prompt_file": "reasoning_os_genesis.md",
        "parser_name": "os_genesis_action_parser",
        "input_mode": "image"
    }
}

logger = logging.getLogger(__name__)

# @register_reasoning("universal_reasoning")
@PluginRegistry.register(namespace="agent.reasoning", name="universal_reasoning")
class UniversalReason(BaseReason):
    def __init__(self, 
                 llm_client, 
                 env_info=None, 
                 preset: str = None,
                 prompt_file: str = None,
                 parser_name: str = None,
                 input_mode: str = None,
                 **kwargs):

        super().__init__(llm_client, env_info)
        
        self.config = kwargs
        # Total LLM calls on parse failure: 1 initial + parse_max_retries retries (default 3 retries → 4 calls).
        self.parse_max_retries = max(0, int(kwargs.get("parse_max_retries", 3)))

        # 1. Loading Preset
        if preset:
            if preset not in BRAIN_PRESETS:
                raise ValueError(f"Unknown Brain Preset: {preset}")
            config = BRAIN_PRESETS[preset]
            
            self.prompt_filename = prompt_file or config["prompt_file"]
            self.parser_name = parser_name or config["parser_name"]
            self.input_mode = input_mode or config.get("input_mode", "image")
            
        else:
            self.prompt_filename = prompt_file or "brain_general.md"
            self.parser_name = parser_name or "json_action_parser"
            self.input_mode = input_mode or "image"

        # 2. Initial resolver
        # ParserClass = get_parser_class(self.parser_name)
        ParserClass = PluginRegistry.get_plugin(namespace="agent.parser", name=self.parser_name)
        self.parser = ParserClass()
        
        logger.debug("Brain preset=%s", preset)
        logger.info(
            "Reasoning ready: template=%s parser=%s",
            self.prompt_filename,
            self.parser_name,
        )

    def think(
        self,
        task: str,
        plan: str,
        perception_result: PerceptionResult,
        memory_context: List[MemoryFragment],
        *,
        available_apps: str = "",
    ) -> Action:
        """Brain think: generate action

        Args:
            task (str): task
            plan (str): plan
            perception_result (PerceptionResult): perception result
            memory_context (List[MemoryFragment]): memory result
            available_apps: Bullet list text from the runner (from ``device.format_start_app_catalog_for_prompt()``).
                Reasoning must not depend on a device handle.

        Returns:
            Action: action
        """
        mode = perception_result.mode
        width = perception_result.metadata.get("width", 1084)
        height = perception_result.metadata.get("height", 2412)

        # 1. Format history
        history_text = self._format_history(memory_context)
        
        # 2. Get Action Space dynamically
        actions_def_dict = get_action_space_by_mode(mode)

        # 3. Render Action Definitions
        actions_def_str = ""
        for action, value in actions_def_dict.items():
            actions_def_str += f"- {action}({', '.join(value['arguments'])}): {value['description'](None)}\n"

        available_apps_str = (available_apps or "").strip()
        if not available_apps_str:
            available_apps_str = (
                "(No application shortcut list was supplied for this session; "
                "prefer Home/launcher navigation unless the task names a known app.)"
            )

        # prompt
        prompt_tpl = self._load_prompt(self.prompt_filename)
        prompt = prompt_tpl.replace("{task}", task) \
                           .replace("{plan}", plan) \
                           .replace("{history_text}", history_text) \
                           .replace("{width}", str(width)) \
                           .replace("{height}", str(height)) \
                           .replace("{perception_prompt}", perception_result.prompt_representation) \
                           .replace("{memory_text}", history_text) \
                           .replace("{actions_def}", actions_def_str) \
                           .replace("{available_apps}", available_apps_str)

        n_images = 0
        images = []
        if self.input_mode == "image":
            images = perception_result.visual_representations or [perception_result.original_screenshot_path]
            n_images = len([p for p in images if p])

        logger.debug("Reasoning prompt (%d chars, %d images):\n%s", len(prompt), n_images, prompt)

        parse_metadata = {
            "mode": mode,
            "width": width,
            "height": height,
            "perception_metadata": perception_result.metadata,
            "elements": perception_result.elements,
        }

        max_attempts = self.parse_max_retries + 1
        response = ""
        action = Action(type=ActionType.FAIL, thought="parse failed")

        for attempt in range(1, max_attempts + 1):
            response = self.llm.generate(prompt, images=images)
            logger.debug("Reasoning raw response (%d chars):\n%s", len(response or ""), response)
            logger.info(
                "Reasoning LLM round-trip done (attempt %d/%d, prompt_chars=%d, response_chars=%d, images=%d)",
                attempt,
                max_attempts,
                len(prompt),
                len(response or ""),
                n_images,
            )

            try:
                action = self.parser.parse(response, parse_metadata)
                return action, response
            except ActionParseError as e:
                if attempt < max_attempts:
                    logger.warning(
                        "Action parse failed (attempt %d/%d): %s — retrying LLM",
                        attempt,
                        max_attempts,
                        e,
                    )
                    continue
                logger.error(
                    "Action parse failed after %d attempt(s): %s",
                    max_attempts,
                    e,
                )
                action = Action(
                    type=ActionType.FAIL,
                    thought=str(e),
                    metadata={"raw_response": response, "parse_attempts": attempt},
                )

        return action, response

    def _format_history(self, fragments: List[MemoryFragment]) -> str:
        """Generate text history from Memory Fragments

        Any memory plugin may emit different ``FragmentType`` values; all must
        reach the LLM so verifier feedback and plans are not silently dropped.

        Returns:
            str: history str
        """
        history_text = ""
        for frag in fragments:
            role_tag = frag.role.upper()
            if frag.type == FragmentType.RAG_DOC:
                history_text += f"\n[SYSTEM KNOWLEDGE]\n{frag.content}\n"
            elif frag.type == FragmentType.TEXT:
                history_text += f"[{role_tag}]: {frag.content}\n"
            elif frag.type == FragmentType.IMAGE:
                history_text += f"[{role_tag}]: [Screenshot Uploaded]\n"
            elif frag.type == FragmentType.ERROR:
                history_text += f"[{role_tag} / VERIFIER]: {frag.content}\n"
            elif frag.type == FragmentType.PLAN:
                history_text += f"[{role_tag}]: {frag.content}\n"
            elif frag.type == FragmentType.USER_PROFILE:
                history_text += f"[{role_tag} / PROFILE]: {frag.content}\n"
            elif frag.type == FragmentType.FEW_SHOT:
                history_text += f"[{role_tag} / FEW_SHOT]: {frag.content}\n"
            elif frag.type == FragmentType.ACTION:
                line = self._format_action_fragment(frag)
                if line:
                    history_text += f"[{role_tag}]: {line}\n"
        return history_text

    def _format_action_fragment(self, frag: MemoryFragment) -> str:
        """Serialize ACTION fragments (e.g. from SummaryMemory) for the prompt."""
        action = frag.content
        if not hasattr(action, "type"):
            return str(action)
        action_str = f"Action: {action.type.value}"
        if getattr(action, "params", None):
            action_str += f" {action.params}"
        if getattr(action, "thought", None):
            return f"Thought: {action.thought}\n{action_str}"
        return action_str

    def _load_prompt(self, filename: str) -> str:
        """Loading prompt

        Raises:
            FileNotFoundError: _description_

        Returns:
            _type_: _description_
        """
        # Prompt location: unimobile/assets/prompts/
        base_dir = os.path.join(os.getcwd(), "zhixing", "prompts")
        
        if os.path.exists(filename):
            path = filename
        else:
            path = os.path.join(base_dir, filename)
            
        if not os.path.exists(path):
             raise FileNotFoundError(f"Prompt file not found: {path}")
             
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
