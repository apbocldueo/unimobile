"""Optional lazy SeeClick/Qwen-VL inference behind the existing model interface."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

from zhixing.core.factory import PluginRegistry
from zhixing.core.llm.interfaces import BaseLLM


@PluginRegistry.register(namespace="llm", name="seeclick_llm")
class SeeClickLLM(BaseLLM):
    """Load a full or LoRA checkpoint only on the first actual prediction."""

    def __init__(
        self, model_path: str = "cckevinn/SeeClick-aitw",
        qwen_path: str = "Qwen/Qwen-VL-Chat", checkpoint_format: str = "full",
        device_map: str = "cuda", local_files_only: bool = True,
        trust_remote_code: bool = True, revision: str | None = None,
        qwen_revision: str | None = None,
    ) -> None:
        """Store model settings without imports, downloads or checkpoint access.

        Args:
            model_path: Local directory or cached SeeClick-AITW repository id.
            qwen_path: Matching Qwen-VL tokenizer and generation configuration.
            checkpoint_format: Full checkpoint or PEFT LoRA adapter.
            device_map: Explicit Transformers placement policy.
            local_files_only: Prohibit model/tokenizer downloads by default.
            trust_remote_code: Allow the checkpoint's Qwen-VL implementation.
            revision: Optional immutable model repository revision.
            qwen_revision: Optional immutable tokenizer/config repository revision.
        Raises:
            ValueError: A configuration value is invalid.
        Returns:
            None.
        """
        if (not all(isinstance(value, str) and value.strip() for value in (model_path, qwen_path, device_map))
                or checkpoint_format not in ("full", "lora")
                or type(local_files_only) is not bool or type(trust_remote_code) is not bool
                or any(value is not None and (not isinstance(value, str) or not value.strip())
                       for value in (revision, qwen_revision))):
            raise ValueError("invalid SeeClick model configuration")
        super().__init__(api_key="", model=model_path)
        self.model_path, self.qwen_path = model_path, qwen_path
        self.checkpoint_format, self.device_map = checkpoint_format, device_map
        self.local_files_only, self.trust_remote_code = local_files_only, trust_remote_code
        self.revision, self.qwen_revision = revision, qwen_revision
        self._backend = self._tokenizer = self._torch = None

    def _load(self) -> None:
        """Initialize optional inference dependencies and cache this client's model.

        Args:
            None.
        Raises:
            ImportError: Optional model runtime packages are not installed.
            Exception: The selected local checkpoint or configuration cannot load.
        Returns:
            None: Backend handles stay on the client, never in serialized run state.
        """
        if self._backend is not None:
            return
        torch, transformers = import_module("torch"), import_module("transformers")
        options = {"trust_remote_code": self.trust_remote_code,
                   "local_files_only": self.local_files_only}
        qwen_options = {**options, **({"revision": self.qwen_revision} if self.qwen_revision else {})}
        model_options = {**options, "device_map": self.device_map,
                         **({"revision": self.revision} if self.revision else {})}
        tokenizer = transformers.AutoTokenizer.from_pretrained(self.qwen_path, **qwen_options)
        if self.checkpoint_format == "lora":
            loader = import_module("peft").AutoPeftModelForCausalLM
        else:
            loader = transformers.AutoModelForCausalLM
            model_options["bf16"] = True
        backend = loader.from_pretrained(self.model_path, **model_options).eval()
        backend.generation_config = transformers.GenerationConfig.from_pretrained(self.qwen_path, **qwen_options)
        # Commit the cache only after all three loads succeed; a failed load
        # cannot leave a half-initialized client for a later run.
        self._torch, self._tokenizer, self._backend = torch, tokenizer, backend

    def _generate_impl(self, prompt: str, images: list[str] | None = None) -> tuple[str, None]:
        """Use the original image-first query and stateless model.chat call.

        Args:
            prompt: Original SeeClick mobile prompt assembled by Reasoning.
            images: Exactly one current screenshot file.
        Raises:
            ValueError: The image input or model response has an invalid shape.
            Exception: Optional loading or model inference fails.
        Returns:
            tuple[str, None]: Original response and unavailable token usage.
        """
        if (not isinstance(prompt, str) or not images or len(images) != 1
                or not isinstance(images[0], str) or not Path(images[0]).is_file()):
            raise ValueError("SeeClick requires exactly one screenshot file")
        self._load()
        query = self._tokenizer.from_list_format([{"image": images[0]}, {"text": prompt}])
        with self._torch.no_grad():
            response, _history = self._backend.chat(self._tokenizer, query=query, history=None)
        if not isinstance(response, str):
            raise ValueError("SeeClick model must return response text")
        return response, None
