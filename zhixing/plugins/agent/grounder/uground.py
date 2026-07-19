import re
from typing import Any

from zhixing.core.factory import PluginRegistry
from zhixing.utils.utils import get_plugin_logger


@PluginRegistry.register(namespace="agent.grounder", name="uground_grounder")
class UGroundGrounder:
    """Ground a natural-language element description to a screen coordinate.

    This mirrors the SeeAct-V / UGround split: the planner chooses an action
    and describes the target element, while UGround predicts a 0-1000 point
    on a resized screenshot.
    """

    _pipeline_phase = "📍 Grounder"

    def __init__(
        self,
        llm_client: Any = None,
        model: str = "osunlp/UGround-V1-7B",
        resized_width: int = 882,
        resized_height: int = 1960,
        coordinate_scale_max: int = 1000,
        **kwargs: Any,
    ) -> None:
        namespace = getattr(self.__class__, "__plugin_namespace__", "agent.grounder")
        name = getattr(self.__class__, "__plugin_name__", self.__class__.__name__)
        self.logger = get_plugin_logger(phase=self._pipeline_phase, namespace=namespace, plugin_name=name)
        self.llm = llm_client
        self.model = model
        self.resized_width = int(resized_width)
        self.resized_height = int(resized_height)
        self.coordinate_scale_max = int(coordinate_scale_max)

    def ground(self, screenshot_path: str, description: str, width: int, height: int) -> tuple[int, int]:
        if not self.llm:
            raise RuntimeError("UGroundGrounder requires an llm_client")

        prompt = self._build_prompt(description)
        image_path = self._prepare_resized_image(screenshot_path)
        response = self.llm.generate(prompt, images=[image_path])
        x_ratio, y_ratio = self._parse_point(response)
        x = round(x_ratio / self.coordinate_scale_max * width)
        y = round(y_ratio / self.coordinate_scale_max * height)
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        self.logger.info("UGround resolved %r -> (%d, %d)", description, x, y)
        return x, y

    def _prepare_resized_image(self, screenshot_path: str) -> str:
        # Keep image resizing local to the grounder to reproduce UGround's fixed
        # 882x1960 visual input without changing the main perception screenshot.
        from PIL import Image

        with Image.open(screenshot_path) as img:
            img = img.convert("RGB")
            resized = img.resize((self.resized_width, self.resized_height))
            out_path = f"{screenshot_path}.uground.jpg"
            resized.save(out_path, format="JPEG")
        return out_path

    @staticmethod
    def _build_prompt(description: str) -> str:
        return (
            "Your task is to help the user identify the precise coordinates (x, y) "
            "of a specific area/element/object on the screen based on a description.\n\n"
            "- Your response should aim to point to the center or a representative point "
            "within the described area/element/object as accurately as possible.\n"
            "- If the description is unclear or ambiguous, infer the most relevant area "
            "or element based on its likely context or purpose.\n"
            "- Your answer should be a single string (x, y) corresponding to the point "
            "of the interest.\n\n"
            f"Description: {description}\n\n"
            "Answer:"
        )

    def _parse_point(self, response: str) -> tuple[float, float]:
        text = (response or "").strip()
        match = re.search(r"\(?\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)?", text)
        if not match:
            raise ValueError(f"UGround response does not contain a coordinate pair: {response!r}")
        return float(match.group(1)), float(match.group(2))
