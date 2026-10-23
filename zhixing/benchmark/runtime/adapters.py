"""Compatibility imports for the former mixed Benchmark adapter module.

New runtime code should import ownership modules directly. This shim preserves
documented and legacy imports while keeping resolver, lifecycle, context, and
evaluator compatibility responsibilities physically separate.
"""

from ..compatibility import build_legacy_evaluator_context
from .context import preflight_device
from .lifecycle import execute_environment_calls, infer_environment_phase
from .resolver import (
    BenchmarkComponentResolver,
    RegistryBenchmarkComponentResolver,
)

__all__ = [
    "BenchmarkComponentResolver",
    "RegistryBenchmarkComponentResolver",
    "build_legacy_evaluator_context",
    "execute_environment_calls",
    "infer_environment_phase",
    "preflight_device",
]
