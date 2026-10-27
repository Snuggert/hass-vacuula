"""Async API client for Vacuula Server (Gen3 & Gen4 robots) with per-robot locking and SSE."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from typing import Any
from urllib.parse import quote

import aiohttp

from .const import (
    FAN_SPEED_ECO,
    GEN3_CATEGORY_MAP,
    GEN3_CATEGORY_SPOT,
    GEN3_MODE_ECO,
    GEN3_MODE_TURBO,
    GEN3_NAV_MODE_TO_CODE,
    NAV_MODE_DEEP,
    NAV_MODE_GENTLE,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
    ROBOT_TYPE_GEN4,
)
from .exceptions import VacuulaApiError, VacuulaConnectionError


def _seg(value: Any) -> str:
    """Percent-encode a single URL path segment, rejecting traversal segments."""
    text = str(value)
    if text in ("", ".", ".."):
        raise VacuulaApiError(f"Invalid identifier in request path: {text!r}")
    return quote(text, safe="")


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

    def _resolve_gen3_modes(
        self, fan_speed: str, navigation_mode: str
    ) -> tuple[int, int]:
        """Resolve Gen3 integer mode and navigationMode, enforcing Turbo for Deep."""
        nav_code = GEN3_NAV_MODE_TO_CODE.get(navigation_mode, 1)
        if navigation_mode == NAV_MODE_DEEP or nav_code == 3:
            mode = GEN3_MODE_TURBO
        else:
            mode = GEN3_MODE_ECO if fan_speed == FAN_SPEED_ECO else GEN3_MODE_TURBO
        return mode, nav_code

    async def async_get_server_info(self) -> dict[str, Any]:
        """GET /api/server - return server metadata."""
        return await self._request("GET", "/api/server")

    async def async_get_robots(self) -> dict[str, dict[str, Any]]:
        """GET /api/robots - return dict of robots keyed by serial."""
        return await self._request("GET", "/api/robots")

    async def async_get_maps(self, serial: str) -> list[dict[str, Any]]:
        """GET /api/robot/{serial}/maps - list saved persistent maps / floorplans."""
        res = await self._request("GET", f"/api/robot/{_seg(serial)}/maps")
        return res if isinstance(res, list) else []

    async def async_get_map_detail(self, serial: str, map_id: str) -> dict[str, Any]:
        """GET /api/robot/{serial}/maps/{map_id} - fetch RLE floormap.json."""
        res = await self._request(
            "GET", f"/api/robot/{_seg(serial)}/maps/{_seg(map_id)}"
        )
        return res if isinstance(res, dict) else {}

    async def async_get_map_boundaries(
        self, serial: str, robot_type: str, map_id: str
    ) -> list[dict[str, Any]]:
        """Fetch room zones and No-Go boundaries for a specific map."""
        if robot_type == ROBOT_TYPE_GEN3:
            resp = await self.async_send_command(
                serial,
                {"cmd": "getMapBoundaries", "params": {"mapId": map_id}},
            )
            data = resp.get("data") if isinstance(resp, dict) else None
            boundaries = (
                (data or {}).get("boundaries", []) if isinstance(data, dict) else []
            )
            return boundaries if isinstance(boundaries, list) else []
        res = await self._request(
            "GET", f"/api/robot/{_seg(serial)}/maps/{_seg(map_id)}/boundaries"
        )
        return res if isinstance(res, list) else []

    async def async_set_map_boundaries(
        self,
        serial: str,
        robot_type: str,
        map_id: str,
        boundaries: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Update room zones and No-Go boundaries for a specific map."""
        if robot_type == ROBOT_TYPE_GEN3:
            await self.async_send_command(
                serial,
                {
                    "cmd": "setMapBoundaries",
                    "params": {"mapId": map_id, "boundaries": boundaries},
                },
            )
            return await self.async_get_map_boundaries(serial, robot_type, map_id)
        res = await self._request(
            "POST",
            f"/api/robot/{_seg(serial)}/maps/{_seg(map_id)}/boundaries",
            json={"boundaries": boundaries},
        )
        return res if isinstance(res, list) else boundaries

    async def async_get_runs(self, serial: str) -> list[dict[str, Any]]:
        """GET /api/robot/{serial}/runs - list historical cleaning runs."""
        res = await self._request("GET", f"/api/robot/{_seg(serial)}/runs")
        return res if isinstance(res, list) else []

    async def async_get_run_detail(self, serial: str, run_id: str) -> dict[str, Any]:
        """GET /api/robot/{serial}/run/{run_id} - fetch RLE runmap.json."""
        res = await self._request(
            "GET", f"/api/robot/{_seg(serial)}/run/{_seg(run_id)}"
        )
        return res if isinstance(res, dict) else {}

    async def async_send_command(
        self, serial: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """POST /api/robot/{serial}/command - serialized per robot."""
        async with self._get_lock(serial):
            return await self._request(
                "POST", f"/api/robot/{_seg(serial)}/command", json=payload
            )

    async def async_get_robot_state(
        self, serial: str, robot_type: str
    ) -> dict[str, Any]:
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
        map_id: str | None = None,
    ) -> dict[str, Any]:
        """Start cleaning on a Gen3 or Gen4 robot."""
        if robot_type == ROBOT_TYPE_GEN3:
            mode, nav_code = self._resolve_gen3_modes(fan_speed, navigation_mode)
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

        map_spec = (
            {"rank_id": map_id, "track_id": None, "nogo_enabled": True}
            if map_id
            else None
        )
        return await self.async_send_command(
            serial,
            {
                "ability": "cleaning.start",
                "runs": [
                    {
                        "map": map_spec,
                        "settings": {
                            "mode": fan_speed,
                            "navigation_mode": navigation_mode,
                        },
                    }
                ],
            },
        )

    async def async_start_zone_cleaning(
        self,
        serial: str,
        robot_type: str,
        map_id: str,
        zone_ids: list[str],
        fan_speed: str = "turbo",
        navigation_mode: str = NAV_MODE_NORMAL,
    ) -> dict[str, Any]:
        """Start cleaning one or more room zones on a Gen3 or Gen4 robot."""
        if not zone_ids:
            raise VacuulaApiError("At least one zone ID must be provided")

        if robot_type == ROBOT_TYPE_GEN3:
            mode, nav_code = self._resolve_gen3_modes(fan_speed, navigation_mode)
            if len(zone_ids) == 1:
                params: dict[str, Any] = {
                    "category": GEN3_CATEGORY_MAP,
                    "mode": mode,
                    "navigationMode": nav_code,
                    "mapId": map_id,
                    "boundaryId": zone_ids[0],
                }
            else:
                params = {
                    "category": GEN3_CATEGORY_MAP,
                    "mode": mode,
                    "navigationMode": nav_code,
                    "boundaryIds": zone_ids,
                }
            return await self.async_send_command(
                serial, {"cmd": "startCleaning", "params": params}
            )

        settings = {"mode": fan_speed, "navigation_mode": navigation_mode}
        runs = [
            {
                "map": {"rank_id": map_id, "track_id": zid, "nogo_enabled": True},
                "settings": settings,
            }
            for zid in zone_ids
        ]
        return await self.async_send_command(
            serial, {"ability": "cleaning.start", "runs": runs}
        )

    async def async_start_spot_cleaning(
        self,
        serial: str,
        robot_type: str,
        width: int = 200,
        height: int = 200,
        fan_speed: str = "turbo",
        navigation_mode: str = NAV_MODE_NORMAL,
    ) -> dict[str, Any]:
        """Start spot cleaning on a Gen3 robot."""
        if robot_type != ROBOT_TYPE_GEN3:
            raise VacuulaApiError("Spot cleaning is only supported on Gen3 robots")
        mode, nav_code = self._resolve_gen3_modes(fan_speed, navigation_mode)
        return await self.async_send_command(
            serial,
            {
                "cmd": "startCleaning",
                "params": {
                    "category": GEN3_CATEGORY_SPOT,
                    "mode": mode,
                    "navigationMode": nav_code,
                    "spotWidth": int(width),
                    "spotHeight": int(height),
                },
            },
        )

    async def async_start_map_exploration(
        self, serial: str, robot_type: str
    ) -> dict[str, Any]:
        """Start persistent map exploration on a Gen3 or Gen4 robot."""
        if robot_type == ROBOT_TYPE_GEN3:
            return await self.async_send_command(
                serial, {"cmd": "startPersistentMapExploration"}
            )
        return await self.async_send_command(
            serial,
            {
                "ability": "cleaning.start",
                "runs": [
                    {
                        "map": None,
                        "settings": {
                            "mode": FAN_SPEED_ECO,
                            "navigation_mode": NAV_MODE_GENTLE,
                        },
                    }
                ],
            },
        )

    async def async_pause_cleaning(
        self, serial: str, robot_type: str
    ) -> dict[str, Any]:
        """Pause cleaning."""
        payload = (
            {"cmd": "pauseCleaning"}
            if robot_type == ROBOT_TYPE_GEN3
            else {"ability": "cleaning.pause"}
        )
        return await self.async_send_command(serial, payload)

    async def async_resume_cleaning(
        self, serial: str, robot_type: str
    ) -> dict[str, Any]:
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

    async def async_return_to_base(
        self, serial: str, robot_type: str
    ) -> dict[str, Any]:
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

    async def async_dismiss_alert(
        self, serial: str, robot_type: str = ROBOT_TYPE_GEN3
    ) -> dict[str, Any]:
        """Dismiss current alert on a Gen3 robot."""
        if robot_type != ROBOT_TYPE_GEN3:
            return {}
        return await self.async_send_command(serial, {"cmd": "dismissCurrentAlert"})

    async def async_set_schedule_enabled(
        self, serial: str, enabled: bool, robot_type: str = ROBOT_TYPE_GEN3
    ) -> dict[str, Any]:
        """Enable or disable the schedule on a Gen3 robot."""
        if robot_type != ROBOT_TYPE_GEN3:
            raise VacuulaApiError(
                "Schedule toggle switch is only supported on Gen3 robots"
            )
        cmd = "enableSchedule" if enabled else "disableSchedule"
        return await self.async_send_command(serial, {"cmd": cmd})

    async def async_send_raw_command(
        self, serial: str, command: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send raw command or ability to robot."""
        if "." in command:
            payload: dict[str, Any] = {"ability": command, **(params or {})}
        elif params is not None:
            payload = {"cmd": command, "params": params}
        else:
            payload = {"cmd": command}
        return await self.async_send_command(serial, payload)

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

    async def async_iter_robot_events(
        self, serial: str
    ) -> AsyncGenerator[dict[str, Any]]:
        """Subscribe to GET /api/robot/{serial}/connect SSE stream yielding parsed JSON."""
        url = f"{self.base_url}/api/robot/{_seg(serial)}/connect"
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
        except (aiohttp.ClientError, TimeoutError) as err:
            raise VacuulaConnectionError(
                f"Connection error talking to {url}: {err}"
            ) from err
        except ValueError as err:
            raise VacuulaApiError(f"Invalid response from {url}: {err}") from err
