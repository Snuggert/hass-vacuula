"""Unit tests for Vacuula select platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import (
    ALL_ZONES_OPTION,
    CLEAN_CATEGORY_HOUSE,
    CLEAN_CATEGORY_MAP,
    DOMAIN,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_CATEGORY_HOUSE,
    GEN3_CATEGORY_MAP,
    GEN3_NAV_MODES,
    GEN4_NAV_MODES,
    NAV_MODE_DEEP,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)
from custom_components.vacuula.select import (
    VacuulaCleaningCategorySelect,
    VacuulaNavigationModeSelect,
    VacuulaTargetZoneSelect,
    async_setup_entry,
)


def create_mock_coordinator(
    hass: HomeAssistant, robot: VacuulaRobotData
) -> tuple[VacuulaCoordinator, AsyncMock, MockConfigEntry]:
    """Create a mock coordinator with a given robot."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)
    coordinator.data = {robot.serial: robot}
    coordinator._known_serials = {robot.serial}
    coordinator.last_update_success = True
    entry.runtime_data = coordinator
    return coordinator, client, entry


async def test_navigation_mode_select_gen3(hass: HomeAssistant) -> None:
    """Test VacuulaNavigationModeSelect for Gen3 robot."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        preferred_navigation_mode=NAV_MODE_NORMAL,
        preferred_fan_speed=FAN_SPEED_ECO,
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    sel = VacuulaNavigationModeSelect(coordinator, "OPS123")

    assert sel.name == "Navigation mode"
    assert sel.options == GEN3_NAV_MODES
    assert sel.current_option == NAV_MODE_NORMAL

    # Selecting Deep navigation mode should force Turbo fan speed on Gen3
    await sel.async_select_option(NAV_MODE_DEEP)
    assert robot.preferred_navigation_mode == NAV_MODE_DEEP
    assert robot.preferred_fan_speed == FAN_SPEED_TURBO

    # When robot missing
    coordinator.data = {}
    assert sel.current_option is None
    await sel.async_select_option(NAV_MODE_NORMAL)  # should not crash


async def test_navigation_mode_select_gen4(hass: HomeAssistant) -> None:
    """Test VacuulaNavigationModeSelect for Gen4 robot."""
    robot = VacuulaRobotData(
        serial="OPS456",
        name="Gen4Bot",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        preferred_navigation_mode="gentle",
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    sel = VacuulaNavigationModeSelect(coordinator, "OPS456")

    assert sel.options == GEN4_NAV_MODES
    assert sel.current_option == "gentle"

    await sel.async_select_option("deep")
    assert robot.preferred_navigation_mode == "deep"


async def test_cleaning_category_select(hass: HomeAssistant) -> None:
    """Test VacuulaCleaningCategorySelect for Gen3 robot."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        preferred_category=GEN3_CATEGORY_MAP,
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    sel = VacuulaCleaningCategorySelect(coordinator, "OPS123")

    assert sel.name == "Cleaning mode"
    assert sel.current_option == CLEAN_CATEGORY_MAP

    await sel.async_select_option(CLEAN_CATEGORY_HOUSE)
    assert robot.preferred_category == GEN3_CATEGORY_HOUSE
    assert sel.current_option == CLEAN_CATEGORY_HOUSE

    await sel.async_select_option(CLEAN_CATEGORY_MAP)
    assert robot.preferred_category == GEN3_CATEGORY_MAP
    assert sel.current_option == CLEAN_CATEGORY_MAP

    # Missing robot
    coordinator.data = {}
    assert sel.current_option is None
    await sel.async_select_option(CLEAN_CATEGORY_MAP)


async def test_target_zone_select(hass: HomeAssistant) -> None:
    """Test VacuulaTargetZoneSelect options, deduplication, and selection."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        zones=[
            {"id": "z1", "name": "Kitchen"},
            {"id": "z2", "name": "Living Room"},
            {"id": "z3", "name": "Kitchen"},  # Duplicate name
            {"id": "z4"},  # No name
        ],
        selected_zone="Kitchen",
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    sel = VacuulaTargetZoneSelect(coordinator, "OPS123")

    assert sel.name == "Target zone"
    assert sel.options == [ALL_ZONES_OPTION, "Kitchen", "Living Room"]
    assert sel.current_option == "Kitchen"

    await sel.async_select_option("Living Room")
    assert robot.selected_zone == "Living Room"
    assert sel.current_option == "Living Room"

    # Selecting invalid zone falls back to ALL_ZONES_OPTION
    robot.selected_zone = "Nonexistent"
    assert sel.current_option == ALL_ZONES_OPTION

    # Missing robot
    coordinator.data = {}
    assert sel.options == [ALL_ZONES_OPTION]
    assert sel.current_option == ALL_ZONES_OPTION
    await sel.async_select_option(ALL_ZONES_OPTION)


async def test_select_setup_entry(hass: HomeAssistant) -> None:
    """Test async_setup_entry creates proper entities for Gen3 and Gen4."""
    robot_gen3 = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, _, entry = create_mock_coordinator(hass, robot_gen3)

    added_entities: list[Any] = []

    def mock_add_entities(entities: list[Any]) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, entry, mock_add_entities)

    # Gen3 gets NavigationMode, TargetZone, and CleaningCategory
    assert len(added_entities) == 3
    types = [type(e).__name__ for e in added_entities]
    assert "VacuulaNavigationModeSelect" in types
    assert "VacuulaTargetZoneSelect" in types
    assert "VacuulaCleaningCategorySelect" in types
