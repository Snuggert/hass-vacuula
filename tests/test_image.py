"""Unit tests for Vacuula image platform."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import DOMAIN, ROBOT_TYPE_GEN3
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)
from custom_components.vacuula.image import (
    VacuulaFloorMapImage,
    VacuulaLastRunMapImage,
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


async def test_floormap_image_entity(hass: HomeAssistant) -> None:
    """Test VacuulaFloorMapImage availability, attributes, rendering, and caching."""
    mock_floormap = {
        "width": 10,
        "height": 10,
        "pixelSize": 50,
        "mapData": [0] * 100,
    }
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        active_map_id="map-101",
        active_map_name="Ground Floor",
        floormap=mock_floormap,
        boundaries=[
            {
                "id": "b1",
                "name": "Kitchen",
                "vertices": [[0, 0], [5, 0], [5, 5], [0, 5]],
            }
        ],
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    img_entity = VacuulaFloorMapImage(coordinator, "OPS123")
    img_entity.entity_id = "image.mappa_floor_map"

    assert img_entity.name == "Floor map"
    assert img_entity.content_type == "image/png"
    assert img_entity.available is True

    attrs = img_entity.extra_state_attributes
    assert attrs["serial"] == "OPS123"
    assert attrs["map_id"] == "map-101"
    assert attrs["map_name"] == "Ground Floor"
    assert "zones" in attrs

    with patch(
        "custom_components.vacuula.image.render_map_png", return_value=b"fake-png-bytes"
    ) as mock_render:
        # First call renders and caches
        png1 = await img_entity.async_image()
        assert png1 == b"fake-png-bytes"
        assert mock_render.call_count == 1

        # Second call returns cached png without re-rendering
        png2 = await img_entity.async_image()
        assert png2 == b"fake-png-bytes"
        assert mock_render.call_count == 1

    # Coordinator update cache invalidation test
    old_updated = img_entity.image_last_updated
    robot.active_map_id = "map-102"
    img_entity._handle_coordinator_update()
    assert img_entity.image_last_updated != old_updated

    # When floormap missing
    robot.floormap = None
    assert img_entity.available is False
    assert await img_entity.async_image() is None

    # When robot missing
    coordinator.data = {}
    assert img_entity.extra_state_attributes == {}


async def test_last_run_map_image_entity(hass: HomeAssistant) -> None:
    """Test VacuulaLastRunMapImage availability, attributes, and rendering."""
    mock_floormap = {"width": 10, "height": 10, "pixelSize": 50, "mapData": [0] * 100}
    mock_runmap = {"width": 10, "height": 10, "pixelSize": 50, "mapData": [1] * 100}
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        active_map_id="map-101",
        last_run_id="run-999",
        floormap=mock_floormap,
        last_runmap=mock_runmap,
        last_run={
            "cleaned_area": 45.2,
            "start_at": "2026-10-25T10:00:00Z",
            "end_at": "2026-10-25T10:45:00Z",
            "status": "completed",
        },
    )
    coordinator, _, _ = create_mock_coordinator(hass, robot)
    img_entity = VacuulaLastRunMapImage(coordinator, "OPS123")
    img_entity.entity_id = "image.mappa_last_run_map"

    assert img_entity.name == "Last run map"
    assert img_entity.content_type == "image/png"
    assert img_entity.available is True

    attrs = img_entity.extra_state_attributes
    assert attrs["serial"] == "OPS123"
    assert attrs["run_id"] == "run-999"
    assert attrs["cleaned_area_m2"] == 45.2
    assert attrs["status"] == "completed"

    with patch(
        "custom_components.vacuula.image.render_map_png", return_value=b"run-png-bytes"
    ) as mock_render:
        png1 = await img_entity.async_image()
        assert png1 == b"run-png-bytes"
        assert mock_render.call_count == 1

        # Caching check
        png2 = await img_entity.async_image()
        assert png2 == b"run-png-bytes"
        assert mock_render.call_count == 1

    # Coordinator update invalidation
    old_updated = img_entity.image_last_updated
    robot.last_run_id = "run-1000"
    img_entity._handle_coordinator_update()
    assert img_entity.image_last_updated != old_updated

    # Empty run state
    robot.last_run = None
    assert img_entity.extra_state_attributes == {}

    # Empty maps
    robot.floormap = None
    robot.last_runmap = None
    assert img_entity.available is False
    assert await img_entity.async_image() is None


async def test_image_setup_entry(hass: HomeAssistant) -> None:
    """Test async_setup_entry creates floor map and last run map images."""
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
    assert len(added_entities) == 2
    types = [type(e).__name__ for e in added_entities]
    assert "VacuulaFloorMapImage" in types
    assert "VacuulaLastRunMapImage" in types
