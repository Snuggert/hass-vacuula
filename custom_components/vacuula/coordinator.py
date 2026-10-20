"""DataUpdateCoordinator for Vacuula Server and robots."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import VacuulaApiClient, VacuulaApiError
from .const import DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


@dataclass
class VacuulaRobotData:
    """Aggregated metadata and live state for a single robot."""

    serial: str
    name: str
    robot_type: str
    connected: bool
    state: dict[str, Any] = field(default_factory=dict)


class VacuulaCoordinator(DataUpdateCoordinator[dict[str, VacuulaRobotData]]):
    """Coordinator managing robot discovery and state polling from Vacuula."""

    def __init__(self, hass: HomeAssistant, client: VacuulaApiClient) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )
        self.client = client

    async def _async_update_data(self) -> dict[str, VacuulaRobotData]:
        """Fetch robot list and poll live state for connected robots."""
        try:
            robots_raw = await self.client.async_get_robots()
        except VacuulaApiError as err:
            raise UpdateFailed(f"Failed to fetch robots from Vacuula: {err}") from err

        results: dict[str, VacuulaRobotData] = {}
        for serial, meta in robots_raw.items():
            connected = bool(meta.get("connected", False))
            robot_type = str(meta.get("type", ""))
            name = str(meta.get("name", serial))
            state: dict[str, Any] = {}

            if connected:
                try:
                    state = await self.client.async_get_robot_state(serial, robot_type)
                except VacuulaApiError as err:
                    _LOGGER.warning("Could not query state for %s (%s): %s", name, serial, err)
                    if self.data and serial in self.data:
                        state = self.data[serial].state

            results[serial] = VacuulaRobotData(
                serial=serial,
                name=name,
                robot_type=robot_type,
                connected=connected,
                state=state,
            )

        return results
