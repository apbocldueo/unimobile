"""Stable identifiers used by the public AgentGraph V1 contract."""

from __future__ import annotations

from enum import Enum


class GraphRole(str, Enum):
    PERCEPTION = "perception"
    PLANNER = "planner"
    REASONING = "reasoning"
    MEMORY = "memory"
    ACTION_EXECUTOR = "action_executor"
    VERIFIER = "verifier"


class DataTypeId(str, Enum):
    TASK_INPUT = "task_input"
    DEVICE_OBSERVATION = "device_observation"
    PLAN_RESULT = "plan_result"
    PERCEPTION_RESULT = "perception_result"
    MEMORY_CONTEXT = "memory_context"
    ACTION = "action"
    ACTION_RESULT = "action_result"
    VERIFIER_RESULT = "verifier_result"
    CONTROL = "control"
    RUN_RESULT = "run_result"


class NodeKind(str, Enum):
    COMPONENT = "component"
    INPUT = "input"
    CONDITION = "condition"
    OUTPUT = "output"
    ROUTER = "router"
    STATE = "state"
    LOOP = "loop"
    SUBGRAPH = "subgraph"


class EdgeKind(str, Enum):
    DATA = "data"
    CONTROL = "control"
    FEEDBACK = "feedback"


class NodeLifecycle(str, Enum):
    ON_RUN_START = "on_run_start"
    PER_STEP = "per_step"
    POST_ACTION = "post_action"
    STATEFUL = "stateful"
    TERMINAL = "terminal"


class PredicateOperator(str, Enum):
    EQ = "eq"
    NE = "ne"
    TRUTHY = "truthy"
    FALSY = "falsy"
    EXISTS = "exists"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"


class FeedbackExhaustedPolicy(str, Enum):
    FAIL = "fail"
    CONTINUE = "continue"
    TERMINATE = "terminate"


class BindingPolicy(str, Enum):
    SINGLE = "single"
    FALLBACK = "fallback"


class PortDirection(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


class PortCardinality(str, Enum):
    SINGLE = "single"
    MULTIPLE = "multiple"


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class StateScope(str, Enum):
    RUN = "run"
    INTERACTION = "interaction"
    SUBGRAPH = "subgraph"
    LOOP = "loop"


class StateMergePolicy(str, Enum):
    REPLACE = "replace"
    APPEND = "append"


class StateOperation(str, Enum):
    READ = "read"
    WRITE = "write"


class LoopExhaustedPolicy(str, Enum):
    FAIL = "fail"
    CONTINUE = "continue"
    TERMINATE = "terminate"


class SubgraphErrorPolicy(str, Enum):
    PROPAGATE = "propagate"
    RETURN_ERROR = "return_error"


CORE_GRAPH_ROLES = tuple(GraphRole)
