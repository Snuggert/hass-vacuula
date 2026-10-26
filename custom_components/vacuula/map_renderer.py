"""Pure-Python RLE map and boundary PNG renderer for Vacuula floorplans and run maps."""

from __future__ import annotations

from .core.map_renderer import (
    MAX_MAP_DIM,
    _decode_rle,
    _draw_line,
    _encode_png,
    _fill_polygon,
    _parse_hex_color,
    _upscale_2x,
    compute_cropped_zones,
    get_crop_box,
    render_map_png,
)

__all__ = [
    "MAX_MAP_DIM",
    "_decode_rle",
    "_draw_line",
    "_encode_png",
    "_fill_polygon",
    "_parse_hex_color",
    "_upscale_2x",
    "compute_cropped_zones",
    "get_crop_box",
    "render_map_png",
]
