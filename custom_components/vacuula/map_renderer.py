"""Pure-Python RLE map and boundary PNG renderer for Vacuula floorplans and run maps."""
from __future__ import annotations

import struct
from typing import Any
import zlib


def _parse_hex_color(hex_str: str, default: tuple[int, int, int] = (90, 169, 255)) -> tuple[int, int, int]:
    """Parse a #RRGGBB hex string into an (R, G, B) tuple."""
    if not isinstance(hex_str, str):
        return default
    clean = hex_str.lstrip("#")
    if len(clean) == 6:
        try:
            return (int(clean[0:2], 16), int(clean[2:4], 16), int(clean[4:6], 16))
        except ValueError:
            return default
    return default


def _decode_rle(rle: list[list[int]], expected_len: int, default_val: int) -> bytearray:
    """Decode Vacuula [[value, count], ...] RLE array into a flat bytearray."""
    buf = bytearray()
    for pair in rle:
        if len(pair) >= 2:
            val = pair[0] & 0xFF
            count = max(0, int(pair[1]))
            buf.extend(bytes([val]) * count)
    if len(buf) < expected_len:
        buf.extend(bytes([default_val]) * (expected_len - len(buf)))
    elif len(buf) > expected_len:
        del buf[expected_len:]
    return buf


def _draw_line(
    rgba: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int, int],
    thickness: int = 1,
) -> None:
    """Draw a line using Bresenham's algorithm onto an RGBA bytearray."""
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    r, g, b, a = color

    while True:
        for ty in range(-thickness // 2, thickness // 2 + 1):
            for tx in range(-thickness // 2, thickness // 2 + 1):
                px = x0 + tx
                py = y0 + ty
                if 0 <= px < width and 0 <= py < height:
                    idx = (py * width + px) * 4
                    rgba[idx] = r
                    rgba[idx + 1] = g
                    rgba[idx + 2] = b
                    rgba[idx + 3] = a
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x0 += sx
        if e2 <= dx:
            err += dx
            y0 += sy


def _fill_polygon(
    rgba: bytearray,
    floor_grid: bytearray | None,
    width: int,
    height: int,
    pts: list[tuple[int, int]],
    color: tuple[int, int, int],
    alpha: float = 0.38,
) -> None:
    """Scanline-fill a polygon, tinting floor pixels with the zone color."""
    if len(pts) < 3:
        return
    min_y = max(0, min(p[1] for p in pts))
    max_y = min(height - 1, max(p[1] for p in pts))
    r, g, b = color
    n = len(pts)

    for y in range(min_y, max_y + 1):
        nodes: list[int] = []
        j = n - 1
        for i in range(n):
            xi, yi = pts[i]
            xj, yj = pts[j]
            if (yi < y <= yj) or (yj < y <= yi):
                x_intersect = int(xi + (y - yi) / (yj - yi) * (xj - xi))
                nodes.append(x_intersect)
            j = i
        nodes.sort()
        for k in range(0, len(nodes) - 1, 2):
            x_start = max(0, nodes[k])
            x_end = min(width - 1, nodes[k + 1])
            for x in range(x_start, x_end + 1):
                cell_idx = y * width + x
                # Only tint interior free-floor pixels (1) if floor_grid is present
                if floor_grid is not None and floor_grid[cell_idx] != 1:
                    continue
                idx = cell_idx * 4
                rgba[idx] = int(rgba[idx] * (1.0 - alpha) + r * alpha)
                rgba[idx + 1] = int(rgba[idx + 1] * (1.0 - alpha) + g * alpha)
                rgba[idx + 2] = int(rgba[idx + 2] * (1.0 - alpha) + b * alpha)


def _encode_png(rgba: bytearray, width: int, height: int) -> bytes:
    """Encode an RGBA bytearray into a standard PNG byte stream using stdlib zlib."""
    raw_rows = bytearray()
    row_bytes = width * 4
    for y in range(height):
        raw_rows.append(0)  # Filter type 0 (None)
        start = y * row_bytes
        raw_rows.extend(rgba[start : start + row_bytes])

    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    idat = zlib.compress(bytes(raw_rows), level=6)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def render_map_png(
    floormap: dict[str, Any] | None,
    boundaries: list[dict[str, Any]] | None = None,
    runmap: dict[str, Any] | None = None,
) -> bytes | None:
    """Render a Vacuula floor map and/or run map into a cropped RGBA PNG."""
    base_map = floormap or runmap
    if not base_map:
        return None

    width = int(base_map.get("width", 0))
    height = int(base_map.get("height", 0))
    if width <= 0 or height <= 0:
        return None

    total = width * height
    rgba = bytearray(total * 4)

    # Dark slate background (#181c24)
    bg_r, bg_g, bg_b, bg_a = (24, 28, 36, 255)
    for i in range(0, total * 4, 4):
        rgba[i] = bg_r
        rgba[i + 1] = bg_g
        rgba[i + 2] = bg_b
        rgba[i + 3] = bg_a

    floor_grid: bytearray | None = None
    min_x, min_y = width, height
    max_x, max_y = 0, 0

    if floormap and isinstance(floormap.get("rle"), list):
        floor_grid = _decode_rle(floormap["rle"], total, 0)
        for idx_cell, val in enumerate(floor_grid):
            if val == 0:
                continue
            y, x = divmod(idx_cell, width)
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y
            p = idx_cell * 4
            if val == 1:  # Free floor
                rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (212, 220, 232, 255)
            elif val == 2:  # Wall
                rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (45, 55, 72, 255)

    # Draw zone polygons and no-go lines if boundaries provided
    if boundaries and floormap:
        for bnd in boundaries:
            verts = bnd.get("vertices")
            if not isinstance(verts, list) or len(verts) < 2:
                continue
            pts = [
                (
                    max(0, min(width - 1, int(float(v[0]) * width))),
                    max(0, min(height - 1, int(float(v[1]) * height))),
                )
                for v in verts
                if isinstance(v, (list, tuple)) and len(v) >= 2
            ]
            if len(pts) < 2:
                continue
            btype = bnd.get("type", "polygon")
            if btype == "polygon":
                rgb = _parse_hex_color(bnd.get("color", "#5aa9ff"))
                _fill_polygon(rgba, floor_grid, width, height, pts, rgb, alpha=0.40)
                outline_rgba = (rgb[0], rgb[1], rgb[2], 255)
                for i in range(len(pts)):
                    p0 = pts[i]
                    p1 = pts[(i + 1) % len(pts)]
                    _draw_line(rgba, width, height, p0[0], p0[1], p1[0], p1[1], outline_rgba, thickness=1)
            else:
                # No-Go line (polyline) in red
                for i in range(len(pts) - 1):
                    _draw_line(
                        rgba,
                        width,
                        height,
                        pts[i][0],
                        pts[i][1],
                        pts[i + 1][0],
                        pts[i + 1][1],
                        (239, 68, 68, 255),
                        thickness=2,
                    )

    # Overlay runmap if provided
    if runmap and isinstance(runmap.get("rle"), list):
        r_width = int(runmap.get("width", width))
        r_height = int(runmap.get("height", height))
        if r_width == width and r_height == height:
            run_grid = _decode_rle(runmap["rle"], total, 128)
            for idx_cell, val in enumerate(run_grid):
                if val == 128:
                    continue
                y, x = divmod(idx_cell, width)
                if x < min_x:
                    min_x = x
                if x > max_x:
                    max_x = x
                if y < min_y:
                    min_y = y
                if y > max_y:
                    max_y = y
                p = idx_cell * 4
                if val == 3:  # Cleaned area (semi-transparent cyan overlay)
                    alpha = 0.55
                    rgba[p] = int(rgba[p] * (1.0 - alpha) + 56 * alpha)
                    rgba[p + 1] = int(rgba[p + 1] * (1.0 - alpha) + 189 * alpha)
                    rgba[p + 2] = int(rgba[p + 2] * (1.0 - alpha) + 248 * alpha)
                    rgba[p + 3] = 255
                elif val == 150:  # Robot path
                    rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (14, 165, 233, 255)
                elif val in (100, 200):  # Dock marker
                    rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (34, 197, 94, 255)

    # Draw dock marker from floormap metadata
    dock = (floormap or {}).get("dock")
    if isinstance(dock, dict) and "pixel_x" in dock and "pixel_y" in dock:
        dx = int(round(float(dock["pixel_x"])))
        dy = int(round(float(dock["pixel_y"])))
        for oy in range(-4, 5):
            for ox in range(-4, 5):
                px, py = dx + ox, dy + oy
                if 0 <= px < width and 0 <= py < height and ox * ox + oy * oy <= 18:
                    p = (py * width + px) * 4
                    if ox * ox + oy * oy <= 9:
                        rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (34, 197, 94, 255)
                    else:
                        rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (255, 255, 255, 255)

    # Auto-crop to non-empty bounding box with 16px padding
    if min_x <= max_x and min_y <= max_y:
        pad = 16
        c_x0 = max(0, min_x - pad)
        c_y0 = max(0, min_y - pad)
        c_x1 = min(width - 1, max_x + pad)
        c_y1 = min(height - 1, max_y + pad)
        c_w = c_x1 - c_x0 + 1
        c_h = c_y1 - c_y0 + 1
        cropped = bytearray(c_w * c_h * 4)
        for row in range(c_h):
            src_start = ((c_y0 + row) * width + c_x0) * 4
            dst_start = row * c_w * 4
            cropped[dst_start : dst_start + c_w * 4] = rgba[src_start : src_start + c_w * 4]
        return _encode_png(cropped, c_w, c_h)

    return _encode_png(rgba, width, height)
