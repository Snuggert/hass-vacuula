"""DataUpdateCoordinator for Vacuula Server with hybrid SSE push, maps, zones, and run history."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VacuulaApiClient, VacuulaApiError
from .const import (
    ALL_ZONES_OPTION,
    CONF_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .core.controller import (
    apply_direct_command_response,
    async_load_robot_maps_and_runs,
    async_poll_robots,
)
from .core.models import (
    VacuulaRobotData,
    did_finish_cleaning,
    is_installer_outdated,
    parse_installer_version,
)

_LOGGER = logging.getLogger(__name__)

__all__ = [
    "VacuulaCoordinator",
    "VacuulaRobotData",
    "is_installer_outdated",
    "parse_installer_version",
]


class VacuulaCoordinator(DataUpdateCoordinator[dict[str, VacuulaRobotData]]):
    """Coordinator managing robot discovery, SSE push streams, maps, zones, and fallback polling."""

    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: VacuulaApiClient
    ) -> None:
        self.config_entry = entry
        scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=scan_interval),
        )
        self.client = client
        self.server_info: dict[str, Any] = {}
        self._known_serials: set[str] = set()
        self._known_zones: dict[str, set[str]] = {}
        self._new_robot_callbacks: list[Callable[[list[str]], None]] = []
        self._new_zones_callbacks: list[
            Callable[[str, list[dict[str, Any]]], None]
        ] = []
        self._server_sse_task: asyncio.Task[None] | None = None
        self._robot_sse_tasks: dict[str, asyncio.Task[None]] = {}
        self._stopping = False

    @callback
    def register_new_robot_callback(
        self, cb: Callable[[list[str]], None]
    ) -> Callable[[], None]:
        """Register a callback invoked with new robot serials whenever discovered."""
        self._new_robot_callbacks.append(cb)
        if self._known_serials:
            cb(list(self._known_serials))

        def _remove() -> None:
            if cb in self._new_robot_callbacks:
                self._new_robot_callbacks.remove(cb)

        return _remove

    @callback
    def register_new_zones_callback(
        self, cb: Callable[[str, list[dict[str, Any]]], None]
    ) -> Callable[[], None]:
        """Register a callback invoked when new cleaning zones are discovered for a robot."""
        self._new_zones_callbacks.append(cb)
        if self.data:
            for serial, robot in self.data.items():
                if robot.zones:
                    cb(serial, robot.zones)

        def _remove() -> None:
            if cb in self._new_zones_callbacks:
                self._new_zones_callbacks.remove(cb)

        return _remove

    def _notify_new_robots(self, serials: set[str]) -> None:
        """Notify all registered platforms about newly discovered robot serials."""
        new_serials = [s for s in serials if s not in self._known_serials]
        if not new_serials:
            return
        self._known_serials.update(new_serials)
        for cb in list(self._new_robot_callbacks):
            cb(new_serials)

    def _notify_new_zones(self, serial: str, zones: list[dict[str, Any]]) -> None:
        """Notify registered callbacks about newly discovered zones for a robot."""
        known = self._known_zones.setdefault(serial, set())
        new_zones = [z for z in zones if z.get("id") and str(z["id"]) not in known]
        if not new_zones:
            return
        for z in new_zones:
            known.add(str(z["id"]))
        for cb in list(self._new_zones_callbacks):
            cb(serial, new_zones)

    def _did_finish_cleaning(
        self, robot_type: str, old_state: dict[str, Any], new_state: dict[str, Any]
    ) -> bool:
        """Return True if the robot just transitioned from BUSY to IDLE."""
        return did_finish_cleaning(robot_type, old_state, new_state)

    async def async_refresh_maps_and_runs(self, serial: str) -> None:
        """Fetch persistent maps, active floorplan, boundaries/zones, and run history."""
        if not self.data or serial not in self.data:
            return
        robot = self.data[serial]
        if await async_load_robot_maps_and_runs(self.client, robot):
            if robot.zones:
                self._notify_new_zones(serial, robot.zones)
            self.async_set_updated_data(dict(self.data))

    async def async_set_active_map(self, serial: str, map_id: str) -> bool:
        """Explicitly set the active floor map for a robot and reload its floorplan and boundaries."""
        if not self.data or serial not in self.data:
            return False
        robot = self.data[serial]
        target_map = next(
            (m for m in robot.maps if str(m.get("id")) == str(map_id)), None
        )
        if not target_map:
            return False

        robot.preferred_map_id = str(map_id)
        robot.active_map_id = str(map_id)
        robot.active_map_name = str(target_map.get("name") or map_id)
        robot.selected_zone = ALL_ZONES_OPTION

        tasks: dict[str, Any] = {
            "floormap": self.client.async_get_map_detail(serial, map_id)
        }
        if robot.connected:
            tasks["boundaries"] = self.client.async_get_map_boundaries(
                serial, robot.robot_type, map_id
            )

        keys = list(tasks.keys())
        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        fetched = dict(zip(keys, results, strict=False))

        if "floormap" in fetched and isinstance(fetched["floormap"], dict):
            robot.floormap = fetched["floormap"]
        if "boundaries" in fetched and isinstance(fetched["boundaries"], list):
            robot.boundaries = fetched["boundaries"]
            robot.zones = [
                b
                for b in fetched["boundaries"]
                if b.get("type") == "polygon" and b.get("name")
            ]
            if robot.zones:
                self._notify_new_zones(serial, robot.zones)

        _ = robot.cropped_zones
        self.async_set_updated_data(dict(self.data))
        return True

    def _async_create_background_task(
        self, target: Any, name: str
    ) -> asyncio.Task[Any]:
        """Create a background task tied to config entry if available, falling back to hass."""
        if hasattr(self.config_entry, "async_create_background_task"):
            return self.config_entry.async_create_background_task(
                self.hass, target, name
            )
        return self.hass.async_create_background_task(target, name)

    async def async_start_sse(self) -> None:
        """Start background SSE listeners for server and robot events."""
        self._stopping = False
        if self._server_sse_task is None or self._server_sse_task.done():
            self._server_sse_task = self.hass.async_create_background_task(
                self._listen_server_events(), f"{DOMAIN}_server_sse"
            )
        self._sync_robot_sse_tasks()

    async def async_stop_sse(self) -> None:
        """Stop all background SSE listeners."""
        self._stopping = True
        if self._server_sse_task and not self._server_sse_task.done():
            self._server_sse_task.cancel()
        for task in self._robot_sse_tasks.values():
            if not task.done():
                task.cancel()
        self._robot_sse_tasks.clear()
        await asyncio.sleep(0)

    def _sync_robot_sse_tasks(self) -> None:
        """Ensure an active SSE listener exists for each connected robot."""
        if self._stopping or not self.data:
            return
        for serial, robot in self.data.items():
            existing = self._robot_sse_tasks.get(serial)
            if robot.connected and (existing is None or existing.done()):
                self._robot_sse_tasks[serial] = self.hass.async_create_background_task(
                    self._listen_robot_events(serial),
                    f"{DOMAIN}_robot_sse_{serial}",
                )
            elif not robot.connected and existing and not existing.done():
                existing.cancel()

    async def _listen_server_events(self) -> None:
        """Listen to GET /api/events for robot connect/disconnect/rename events."""
        while not self._stopping:
            try:
                async for event_name, payload in self.client.async_iter_server_events():
                    if (
                        event_name == "robots"
                        and isinstance(payload, dict)
                        and self.data is not None
                    ):
                        updated = dict(self.data)
                        newly_connected: list[str] = []
                        for serial, meta in payload.items():
                            connected = bool(meta.get("connected", False))
                            robot_type = str(meta.get("type", ""))
                            name = str(meta.get("name", serial))
                            installed_with = meta.get("installed_with")
                            if serial in updated:
                                was_connected = updated[serial].connected
                                updated[serial].connected = connected
                                updated[serial].name = name
                                if installed_with is not None:
                                    updated[serial].installed_with = installed_with
                                if connected and not was_connected:
                                    newly_connected.append(serial)
                            else:
                                updated[serial] = VacuulaRobotData(
                                    serial=serial,
                                    name=name,
                                    robot_type=robot_type,
                                    connected=connected,
                                    installed_with=installed_with,
                                )
                                if connected:
                                    newly_connected.append(serial)

                        self.async_set_updated_data(updated)
                        self._notify_new_robots(set(updated.keys()))
                        self._sync_robot_sse_tasks()
                        for serial in newly_connected:
                            self._async_create_background_task(
                                self.async_refresh_robot(serial),
                                f"{DOMAIN}_refresh_robot_{serial}",
                            )
                            self._async_create_background_task(
                                self.async_refresh_maps_and_runs(serial),
                                f"{DOMAIN}_refresh_maps_{serial}",
                            )
            except asyncio.CancelledError:
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "Server SSE stream disconnected (%s); retrying in 10s", err
                )
                await asyncio.sleep(10)

    async def _listen_robot_events(self, serial: str) -> None:
        """Listen to GET /api/robot/{serial}/connect for real-time state pushes."""
        while not self._stopping:
            robot = self.data.get(serial) if self.data else None
            if not robot or not robot.connected:
                return
            try:
                async for frame in self.client.async_iter_robot_events(serial):
                    if not self.data or serial not in self.data:
                        continue
                    current = self.data[serial]
                    old_state = current.state
                    new_state: dict[str, Any] | None = None
                    # Gen3 SSE frames: {"serial": ..., "event": ..., "data": <state_dict>}
                    if isinstance(frame.get("data"), dict) and "state" in frame["data"]:
                        new_state = frame["data"]
                        current.state = new_state
                        current.sync_preferences_from_state()
                        self.async_set_updated_data(dict(self.data))
                    # Gen4 SSE frames: {"serial": ..., "event": {"to": {"service": "state.changed"}, "body": <state_dict>}}
                    elif isinstance(frame.get("event"), dict):
                        ev = frame["event"]
                        if isinstance(ev.get("body"), dict) and "state" in ev["body"]:
                            new_state = {"body": ev["body"]}
                            current.state = new_state
                            self.async_set_updated_data(dict(self.data))

                    if new_state and self._did_finish_cleaning(
                        current.robot_type, old_state, new_state
                    ):
                        self._async_create_background_task(
                            self.async_refresh_maps_and_runs(serial),
                            f"{DOMAIN}_refresh_maps_{serial}",
                        )
            except asyncio.CancelledError:
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug(
                    "Robot %s SSE stream disconnected (%s); retrying in 10s",
                    serial,
                    err,
                )
                await asyncio.sleep(10)
            if not self._stopping:
                await asyncio.sleep(1)

    async def async_apply_command_response(
        self, serial: str, response: dict[str, Any] | None
    ) -> None:
        """Update robot state directly from a command response or refresh that robot."""
        if not self.data or serial not in self.data:
            return
        if apply_direct_command_response(self.data[serial], response):
            self.async_set_updated_data(dict(self.data))
            return
        await self.async_refresh_robot(serial)

    async def async_refresh_robot(self, serial: str) -> None:
        """Poll state for a single robot without re-polling other robots."""
        if not self.data or serial not in self.data:
            return
        robot = self.data[serial]
        if not robot.connected:
            return
        try:
            state = await self.client.async_get_robot_state(serial, robot.robot_type)
        except VacuulaApiError as err:
            _LOGGER.debug("Failed to refresh robot %s: %s", serial, err)
            return
        robot.state = state
        robot.sync_preferences_from_state()
        self.async_set_updated_data(dict(self.data))

    async def _async_update_data(self) -> dict[str, VacuulaRobotData]:
        """Fetch robot list and concurrently poll state for connected robots."""
        if not self.server_info:
            try:
                info = await self.client.async_get_server_info()
                if isinstance(info, dict):
                    self.server_info = info
            except Exception:  # noqa: BLE001
                pass

        try:
            robots_raw = await self.client.async_get_robots()
        except VacuulaApiError as err:
            raise UpdateFailed(f"Failed to fetch robots from Vacuula: {err}") from err

        previous: dict[str, VacuulaRobotData] = getattr(self, "data", None) or {}
        results, need_maps_refresh = await async_poll_robots(
            self.client, robots_raw, previous
        )
        self.data = results

        for serial in set(need_maps_refresh):
            await self.async_refresh_maps_and_runs(serial)

        self._notify_new_robots(set(results.keys()))
        self._sync_robot_sse_tasks()
        return results
