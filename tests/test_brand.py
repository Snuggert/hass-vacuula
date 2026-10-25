"""Tests for Vacuula brand assets and HACS / Home Assistant brand compliance."""

import json
import re
from pathlib import Path

from PIL import Image

BRAND_DIR = Path(__file__).parent.parent / "custom_components" / "vacuula" / "brand"
ROOT_BRAND_DIR = Path(__file__).parent.parent / "brand"
MANIFEST_PATH = (
    Path(__file__).parent.parent / "custom_components" / "vacuula" / "manifest.json"
)
HACS_JSON_PATH = Path(__file__).parent.parent / "hacs.json"
README_PATH = Path(__file__).parent.parent / "README.md"

EXPECTED_FILES = {
    "icon.png": (256, 256),
    "icon@2x.png": (512, 512),
    "dark_icon.png": (256, 256),
    "dark_icon@2x.png": (512, 512),
    "logo.png": (512, 512),
    "logo@2x.png": (512, 512),
    "dark_logo.png": (512, 512),
    "dark_logo@2x.png": (512, 512),
}


def test_brand_directory_exists() -> None:
    """Verify that the brand directory exists in the integration component."""
    assert BRAND_DIR.is_dir(), f"Brand directory does not exist at {BRAND_DIR}"


def test_all_expected_brand_files_exist() -> None:
    """Verify all 8 Home Assistant and HACS standard brand asset files exist."""
    missing = [name for name in EXPECTED_FILES if not (BRAND_DIR / name).is_file()]
    assert not missing, f"Missing brand assets in {BRAND_DIR}: {missing}"


def test_brand_image_dimensions_and_formats() -> None:
    """Verify each brand asset has correct dimensions and PNG RGBA formatting."""
    for filename, expected_size in EXPECTED_FILES.items():
        file_path = BRAND_DIR / filename
        assert file_path.is_file(), f"File {filename} does not exist"
        with Image.open(file_path) as img:
            assert img.format == "PNG", f"{filename} is not a PNG (found {img.format})"
            assert img.mode == "RGBA", f"{filename} is not RGBA (found {img.mode})"
            assert img.size == expected_size, (
                f"{filename} size is {img.size}, expected {expected_size}"
            )
            bbox = img.getbbox()
            assert bbox is not None, (
                f"{filename} appears to be completely empty/transparent"
            )


def test_brand_contrast_light_and_dark_modes() -> None:
    """Verify light assets have dark artwork and dark assets have bright artwork."""
    # Light mode icons/logos should be dark on white background
    for filename in ["icon.png", "icon@2x.png", "logo.png", "logo@2x.png"]:
        file_path = BRAND_DIR / filename
        if not file_path.is_file():
            continue
        with Image.open(file_path) as img:
            opaque_pixels = [p for p in img.getdata() if p[3] > 128]
            assert opaque_pixels, f"No opaque pixels in {filename}"
            avg_lum = sum(
                0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in opaque_pixels
            ) / len(opaque_pixels)
            assert avg_lum < 100, (
                f"{filename} should be optimized for light backgrounds (avg luminance < 100, got {avg_lum:.1f})"
            )

    # Dark mode icons/logos should be bright on dark background
    for filename in [
        "dark_icon.png",
        "dark_icon@2x.png",
        "dark_logo.png",
        "dark_logo@2x.png",
    ]:
        file_path = BRAND_DIR / filename
        assert file_path.is_file(), f"Dark asset {filename} missing"
        with Image.open(file_path) as img:
            opaque_pixels = [p for p in img.getdata() if p[3] > 128]
            assert opaque_pixels, f"No opaque pixels in {filename}"
            avg_lum = sum(
                0.299 * p[0] + 0.587 * p[1] + 0.114 * p[2] for p in opaque_pixels
            ) / len(opaque_pixels)
            assert avg_lum > 180, (
                f"{filename} should be optimized for dark backgrounds (avg luminance > 180, got {avg_lum:.1f})"
            )


def test_manifest_and_hacs_domain_alignment() -> None:
    """Verify manifest.json and hacs.json domain match brand path."""
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)
    assert manifest["domain"] == "vacuula"
    assert manifest["name"] == "Neato Botvac (Vacuula Client - Unofficial)"

    with open(HACS_JSON_PATH, encoding="utf-8") as f:
        hacs = json.load(f)
    assert hacs["name"] == "Neato Botvac (Vacuula Client - Unofficial)"


def test_root_brand_directory_mirrored() -> None:
    """Verify repository root brand directory exists and matches component brand directory."""
    assert ROOT_BRAND_DIR.is_dir(), f"Root brand directory missing at {ROOT_BRAND_DIR}"
    for filename in EXPECTED_FILES:
        component_file = BRAND_DIR / filename
        root_file = ROOT_BRAND_DIR / filename
        assert root_file.is_file(), f"Missing {filename} in root brand directory"
        assert root_file.read_bytes() == component_file.read_bytes(), (
            f"Content mismatch between component brand/{filename} and root brand/{filename}"
        )


def test_readme_hacs_compatibility() -> None:
    """Verify README.md images and links use absolute URLs for HACS in-app rendering."""
    assert README_PATH.is_file(), f"README missing at {README_PATH}"
    content = README_PATH.read_text(encoding="utf-8")

    # Check images (HTML <img src="..."> and markdown ![alt](...))
    html_imgs = re.findall(r'<img[^>]+src=[\'"]([^\'"]+)[\'"]', content)
    md_imgs = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", content)
    all_imgs = html_imgs + md_imgs

    relative_imgs = [img for img in all_imgs if not img.startswith("https://")]
    assert not relative_imgs, (
        f"README contains relative image URLs that break in HACS: {relative_imgs}. "
        "Use absolute raw URLs (https://raw.githubusercontent.com/Snuggert/hass-vacuula/main/...)."
    )

    # Check links (HTML <a href="..."> and markdown [text](...))
    html_links = re.findall(r'<a[^>]+href=[\'"]([^\'"]+)[\'"]', content)
    md_links = re.findall(r"\[[^\]]+\]\(([^)]+)\)", content)
    all_links = html_links + md_links

    relative_links = [
        link
        for link in all_links
        if not link.startswith("https://")
        and not link.startswith("#")
        and not link.startswith("mailto:")
    ]
    assert not relative_links, (
        f"README contains relative link URLs that break in HACS: {relative_links}. "
        "Use absolute GitHub URLs (https://github.com/Snuggert/hass-vacuula/...)."
    )
