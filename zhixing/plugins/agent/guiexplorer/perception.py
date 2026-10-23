"""Official GUI-explorer drawing/crops with shared M3A UI and image helpers."""

from pathlib import Path

from zhixing.components import DeviceObservation, RuntimeContext
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.m3a.perception import load_pixels, save_pixels

from . import source
from .types import GUIExplorerView


def source_ui(values):
    """Reconstruct source dataclasses from explicit portable observation data.

    Args:
        values: Ordered official GUI-explorer UI dictionaries.
    Raises:
        TypeError: Source UI fields or bounding boxes are malformed.
    Returns:
        list: Original UIElement instances in unchanged order.
    """
    return [source.UIElement(**dict(value)) for value in values]


def marked_target(view: GUIExplorerView, index: int) -> str:
    """Preserve the original selected-target raw-image copy, including negative indices.

    Args:
        view: Before view with full ordered UI data and geometry.
        index: Original parsed index.
    Raises:
        Exception: Source indexing, drawing or file I/O fails.
    Returns:
        str: Separate target image path; the action model input stays immutable.
    """
    data = view.observation.metadata["guiexplorer"]
    pixels = load_pixels(view.raw)
    source.add_ui_element_mark(pixels, source_ui(data["ui_elements"])[index], index,
        data["logical_screen_size"], data["physical_frame_boundary"], data["orientation"])
    return save_pixels(pixels, Path(view.raw).with_name(Path(view.raw).stem + "-target.png"))


@PluginRegistry.register(namespace="agent.perception", name="guiexplorer_perception")
class GUIExplorerPerception:
    """Encode one captured state without acquiring a device or loading a model."""

    def __init__(self, after: bool = False) -> None:
        """Select the source post-action label policy.

        Args:
            after: Label the after SoM and omit unused retrieval crops.
        Returns:
            None.
        """
        self.after = after

    def invoke(self, input: DeviceObservation, runtime: RuntimeContext) -> GUIExplorerView:
        """Render original descriptions/marks and preserve exact crop-index association.

        Args:
            input: Captured source UI, geometry, package and lossless screenshot.
            runtime: Unused context; this operation has no device/model access.
        Raises:
            Exception: Source data, image geometry, drawing or crop persistence fails.
        Returns:
            GUIExplorerView: Ordered source images, description and crop artifacts.
        """
        from PIL import Image

        del runtime
        data = input.metadata["guiexplorer"]
        elements = source_ui(data["ui_elements"])
        logical, physical, orientation = data["logical_screen_size"], data["physical_frame_boundary"], data["orientation"]
        pixels = load_pixels(input.screenshot_path)
        original = Image.fromarray(pixels)
        paths, indices = [], []
        path = Path(input.screenshot_path)
        for index, element in enumerate(elements):
            if not source.validate_ui_element(element, logical):
                continue
            source.add_ui_element_mark(pixels, element, index, logical, physical, orientation)
            if not self.after and element.bbox_pixels:
                upper, lower = source._ui_element_logical_corner(element, orientation)
                upper = source._logical_to_physical(upper, logical, physical, orientation)
                lower = source._logical_to_physical(lower, logical, physical, orientation)
                crop_path = path.with_name(f"{path.stem}-crop-{index}.png")
                original.crop((*upper, *lower)).save(crop_path)
                paths.append(str(crop_path))
                indices.append(index)
        if self.after:
            source.add_screenshot_label(pixels, "after")
        som = save_pixels(pixels, path.with_name(path.stem + "-som.png"))
        return GUIExplorerView(input, str(path), som,
            source._generate_ui_elements_description_list(elements, logical), tuple(indices), tuple(paths))
