"""Unit tests for Vacuula sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfArea, UnitOfTime
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import (
    DOMAIN,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)
from custom_components.vacuula.sensor import (
    VacuulaActionSensor,
    VacuulaAlertSensor,
    VacuulaBatterySensor,
    VacuulaLastCleanAreaSensor,
    VacuulaLastCleanDurationSensor,
    VacuulaTotalCleansSensor,
    async_setup_entry,
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


async def test_alert_sensor_gen3_and_gen4(hass: HomeAssistant) -> None:
    """Test VacuulaAlertSensor for Gen3 and Gen4 robots."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"alert": "dustbin_full", "error": None},
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    sensor = VacuulaAlertSensor(coordinator, "OPS123")

    assert sensor.unique_id == "OPS123_alert"
    assert sensor.name == "Alert"
    assert sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert sensor.native_value == "dustbin_full"

    # When error takes precedence
    robot.state = {"alert": "dustbin_full", "error": "brush_stuck"}
    assert sensor.native_value == "brush_stuck"

    # When no alert or error
    robot.state = {"alert": None, "error": None}
    assert sensor.native_value == "none"

    # Gen4 test
    robot_gen4 = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={"body": {"errors": [{"code": "navigation_stuck"}]}},
    )
    coordinator_g4, _ = create_mock_coordinator(hass, robot_gen4)
    sensor_g4 = VacuulaAlertSensor(coordinator_g4, "G4-123")
    assert sensor_g4.native_value == "navigation_stuck"


async def test_all_sensors_setup_entry(hass: HomeAssistant) -> None:
    """Test that all sensors are registered on async_setup_entry."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={
            "action": 1,
            "alert": "dustbin_full",
            "details": {"charge": 88},
        },
        last_run={
            "cleaned_area": 42.5,
            "start_at": "2026-10-25T10:00:00Z",
            "end_at": "2026-10-25T10:30:00Z",
        },
        total_runs=1,
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entry = coordinator.config_entry

    entities_added: list[object] = []

    def mock_add_entities(entities: list[object]) -> None:
        entities_added.extend(entities)

    await async_setup_entry(hass, entry, mock_add_entities)

    keys = [e._attr_unique_id for e in entities_added]
    assert "OPS123_battery" in keys
    assert "OPS123_action" in keys
    assert "OPS123_alert" in keys
    assert "OPS123_last_clean_area" in keys
    assert "OPS123_last_clean_duration" in keys
    assert "OPS123_total_cleans" in keys

    # Verify battery sensor values
    battery = next(e for e in entities_added if isinstance(e, VacuulaBatterySensor))
    assert battery.native_value == 88
    assert battery.native_unit_of_measurement == PERCENTAGE

    # Verify action sensor
    action = next(e for e in entities_added if isinstance(e, VacuulaActionSensor))
    assert action.native_value == "house_cleaning"

    # Verify stats
    area = next(e for e in entities_added if isinstance(e, VacuulaLastCleanAreaSensor))
    assert area.native_value == 42.5
    assert area.native_unit_of_measurement == UnitOfArea.SQUARE_METERS

    dur = next(e for e in entities_added if isinstance(e, VacuulaLastCleanDurationSensor))
    assert dur.native_value == 30.0
    assert dur.native_unit_of_measurement == UnitOfTime.MINUTES

    total = next(e for e in entities_added if isinstance(e, VacuulaTotalCleansSensor))
    assert total.native_value == 1
