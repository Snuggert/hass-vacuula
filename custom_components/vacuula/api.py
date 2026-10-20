"""Async API client for Vacuula Server (Gen3 & Gen4 robots) with per-robot locking and SSE."""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
import json
from typing import Any

import aiohttp

from .const import (
    FAN_SPEED_ECO,
    GEN3_CATEGORY_MAP,
    GEN3_MODE_ECO,
    GEN3_MODE_TURBO,
    GEN3_NAV_DEEP,
    GEN3_NAV_NAME_TO_CODE,
    GEN3_NAV_NORMAL,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)


class VacuulaApiError(Exception):
    """Exception raised for Vacuula API errors."""


class VacuulaApiClient:
    """Async HTTP + SSE client for a Vacuula server instance."""

    def __init__(self, base_url: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self.base_url = base_url.rstrip("/")
        self._session = session
        self._robot_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, serial: str) -> asyncio.Lock:
        """Return a per-robot lock so commands/polls never overlap on the robot socket."""
        if serial not in self._robot_locks:
            self._robot_locks[serial] = asyncio.Lock()
        return self._robot_locks[serial]

    async def async_get_server_info(self) -> dict[str, Any]:
        """GET /api/server - return server metadata."""
        return await self._request("GET", "/api/server")

    async def async_get_robots(self) -> dict[str, dict[str, Any]]:
        """GET /api/robots - return dict of robots keyed by serial."""
        return await self._request("GET", "/api/robots")

    async def async_send_command(self, serial: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/robot/{serial}/command - serialized per robot."""
        async with self._get_lock(serial):
            return await self._request(
                "POST", f"/api/robot/{serial}/command", json=payload
            )

    async def async_get_robot_state(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Fetch live state from a connected Gen3 or Gen4 robot."""
        if robot_type == ROBOT_TYPE_GEN3:
            return await self.async_send_command(serial, {"cmd": "getRobotState"})
        if robot_type == ROBOT_TYPE_GEN4:
            return await self.async_send_command(serial, {"ability": "state.show"})
        raise VacuulaApiError(f"Unsupported robot type: {robot_type}")

    async def async_start_cleaning(
        self,
        serial: str,
        robot_type: str,
        fan_speed: str = "turbo",
        navigation_mode: str = NAV_MODE_NORMAL,
        category: int = GEN3_CATEGORY_MAP,
    ) -> dict[str, Any]:
        """Start cleaning on a Gen3 or Gen4 robot."""
        if robot_type == ROBOT_TYPE_GEN3:
            nav_code = GEN3_NAV_NAME_TO_CODE.get(navigation_mode, GEN3_NAV_NORMAL)
            # Neato Gen3 firmware requires Turbo mode (2) when Deep navigation (3) is selected
            if nav_code == GEN3_NAV_DEEP:
                mode = GEN3_MODE_TURBO
            else:
                mode = GEN3_MODE_ECO if fan_speed == FAN_SPEED_ECO else GEN3_MODE_TURBO

            return await self.async_send_command(
                serial,
                {
                    "cmd": "startCleaning",
                    "params": {
                        "category": category,
                        "mode": mode,
                        "navigationMode": nav_code,
                    },
                },
            )

        return await self.async_send_command(
            serial,
            {
                "ability": "cleaning.start",
                "runs": [
                    {
                        "map": None,
                        "settings": {
                            "mode": fan_speed,
                            "navigation_mode": navigation_mode,
                        },
                    }
                ],
            },
        )

    async def async_pause_cleaning(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Pause cleaning."""
        payload = (
            {"cmd": "pauseCleaning"}
            if robot_type == ROBOT_TYPE_GEN3
            else {"ability": "cleaning.pause"}
        )
        return await self.async_send_command(serial, payload)

    async def async_resume_cleaning(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Resume cleaning."""
        payload = (
            {"cmd": "resumeCleaning"}
            if robot_type == ROBOT_TYPE_GEN3
            else {"ability": "cleaning.resume"}
        )
        return await self.async_send_command(serial, payload)

    async def async_stop_cleaning(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Stop cleaning."""
        payload = (
            {"cmd": "stopCleaning"}
            if robot_type == ROBOT_TYPE_GEN3
            else {"ability": "cleaning.cancel"}
        )
        return await self.async_send_command(serial, payload)

    async def async_return_to_base(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Send robot back to its charging base."""
        payload = (
            {"cmd": "sendToBase"}
            if robot_type == ROBOT_TYPE_GEN3
            else {"ability": "navigation.return_to_base"}
        )
        return await self.async_send_command(serial, payload)

    async def async_locate(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Play sound on the robot to locate it."""
        payload = (
            {"cmd": "findMe"}
            if robot_type == ROBOT_TYPE_GEN3
            else {"ability": "utilities.find_me"}
        )
        return await self.async_send_command(serial, payload)

    async def async_dismiss_alert(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Dismiss current alert on a Gen3 robot."""
        if robot_type != ROBOT_TYPE_GEN3:
            return {}
        return await self.async_send_command(serial, {"cmd": "dismissCurrentAlert"})

    async def async_set_schedule_enabled(
        self, serial: str, robot_type: str, enabled: bool
    ) -> dict[str, Any]:
        """Enable or disable the schedule on a Gen3 robot."""
        if robot_type != ROBOT_TYPE_GEN3:
            raise VacuulaApiError("Schedule toggle switch is only supported on Gen3 robots")
        cmd = "enableSchedule" if enabled else "disableSchedule"
        return await self.async_send_command(serial, {"cmd": cmd})

    async def async_iter_server_events(self) -> AsyncGenerator[tuple[str, Any]]:
        """Subscribe to GET /api/events SSE stream yielding (event_name, parsed_data)."""
        url = f"{self.base_url}/api/events"
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=45)
        async with self._session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            event_name = "message"
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("event:"):
                    event_name = line[6:].strip()
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        yield event_name, json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    event_name = "message"

    async def async_iter_robot_events(self, serial: str) -> AsyncGenerator[dict[str, Any]]:
        """Subscribe to GET /api/robot/{serial}/connect SSE stream yielding parsed JSON."""
        url = f"{self.base_url}/api/robot/{serial}/connect"
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=10, sock_read=45)
        async with self._session.get(url, timeout=timeout) as resp:
            resp.raise_for_status()
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if line.startswith("data:"):
                    data_str = line[5:].strip()
                    try:
                        parsed = json.loads(data_str)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(parsed, dict):
                        yield parsed

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Perform an HTTP request against the Vacuula server."""
        url = f"{self.base_url}{path}"
        try:
            async with self._session.request(
                method, url, timeout=aiohttp.ClientTimeout(total=35), **kwargs
            ) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    raise VacuulaApiError(f"HTTP {resp.status} from {url}: {text}")
                return await resp.json(content_type=None)
        except aiohttp.ClientError as err:
            raise VacuulaApiError(f"Connection error talking to {url}: {err}") from err
