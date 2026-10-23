"""Original AndroidGen text filtering and SoM, reusing M3A's pure image helpers."""

from dataclasses import replace
from pathlib import Path

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.m3a.perception import load_pixels, save_pixels
from zhixing.plugins.agent.m3a.source import add_ui_element_mark, validate_ui_element
from zhixing.plugins.agent.m3a.types import source_ui

from .source import Env
from .types import AndroidGenView


def encode_view(observation) -> AndroidGenView:
    """Render both source views without renumbering filtered UI elements.

    Args:
        observation: Full source UI/geometry and raw PNG from the explicit provider.
    Raises:
        Exception: UI, image or original marking is invalid.
    Returns:
        AndroidGenView: Original prompts and pre-action record with immutable images.
    """
    data = observation.metadata["androidgen"]
    elements = source_ui(data["ui_elements"])
    logical = tuple(data["logical_screen_size"])
    # These source methods are pure: their instance never holds device services.
    formatter = Env.__new__(Env)
    text = formatter._generate_ui_elements_description_list_full(elements, logical)
    pixels = load_pixels(observation.screenshot_path)
    for index, element in enumerate(elements):
        if validate_ui_element(element, logical):
            add_ui_element_mark(pixels, element, index, logical,
                tuple(data["physical_frame_boundary"]), data["orientation"])
    raw = Path(observation.screenshot_path)
    marked = save_pixels(pixels, raw.with_name(raw.stem + "-som.png"))
    record = {"env": "android", "app": data["app"], "image": marked, "raw": str(raw), "state": text}
    state = {"image": {"image_url": marked,
        "text": f"App Name: {record['app']}. The image is the current device screenshot."},
        "text": {"text": f"App Name: {record['app']}\nThe state of the current app: {text}"}}
    return AndroidGenView(observation, state, record)


@PluginRegistry.register(namespace="agent.perception", name="androidgen_perception")
class AndroidGenPerception:
    """Encode source observations as a separate, device-free graph operation."""

    def invoke(self, input, runtime):
        """Attach one encoded view to the current frame.

        Args:
            input: frame and observation ports.
            runtime: Unused context.
        Raises:
            Exception: Pure encoding fails.
        Returns:
            AndroidGenFrame: Current pre-action source state.
        """
        del runtime
        return replace(input["frame"], view=encode_view(input["observation"]), output={}, code="",
                       planning_done=False, planning_attempts=0)
