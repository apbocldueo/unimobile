"""Source knowledge/history adapters around unchanged shared episode and Memory nodes."""

from dataclasses import replace
import math
import os

from zhixing.components import Action, ActionResult, ActionType, ExecutionStatus, RunStatus
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.m3a.memory import M3AHistory

from .types import GUIExplorerKnowledge, KnowledgeEntry


@PluginRegistry.register(namespace="agent.memory", name="guiexplorer_history")
class GUIExplorerHistory:
    """Reuse the exact existing history-write policy with truthful source attribution."""

    def invoke(self, input, runtime):
        """Extract the prior accepted summary once, including the terminal flush.

        Args:
            input: Common M3AFrame cursor with source-specific step evidence.
            runtime: Unused context passed through the existing operation.
        Returns:
            MemoryFragment | None: Original text with GUI-explorer source metadata.
        """
        fragment = M3AHistory().invoke(input, runtime)
        return replace(fragment, metadata={**fragment.metadata, "source": "guiexplorer.summary"}) if fragment else None


@PluginRegistry.register(namespace="agent.memory", name="guiexplorer_retrieve")
class GUIExplorerRetrieve:
    """Read image knowledge every round; never cache a task-level text Guide."""

    def __init__(self, retrieval, top_k: int | None = None, threshold: float | None = None):
        """Bind the explicit original RAG client and defer environment defaults.

        Args:
            retrieval: Original-compatible image retrieval dependency.
            top_k: Source override; otherwise RAG_TOP_K, default 1.
            threshold: Source override; otherwise RAG_THRESHOLD, default 0.9.
        Raises:
            ValueError: Explicit retrieval settings are invalid.
        Returns:
            None.
        """
        if top_k is not None and (type(top_k) is not int or top_k < 1):
            raise ValueError("top_k must be a positive integer")
        if threshold is not None and (type(threshold) not in (int, float) or not math.isfinite(threshold)):
            raise ValueError("threshold must be finite")
        self.retrieval, self.top_k, self.threshold = retrieval, top_k, threshold
        self._settings = None

    def invoke(self, input, runtime):
        """Keep the original crop/result zip and original hint insertion order.

        Args:
            input: Source before view with full-index crop associations.
            runtime: Unused context; this operation cannot access a device.
        Raises:
            Exception: Original RAG retrieval or result mapping fails.
        Returns:
            GUIExplorerKnowledge: Complete nonempty element knowledge groups.
        """
        del runtime
        if self._settings is None:
            self._settings = (self.top_k if self.top_k is not None else int(os.getenv("RAG_TOP_K", 1)),
                              self.threshold if self.threshold is not None else float(os.getenv("RAG_THRESHOLD", 0.9)))
        top_k, threshold = self._settings
        data = input.observation.metadata["guiexplorer"]
        results = self.retrieval.retrieve_batch(input.crop_paths, top_k=top_k, threshold=threshold,
            package_name=data["top_app_package_name"])
        entries = tuple(KnowledgeEntry(index, tuple(item["knowledge"] for item in result))
                        for index, result in zip(input.crop_indices, results) if result)
        return GUIExplorerKnowledge(input, entries)


@PluginRegistry.register(namespace="agent.memory", name="guiexplorer_finish")
class GUIExplorerFinish:
    """Publish source episode facts independently of external Benchmark correctness."""

    def invoke(self, input, runtime):
        """Save complete source evidence and return a nonphysical terminal acknowledgment.

        Args:
            input: Finished common frame after final history flush.
            runtime: Run-owned artifact and terminal-state services.
        Raises:
            Exception: Source episode evidence cannot be persisted.
        Returns:
            tuple: Ordered action acknowledgments plus source stop/budget result.
        """
        status = RunStatus.STEP_LIMIT if not input.done else RunStatus.FAILURE if input.goal_status == "infeasible" else RunStatus.SUCCESS
        payload = {"source_commit": "01338e8ccc1c21d9897642ba197c6ac177e90118", "profile": "non-demo-online",
            "agent_done": input.done, "goal_status": input.goal_status, "decision_rounds": input.round_number,
            "episode": [step.evidence() for step in input.episode],
            "history": [step.evidence() for step in input.history], "benchmark_evaluated": False}
        path = runtime.artifacts.namespace / "guiexplorer-episode.json"
        runtime.artifacts.write_json(path, payload)
        ack = ActionResult(Action(ActionType.DONE if status is RunStatus.SUCCESS else ActionType.FAIL),
            ExecutionStatus.TERMINAL, terminal_status=status,
            metadata={"guiexplorer": payload, "artifact": runtime.artifacts.reference(path)})
        runtime.state.last_action, runtime.state.last_action_result = ack.action, ack
        return (*input.actions, ack)
