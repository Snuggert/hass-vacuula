"""Unit tests for the bundled Vacuula Lovelace map card."""

from __future__ import annotations

import subprocess
from pathlib import Path

CARD_PATH = (
    Path(__file__).parent.parent
    / "custom_components"
    / "vacuula"
    / "frontend"
    / "vacuula-map-card.js"
)


def test_card_file_exists_and_syntax() -> None:
    """Verify that vacuula-map-card.js exists and is syntactically valid JavaScript."""
    assert CARD_PATH.is_file()
    result = subprocess.run(
        ["node", "--check", str(CARD_PATH)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"JS Syntax Error: {result.stderr}"


def test_card_responsive_media_queries() -> None:
    """Verify that vacuula-map-card.js contains responsive media queries for large screens."""
    content = CARD_PATH.read_text(encoding="utf-8")

    # Media queries for tablets/laptops and large desktop monitors
    assert "@media (min-width: 600px)" in content
    assert "@media (min-width: 1024px)" in content
    assert "@media (min-width: 1440px)" in content

    # CSS variables for customizable sizing
    assert "--vacuula-map-max-height" in content
    assert "--vacuula-map-min-height" in content

    # Lovelace Panel mode support
    assert ":host([panel])" in content or "panel-mode" in content


def test_card_grid_options() -> None:
    """Verify that the card implements getGridOptions for HA Sections dashboard."""
    content = CARD_PATH.read_text(encoding="utf-8")
    assert "getGridOptions" in content
    assert "min_columns" in content
    assert "min_rows" in content


def test_card_dustbin_and_alert_notifications() -> None:
    """Verify that the card implements alert and dustbin banner notification rendering."""
    content = CARD_PATH.read_text(encoding="utf-8")

    # Alert banner class and dismiss button
    assert "alert-banner" in content
    assert "btn-dismiss-alert" in content
    assert "dismiss_alert" in content

    # Dust bin alert and error strings
    assert "dustbin_full" in content
    assert "dustbin_missing" in content
    assert "Dust Bin Full" in content or "dust bin is full" in content.lower()

    # Telemetry dustbin badge
    assert "Bin Full" in content


def test_card_configurable_toggles() -> None:
    """Verify that the card supports granular boolean configuration toggles."""
    content = CARD_PATH.read_text(encoding="utf-8")

    required_toggles = [
        "show_alerts",
        "show_bin_alert",
        "show_header",
        "show_status_badge",
        "show_battery",
        "show_schedule",
        "show_toolbar",
        "show_zone_labels",
        "show_zone_chips",
        "show_controls",
        "show_modes",
        "expand_on_desktop",
        "map_height",
    ]
    for toggle in required_toggles:
        assert toggle in content, f"Missing config toggle '{toggle}' in card"


def test_card_editor_has_all_toggles() -> None:
    """Verify that VacuulaMapCardEditor includes controls for all new configuration options."""
    content = CARD_PATH.read_text(encoding="utf-8")

    editor_controls = [
        "id=\"map_height\"",
        "id=\"show_alerts\"",
        "id=\"show_bin_alert\"",
        "id=\"show_header\"",
        "id=\"show_status_badge\"",
        "id=\"show_battery\"",
        "id=\"show_schedule\"",
        "id=\"show_toolbar\"",
        "id=\"show_zone_chips\"",
        "id=\"show_modes\"",
        "id=\"expand_on_desktop\"",
    ]
    for ctrl in editor_controls:
        assert ctrl in content, f"Missing editor control {ctrl} in VacuulaMapCardEditor"
