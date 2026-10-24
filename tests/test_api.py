"""Unit tests for the VacuulaApiClient and error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock

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

    await client.async_get_maps("serial/1")
    client._request.assert_awaited_with("GET", "/api/robot/serial%2F1/maps")

    await client.async_get_map_detail("serial/1", "map/2")
    client._request.assert_awaited_with("GET", "/api/robot/serial%2F1/maps/map%2F2")

    await client.async_get_run_detail("serial/1", "run/9")
    client._request.assert_awaited_with("GET", "/api/robot/serial%2F1/run/run%2F9")


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
