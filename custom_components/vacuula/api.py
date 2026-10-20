"""Async API client for Vacuula Server (Gen3 & Gen4 robots)."""
from __future__ import annotations

from typing import Any
import aiohttp

from .const import (
    FAN_SPEED_ECO,
    GEN3_CATEGORY_HOUSE,
    GEN3_MODE_ECO,
    GEN3_MODE_TURBO,
    GEN3_NAV_NORMAL,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)


class VacuulaApiError(Exception):
    """Exception raised for Vacuula API errors."""


class VacuulaApiClient:
    """Async HTTP client for a Vacuula server instance."""

    def __init__(self, base_url: str, session: aiohttp.ClientSession) -> None:
        """Initialize the API client."""
        self.base_url = base_url.rstrip("/")
        self._session = session

    async def async_get_server_info(self) -> dict[str, Any]:
        """GET /api/server - return server metadata."""
        return await self._request("GET", "/api/server")

    async def async_get_robots(self) -> dict[str, dict[str, Any]]:
        """GET /api/robots - return dict of robots keyed by serial."""
        return await self._request("GET", "/api/robots")

    async def async_send_command(self, serial: str, payload: dict[str, Any]) -> dict[str, Any]:
        """POST /api/robot/{serial}/command - send command payload to a connected robot."""
        return await self._request("POST", f"/api/robot/{serial}/command", json=payload)

    async def async_get_robot_state(self, serial: str, robot_type: str) -> dict[str, Any]:
        """Fetch live state from a connected Gen3 or Gen4 robot."""
        if robot_type == ROBOT_TYPE_GEN3:
            return await self.async_send_command(serial, {"cmd": "getRobotState"})
        if robot_type == ROBOT_TYPE_GEN4:
            return await self.async_send_command(serial, {"ability": "state.show"})
        raise VacuulaApiError(f"Unsupported robot type: {robot_type}")

    async def async_start_cleaning(
        self, serial: str, robot_type: str, fan_speed: str = "turbo"
    ) -> dict[str, Any]:
        """Start house cleaning on a Gen3 or Gen4 robot."""
        if robot_type == ROBOT_TYPE_GEN3:
            mode = GEN3_MODE_ECO if fan_speed == FAN_SPEED_ECO else GEN3_MODE_TURBO
            return await self.async_send_command(
                serial,
                {
                    "cmd": "startCleaning",
                    "params": {
                        "category": GEN3_CATEGORY_HOUSE,
                        "mode": mode,
                        "navigationMode": GEN3_NAV_NORMAL,
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
                            "navigation_mode": "normal",
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
