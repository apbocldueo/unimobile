"""AndroidGen's one-shot ExpSearch, independent of the core six role contracts."""

import json

from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="knowledge", name="androidgen_examples")
class AndroidGenExamples:
    """Lazy original Contriever and complete/env-filtered experience library."""

    def __init__(self, database_path: str = "data/androidgen/experience.json",
                 retriever_ckpt_path: str = "facebook/contriever-msmarco", *,
                 device: str | None = None, max_batch_size: int = 400, retriever=None) -> None:
        """Remember public configuration; loading occurs at retrieval time only.

        Args:
            database_path: Original JSON experience dictionary.
            retriever_ckpt_path: Original Contriever checkpoint, local path or model ID.
            device: Original optional tensor device override.
            max_batch_size: Original candidate batch bound.
            retriever: Explicit original-compatible backend for dependency injection.
        Raises:
            ValueError: The source batch size is not a positive integer.
        Returns:
            None.
        """
        if type(max_batch_size) is not int or max_batch_size <= 0:
            raise ValueError("max_batch_size must be positive")
        self.database_path, self.checkpoint = database_path, retriever_ckpt_path
        self.device, self.batch_size, self.retriever = device, max_batch_size, retriever

    def retrieve_example(self, task, env, init_state, allow_same=True):
        """Use original complete/env filters and raw dot-product top-k selection.

        Args:
            task: Original user instruction, without a query prefix.
            env: Source environment name.
            init_state: Accepted but deliberately not used; source App filter is commented out.
            allow_same: Original optional exclusion rule; online default is True.
        Raises:
            Exception: Database, checkpoint or original retrieval fails.
        Returns:
            str | None: Original example string, or None for no eligible examples.
        """
        if self.retriever is None:
            from zhixing.plugins.agent.androidgen._retriever import Retriever

            self.retriever = Retriever(self.checkpoint, self.device, self.batch_size)
        with open(self.database_path, encoding="utf-8") as stream:
            database = json.load(stream)
        examples = [example for example in database.values() if example['complete'] and example['env'] == env]
        if not examples:
            return None
        tasks = [record['task'] for record in examples]
        if allow_same:
            index = int(self.retriever.select_topk(task, tasks, k=1).indices[0])
        else:
            indices = [int(value) for value in self.retriever.select_topk(task, tasks, k=10).indices]
            index = next((value for value in indices if examples[value]['task'] != task), indices[0])
        return examples[index]['example']
