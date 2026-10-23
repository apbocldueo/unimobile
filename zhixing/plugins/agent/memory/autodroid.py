"""App Memory retrieval and observed history through the existing Memory role."""

from __future__ import annotations

from dataclasses import dataclass, field

from zhixing.components import BaseMemory, MemoryInput, MemoryOperation, MemoryResult, RuntimeContext
from zhixing.core.agent.protocol import FragmentType, MemoryFragment
from zhixing.core.factory import PluginRegistry
from zhixing.knowledge.autodroid import AppMemoryIndex, EmbeddingProvider, load_app_memory


@dataclass
class _MemoryState:
    """Private per-run retrieval and history state."""

    task: str = ""
    history: list[MemoryFragment] = field(default_factory=list)
    guide: MemoryFragment | None = None


@PluginRegistry.register(namespace="agent.memory", name="autodroid_memory")
class AutoDroidMemory(BaseMemory):
    """Retrieve on READ; core-role execution does not call RETRIEVE_EXPERIENCE."""

    def __init__(self, memory_path: str, app_id: str = "", top_k: int = 3,
                 embedding: EmbeddingProvider | None = None, embedding_device: str = "cpu",
                 upstream_app: str = "") -> None:
        """Store lazy configuration without opening files or loading a model.

        Args:
            memory_path: Normalized JSON or upstream memory directory.
            app_id: Expected memory app, required for upstream directories.
            top_k: Relevant simulated task count.
            embedding: Injectable semantic encoder.
            embedding_device: Device for the optional INSTRUCTOR encoder.
            upstream_app: Original directory table key, if different from app_id.
        Raises:
            ValueError: Configuration is invalid.
        Returns:
            None.
        """
        if not memory_path or isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 100:
            raise ValueError("AutoDroid Memory requires a path and top_k in 1..100")
        self.memory_path, self.app_id, self.top_k = memory_path, app_id, top_k
        self.embedding, self.embedding_device = embedding, embedding_device
        self.upstream_app = upstream_app

    def invoke(self, input: MemoryInput, runtime: RuntimeContext) -> MemoryResult:
        """Append actual execution history or return cached task-specific guidance.

        Args:
            input: Existing RESET, APPEND or READ operation.
            runtime: Owner of all mutable task state.
        Raises:
            ValueError: An operation, task transition or memory input is invalid.
            Exception: Memory loading or semantic retrieval fails on first READ.
        Returns:
            MemoryResult: Structured Guide followed by observed history fragments.
        """
        key = "autodroid.memory"
        if input.operation is MemoryOperation.RESET:
            runtime.state.strategy_state.pop(key, None)
            return MemoryResult(input.operation)
        state = runtime.state.strategy_state.setdefault(key, _MemoryState())
        if input.operation is MemoryOperation.APPEND:
            fragment = input.fragment
            if fragment is None:
                raise ValueError("APPEND requires a fragment")
            if fragment.role == "user" and fragment.type is FragmentType.TEXT:
                task = str(fragment.content)
                if state.task and state.task != task:
                    raise ValueError("a new task requires a fresh RuntimeContext")
                state.task = task
            else:
                state.history.append(fragment)
            return MemoryResult(input.operation)
        if input.operation is not MemoryOperation.READ:
            raise ValueError("AutoDroid Memory supports RESET, APPEND and READ")
        if not state.task:
            raise ValueError("AutoDroid Memory must receive TaskInput before READ")
        if state.guide is None:
            memory = load_app_memory(self.memory_path, self.app_id, self.upstream_app)
            # Only inert retrieval data enters run state; the optional backend
            # and checkpoint remain local and cannot leak into result evidence.
            index = AppMemoryIndex(memory, self.embedding, self.embedding_device)
            guide = index.retrieve(state.task, self.top_k)
            state.guide = MemoryFragment("system", FragmentType.RAG_DOC, guide.model_dump(mode="json"),
                                        {"source": "autodroid.app_memory"})
        return MemoryResult(input.operation, fragments=(state.guide, *state.history))
