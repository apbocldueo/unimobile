"""Shared coordinate normalization for perception plugins (0–1000 VLM scale)."""

from __future__ import annotations

from typing import Any

# VLM-friendly coordinate scale (e.g. Qwen3-VL often outputs 0–1000 taps).
COORDINATE_SCALE_MAX = 1000


def pixel_to_normalized_coordinate(
    x: int,
    y: int,
    width: int,
    height: int,
    *,
    scale_max: int = COORDINATE_SCALE_MAX,
) -> tuple[int, int]:
    """Map pixel center to ``[0, scale_max]`` on each axis (width → x, height → y)."""
    if width <= 0 or height <= 0:
        return x, y
    nx = int(round(x / width * scale_max))
    ny = int(round(y / height * scale_max))
    return (
        max(0, min(scale_max, nx)),
        max(0, min(scale_max, ny)),
    )


def normalized_coordinate_to_pixel(
    x: int | float,
    y: int | float,
    width: int,
    height: int,
    *,
    scale_max: int = COORDINATE_SCALE_MAX,
) -> tuple[int, int]:
    """Map ``[0, scale_max]`` tap coords back to pixel center for device execution."""
    if width <= 0 or height <= 0:
        return int(x), int(y)
    px = int(round(float(x) / scale_max * width))
    py = int(round(float(y) / scale_max * height))
    return (
        max(0, min(width - 1, px)),
        max(0, min(height - 1, py)),
    )


def apply_coordinate_normalization_to_elements(
    elements: list[dict[str, Any]],
    width: int,
    height: int,
    *,
    scale_max: int = COORDINATE_SCALE_MAX,
) -> list[dict[str, Any]]:
    """Replace each element's ``coordinates`` with normalized values; keep ``bbox`` / ``bbox_pixel`` unchanged."""
    out: list[dict[str, Any]] = []
    for ele in elements:
        item = dict(ele)
        coords = item.get("coordinates") or [0, 0]
        if len(coords) >= 2:
            item["coordinates"] = list(
                pixel_to_normalized_coordinate(
                    int(coords[0]), int(coords[1]), width, height, scale_max=scale_max
                )
            )
        out.append(item)
    return out


def build_coordinate_metadata(
    *,
    normalize_coordinates_to_1000: bool,
    coordinate_scale_max: int = COORDINATE_SCALE_MAX,
) -> dict[str, Any]:
    """Flags consumed by reasoning/parser for coordinate de-normalization."""
    return {
        "coordinates_normalized": bool(normalize_coordinates_to_1000),
        "coordinate_scale_max": coordinate_scale_max,
    }


def format_normalized_coordinate_instruction(
    *,
    coordinates_normalized: bool,
    coordinate_scale_max: int = COORDINATE_SCALE_MAX,
    pixel_mode_line: str = "Use Tap/Long_press with absolute pixel x,y from the Center column (not element index).",
) -> str:
    """One-line (or multi-line) prompt note for Tap coordinate scale."""
    if coordinates_normalized:
        return (
            f"IMPORTANT: Center (x, y) are on a 0–{coordinate_scale_max} scale (x relative to screen width, "
            f"y relative to screen height), NOT raw pixels. For Tap/Long_press, copy these Center "
            f"values exactly into arguments.x and arguments.y — the runtime converts them to device pixels."
        )
    return pixel_mode_line
