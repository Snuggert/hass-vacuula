#!/usr/bin/env python3
"""Generate compliant Home Assistant MDI-style brand assets for Neato Botvac integration.

Creates clean, modern, flat-design Neato D-shape robot vacuum artwork in both
Light mode (dark charcoal body with Home Assistant blue accents) and
Dark mode (high-contrast silver/white body with cyan accents).
Zero trademark or vampire elements.
"""

from pathlib import Path

from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_BRAND_DIR = REPO_ROOT / "custom_components" / "vacuula" / "brand"
ROOT_BRAND_DIR = REPO_ROOT / "brand"
DOCS_ASSETS_DIR = REPO_ROOT / "docs" / "assets"


def draw_robot(size: int = 2048, dark_theme: bool = False) -> Image.Image:
    """Draw a high-res MDI-style Neato D-shape robot vacuum."""
    # Scale coordinates relative to 2048 canvas
    scale = size / 2048.0
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Color palette
    if dark_theme:
        # Dark theme palette (bright robot on transparent canvas, avg luminance > 180)
        c_body = (226, 232, 240, 255)       # Slate 200 (~230 lum)
        c_body_stroke = (148, 163, 184, 255) # Slate 400
        c_bumper = (241, 245, 249, 255)     # Slate 100
        c_bumper_line = (148, 163, 184, 255)
        c_turret_base = (203, 213, 225, 255) # Slate 300
        c_turret_top = (248, 250, 252, 255)  # Slate 50
        c_turret_core = (15, 23, 42, 255)    # Slate 900
        c_accent = (56, 189, 248, 255)       # HA Cyan / Sky 400
        c_accent_glow = (14, 165, 233, 255)  # Sky 500
        c_detail = (148, 163, 184, 255)
    else:
        # Light theme palette (dark robot on transparent canvas, avg luminance < 100)
        c_body = (30, 41, 59, 255)          # Slate 800 (~40 lum)
        c_body_stroke = (51, 65, 85, 255)   # Slate 700
        c_bumper = (15, 23, 42, 255)        # Slate 900 (~20 lum)
        c_bumper_line = (71, 85, 105, 255)  # Slate 600
        c_turret_base = (51, 65, 85, 255)   # Slate 700
        c_turret_top = (15, 23, 42, 255)    # Slate 900
        c_turret_core = (14, 165, 233, 255) # HA Blue
        c_accent = (2, 132, 199, 255)       # HA Sky 600
        c_accent_glow = (56, 189, 248, 255) # HA Sky 400
        c_detail = (71, 85, 105, 255)

    # 1. Main Neato D-shape Body
    # Flat top bumper edge from x=280 to 1768, y=360
    # Rounded top corners down to y=880
    # Semi-circular bottom arc from y=880 to 1840, centered around (1024, 1040)
    # Using composite primitives for crisp geometry

    # Rear semi-circle: center (1024, 1080), radius 744 (x: 280 to 1768, y: 336 to 1824)
    draw.pieslice(
        [(280 * scale, 336 * scale), (1768 * scale, 1824 * scale)],
        start=0,
        end=180,
        fill=c_body,
        outline=c_body_stroke,
        width=int(14 * scale),
    )

    # Front rectangular block: from x=280 to 1768, y=440 to 1080
    draw.rounded_rectangle(
        [(280 * scale, 340 * scale), (1768 * scale, 1080 * scale)],
        radius=int(120 * scale),
        fill=c_body,
        outline=c_body_stroke,
        width=int(14 * scale),
    )

    # Fill the seam between rectangle and semi-circle
    draw.rectangle(
        [(288 * scale, 800 * scale), (1760 * scale, 1080 * scale)],
        fill=c_body,
    )

    # 2. Front Bumper Assembly
    # Front bumper band at top
    draw.rounded_rectangle(
        [(280 * scale, 340 * scale), (1768 * scale, 600 * scale)],
        radius=int(120 * scale),
        fill=c_bumper,
        outline=c_body_stroke,
        width=int(14 * scale),
    )
    # Bottom cut of bumper
    draw.rectangle(
        [(280 * scale, 520 * scale), (1768 * scale, 600 * scale)],
        fill=c_bumper,
    )
    # Bumper separation line
    draw.line(
        [(280 * scale, 600 * scale), (1768 * scale, 600 * scale)],
        fill=c_bumper_line,
        width=int(16 * scale),
    )

    # 3. Dustbin Compartment & Handle Groove
    # Rounded dustbin panel in center
    draw.rounded_rectangle(
        [(580 * scale, 720 * scale), (1468 * scale, 1160 * scale)],
        radius=int(60 * scale),
        outline=c_detail,
        width=int(12 * scale),
    )
    # Bin release / handle latch
    draw.rounded_rectangle(
        [(884 * scale, 740 * scale), (1164 * scale, 790 * scale)],
        radius=int(24 * scale),
        fill=c_detail,
    )

    # 4. Laser Distance Sensor (LiDAR) Turret (Classic Neato signature)
    # Center (1024, 1440)
    turret_cx, turret_cy = 1024 * scale, 1420 * scale
    r_outer = 220 * scale
    r_mid = 180 * scale
    r_lens = 45 * scale

    # Outer turret ring / shadow
    draw.ellipse(
        [
            (turret_cx - r_outer, turret_cy - r_outer),
            (turret_cx + r_outer, turret_cy + r_outer),
        ],
        fill=c_turret_base,
        outline=c_body_stroke,
        width=int(12 * scale),
    )

    # Inner raised cap
    draw.ellipse(
        [
            (turret_cx - r_mid, turret_cy - r_mid),
            (turret_cx + r_mid, turret_cy + r_mid),
        ],
        fill=c_turret_top,
        outline=c_detail,
        width=int(10 * scale),
    )

    # Laser scanner aperture slit
    draw.rounded_rectangle(
        [
            (turret_cx - 150 * scale, turret_cy - 24 * scale),
            (turret_cx + 150 * scale, turret_cy + 24 * scale),
        ],
        radius=int(18 * scale),
        fill=c_turret_core,
    )

    # Center optical element with vivid Home Assistant blue accent
    draw.ellipse(
        [
            (turret_cx - r_lens, turret_cy - r_lens),
            (turret_cx + r_lens, turret_cy + r_lens),
        ],
        fill=c_accent,
        outline=c_accent_glow,
        width=int(6 * scale),
    )

    # 5. Power & Status Button (Home Assistant clean LED indicator)
    btn_cx, btn_cy = 1024 * scale, 680 * scale
    r_btn = 40 * scale
    draw.ellipse(
        [
            (btn_cx - r_btn, btn_cy - r_btn),
            (btn_cx + r_btn, btn_cy + r_btn),
        ],
        fill=c_accent,
        outline=c_accent_glow,
        width=int(8 * scale),
    )

    # Subtle corner sensor windows on front bumper
    for x_win in [400 * scale, 1648 * scale]:
        draw.ellipse(
            [(x_win - 20 * scale, 420 * scale), (x_win + 20 * scale, 460 * scale)],
            fill=c_detail,
        )

    return img


def generate_svg() -> str:
    """Generate clean MDI-style SVG artwork for documentation and README."""
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="100%" height="100%">
  <defs>
    <filter id="shadow" x="-10%" y="-10%" width="130%" height="130%">
      <feDropShadow dx="0" dy="12" stdDeviation="10" flood-color="#000000" flood-opacity="0.3"/>
    </filter>
    <linearGradient id="body" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#2d3748"/>
      <stop offset="100%" stop-color="#1a202c"/>
    </linearGradient>
    <linearGradient id="bumper" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#111827"/>
      <stop offset="100%" stop-color="#1f2937"/>
    </linearGradient>
    <linearGradient id="accent" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>

  <!-- Robot D-shape Body -->
  <g filter="url(#shadow)">
    <!-- Rear semicircle -->
    <path d="M 70 270 A 186 186 0 0 0 442 270 L 442 120 C 442 90 412 85 382 85 L 130 85 C 100 85 70 90 70 120 Z"
          fill="url(#body)" stroke="#4a5568" stroke-width="4"/>

    <!-- Front Bumper -->
    <path d="M 70 150 L 70 120 C 70 90 100 85 130 85 L 382 85 C 412 85 442 90 442 120 L 442 150 Z"
          fill="url(#bumper)" stroke="#4a5568" stroke-width="3"/>
    <line x1="70" y1="150" x2="442" y2="150" stroke="#374151" stroke-width="4"/>

    <!-- Dustbin outline -->
    <rect x="145" y="180" width="222" height="110" rx="15" fill="none" stroke="#4a5568" stroke-width="3"/>
    <rect x="221" y="185" width="70" height="12" rx="6" fill="#4a5568"/>

    <!-- Power / Status LED -->
    <circle cx="256" cy="168" r="10" fill="url(#accent)"/>

    <!-- LiDAR Turret -->
    <circle cx="256" cy="355" r="55" fill="#374151" stroke="#4a5568" stroke-width="3"/>
    <circle cx="256" cy="355" r="45" fill="#1f2937" stroke="#4a5568" stroke-width="2"/>
    <rect x="218" y="350" width="76" height="10" rx="5" fill="#111827"/>
    <circle cx="256" cy="355" r="11" fill="url(#accent)"/>
  </g>
</svg>"""


def generate_brands() -> None:
    """Generate all 8 Home Assistant brand PNG assets and docs SVG."""
    print("Generating MDI-style master artwork (2048x2048)...")
    light_master = draw_robot(2048, dark_theme=False)
    dark_master = draw_robot(2048, dark_theme=True)

    assets = [
        ("icon@2x.png", light_master.resize((512, 512), Image.Resampling.LANCZOS)),
        ("icon.png", light_master.resize((256, 256), Image.Resampling.LANCZOS)),
        ("logo@2x.png", light_master.resize((512, 512), Image.Resampling.LANCZOS)),
        ("logo.png", light_master.resize((512, 512), Image.Resampling.LANCZOS)),
        ("dark_icon@2x.png", dark_master.resize((512, 512), Image.Resampling.LANCZOS)),
        ("dark_icon.png", dark_master.resize((256, 256), Image.Resampling.LANCZOS)),
        ("dark_logo@2x.png", dark_master.resize((512, 512), Image.Resampling.LANCZOS)),
        ("dark_logo.png", dark_master.resize((512, 512), Image.Resampling.LANCZOS)),
    ]

    for target_dir in [COMPONENT_BRAND_DIR, ROOT_BRAND_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename, img in assets:
            dest = target_dir / filename
            img.save(dest, optimize=True)
            print(f"Saved {dest.relative_to(REPO_ROOT)} ({img.size[0]}x{img.size[1]})")

    # Also update docs/assets
    DOCS_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    svg_path = DOCS_ASSETS_DIR / "integration_logo.svg"
    svg_path.write_text(generate_svg(), encoding="utf-8")
    print(f"Saved {svg_path.relative_to(REPO_ROOT)}")

    # Remove old vacuula_logo.svg if present
    old_vacuula_svg = DOCS_ASSETS_DIR / "vacuula_logo.svg"
    if old_vacuula_svg.is_file():
        old_vacuula_svg.unlink()
        print(f"Removed deprecated upstream {old_vacuula_svg.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    generate_brands()
