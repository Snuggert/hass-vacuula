"""Unit tests for Vacuula domain services."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula import _async_register_services
from custom_components.vacuula.api import VacuulaApiError
from custom_components.vacuula.const import (
    DOMAIN,
    ROBOT_TYPE_GEN3,
    SERVICE_CLEAN_SPOT,
    SERVICE_CLEAN_ZONE,
    SERVICE_CLEAN_ZONES,
    SERVICE_DISMISS_ALERT,
    SERVICE_REFRESH_MAPS,
    SERVICE_SEND_RAW_COMMAND,
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


async def test_service_target_resolution_by_entity_id(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test target robot resolution via state attributes and entity registry."""
    _, client, _ = await setup_mock_environment(hass, mock_robot)
    client.async_start_zone_cleaning.return_value = {"status": "ok"}

    # 1. Resolve via state attributes
    hass.states.async_set(
        "vacuum.living_room_vacuum",
        "docked",
        {"serial": "OPS123"},
    )
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        {"entity_id": "vacuum.living_room_vacuum", "zones": ["Kitchen"]},
        blocking=True,
    )
    client.async_start_zone_cleaning.assert_awaited_once()
    client.async_start_zone_cleaning.reset_mock()

    # 2. Resolve via entity registry unique_id
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "vacuum",
        DOMAIN,
        "OPS123_vacuum",
        suggested_object_id="registered_vacuum",
    )
    # Clear state serial attribute to force registry fallback
    hass.states.async_set("vacuum.registered_vacuum", "docked")
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        {"entity_id": "vacuum.registered_vacuum", "zones": ["Kitchen"]},
        blocking=True,
    )
    client.async_start_zone_cleaning.assert_awaited_once()


async def test_service_single_robot_and_ambiguous_resolution(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test auto-resolution when 1 robot exists, and ambiguity error with multiple robots."""
    _, client, coordinator = await setup_mock_environment(hass, mock_robot)
    client.async_start_zone_cleaning.return_value = {"status": "ok"}

    # 1. Single robot automatically resolved without serial or entity_id
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        {"zones": ["Kitchen"]},
        blocking=True,
    )
    client.async_start_zone_cleaning.assert_awaited_once()
    client.async_start_zone_cleaning.reset_mock()

    # 2. Ambiguity error when multiple robots exist and no serial provided
    robot2 = VacuulaRobotData(
        serial="BOT2",
        name="Upstairs Bot",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator.data["BOT2"] = robot2

    with pytest.raises(HomeAssistantError, match="Multiple robots are configured"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONES,
            {"zones": ["Kitchen"]},
            blocking=True,
        )

    # 3. No robots found error
    coordinator.data.clear()
    with pytest.raises(HomeAssistantError, match="No robots found in Vacuula"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONES,
            {"zones": ["Kitchen"]},
            blocking=True,
        )


async def test_service_api_error_and_refresh_all(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test API error propagation and refreshing maps across all robots."""
    _, client, coordinator = await setup_mock_environment(hass, mock_robot)
    coordinator.async_refresh_maps_and_runs = AsyncMock()

    # 1. API error bubbling up as HomeAssistantError
    client.async_start_zone_cleaning.side_effect = VacuulaApiError(
        "Robot busy navigation failed"
    )
    with pytest.raises(HomeAssistantError, match="Robot busy navigation failed"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONES,
            {"serial": "OPS123", "zones": ["Kitchen"]},
            blocking=True,
        )

    # 2. Refresh maps without serial/entity_id refreshes all robots in all loaded entries
    await hass.services.async_call(
        DOMAIN,
        SERVICE_REFRESH_MAPS,
        {},
        blocking=True,
    )
    coordinator.async_refresh_maps_and_runs.assert_awaited_once_with("OPS123")

    # 3. Duplicate registration is idempotent
    _async_register_services(hass)


async def test_service_clean_zones_scalar_and_unmatched_registry(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_zones with a scalar non-string/non-list zone input and unmatched registry entity."""
    _, client, _ = await setup_mock_environment(hass, mock_robot)
    client.async_start_zone_cleaning.return_value = {"status": "ok"}

    # 1. Non-str, non-list scalar (e.g. integer zone token 123)
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONES,
        {"serial": "OPS123", "zones": 123},
        blocking=True,
    )
    client.async_start_zone_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        "map-1",
        ["123"],
        fan_speed="turbo",
        navigation_mode="normal",
    )

    # 2. Entity registry entry with unique_id that does NOT match any robot
    ent_reg = er.async_get(hass)
    ent_reg.async_get_or_create(
        "vacuum",
        DOMAIN,
        "UNMATCHED_ROBOT_VACUUM",
        suggested_object_id="orphan_vacuum",
    )
    hass.states.async_set("vacuum.orphan_vacuum", "docked")

    # When entity_id resolves to None serial, and multiple robots exist, error is raised
    robot2 = VacuulaRobotData(
        serial="OTHER_BOT",
        name="Other Bot",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    mock_robot_dict = {
        mock_robot.serial: mock_robot,
        robot2.serial: robot2,
    }
    with pytest.raises(HomeAssistantError, match="Multiple robots are configured"):
        _async_register_services(hass)
        from custom_components.vacuula import _resolve_target_robot

        # Set coordinator data to 2 robots
        entry = hass.config_entries.async_entries(DOMAIN)[0]
        entry.runtime_data.data = mock_robot_dict
        _resolve_target_robot(hass, entity_id="vacuum.orphan_vacuum")


async def test_service_clean_zone(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test clean_zone finds zone by name and triggers cleaning."""
    _, client, coordinator = await setup_mock_environment(hass, mock_robot)
    client.async_start_zone_cleaning.return_value = {"status": "ok"}
    coordinator.async_apply_command_response = AsyncMock()

    # Successful clean_zone with zone_name and optional mode
    await hass.services.async_call(
        DOMAIN,
        SERVICE_CLEAN_ZONE,
        {
            "serial": "OPS123",
            "zone_name": "Kitchen",
            "mode": "eco",
            "navigation_mode": "extra_care",
        },
        blocking=True,
    )
    client.async_start_zone_cleaning.assert_awaited_once_with(
        "OPS123",
        ROBOT_TYPE_GEN3,
        "map-1",
        ["zone-kitchen"],
        fan_speed="eco",
        navigation_mode="extra_care",
    )
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"status": "ok"}
    )

    # Zone not found error
    with pytest.raises(HomeAssistantError, match="Zone 'NonExistent' not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONE,
            {
                "serial": "OPS123",
                "zone_name": "NonExistent",
            },
            blocking=True,
        )

    # Map name filtering: mismatch raises error, match succeeds
    with pytest.raises(HomeAssistantError, match="Zone 'Kitchen' not found"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONE,
            {
                "serial": "OPS123",
                "zone_name": "Kitchen",
                "map_name": "Second Floor",
            },
            blocking=True,
        )

    # No active map error
    mock_robot.active_map_id = None
    with pytest.raises(HomeAssistantError, match="No active floor map available"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAN_ZONE,
            {
                "serial": "OPS123",
                "zone_name": "Kitchen",
            },
            blocking=True,
        )


async def test_service_dismiss_alert(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test dismiss_alert calls client.async_dismiss_alert."""
    _, client, coordinator = await setup_mock_environment(hass, mock_robot)
    client.async_dismiss_alert.return_value = {"status": "ok"}
    coordinator.async_apply_command_response = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DISMISS_ALERT,
        {"serial": "OPS123"},
        blocking=True,
    )
    client.async_dismiss_alert.assert_awaited_once_with("OPS123")
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"status": "ok"}
    )


async def test_service_send_raw_command(
    hass: HomeAssistant, mock_robot: VacuulaRobotData
) -> None:
    """Test send_raw_command calls client.async_send_raw_command."""
    _, client, coordinator = await setup_mock_environment(hass, mock_robot)
    client.async_send_raw_command.return_value = {"result": "success"}
    coordinator.async_apply_command_response = AsyncMock()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND_RAW_COMMAND,
        {
            "serial": "OPS123",
            "command": "getRobotState",
            "params": {"foo": "bar"},
        },
        blocking=True,
    )
    client.async_send_raw_command.assert_awaited_once_with(
        "OPS123", "getRobotState", {"foo": "bar"}
    )
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"result": "success"}
    )


@pytest.mark.asyncio
async def test_client_async_send_raw_command() -> None:
    """Test VacuulaApiClient.async_send_raw_command payload formatting."""
    from custom_components.vacuula.core.client import VacuulaApiClient

    client = VacuulaApiClient("http://test-server", AsyncMock())
    client.async_send_command = AsyncMock(return_value={"ok": True})

    # 1. With params
    await client.async_send_raw_command("SER123", "getRobotState", {"key": "val"})
    client.async_send_command.assert_awaited_with(
        "SER123", {"cmd": "getRobotState", "params": {"key": "val"}}
    )

    # 2. Ability with dot in command (without and with params)
    await client.async_send_raw_command("SER123", "cleaning.start")
    client.async_send_command.assert_awaited_with(
        "SER123", {"ability": "cleaning.start"}
    )
    await client.async_send_raw_command("SER123", "cleaning.start", {"mode": "turbo"})
    client.async_send_command.assert_awaited_with(
        "SER123", {"ability": "cleaning.start", "mode": "turbo"}
    )
    # 3. Simple cmd
    await client.async_send_raw_command("SER123", "pauseCleaning")
    client.async_send_command.assert_awaited_with("SER123", {"cmd": "pauseCleaning"})
