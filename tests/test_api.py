"""Unit tests for the VacuulaApiClient and error handling."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.vacuula.api import (
    VacuulaApiClient,
    VacuulaApiError,
    _seg,
)
from custom_components.vacuula.const import (
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_MODE_ECO,
    GEN3_MODE_TURBO,
    NAV_MODE_DEEP,
    NAV_MODE_EXTRA_CARE,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)


def test_vacuula_api_error_hierarchy() -> None:
    """Ensure VacuulaApiError inherits from HomeAssistantError for clean UI error handling."""
    assert issubclass(VacuulaApiError, HomeAssistantError)
    err = VacuulaApiError("Robot is currently unreachable")
    assert isinstance(err, HomeAssistantError)
    assert str(err) == "Robot is currently unreachable"


def test_seg_encoding_and_traversal_rejection() -> None:
    """Test URL path segment encoding and directory traversal rejection."""
    assert _seg("OPS123-456") == "OPS123-456"
    assert _seg("my room/zone") == "my%20room%2Fzone"
    assert _seg("map#1?query=yes") == "map%231%3Fquery%3Dyes"

    with pytest.raises(VacuulaApiError, match="Invalid identifier in request path"):
        _seg("")

    with pytest.raises(VacuulaApiError, match="Invalid identifier in request path"):
        _seg(".")

    with pytest.raises(VacuulaApiError, match="Invalid identifier in request path"):
        _seg("..")


def test_resolve_gen3_modes() -> None:
    """Test mode resolution for Gen3 robots, verifying Deep mode enforces Turbo."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())

    # Eco + Normal -> Mode 1, Nav 1
    assert client._resolve_gen3_modes(FAN_SPEED_ECO, NAV_MODE_NORMAL) == (
        GEN3_MODE_ECO,
        1,
    )

    # Turbo + Normal -> Mode 2, Nav 1
    assert client._resolve_gen3_modes(FAN_SPEED_TURBO, NAV_MODE_NORMAL) == (
        GEN3_MODE_TURBO,
        1,
    )

    # Turbo + Extra Care -> Mode 2, Nav 2
    assert client._resolve_gen3_modes(FAN_SPEED_TURBO, NAV_MODE_EXTRA_CARE) == (
        GEN3_MODE_TURBO,
        2,
    )

    # Eco + Deep -> Mode 2 (enforced Turbo!), Nav 3
    assert client._resolve_gen3_modes(FAN_SPEED_ECO, NAV_MODE_DEEP) == (
        GEN3_MODE_TURBO,
        3,
    )


def test_per_robot_locks() -> None:
    """Test that command locks are shared per serial and isolated across serials."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())
    lock_a1 = client._get_lock("serial-A")
    lock_a2 = client._get_lock("serial-A")
    lock_b = client._get_lock("serial-B")

    assert lock_a1 is lock_a2
    assert lock_a1 is not lock_b


async def test_api_client_requests_url_encoding() -> None:
    """Test that API client methods encode path parameters properly."""
    client = VacuulaApiClient("http://vacuula.local:8085", AsyncMock())
    client._request = AsyncMock(return_value={"status": "ok"})  # type: ignore[method-assign]

    await client.async_get_server_info()
    client._request.assert_awaited_with("GET", "/api/server")

    await client.async_get_robots()
    client._request.assert_awaited_with("GET", "/api/robots")

    await client.async_get_maps("serial/1")
    client._request.assert_awaited_with("GET", "/api/robot/serial%2F1/maps")

    await client.async_get_map_detail("serial/1", "map/2")
    client._request.assert_awaited_with("GET", "/api/robot/serial%2F1/maps/map%2F2")

    await client.async_get_run_detail("serial/1", "run/9")
    client._request.assert_awaited_with("GET", "/api/robot/serial%2F1/run/run%2F9")

    # Map exploration
    client.async_send_command = AsyncMock(return_value={"status": "ok"})  # type: ignore[method-assign]
    await client.async_start_map_exploration("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with(
        "s1", {"cmd": "startPersistentMapExploration"}
    )

    await client.async_start_map_exploration("s1", ROBOT_TYPE_GEN4)
    assert client.async_send_command.call_count == 2


async def test_get_robot_state_gen3_vs_gen4() -> None:
    """Test state polling commands for Gen3 and Gen4 robots."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())
    client.async_send_command = AsyncMock(return_value={"state": 1})  # type: ignore[method-assign]

    # Gen3 -> getRobotState
    await client.async_get_robot_state("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "getRobotState"})

    # Gen4 -> state.show
    await client.async_get_robot_state("s1", ROBOT_TYPE_GEN4)
    client.async_send_command.assert_awaited_with("s1", {"ability": "state.show"})

    # Unsupported -> raises VacuulaApiError
    with pytest.raises(VacuulaApiError, match="Unsupported robot type"):
        await client.async_get_robot_state("s1", "unknown.gen")


async def test_start_zone_cleaning_payloads() -> None:
    """Test start_zone_cleaning for single and multi-zone requests."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())
    client.async_send_command = AsyncMock(return_value={"status": "ok"})  # type: ignore[method-assign]

    # Empty zones list raises error
    with pytest.raises(VacuulaApiError, match="At least one zone ID"):
        await client.async_start_zone_cleaning("s1", ROBOT_TYPE_GEN3, "m1", [])

    # Gen3 Single Zone
    await client.async_start_zone_cleaning(
        "s1", ROBOT_TYPE_GEN3, "m1", ["zone-kitchen"], FAN_SPEED_TURBO, NAV_MODE_NORMAL
    )
    client.async_send_command.assert_awaited_with(
        "s1",
        {
            "cmd": "startCleaning",
            "params": {
                "category": 4,
                "mode": 2,
                "navigationMode": 1,
                "mapId": "m1",
                "boundaryId": "zone-kitchen",
            },
        },
    )

    # Gen3 Multi Zone
    await client.async_start_zone_cleaning(
        "s1", ROBOT_TYPE_GEN3, "m1", ["z1", "z2"], FAN_SPEED_ECO, NAV_MODE_NORMAL
    )
    client.async_send_command.assert_awaited_with(
        "s1",
        {
            "cmd": "startCleaning",
            "params": {
                "category": 4,
                "mode": 1,
                "navigationMode": 1,
                "boundaryIds": ["z1", "z2"],
            },
        },
    )

    # Gen4 Zone Clean
    await client.async_start_zone_cleaning(
        "s1", ROBOT_TYPE_GEN4, "m1", ["z1"], FAN_SPEED_TURBO, NAV_MODE_NORMAL
    )
    client.async_send_command.assert_awaited_with(
        "s1",
        {
            "ability": "cleaning.start",
            "runs": [
                {
                    "map": {"rank_id": "m1", "track_id": "z1", "nogo_enabled": True},
                    "settings": {"mode": "turbo", "navigation_mode": "normal"},
                }
            ],
        },
    )


async def test_gen3_exclusive_actions_on_gen4() -> None:
    """Test that Gen3-only actions raise VacuulaApiError when invoked on Gen4 robots."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())

    with pytest.raises(VacuulaApiError, match="Spot cleaning is only supported"):
        await client.async_start_spot_cleaning("s1", ROBOT_TYPE_GEN4)

    with pytest.raises(
        VacuulaApiError, match="Schedule toggle switch is only supported"
    ):
        await client.async_set_schedule_enabled("s1", True, ROBOT_TYPE_GEN4)


async def test_control_commands_gen3_and_gen4() -> None:
    """Test standard pause, resume, stop, return to base, and locate commands."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())
    client.async_send_command = AsyncMock(return_value={"status": "ok"})  # type: ignore[method-assign]

    # Gen3 commands
    await client.async_pause_cleaning("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "pauseCleaning"})

    await client.async_resume_cleaning("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "resumeCleaning"})

    await client.async_stop_cleaning("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "stopCleaning"})

    await client.async_return_to_base("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "sendToBase"})

    await client.async_locate("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "findMe"})

    await client.async_dismiss_alert("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "dismissCurrentAlert"})

    # Gen4 dismissal is no-op
    assert await client.async_dismiss_alert("s1", ROBOT_TYPE_GEN4) == {}

    # Gen3 schedule commands
    await client.async_set_schedule_enabled("s1", True, ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "enableSchedule"})

    await client.async_set_schedule_enabled("s1", False, ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with("s1", {"cmd": "disableSchedule"})

    # Gen4 commands
    await client.async_pause_cleaning("s1", ROBOT_TYPE_GEN4)
    client.async_send_command.assert_awaited_with("s1", {"ability": "cleaning.pause"})

    await client.async_resume_cleaning("s1", ROBOT_TYPE_GEN4)
    client.async_send_command.assert_awaited_with("s1", {"ability": "cleaning.resume"})

    await client.async_stop_cleaning("s1", ROBOT_TYPE_GEN4)
    client.async_send_command.assert_awaited_with("s1", {"ability": "cleaning.cancel"})

    await client.async_return_to_base("s1", ROBOT_TYPE_GEN4)
    client.async_send_command.assert_awaited_with(
        "s1", {"ability": "navigation.return_to_base"}
    )

    await client.async_locate("s1", ROBOT_TYPE_GEN4)
    client.async_send_command.assert_awaited_with(
        "s1", {"ability": "utilities.find_me"}
    )


async def test_start_cleaning_and_spot_cleaning() -> None:
    """Test start cleaning and spot cleaning on Gen3 and Gen4."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())
    client.async_send_command = AsyncMock(return_value={"status": "ok"})  # type: ignore[method-assign]

    # Gen3 start cleaning
    await client.async_start_cleaning("s1", ROBOT_TYPE_GEN3)
    client.async_send_command.assert_awaited_with(
        "s1",
        {
            "cmd": "startCleaning",
            "params": {"category": 4, "mode": 2, "navigationMode": 1},
        },
    )

    # Gen4 start cleaning with map
    await client.async_start_cleaning("s1", ROBOT_TYPE_GEN4, map_id="m-100")
    client.async_send_command.assert_awaited_with(
        "s1",
        {
            "ability": "cleaning.start",
            "runs": [
                {
                    "map": {"rank_id": "m-100", "track_id": None, "nogo_enabled": True},
                    "settings": {"mode": "turbo", "navigation_mode": "normal"},
                }
            ],
        },
    )

    # Gen3 spot cleaning
    await client.async_start_spot_cleaning(
        "s1", ROBOT_TYPE_GEN3, 150, 250, FAN_SPEED_ECO, NAV_MODE_NORMAL
    )
    client.async_send_command.assert_awaited_with(
        "s1",
        {
            "cmd": "startCleaning",
            "params": {
                "category": 3,
                "mode": 1,
                "navigationMode": 1,
                "spotWidth": 150,
                "spotHeight": 250,
            },
        },
    )


class AsyncContextManagerMock:
    """Helper mock for async context managers."""

    def __init__(self, return_value: Any) -> None:
        self.return_value = return_value

    async def __aenter__(self) -> Any:
        return self.return_value

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        pass


async def test_request_error_handling() -> None:
    """Test _request handles HTTP error codes, connection errors, timeouts, and JSON errors."""
    session = MagicMock()
    client = VacuulaApiClient("http://localhost:8085", session)

    # HTTP 404 response
    resp_mock = AsyncMock()
    resp_mock.status = 404
    resp_mock.text.return_value = "Robot not found"
    session.request.return_value = AsyncContextManagerMock(resp_mock)

    with pytest.raises(VacuulaApiError, match="HTTP 404.*Robot not found"):
        await client._request("GET", "/api/robot/s1")

    # ClientError
    session.request.side_effect = aiohttp.ClientConnectionError("Connection refused")
    with pytest.raises(VacuulaApiError, match="Connection error talking to"):
        await client._request("GET", "/api/robot/s1")

    # TimeoutError
    session.request.side_effect = TimeoutError("Request timed out")
    with pytest.raises(VacuulaApiError, match="Connection error talking to"):
        await client._request("GET", "/api/robot/s1")

    # ValueError (invalid JSON)
    resp_mock.status = 200
    resp_mock.json.side_effect = ValueError("Invalid JSON")
    session.request.side_effect = None
    session.request.return_value = AsyncContextManagerMock(resp_mock)
    with pytest.raises(VacuulaApiError, match="Invalid response from"):
        await client._request("GET", "/api/robot/s1")


async def test_sse_event_streaming() -> None:
    """Test SSE generator parsing server events and robot events."""
    session = MagicMock()
    client = VacuulaApiClient("http://localhost:8085", session)

    # Mock server events SSE stream
    class AsyncLineIterator:
        def __init__(self, lines: list[bytes]) -> None:
            self.lines = lines

        def __aiter__(self) -> AsyncLineIterator:
            self._iter = iter(self.lines)
            return self

        async def __anext__(self) -> bytes:
            try:
                return next(self._iter)
            except StopIteration:
                raise StopAsyncIteration from None

    server_lines = [
        b":ping\n",
        b"event: robot_connect\n",
        b'data: {"serial": "s1"}\n',
        b"event: invalid_json\n",
        b"data: bad json\n",
        b"\n",
    ]
    resp_mock = AsyncMock()
    resp_mock.content = AsyncLineIterator(server_lines)
    resp_mock.raise_for_status = MagicMock()
    session.get.return_value = AsyncContextManagerMock(resp_mock)

    events = [item async for item in client.async_iter_server_events()]
    assert events == [("robot_connect", {"serial": "s1"})]

    # Mock robot events SSE stream
    robot_lines = [
        b":ping\n",
        b'data: {"state": 1}\n',
        b"data: corrupt\n",
        b"\n",
    ]
    resp_robot = AsyncMock()
    resp_robot.content = AsyncLineIterator(robot_lines)
    resp_robot.raise_for_status = MagicMock()
    session.get.return_value = AsyncContextManagerMock(resp_robot)

    robot_events = [item async for item in client.async_iter_robot_events("s1")]
    assert robot_events == [{"state": 1}]


async def test_get_map_boundaries_and_runs_edge_cases() -> None:
    """Test boundary and runs retrieval with corrupt, malformed, and non-list payloads."""
    client = VacuulaApiClient("http://localhost:8085", AsyncMock())

    # 1. Gen3 get_map_boundaries: data is None or missing boundaries
    client.async_send_command = AsyncMock(return_value={"data": None})  # type: ignore[method-assign]
    assert await client.async_get_map_boundaries("s1", ROBOT_TYPE_GEN3, "m1") == []

    client.async_send_command = AsyncMock(
        return_value={"data": {"boundaries": "not_a_list"}}
    )  # type: ignore[method-assign]
    assert await client.async_get_map_boundaries("s1", ROBOT_TYPE_GEN3, "m1") == []

    client.async_send_command = AsyncMock(
        return_value={"data": {"boundaries": [{"id": "b1", "name": "Kitchen"}]}}
    )  # type: ignore[method-assign]
    assert await client.async_get_map_boundaries("s1", ROBOT_TYPE_GEN3, "m1") == [
        {"id": "b1", "name": "Kitchen"}
    ]

    # 2. Gen4 get_map_boundaries: server returns error dict or None
    client._request = AsyncMock(return_value={"error": "Map not found"})  # type: ignore[method-assign]
    assert await client.async_get_map_boundaries("s1", ROBOT_TYPE_GEN4, "m1") == []

    client._request = AsyncMock(return_value=[{"id": "b2", "name": "Bedroom"}])  # type: ignore[method-assign]
    assert await client.async_get_map_boundaries("s1", ROBOT_TYPE_GEN4, "m1") == [
        {"id": "b2", "name": "Bedroom"}
    ]

    # 3. async_get_runs: returns [] when server returns non-list
    client._request = AsyncMock(return_value={"error": "no runs"})  # type: ignore[method-assign]
    assert await client.async_get_runs("s1") == []

    # 4. async_get_map_detail & async_get_run_detail: returns {} when server returns non-dict
    client._request = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert await client.async_get_map_detail("s1", "m1") == {}
    assert await client.async_get_run_detail("s1", "r1") == {}


async def test_async_send_command_locking_and_concurrency() -> None:
    """Test that commands to the same robot are serialized by the robot lock."""
    import asyncio

    session = MagicMock()
    client = VacuulaApiClient("http://localhost:8085", session)

    execution_order: list[str] = []

    async def fake_request(method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        tag = kwargs.get("json", {}).get("tag", "unknown")
        execution_order.append(f"start_{tag}")
        await asyncio.sleep(0.05)
        execution_order.append(f"end_{tag}")
        return {"status": "ok", "tag": tag}

    client._request = AsyncMock(side_effect=fake_request)  # type: ignore[method-assign]

    # Concurrent commands to the SAME robot serial -> must be strictly serialized
    task1 = asyncio.create_task(
        client.async_send_command("robot-1", {"cmd": "c1", "tag": "c1"})
    )
    task2 = asyncio.create_task(
        client.async_send_command("robot-1", {"cmd": "c2", "tag": "c2"})
    )
    await asyncio.gather(task1, task2)

    assert execution_order == [
        "start_c1",
        "end_c1",
        "start_c2",
        "end_c2",
    ] or execution_order == [
        "start_c2",
        "end_c2",
        "start_c1",
        "end_c1",
    ]
