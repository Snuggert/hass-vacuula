"""Unit tests for Vacuula sensor platform."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.components.sensor import SensorStateClass
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
    VacuulaConnectedRobotsSensor,
    VacuulaLastCleanAreaSensor,
    VacuulaLastCleanDurationSensor,
    VacuulaServerVersionSensor,
    VacuulaTotalCleansSensor,
    async_setup_entry,
)


def create_mock_coordinator(
    hass: HomeAssistant, robot: VacuulaRobotData | None = None
) -> tuple[VacuulaCoordinator, AsyncMock]:
    """Create a mock coordinator with an optional robot."""
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
    coordinator.data = {robot.serial: robot} if robot else {}
    coordinator._known_serials = {robot.serial} if robot else set()
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

    dur = next(
        e for e in entities_added if isinstance(e, VacuulaLastCleanDurationSensor)
    )
    assert dur.native_value == 30.0
    assert dur.native_unit_of_measurement == UnitOfTime.MINUTES

    total = next(e for e in entities_added if isinstance(e, VacuulaTotalCleansSensor))
    assert total.native_value == 1


async def test_sensors_gen4_and_edge_cases(hass: HomeAssistant) -> None:
    """Test Gen4 values and edge cases across all sensor entities."""
    robot_g4 = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={
            "body": {
                "action": "cleaning",
                "details": {"charge": 95},
                "errors": [],
            }
        },
        last_run=None,
        total_runs=0,
    )
    coordinator, _ = create_mock_coordinator(hass, robot_g4)

    # Battery
    battery = VacuulaBatterySensor(coordinator, "G4-123")
    assert battery.native_value == 95
    robot_g4.state = {"body": {"details": {}}}
    assert battery.native_value is None
    robot_g4.state = None
    assert battery.native_value is None

    # Action
    action = VacuulaActionSensor(coordinator, "G4-123")
    robot_g4.state = {"body": {"action": "docking"}}
    assert action.native_value == "docking"
    robot_g4.state = None
    assert action.native_value is None

    # Gen3 unknown action code
    robot_g3 = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"action": 999},
    )
    coord_g3, _ = create_mock_coordinator(hass, robot_g3)
    action_g3 = VacuulaActionSensor(coord_g3, "OPS123")
    assert action_g3.native_value == "unknown_999"

    # Alert sensor Gen4 edge cases
    alert_g4 = VacuulaAlertSensor(coordinator, "G4-123")
    robot_g4.state = {"body": {"errors": []}}
    assert alert_g4.native_value == "none"
    robot_g4.state = {"body": {"errors": [{"other_field": 123}]}}
    assert alert_g4.native_value == "none"
    robot_g4.state = None
    assert alert_g4.native_value == "none"

    # Last clean area sensor edge cases
    area_sensor = VacuulaLastCleanAreaSensor(coordinator, "G4-123")
    assert area_sensor.available is True
    assert area_sensor.native_value is None
    assert area_sensor.extra_state_attributes == {}

    robot_g4.last_run = {"cleaned_area": None, "status": "complete"}
    assert area_sensor.native_value is None
    assert area_sensor.extra_state_attributes["status"] == "complete"

    # Last clean duration sensor edge cases
    dur_sensor = VacuulaLastCleanDurationSensor(coordinator, "G4-123")
    assert dur_sensor.available is True
    robot_g4.last_run = None
    assert dur_sensor.native_value is None

    # Non-string dates
    robot_g4.last_run = {"start_at": 12345, "end_at": None}
    assert dur_sensor.native_value is None

    # Malformed ISO dates
    robot_g4.last_run = {"start_at": "invalid-date", "end_at": "invalid-date"}
    assert dur_sensor.native_value is None

    # Total cleans sensor edge cases
    total_sensor = VacuulaTotalCleansSensor(coordinator, "G4-123")
    assert total_sensor.available is True
    assert total_sensor.native_value == 0

    coord_empty, _ = create_mock_coordinator(hass, None)
    total_missing = VacuulaTotalCleansSensor(coord_empty, "NONE")
    assert total_missing.available is False
    assert total_missing.native_value == 0


async def test_server_sensors(hass: HomeAssistant) -> None:
    """Test VacuulaServerVersionSensor and VacuulaConnectedRobotsSensor."""
    robot1 = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    robot2 = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=False,
    )
    coordinator, _ = create_mock_coordinator(hass, robot1)
    coordinator.data[robot2.serial] = robot2
    coordinator._known_serials.add(robot2.serial)
    coordinator.server_info = {"version": "2.4.0"}
    entry = coordinator.config_entry

    # Test VacuulaServerVersionSensor
    ver_sensor = VacuulaServerVersionSensor(coordinator, entry)
    assert ver_sensor.unique_id == f"server_{entry.entry_id}_server_version"
    assert ver_sensor.entity_category == EntityCategory.DIAGNOSTIC
    assert ver_sensor.native_value == "2.4.0"
    assert ver_sensor.device_info["identifiers"] == {
        (DOMAIN, f"server_{entry.entry_id}")
    }
    assert ver_sensor.device_info["model"] == "Vacuula Server"
    assert ver_sensor.device_info["manufacturer"] == "Vacuula"
    assert ver_sensor.device_info["sw_version"] == "2.4.0"

    # Test VacuulaConnectedRobotsSensor
    conn_sensor = VacuulaConnectedRobotsSensor(coordinator, entry)
    assert conn_sensor.unique_id == f"server_{entry.entry_id}_connected_robots"
    assert conn_sensor.state_class == SensorStateClass.MEASUREMENT
    assert conn_sensor.native_value == 1
    assert conn_sensor.device_info["identifiers"] == {
        (DOMAIN, f"server_{entry.entry_id}")
    }

    # When robot2 connects
    robot2.connected = True
    assert conn_sensor.native_value == 2

    # When no data
    coordinator.data = {}
    assert conn_sensor.native_value == 0


async def test_sensor_setup_entry_includes_server_sensors(hass: HomeAssistant) -> None:
    """Test async_setup_entry registers VacuulaServerVersionSensor and VacuulaConnectedRobotsSensor."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entry = coordinator.config_entry

    entities_added = []
    await async_setup_entry(hass, entry, entities_added.extend)
    assert any(isinstance(e, VacuulaServerVersionSensor) for e in entities_added)
    assert any(isinstance(e, VacuulaConnectedRobotsSensor) for e in entities_added)
