"""Unit tests for Vacuula base entity."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
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
from custom_components.vacuula.entity import VacuulaEntity


def create_mock_coordinator(
    hass: HomeAssistant,
    robot: VacuulaRobotData | None = None,
) -> tuple[VacuulaCoordinator, MockConfigEntry]:
    """Create a mock coordinator with an optional robot."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
        state=ConfigEntryState.LOADED,
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)
    coordinator.data = {robot.serial: robot} if robot else {}
    entry.runtime_data = coordinator
    return coordinator, entry


async def test_base_entity_robot_accessors(hass: HomeAssistant) -> None:
    """Test robot property accessors and available property."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"meta": {"modelName": "Neato Botvac D7 Connected", "firmware": "4.5.3"}},
    )
    coordinator, _ = create_mock_coordinator(hass, robot)
    entity = VacuulaEntity(coordinator, "OPS123", "test_key")

    assert entity.unique_id == "OPS123_test_key"
    assert entity.robot == robot
    assert entity._robot == robot
    assert entity.available is True

    # Test when robot disconnected
    robot.connected = False
    assert entity.available is False

    # Test when robot not in coordinator data
    entity_missing = VacuulaEntity(coordinator, "NONEXISTENT", "test_key")
    assert entity_missing.robot is None
    assert entity_missing._robot is None
    assert entity_missing.available is False


async def test_base_entity_device_info(hass: HomeAssistant) -> None:
    """Test device_info with metadata, default models, and missing robot."""
    # 1. Gen3 with custom modelName and firmware
    robot_gen3 = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={"meta": {"modelName": "Neato Botvac D7 Connected", "firmware": "4.5.3"}},
    )
    coord_gen3, _ = create_mock_coordinator(hass, robot_gen3)
    entity_gen3 = VacuulaEntity(coord_gen3, "OPS123", "test")
    entity_gen3.hass = hass
    dev_reg = dr.async_get(hass)
    server_device = dev_reg.async_get_or_create(
        config_entry_id=coord_gen3.config_entry.entry_id,
        identifiers={(DOMAIN, f"server_{coord_gen3.config_entry.entry_id}")},
    )
    info_gen3 = entity_gen3.device_info
    assert info_gen3["identifiers"] == {(DOMAIN, "OPS123")}
    assert info_gen3["name"] == "Neato D7"
    assert info_gen3["manufacturer"] == "Neato Robotics"
    assert info_gen3["model"] == "Neato Botvac D7 Connected"
    assert info_gen3["sw_version"] == "4.5.3"
    assert info_gen3.get("via_device_id") == server_device.id
    # 2. Gen3 fallback default model
    robot_gen3_nometa = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        state={},
    )
    coord_gen3_nometa, _ = create_mock_coordinator(hass, robot_gen3_nometa)
    entity_gen3_nometa = VacuulaEntity(coord_gen3_nometa, "OPS123", "test")
    info_gen3_nometa = entity_gen3_nometa.device_info
    assert info_gen3_nometa["model"] == "Neato Botvac Connected (Gen3)"

    # 3. Gen4 fallback default model
    robot_gen4 = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={},
    )
    coord_gen4, _ = create_mock_coordinator(hass, robot_gen4)
    entity_gen4 = VacuulaEntity(coord_gen4, "G4-123", "test")
    info_gen4 = entity_gen4.device_info
    assert info_gen4["model"] == "Neato Botvac (Gen4)"

    # 4. When robot is None
    coord_empty, _ = create_mock_coordinator(hass, None)
    entity_empty = VacuulaEntity(coord_empty, "MISSING", "test")
    info_empty = entity_empty.device_info
    assert info_empty["name"] == "MISSING"
    assert info_empty["model"] == "Neato Botvac (Gen4)"


async def test_base_entity_gen4_body(hass: HomeAssistant) -> None:
    """Test _gen4_body extraction from state."""
    # Body nested in 'body'
    robot_nested = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={"body": {"state": "idle", "details": {"charge": 90}}},
    )
    coord_nested, _ = create_mock_coordinator(hass, robot_nested)
    entity_nested = VacuulaEntity(coord_nested, "G4-123", "test")
    assert entity_nested._gen4_body == {"state": "idle", "details": {"charge": 90}}

    # Flat state
    robot_flat = VacuulaRobotData(
        serial="G4-123",
        name="Neato D10",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={"state": "idle", "details": {"charge": 90}},
    )
    coord_flat, _ = create_mock_coordinator(hass, robot_flat)
    entity_flat = VacuulaEntity(coord_flat, "G4-123", "test")
    assert entity_flat._gen4_body == {"state": "idle", "details": {"charge": 90}}

    # State is None
    robot_flat.state = None
    assert entity_flat._gen4_body == {}

    # Robot is None
    coord_empty, _ = create_mock_coordinator(hass, None)
    entity_empty = VacuulaEntity(coord_empty, "NONE", "test")
    assert entity_empty._gen4_body == {}
