"""Unit tests for Vacuula domain services."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula import _async_register_services
from custom_components.vacuula.const import (
    DOMAIN,
    ROBOT_TYPE_GEN3,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONES,
    SERVICE_REFRESH_MAPS,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)


@pytest.fixture
def mock_robot() -> VacuulaRobotData:
    """Return a mock robot with map and zones configured."""
    return VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        active_map_id="map-1",
        active_map_name="Ground Floor",
        zones=[
            {"id": "zone-kitchen", "name": "Kitchen", "type": "polygon"},
            {"id": "zone-living", "name": "Living Room", "type": "polygon"},
        ],
    )


async def setup_mock_environment(
    hass: HomeAssistant, robot: VacuulaRobotData
) -> tuple[MockConfigEntry, AsyncMock, VacuulaCoordinator]:
    """Helper to set up a mock coordinator, config entry, and register services."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.async_get_robot_state.return_value = {
        "state": 1,
        "details": {"isCharging": True, "charge": 80},
    }
    coordinator = VacuulaCoordinator(hass, entry, client)
    coordinator.data = {robot.serial: robot}

    entry.runtime_data = coordinator
    _async_register_services(hass)

    return entry, client, coordinator


async def test_service_clean_zones_by_name(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_zones translates zone names to IDs and calls client API."""
    _, client, _ = await setup_mock_environment(hass, mock_robot)
    client.async_start_zone_cleaning.return_value = {"status": "ok"}

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        {"serial": "OPS123", "zones": ["Kitchen"]},
        blocking=True,
    )

    client.async_start_zone_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        "map-1",
        ["zone-kitchen"],
        fan_speed="turbo",
        navigation_mode="normal",
    )


async def test_service_clean_zones_comma_string(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_zones handles comma-separated string input."""
    _, client, _ = await setup_mock_environment(hass, mock_robot)
    client.async_start_zone_cleaning.return_value = {"status": "ok"}

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        {"serial": "OPS123", "zones": "Kitchen, Living Room"},
        blocking=True,
    )

    client.async_start_zone_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        "map-1",
        ["zone-kitchen", "zone-living"],
        fan_speed="turbo",
        navigation_mode="normal",
    )


async def test_service_clean_zones_no_active_map(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_zones raises HomeAssistantError when no map is active."""
    mock_robot.active_map_id = None
    await setup_mock_environment(hass, mock_robot)

    with pytest.raises(HomeAssistantError, match="No active floor map available"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONES,
            {"serial": "OPS123", "zones": ["Kitchen"]},
            blocking=True,
        )


async def test_service_clean_zones_robot_not_found(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_zones raises HomeAssistantError when robot serial does not exist."""
    await setup_mock_environment(hass, mock_robot)

    with pytest.raises(HomeAssistantError, match="Robot 'UNKNOWN' not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONES,
            {"serial": "UNKNOWN", "zones": ["Kitchen"]},
            blocking=True,
        )


async def test_service_clean_spot_custom_params(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_spot with custom dimensions and parameters."""
    _, client, _ = await setup_mock_environment(hass, mock_robot)
    client.async_start_spot_cleaning.return_value = {"status": "ok"}

    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_SPOT,
        {
            "serial": "OPS123",
            "width": 300,
            "height": 400,
            "fan_speed": "eco",
            "navigation_mode": "extra_care",
        },
        blocking=True,
    )

    client.async_start_spot_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        width=300,
        height=400,
        fan_speed="eco",
        navigation_mode="extra_care",
    )


async def test_service_refresh_maps(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test refresh_maps triggers async_refresh_maps_and_runs on coordinator."""
    _, _, coordinator = await setup_mock_environment(hass, mock_robot)
    coordinator.async_refresh_maps_and_runs = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_REFRESH_MAPS,
        {"serial": "OPS123"},
        blocking=True,
    )

    coordinator.async_refresh_maps_and_runs.assert_awaited_once_with("OPS123")
