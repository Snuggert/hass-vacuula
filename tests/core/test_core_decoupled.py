"""Pure-Python SDK & Domain Core unit tests (Zero Home Assistant dependency)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import devtools.core as vacuula_core
from devtools.core import (
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_CATEGORY_HOUSE,
    GEN3_STATE_BUSY,
    GEN3_STATE_ERROR,
    GEN3_STATE_IDLE,
    GEN3_STATE_PAUSED,
    NAV_MODE_EXTRA_CARE,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
    VacuulaApiClient,
    VacuulaApiError,
    VacuulaController,
    VacuulaRobotData,
    compute_cropped_zones,
    did_finish_cleaning,
    is_installer_outdated,
    parse_installer_version,
    render_map_png,
)


def test_devtools_core_imports_without_homeassistant() -> None:
    """Verify devtools.core can be imported in a subprocess where homeassistant is blocked."""
    repo_root = Path(__file__).resolve().parents[2]
    code = (
        "import sys; "
        "sys.modules['homeassistant'] = None; "
        "sys.modules['homeassistant.exceptions'] = None; "
        "sys.modules['homeassistant.const'] = None; "
        f"sys.path.insert(0, {str(repo_root)!r}); "
        "import devtools.core as vacuula_core; "
        "assert hasattr(vacuula_core, 'VacuulaApiClient'); "
        "assert hasattr(vacuula_core, 'VacuulaController'); "
        "assert issubclass(vacuula_core.VacuulaApiError, Exception)"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=False,
    )
    assert res.returncode == 0, f"Subprocess failed: {res.stderr}"


def test_robot_data_normalization_and_snapshot() -> None:
    """Test Gen3 & Gen4 VacuulaRobotData state normalization and snapshot export."""
    robot = VacuulaRobotData(
        serial="OPS999-111",
        name="Test D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        installed_with="1.1.0-b2",
        state={
            "state": GEN3_STATE_IDLE,
            "action": 0,
            "cleaning": {
                "category": GEN3_CATEGORY_HOUSE,
                "mode": 1,
                "navigationMode": 2,
            },
            "details": {
                "isDocked": True,
                "isCharging": True,
                "isScheduleEnabled": True,
                "charge": 88,
            },
        },
    )
    robot.sync_preferences_from_state()
    assert robot.preferred_fan_speed == FAN_SPEED_ECO
    assert robot.preferred_navigation_mode == NAV_MODE_EXTRA_CARE
    assert robot.preferred_category == GEN3_CATEGORY_HOUSE
    assert robot.activity_state == "docked"
    assert robot.battery_level == 88
    assert robot.is_docked is True
    assert robot.is_charging is True

    snap = robot.to_snapshot(min_installer_version="1.1.0-b3")
    assert snap["activity"] == "docked"
    assert snap["clean_category"] == "house"
    assert snap["installer_outdated"] is True
    assert snap["schedule_enabled"] is True

    # Test BUSY -> PAUSED -> RETURNING -> ERROR states
    robot.state["state"] = GEN3_STATE_BUSY
    robot.state["action"] = 11
    robot.state["details"]["isDocked"] = False
    assert robot.activity_state == "cleaning"
    assert robot.current_action_name == "map_cleaning"

    robot.state["state"] = GEN3_STATE_PAUSED
    assert robot.activity_state == "paused"

    robot.state["state"] = GEN3_STATE_IDLE
    robot.state["action"] = 4
    assert robot.activity_state == "returning"

    robot.state["state"] = GEN3_STATE_ERROR
    robot.state["error"] = "ui_error_brush_stuck"
    assert robot.activity_state == "error"

    # Gen4 state normalization
    gen4 = VacuulaRobotData(
        serial="GEN4-001",
        name="Test D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={"body": {"state": "busy", "action": "cleaning", "battery_level": 74}},
    )
    assert gen4.activity_state == "cleaning"
    assert gen4.battery_level == 74
    gen4.state = {"body": {"state": "idle", "is_docked": True, "is_charging": True}}
    assert gen4.activity_state == "docked"
    assert gen4.is_docked is True
    assert gen4.is_charging is True


@pytest.mark.asyncio
async def test_vacuula_controller_lifecycle() -> None:
    """Test standalone VacuulaController polling, map loading, and command application."""
    mock_client = MagicMock(spec=VacuulaApiClient)
    mock_client.async_get_server_info = AsyncMock(
        return_value={"version": "1.1.0-b9", "min_installer_version": "1.1.0-b3"}
    )
    mock_client.async_get_robots = AsyncMock(
        return_value={
            "OPS111-222": {
                "name": "Downstairs D7",
                "type": ROBOT_TYPE_GEN3,
                "connected": True,
                "installed_with": "1.1.0-b3",
            }
        }
    )
    mock_client.async_get_robot_state = AsyncMock(
        return_value={
            "state": GEN3_STATE_IDLE,
            "action": 0,
            "details": {"isDocked": True, "isCharging": False, "charge": 99},
        }
    )
    mock_client.async_get_maps = AsyncMock(
        return_value=[{"id": "map-1", "name": "First Floor", "enabled": True}]
    )
    mock_client.async_get_map_detail = AsyncMock(
        return_value={"width": 16, "height": 16, "rle": [[1, 256]]}
    )
    mock_client.async_get_map_boundaries = AsyncMock(
        return_value=[
            {
                "id": "z-1",
                "name": "Office",
                "type": "polygon",
                "color": "#38bdf8",
                "vertices": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
            }
        ]
    )
    mock_client.async_get_runs = AsyncMock(
        return_value=[
            {
                "id": "run-1",
                "run": {"start_at": "2026-10-26T09:00:00Z", "cleaned_area": 24.0},
            }
        ]
    )
    mock_client.async_get_run_detail = AsyncMock(
        return_value={"width": 16, "height": 16, "rle": [[3, 256]]}
    )

    controller = VacuulaController(mock_client)
    updates: list[dict[str, VacuulaRobotData]] = []
    unsub = controller.add_listener(updates.append)

    robots = await controller.async_refresh_all()
    assert "OPS111-222" in robots
    bot = robots["OPS111-222"]
    assert bot.active_map_id == "map-1"
    assert bot.active_map_name == "First Floor"
    assert len(bot.zones) == 1
    assert bot.resolve_zone_ids(["office"]) == ["z-1"]
    assert bot.total_runs == 1
    assert len(updates) == 1

    # Apply direct Gen3 command response
    await controller.async_apply_command_response(
        "OPS111-222",
        {
            "state": GEN3_STATE_BUSY,
            "action": 1,
            "details": {"isDocked": False, "isCharging": False, "charge": 97},
        },
    )
    assert bot.activity_state == "cleaning"
    assert len(updates) == 2

    # Test explicit map selection
    bot.maps = [
        {"id": "map-1", "name": "First Floor"},
        {"id": "map-2", "name": "Second Floor"},
    ]
    mock_client.async_get_map_detail.return_value = {
        "width": 32,
        "height": 32,
        "rle": [[1, 1024]],
    }
    mock_client.async_get_map_boundaries.return_value = [
        {"id": "z-2", "name": "Bedroom", "type": "polygon"}
    ]
    assert await controller.async_set_active_map("OPS111-222", "map-2") is True
    assert bot.active_map_id == "map-2"
    assert bot.active_map_name == "Second Floor"
    assert bot.preferred_map_id == "map-2"
    assert len(bot.zones) == 1
    assert bot.zones[0]["name"] == "Bedroom"
    assert len(updates) == 3

    unsub()


def test_version_and_map_helpers() -> None:
    """Verify version comparison and map rendering helpers via devtools.core."""
    assert parse_installer_version("1.1.0") > parse_installer_version("1.1.0-b9")
    assert is_installer_outdated("1.1.0-b2", "1.1.0-b3") is True
    assert is_installer_outdated("1.1.0-b3", "1.1.0-b3") is False
    assert did_finish_cleaning(
        ROBOT_TYPE_GEN3, {"state": GEN3_STATE_BUSY}, {"state": GEN3_STATE_IDLE}
    )

    floormap = {"width": 20, "height": 20, "rle": [[1, 400]]}
    boundaries = [
        {
            "id": "b1",
            "name": "Hallway",
            "type": "polygon",
            "color": "#4ade80",
            "vertices": [[0.2, 0.2], [0.8, 0.2], [0.8, 0.8], [0.2, 0.8]],
        }
    ]
    zones = compute_cropped_zones(floormap, boundaries)
    assert len(zones) == 1
    assert zones[0]["name"] == "Hallway"
    png = render_map_png(floormap, boundaries)
    assert png is not None
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert vacuula_core.FAN_SPEED_TURBO == FAN_SPEED_TURBO
    assert issubclass(VacuulaApiError, Exception)
