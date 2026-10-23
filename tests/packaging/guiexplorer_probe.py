"""Run installed GUI-explorer YAML from outside the repository with fake external I/O."""

from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys

from PIL import Image
import zhixing
from zhixing.components import RunStatus, RuntimeContext
from zhixing.graph import load_graph_yaml
from zhixing.guiexplorer import build_guiexplorer_graph
from zhixing.plugins.agent.guiexplorer.environment import GUIExplorerEnvironment
from zhixing.plugins.agent.guiexplorer.source import BoundingBox, UIElement
from zhixing.plugins.agent.guiexplorer.types import GUIExplorerReply
from zhixing.sdk import AgentRunConfig, compile_agent


class Model:
    """Script only external responses while installed components run unchanged."""

    def __init__(self):
        """Create isolated action/summary and comparison call counts."""
        self.calls, self.comparisons = 0, 0

    def generate_guiexplorer(self, prompt, images):
        """Return action, summary and termination responses to actual installed prompts.

        Args:
            prompt: Actual composed source prompt.
            images: Actual lossless source image paths.
        Returns:
            GUIExplorerReply: Scripted original model result.
        """
        self.calls += 1
        assert len(images) == 2 and all(Path(path).is_file() for path in images)
        if self.calls == 1:
            assert prompt.index("hint-B") < prompt.index("hint-A")
            return GUIExplorerReply('Reasoning: tap\nAction: {"action_type":"click","index":1}')
        if self.calls == 2:
            return GUIExplorerReply("Opened the target.")
        assert self.calls == 3 and "Step 1- Action selected:" in prompt and "Opened the target." in prompt
        return GUIExplorerReply('Reasoning: done\nAction: {"action_type":"status","goal_status":"complete"}')

    @asynccontextmanager
    async def ranking_session(self):
        """Yield one fake comparison service without importing aiohttp.

        Yields:
            Model: Source-compatible comparison session.
        """
        yield self

    async def ask(self, prompt, usage):
        """Choose the second knowledge entry using the actual source sorter.

        Args:
            prompt: Source comparison prompt.
            usage: Source token accumulator.
        Returns:
            str: Original comparison answer.
        """
        self.comparisons += 1
        usage["prompt_tokens"] += 1
        return "2"


class Device:
    """Explicit source Device fixture with complete required observation protocol."""

    def __init__(self):
        """Create local source UI and observable click/stability state."""
        self.clicks, self.waits = [], 0
        self.elements = [UIElement(text=str(index), is_visible=True, is_clickable=True,
            bbox_pixels=BoundingBox(10 + index * 100, 80 + index * 100, 40, 100)) for index in range(2)]

    def wait_to_stabilize(self):
        """Return an observable source stable state."""
        self.waits += 1
        return self.elements

    def _get_ui_elements(self):
        """Return the original fresh post-action UI."""
        return self.elements

    def get_orientation(self):
        """Return source portrait rotation."""
        return 0

    def get_screen_size(self):
        """Return source logical dimensions."""
        return (240, 400)

    def get_physical_frame_boundary(self):
        """Return source physical frame coordinates."""
        return (0, 0, 240, 400)

    def get_screenshot(self):
        """Return source-compatible local RGB pixels."""
        return Image.new("RGB", (240, 400), (80, 90, 100))

    def get_top_package_name(self):
        """Return the original package query field."""
        return "fixture.app"

    def click(self, x, y):
        """Record only an explicitly requested original click.

        Args:
            x, y: Original integer coordinates.
        Returns:
            None.
        """
        self.clicks.append((x, y))


class Retrieval:
    """External retrieval fixture that verifies actual installed crop artifacts."""

    def retrieve_batch(self, paths, **kwargs):
        """Return deterministic image knowledge for both original UI indices.

        Args:
            paths: Lossless original crop paths.
            kwargs: Original package/top-k/threshold.
        Returns:
            list: Original-shaped knowledge groups.
        """
        assert len(paths) == 2 and all(Path(path).is_file() for path in paths)
        assert kwargs == {"top_k": 1, "threshold": 0.9, "package_name": "fixture.app"}
        return [[{"knowledge": "hint-A"}], [{"knowledge": "hint-B"}]]


loaded = load_graph_yaml("guiexplorer_online.yaml")
assert loaded.is_success and loaded.graph.canonical_hash() == build_guiexplorer_graph().canonical_hash()
model, device, context = Model(), Device(), RuntimeContext(max_steps=31)
result = compile_agent(loaded, dependencies={"llm": model, "retrieval": Retrieval()}).run("Open the target",
    AgentRunConfig(artifact_root=Path("artifacts"), max_steps=31, include_ui_tree=False),
    device=GUIExplorerEnvironment(device), runtime=context)
assert result.status is RunStatus.SUCCESS, result.error
assert model.calls == 3 and model.comparisons == 2 and device.clicks == [(145, 70)] and device.waits == 4
payload = context.state.last_action_result.metadata["guiexplorer"]
assert payload["decision_rounds"] == 2 and len(payload["history"]) == 2 and payload["benchmark_evaluated"] is False
assert Path(zhixing.__file__).resolve().is_relative_to(Path(sys.prefix).resolve())
print("guiexplorer-installed:" + json.dumps({"status": result.status.value, "model_calls": model.calls}))
