"""Shared fixtures and mocks for Vacuula integration tests."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

# Pre-initialize pycares channel so its background daemon thread is present before test thread tracking begins
try:
    import pycares

    _ = pycares.Channel()
except Exception:
    pass

MOCK_SERVER_INFO: dict[str, Any] = {
    "version": "1.0.0",
    "gen4_port": 3443,
    "timezone": "Europe/Amsterdam",
    "utc_offset_minutes": 120,
}

MOCK_ROBOTS: dict[str, Any] = {
    "OPS01234-001122334455": {
        "name": "Mappa",
        "type": "neato.gen3",
        "connected": True,
        "nucleo_url": "http://192.168.1.60:80",
    }
}

MOCK_FLOORMAP: dict[str, Any] = {
    "width": 100,
    "height": 100,
    "rle": [[1, 10000]],
    "dock": {"pixel_x": 10, "pixel_y": 10},
}

MOCK_BOUNDARIES: list[dict[str, Any]] = [
    {
        "id": "bnd-kitchen",
        "name": "Kitchen",
        "type": "polygon",
        "color": "#38bdf8",
        "vertices": [[0.1, 0.1], [0.5, 0.1], [0.5, 0.5], [0.1, 0.5]],
    }
]

MOCK_RUNS: list[dict[str, Any]] = [
    {
        "id": "run-001",
        "run": {
            "status": 1,
            "area": 42.5,
            "duration": 35.0,
            "start_time": "2026-10-24T18:00:00Z",
            "end_time": "2026-10-24T18:35:00Z",
        },
    }
]

MOCK_RUNMAP: dict[str, Any] = {
    "width": 100,
    "height": 100,
    "rle": [[3, 5000], [128, 5000]],
}

MOCK_GEN3_STATE: dict[str, Any] = {
    "state": 1,
    "action": 0,
    "error": None,
    "alert": None,
    "details": {
        "isCharging": False,
        "isDocked": True,
        "charge": 95,
        "isScheduleEnabled": True,
    },
    "availableCommands": {
        "start": True,
        "stop": False,
        "pause": False,
        "resume": False,
        "goToBase": False,
    },
    "meta": {
        "modelName": "BotVacD7Connected",
        "firmware": "4.5.3-189",
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations for all tests."""
    return


@pytest.fixture
def mock_api_client() -> AsyncMock:
    """Return a mocked VacuulaApiClient."""
    client = AsyncMock()
    client.async_get_server_info.return_value = MOCK_SERVER_INFO
    client.async_get_robots.return_value = MOCK_ROBOTS
    client.async_get_maps.return_value = [{"id": "map-001", "name": "Ground Floor"}]
    client.async_get_map_detail.return_value = MOCK_FLOORMAP
    client.async_get_map_boundaries.return_value = MOCK_BOUNDARIES
    client.async_get_runs.return_value = MOCK_RUNS
    client.async_get_run_detail.return_value = MOCK_RUNMAP
    client.async_get_robot_state.return_value = MOCK_GEN3_STATE
    client.async_send_command.return_value = {"result": "ok"}
    client.async_start_cleaning.return_value = {"result": "ok"}
    client.async_start_zone_cleaning.return_value = {"result": "ok"}
    client.async_start_spot_cleaning.return_value = {"result": "ok"}
    client.async_start_map_exploration.return_value = {"result": "ok"}
    client.async_pause_cleaning.return_value = {"result": "ok"}
    client.async_resume_cleaning.return_value = {"result": "ok"}
    client.async_stop_cleaning.return_value = {"result": "ok"}
    client.async_return_to_base.return_value = {"result": "ok"}
    client.async_locate.return_value = {"result": "ok"}
    client.async_dismiss_alert.return_value = {"result": "ok"}
    client.async_set_schedule_enabled.return_value = {"result": "ok"}
    return client
