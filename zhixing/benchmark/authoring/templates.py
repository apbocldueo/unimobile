"""Built-in small Benchmark Package scaffold templates."""

from __future__ import annotations

from typing import Any

TEMPLATE_NAMES = ("minimal", "dynamic-task", "composite-evaluation")


def template_task(template: str) -> dict[str, Any]:
    """Return one canonical teaching task for a scaffold template.

    Args:
        template (str): Supported template name.

    Raises:
        ValueError: Template is unknown.

    Returns:
        dict[str, Any]: Canonical BenchmarkTask mapping.
    """
    if template not in TEMPLATE_NAMES:
        raise ValueError(f"unknown Benchmark template: {template}")
    base: dict[str, Any] = {
        "id": "example-task",
        "instruction": "Complete the example task",
        "type": "static",
        "task_initializer": {},
        "environment_initializer": [],
        "cleanup_initializer": [],
        "evaluator": {
            "name": "system_state",
            "params": {"method": "file_exist", "file_path": "/sdcard/example.txt"},
        },
        "requires_login": False,
        "max_steps": 5,
    }
    if template == "dynamic-task":
        base.update(
            {
                "instruction": "Create a note containing ${value}",
                "type": "dynamic",
                "task_initializer": {
                    "value": {
                        "name": "random_choice",
                        "params": {"candidates": ["alpha", "beta"]},
                    }
                },
            }
        )
    elif template == "composite-evaluation":
        base["evaluator"] = {
            "name": "composite",
            "params": {
                "logic": "THRESHOLD",
                "min_passed": 1,
                "rules": [
                    {
                        "name": "system_state",
                        "params": {
                            "method": "file_exist",
                            "file_path": "/sdcard/example.txt",
                        },
                    },
                    {
                        "name": "text",
                        "params": {
                            "method": "contains",
                            "expected": "example",
                        },
                    },
                ],
            },
        }
    return base


def template_plugin_ids(template: str) -> tuple[str, ...]:
    """Return logical plugin declarations used by a template.

    Args:
        template (str): Supported template name.

    Raises:
        ValueError: Template is unknown.

    Returns:
        tuple[str, ...]: Stable plugin identifiers.
    """
    if template not in TEMPLATE_NAMES:
        raise ValueError(f"unknown Benchmark template: {template}")
    values = ["file_exist"]
    if template == "dynamic-task":
        values.append("random_choice")
    if template == "composite-evaluation":
        values.append("contains")
    return tuple(values)


__all__ = ["TEMPLATE_NAMES", "template_plugin_ids", "template_task"]
