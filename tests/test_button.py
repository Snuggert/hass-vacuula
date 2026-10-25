"""Unit tests for Vacuula button platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.button import (
    VacuulaCleanZoneButton,
    VacuulaDismissAlertButton,
    VacuulaExploreMapButton,
    VacuulaLocateButton,
    VacuulaRefreshMapsButton,
    async_setup_entry,
)
from custom_components.vacuula.const import DOMAIN, ROBOT_TYPE_GEN3, ROBOT_TYPE_GEN4
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
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


async def test_locate_button(hass: HomeAssistant) -> None:
    """Test VacuulaLocateButton press calling client.async_locate."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, client, _ = create_mock_coordinator(hass, robot)
    btn = VacuulaLocateButton(coordinator, "OPS123")

    assert btn.name == "Locate"
    assert btn.icon == "mdi:volume-high"

    await btn.async_press()
    client.async_locate.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)


async def test_dismiss_alert_button(hass: HomeAssistant) -> None:
    """Test VacuulaDismissAlertButton press."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, client, _ = create_mock_coordinator(hass, robot)
    client.async_dismiss_alert.return_value = {"result": "ok", "state": 1}
    coordinator.async_apply_command_response = AsyncMock()

    btn = VacuulaDismissAlertButton(coordinator, "OPS123")
    assert btn.name == "Dismiss alert"
    assert btn.icon == "mdi:bell-cancel-outline"

    await btn.async_press()
    client.async_dismiss_alert.assert_awaited_once_with("OPS123", ROBOT_TYPE_GEN3)
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"result": "ok", "state": 1}
    )


async def test_refresh_maps_button(hass: HomeAssistant) -> None:
    """Test VacuulaRefreshMapsButton availability and press."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    coordinator.async_refresh_maps_and_runs = AsyncMock()

    btn = VacuulaRefreshMapsButton(coordinator, "OPS123")
    assert btn.name == "Refresh maps"
    assert btn.icon == "mdi:map-search-outline"
    assert btn.available is True

    await btn.async_press()
    coordinator.async_refresh_maps_and_runs.assert_awaited_once_with("OPS123")

    # When robot data missing, should be unavailable
    coordinator.data = {}
    assert btn.available is False


async def test_explore_map_button(hass: HomeAssistant) -> None:
    """Test VacuulaExploreMapButton press for Gen4."""
    robot = VacuulaRobotData(
        serial="OPS456",
        name="Gen4Bot",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
    )
    coordinator, client, _ = create_mock_coordinator(hass, robot)
    client.async_start_map_exploration.return_value = {"result": "ok"}
    coordinator.async_apply_command_response = AsyncMock()

    btn = VacuulaExploreMapButton(coordinator, "OPS456")
    assert btn.name == "Explore new map"
    assert btn.icon == "mdi:compass-outline"

    await btn.async_press()
    client.async_start_map_exploration.assert_awaited_once_with(
        "OPS456", ROBOT_TYPE_GEN4
    )
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS456", {"result": "ok"}
    )


async def test_clean_zone_button(hass: HomeAssistant) -> None:
    """Test VacuulaCleanZoneButton attributes and zone clean execution."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        active_map_id="map-101",
        preferred_fan_speed="turbo",
        preferred_navigation_mode="normal",
    )
    coordinator, client, _ = create_mock_coordinator(hass, robot)
    client.async_start_zone_cleaning.return_value = {"result": "ok"}
    coordinator.async_apply_command_response = AsyncMock()

    btn = VacuulaCleanZoneButton(
        coordinator,
        serial="OPS123",
        zone_id="b-kitchen-uuid",
        zone_name="Kitchen",
    )
    assert btn.name == "Clean Kitchen"
    assert btn.icon == "mdi:broom"
    assert btn.extra_state_attributes == {
        "zone_id": "b-kitchen-uuid",
        "zone_name": "Kitchen",
        "map_id": "map-101",
    }

    await btn.async_press()
    client.async_start_zone_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        "map-101",
        ["b-kitchen-uuid"],
        fan_speed="turbo",
        navigation_mode="normal",
    )
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"result": "ok"}
    )

    # Test press when no active map
    robot.active_map_id = None
    client.async_start_zone_cleaning.reset_mock()
    await btn.async_press()
    client.async_start_zone_cleaning.assert_not_called()


async def test_button_setup_entry(hass: HomeAssistant) -> None:
    """Test async_setup_entry dynamically adding robot and zone buttons."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, _, entry = create_mock_coordinator(hass, robot)

    added_entities: list[Any] = []

    def mock_add_entities(entities: list[Any]) -> None:
        added_entities.extend(entities)

    await async_setup_entry(hass, entry, mock_add_entities)

    # register_new_robot_callback immediately fires with existing known serials
    assert len(added_entities) == 4
    entity_types = [type(e).__name__ for e in added_entities]
    assert "VacuulaLocateButton" in entity_types
    assert "VacuulaRefreshMapsButton" in entity_types
    assert "VacuulaExploreMapButton" in entity_types
    assert "VacuulaDismissAlertButton" in entity_types

    # Trigger zone callback
    coordinator._new_zones_callbacks[0]("OPS123", [{"id": "z1", "name": "Living Room"}])
    assert len(added_entities) == 5
    assert isinstance(added_entities[-1], VacuulaCleanZoneButton)
    assert added_entities[-1].name == "Clean Living Room"
