"""Unit tests verifying version consistency across project metadata."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parent.parent


def test_version_consistency() -> None:
    """Verify that version strings across manifest, __init__, and pyproject match."""
    manifest_path = ROOT / "custom_components" / "vacuula" / "manifest.json"
    init_path = ROOT / "custom_components" / "vacuula" / "__init__.py"
    pyproject_path = ROOT / "pyproject.toml"
    changelog_path = ROOT / "CHANGELOG.md"

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)
    version = manifest.get("version")
    assert version is not None

    init_content = init_path.read_text(encoding="utf-8")
    match_frontend = re.search(r'FRONTEND_VERSION\s*=\s*"([^"]+)"', init_content)
    assert match_frontend is not None
    assert match_frontend.group(1) == version

    pyproject_content = pyproject_path.read_text(encoding="utf-8")
    match_pyproject = re.search(r'version\s*=\s*"([^"]+)"', pyproject_content)
    assert match_pyproject is not None
    assert match_pyproject.group(1) == version

    changelog_content = changelog_path.read_text(encoding="utf-8")
    assert f"## [{version}]" in changelog_content
