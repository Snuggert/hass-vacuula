"""Unit tests for VacuulaCoordinator and SSE event multiplexing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.const import (
    DOMAIN,
    FAN_SPEED_TURBO,
    GEN3_MODE_TURBO,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)
from custom_components.vacuula.coordinator import (
    VacuulaCoordinator,
    VacuulaRobotData,
)


async def test_coordinator_init_and_state(hass: HomeAssistant) -> None:
    """Test coordinator initialization and data model."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.async_get_robots.return_value = {
        "OPS123": {
            "name": "Mappa",
            "type": ROBOT_TYPE_GEN3,
            "connected": True,
        }
    }
    client.async_get_robot_state.return_value = {
        "state": 1,
        "details": {"isCharging": True, "charge": 80},
    }

    async def mock_iter_events(_serial: str):
        if False:
            yield {}

    client.async_iter_robot_events = mock_iter_events

    coordinator = VacuulaCoordinator(hass, entry, client)
    data = await coordinator._async_update_data()

    assert "OPS123" in data
    robot = data["OPS123"]
    assert robot.name == "Mappa"
    assert robot.connected is True
    assert robot.state == {"state": 1, "details": {"isCharging": True, "charge": 80}}

    await coordinator.async_stop_sse()


async def test_coordinator_robot_preferences_sync() -> None:
    """Test sync_preferences_from_state correctly extracts mode & navigation code."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Bot",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    # Gen3 cleaning state: mode 2 (Turbo), navigationMode 1 (Normal)
    robot.state = {
        "cleaning": {
            "mode": GEN3_MODE_TURBO,
            "navigationMode": 1,
            "category": 4,
        }
    }
    robot.sync_preferences_from_state()

    assert robot.preferred_fan_speed == FAN_SPEED_TURBO
    assert robot.preferred_navigation_mode == "normal"
    assert robot.preferred_category == 4


async def test_coordinator_did_finish_cleaning(hass: HomeAssistant) -> None:
    """Test completion detection from busy state to idle."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)
    coordinator = VacuulaCoordinator(hass, entry, AsyncMock())

    # Gen3: state 2 (busy) -> state 1 (idle) -> finished!
    assert (
        coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, {"state": 2}, {"state": 1})
        is True
    )

    # Gen3: state 1 (idle) -> state 1 (idle) -> False
    assert (
        coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, {"state": 1}, {"state": 1})
        is False
    )

    # Gen4: state "busy" -> state "idle" -> finished!
    old_gen4 = {"body": {"state": "busy"}}
    new_gen4 = {"body": {"state": "idle"}}
    assert coordinator._did_finish_cleaning(ROBOT_TYPE_GEN4, old_gen4, new_gen4) is True


async def test_coordinator_sse_lifecycle(hass: HomeAssistant) -> None:
    """Test starting and stopping SSE listeners cancels all tasks cleanly."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)

    # Start SSE
    with patch.object(coordinator, "_listen_server_events", AsyncMock()):
        await coordinator.async_start_sse()
        assert coordinator._server_sse_task is not None

    # Stop SSE
    await coordinator.async_stop_sse()
    assert coordinator._stopping is True
    await asyncio.sleep(0)
    assert (
        coordinator._server_sse_task.cancelled() or coordinator._server_sse_task.done()
    )
