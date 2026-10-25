#!/usr/bin/env python3
"""Generate all 8 standard Home Assistant and HACS brand assets from master artwork."""

from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPONENT_BRAND_DIR = REPO_ROOT / "custom_components" / "vacuula" / "brand"
ROOT_BRAND_DIR = REPO_ROOT / "brand"


def generate_brands() -> None:
    """Generate compliant brand images for light and dark themes."""
    source_path = COMPONENT_BRAND_DIR / "icon@2x.png"
    if not source_path.is_file():
        raise FileNotFoundError(f"Source master artwork not found at {source_path}")

    master = Image.open(source_path).convert("RGBA")

    # Generate dark-mode master artwork (bright artwork with vivid status accents)
    dark_master = Image.new("RGBA", master.size)
    dark_pixels = []
    for r, g, b, a in master.getdata():
        if a == 0:
            dark_pixels.append((0, 0, 0, 0))
        elif r > g + 20 and r > b + 20:
            dark_pixels.append((255, 75, 85, a))
        else:
            lum = (r + g + b) / 3.0
            new_lum = int(245 - (lum / 60.0) * 35)
            new_lum = max(195, min(255, new_lum))
            dark_pixels.append((new_lum, new_lum, new_lum, a))
    dark_master.putdata(dark_pixels)

    # Asset definitions: (filename, image, size)
    assets = [
        ("icon@2x.png", master, (512, 512)),
        ("icon.png", master.resize((256, 256), Image.Resampling.LANCZOS), (256, 256)),
        ("logo@2x.png", master, (512, 512)),
        ("logo.png", master, (512, 512)),
        ("dark_icon@2x.png", dark_master, (512, 512)),
        (
            "dark_icon.png",
            dark_master.resize((256, 256), Image.Resampling.LANCZOS),
            (256, 256),
        ),
        ("dark_logo@2x.png", dark_master, (512, 512)),
        ("dark_logo.png", dark_master, (512, 512)),
    ]

    for target_dir in [COMPONENT_BRAND_DIR, ROOT_BRAND_DIR]:
        target_dir.mkdir(parents=True, exist_ok=True)
        for filename, img, _size in assets:
            dest = target_dir / filename
            img.save(dest, optimize=True)
            print(f"Saved {dest.relative_to(REPO_ROOT)} ({img.size[0]}x{img.size[1]})")


if __name__ == "__main__":
    generate_brands()
