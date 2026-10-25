"""Unit tests for Vacuula switch platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import DOMAIN, ROBOT_TYPE_GEN3, ROBOT_TYPE_GEN4
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)
from custom_components.vacuula.switch import (
    VacuulaScheduleSwitch,
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


async def test_schedule_switch(hass: HomeAssistant) -> None:
    """Test VacuulaScheduleSwitch state, turn on, and turn off."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"details": {"isScheduleEnabled": True}},
    )
    coordinator, client, _ = create_mock_coordinator(hass, robot)
    client.async_set_schedule_enabled.return_value = {"result": "ok"}
    coordinator.async_apply_command_response = AsyncMock()

    sw = VacuulaScheduleSwitch(coordinator, "OPS123")
    assert sw.name == "Schedule"
    assert sw.icon == "mdi:calendar-clock"
    assert sw.is_on is True

    # Turn off
    await sw.async_turn_off()
    client.async_set_schedule_enabled.assert_awaited_once_with("OPS123", False)
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"result": "ok"}
    )

    # Turn on
    client.async_set_schedule_enabled.reset_mock()
    coordinator.async_apply_command_response.reset_mock()
    await sw.async_turn_on()
    client.async_set_schedule_enabled.assert_awaited_once_with("OPS123", True)
    coordinator.async_apply_command_response.assert_awaited_once_with(
        "OPS123", {"result": "ok"}
    )

    # When robot or state missing
    coordinator.data = {}
    assert sw.is_on is None


async def test_switch_setup_entry(hass: HomeAssistant) -> None:
    """Test async_setup_entry creates switch for Gen3 and skips for Gen4."""
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
    assert len(added_entities) == 1
    assert isinstance(added_entities[0], VacuulaScheduleSwitch)

    # For Gen4 robot, switch should not be added
    robot_gen4 = VacuulaRobotData(
        serial="OPS456",
        name="Gen4Bot",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
    )
    coordinator.data = {"OPS456": robot_gen4}
    gen4_entities: list[Any] = []
    coordinator._new_robot_callbacks[0](["OPS456"])
    assert len(gen4_entities) == 0
