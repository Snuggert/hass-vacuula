"""Pure-Python RLE map and boundary PNG renderer for Vacuula floorplans and run maps."""

from __future__ import annotations

import struct
import zlib
from typing import Any


def _parse_hex_color(
    hex_str: str, default: tuple[int, int, int] = (90, 169, 255)
) -> tuple[int, int, int]:
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


MAX_MAP_DIM = 4096


def _decode_rle(rle: list[list[int]], expected_len: int, default_val: int) -> bytearray:
    """Decode Vacuula [[value, count], ...] RLE array into a flat bytearray."""
    buf = bytearray()
    for pair in rle:
        if len(buf) >= expected_len:
            break
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            val = int(pair[0]) & 0xFF
            remaining = expected_len - len(buf)
            count = min(max(0, int(pair[1])), remaining)
            if count > 0:
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
                if floor_grid is not None and floor_grid[cell_idx] != 1:
                    continue
                idx = cell_idx * 4
                rgba[idx] = int(rgba[idx] * (1.0 - alpha) + r * alpha)
                rgba[idx + 1] = int(rgba[idx + 1] * (1.0 - alpha) + g * alpha)
                rgba[idx + 2] = int(rgba[idx + 2] * (1.0 - alpha) + b * alpha)


def _upscale_2x(rgba: bytearray, width: int, height: int) -> tuple[bytearray, int, int]:
    """Upscale an RGBA buffer by 2x using nearest-neighbor for crisp high-DPI rendering."""
    out_w = width * 2
    out_h = height * 2
    out = bytearray(out_w * out_h * 4)
    src_row_bytes = width * 4
    dst_row_bytes = out_w * 4

    for y in range(height):
        src_offset = y * src_row_bytes
        dst_row0 = (y * 2) * dst_row_bytes
        for x in range(width):
            sp = src_offset + x * 4
            pixel = rgba[sp : sp + 4]
            dp = dst_row0 + (x * 2) * 4
            out[dp : dp + 4] = pixel
            out[dp + 4 : dp + 8] = pixel
        # Duplicate row y*2 into y*2 + 1
        out[dst_row0 + dst_row_bytes : dst_row0 + 2 * dst_row_bytes] = out[
            dst_row0 : dst_row0 + dst_row_bytes
        ]
    return out, out_w, out_h


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
    idat = zlib.compress(bytes(raw_rows), level=1)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def _update_bbox_from_rle(
    rle: list[list[int]],
    width: int,
    total: int,
    ignore_val: int,
    min_x: int,
    min_y: int,
    max_x: int,
    max_y: int,
) -> tuple[int, int, int, int]:
    """Update (min_x, min_y, max_x, max_y) in O(runs) directly from RLE pairs."""
    idx = 0
    for pair in rle:
        if idx >= total:
            break
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            val = int(pair[0]) & 0xFF
            count = min(max(0, int(pair[1])), total - idx)
            if count <= 0:
                continue
            if val != ignore_val:
                y0, x0 = divmod(idx, width)
                y1, x1 = divmod(idx + count - 1, width)
                if y0 < min_y:
                    min_y = y0
                if y1 > max_y:
                    max_y = y1
                if y0 == y1:
                    if x0 < min_x:
                        min_x = x0
                    if x1 > max_x:
                        max_x = x1
                else:
                    min_x = 0
                    max_x = width - 1
            idx += count
    return min_x, min_y, max_x, max_y


def get_crop_box(
    floormap: dict[str, Any] | None,
    runmap: dict[str, Any] | None = None,
    pad: int = 16,
) -> tuple[int, int, int, int, int, int]:
    """Compute (c_x0, c_y0, c_w, c_h, width, height) for the auto-cropped map."""
    base_map = floormap or runmap
    if not base_map:
        return (0, 0, 1, 1, 1, 1)
    width = int(base_map.get("width", 0))
    height = int(base_map.get("height", 0))
    if width <= 0 or height <= 0 or width > MAX_MAP_DIM or height > MAX_MAP_DIM:
        return (0, 0, 1, 1, 1, 1)

    total = width * height
    min_x, min_y = width, height
    max_x, max_y = 0, 0

    if floormap and isinstance(floormap.get("rle"), list):
        min_x, min_y, max_x, max_y = _update_bbox_from_rle(
            floormap["rle"], width, total, 0, min_x, min_y, max_x, max_y
        )

    if runmap and isinstance(runmap.get("rle"), list):
        r_width = int(runmap.get("width", width))
        r_height = int(runmap.get("height", height))
        if r_width == width and r_height == height:
            min_x, min_y, max_x, max_y = _update_bbox_from_rle(
                runmap["rle"], width, total, 128, min_x, min_y, max_x, max_y
            )

    if min_x <= max_x and min_y <= max_y:
        c_x0 = max(0, min_x - pad)
        c_y0 = max(0, min_y - pad)
        c_x1 = min(width - 1, max_x + pad)
        c_y1 = min(height - 1, max_y + pad)
        return (c_x0, c_y0, c_x1 - c_x0 + 1, c_y1 - c_y0 + 1, width, height)

    return (0, 0, width, height, width, height)


def compute_cropped_zones(
    floormap: dict[str, Any] | None,
    boundaries: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return zone metadata with coordinates normalized [0..1] to the cropped PNG."""
    if not floormap or not boundaries:
        return []
    c_x0, c_y0, c_w, c_h, width, height = get_crop_box(floormap)
    result: list[dict[str, Any]] = []

    for bnd in boundaries:
        if bnd.get("type") != "polygon" or not bnd.get("name"):
            continue
        verts = bnd.get("vertices")
        if not isinstance(verts, list) or len(verts) < 3:
            continue

        pts: list[list[float]] = []
        for v in verts:
            if isinstance(v, (list, tuple)) and len(v) >= 2:
                px = float(v[0]) * width
                py = float(v[1]) * height
                nx = round(max(0.0, min(1.0, (px - c_x0) / c_w)), 4)
                ny = round(max(0.0, min(1.0, (py - c_y0) / c_h)), 4)
                pts.append([nx, ny])

        if len(pts) < 3:
            continue

        unique_pts = pts[:-1] if len(pts) > 3 and pts[0] == pts[-1] else pts
        cx = round(sum(p[0] for p in unique_pts) / len(unique_pts), 4)
        cy = round(sum(p[1] for p in unique_pts) / len(unique_pts), 4)

        result.append(
            {
                "id": bnd.get("id"),
                "name": bnd.get("name"),
                "color": bnd.get("color", "#5aa9ff"),
                "x": cx,
                "y": cy,
                "points": pts,
            }
        )
    return result


def render_map_png(
    floormap: dict[str, Any] | None,
    boundaries: list[dict[str, Any]] | None = None,
    runmap: dict[str, Any] | None = None,
) -> bytes | None:
    """Render a Vacuula floor map and/or run map into a cropped 2x high-DPI RGBA PNG."""
    base_map = floormap or runmap
    if not base_map:
        return None

    width = int(base_map.get("width", 0))
    height = int(base_map.get("height", 0))
    if width <= 0 or height <= 0 or width > MAX_MAP_DIM or height > MAX_MAP_DIM:
        return None

    total = width * height
    # Dark slate background (#181c24) initialized at C speed
    rgba = bytearray(b"\x18\x1c\x24\xff" * total)

    floor_grid: bytearray | None = None
    min_x, min_y = width, height
    max_x, max_y = 0, 0

    if floormap and isinstance(floormap.get("rle"), list):
        rle = floormap["rle"]
        if boundaries:
            floor_grid = _decode_rle(rle, total, 0)
        idx = 0
        for pair in rle:
            if idx >= total:
                break
            if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                val = int(pair[0]) & 0xFF
                count = min(max(0, int(pair[1])), total - idx)
                if count <= 0:
                    continue
                if val != 0:
                    y0, x0 = divmod(idx, width)
                    y1, x1 = divmod(idx + count - 1, width)
                    if y0 < min_y:
                        min_y = y0
                    if y1 > max_y:
                        max_y = y1
                    if y0 == y1:
                        if x0 < min_x:
                            min_x = x0
                        if x1 > max_x:
                            max_x = x1
                    else:
                        min_x = 0
                        max_x = width - 1
                    if val == 1:  # Free floor (#d4dce8)
                        rgba[idx * 4 : (idx + count) * 4] = b"\xd4\xdc\xe8\xff" * count
                    elif val == 2:  # Wall (#2d3748)
                        rgba[idx * 4 : (idx + count) * 4] = b"\x2d\x37\x48\xff" * count
                idx += count

    # Fill zone polygons on base floor grid
    parsed_boundaries: list[
        tuple[str, tuple[int, int, int], list[tuple[int, int]]]
    ] = []
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
            btype = str(bnd.get("type", "polygon"))
            rgb = _parse_hex_color(bnd.get("color", "#5aa9ff"))
            parsed_boundaries.append((btype, rgb, pts))
            if btype == "polygon":
                _fill_polygon(rgba, floor_grid, width, height, pts, rgb, alpha=0.40)

    # Overlay runmap if provided
    if runmap and isinstance(runmap.get("rle"), list):
        r_width = int(runmap.get("width", width))
        r_height = int(runmap.get("height", height))
        if r_width == width and r_height == height:
            idx = 0
            for pair in runmap["rle"]:
                if idx >= total:
                    break
                if isinstance(pair, (list, tuple)) and len(pair) >= 2:
                    val = int(pair[0]) & 0xFF
                    count = min(max(0, int(pair[1])), total - idx)
                    if count <= 0:
                        continue
                    if val != 128:
                        y0, x0 = divmod(idx, width)
                        y1, x1 = divmod(idx + count - 1, width)
                        if y0 < min_y:
                            min_y = y0
                        if y1 > max_y:
                            max_y = y1
                        if y0 == y1:
                            if x0 < min_x:
                                min_x = x0
                            if x1 > max_x:
                                max_x = x1
                        else:
                            min_x = 0
                            max_x = width - 1
                        if val == 3:  # Cleaned area (semi-transparent cyan overlay)
                            for c_idx in range(idx, idx + count):
                                p = c_idx * 4
                                rgba[p] = int(rgba[p] * 0.45 + 30.8)
                                rgba[p + 1] = int(rgba[p + 1] * 0.45 + 103.95)
                                rgba[p + 2] = int(rgba[p + 2] * 0.45 + 136.4)
                                rgba[p + 3] = 255
                        elif val == 150:  # Robot path (#0ea5e9)
                            rgba[idx * 4 : (idx + count) * 4] = (
                                b"\x0e\xa5\xe9\xff" * count
                            )
                        elif val in (100, 200):  # Dock marker (#22c55e)
                            rgba[idx * 4 : (idx + count) * 4] = (
                                b"\x22\xc5\x5e\xff" * count
                            )
                    idx += count

    # Draw zone outlines and no-go lines on top of run overlay so borders stay sharp
    for btype, rgb, pts in parsed_boundaries:
        if btype == "polygon":
            outline_rgba = (rgb[0], rgb[1], rgb[2], 255)
            for i in range(len(pts)):
                p0 = pts[i]
                p1 = pts[(i + 1) % len(pts)]
                _draw_line(
                    rgba,
                    width,
                    height,
                    p0[0],
                    p0[1],
                    p1[0],
                    p1[1],
                    outline_rgba,
                    thickness=1,
                )
        else:
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

    # Draw dock marker from floormap metadata
    dock = (floormap or {}).get("dock")
    dx: int | None = None
    dy: int | None = None
    if isinstance(dock, dict) and "pixel_x" in dock and "pixel_y" in dock:
        dx = int(round(float(dock["pixel_x"])))
        dy = int(round(float(dock["pixel_y"])))
    elif (
        floormap
        and isinstance(floormap.get("base"), (list, tuple))
        and len(floormap["base"]) >= 2
    ):
        base = floormap["base"]
        md = floormap.get("metadata")
        if (
            isinstance(md, dict)
            and "origin_x" in md
            and "origin_y" in md
            and "resolution" in md
        ):
            res = float(md["resolution"])
            if res > 0:
                px = (float(base[0]) - float(md["origin_x"])) / res
                py = (float(base[1]) - float(md["origin_y"])) / res
                dx = int(round(px))
                dy = int(round(height - 1 - py))
        elif 0.0 <= float(base[0]) <= 1.0 and 0.0 <= float(base[1]) <= 1.0:
            dx = int(round(float(base[0]) * width))
            dy = int(round(float(base[1]) * height))

    if dx is not None and dy is not None:
        for oy in range(-4, 5):
            for ox in range(-4, 5):
                px, py = dx + ox, dy + oy
                if 0 <= px < width and 0 <= py < height and ox * ox + oy * oy <= 18:
                    p = (py * width + px) * 4
                    if ox * ox + oy * oy <= 9:
                        rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (
                            34,
                            197,
                            94,
                            255,
                        )
                    else:
                        rgba[p], rgba[p + 1], rgba[p + 2], rgba[p + 3] = (
                            255,
                            255,
                            255,
                            255,
                        )

    # Auto-crop to non-empty bounding box with 16px padding, then 2x upscale
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
            cropped[dst_start : dst_start + c_w * 4] = rgba[
                src_start : src_start + c_w * 4
            ]
        up_rgba, up_w, up_h = _upscale_2x(cropped, c_w, c_h)
        return _encode_png(up_rgba, up_w, up_h)

    up_rgba, up_w, up_h = _upscale_2x(rgba, width, height)
    return _encode_png(up_rgba, up_w, up_h)
