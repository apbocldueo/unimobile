"""High-level AgentGraph authoring contracts for the current YAML format."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import GraphModel


class MobileModelAuthoring(GraphModel):
    """User-facing model selection for a standard mobile Agent."""

    provider: Literal["openai_compatible"] = "openai_compatible"
    name: str = Field(default="gpt-4o", min_length=1, max_length=128)
    secret_ref: str = Field(default="api_key", min_length=1, max_length=128)
    base_url: str | None = Field(default=None, max_length=2048)
    base_url_secret: str | None = Field(default="base_url", max_length=128)


class MobileReasoningAuthoring(GraphModel):
    """Optional reasoning settings exposed by the standard mobile template."""

    component: Literal["universal_reasoning"] = "universal_reasoning"
    preset: str = Field(default="general_vlm_type", min_length=1, max_length=128)
    parse_max_retries: int = Field(default=2, ge=0, le=10)


class MobileMemoryAuthoring(GraphModel):
    """Optional sliding-window memory settings."""

    enabled: bool = True
    window_size: int = Field(default=6, ge=1, le=1000)


class MobileCapabilitiesAuthoring(GraphModel):
    """Capabilities supported by the first high-level mobile template."""

    perception: Literal["screenshot"] = "screenshot"
    reasoning: MobileReasoningAuthoring = Field(default_factory=MobileReasoningAuthoring)
    memory: MobileMemoryAuthoring = Field(default_factory=MobileMemoryAuthoring)


class MobilePoliciesAuthoring(GraphModel):
    """Bounded execution policies owned by the high-level YAML author."""

    max_steps: int = Field(default=15, ge=1, le=1000)
    max_feedback_iterations: int | None = Field(default=None, ge=1, le=10)


class MobileAgentAuthoring(GraphModel):
    """Schema-2 user-facing YAML for the standard mobile Agent template.

    This contract deliberately omits runtime nodes, ports, namespaces, device
    serials, and generated control-flow glue. Those facts are supplied by the
    compiler and the runtime profile.
    """

    kind: Literal["agent_graph"] = "agent_graph"
    schema_version: Literal[2] = 2
    profile: Literal["mobile_agent"] = "mobile_agent"
    name: str = Field(min_length=1, max_length=256)
    template: Literal["mobile_vlm"] = "mobile_vlm"
    model: MobileModelAuthoring = Field(default_factory=MobileModelAuthoring)
    capabilities: MobileCapabilitiesAuthoring = Field(default_factory=MobileCapabilitiesAuthoring)
    policies: MobilePoliciesAuthoring = Field(default_factory=MobilePoliciesAuthoring)
