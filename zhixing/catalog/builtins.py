"""Deterministic built-in component catalog shared by SDK, YAML, and Studio."""

from __future__ import annotations

import importlib
import importlib.util
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from zhixing.components.authoring import ComponentCategory, ComponentDependencySlot
from zhixing.core.factory import PluginRegistry
from zhixing.graph import GraphComponentRef, GraphRole

from zhixing.runtime.binding import RegistryComponentResolver


_LLM_DEPENDENCY_SLOT = ComponentDependencySlot(
    name="llm",
    required=True,
    accepted_namespaces=("llm",),
    accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
    config_schema={
        "type": "object",
        "required": ["name", "params"],
        "properties": {
            "namespace": {"type": "string", "const": "llm"},
            "name": {"type": "string", "minLength": 1},
            "version": {"type": ["string", "null"]},
            "params": {"type": "object"},
        },
        "additionalProperties": False,
    },
)


def _ecoagent_model_slots(name):
    """Declare EcoAgent's explicit model dependencies without loading their implementations.

    Args:
        name: Built-in stage suffix; collect-only stages use the same optional slot.
    Returns:
        tuple: Authoring metadata; submit constructors still enforce conditional requirements.
    """
    slot = {'plan': 'planner_llm', 'predict': 'executor_llm', 'action': 'executor_llm',
            'description': 'description_llm', 'summary': 'summary_llm'}.get(name)
    return () if slot is None else (ComponentDependencySlot(name=slot, required=name not in ('description', 'summary'),
        accepted_namespaces=('llm',), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
        config_schema=_LLM_DEPENDENCY_SLOT.to_safe_dict()['configSchema']),)


@dataclass(frozen=True)
class BuiltInComponentSpec:
    """Describe one framework-owned component without importing its module."""

    namespace: str
    name: str
    module: str
    version: str = "1"
    extra: str = ""
    required_modules: tuple[str, ...] = ()
    dependency_slots: tuple[ComponentDependencySlot, ...] = ()

    def __post_init__(self) -> None:
        """Validate and freeze built-in dependency authoring metadata.

        Args:
            None.

        Raises:
            ValueError: A declaration has too many, malformed, or duplicate
                dependency slots.

        Returns:
            None.
        """
        slots = tuple(self.dependency_slots)
        if len(slots) > 32 or any(
            not isinstance(item, ComponentDependencySlot) for item in slots
        ):
            raise ValueError("built-in dependency slots are invalid")
        names = [item.name for item in slots]
        if len(names) != len(set(names)):
            raise ValueError("built-in dependency slot names must be unique")
        object.__setattr__(self, "dependency_slots", slots)

    @property
    def identifier(self) -> str:
        """Return the stable namespace/name identifier.

        Args:
            None.

        Raises:
            None.

        Returns:
            str: Stable component identifier.
        """
        return f"{self.namespace}:{self.name}"


@dataclass(frozen=True)
class BuiltInAvailability:
    """Report whether one catalog entry can be imported in this environment."""

    identifier: str
    available: bool
    extra: str = ""
    error_type: str = ""


class BuiltInComponentUnavailableError(LookupError):
    """Signal a selected built-in component or optional dependency is unavailable."""


_SPECS = (
    BuiltInComponentSpec('llm', 'moba_llm', 'zhixing.plugins.llm.moba_llm', extra='moba', required_modules=('numpy', 'cv2', 'requests')),
    BuiltInComponentSpec('knowledge', 'moba_experience', 'zhixing.knowledge.moba'),
    BuiltInComponentSpec('agent.memory', 'moba_load', 'zhixing.plugins.agent.moba.memory',
        dependency_slots=(ComponentDependencySlot(name='experience', required=True,
            accepted_namespaces=('knowledge',), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,)),)),
    *(BuiltInComponentSpec('agent.' + family, 'moba_' + name, 'zhixing.plugins.agent.moba.' + module,
        dependency_slots=(_LLM_DEPENDENCY_SLOT, ComponentDependencySlot(name='embedding', required=name != 'resolve_app',
            accepted_namespaces=('llm',), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,)))
            if family in ('reasoning', 'planner', 'verifier') else ())
      for family, module, names in (
          ('memory', 'memory', ('initialize', 'resume', 'prepare', 'record', 'split', 'advance', 'persist', 'join', 'commit', 'finish')),
          ('perception', 'perception', ('perceive',)),
          ('perception', 'execution', ('observe',)),
          ('action_executor', 'execution', ('execute', 'wait_round')),
          ('reasoning', 'reasoning', ('reason', 'resolve_app')),
          ('planner', 'planning', ('plan',)),
          ('verifier', 'verifier', ('verify',)))
      for name in names),
    BuiltInComponentSpec('llm', 'visiontasker_llm', 'zhixing.plugins.llm.visiontasker_llm'),
    BuiltInComponentSpec('vision', 'visiontasker_vision', 'zhixing.plugins.agent.visiontasker.vision'),
    BuiltInComponentSpec('agent.reasoning', 'visiontasker_reason', 'zhixing.plugins.agent.visiontasker.reasoning',
        dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec('agent.perception', 'visiontasker_perception', 'zhixing.plugins.agent.visiontasker.perception',
        dependency_slots=(ComponentDependencySlot(name='vision', required=True,
            accepted_namespaces=('vision',), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,)),)),
    BuiltInComponentSpec('agent.verifier', 'visiontasker_verify', 'zhixing.plugins.agent.visiontasker.verifier',
        extra='visiontasker', required_modules=('cv2', 'skimage')),
    *(BuiltInComponentSpec('agent.' + family, 'visiontasker_' + name,
        'zhixing.plugins.agent.visiontasker.' + module)
      for family, module, names in (
          ('memory', 'memory', ('initialize', 'resume', 'feedback', 'record', 'pass', 'commit', 'finish')),
          ('perception', 'execution', ('observe',)),
          ('action_executor', 'execution', ('execute',)),
          ('reasoning', 'parser', ('parse',)))
      for name in names),
    BuiltInComponentSpec("llm", "guiexplorer_llm", "zhixing.plugins.llm.guiexplorer_llm"),
    BuiltInComponentSpec("knowledge", "guiexplorer_retrieval", "zhixing.knowledge.guiexplorer"),
    BuiltInComponentSpec("agent.memory", "guiexplorer_retrieve", "zhixing.plugins.agent.guiexplorer.memory",
        dependency_slots=(ComponentDependencySlot(name="retrieval", required=True,
            accepted_namespaces=("knowledge",), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,)),)),
    *(BuiltInComponentSpec("agent." + family, "guiexplorer_" + name,
        "zhixing.plugins.agent.guiexplorer." + module,
        dependency_slots=(_LLM_DEPENDENCY_SLOT,) if family == "reasoning" else ())
      for family, module, names in (
          ("memory", "memory", ("history", "finish")),
          ("perception", "execution", ("observe", "wait_round")),
          ("action_executor", "execution", ("execute",)),
          ("reasoning", "reasoning", ("rank", "select", "summary")))
      for name in names),
    BuiltInComponentSpec("agent.perception", "guiexplorer_perception", "zhixing.plugins.agent.guiexplorer.perception",
        extra="guiexplorer", required_modules=("numpy", "cv2")),
    BuiltInComponentSpec('llm', 'ecoagent_llm', 'zhixing.plugins.llm.ecoagent_llm'),
    *(BuiltInComponentSpec('agent.' + family, 'ecoagent_' + name,
        'zhixing.plugins.agent.ecoagent.' + module, dependency_slots=_ecoagent_model_slots(name))
      for family, module, names in (
          ('memory', 'memory', ('initialize', 'resume', 'join', 'continue', 'merge', 'commit', 'finish')),
          ('perception', 'perception', ('observe', 'description')),
          ('verifier', 'verifier', ('summary',)),
          ('reasoning', 'reasoning', ('predict', 'action')),
          ('planner', 'planning', ('plan',)),
          ('action_executor', 'execution', ('execute',)))
      for name in names),
    BuiltInComponentSpec('llm', 'androidarena_llm', 'zhixing.plugins.llm.androidarena_llm'),
    BuiltInComponentSpec('agent.perception', 'androidarena_screen', 'zhixing.plugins.agent.androidarena.perception'),
    BuiltInComponentSpec('agent.perception', 'androidarena_observe', 'zhixing.plugins.agent.androidarena.perception'),
    BuiltInComponentSpec('agent.perception', 'androidarena_perception', 'zhixing.plugins.agent.androidarena.perception',
        extra='androidarena', required_modules=('lxml', 'xmltodict')),
    BuiltInComponentSpec('agent.action_executor', 'androidarena_reset', 'zhixing.plugins.agent.androidarena.execution'),
    BuiltInComponentSpec('agent.action_executor', 'androidarena_execute', 'zhixing.plugins.agent.androidarena.execution'),
    BuiltInComponentSpec('agent.reasoning', 'androidarena_reasoning', 'zhixing.plugins.agent.androidarena.reasoning',
        dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec('agent.reasoning', 'androidarena_reflection', 'zhixing.plugins.agent.androidarena.reasoning',
        dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec('agent.verifier', 'androidarena_judge', 'zhixing.plugins.agent.androidarena.verifier',
        dependency_slots=(ComponentDependencySlot(name='judge_llm', required=True,
            accepted_namespaces=('llm',), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
            config_schema={'type': 'object', 'required': ['name', 'params'],
                'properties': {'namespace': {'type': 'string', 'const': 'llm'},
                    'name': {'type': 'string', 'minLength': 1}, 'version': {'type': ['string', 'null']},
                    'params': {'type': 'object'}}, 'additionalProperties': False}),)),
    *(BuiltInComponentSpec('agent.memory', 'androidarena_' + name, 'zhixing.plugins.agent.androidarena.memory')
      for name in ('initialize', 'trial', 'start', 'resume', 'pass', 'commit', 'end_trial', 'finish')),
    BuiltInComponentSpec("llm", "androidgen_llm", "zhixing.plugins.llm.androidgen_llm"),
    BuiltInComponentSpec("knowledge", "androidgen_examples", "zhixing.knowledge.androidgen"),
    BuiltInComponentSpec("agent.perception", "androidgen_perception", "zhixing.plugins.agent.androidgen.perception", extra="androidgen", required_modules=("numpy", "cv2")),
    BuiltInComponentSpec("agent.perception", "androidgen_observe", "zhixing.plugins.agent.androidgen.execution"),
    BuiltInComponentSpec("agent.action_executor", "androidgen_setup", "zhixing.plugins.agent.androidgen.execution"),
    BuiltInComponentSpec("agent.action_executor", "androidgen_execute", "zhixing.plugins.agent.androidgen.execution"),
    BuiltInComponentSpec("agent.verifier", "androidgen_feedback", "zhixing.plugins.agent.androidgen.reasoning"),
    BuiltInComponentSpec("agent.reasoning", "androidgen_reasoning", "zhixing.plugins.agent.androidgen.reasoning", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.planner", "androidgen_reflect_plan", "zhixing.plugins.agent.androidgen.planning",
        dependency_slots=(ComponentDependencySlot(name="planner_llm", required=True,
            accepted_namespaces=("llm",), accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
            config_schema={"type": "object", "required": ["name", "params"],
                "properties": {"namespace": {"type": "string", "const": "llm"},
                    "name": {"type": "string", "minLength": 1},
                    "version": {"type": ["string", "null"]}, "params": {"type": "object"}},
                "additionalProperties": False}),)),
    BuiltInComponentSpec("agent.memory", "androidgen_bootstrap", "zhixing.plugins.agent.androidgen.memory",
        dependency_slots=(ComponentDependencySlot(name="examples", required=True, accepted_namespaces=("knowledge",),
            accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
            config_schema={"type": "object", "required": ["namespace", "name", "params"],
                "properties": {"namespace": {"const": "knowledge"}, "name": {"type": "string", "minLength": 1},
                    "params": {"type": "object"}}, "additionalProperties": False}),)),
    *(BuiltInComponentSpec("agent.memory", "androidgen_" + name, "zhixing.plugins.agent.androidgen.memory")
      for name in ("pass", "resume", "history", "ready", "commit", "finish")),
    BuiltInComponentSpec("agent.memory", "m3a_pass", "zhixing.plugins.agent.m3a.memory"),
    BuiltInComponentSpec("llm", "m3a_llm", "zhixing.plugins.llm.m3a_llm"),
    BuiltInComponentSpec("agent.perception", "m3a_perception", "zhixing.plugins.agent.m3a.perception", extra="m3a", required_modules=("numpy", "cv2")),
    BuiltInComponentSpec("agent.perception", "m3a_observe", "zhixing.plugins.agent.m3a.execution"),
    BuiltInComponentSpec("agent.perception", "m3a_termination", "zhixing.plugins.agent.m3a.execution"),
    BuiltInComponentSpec("agent.reasoning", "m3a_select", "zhixing.plugins.agent.m3a.reasoning", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.reasoning", "m3a_summary", "zhixing.plugins.agent.m3a.reasoning", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.action_executor", "m3a_setup", "zhixing.plugins.agent.m3a.execution"),
    BuiltInComponentSpec("agent.action_executor", "m3a_execute", "zhixing.plugins.agent.m3a.execution"),
    BuiltInComponentSpec("agent.memory", "m3a_resume", "zhixing.plugins.agent.m3a.memory"),
    BuiltInComponentSpec("agent.memory", "m3a_history", "zhixing.plugins.agent.m3a.memory"),
    BuiltInComponentSpec("agent.memory", "m3a_commit", "zhixing.plugins.agent.m3a.memory"),
    BuiltInComponentSpec("agent.memory", "m3a_finish", "zhixing.plugins.agent.m3a.memory"),
    BuiltInComponentSpec("llm", "aguvis_llm", "zhixing.plugins.llm.aguvis_llm"),
    BuiltInComponentSpec("agent.reasoning", "aguvis_reasoning", "zhixing.plugins.agent.reasoning.aguvis", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.action_executor", "aguvis_prepare", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.action_executor", "aguvis_request", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.memory", "aguvis_advance", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.memory", "aguvis_answer", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.memory", "aguvis_merge", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.memory", "aguvis_history", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.memory", "aguvis_resume", "zhixing.plugins.agent.aguvis_adapters"),
    BuiltInComponentSpec("agent.perception", "vdroid_html", "zhixing.plugins.agent.vdroid.operations"),
    BuiltInComponentSpec("agent.planner", "vdroid_candidates", "zhixing.plugins.agent.vdroid.operations"),
    BuiltInComponentSpec("agent.planner", "ordered_argmax", "zhixing.plugins.agent.planner.ranking"),
    BuiltInComponentSpec("agent.verifier", "vdroid_batch_verifier", "zhixing.plugins.agent.vdroid.operations",
        dependency_slots=(ComponentDependencySlot(name="scorer", required=True,
            accepted_categories=(ComponentCategory.RUNTIME_SERVICE,),
            config_schema={"oneOf": [
                {"type": "object", "required": ["service"],
                 "properties": {"service": {"const": "vdroid_reward_head"}}, "additionalProperties": False},
                {"type": "object", "required": ["namespace", "name", "params"],
                 "properties": {"namespace": {"type": "string", "minLength": 1},
                     "name": {"type": "string", "minLength": 1},
                     "version": {"type": ["string", "null"]}, "params": {"type": "object"}},
                 "additionalProperties": False}]}),)),
    BuiltInComponentSpec("agent.grounder", "workflow_grounder", "zhixing.plugins.agent.workflow_compat", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.action_executor", "workflow_setup", "zhixing.plugins.agent.workflow_compat"),
    BuiltInComponentSpec("agent.planner", "workflow_planner", "zhixing.plugins.agent.workflow_compat", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.perception", "os_genesis_perception", "zhixing.plugins.agent.perception.os_genesis"),
    BuiltInComponentSpec("agent.perception", "grid_perception", "zhixing.plugins.agent.perception.grid"),
    BuiltInComponentSpec("agent.perception", "xml_som_perception", "zhixing.plugins.agent.perception.xml_som"),
    BuiltInComponentSpec("agent.memory", "workflow_state", "zhixing.plugins.agent.workflow_compat"),
    BuiltInComponentSpec("agent.perception", "workflow_perception", "zhixing.plugins.agent.workflow_compat"),
    BuiltInComponentSpec("agent.reasoning", "workflow_reasoning", "zhixing.plugins.agent.workflow_compat", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.verifier", "workflow_verifier", "zhixing.plugins.agent.workflow_compat"),
    BuiltInComponentSpec("agent.memory", "agent_sama_merge", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_resume", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_finish", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_pass", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_initialize", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_commit", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_begin_round", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_recovery_ready", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_after_reflection", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_invalid_control", "zhixing.plugins.agent.memory.agent_sama"),
    BuiltInComponentSpec("agent.memory", "agent_sama_record_atom", "zhixing.plugins.agent.agent_sama_execution"),
    BuiltInComponentSpec("agent.memory", "agent_sama_wait_complete", "zhixing.plugins.agent.agent_sama_execution"),
    BuiltInComponentSpec("device", "agent_sama_identity_before", "zhixing.devices.app_identity"),
    BuiltInComponentSpec("device", "agent_sama_identity_after", "zhixing.devices.app_identity"),
    BuiltInComponentSpec("agent.perception", "agent_sama_bind_observation", "zhixing.devices.app_identity"),
    BuiltInComponentSpec("agent.perception", "agent_sama_observation_request", "zhixing.devices.app_identity"),
    BuiltInComponentSpec("vision", "agent_sama_screen_parser", "zhixing.plugins.agent.perception.agent_sama"),
    BuiltInComponentSpec("agent.perception", "agent_sama_screen", "zhixing.plugins.agent.perception.agent_sama"),
    BuiltInComponentSpec("agent.perception", "agent_sama_describe", "zhixing.plugins.agent.perception.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.planner", "agent_sama_candidates", "zhixing.plugins.agent.planner.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.planner", "agent_sama_judge", "zhixing.plugins.agent.planner.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.planner", "agent_sama_recovery", "zhixing.plugins.agent.planner.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.reasoning", "agent_sama_actor", "zhixing.plugins.agent.reasoning.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.verifier", "agent_sama_reflection", "zhixing.plugins.agent.verifier.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.verifier", "agent_sama_recovery_gate", "zhixing.plugins.agent.verifier.agent_sama"),
    BuiltInComponentSpec("agent.verifier", "agent_sama_notes", "zhixing.plugins.agent.verifier.agent_sama", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.action_executor", "agent_sama_atom_request", "zhixing.plugins.agent.agent_sama_execution"),
    BuiltInComponentSpec("agent.action_executor", "agent_sama_wait_request", "zhixing.plugins.agent.agent_sama_execution"),
    BuiltInComponentSpec("agent.action_executor", "agent_sama_terminal_request", "zhixing.plugins.agent.agent_sama_execution"),
    BuiltInComponentSpec("llm", "agent_sama_llm", "zhixing.plugins.llm.agent_sama_llm"),
    BuiltInComponentSpec("agent.memory", "agent_sama_official_memory", "zhixing.plugins.agent.sama_official.roles"),
    BuiltInComponentSpec("agent.memory", "agent_sama_official_resume", "zhixing.plugins.agent.sama_official.boundaries"),
    BuiltInComponentSpec("agent.memory", "agent_sama_official_merge", "zhixing.plugins.agent.sama_official.boundaries"),
    BuiltInComponentSpec("agent.perception", "agent_sama_official_perception", "zhixing.plugins.agent.sama_official.roles", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.planner", "agent_sama_official_planner", "zhixing.plugins.agent.sama_official.roles", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.reasoning", "agent_sama_official_reasoning", "zhixing.plugins.agent.sama_official.roles", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.verifier", "agent_sama_official_verifier", "zhixing.plugins.agent.sama_official.roles", dependency_slots=(_LLM_DEPENDENCY_SLOT,)),
    BuiltInComponentSpec("agent.action_executor", "agent_sama_official_action_executor", "zhixing.plugins.agent.sama_official.roles"),
    BuiltInComponentSpec("vision", "agent_sama_official_screen_parser", "zhixing.plugins.agent.sama_official.boundaries"),
    BuiltInComponentSpec(
        "agent.memory", "seeclick_memory",
        "zhixing.plugins.agent.memory.seeclick",
    ),
    BuiltInComponentSpec(
        "agent.reasoning", "seeclick_reasoning",
        "zhixing.plugins.agent.reasoning.seeclick",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "llm", "seeclick_llm", "zhixing.plugins.llm.seeclick_llm",
    ),
    BuiltInComponentSpec(
        "agent.perception", "autodroid_perception",
        "zhixing.plugins.agent.perception.autodroid",
    ),
    BuiltInComponentSpec(
        "agent.memory", "autodroid_memory",
        "zhixing.plugins.agent.memory.autodroid",
    ),
    BuiltInComponentSpec(
        "agent.reasoning", "autodroid_reasoning",
        "zhixing.plugins.agent.reasoning.autodroid",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.perception",
        "screenshot_perception",
        "zhixing.plugins.agent.perception.screenshot",
    ),
    BuiltInComponentSpec(
        "agent.perception",
        "coordinate_perception",
        "zhixing.plugins.agent.perception.coordinate",
    ),
    BuiltInComponentSpec(
        "agent.reasoning",
        "universal_reasoning",
        "zhixing.plugins.agent.reasoning.universal_reasoning",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.memory",
        "sliding_window_memory",
        "zhixing.plugins.agent.memory.sliding_window",
    ),
    BuiltInComponentSpec(
        "agent.memory",
        "summary_memory",
        "zhixing.plugins.agent.memory.summary_memory",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.planner",
        "universal_planner",
        "zhixing.plugins.agent.planner.universal_planner",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.verifier",
        "screen_diff_verifier",
        "zhixing.plugins.agent.verifier.screen_diff",
        extra="vision",
        required_modules=("cv2", "numpy"),
    ),
    BuiltInComponentSpec(
        "agent.verifier",
        "llm_reflect_verifier",
        "zhixing.plugins.agent.verifier.llm_reflect",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "agent.verifier",
        "android_content_delta_verifier",
        "zhixing.plugins.agent.verifier.android_content_delta",
    ),
    BuiltInComponentSpec(
        "agent.action_executor",
        "legacy_action_executor",
        "zhixing.engine.agent.legacy_action_executor",
    ),
    BuiltInComponentSpec(
        "agent.grounder",
        "uground_grounder",
        "zhixing.plugins.agent.grounder.uground",
        dependency_slots=(_LLM_DEPENDENCY_SLOT,),
    ),
    BuiltInComponentSpec(
        "llm",
        "openai_llm",
        "zhixing.plugins.llm.openai_llm",
        extra="openai",
        required_modules=("openai",),
    ),
    BuiltInComponentSpec(
        "zhixing.control",
        "action_request",
        "zhixing.runtime.transforms",
    ),
    BuiltInComponentSpec(
        "zhixing.control",
        "verification_terminal_action",
        "zhixing.runtime.transforms",
    ),
    BuiltInComponentSpec(
        "zhixing.runtime",
        "device_observe",
        "zhixing.runtime.transforms",
    ),
    BuiltInComponentSpec(
        "zhixing.runtime",
        "action_executor",
        "zhixing.runtime.transforms",
    ),
)

_PARSER_MODULES = (
    "zhixing.plugins.agent.parsers.seeclick_action_parser",
    "zhixing.plugins.agent.parsers.appagent_action_parser",
    "zhixing.plugins.agent.parsers.gui_schema_action_parser",
    "zhixing.plugins.agent.parsers.guicourse_action_parser",
    "zhixing.plugins.agent.parsers.json_action_parser",
    "zhixing.plugins.agent.parsers.mobile_agent_action_parser",
    "zhixing.plugins.agent.parsers.mobile_use_tool_parser",
    "zhixing.plugins.agent.parsers.mobimind_parser",
    "zhixing.plugins.agent.parsers.os_genesis_action_parser",
    "zhixing.plugins.agent.parsers.section_parser",
    "zhixing.plugins.agent.parsers.seeact_uground_action_parser",
    "zhixing.plugins.agent.parsers.showui_action_parser",
)


class BuiltInComponentCatalog:
    """Resolve only framework-owned, explicitly listed component modules."""

    def __init__(
        self,
        specs: tuple[BuiltInComponentSpec, ...] = _SPECS,
    ) -> None:
        """Create a deterministic catalog without importing component modules.

        Args:
            specs (tuple[BuiltInComponentSpec, ...]): Explicit supported entries.

        Raises:
            ValueError: Duplicate namespace/name declarations are present.

        Returns:
            None: Initializes an immutable lookup table.
        """
        entries: dict[tuple[str, str], BuiltInComponentSpec] = {}
        for spec in specs:
            key = (spec.namespace, spec.name)
            if key in entries and entries[key] != spec:
                raise ValueError(f"conflicting built-in component {spec.identifier}")
            entries[key] = spec
        self._entries = MappingProxyType(entries)

    def get(self, namespace: str, name: str) -> BuiltInComponentSpec | None:
        """Return one declaration without importing its module.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Raises:
            None.

        Returns:
            BuiltInComponentSpec | None: Matching declaration.
        """
        return self._entries.get((namespace, name))

    def entries(self) -> tuple[BuiltInComponentSpec, ...]:
        """Return supported entries in deterministic order.

        Args:
            None.

        Raises:
            None.

        Returns:
            tuple[BuiltInComponentSpec, ...]: Sorted catalog entries.
        """
        return tuple(self._entries[key] for key in sorted(self._entries))

    def ensure(self, namespace: str, name: str) -> type[Any]:
        """Import and return one selected built-in plugin class.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Raises:
            LookupError: The component is not framework-owned.
            BuiltInComponentUnavailableError: An optional dependency or import fails.

        Returns:
            type[Any]: Registered component class.
        """
        spec = self.get(namespace, name)
        if spec is None:
            raise LookupError(f"unknown built-in component {namespace}:{name}")
        missing = tuple(
            module
            for module in spec.required_modules
            if importlib.util.find_spec(module) is None
        )
        if missing:
            hint = f"; install zhixing[{spec.extra}]" if spec.extra else ""
            raise BuiltInComponentUnavailableError(
                f"built-in component {spec.identifier} requires {', '.join(missing)}{hint}"
            )
        try:
            if namespace in {"agent.reasoning", "agent.planner"}:
                for module in _PARSER_MODULES:
                    importlib.import_module(module)
            importlib.import_module(spec.module)
            return PluginRegistry.get_plugin(namespace, name)
        except BuiltInComponentUnavailableError:
            raise
        except Exception as error:
            hint = f"; install zhixing[{spec.extra}]" if spec.extra else ""
            raise BuiltInComponentUnavailableError(
                f"built-in component {spec.identifier} is unavailable "
                f"({type(error).__name__}){hint}"
            ) from error

    def availability(self, namespace: str, name: str) -> BuiltInAvailability:
        """Inspect one selected catalog entry without leaking import messages.

        Args:
            namespace (str): Component namespace.
            name (str): Component name.

        Raises:
            None: Unavailable entries are returned as data.

        Returns:
            BuiltInAvailability: Structured availability result.
        """
        spec = self.get(namespace, name)
        identifier = f"{namespace}:{name}"
        if spec is None:
            return BuiltInAvailability(identifier, False, error_type="unknown_component")
        try:
            self.ensure(namespace, name)
        except Exception as error:
            return BuiltInAvailability(
                identifier,
                False,
                extra=spec.extra,
                error_type=type(error).__name__,
            )
        return BuiltInAvailability(identifier, True, extra=spec.extra)


BUILTIN_COMPONENT_CATALOG = BuiltInComponentCatalog()


class BuiltInComponentResolver(RegistryComponentResolver):
    """Instantiate selected built-ins with explicit secrets and dependencies."""

    def __init__(
        self,
        *,
        catalog: BuiltInComponentCatalog = BUILTIN_COMPONENT_CATALOG,
        secret_provider: Mapping[str, Any] | Callable[[str], Any] | None = None,
        dependency_provider: Mapping[str, Any] | None = None,
        constructor_kwargs: Mapping[str, Any] | None = None,
    ) -> None:
        """Configure production binding without scanning installed packages.

        Args:
            catalog (BuiltInComponentCatalog): Explicit framework catalog.
            secret_provider (Mapping[str, Any] | Callable[[str], Any] | None):
                Runtime-only SecretRef provider.
            dependency_provider (Mapping[str, Any] | None): Prebuilt dependencies.
            constructor_kwargs (Mapping[str, Any] | None): Explicit constructor defaults.

        Raises:
            None.

        Returns:
            None: Initializes the resolver.
        """
        super().__init__(
            secret_provider=secret_provider,
            dependency_provider=dependency_provider,
            constructor_kwargs=constructor_kwargs,
        )
        self.catalog = catalog

    def _dependency(self, name: str, specification: Any) -> Any:
        """Resolve nested built-in dependencies after deterministic import.

        Args:
            name (str): Constructor dependency name.
            specification (Any): Literal or nested component reference.

        Raises:
            LookupError: A nested built-in is unavailable.

        Returns:
            Any: Resolved dependency instance or literal value.
        """
        if name in self.dependency_provider:
            return super()._dependency(name, specification)
        if isinstance(specification, Mapping) and specification.get("name"):
            namespace = str(
                specification.get("namespace")
                or ("llm" if name == "llm" else f"agent.{name}")
            )
            self.catalog.ensure(namespace, str(specification["name"]))
        return super()._dependency(name, specification)

    def resolve(
        self,
        reference: GraphComponentRef,
        role: GraphRole | None = None,
    ) -> Any:
        """Instantiate one selected built-in component.

        Args:
            reference (GraphComponentRef): Declarative component reference.
            role (GraphRole | None): Expected core role, used by adapters later.

        Raises:
            LookupError: Component or dependency is unavailable.
            TypeError: Constructor parameters are incompatible.

        Returns:
            Any: New component instance.
        """
        spec = self.catalog.get(reference.namespace, reference.name)
        if spec is None:
            raise LookupError(
                f"unknown built-in component {reference.namespace}:{reference.name}"
            )
        if reference.version is not None and reference.version != spec.version:
            raise LookupError(
                f"built-in component {spec.identifier} does not provide "
                f"version {reference.version!r}"
            )
        self.catalog.ensure(reference.namespace, reference.name)
        return super().resolve(reference, role)  # type: ignore[arg-type]


def create_builtin_resolver(
    *,
    secrets: Mapping[str, Any] | Callable[[str], Any] | None = None,
    dependencies: Mapping[str, Any] | None = None,
) -> BuiltInComponentResolver:
    """Create the default framework-owned component resolver.

    Args:
        secrets (Mapping[str, Any] | Callable[[str], Any] | None): Secret provider.
        dependencies (Mapping[str, Any] | None): Prebuilt named dependencies.

    Raises:
        None.

    Returns:
        BuiltInComponentResolver: Fresh deterministic resolver.
    """
    return BuiltInComponentResolver(
        secret_provider=secrets,
        dependency_provider=dependencies,
    )


__all__ = [
    "BUILTIN_COMPONENT_CATALOG",
    "BuiltInAvailability",
    "BuiltInComponentCatalog",
    "BuiltInComponentResolver",
    "BuiltInComponentSpec",
    "BuiltInComponentUnavailableError",
    "create_builtin_resolver",
]
