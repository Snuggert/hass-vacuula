"""DataUpdateCoordinator for Vacuula Server with hybrid SSE push and fallback polling."""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VacuulaApiClient, VacuulaApiError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FAN_SPEED_ECO,
    FAN_SPEED_TURBO,
    GEN3_CATEGORY_HOUSE,
    GEN3_CATEGORY_MAP,
    GEN3_MODE_ECO,
    GEN3_NAV_CODE_TO_NAME,
    NAV_MODE_NORMAL,
    ROBOT_TYPE_GEN3,
)

_LOGGER = logging.getLogger(__name__)


@dataclass
class VacuulaRobotData:
    """Aggregated metadata, live state, and user-selected preferences for a single robot."""

    serial: str
    name: str
    robot_type: str
    connected: bool
    state: dict[str, Any] = field(default_factory=dict)
    preferred_fan_speed: str = FAN_SPEED_TURBO
    preferred_navigation_mode: str = NAV_MODE_NORMAL
    preferred_category: int = GEN3_CATEGORY_MAP

    def sync_preferences_from_state(self) -> None:
        """Seed cleaning preferences from robot state when available."""
        if self.robot_type == ROBOT_TYPE_GEN3 and self.state:
            cleaning = self.state.get("cleaning", {})
            mode = cleaning.get("mode")
            if mode is not None:
                self.preferred_fan_speed = (
                    FAN_SPEED_ECO if mode == GEN3_MODE_ECO else FAN_SPEED_TURBO
                )
            nav_code = cleaning.get("navigationMode")
            if nav_code in GEN3_NAV_CODE_TO_NAME:
                self.preferred_navigation_mode = GEN3_NAV_CODE_TO_NAME[nav_code]
            category = cleaning.get("category")
            if category in (GEN3_CATEGORY_HOUSE, GEN3_CATEGORY_MAP):
                self.preferred_category = category


class VacuulaCoordinator(DataUpdateCoordinator[dict[str, VacuulaRobotData]]):
    """Coordinator managing robot discovery, SSE push streams, and fallback polling."""

    def __init__(self, hass: HomeAssistant, client: VacuulaApiClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client
        self._known_serials: set[str] = set()
        self._new_robot_callbacks: list[Callable[[list[str]], None]] = []
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

    def _notify_new_robots(self, serials: set[str]) -> None:
        """Notify all registered platforms about newly discovered robot serials."""
        new_serials = [s for s in serials if s not in self._known_serials]
        if not new_serials:
            return
        self._known_serials.update(new_serials)
        for cb in list(self._new_robot_callbacks):
            cb(new_serials)

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
                    if event_name == "robots" and isinstance(payload, dict) and self.data is not None:
                        updated = dict(self.data)
                        newly_connected: list[str] = []
                        for serial, meta in payload.items():
                            connected = bool(meta.get("connected", False))
                            robot_type = str(meta.get("type", ""))
                            name = str(meta.get("name", serial))
                            if serial in updated:
                                was_connected = updated[serial].connected
                                updated[serial].connected = connected
                                updated[serial].name = name
                                if connected and not was_connected:
                                    newly_connected.append(serial)
                            else:
                                updated[serial] = VacuulaRobotData(
                                    serial=serial,
                                    name=name,
                                    robot_type=robot_type,
                                    connected=connected,
                                )
                                if connected:
                                    newly_connected.append(serial)

                        self.async_set_updated_data(updated)
                        self._notify_new_robots(set(updated.keys()))
                        self._sync_robot_sse_tasks()
                        for serial in newly_connected:
                            self.hass.async_create_task(self.async_refresh_robot(serial))
            except asyncio.CancelledError:
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Server SSE stream disconnected (%s); retrying in 10s", err)
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
                    # Gen3 SSE frames: {"serial": ..., "event": ..., "data": <state_dict>}
                    if isinstance(frame.get("data"), dict):
                        current.state = frame["data"]
                        current.sync_preferences_from_state()
                        self.async_set_updated_data(dict(self.data))
                    # Gen4 SSE frames: {"serial": ..., "event": {"to": {"service": "state.changed"}, "body": <state_dict>}}
                    elif isinstance(frame.get("event"), dict):
                        ev = frame["event"]
                        if isinstance(ev.get("body"), dict) and "state" in ev["body"]:
                            current.state = {"body": ev["body"]}
                            self.async_set_updated_data(dict(self.data))
            except asyncio.CancelledError:
                return
            except Exception as err:  # noqa: BLE001
                _LOGGER.debug("Robot %s SSE stream disconnected (%s); retrying in 10s", serial, err)
                await asyncio.sleep(10)

    async def async_apply_command_response(
        self, serial: str, response: dict[str, Any] | None
    ) -> None:
        """Update robot state directly from a command response or refresh that robot."""
        if not self.data or serial not in self.data:
            return
        robot = self.data[serial]
        # Gen3 commands return the full updated state payload directly
        if (
            isinstance(response, dict)
            and robot.robot_type == ROBOT_TYPE_GEN3
            and "state" in response
            and "details" in response
        ):
            robot.state = response
            robot.sync_preferences_from_state()
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
        try:
            robots_raw = await self.client.async_get_robots()
        except VacuulaApiError as err:
            raise UpdateFailed(f"Failed to fetch robots from Vacuula: {err}") from err

        previous = self.data or {}

        async def _poll_one(serial: str, meta: dict[str, Any]) -> tuple[str, VacuulaRobotData]:
            connected = bool(meta.get("connected", False))
            robot_type = str(meta.get("type", ""))
            name = str(meta.get("name", serial))
            prev_robot = previous.get(serial)

            robot_data = VacuulaRobotData(
                serial=serial,
                name=name,
                robot_type=robot_type,
                connected=connected,
                state=prev_robot.state if prev_robot else {},
                preferred_fan_speed=(
                    prev_robot.preferred_fan_speed if prev_robot else FAN_SPEED_TURBO
                ),
                preferred_navigation_mode=(
                    prev_robot.preferred_navigation_mode if prev_robot else NAV_MODE_NORMAL
                ),
                preferred_category=(
                    prev_robot.preferred_category if prev_robot else GEN3_CATEGORY_MAP
                ),
            )

            if connected:
                try:
                    robot_data.state = await self.client.async_get_robot_state(
                        serial, robot_type
                    )
                    if prev_robot is None:
                        robot_data.sync_preferences_from_state()
                except VacuulaApiError as err:
                    _LOGGER.warning("Could not query state for %s (%s): %s", name, serial, err)

            return serial, robot_data

        pairs = await asyncio.gather(
            *(_poll_one(serial, meta) for serial, meta in robots_raw.items())
        )
        results = dict(pairs)
        self._notify_new_robots(set(results.keys()))
        self._sync_robot_sse_tasks()
        return results
