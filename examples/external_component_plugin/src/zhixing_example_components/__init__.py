"""Standalone example provider for ZhiXing external components."""

from .components import RunLabeler, RunLabelerConfig, TaskRunLabeler
from .provider import (
    RUN_LABELER,
    RUN_LABELER_CONTRACT,
    TASK_RUN_LABELER,
    TASK_RUN_LABELER_CONTRACT,
    bundle,
)

__all__ = [
    "RUN_LABELER",
    "RUN_LABELER_CONTRACT",
    "TASK_RUN_LABELER",
    "TASK_RUN_LABELER_CONTRACT",
    "RunLabeler",
    "RunLabelerConfig",
    "TaskRunLabeler",
    "bundle",
]
