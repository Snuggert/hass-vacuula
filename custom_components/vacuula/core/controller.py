"""Pure-Python async controller for Vacuula Server (Zero Home Assistant dependencies)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .client import VacuulaApiClient
from .const import (
    ALL_ZONES_OPTION,
    FAN_SPEED_TURBO,
    GEN3_CATEGORY_MAP,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
)
from .exceptions import VacuulaApiError
from .models import VacuulaRobotData, did_finish_cleaning

_LOGGER = logging.getLogger(__name__)


def build_robot_data(
    serial: str, meta: dict[str, Any], prev: VacuulaRobotData | None = None
) -> VacuulaRobotData:
    """Create a VacuulaRobotData from server metadata while preserving prior cached state."""
    connected = bool(meta.get("connected", False))
    robot_type = str(meta.get("type", ""))
    name = str(meta.get("name", serial))
    installed_with = meta.get("installed_with") or (
        prev.installed_with if prev else None
    )
    return VacuulaRobotData(
        serial=serial,
        name=name,
        robot_type=robot_type,
        connected=connected,
        state=prev.state if prev else {},
        preferred_fan_speed=prev.preferred_fan_speed if prev else FAN_SPEED_TURBO,
        preferred_navigation_mode=(
            prev.preferred_navigation_mode if prev else NAV_MODE_NORMAL
        ),
        preferred_category=prev.preferred_category if prev else GEN3_CATEGORY_MAP,
        selected_zone=prev.selected_zone if prev else ALL_ZONES_OPTION,
        maps=prev.maps if prev else [],
        active_map_id=prev.active_map_id if prev else None,
        active_map_name=prev.active_map_name if prev else None,
        floormap=prev.floormap if prev else None,
        boundaries=prev.boundaries if prev else [],
        zones=prev.zones if prev else [],
        last_run=prev.last_run if prev else None,
        last_run_id=prev.last_run_id if prev else None,
        last_runmap=prev.last_runmap if prev else None,
        total_runs=prev.total_runs if prev else 0,
        maps_loaded=prev.maps_loaded if prev else False,
        installed_with=installed_with,
    )


async def async_poll_robots(
    client: VacuulaApiClient,
    robots_raw: dict[str, dict[str, Any]],
    previous: dict[str, VacuulaRobotData],
) -> tuple[dict[str, VacuulaRobotData], list[str]]:
    """Concurrently poll live state for all connected robots and identify map refresh candidates."""
    need_maps_refresh: list[str] = []

    async def _poll_one(
        serial: str, meta: dict[str, Any]
    ) -> tuple[str, VacuulaRobotData]:
        prev = previous.get(serial)
        robot_data = build_robot_data(serial, meta, prev)

        if robot_data.connected:
            try:
                new_state = await client.async_get_robot_state(
                    serial, robot_data.robot_type
                )
                if prev and did_finish_cleaning(
                    robot_data.robot_type, prev.state, new_state
                ):
                    need_maps_refresh.append(serial)
                robot_data.state = new_state
                if prev is None:
                    robot_data.sync_preferences_from_state()
            except VacuulaApiError as err:
                _LOGGER.warning(
                    "Could not query state for %s (%s): %s",
                    robot_data.name,
                    serial,
                    err,
                )

        if not robot_data.maps_loaded:
            need_maps_refresh.append(serial)

        return serial, robot_data

    pairs = await asyncio.gather(
        *(_poll_one(serial, meta) for serial, meta in robots_raw.items())
    )
    return dict(pairs), need_maps_refresh


def apply_direct_command_response(
    robot: VacuulaRobotData, response: dict[str, Any] | None
) -> bool:
    """Apply a Gen3 direct state response in-place if present, returning True if applied."""
    if (
        isinstance(response, dict)
        and robot.robot_type == ROBOT_TYPE_GEN3
        and "state" in response
        and "details" in response
    ):
        robot.state = response
        robot.sync_preferences_from_state()
        return True
    return False


async def async_load_robot_maps_and_runs(
    client: VacuulaApiClient, robot: VacuulaRobotData
) -> bool:
    """Concurrently fetch maps, active floorplan, boundaries, and run history for a robot."""
    serial = robot.serial
    try:
        maps_res: Any
        runs_res: Any
        maps_res, runs_res = await asyncio.gather(
            client.async_get_maps(serial),
            client.async_get_runs(serial),
            return_exceptions=True,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug("Error fetching maps/runs for %s: %s", serial, err)
        return False

    need_floormap_id: str | None = None
    need_boundaries_id: str | None = None
    need_runmap_id: str | None = None

    if isinstance(maps_res, list):
        robot.maps = maps_res
        active_map = next(
            (
                m
                for m in maps_res
                if m.get("enabled") or m.get("promoted") or m.get("in_maps_list")
            ),
            maps_res[0] if maps_res else None,
        )
        if active_map and active_map.get("id"):
            map_id = str(active_map["id"])
            map_changed = map_id != robot.active_map_id
            robot.active_map_id = map_id
            robot.active_map_name = str(active_map.get("name") or map_id)
            if map_changed or robot.floormap is None:
                need_floormap_id = map_id
            if robot.connected:
                need_boundaries_id = map_id

    if isinstance(runs_res, list):
        robot.total_runs = len(runs_res)
        if runs_res:
            sorted_runs = sorted(
                runs_res,
                key=lambda r: str(
                    r.get("run", {}).get("start_at") or r.get("id") or ""
                ),
            )
            latest_entry = sorted_runs[-1]
            run_id = str(latest_entry.get("id") or "")
            run_obj = latest_entry.get("run")
            robot.last_run = run_obj if isinstance(run_obj, dict) else latest_entry
            if run_id and (run_id != robot.last_run_id or robot.last_runmap is None):
                robot.last_run_id = run_id
                need_runmap_id = run_id

    # Fetch floorplan detail, boundaries, and runmap concurrently in a single RTT
    tasks: dict[str, Any] = {}
    if need_floormap_id:
        tasks["floormap"] = client.async_get_map_detail(serial, need_floormap_id)
    if need_boundaries_id:
        tasks["boundaries"] = client.async_get_map_boundaries(
            serial, robot.robot_type, need_boundaries_id
        )
    if need_runmap_id:
        tasks["runmap"] = client.async_get_run_detail(serial, need_runmap_id)

    if tasks:
        keys = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        fetched = dict(zip(keys, results, strict=False))

        if "floormap" in fetched:
            res = fetched["floormap"]
            if isinstance(res, Exception):
                _LOGGER.debug("Could not fetch floormap %s: %s", need_floormap_id, res)
            elif isinstance(res, dict):
                robot.floormap = res

        if "boundaries" in fetched:
            res = fetched["boundaries"]
            if isinstance(res, Exception):
                _LOGGER.debug("Could not fetch map boundaries for %s: %s", serial, res)
            elif isinstance(res, list):
                robot.boundaries = res
                robot.zones = [
                    b for b in res if b.get("type") == "polygon" and b.get("name")
                ]

        if "runmap" in fetched:
            res = fetched["runmap"]
            if isinstance(res, Exception):
                _LOGGER.debug("Could not fetch runmap %s: %s", need_runmap_id, res)
            elif isinstance(res, dict):
                robot.last_runmap = res

    robot.maps_loaded = True
    # Pre-warm cropped_zones cache
    _ = robot.cropped_zones
    return True


class VacuulaController:
    """Standalone async controller managing Vacuula robot discovery, polling, maps, and commands."""

    def __init__(self, client: VacuulaApiClient) -> None:
        """Initialize the controller."""
        self.client = client
        self.server_info: dict[str, Any] = {}
        self.robots: dict[str, VacuulaRobotData] = {}
        self._listeners: list[Callable[[dict[str, VacuulaRobotData]], None]] = []

    def add_listener(
        self, callback_fn: Callable[[dict[str, VacuulaRobotData]], None]
    ) -> Callable[[], None]:
        """Subscribe to state updates."""
        self._listeners.append(callback_fn)

        def _unsubscribe() -> None:
            if callback_fn in self._listeners:
                self._listeners.remove(callback_fn)

        return _unsubscribe

    def _notify_listeners(self) -> None:
        """Notify all registered listeners with the current robots dictionary."""
        snapshot = dict(self.robots)
        for listener in list(self._listeners):
            listener(snapshot)

    async def async_refresh_all(self) -> dict[str, VacuulaRobotData]:
        """Fetch server info, robot list, and concurrently poll state + maps."""
        if not self.server_info:
            try:
                info = await self.client.async_get_server_info()
                if isinstance(info, dict):
                    self.server_info = info
            except Exception:  # noqa: BLE001
                pass

        robots_raw = await self.client.async_get_robots()
        self.robots, need_maps_refresh = await async_poll_robots(
            self.client, robots_raw, dict(self.robots)
        )

        for serial in set(need_maps_refresh):
            await self.async_refresh_maps_and_runs(serial, notify=False)

        self._notify_listeners()
        return self.robots

    async def async_refresh_robot(self, serial: str) -> VacuulaRobotData | None:
        """Poll state for a single robot."""
        robot = self.robots.get(serial)
        if not robot or not robot.connected:
            return robot
        try:
            state = await self.client.async_get_robot_state(serial, robot.robot_type)
            robot.state = state
            robot.sync_preferences_from_state()
            self._notify_listeners()
        except VacuulaApiError as err:
            _LOGGER.debug("Failed to refresh robot %s: %s", serial, err)
        return robot

    async def async_apply_command_response(
        self, serial: str, response: dict[str, Any] | None
    ) -> None:
        """Update robot state directly from a command response or refresh that robot."""
        robot = self.robots.get(serial)
        if not robot:
            return
        if apply_direct_command_response(robot, response):
            self._notify_listeners()
            return
        await self.async_refresh_robot(serial)

    async def async_refresh_maps_and_runs(
        self, serial: str, *, notify: bool = True
    ) -> None:
        """Fetch persistent maps, active floorplan, boundaries/zones, and run history."""
        robot = self.robots.get(serial)
        if not robot:
            return
        if await async_load_robot_maps_and_runs(self.client, robot) and notify:
            self._notify_listeners()
