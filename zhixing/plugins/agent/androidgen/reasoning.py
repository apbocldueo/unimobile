"""Original actor messages and AutoCheck feedback as independent role nodes."""

from dataclasses import replace

from zhixing.core.factory import PluginRegistry

from .source import get_code_snippet
from .types import format_plan


@PluginRegistry.register(namespace="agent.verifier", name="androidgen_feedback")
class AndroidGenFeedback:
    """Expose previous fail feedback after planning, without another model or retry."""

    def __init__(self, enabled: bool = True) -> None:
        """Remember AutoCheck setting. Args: enabled: Source flag. Returns: None."""
        self.enabled = enabled

    def invoke(self, input, runtime):
        """Copy the original previous execution message into this round's input.

        Args:
            input: Frame after ReflectPlan.
            runtime: Unused context.
        Raises:
            KeyError: A previous source result violates the original result schema.
        Returns:
            AndroidGenFrame: Exact source feedback fields, or unchanged output.
        """
        del runtime
        output = dict(input.output or {})
        previous = input.previous_result
        if self.enabled and previous is not None and previous['operation'] == 'fail':
            output['error_feedback'] = previous['kwargs']['message']
        return replace(input, output=output)


@PluginRegistry.register(namespace="agent.reasoning", name="androidgen_reasoning")
class AndroidGenReasoning:
    """One actor request and the original first-fence extraction failure boundary."""

    def __init__(self, llm_client, model_type: str = "text") -> None:
        """Bind source-compatible actor service and its independent input type.

        Args:
            llm_client: Original generate-compatible actor dependency.
            model_type: Original text/image selection.
        Raises:
            ValueError: The input type is unsupported.
        Returns:
            None.
        """
        if model_type not in ("text", "image"):
            raise ValueError("actor model_type must be text or image")
        self.llm, self.model_type = llm_client, model_type

    def invoke(self, input, runtime):
        """Preserve prefix messages, last-20-message window and exact current prompt.

        Args:
            input: Current source frame after the feedback node.
            runtime: Unused context.
        Raises:
            RuntimeError: Original fenced-code extraction fails outside execution recovery.
            Exception: Source actor model request fails.
        Returns:
            AndroidGenFrame: Raw response and unmodified extracted Python code.
        """
        del runtime
        state = input.view.state[self.model_type]
        prompt = f"# Current State: {state['text']}"
        plan = format_plan(input.plan)
        if plan:
            prompt += f'\n\n# Plan: {plan}'
        feedback = input.output.get('error_feedback')
        if feedback:
            prompt += f'\n\n# Last Round Error: {feedback}'
        if self.model_type == 'image':
            prompt = {"text": prompt, "image_url": state['image_url']}
        history = [{"role": "user", "content": {"text": f'# User Instruction: {input.task.instruction}'}},
                   {"role": "assistant", "content": {"text": "** Task Start **"}}, *input.messages[-20:]]
        response = self.llm.generate(prompt=prompt, system_prompt=input.system_prompt, history=history)
        return replace(input, output={**input.output, "response": response}, code=get_code_snippet(response))
