from __future__ import annotations

import copy
import importlib
from pathlib import Path

from zhixing.core.factory import PluginRegistry

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 test environments.
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[2]


def _project():
    with (ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)["project"]


def _names(requirements: list[str]) -> set[str]:
    return {
        item.split(";", 1)[0]
        .split("[", 1)[0]
        .split("<", 1)[0]
        .split(">", 1)[0]
        .split("=", 1)[0]
        .strip()
        .lower()
        for item in requirements
    }


def test_base_and_optional_dependency_boundaries():
    project = _project()
    assert _names(project["dependencies"]) == {"pydantic", "pyyaml", "pillow"}
    extras = project["optional-dependencies"]
    assert {"openai", "vision", "harmony", "benchmark", "all", "dev"} <= set(extras)
    assert _names(extras["openai"]) == {"openai"}
    assert _names(extras["vision"]) == {
        "numpy",
        "opencv-python",
        "requests",
        "torch",
        "transformers",
    }
    assert _names(extras["harmony"]) == {"hmdriver2"}
    assert _names(extras["benchmark"]) == {"pyperclip"}
    runtime_union = set().union(
        *(_names(extras[name]) for name in ("openai", "vision", "harmony", "benchmark"))
    )
    assert _names(extras["all"]) == runtime_union
    assert not {"pytest", "build", "twine"} & _names(project["dependencies"])
    assert not {"dashscope", "pyshine", "torchvision", "ultralytics"} & _names(extras["all"])


def test_requirements_files_are_thin_project_views():
    assert (ROOT / "requirements.txt").read_text(encoding="utf-8").strip() == ".[all]"
    assert (ROOT / "requirements-dev.txt").read_text(encoding="utf-8").strip() == "-e .[all,dev]"


def test_discovery_isolates_a_missing_optional_dependency(monkeypatch):
    original_import = importlib.import_module
    original_registry = copy.deepcopy(PluginRegistry._registry)

    def controlled_import(name: str, package=None):
        if name == "zhixing.plugins.agent.perception.grid":
            raise ModuleNotFoundError("No module named 'cv2'")
        return original_import(name, package)

    monkeypatch.setattr(importlib, "import_module", controlled_import)
    try:
        report = PluginRegistry.autodiscover("zhixing.plugins.agent.perception")
        assert any(item.module.endswith(".grid") for item in report.failures)
        assert any(item.endswith(".screenshot") for item in report.imported_modules)
        assert "screenshot_perception" in PluginRegistry._registry.get("agent.perception", {})
    finally:
        PluginRegistry._registry = original_registry
