"""Unit tests for VacuulaCoordinator and SSE event multiplexing."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.vacuula.api import VacuulaApiError
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
        options={"scan_interval": 45},
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
        try:
            while True:
                await asyncio.sleep(3600)
                yield {}
        except asyncio.CancelledError:
            return

    client.async_iter_robot_events = mock_iter_events
    client.async_get_maps.return_value = []
    client.async_get_runs.return_value = []

    coordinator = VacuulaCoordinator(hass, entry, client)
    assert coordinator.update_interval == timedelta(seconds=45)
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

    async def empty_events(_s: str):
        if False:
            yield {}

    client.async_iter_robot_events = empty_events
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


async def test_coordinator_event_dispatching(hass: HomeAssistant) -> None:
    """Test SSE event processing and state updates."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()

    async def empty_events(_s: str):
        if False:
            yield {}

    client.async_iter_robot_events = empty_events
    coordinator = VacuulaCoordinator(hass, entry, client)
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=False,
    )
    coordinator.data = {"OPS123": robot}

    # 1. Test Server Events loop handling "robots" payload
    async def fake_server_events():
        yield (
            "robots",
            {
                "OPS123": {
                    "name": "Mappa Renamed",
                    "connected": True,
                    "type": ROBOT_TYPE_GEN3,
                },
                "OPS456": {
                    "name": "NewBot",
                    "connected": True,
                    "type": ROBOT_TYPE_GEN4,
                },
            },
        )
        coordinator._stopping = True

    client.async_iter_server_events = fake_server_events
    coordinator._stopping = False
    with (
        patch.object(coordinator, "async_refresh_robot", AsyncMock()),
        patch.object(coordinator, "async_refresh_maps_and_runs", AsyncMock()),
    ):
        await coordinator._listen_server_events()

    assert robot.name == "Mappa Renamed"
    assert robot.connected is True
    assert "OPS456" in coordinator.data
    assert coordinator.data["OPS456"].name == "NewBot"

    # 2. Test Robot Events loop handling Gen3 state frame
    async def fake_robot_events_gen3(_serial: str):
        yield {"data": {"state": 1, "details": {"charge": 100}}}
        coordinator._stopping = True

    client.async_iter_robot_events = fake_robot_events_gen3
    coordinator._stopping = False
    with (
        patch.object(coordinator, "_did_finish_cleaning", return_value=True),
        patch.object(
            coordinator, "async_refresh_maps_and_runs", AsyncMock()
        ) as mock_refresh,
    ):
        await coordinator._listen_robot_events("OPS123")
        assert robot.state == {"state": 1, "details": {"charge": 100}}
        mock_refresh.assert_called_once()

    # 3. Test Robot Events loop handling Gen4 state frame
    robot_gen4 = coordinator.data["OPS456"]
    coordinator._stopping = False

    async def fake_robot_events_gen4(_serial: str):
        yield {"event": {"body": {"state": "idle", "battery": 90}}}
        coordinator._stopping = True

    client.async_iter_robot_events = fake_robot_events_gen4
    await coordinator._listen_robot_events("OPS456")
    assert robot_gen4.state == {"body": {"state": "idle", "battery": 90}}


async def test_coordinator_apply_command_and_refresh(hass: HomeAssistant) -> None:
    """Test async_apply_command_response and async_refresh_maps_and_runs."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()

    async def empty_events(_s: str):
        if False:
            yield {}

    client.async_iter_robot_events = empty_events
    coordinator = VacuulaCoordinator(hass, entry, client)
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Mappa",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        zones=[
            {"id": "b-kitchen", "name": "Kitchen"},
            {"id": "b-living", "name": "Living Room"},
        ],
    )
    coordinator.data = {"OPS123": robot}

    # Test resolve_zone_ids
    assert robot.resolve_zone_ids(["Kitchen", "b-living", "raw-id"]) == [
        "b-kitchen",
        "b-living",
        "raw-id",
    ]

    # Test apply command response with state dict
    await coordinator.async_apply_command_response(
        "OPS123", {"state": 2, "details": {"charge": 80}}
    )
    assert robot.state == {"state": 2, "details": {"charge": 80}}

    # Test apply command response with empty dict triggers async_refresh_robot
    with patch.object(coordinator, "async_refresh_robot", AsyncMock()) as mock_refresh:
        await coordinator.async_apply_command_response("OPS123", {})
        mock_refresh.assert_awaited_once_with("OPS123")

    # Test async_refresh_maps_and_runs
    client.async_get_maps.return_value = [
        {"id": "map-101", "name": "Main Floor", "active": True}
    ]
    client.async_get_map_detail.return_value = {"width": 10, "height": 10}
    client.async_get_map_boundaries.return_value = [
        {"id": "b-kitchen", "name": "Kitchen"}
    ]
    client.async_get_runs.return_value = [{"id": "run-1"}]
    client.async_get_run_detail.return_value = {"width": 10}

    zone_notifications: list[Any] = []
    coordinator.register_new_zones_callback(
        lambda s, z: zone_notifications.append((s, z))
    )

    await coordinator.async_refresh_maps_and_runs("OPS123")
    assert robot.active_map_id == "map-101"
    assert robot.active_map_name == "Main Floor"
    assert robot.last_run_id == "run-1"
    assert len(zone_notifications) == 1


async def test_coordinator_update_data_errors(hass: HomeAssistant) -> None:
    """Test _async_update_data error handling for robots list and robot state."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()

    async def empty_events(_s: str):
        if False:
            yield {}

    client.async_iter_robot_events = empty_events
    coordinator = VacuulaCoordinator(hass, entry, client)

    # 1. async_get_robots raises VacuulaApiError -> UpdateFailed
    client.async_get_robots.side_effect = VacuulaApiError("Server down")
    with pytest.raises(UpdateFailed, match="Failed to fetch robots"):
        await coordinator._async_update_data()

    # 2. Individual robot state query raises VacuulaApiError -> catches & continues
    client.async_get_robots.side_effect = None
    client.async_get_robots.return_value = {
        "OPS123": {"name": "Bot1", "type": ROBOT_TYPE_GEN3, "connected": True}
    }
    client.async_get_robot_state.side_effect = VacuulaApiError("Timeout reading state")
    data = await coordinator._async_update_data()
    assert "OPS123" in data
    assert data["OPS123"].state == {}
    await coordinator.async_stop_sse()


async def test_coordinator_refresh_robot_edge_cases(hass: HomeAssistant) -> None:
    """Test async_refresh_robot with missing robot, disconnected robot, or API error."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)
    coordinator.data = {
        "OPS123": VacuulaRobotData(
            serial="OPS123",
            name="Bot",
            robot_type=ROBOT_TYPE_GEN3,
            connected=False,
        )
    }

    # 1. Missing serial
    await coordinator.async_refresh_robot("UNKNOWN")
    client.async_get_robot_state.assert_not_called()

    # 2. Disconnected robot
    await coordinator.async_refresh_robot("OPS123")
    client.async_get_robot_state.assert_not_called()

    # 3. Connected robot but API error
    coordinator.data["OPS123"].connected = True
    client.async_get_robot_state.side_effect = VacuulaApiError("Command failed")
    await coordinator.async_refresh_robot("OPS123")
    client.async_get_robot_state.assert_awaited_once()


async def test_coordinator_refresh_maps_api_errors(hass: HomeAssistant) -> None:
    """Test async_refresh_maps_and_runs error handling when individual sub-requests fail."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Bot",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    coordinator.data = {"OPS123": robot}

    # 1. Missing serial early return
    await coordinator.async_refresh_maps_and_runs("UNKNOWN")
    client.async_get_maps.assert_not_called()

    # 2. Detail calls raise VacuulaApiError but execution completes gracefully
    client.async_get_maps.return_value = [
        {"id": "map-1", "name": "Map 1", "active": True}
    ]
    client.async_get_map_detail.side_effect = VacuulaApiError("Floormap missing")
    client.async_get_map_boundaries.side_effect = VacuulaApiError("Boundaries missing")
    client.async_get_runs.return_value = [{"id": "run-1"}]
    client.async_get_run_detail.side_effect = VacuulaApiError("Run detail missing")

    await coordinator.async_refresh_maps_and_runs("OPS123")
    assert robot.active_map_id == "map-1"
    assert robot.floormap is None
    assert robot.last_runmap is None
    assert robot.maps_loaded is True

    # 3. Duplicate notify new zones early return
    coordinator._known_zones["OPS123"] = {"z1"}
    coordinator._notify_new_zones("OPS123", [{"id": "z1", "name": "Kitchen"}])


def test_parse_installer_version_and_outdated_check() -> None:
    """Test installer version parsing and outdated logic matching Vacuula v1.1.0."""
    from custom_components.vacuula.coordinator import (
        is_installer_outdated,
        parse_installer_version,
    )

    # Valid versions
    assert parse_installer_version("1.0.0") == (1, 0, 0, float("inf"))
    assert parse_installer_version("1.1.0-b3") == (1, 1, 0, 3)
    assert parse_installer_version("1.1.0-b6") == (1, 1, 0, 6)
    assert parse_installer_version("1.1.0") == (1, 1, 0, float("inf"))

    # Invalid version string fallback
    assert parse_installer_version("invalid") == (-999, -999, -999, float("-inf"))

    # Outdated comparisons against min version 1.1.0-b3
    assert is_installer_outdated("1.0.0", "1.1.0-b3") is True
    assert is_installer_outdated("1.1.0-b1", "1.1.0-b3") is True
    assert is_installer_outdated("1.1.0-b2", "1.1.0-b3") is True
    assert is_installer_outdated("1.1.0-b3", "1.1.0-b3") is False
    assert is_installer_outdated("1.1.0-b6", "1.1.0-b3") is False
    assert is_installer_outdated("1.1.0", "1.1.0-b3") is False
    assert is_installer_outdated("1.2.0", "1.1.0-b3") is False

    # Dev and None versions are never considered outdated
    assert is_installer_outdated("1.1.0-dev", "1.1.0-b3") is False
    assert is_installer_outdated(None, "1.1.0-b3") is False
    assert is_installer_outdated("", "1.1.0-b3") is False


async def test_coordinator_handles_v110_server_info_and_installed_with(
    hass: HomeAssistant,
) -> None:
    """Test coordinator updates server_info and robot installed_with field."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    client.async_get_server_info.return_value = {
        "version": "1.1.0",
        "min_installer_version": "1.1.0-b3",
        "gen3_port": 335,
        "gen4_port": 3443,
        "ha_ingress": False,
        "timezone": "Europe/Oslo",
        "utc_offset_minutes": 60,
    }
    client.async_get_robots.return_value = {
        "OPS123": {
            "name": "Mappa",
            "type": ROBOT_TYPE_GEN3,
            "connected": True,
            "installed_with": "1.0.0",
        }
    }
    client.async_get_robot_state.return_value = {"state": 1}
    client.async_get_maps.return_value = []
    client.async_get_runs.return_value = []

    async def mock_iter_robot_events(_serial: str):
        if False:
            yield {}

    client.async_iter_robot_events = mock_iter_robot_events

    coordinator = VacuulaCoordinator(hass, entry, client)
    data = await coordinator._async_update_data()

    assert coordinator.server_info["version"] == "1.1.0"
    assert coordinator.server_info["min_installer_version"] == "1.1.0-b3"
    assert coordinator.server_info["gen3_port"] == 335
    assert data["OPS123"].installed_with == "1.0.0"


async def test_coordinator_did_finish_cleaning_all_edge_cases(
    hass: HomeAssistant,
) -> None:
    """Test edge cases for _did_finish_cleaning across Gen3 and Gen4."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)
    coordinator = VacuulaCoordinator(hass, entry, AsyncMock())

    # Empty or None states
    assert coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, {}, {}) is False
    assert (
        coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, None, {"state": 1})  # type: ignore[arg-type]
        is False
    )
    assert (
        coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, {"state": 2}, None)  # type: ignore[arg-type]
        is False
    )

    # Gen3 transitions
    assert (
        coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, {"state": 2}, {"state": 3})
        is False
    )
    assert (
        coordinator._did_finish_cleaning(ROBOT_TYPE_GEN3, {"state": 1}, {"state": 2})
        is False
    )

    # Gen4 transitions
    # Case insensitivity
    assert (
        coordinator._did_finish_cleaning(
            ROBOT_TYPE_GEN4,
            {"body": {"state": "BUSY"}},
            {"body": {"state": "IDLE"}},
        )
        is True
    )
    # Busy to Paused
    assert (
        coordinator._did_finish_cleaning(
            ROBOT_TYPE_GEN4,
            {"body": {"state": "busy"}},
            {"body": {"state": "paused"}},
        )
        is False
    )
    # Flat states without nested body
    assert (
        coordinator._did_finish_cleaning(
            ROBOT_TYPE_GEN4,
            {"state": "busy"},
            {"state": "idle"},
        )
        is True
    )
    # Non-dict bodies
    assert (
        coordinator._did_finish_cleaning(
            ROBOT_TYPE_GEN4,
            {"body": "not_a_dict"},
            {"body": {"state": "idle"}},
        )
        is False
    )
    assert (
        coordinator._did_finish_cleaning(
            ROBOT_TYPE_GEN4,
            {"body": None},
            {"body": {"state": "idle"}},
        )
        is False
    )


async def test_coordinator_resolve_zone_ids_edge_cases() -> None:
    """Test room zone resolution with empty tokens, case variations, unknown IDs, and malformed zones."""
    robot = VacuulaRobotData(
        serial="OPS123",
        name="Neato D7",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
        zones=[
            {"id": "zone-k", "name": "Kitchen"},
            {"id": "zone-lr", "name": "Living Room"},
            {"id": None, "name": "InvalidZone1"},
            {"id": "zone-no-name", "name": None},
            {},
        ],
    )

    # 1. Matching by case-insensitive name with whitespace
    assert robot.resolve_zone_ids(["  kItChEn  "]) == ["zone-k"]

    # 2. Matching directly by ID
    assert robot.resolve_zone_ids(["zone-lr"]) == ["zone-lr"]

    # 3. Empty strings and pure whitespace are skipped
    assert robot.resolve_zone_ids(["", "   ", "Kitchen"]) == ["zone-k"]

    # 4. Unknown tokens are preserved as fallback raw IDs
    assert robot.resolve_zone_ids(["Basement", "zone-k"]) == ["Basement", "zone-k"]


async def test_coordinator_notify_new_zones_and_callback_removal(
    hass: HomeAssistant,
) -> None:
    """Test deduplication of new zones and unregistering callbacks."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)
    coordinator = VacuulaCoordinator(hass, entry, AsyncMock())

    received_zones: list[list[dict[str, Any]]] = []

    def on_new_zones(serial: str, zones: list[dict[str, Any]]) -> None:
        received_zones.append(zones)

    remove_cb = coordinator.register_new_zones_callback(on_new_zones)

    # First notification: adds zone 1 & 2
    coordinator._notify_new_zones(
        "s1",
        [
            {"id": "z1", "name": "Room 1"},
            {"id": "z2", "name": "Room 2"},
            {"id": None, "name": "NoId"},
        ],
    )
    assert len(received_zones) == 1
    assert len(received_zones[0]) == 2

    # Second notification with duplicate zones: should not call callback
    coordinator._notify_new_zones(
        "s1",
        [{"id": "z1", "name": "Room 1"}, {"id": "z2", "name": "Room 2"}],
    )
    assert len(received_zones) == 1

    # Remove callback
    remove_cb()
    coordinator._notify_new_zones("s1", [{"id": "z3", "name": "Room 3"}])
    assert len(received_zones) == 1


async def test_coordinator_apply_command_response_edge_cases(
    hass: HomeAssistant,
) -> None:
    """Test apply_command_response with missing serial, missing details, and Gen4 responses."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)
    coordinator = VacuulaCoordinator(hass, entry, AsyncMock())
    robot_gen3 = VacuulaRobotData(
        serial="s1",
        name="Gen3 Bot",
        robot_type=ROBOT_TYPE_GEN3,
        connected=True,
    )
    robot_gen4 = VacuulaRobotData(
        serial="s2",
        name="Gen4 Bot",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
    )
    coordinator.data = {"s1": robot_gen3, "s2": robot_gen4}
    coordinator.async_refresh_robot = AsyncMock()

    # 1. Serial not in coordinator.data -> returns safely without doing anything
    await coordinator.async_apply_command_response("unknown_serial", {"state": 1})
    coordinator.async_refresh_robot.assert_not_called()

    # 2. Gen3 response without 'details' -> falls back to async_refresh_robot
    await coordinator.async_apply_command_response("s1", {"state": 1})
    coordinator.async_refresh_robot.assert_awaited_once_with("s1")
    coordinator.async_refresh_robot.reset_mock()

    # 3. Gen4 response -> falls back to async_refresh_robot
    await coordinator.async_apply_command_response("s2", {"ability": "state.show"})
    coordinator.async_refresh_robot.assert_awaited_once_with("s2")


async def test_coordinator_listen_robot_events_gen4_and_disconnect(
    hass: HomeAssistant,
) -> None:
    """Test Gen4 SSE event frame processing and disconnected robot loop exit."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="http://192.168.1.50:8085",
        data={"url": "http://192.168.1.50:8085"},
    )
    entry.add_to_hass(hass)

    client = AsyncMock()
    coordinator = VacuulaCoordinator(hass, entry, client)
    robot_gen4 = VacuulaRobotData(
        serial="g4",
        name="Gen4 Bot",
        robot_type=ROBOT_TYPE_GEN4,
        connected=True,
        state={"body": {"state": "idle"}},
    )
    coordinator.data = {"g4": robot_gen4}

    # Stream containing Gen4 body frame and an invalid body frame
    async def fake_g4_stream(_serial: str):
        yield {"event": {"body": {"state": "busy"}}}
        yield {"event": {"body": "invalid_string"}}
        yield {"event": None}
        coordinator._stopping = True

    client.async_iter_robot_events = fake_g4_stream

    await coordinator._listen_robot_events("g4")
    assert robot_gen4.state == {"body": {"state": "busy"}}

    # Disconnected robot terminates loop immediately
    robot_gen4.connected = False
    coordinator._stopping = False
    await coordinator._listen_robot_events("g4")
