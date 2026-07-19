import os
import re
from typing import Any

from zhixing.core.agent.interfaces import BaseVerifier
from zhixing.core.agent.protocol import Action, ActionType, VerifierInput, VerifierResult
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="agent.verifier", name="llm_reflect_verifier")
class LLMReflectVerifier(BaseVerifier):
    """MobileAgent-style LLM reflection over before/after screenshots."""

    def __init__(
        self,
        llm_client: Any,
        prompt_file: str = "verifier_mobileagent_reflect.md",
        add_info: str = "",
        **kwargs: Any,
    ) -> None:
        self.llm = llm_client
        self.prompt_file = prompt_file
        self.add_info = add_info

    def verify(self, input_data: VerifierInput) -> VerifierResult:
        action = input_data.action
        if action.type not in [ActionType.TAP, ActionType.LONG_PRESS, ActionType.SWIPE, ActionType.TEXT, ActionType.START_APP]:
            return VerifierResult(is_success=True, feedback="Action type skipped reflection")

        prompt = self._render_prompt(input_data)
        response = self.llm.generate(
            prompt,
            images=[input_data.screenshot_before, input_data.screenshot_after],
        )
        answer = self._extract_answer(response)
        feedback = self._extract_thought(response) or response.strip()

        if answer == "A":
            return VerifierResult(
                is_success=True,
                feedback=feedback or "The operation met expectation.",
                score=1.0,
                metadata={"raw_response": response},
            )
        if answer == "B":
            return VerifierResult(
                is_success=False,
                feedback=feedback or "The operation led to a wrong page; go back.",
                should_retry=True,
                correction_suggestion=Action(
                    type=ActionType.KEY,
                    params={"code": "back"},
                    thought="Reflection judged the previous operation entered a wrong page, so go back.",
                ),
                metadata={"raw_response": response},
            )
        if answer == "C":
            return VerifierResult(
                is_success=False,
                feedback=feedback or "The operation produced no visible change.",
                should_retry=True,
                metadata={"raw_response": response},
            )
        if answer == "D":
            return VerifierResult(
                is_success=True,
                feedback=feedback or "The operation result is uncertain; continuing.",
                score=0.5,
                metadata={"raw_response": response, "uncertain": True},
            )

        return VerifierResult(
            is_success=True,
            feedback=f"Reflection answer was unclear; continuing. Raw answer: {answer or response[:120]}",
            metadata={"raw_response": response},
        )

    def _render_prompt(self, input_data: VerifierInput) -> str:
        template = self._load_prompt(self.prompt_file)
        action = input_data.action
        operation = (action.metadata or {}).get("operation") or action.thought or action.type.value
        action_text = (action.metadata or {}).get("mobile_agent_action") or f"{action.type.value} {action.params}"
        return (
            template.replace("{task}", input_data.task)
            .replace("{operation}", str(operation))
            .replace("{action}", str(action_text))
            .replace("{add_info}", self.add_info or "")
        )

    @staticmethod
    def _extract_answer(response: str) -> str:
        section = LLMReflectVerifier._section(response, "Answer")
        match = re.search(r"\b([ABCD])\b", section or response or "", re.IGNORECASE)
        return match.group(1).upper() if match else ""

    @staticmethod
    def _extract_thought(response: str) -> str:
        return LLMReflectVerifier._section(response, "Thought")

    @staticmethod
    def _section(text: str, name: str) -> str:
        pattern = rf"###\s*{re.escape(name)}\s*###\s*(.*?)(?=\n###\s*[A-Za-z ]+\s*###|\Z)"
        match = re.search(pattern, text or "", re.IGNORECASE | re.DOTALL)
        if not match:
            return ""
        return " ".join(match.group(1).strip().split())

    @staticmethod
    def _load_prompt(filename: str) -> str:
        if os.path.exists(filename):
            path = filename
        else:
            path = os.path.join(os.getcwd(), "zhixing", "prompts", filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Prompt file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
