"""Read-only App Memory and optional, lazily loaded semantic retrieval."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Protocol, Sequence

from zhixing.plugins.agent.autodroid_types import AppMemory, Guide, GuideHit, MemoryEntry, Target


class EmbeddingProvider(Protocol):
    """An injectable batch encoder; embeddings must share the memory's model."""

    def encode(self, texts: Sequence[str], instruction: str) -> Sequence[Sequence[float]]:
        """Encode text using the explicitly declared instruction.

        Args:
            texts: Sentences to encode.
            instruction: Instruction prefix, or empty for legacy plain sentences.
        Returns:
            Sequence[Sequence[float]]: One finite, nonzero vector per sentence.
        """
        ...


class InstructorEncoder:
    """Load INSTRUCTOR only when the selected Memory actually retrieves."""

    def __init__(self, model: str, device: str = "cpu") -> None:
        """Store configuration without imports, network or model construction.

        Args:
            model: INSTRUCTOR checkpoint identifier or local directory.
            device: Explicit inference device.
        Returns:
            None.
        """
        self.model_id = model
        self.device = device
        self._model = None

    def encode(self, texts: Sequence[str], instruction: str) -> Sequence[Sequence[float]]:
        """Generate embeddings using the selected optional backend.

        Args:
            texts: Sentences in the memory's declared encoding convention.
            instruction: INSTRUCTOR instruction, or empty for legacy inputs.
        Raises:
            RuntimeError: Optional embedding dependencies are missing.
            Exception: Checkpoint loading or inference fails.
        Returns:
            Sequence[Sequence[float]]: Dense vectors.
        """
        if self._model is None:
            try:
                from InstructorEmbedding import INSTRUCTOR
            except ImportError as error:
                raise RuntimeError("AutoDroid retrieval requires zhixing[autodroid] or an injected encoder") from error
            self._model = INSTRUCTOR(self.model_id, device=self.device)
        sentences = [[instruction, text] for text in texts] if instruction else list(texts)
        return self._model.encode(sentences, show_progress_bar=False).tolist()


def _read_json(path: Path) -> object:
    """Read one bounded UTF-8 memory artifact.

    Args:
        path: Explicit caller-owned input file.
    Raises:
        ValueError: Input exceeds 64 MiB or is not valid JSON.
        OSError: The file is unavailable.
    Returns:
        object: Decoded JSON data.
    """
    if path.stat().st_size > 64 * 1024 * 1024:
        raise ValueError("AutoDroid memory file exceeds 64 MiB")
    return json.loads(path.read_text(encoding="utf-8"))


def load_app_memory(path: str | Path, app_id: str = "", upstream_app: str = "") -> AppMemory:
    """Load normalized JSON or the upstream memory directory's parallel tables.

    Args:
        path: A normalized file or directory containing the three upstream tables.
        app_id: Expected Android package, required for an upstream directory.
        upstream_app: Optional original table key when different from the package.
    Raises:
        ValueError: Data is malformed, mismatched or for another app.
        OSError: A required file is unavailable.
    Returns:
        AppMemory: Validated immutable online memory input.
    """
    source = Path(path).expanduser()
    if source.is_file():
        memory = AppMemory.model_validate(_read_json(source))
        if app_id and memory.app_id != app_id:
            raise ValueError("AutoDroid memory app_id does not match configuration")
        return memory
    if not app_id:
        raise ValueError("upstream memory directory requires an explicit app_id")
    elements = _read_json(source / "node_filtered_elements.json")
    functions = _read_json(source / "element_description.json")
    embeddings = _read_json(source / "embedded_elements_desc.json")
    table_key = upstream_app or app_id
    if not all(isinstance(table, dict) and isinstance(table.get(table_key), dict)
               for table in (elements, functions, embeddings)):
        raise ValueError("upstream memory tables do not contain the configured app")
    entries: list[MemoryEntry] = []
    for state_id, state in elements[table_key].items():
        if not isinstance(state, dict) or not isinstance(state.get("elements"), list):
            raise ValueError("invalid upstream element table")
        descriptions = functions[table_key].get(state_id, [])
        vectors = embeddings[table_key].get(state_id, [])
        if not isinstance(descriptions, list) or not isinstance(vectors, list):
            raise ValueError("upstream descriptions and embeddings must be lists")
        if len(descriptions) != len(state["elements"]) or len(vectors) != len(descriptions):
            raise ValueError("upstream parallel table lengths differ")
        prefix = tuple(Target(description=description) for description in state.get("path", []))
        for index, (element, function, vector) in enumerate(zip(state["elements"], descriptions, vectors)):
            if not function or not vector:
                continue
            entries.append(MemoryEntry(id=f"{state_id}:{index}", task=function, function=function,
                                       path=(*prefix, Target(description=element)), embedding=vector))
    # The public TaskPolicy uses a plain 'task: ' query against its cached vectors.
    return AppMemory(app_id=app_id, embedding_instruction="", entries=tuple(entries))


def _vector(value: Sequence[float]) -> tuple[float, ...]:
    """Validate and unit-normalize a dense semantic vector.

    Args:
        value: Encoder output or cached embedding.
    Raises:
        ValueError: Values are empty, nonfinite, boolean or have zero norm.
    Returns:
        tuple[float, ...]: A finite unit vector.
    """
    if any(isinstance(item, bool) for item in value):
        raise ValueError("embedding values cannot be boolean")
    result = tuple(float(item) for item in value)
    norm = math.sqrt(sum(item * item for item in result))
    if not result or not all(math.isfinite(item) for item in result) or not math.isfinite(norm) or norm == 0:
        raise ValueError("embedding must be finite and nonzero")
    return tuple(item / norm for item in result)


class AppMemoryIndex:
    """Cosine-ranked memory with no lexical fallback or hidden data mutation."""

    def __init__(self, memory: AppMemory, encoder: EmbeddingProvider | None = None, device: str = "cpu") -> None:
        """Bind a snapshot and an explicit or optional lazy encoder.

        Args:
            memory: Validated App Memory.
            encoder: Injectable backend using the snapshot's embedding convention.
            device: Device for the default lazy backend.
        Returns:
            None.
        """
        self.memory = memory
        self.encoder = encoder or InstructorEncoder(memory.embedding_model, device)
        self._vectors: tuple[tuple[float, ...], ...] | None = None

    def retrieve(self, task: str, top_k: int = 3) -> Guide:
        """Retrieve simulated tasks and paths using cosine similarity.

        Args:
            task: Current user instruction.
            top_k: Number of relevant entries to return.
        Raises:
            ValueError: Encoder shape, dimensions or configured bounds are invalid.
            Exception: The selected embedding backend fails.
        Returns:
            Guide: Ranked immutable entries with stable tie ordering.
        """
        if not task.strip() or not 1 <= top_k <= 100:
            raise ValueError("retrieval requires a task and top_k in 1..100")
        if self._vectors is None:
            missing = [entry.task for entry in self.memory.entries if not entry.embedding]
            encoded = list(self.encoder.encode(missing, self.memory.embedding_instruction)) if missing else []
            if len(encoded) != len(missing):
                raise ValueError("encoder returned the wrong number of memory vectors")
            cursor = iter(encoded)
            self._vectors = tuple(_vector(entry.embedding or next(cursor)) for entry in self.memory.entries)
        query = task if self.memory.embedding_instruction else "task: " + task
        encoded_query = list(self.encoder.encode([query], self.memory.embedding_instruction))
        if len(encoded_query) != 1:
            raise ValueError("encoder returned the wrong number of query vectors")
        vector = _vector(encoded_query[0])
        if any(len(item) != len(vector) for item in self._vectors):
            raise ValueError("query and memory embedding dimensions differ")
        scores = [sum(left * right for left, right in zip(vector, candidate)) for candidate in self._vectors]
        order = sorted(range(len(scores)), key=lambda index: (-scores[index], self.memory.entries[index].id))[:top_k]
        return Guide(app_id=self.memory.app_id,
                     hits=tuple(GuideHit(entry=self.memory.entries[index], score=scores[index]) for index in order),
                     equivalent_groups=self.memory.equivalent_groups)
