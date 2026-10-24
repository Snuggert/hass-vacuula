"""Button platform for Vacuula robots (Locate, Dismiss Alert, Explore Map, Refresh Maps, Per-Room Zone Clean)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import slugify

from . import VacuulaConfigEntry
from .const import ROBOT_TYPE_GEN3
from .coordinator import VacuulaCoordinator
from .entity import VacuulaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula button entities including dynamic per-room zone clean buttons."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        entities: list[ButtonEntity] = []
        for serial in serials:
            entities.extend(
                [
                    VacuulaLocateButton(coordinator, serial),
                    VacuulaRefreshMapsButton(coordinator, serial),
                    VacuulaExploreMapButton(coordinator, serial),
                ]
            )
            robot = coordinator.data.get(serial)
            if robot and robot.robot_type == ROBOT_TYPE_GEN3:
                entities.append(VacuulaDismissAlertButton(coordinator, serial))
        async_add_entities(entities)

    @callback
    def _async_add_new_zones(serial: str, zones: list[dict[str, Any]]) -> None:
        async_add_entities(
            VacuulaCleanZoneButton(
                coordinator,
                serial,
                str(z["id"]),
                str(z["name"]),
            )
            for z in zones
            if z.get("id") and z.get("name")
        )

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )
    entry.async_on_unload(coordinator.register_new_zones_callback(_async_add_new_zones))


class VacuulaLocateButton(VacuulaEntity, ButtonEntity):
    """Button to trigger the robot's 'Find Me' sound."""

    _attr_name = "Locate"
    _attr_icon = "mdi:volume-high"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the locate button."""
        super().__init__(coordinator, serial, "locate")

    async def async_press(self) -> None:
        """Play locate sound on the robot."""
        if robot := self._robot:
            await self.coordinator.client.async_locate(self._serial, robot.robot_type)


class VacuulaDismissAlertButton(VacuulaEntity, ButtonEntity):
    """Button to dismiss the current alert on a Gen3 robot."""

    _attr_name = "Dismiss alert"
    _attr_icon = "mdi:bell-cancel-outline"

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the dismiss alert button."""
        super().__init__(coordinator, serial, "dismiss_alert")

    async def async_press(self) -> None:
        """Dismiss current alert and update robot state."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_dismiss_alert(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)


class VacuulaRefreshMapsButton(VacuulaEntity, ButtonEntity):
    """Button to reload floor maps, room boundaries, and run history from Vacuula."""

    _attr_name = "Refresh maps"
    _attr_icon = "mdi:map-search-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the refresh maps button."""
        super().__init__(coordinator, serial, "refresh_maps")

    @property
    def available(self) -> bool:
        """Available whenever the Vacuula server is reachable."""
        return bool(self.coordinator.last_update_success and self._robot is not None)

    async def async_press(self) -> None:
        """Trigger a refresh of maps, boundaries, and historical runs."""
        await self.coordinator.async_refresh_maps_and_runs(self._serial)


class VacuulaExploreMapButton(VacuulaEntity, ButtonEntity):
    """Button to start a new persistent map exploration run."""

    _attr_name = "Explore new map"
    _attr_icon = "mdi:compass-outline"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the explore map button."""
        super().__init__(coordinator, serial, "explore_map")

    async def async_press(self) -> None:
        """Start persistent map exploration."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_start_map_exploration(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)


class VacuulaCleanZoneButton(VacuulaEntity, ButtonEntity):
    """One-tap button to clean a specific named room/zone on the robot's floorplan."""

    _attr_icon = "mdi:broom"

    def __init__(
        self,
        coordinator: VacuulaCoordinator,
        serial: str,
        zone_id: str,
        zone_name: str,
    ) -> None:
        """Initialize a room zone clean button."""
        slug = slugify(zone_name) or zone_id[:8]
        super().__init__(coordinator, serial, f"clean_zone_{slug}_{zone_id[:8]}")
        self._zone_id = zone_id
        self._zone_name = zone_name
        self._attr_name = f"Clean {zone_name}"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the boundary ID and map ID for this zone button."""
        robot = self._robot
        return {
            "zone_id": self._zone_id,
            "zone_name": self._zone_name,
            "map_id": robot.active_map_id if robot else None,
        }

    async def async_press(self) -> None:
        """Start cleaning this specific room zone."""
        robot = self._robot
        if not robot or not robot.active_map_id:
            return
        resp = await self.coordinator.client.async_start_zone_cleaning(
            self._serial,
            robot.robot_type,
            robot.active_map_id,
            [self._zone_id],
            fan_speed=robot.preferred_fan_speed,
            navigation_mode=robot.preferred_navigation_mode,
        )
        await self.coordinator.async_apply_command_response(self._serial, resp)
