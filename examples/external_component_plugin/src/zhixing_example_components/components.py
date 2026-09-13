"""Public-API-only component implementations for the standalone example."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from zhixing.components import (
    BaseComponent,
    ComponentCategory,
    RuntimeContext,
    TaskInput,
)


class RunLabelerConfig(BaseModel):
    """Strict declarative configuration for the example text component."""

    model_config = ConfigDict(extra="forbid")

    prefix: str = "example"


class RunLabeler(BaseComponent[str, str]):
    """Label text with declarative configuration and the active run identity."""

    component_category = ComponentCategory.EXTENSION
    input_type = str
    output_type = str

    def __init__(self, prefix: str = "example") -> None:
        """Store the validated declarative prefix.

        Args:
            prefix (str): Text prepended to every invocation result.

        Raises:
            None.

        Returns:
            None.
        """
        self.prefix = prefix

    def invoke(self, input: str, runtime: RuntimeContext) -> str:
        """Return a deterministic value proving RuntimeContext propagation.

        Args:
            input (str): Graph input text.
            runtime (RuntimeContext): Run-scoped framework context.

        Raises:
            None.

        Returns:
            str: Prefix, input value, and run ID joined into one result.
        """
        return f"{self.prefix}:{input}:{runtime.run_id}"


class TaskRunLabeler(BaseComponent[TaskInput, str]):
    """Label a typed Mobile Agent task without receiving device capabilities."""

    component_category = ComponentCategory.EXTENSION
    input_type = TaskInput
    output_type = str

    def __init__(self, prefix: str = "example") -> None:
        """Store the validated declarative prefix.

        Args:
            prefix (str): Text prepended to every invocation result.

        Raises:
            None.

        Returns:
            None.
        """
        self.prefix = prefix

    def invoke(self, input: TaskInput, runtime: RuntimeContext) -> str:
        """Return safe task/run audit evidence for a graph output branch.

        Args:
            input (TaskInput): Typed task supplied at the AgentGraph boundary.
            runtime (RuntimeContext): Current run-scoped framework context.

        Raises:
            None.

        Returns:
            str: Prefix, instruction, and run ID joined into one result.
        """
        return f"{self.prefix}:{input.instruction}:{runtime.run_id}"


__all__ = ["RunLabeler", "RunLabelerConfig", "TaskRunLabeler"]
