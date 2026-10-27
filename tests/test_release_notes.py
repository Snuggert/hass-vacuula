"""Tests for devtools.release_notes."""

from __future__ import annotations

from pathlib import Path

from devtools.release_notes import (
    build_release_notes,
    extract_changelog_notes,
    extract_contributors_section,
)


def test_extract_changelog_notes() -> None:
    """Verify extracting curated release notes from CHANGELOG.md for a given tag."""
    root = Path(__file__).resolve().parent.parent
    notes_080 = extract_changelog_notes(root / "CHANGELOG.md", "v0.8.0")
    assert "@veronoicc" in notes_080
    assert "### Added" in notes_080
    assert "## [0.8.0]" not in notes_080

    notes_081 = extract_changelog_notes(root / "CHANGELOG.md", "v0.8.1")
    assert "Multi-Map Selection Entity" in notes_081
    assert "### Fixed" in notes_081
    assert "## [0.8.1]" not in notes_081


def test_extract_contributors_section_with_new_contributors() -> None:
    """Verify extracting New Contributors section from GitHub auto-notes."""
    auto = (
        "## What's Changed\n* foo by @bar in #1\n\n"
        "## New Contributors\n* @bar made their first contribution in #1\n\n"
        "**Full Changelog**: https://example.com"
    )
    result = extract_contributors_section(auto)
    assert "## New Contributors" in result
    assert "@bar" in result
    assert "## What's Changed" not in result


def test_extract_contributors_section_returning_contributors() -> None:
    """Verify extracting unique contributors when there are no new contributors."""
    auto = (
        "## What's Changed\n* foo by @alice in #1\n* bar by @bob in #2\n\n"
        "**Full Changelog**: https://example.com"
    )
    result = extract_contributors_section(auto)
    assert "## Contributors" in result
    assert "* @alice" in result
    assert "* @bob" in result
    assert "## What's Changed" not in result


def test_build_release_notes() -> None:
    """Verify full release notes generation combining curated notes and auto contributors."""
    root = Path(__file__).resolve().parent.parent
    auto = (
        "## What's Changed\n* feat by @veronoicc in #3\n\n"
        "## New Contributors\n* @veronoicc made their first contribution in #3\n\n"
        "**Full Changelog**: https://github.com/Snuggert/hass-vacuula/compare/v0.7.2...v0.8.0"
    )
    notes = build_release_notes("v0.8.0", auto_notes=auto, root=root)
    assert "@veronoicc" in notes
    assert "### Added" in notes
    assert "## New Contributors" in notes
    assert "## What's Changed" not in notes
