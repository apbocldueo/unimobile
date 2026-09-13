"""Non-destructive Benchmark Package scaffolding."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

from .templates import TEMPLATE_NAMES, template_plugin_ids, template_task

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_.-]{0,127}$")


def scaffold_benchmark_package(
    destination: Path,
    *,
    name: str,
    publisher: str = "local",
    version: str = "0.1.0",
    template: str = "minimal",
    force: bool = False,
) -> Path:
    """Create a small valid Benchmark Package without running plugins.

    Args:
        destination (Path): Package directory to create.
        name (str): Stable package name.
        publisher (str): Stable publisher identity.
        version (str): Semantic version string.
        template (str): One of the built-in templates.
        force (bool): Explicitly permit replacing generated file names.

    Raises:
        ValueError: Identity or template is invalid.
        FileExistsError: Destination is non-empty and force is false.
        OSError: Files cannot be created.

    Returns:
        Path: Created Package root.
    """
    if not _IDENTIFIER.fullmatch(name) or not _IDENTIFIER.fullmatch(publisher):
        raise ValueError("publisher and name must be lowercase stable identifiers")
    if template not in TEMPLATE_NAMES:
        raise ValueError(f"template must be one of {', '.join(TEMPLATE_NAMES)}")
    root = Path(destination)
    if root.exists() and any(root.iterdir()) and not force:
        raise FileExistsError("destination is not empty; use explicit force mode")
    tasks_dir = root / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    (root / "assets").mkdir(exist_ok=True)
    (root / "ground_truth").mkdir(exist_ok=True)
    (root / "protocols").mkdir(exist_ok=True)
    task = template_task(template)
    manifest = {
        "schema_version": "1.0",
        "identity": {
            "publisher": publisher,
            "name": name,
            "version": version,
        },
        "title": f"{name} Benchmark",
        "platforms": ["android"],
        "splits": {"test": {"files": ["tasks/test.json"]}},
        "resources": [],
        "ground_truth": {},
        "apps": [],
        "plugins": [
            {"id": plugin_id, "optional": False}
            for plugin_id in template_plugin_ids(template)
        ],
        "default_protocol": "protocols/default.yaml",
    }
    protocol = {
        "schema_version": "1.0",
        "seed": 0,
        "repeats": 1,
        "task_order": {"strategy": "fixed"},
        "task_materialization": {
            "reuse_across_agents": True,
            "strict_fairness": False,
        },
        "device": {
            "platform": "android",
            "locale": "en-US",
            "orientation": "portrait",
            "version_policy": "compatible",
        },
        "apps": [],
        "budget": {
            "max_interactions": 5,
            "max_activations": 50,
            "timeout_seconds": 120,
        },
        "isolation": {
            "reset": "before_each_agent",
            "cleanup": "after_each_run",
            "require_verified_reset": False,
        },
        "failure": {
            "initializer": {
                "outcome": "invalidate",
                "continue_suite": True,
                "preserve_evidence": True,
            },
            "agent": {
                "outcome": "evaluate_if_possible",
                "continue_suite": True,
                "preserve_evidence": True,
            },
            "evaluator": {
                "outcome": "invalidate",
                "continue_suite": True,
                "preserve_evidence": True,
            },
            "cleanup": {
                "outcome": "invalidate",
                "continue_suite": True,
                "preserve_evidence": True,
            },
        },
    }
    files = {
        root / "benchmark.yaml": yaml.safe_dump(manifest, sort_keys=False),
        tasks_dir / "test.json": json.dumps(
            [task],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        root / "protocols/default.yaml": yaml.safe_dump(
            protocol,
            sort_keys=False,
        ),
        root / "README.md": (
            f"# {name}\n\n"
            f"Generated from the `{template}` teaching template. "
            "Validate and dry-run before executing it on a device.\n"
        ),
    }
    for path, content in files.items():
        if path.exists() and not force:
            raise FileExistsError(f"generated file already exists: {path.name}")
        path.write_text(content, encoding="utf-8")
    return root


__all__ = ["scaffold_benchmark_package"]
