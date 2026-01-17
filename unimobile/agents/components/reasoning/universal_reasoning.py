import logging
import os
from typing import List
from unimobile.core.interfaces import BaseReason
from unimobile.core.protocol import Action, PerceptionResult, MemoryFragment, FragmentType
from unimobile.utils.registry import register_reasoning, get_parser_class

logger = logging.getLogger(__name__)

ATOMIC_ACTION_SIGNITURES = {
    "Tap": {
        "arguments": ["x", "y"],
        "description": lambda info: "Tap the position (x, y) in current screen.The origin [0,0] is at the top-left corner of the screen, x is the horizontal coordinate, and y is the vertical coordinate. Example: {\"name\":\"Tap\", \"arguments\":{\"x\":\"100\", \"y\": \"200\"}}"
    },
    "Swipe": {
        "arguments": ["direction", "dist"],
        "description": lambda info: "This function swipes a UI element on the smartphone screen, such as a scroll view or slider. Use direction to specify one of: 'up', 'down', 'left', or 'right'. Use dist to set the swipe distance: 'short', 'medium', or 'long'. Example: {\"name\":\"Swipe\", \"arguments\":{\"direction\":\"up\", \"dist\": \"short\"}}. It indicates that the sliding distance is short when sliding up."
    },
    "Type": {
        "arguments": ["text"],
        "description": lambda info: "Type the \"text\" in an input box, when there is keyboard in screenshot, the opeartion often is used. Example: {\"name\":\"Type\", \"arguments\":{\"text\":\"text\"}}"
    },
    "Enter": {
        "arguments": [],
        "description": lambda info: "Press the Enter key after typing (useful for searching). Example: {\"name\":\"Enter\", \"arguments\":{}}"
    },
    "Back": {
        "arguments": [],
        "description": lambda info: "Return to the previous state. Example: {\"name\":\"Back\", \"arguments\":{}}"
    },
    "Home": {
        "arguments": [],
        "description": lambda info: "Return to home page. Example: {\"name\":\"Home\", \"arguments\":{}}"
    },
    "Clear":{
        "arguments": [],
        "description": lambda info: "Clear the text in an input box, when the text is error, the opeartion is used. Example: {\"name\":\"Clear\", \"arguments\":{}}"
    },
    "Done": {
        "arguments": [],
        "description": lambda info: "Signal that the task is successfully completed. Use this when the goal is achieved. Example: {\"name\":\"Done\", \"arguments\":{}}"
    }
}


ATOMIC_ACTION_SIGNITURES_GRIDDING = {
    "Tap": {
        "arguments": ["area", "subarea"],
        "description": lambda info: "This function is used to tap a grid area shown on the smartphone screen. 'area' is the integer label assigned to a grid area shown on the smartphone screen. 'subarea' is a string representing the exact location to tap within the grid area. It can take one of the nine values: center, top-left, top, top-right, left, right, bottom-left, bottom, and bottom-right. A simple use case can be {\"name\":\"Tap\", \"arguments\":{\"area\":5, \"subarea\": \"center\"}}, which taps the exact center of the grid area labeled with the number 5."
    },
    "Swipe": {
        "arguments": ["direction", "dist"],
        "description": lambda info: "This function swipes a UI element on the smartphone screen, such as a scroll view or slider. Use direction to specify one of: 'up', 'down', 'left', or 'right'. Use dist to set the swipe distance: 'short', 'medium', or 'long'. Example: {\"name\":\"Swipe\", \"arguments\":{\"direction\":\"up\", \"dist\": \"short\"}}. It indicates that the sliding distance is short when sliding up."
    },
    "Type": {
        "arguments": ["text"],
        "description": lambda info: "Type the \"text\" in an input box, when you need search, the opeartion often is used. Example: {\"name\":\"Type\", \"arguments\":{\"text\":\"text\"}}"
    },
    "Enter": {
        "arguments": [],
        "description": lambda info: "Press Enter to submit input. Use immediately after typing to trigger search or send. Example: {\"name\":\"Enter\", \"arguments\":{}}"
    },
    "Done": {
        "arguments": [],
        "description": lambda info: "Signal that the task is successfully completed. Use this when the goal is achieved. Example: {\"name\":\"Done\", \"arguments\":{}}"
    },
    "Clear":{
        "arguments": [],
        "description": lambda info: "Clear the text in an input box, when the text is error, the opeartion is used. Example: {\"name\":\"Clear\", \"arguments\":{}}"
    }
}


ATOMIC_ACTION_SIGNITURES_SOM = {
    "Tap": {
        "arguments": ["element_id"],
        "description": lambda info: "Tap the UI element identified by the numeric tag ID (shown in red boxes). Do NOT calculate coordinates manually. Example: {\"name\":\"Tap\", \"arguments\":{\"element_id\": 5}}"
    },
    "Type": {
        "arguments": ["text", "element_id"], 
        "description": lambda info: "Type text into the input box identified by 'element_id'. If no ID is provided, it types into the currently focused field. Example: {\"name\":\"Type\", \"arguments\":{\"text\":\"coffee\", \"element_id\": 3}}"
    },
    "Swipe": {
        "arguments": ["direction", "dist"],
        "description": lambda info: "Swipe the screen. Direction: 'up', 'down', 'left', 'right'. Distance: 'short', 'medium', 'long'. Example: {\"name\":\"Swipe\", \"arguments\":{\"direction\":\"up\", \"dist\": \"medium\"}}"
    },
    "Enter": {
        "arguments": [],
        "description": lambda info: "Press Enter to submit input. Use immediately after typing to trigger search or send. Example: {\"name\":\"Enter\", \"arguments\":{}}"
    },
    "Back": {
        "arguments": [],
        "description": lambda info: "Return to the previous state. Example: {\"name\":\"Back\", \"arguments\":{}}"
    },
    "Home": {
        "arguments": [],
        "description": lambda info: "Return to home page. Example: {\"name\":\"Home\", \"arguments\":{}}"
    },
    "Done": {
        "arguments": [],
        "description": lambda info: "Signal that the task is successfully completed. Example: {\"name\":\"Done\", \"arguments\":{}}"
    },
    "Clear":{
        "arguments": [],
        "description": lambda info: "Clear the text in an input box, when the text is error, the opeartion is used. Example: {\"name\":\"Clear\", \"arguments\":{}}"
    }
}

BRAIN_PRESETS = {
    "general_vlm_type": {
        "prompt_file": "reasoning_general.md",
        "parser_name": "json_action_parser",
        "input_mode": "image"
    }
}

@register_reasoning("universal_reasoning")
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
        ParserClass = get_parser_class(self.parser_name)
        self.parser = ParserClass()
        
        logger.info(f"preset is {preset}")
        logger.info(f"🧠 UniversalBrain: Template={self.prompt_filename}, Parser={self.parser_name}")

    def think(self, task: str, plan: str, perception_result: PerceptionResult, memory_context: List[MemoryFragment]) -> Action:
        """Brain think: generate action

        Args:
            task (str): task
            plan (str): plan
            perception_result (PerceptionResult): perception result
            memory_context (List[MemoryFragment]): memory result

        Returns:
            Action: action
        """
        mode = perception_result.mode
        width = perception_result.metadata.get("width", 1084)
        height = perception_result.metadata.get("height", 2412)

        # history
        history_text = self._format_history(memory_context)
        
        # Action
        if mode == "grid":
            actions_def_dict = ATOMIC_ACTION_SIGNITURES_GRIDDING
        elif mode == "set_of_marks":
            actions_def_dict = ATOMIC_ACTION_SIGNITURES_SOM
        else:
            actions_def_dict = ATOMIC_ACTION_SIGNITURES

        actions_def_str = ""
        for action, value in actions_def_dict.items():
            actions_def_str += f"- {action}({', '.join(value['arguments'])}): {value['description'](None)}\n"

        # prompt
        prompt_tpl = self._load_prompt(self.prompt_filename)
        prompt = prompt_tpl.replace("{task}", task) \
                           .replace("{plan}", plan) \
                           .replace("{history_text}", history_text) \
                           .replace("{width}", str(width)) \
                           .replace("{height}", str(height)) \
                           .replace("{perception_prompt}", perception_result.prompt_representation) \
                           .replace("{actions_def}", actions_def_str)

        logger.info(f"🧠 Prompt: {prompt[:]}...")

        # image
        images = []
        if self.input_mode == "image":
             images = perception_result.visual_representations or [perception_result.original_screenshot_path]

        # LLM
        response = self.llm.generate(prompt, images=images)
        logger.info(f"🧠 Response: {response}")

        # Parser
        parse_metadata = {
            "mode": mode,
            "width": width,
            "height": height,
            "perception_metadata": perception_result.metadata,
            "elements": perception_result.elements
        }
        
        return self.parser.parse(response, parse_metadata), response

    def _format_history(self, fragments: List[MemoryFragment]) -> str:
        """Generate text history from Memory Fragments

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
        return history_text

    def _load_prompt(self, filename: str) -> str:
        """Loading prompt

        Raises:
            FileNotFoundError: _description_

        Returns:
            _type_: _description_
        """
        # Prompt location: unimobile/assets/prompts/
        base_dir = os.path.join(os.getcwd(), "unimobile", "agents", "prompts")
        
        if os.path.exists(filename):
            path = filename
        else:
            path = os.path.join(base_dir, filename)
            
        if not os.path.exists(path):
             raise FileNotFoundError(f"Prompt file not found: {path}")
             
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
