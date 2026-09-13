"""Small side-effect-free Benchmark Package fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from zhixing.benchmark.resources import file_sha256


def task(task_id: str = "demo-1", *, local_path: str = "asset://fixture") -> dict:
    """Build one canonical static BenchmarkTask mapping.

    Args:
        task_id (str): Stable task identity.
        local_path (str): Host-side initializer resource reference.

    Raises:
        None.

    Returns:
        dict: Canonical V1 task mapping.
    """
    return {
        "id": task_id,
        "instruction": f"Open fixture for {task_id}",
        "app": "files",
        "type": "static",
        "task_initializer": {},
        "environment_initializer": [
            {
                "name": "push_file",
                "params": {
                    "local_path": local_path,
                    "phone_folder_path": "/storage/emulated/0/Download",
                },
            }
        ],
        "evaluator": {
            "name": "system_state",
            "params": {
                "method": "file_exist",
                "file_path": "/storage/emulated/0/Download/fixture.txt",
            },
        },
        "requires_login": False,
        "max_steps": 5,
    }


def write_package(
    root: Path,
    *,
    tasks: list[dict] | None = None,
    version: str = "1.0.0",
) -> Path:
    """Write one minimal, valid Benchmark Package fixture.

    Args:
        root (Path): Destination Package root.
        tasks (list[dict] | None): Optional task mappings.
        version (str): Package semantic version.

    Raises:
        OSError: Fixture files cannot be written.

    Returns:
        Path: Created Package root.
    """
    (root / "tasks").mkdir(parents=True)
    (root / "assets").mkdir()
    (root / "protocols").mkdir()
    asset = root / "assets" / "fixture.txt"
    asset.write_text("fixture\n", encoding="utf-8")
    selected_tasks = tasks or [task()]
    (root / "tasks" / "test.json").write_text(
        json.dumps(selected_tasks, ensure_ascii=False),
        encoding="utf-8",
    )
    protocol = {
        "schema_version": "1.0",
        "seed": 7,
        "repeats": 1,
        "task_order": {"strategy": "fixed"},
        "task_materialization": {"reuse_across_agents": True},
        "device": {
            "platform": "android",
            "locale": "en-US",
            "orientation": "portrait",
            "version_policy": "compatible",
        },
        "apps": [],
        "budget": {
            "max_interactions": 5,
            "max_activations": 20,
            "timeout_seconds": 60,
        },
        "isolation": {
            "reset": "before_each_agent",
            "cleanup": "after_each_run",
            "require_verified_reset": True,
        },
        "failure": {
            stage: {
                "outcome": (
                    "evaluate_if_possible" if stage == "agent" else "invalidate"
                ),
                "continue_suite": True,
                "preserve_evidence": True,
            }
            for stage in ("initializer", "agent", "evaluator", "cleanup")
        },
    }
    (root / "protocols" / "default.yaml").write_text(
        yaml.safe_dump(protocol, sort_keys=False),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": "1.0",
        "identity": {
            "publisher": "tests",
            "name": "fixture",
            "version": version,
        },
        "title": "Fixture Benchmark",
        "platforms": ["android"],
        "splits": {"test": {"files": ["tasks/test.json"]}},
        "resources": [
            {
                "id": "fixture",
                "kind": "asset",
                "path": "assets/fixture.txt",
                "media_type": "text/plain",
                "sha256": file_sha256(asset),
                "size": asset.stat().st_size,
            }
        ],
        "ground_truth": {},
        "apps": [
            {
                "id": "files",
                "platform": "android",
                "requires_login": False,
            }
        ],
        "plugins": [
            {"id": "push_file", "optional": False},
            {"id": "file_exist", "optional": False},
        ],
        "default_protocol": "protocols/default.yaml",
    }
    (root / "benchmark.yaml").write_text(
        yaml.safe_dump(manifest, sort_keys=False),
        encoding="utf-8",
    )
    return root

