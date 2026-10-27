"""Vacuum platform for Vacuula (Gen3 & Gen4 Neato robots)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.vacuum import (
    Segment,
    StateVacuumEntity,
    VacuumActivity,
    VacuumEntityFeature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import VacuulaConfigEntry
from .const import (
    ALL_ZONES_OPTION,
    FAN_SPEED_TURBO,
    FAN_SPEEDS_GEN3,
    FAN_SPEEDS_GEN4,
    GEN3_ACTION_NAMES,
    ROBOT_TYPE_GEN3,
)
from .coordinator import VacuulaCoordinator, is_installer_outdated
from .entity import VacuulaEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

FEATURE_CLEAN_AREA = getattr(VacuumEntityFeature, "CLEAN_AREA", 16384)

SUPPORTED_FEATURES = (
    VacuumEntityFeature.STATE
    | VacuumEntityFeature.START
    | VacuumEntityFeature.PAUSE
    | VacuumEntityFeature.STOP
    | VacuumEntityFeature.RETURN_HOME
    | VacuumEntityFeature.LOCATE
    | VacuumEntityFeature.FAN_SPEED
)


_ACTIVITY_MAP: dict[str, VacuumActivity] = {
    "error": VacuumActivity.ERROR,
    "paused": VacuumActivity.PAUSED,
    "returning": VacuumActivity.RETURNING,
    "cleaning": VacuumActivity.CLEANING,
    "docked": VacuumActivity.DOCKED,
    "idle": VacuumActivity.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: VacuulaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Vacuula vacuum entities with dynamic robot discovery."""
    coordinator: VacuulaCoordinator = entry.runtime_data

    @callback
    def _async_add_new_robots(serials: list[str]) -> None:
        async_add_entities(VacuulaVacuumEntity(coordinator, s) for s in serials)

    entry.async_on_unload(
        coordinator.register_new_robot_callback(_async_add_new_robots)
    )


class VacuulaVacuumEntity(VacuulaEntity, StateVacuumEntity):
    """Representation of a Neato robot vacuum managed by Vacuula."""

    _attr_name = None

    def __init__(self, coordinator: VacuulaCoordinator, serial: str) -> None:
        """Initialize the vacuum entity."""
        super().__init__(coordinator, serial, "vacuum")

    @property
    def supported_features(self) -> VacuumEntityFeature:
        """Flag supported features for this vacuum dynamically."""
        features = SUPPORTED_FEATURES
        robot = self._robot
        if robot:
            if robot.robot_type == ROBOT_TYPE_GEN3:
                features |= VacuumEntityFeature.CLEAN_SPOT
            if robot.zones:
                features |= FEATURE_CLEAN_AREA
        return features

    @property
    def fan_speed_list(self) -> list[str]:
        """Return the list of available fan speeds for this robot generation."""
        robot = self._robot
        if robot and robot.robot_type == ROBOT_TYPE_GEN3:
            return FAN_SPEEDS_GEN3
        return FAN_SPEEDS_GEN4

    @property
    def activity(self) -> VacuumActivity | None:
        """Return current vacuum activity."""
        robot = self._robot
        if not robot or not robot.state:
            return None
        return _ACTIVITY_MAP.get(robot.activity_state, VacuumActivity.IDLE)

    @property
    def fan_speed(self) -> str | None:
        """Return the currently selected fan speed."""
        robot = self._robot
        return robot.preferred_fan_speed if robot else FAN_SPEED_TURBO

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return generation-specific and map/zone state attributes."""
        robot = self._robot
        if not robot or not robot.state:
            return {}
        zone_names = [str(z.get("name")) for z in robot.zones if z.get("name")]
        zones_payload = [
            {
                "id": str(z["id"]),
                "name": str(z["name"]),
                "map_name": robot.active_map_name,
            }
            for z in robot.zones
            if z.get("id") and z.get("name")
        ]
        maps_payload = [m.get("name") for m in robot.maps if m.get("name")] or (
            [robot.active_map_name] if robot.active_map_name else []
        )
        base_attrs: dict[str, Any] = {
            "navigation_mode": robot.preferred_navigation_mode,
            "active_map_id": robot.active_map_id,
            "active_map_name": robot.active_map_name,
            "available_zones": zone_names,
            "cleanable_zones": zones_payload,
            "maps": maps_payload,
            "selected_zone": robot.selected_zone,
        }
        if robot.robot_type == ROBOT_TYPE_GEN3:
            action_code = int(robot.state.get("action", 0))
            base_attrs.update(
                {
                    "action": GEN3_ACTION_NAMES.get(action_code, str(action_code)),
                    "error": robot.state.get("error"),
                    "alert": robot.state.get("alert"),
                }
            )
            if robot.installed_with:
                base_attrs["installed_with"] = robot.installed_with
                min_ver = self.coordinator.server_info.get("min_installer_version")
                base_attrs["outdated_installer"] = is_installer_outdated(
                    robot.installed_with, min_ver
                )
            return base_attrs

        body = self._gen4_body
        base_attrs.update(
            {
                "action": body.get("action"),
                "errors": body.get("errors"),
            }
        )
        return base_attrs

    async def async_start(self) -> None:
        """Start or resume cleaning (full map/house or selected room zone)."""
        robot = self._robot
        if not robot:
            return
        if self.activity == VacuumActivity.PAUSED:
            resp = await self.coordinator.client.async_resume_cleaning(
                self._serial, robot.robot_type
            )
        elif (
            robot.selected_zone
            and robot.selected_zone != ALL_ZONES_OPTION
            and robot.active_map_id
        ):
            zone_ids = robot.resolve_zone_ids([robot.selected_zone])
            resp = await self.coordinator.client.async_start_zone_cleaning(
                self._serial,
                robot.robot_type,
                robot.active_map_id,
                zone_ids,
                fan_speed=robot.preferred_fan_speed,
                navigation_mode=robot.preferred_navigation_mode,
            )
        else:
            resp = await self.coordinator.client.async_start_cleaning(
                self._serial,
                robot.robot_type,
                fan_speed=robot.preferred_fan_speed,
                navigation_mode=robot.preferred_navigation_mode,
                category=robot.preferred_category,
                map_id=robot.active_map_id,
            )
        await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_pause(self) -> None:
        """Pause the cleaning task."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_pause_cleaning(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_stop(self, **kwargs: Any) -> None:
        """Stop the vacuum cleaner."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_stop_cleaning(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_return_to_base(self, **kwargs: Any) -> None:
        """Set the vacuum cleaner to return to the dock."""
        if robot := self._robot:
            resp = await self.coordinator.client.async_return_to_base(
                self._serial, robot.robot_type
            )
            await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_locate(self, **kwargs: Any) -> None:
        """Locate the vacuum cleaner."""
        if robot := self._robot:
            await self.coordinator.client.async_locate(self._serial, robot.robot_type)

    async def async_set_fan_speed(self, fan_speed: str, **kwargs: Any) -> None:
        """Set preferred fan speed for the next cleaning run."""
        robot = self._robot
        if robot and fan_speed in self.fan_speed_list:
            robot.preferred_fan_speed = fan_speed
            self.coordinator.async_update_listeners()

    async def async_clean_spot(self, **kwargs: Any) -> None:
        """Perform spot cleaning."""
        robot = self._robot
        if not robot:
            return
        width = kwargs.get("width", 200)
        height = kwargs.get("height", 200)
        resp = await self.coordinator.client.async_start_spot_cleaning(
            self._serial,
            robot.robot_type,
            width=width,
            height=height,
            fan_speed=robot.preferred_fan_speed,
            navigation_mode=robot.preferred_navigation_mode,
        )
        await self.coordinator.async_apply_command_response(self._serial, resp)

    async def async_get_segments(self) -> list[Segment]:
        """Return list of cleanable segments (zones/rooms)."""
        robot = self._robot
        if not robot or not robot.zones:
            return []
        return [
            Segment(
                id=str(z.get("id")),
                name=str(z.get("name")),
                group=robot.active_map_name,
            )
            for z in robot.zones
            if z.get("id") and z.get("name")
        ]

    async def async_clean_segments(self, segment_ids: list[str], **kwargs: Any) -> None:
        """Clean selected segments/rooms."""
        robot = self._robot
        if not robot or not robot.zones or not segment_ids or not robot.active_map_id:
            return
        zone_ids = robot.resolve_zone_ids(segment_ids)
        if not zone_ids:
            _LOGGER.warning("No matching zones found for segment_ids: %s", segment_ids)
            return
        map_id = robot.active_map_id
        resp = await self.coordinator.client.async_start_zone_cleaning(
            self._serial,
            robot.robot_type,
            map_id,
            zone_ids,
            fan_speed=robot.preferred_fan_speed,
            navigation_mode=robot.preferred_navigation_mode,
        )
        await self.coordinator.async_apply_command_response(self._serial, resp)
