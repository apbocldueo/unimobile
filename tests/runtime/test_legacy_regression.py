from __future__ import annotations

from pathlib import Path

from PIL import Image

from zhixing.components import Action, ActionType, PerceptionResult
from zhixing.core.agent.protocol import PlanResult
from zhixing.core.factory import PluginRegistry
from zhixing.core.runner import AgentRunner
from zhixing.engine.agent.modular_agent import ModularAgent


def test_legacy_modular_agent_reset_and_step_remain_available(monkeypatch):
    class Perception:
        def __init__(self, **kwargs):
            pass

        def perceive(self, input):
            return PerceptionResult("legacy", input.screenshot_path)

    class Reasoning:
        def __init__(self, **kwargs):
            pass

        def think(self, task, plan, perception_result, memory_context, *, available_apps=""):
            return Action(ActionType.DONE), "done"

    class Memory:
        def __init__(self, **kwargs):
            self.values = []

        def add(self, value):
            self.values.append(value)

        def get_working_context(self):
            return list(self.values)

        def clear(self):
            self.values.clear()

        def retrieve_experience(self, screenshot_path, task):
            return None

        def load_knowledge(self, query):
            return None

    monkeypatch.setitem(PluginRegistry._registry, "agent.perception", {"legacy_p": Perception})
    monkeypatch.setitem(PluginRegistry._registry, "agent.reasoning", {"legacy_r": Reasoning})
    monkeypatch.setitem(PluginRegistry._registry, "agent.memory", {"legacy_m": Memory})
    agent = ModularAgent(
        config={
            "components": {
                "perception": {"name": "legacy_p"},
                "reasoning": {"name": "legacy_r"},
                "memory": {"name": "legacy_m"},
            }
        },
        device=object(),
    )
    agent.reset({"instruction": "legacy task"})
    action = agent.step("shot.png", 100, 200, "tree.xml")
    assert action.type is ActionType.DONE
    assert agent.current_task == "legacy task"


def test_legacy_agent_runner_entry_point_still_runs(monkeypatch, tmp_path):
    from zhixing.core import runner as runner_module

    class Device:
        def format_start_app_catalog_for_prompt(self):
            return "- settings"

        def screenshot(self, path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (10, 20)).save(path)

        def get_xml(self, path):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            Path(path).write_text("<hierarchy />", encoding="utf-8")

    class Agent:
        def __init__(self):
            self.reset_input = None

        def reset(self, value):
            self.reset_input = value

        def step(self, screenshot_path, width, height, xml_path):
            assert (width, height) == (10, 20)
            return Action(ActionType.DONE)

    monkeypatch.setattr(runner_module.os, "getcwd", lambda: str(tmp_path))
    monkeypatch.setattr(runner_module.time, "sleep", lambda _seconds: None)
    agent = Agent()
    trajectory = AgentRunner(Device()).run(
        agent,
        {"task_params": {"instruction": "legacy runner task"}},
        max_steps=1,
    )
    assert len(trajectory) == 1
    assert trajectory[0]["action"].type is ActionType.DONE
    assert agent.reset_input["instruction"] == "legacy runner task"
