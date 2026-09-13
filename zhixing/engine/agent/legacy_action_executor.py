"""Registered compatibility ActionExecutor for AgentGraph compilation.

Registration happens only when the existing engine plugin discovery is invoked;
importing :mod:`zhixing.graph` remains side-effect free.
"""

from zhixing.components import LegacyActionExecutor
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="agent.action_executor", name="legacy_action_executor")
class RegisteredLegacyActionExecutor(LegacyActionExecutor):
    """Execute canonical actions through the current device action mapping."""

