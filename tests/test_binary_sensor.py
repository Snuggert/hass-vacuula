"""Unit tests for Vacuula binary sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.binary_sensor import (
    VacuulaBinFullBinarySensor,
    async_setup_entry,
)
from custom_components.vacuula.const import (
    DOMAIN,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)


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
    coordinator._known_serials = {robot.serial}
    entry.runtime_data = coordinator
    return coordinator, client


async def test_gen3_bin_full_binary_sensor(hass: HomeAssistant) -> None:
    """Test Gen3 bin full binary sensor states and attributes."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"alert": "dustbin_full", "error": None, "details": {}},
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    sensor = VacuulaBinFullBinarySensor(coordinator, "OPS123")

    assert sensor.unique_id == "OPS123_bin_full"
    assert sensor.name == "Dust bin full"
    assert sensor.device_class == BinarySensorDeviceClass.PROBLEM
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.icon == "mdi:delete-empty"
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["alert"] == "dustbin_full"
    assert "Empty" in sensor.extra_state_attributes["description"]

    # When dust bin missing
    robot.state = {"alert": None, "error": "dustbin_missing", "details": {}}
    assert sensor.is_on is True

    # When alert is cleared (normal)
    robot.state = {"alert": None, "error": None, "details": {}}
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["description"] == "Normal"

    # When robot state is None
    robot.state = None
    assert sensor.is_on is None


async def test_gen4_bin_full_binary_sensor(hass: HomeAssistant) -> None:
    """Test Gen4 bin full binary sensor states."""
    robot = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={
            "body": {
                "errors": [{"code": "dustbin_full", "severity": "warning"}],
            }
        },
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    sensor = VacuulaBinFullBinarySensor(coordinator, "G4-123")

    assert sensor.is_on is True

    # Normal without errors
    robot.state = {"body": {"errors": []}}
    assert sensor.is_on is False


async def test_binary_sensor_setup_entry(hass: HomeAssistant) -> None:
    """Test that async_setup_entry creates all binary sensor entities including bin full."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"alert": None},
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entry = coordinator.config_entry

    entities_added: list[object] = []

    def mock_add_entities(entities: list[object]) -> None:
        entities_added.extend(entities)

    await async_setup_entry(hass, entry, mock_add_entities)

    keys = [e._attr_unique_id for e in entities_added]
    assert "OPS123_connected" in keys
    assert "OPS123_docked" in keys
    assert "OPS123_charging" in keys
    assert "OPS123_dock_seen" in keys
    assert "OPS123_bin_full" in keys
