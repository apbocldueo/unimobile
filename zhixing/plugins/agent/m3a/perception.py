"""M3A source UI/SoM encoding without device access or element renumbering."""

from __future__ import annotations

from pathlib import Path

from zhixing.components import DeviceObservation, RuntimeContext
from zhixing.core.factory import PluginRegistry

from . import source
from .types import M3AView, source_ui


def load_pixels(path: str):
    """Read RGB pixels losslessly from one captured/rendered PNG.

    Args:
        path: Image artifact path.
    Raises:
        OSError: Image cannot be read.
        ImportError: The M3A vision dependencies are absent.
    Returns:
        numpy.ndarray: Writable RGB uint8 pixels.
    """
    import numpy as np
    from PIL import Image

    with Image.open(path) as image:
        return np.array(image.convert("RGB"))


def save_pixels(pixels, path: Path) -> str:
    """Save exact pixels without JPEG loss before the original model wrapper.

    Args:
        pixels: RGB array to persist.
        path: Run-local PNG destination.
    Raises:
        OSError: Writing fails.
    Returns:
        str: Written artifact path.
    """
    from PIL import Image

    Image.fromarray(pixels).save(path)
    return str(path)


def mark_target(view: M3AView, index: int) -> str:
    """Apply the source's selected-target annotation to its raw screenshot copy.

    Args:
        view: Before-action view with the full ordered element list.
        index: Original index, with original Python negative-index behavior.
    Raises:
        Exception: Original index, geometry, drawing or persistence fails.
    Returns:
        str: Separate target image; the captured observation remains immutable.
    """
    data = view.observation.metadata["m3a"]
    pixels = load_pixels(view.raw)
    source.add_ui_element_mark(pixels, source_ui(data["ui_elements"])[index], index,
        tuple(data["logical_screen_size"]), tuple(data["physical_frame_boundary"]), data["orientation"])
    return save_pixels(pixels, Path(view.raw).with_name(Path(view.raw).stem + "-target.png"))


def label_before(view: M3AView) -> str:
    """Label the source's saved before copy, leaving the summary input unlabelled.

    Args:
        view: Before view whose original SoM is used as summary model input.
    Raises:
        Exception: Original drawing or image persistence fails.
    Returns:
        str: Labelled evidence image, preserving the official copy/alias quirk.
    """
    pixels = load_pixels(view.som)
    source.add_screenshot_label(pixels, "before")
    return save_pixels(pixels, Path(view.som).with_name(Path(view.som).stem + "-before.png"))


@PluginRegistry.register(namespace="agent.perception", name="m3a_perception")
class M3APerception:
    """Render exact official UI descriptions and marks from one explicit observation."""

    def __init__(self, *, after: bool = False) -> None:
        """Select the source after-image label policy.

        Args:
            after: Add the source after label for summary input/evidence.
        Returns:
            None.
        """
        self.after = after

    def invoke(self, input: DeviceObservation, runtime: RuntimeContext) -> M3AView:
        """Encode visible valid elements while retaining full source indexes.

        Args:
            input: Captured observation with explicit M3A UI and geometry data.
            runtime: Unused context; perception performs no device/model calls.
        Raises:
            Exception: Input, image, original geometry or drawing is invalid.
        Returns:
            M3AView: Ordered raw/SoM images and exact source UI description.
        """
        del runtime
        data = input.metadata["m3a"]
        elements = source_ui(data["ui_elements"])
        logical = tuple(data["logical_screen_size"])
        description = source._generate_ui_elements_description_list(elements, logical)
        pixels = load_pixels(input.screenshot_path)
        for index, element in enumerate(elements):
            if source.validate_ui_element(element, logical):
                source.add_ui_element_mark(pixels, element, index, logical,
                    tuple(data["physical_frame_boundary"]), data["orientation"])
        if self.after:
            source.add_screenshot_label(pixels, "after")
        path = Path(input.screenshot_path)
        marked = save_pixels(pixels, path.with_name(path.stem + "-som.png"))
        return M3AView(input, input.screenshot_path, marked, description)
