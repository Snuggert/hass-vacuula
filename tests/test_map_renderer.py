"""Unit tests for pure-Python map rendering and RLE decoding."""

from __future__ import annotations

from custom_components.vacuula.map_renderer import (
    MAX_MAP_DIM,
    _decode_rle,
    _fill_polygon,
    _parse_hex_color,
    compute_cropped_zones,
    get_crop_box,
    render_map_png,
)


def test_parse_hex_color() -> None:
    """Test hex color parsing with valid, invalid, and edge-case values."""
    assert _parse_hex_color("#ff5500") == (255, 85, 0)
    assert _parse_hex_color("00ff00") == (0, 255, 0)
    assert _parse_hex_color("invalid") == (90, 169, 255)
    assert _parse_hex_color(None) == (90, 169, 255)  # type: ignore[arg-type]


def test_decode_rle_standard() -> None:
    """Test standard RLE decoding."""
    rle = [[1, 5], [2, 3], [0, 2]]
    decoded = _decode_rle(rle, expected_len=10, default_val=0)
    assert len(decoded) == 10
    assert list(decoded) == [1, 1, 1, 1, 1, 2, 2, 2, 0, 0]


def test_decode_rle_padding_and_truncation() -> None:
    """Test RLE decoding with padding and truncation."""
    # Under-length -> padded with default_val
    decoded_short = _decode_rle([[1, 2]], expected_len=5, default_val=99)
    assert len(decoded_short) == 5
    assert list(decoded_short) == [1, 1, 99, 99, 99]

    # Over-length -> truncated to expected_len
    decoded_long = _decode_rle([[1, 10]], expected_len=4, default_val=0)
    assert len(decoded_long) == 4
    assert list(decoded_long) == [1, 1, 1, 1]


def test_decode_rle_memory_exhaustion_guard() -> None:
    """Test that a malicious/corrupted huge count does not allocate unbounded memory."""
    huge_count = 10_000_000_000
    rle = [[1, huge_count], [2, 5]]
    decoded = _decode_rle(rle, expected_len=20, default_val=0)
    assert len(decoded) == 20
    assert list(decoded) == [1] * 20


def test_get_crop_box_invalid_dimensions() -> None:
    """Test get_crop_box with empty or out-of-bounds maps."""
    assert get_crop_box(None, None) == (0, 0, 1, 1, 1, 1)
    assert get_crop_box({"width": 0, "height": 10}) == (0, 0, 1, 1, 1, 1)
    assert get_crop_box({"width": -5, "height": 10}) == (0, 0, 1, 1, 1, 1)
    assert get_crop_box({"width": MAX_MAP_DIM + 1, "height": 100}) == (0, 0, 1, 1, 1, 1)
    assert get_crop_box({"width": 100, "height": MAX_MAP_DIM + 1}) == (0, 0, 1, 1, 1, 1)


def test_get_crop_box_auto_crop() -> None:
    """Test auto-cropping around non-empty floor cells."""
    # 10x10 map, non-empty pixel at (4, 4)
    floormap = {
        "width": 10,
        "height": 10,
        "rle": [[0, 44], [1, 1], [0, 55]],
    }
    c_x0, c_y0, c_w, c_h, w, h = get_crop_box(floormap, pad=2)
    assert w == 10
    assert h == 10
    assert c_x0 == 2  # max(0, 4 - 2)
    assert c_y0 == 2  # max(0, 4 - 2)
    assert c_w == 5  # (4 + 2) - 2 + 1
    assert c_h == 5


def test_compute_cropped_zones() -> None:
    """Test coordinate normalization of room boundaries."""
    floormap = {
        "width": 100,
        "height": 100,
        "rle": [[1, 10000]],
    }
    boundaries = [
        {
            "id": "bnd-1",
            "name": "Living Room",
            "type": "polygon",
            "color": "#38bdf8",
            "vertices": [
                [0.1, 0.1],
                [0.5, 0.1],
                [0.5, 0.5],
                [0.1, 0.5],
                [0.1, 0.1],  # Closed
            ],
        },
        {
            "id": "bnd-line",
            "name": "No-Go",
            "type": "polyline",  # Ignored by compute_cropped_zones
            "vertices": [[0.0, 0.0], [1.0, 1.0]],
        },
    ]
    zones = compute_cropped_zones(floormap, boundaries)
    assert len(zones) == 1
    z = zones[0]
    assert z["id"] == "bnd-1"
    assert z["name"] == "Living Room"
    assert z["color"] == "#38bdf8"
    assert 0.0 <= z["x"] <= 1.0
    assert 0.0 <= z["y"] <= 1.0
    assert len(z["points"]) == 5


def test_render_map_png_output() -> None:
    """Test PNG rendering produces a valid PNG stream."""
    floormap = {
        "width": 20,
        "height": 20,
        "rle": [[1, 400]],
        "dock": {"pixel_x": 10, "pixel_y": 10},
    }
    boundaries = [
        {
            "id": "zone-1",
            "name": "Kitchen",
            "type": "polygon",
            "color": "#5aa9ff",
            "vertices": [[0.1, 0.1], [0.8, 0.1], [0.8, 0.8], [0.1, 0.8]],
        },
        {
            "id": "nogo-1",
            "name": "Wires",
            "type": "polyline",
            "vertices": [[0.2, 0.2], [0.4, 0.4]],
        },
    ]
    runmap = {
        "width": 20,
        "height": 20,
        "rle": [[3, 100], [150, 10], [128, 290]],
    }
    png_bytes = render_map_png(floormap, boundaries=boundaries, runmap=runmap)
    assert png_bytes is not None
    # Check PNG magic signature: \x89PNG\r\n\x1a\n
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    # Check IEND chunk exists at end
    assert b"IEND" in png_bytes


def test_render_map_png_dimension_bounds() -> None:
    """Test that oversized maps return None immediately."""
    assert render_map_png({"width": MAX_MAP_DIM + 1, "height": 100, "rle": []}) is None
    assert render_map_png({"width": 100, "height": MAX_MAP_DIM + 1, "rle": []}) is None
    assert render_map_png(None) is None


def test_map_renderer_edge_cases() -> None:
    """Test edge cases in hex parsing, crop box with runmap, and uncropped fallback."""
    # 6-char invalid hex value causes ValueError inside try/except
    assert _parse_hex_color("ZZZZZZ") == (90, 169, 255)

    # get_crop_box with runmap expanding bounds
    floormap = {
        "width": 20,
        "height": 20,
        "rle": [[0, 200], [1, 1], [0, 199]],  # (0, 10)
    }
    runmap = {
        "width": 20,
        "height": 20,
        "rle": [[128, 50], [3, 1], [128, 349]],  # (10, 2)
    }
    c_x0, c_y0, c_w, c_h, _, _ = get_crop_box(floormap, runmap=runmap, pad=1)
    assert c_x0 <= 10
    assert c_y0 <= 2

    # compute_cropped_zones with < 3 valid vertices or degenerate polygon
    bad_boundaries = [
        {"id": "b1", "name": "Bad", "type": "polygon", "vertices": [[0.1, 0.1]]},
        {"id": "b2", "name": "Bad2", "type": "polygon", "vertices": "not a list"},
    ]
    assert compute_cropped_zones(floormap, bad_boundaries) == []

    # render_map_png with runmap containing dock marker (val 100) and uncropped map
    empty_floormap = {"width": 10, "height": 10, "rle": [[0, 100]]}
    png_empty = render_map_png(empty_floormap)
    assert png_empty is not None
    assert png_empty.startswith(b"\x89PNG")


def test_render_map_gen4_base_and_normalized_dock() -> None:
    """Test dock rendering with Gen4 world coords (flipped Y) and normalized base fallback."""
    # Gen4 floormap with base and metadata
    gen4_floormap = {
        "width": 100,
        "height": 100,
        "rle": [[1, 10000]],
        "base": [1.0, 2.0, 0.0],
        "metadata": {
            "origin_x": 0.0,
            "origin_y": 0.0,
            "resolution": 0.05,
        },
    }
    png_gen4 = render_map_png(gen4_floormap)
    assert png_gen4 is not None
    assert png_gen4.startswith(b"\x89PNG")

    # Normalized base fallback (e.g. [0.5, 0.5])
    norm_floormap = {
        "width": 50,
        "height": 50,
        "rle": [[1, 2500]],
        "base": [0.5, 0.5],
    }
    png_norm = render_map_png(norm_floormap)
    assert png_norm is not None
    assert png_norm.startswith(b"\x89PNG")


def test_map_renderer_additional_edge_cases() -> None:
    """Test degenerate polygons, zero-resolution metadata, walls, and dock markers."""
    # 1. _fill_polygon with degenerate < 3 vertices
    rgba = bytearray(10 * 10 * 4)
    _fill_polygon(rgba, None, 10, 10, [(1, 1), (2, 2)], (255, 0, 0))
    # Buffer should remain completely unmodified
    assert all(b == 0 for b in rgba)

    # 2. _decode_rle with negative count
    decoded = _decode_rle([[1, -5]], expected_len=3, default_val=0)
    assert list(decoded) == [0, 0, 0]

    # 3. render_map_png with walls (val=2), dock marker (val=100 & 200), and zero resolution
    map_with_walls_and_zero_res = {
        "width": 10,
        "height": 10,
        "rle": [[2, 50], [1, 50]],  # Half walls, half free floor
        "base": [1.0, 1.0],
        "metadata": {
            "origin_x": 0.0,
            "origin_y": 0.0,
            "resolution": 0.0,  # Zero resolution edge case
        },
    }
    runmap_with_docks = {
        "width": 10,
        "height": 10,
        "rle": [[100, 5], [200, 5], [128, 90]],  # Dock markers
    }
    png = render_map_png(map_with_walls_and_zero_res, runmap=runmap_with_docks)
    assert png is not None
    assert png.startswith(b"\x89PNG")
