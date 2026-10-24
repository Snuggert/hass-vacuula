"""Unit tests for Vacuula vacuum platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

try:
    from homeassistant.components.vacuum import VacuumActivity
except ImportError:
    from custom_components.vacuula.vacuum import VacuumActivity  # type: ignore[assignment]
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import (
    ALL_ZONES_OPTION,
    DOMAIN,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_ACTION_DOCKING,
    GEN3_ACTION_HOUSE_CLEANING,
    GEN3_STATE_BUSY,
    GEN3_STATE_ERROR,
    GEN3_STATE_IDLE,
    GEN3_STATE_PAUSED,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)
from custom_components.vacuula.vacuum import VacuulaVacuumEntity


def create_mock_coordinator(
    hass: HomeAssistant, robot: VacuulaRobotData
) -> tuple[VacuulaCoordinator, AsyncMock]:
    """Create a mock coordinator with a given robot."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.async_get_robot_state.return_value = {"state": 1}
    coordinator = VacuulaCoordinator(hass, entry, client)
    coordinator.data = {robot.serial: robot}
    entry.runtime_data = coordinator
    return coordinator, client


async def test_gen3_vacuum_activity_states(hass: HomeAssistant) -> None:
    """Test Gen3 state mapping to Home Assistant VacuumActivity."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entity = VacuulaVacuumEntity(coordinator, "OPS123")

    # Docked
    robot.state = {"state": GEN3_STATE_IDLE, "details": {"isDocked": True}}
    assert entity.activity == VacuumActivity.DOCKED

    # Idle (undocked)
    robot.state = {"state": GEN3_STATE_IDLE, "details": {"isDocked": False}}
    assert entity.activity == VacuumActivity.IDLE

    # Cleaning
    robot.state = {
        "state": GEN3_STATE_BUSY,
        "action": GEN3_ACTION_HOUSE_CLEANING,
        "details": {"isDocked": False},
    }
    assert entity.activity == VacuumActivity.CLEANING

    # Returning to dock
    robot.state = {
        "state": GEN3_STATE_BUSY,
        "action": GEN3_ACTION_DOCKING,
        "details": {"isDocked": False},
    }
    assert entity.activity == VacuumActivity.RETURNING

    # Paused
    robot.state = {"state": GEN3_STATE_PAUSED, "details": {}}
    assert entity.activity == VacuumActivity.PAUSED

    # Error
    robot.state = {"state": GEN3_STATE_ERROR, "details": {}}
    assert entity.activity == VacuumActivity.ERROR


async def test_gen4_vacuum_activity_states(hass: HomeAssistant) -> None:
    """Test Gen4 state mapping to Home Assistant VacuumActivity."""
    robot = VacuulaRobotData(
        serial="OPS456",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entity = VacuulaVacuumEntity(coordinator, "OPS456")

    # Cleaning
    robot.state = {"body": {"state": "busy", "action": "cleaning"}}
    assert entity.activity == VacuumActivity.CLEANING

    # Returning
    robot.state = {"body": {"state": "busy", "action": "docking"}}
    assert entity.activity == VacuumActivity.RETURNING

    # Paused
    robot.state = {"body": {"state": "paused"}}
    assert entity.activity == VacuumActivity.PAUSED

    # Error
    robot.state = {"body": {"state": "error"}}
    assert entity.activity == VacuumActivity.ERROR

    # Docked
    robot.state = {"body": {"state": "idle", "details": {"is_docked": True}}}
    assert entity.activity == VacuumActivity.DOCKED


async def test_vacuum_start_commands(hass: HomeAssistant) -> None:
    """Test async_start commands for full clean, resume, and zone clean."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        active_map_id="map-1",
        selected_zone=ALL_ZONES_OPTION,
        preferred_fan_speed=FAN_SPEED_TURBO,
        preferred_navigation_mode="normal",
        preferred_category=4,
        state={"state": GEN3_STATE_IDLE, "details": {"isDocked": True}},
        zones=[{"id": "zone-k", "name": "Kitchen", "type": "polygon"}],
    )
    coordinator, client = create_mock_coordinator(hass, robot)
    client.async_start_cleaning.return_value = {"state": GEN3_STATE_BUSY}
    client.async_resume_cleaning.return_value = {"state": GEN3_STATE_BUSY}
    client.async_start_zone_cleaning.return_value = {"state": GEN3_STATE_BUSY}

    entity = VacuulaVacuumEntity(coordinator, "OPS123")

    # Full clean when idle
    await entity.async_start()
    client.async_start_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        fan_speed=FAN_SPEED_TURBO,
        navigation_mode="normal",
        category=4,
        map_id="map-1",
    )

    # Resume when paused
    robot.state = {"state": GEN3_STATE_PAUSED}
    await entity.async_start()
    client.async_resume_cleaning.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)

    # Zone clean when a specific zone is selected
    robot.state = {"state": GEN3_STATE_IDLE, "details": {"isDocked": True}}
    robot.selected_zone = "Kitchen"
    await entity.async_start()
    client.async_start_zone_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        "map-1",
        ["zone-k"],
        fan_speed=FAN_SPEED_TURBO,
        navigation_mode="normal",
    )


async def test_vacuum_control_commands(hass: HomeAssistant) -> None:
    """Test pause, stop, return to base, and locate commands."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"state": GEN3_STATE_BUSY},
    )
    coordinator, client = create_mock_coordinator(hass, robot)
    entity = VacuulaVacuumEntity(coordinator, "OPS123")

    await entity.async_pause()
    client.async_pause_cleaning.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)

    await entity.async_stop()
    client.async_stop_cleaning.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)

    await entity.async_return_to_base()
    client.async_return_to_base.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)

    await entity.async_locate()
    client.async_locate.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)


async def test_vacuum_fan_speed_and_attributes(hass: HomeAssistant) -> None:
    """Test setting fan speed and reading extra state attributes."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        preferred_fan_speed=FAN_SPEED_TURBO,
        preferred_navigation_mode="normal",
        active_map_id="map-abc",
        active_map_name="Main Floor",
        selected_zone=ALL_ZONES_OPTION,
        zones=[{"id": "zone-1", "name": "Hallway", "type": "polygon"}],
        state={"state": GEN3_STATE_IDLE, "action": 0},
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entity = VacuulaVacuumEntity(coordinator, "OPS123")

    assert entity.fan_speed == FAN_SPEED_TURBO
    await entity.async_set_fan_speed(FAN_SPEED_ECO)
    assert robot.preferred_fan_speed == FAN_SPEED_ECO

    attrs = entity.extra_state_attributes
    assert attrs["navigation_mode"] == "normal"
    assert attrs["active_map_id"] == "map-abc"
    assert attrs["active_map_name"] == "Main Floor"
    assert attrs["available_zones"] == ["Hallway"]
    assert attrs["selected_zone"] == ALL_ZONES_OPTION
