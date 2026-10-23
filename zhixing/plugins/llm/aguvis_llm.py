"""Optional lazy Qwen2-VL inference preserving the pinned Aguvis CLI protocol."""

from __future__ import annotations

from importlib import import_module
from importlib.resources import files
import json
from pathlib import Path

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.aguvis_types import AguvisRequest


def source_protocol() -> dict:
    """Read packaged source constants without checkpoint or cwd access.

    Raises:
        OSError: The package resource is missing.
    Returns:
        dict: Exact pinned source strings used for inference.
    """
    return json.loads(files("zhixing.prompts").joinpath("aguvis_protocol.json").read_text(encoding="utf-8"))


def request_messages(request: AguvisRequest, image) -> tuple[list[dict], str]:
    """Construct the original image-first messages and assistant prefill.

    Args:
        request: Validated single prediction with external action history.
        image: RGB PIL image, as expected by the source vision processor.
    Raises:
        ValueError: Mode or required request fields are invalid.
    Returns:
        tuple: Source system/user messages and separate recipient prefix.
    """
    if (not isinstance(request, AguvisRequest) or request.mode not in ("self-plan", "force-plan", "grounding")
            or not isinstance(request.instruction, str) or not request.instruction.strip()
            or not isinstance(request.previous_actions, tuple)
            or any(not isinstance(item, str) for item in request.previous_actions)
            or request.low_level_instruction is not None and not isinstance(request.low_level_instruction, str)):
        raise ValueError("invalid Aguvis request")
    protocol = source_protocol()
    messages = [{"role": "system", "content": protocol[
        "grounding_system_message" if request.mode == "grounding" else "agent_system_message"]},
        {"role": "user", "content": [{"type": "image", "image": image}, {"type": "text", "text":
            protocol["user_instruction"].format(overall_goal=request.instruction,
                previous_actions="\n".join(request.previous_actions) or "None",
                low_level_instruction=request.low_level_instruction)}]}]
    prefix = "<|im_start|>assistant<|recipient|>"
    if request.low_level_instruction:
        prefix += f"all\nAction: {request.low_level_instruction}\n"
    elif request.mode == "grounding":
        prefix += "os\n"
    elif request.mode == "force-plan":
        prefix += "all\nThought: "
    return messages, prefix


@PluginRegistry.register(namespace="llm", name="aguvis_llm")
class AguvisLLM:
    """Keep all optional imports and checkpoint access behind actual prediction."""

    def __init__(self, model_path: str = "xlangai/Aguvis-7B-720P", device: str = "cuda",
                 revision: str | None = "6dd54127b5b84b9ee89172a5065ab6be576f0db9",
                 local_files_only: bool = True, temperature: float = 0, max_new_tokens: int = 1024):
        """Store bounded inference configuration without I/O.

        Args:
            model_path: Local directory or explicitly cached model identifier.
            device: Explicit Torch placement; CUDA matches the source CLI.
            revision: Immutable model/config revision, or explicit caller override.
            local_files_only: Prohibit automatic downloads by default.
            temperature: Source generation temperature.
            max_new_tokens: Bounded generated continuation length.
        Raises:
            ValueError: Configuration is invalid.
        Returns:
            None.
        """
        import math
        if (not all(isinstance(item, str) and item.strip() for item in (model_path, device))
                or type(local_files_only) is not bool
                or revision is not None and (not isinstance(revision, str) or not revision.strip())
                or type(temperature) not in (int, float) or not math.isfinite(temperature) or not 0 <= temperature <= 2
                or type(max_new_tokens) is not int or not 1 <= max_new_tokens <= 8192):
            raise ValueError("invalid Aguvis model configuration")
        self.model_path, self.device, self.revision = model_path, device, revision
        self.local_files_only, self.temperature, self.max_new_tokens = local_files_only, temperature, max_new_tokens
        self._model = self._processor = self._torch = self._vision = None

    def _load(self) -> None:
        """Load inference-only optional dependencies on first real call.

        Raises:
            ImportError: Optional Aguvis inference dependencies are absent.
            Exception: Local checkpoint loading or placement fails.
        Returns:
            None: Cache handles only after all initialization succeeds.
        """
        if self._model is not None:
            return
        torch, transformers, vision = (import_module(name) for name in ("torch", "transformers", "qwen_vl_utils"))
        options = {"local_files_only": self.local_files_only}
        if self.revision is not None:
            options["revision"] = self.revision
        model = transformers.Qwen2VLForConditionalGeneration.from_pretrained(self.model_path, **options)
        processor = transformers.Qwen2VLProcessor.from_pretrained(self.model_path, **options)
        model.to(self.device)
        model.tie_weights()
        self._model, self._processor, self._torch, self._vision = model, processor, torch, vision

    def generate_aguvis(self, request: AguvisRequest) -> str:
        """Generate exactly one continuation with source preprocessing/decoding.

        Args:
            request: Current screenshot, goal, history and mode.
        Raises:
            ValueError: Request or screenshot is invalid.
            Exception: Optional model loading or inference fails.
        Returns:
            str: Source-style decoded continuation, excluding the prefill.
        """
        from PIL import Image
        if not isinstance(request, AguvisRequest) or not Path(request.screenshot_path).is_file():
            raise ValueError("Aguvis requires one existing screenshot")
        with Image.open(request.screenshot_path) as source_image:
            image = source_image.convert("RGB")
        messages, prefix = request_messages(request, image)
        self._load()
        text = self._processor.apply_chat_template(messages, tokenize=False, add_generation_prompt=False,
            chat_template=source_protocol()["chat_template"]) + prefix
        images, videos = self._vision.process_vision_info(messages)
        inputs = self._processor(text=[text], images=images, videos=videos, padding=True, return_tensors="pt")
        inputs = inputs.to(self._model.device)
        with self._torch.inference_mode():
            continuation = self._model.generate(**inputs, temperature=self.temperature, max_new_tokens=self.max_new_tokens)
        tokens = continuation.tolist()[0][len(inputs.input_ids[0]):]
        output = self._processor.tokenizer.decode(tokens, skip_special_tokens=True).strip()
        for stop in source_protocol()["until"]:
            if stop:
                output = output.split(stop)[0]
        return output
